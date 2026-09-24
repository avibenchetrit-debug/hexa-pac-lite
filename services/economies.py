# -*- coding: utf-8 -*-
"""Économies d'énergie et facture après PAC (Lot 2).

Principe : on part de ce que le client paie aujourd'hui (facture annuelle A), on en déduit
le besoin de chaleur réel de la maison, puis ce que coûtera ce même besoin avec la PAC.

Ce module est la version serveur (devis / pré-devis) de calculerEconomies() dans
templates/index.html (bloc HEXA-ECONOMIES). Les deux sont tenues identiques par
tests/test_lot2_economies.py, qui rejoue les mêmes cas sur les deux implémentations.
Fonctions pures : aucune lecture de fichier, aucun état.
"""
import math
import re

# Valeurs par défaut des hypothèses (Admin → « Hypothèses économie d'énergie »).
DEFAULT_PARAMS = {
    "conso_zone_kwh_m2_an": {"h1": 150, "h2": 130, "h3": 110},
    "scop_defaut": 3.5,
    "prix_kwh": {"electricite": 0.21, "gaz": 0.12, "fioul": 0.13, "bois": 0.07},
    "inflation_annuelle_pct": {"electricite": 3, "gaz": 4, "fioul": 4, "bois": 2.5, "defaut": 4},
    "duree_vie_pac_ans": 20,
    # Lot 2
    "rendement_pct": {"fioul": 85, "gaz": 90, "bois": 75, "electricite": 100, "pac": 250},
    "ecs_kwh_par_personne": 800,
    "cop_ecs_duo": 2.5,
    "cop_ecs_cet": 2.8,
    "coef_periode": {"avant_1975": 1.3, "1975_2000": 1.0, "apres_2000": 0.7, "inconnue": 1.0},
}

# Rendement d'un ballon électrique existant (ECS actuelle quand la chaudière ne la fait pas).
RENDEMENT_BALLON_ELECTRIQUE = 0.9
# Nombre de personnes retenu quand la fiche ne le précise pas.
PERSONNES_DEFAUT = 2
# Part maximale de l'ECS dans la facture de la chaudière.
PLAFOND_PART_ECS = 0.30

SOURCES = ("reel", "a_confirmer", "audit", "dpe", "estime")


def _num(v, defaut=None):
    try:
        if v is None or (isinstance(v, str) and not v.strip()):
            return defaut
        return float(str(v).replace(",", ".").replace(" ", "").replace(" ", ""))
    except (TypeError, ValueError):
        return defaut


def _arrondi(x):
    """Arrondi au plus proche, demi vers le haut (= Math.round du JS)."""
    return int(math.floor(x + 0.5))


def params_complets(params):
    """Hypothèses admin complétées par les valeurs par défaut (fusion clé par clé)."""
    out = {}
    params = params if isinstance(params, dict) else {}
    for k, d in DEFAULT_PARAMS.items():
        v = params.get(k)
        if isinstance(d, dict):
            fusion = dict(d)
            if isinstance(v, dict):
                fusion.update({kk: vv for kk, vv in v.items() if _num(vv) is not None})
            out[k] = fusion
        else:
            out[k] = v if _num(v) is not None else d
    return out


def cle_energie(mode_chauffage):
    """mode_chauffage de la fiche -> clé des hypothèses (fioul, gaz, bois, electricite, pac)."""
    e = str(mode_chauffage or "").strip().lower()
    if not e:
        return None
    if e.startswith("pac") or "pompe" in e:
        return "pac"
    if "fioul" in e or "fuel" in e:
        return "fioul"
    if "gaz" in e or "gpl" in e or "propane" in e or "butane" in e:
        return "gaz"
    if "bois" in e or "granul" in e or "biomasse" in e:
        return "bois"
    if "elec" in e or "élec" in e:
        return "electricite"
    return None


def _prix(p, energie):
    cle = "electricite" if energie in ("pac", "electricite") else energie
    return _num(p["prix_kwh"].get(cle), 0) or 0


def _inflation(p, energie):
    infl = p["inflation_annuelle_pct"]
    cle = "electricite" if energie in ("pac", "electricite") else energie
    v = _num(infl.get(cle))
    if v is None:
        v = _num(infl.get("defaut"), 4)
    return v / 100


def periode_construction(annee):
    """Année (« 1968 ») ou période texte du DPE (« 1948-1974 », « avant 1948 », « après 2021 »)
    -> clé de coef_periode. Lecture seule de la valeur de la fiche."""
    s = str(annee or "").strip().lower()
    annees = [int(a) for a in re.findall(r"(1[5-9]\d\d|20\d\d)", s)]
    if not annees:
        return "inconnue"
    if "avant" in s:
        ref = min(annees) - 1
    elif "apr" in s:
        ref = max(annees) + 1
    else:
        ref = max(annees)  # une période « 1948-1974 » se classe par sa borne haute
    if ref < 1975:
        return "avant_1975"
    if ref <= 2000:
        return "1975_2000"
    return "apres_2000"


def ecs_par_chaudiere(ecs_fiche, energie):
    """La chaudière actuelle produit-elle l'ECS ? Champ « ecs » de la fiche.
    Non renseigné -> oui (hypothèse prudente : on retire l'ECS de la part chauffage)."""
    v = str(ecs_fiche or "").strip().lower()
    if not v:
        return True
    return v == "chaudiere" or (energie is not None and v == energie)


def scop_modele(etas35, etas55, emetteur, service, params):
    """SCOP du modèle choisi (ETAS × 2,5 / 100, comme le dimensionnement), sinon scop_defaut."""
    p = params_complets(params)
    etas = _num(etas35, 0) if (emetteur == "plancher_chauffant" and service == "chauffage_seul") else _num(etas55, 0)
    scop = (etas / 100) * 2.5 if etas and etas > 0 else 0
    return scop if scop > 0 else (_num(p["scop_defaut"], 3.5) or 3.5)


def estimer_facture_annuelle(surface_chauffee, zone, annee, energie, ecs_chaudiere, personnes, params):
    """Estimation de la facture annuelle de la chaudière quand rien n'est connu (source « estime »).
    Renvoie None si la surface ou l'énergie manque (jamais de valeur inventée)."""
    p = params_complets(params)
    energie = cle_energie(energie)
    surface = _num(surface_chauffee, 0) or 0
    if surface <= 0 or not energie:
        return None
    z = str(zone or "").lower()
    zr = "h1" if z.startswith("h1") else ("h3" if z.startswith("h3") else "h2")
    conso = _num(p["conso_zone_kwh_m2_an"].get(zr), 130) or 130
    coef = _num(p["coef_periode"].get(periode_construction(annee)), 1.0) or 1.0
    rend = (_num(p["rendement_pct"].get(energie), 100) or 100) / 100
    prix = _prix(p, energie)
    besoin = surface * conso * coef
    facture = besoin / rend * prix
    if ecs_chaudiere:
        n = _num(personnes) or PERSONNES_DEFAUT
        facture += n * _num(p["ecs_kwh_par_personne"], 800) / rend * prix
    return round(facture, 2)


def calculer_economies(entree, params):
    """Calcul des économies (Lot 2 §2). entree : dict
        facture_annuelle   A, € TTC/an payés aujourd'hui à la chaudière
        energie            mode_chauffage de la fiche
        ecs_chaudiere      bool : la chaudière fait-elle l'ECS ?
        personnes          nombre de personnes du foyer
        service            'chauffage_seul' | 'chauffage_ecs'
        ballon             bool : ballon thermodynamique retenu (chauffage seul)
        scop               SCOP du modèle (sinon scop_defaut)
    Renvoie {'ok': False, 'raison': …} si le calcul est impossible (jamais de valeur inventée)."""
    p = params_complets(params)
    A = _num(entree.get("facture_annuelle"), 0) or 0
    energie = cle_energie(entree.get("energie"))
    if A <= 0:
        return {"ok": False, "raison": "facture"}
    if not energie:
        return {"ok": False, "raison": "energie"}
    n = _num(entree.get("personnes")) or PERSONNES_DEFAUT
    ecs_chaudiere = bool(entree.get("ecs_chaudiere"))
    service = str(entree.get("service") or "chauffage_seul")
    duo = service in ("chauffage_ecs", "chauffage+ecs")
    ballon = bool(entree.get("ballon")) and not duo
    scop = _num(entree.get("scop"), 0) or _num(p["scop_defaut"], 3.5) or 3.5

    rend = (_num(p["rendement_pct"].get(energie), 100) or 100) / 100
    prix = _prix(p, energie)
    prix_elec = _num(p["prix_kwh"].get("electricite"), 0.21) or 0.21
    kwh_ecs = n * (_num(p["ecs_kwh_par_personne"], 800) or 0)

    # a) part ECS dans la facture (si la même chaudière la produit), plafonnée à 30 %
    ecs_avant = min(kwh_ecs / rend * prix, PLAFOND_PART_ECS * A) if ecs_chaudiere else 0.0
    # b) c) d) chauffage seul, avant -> besoin -> après
    chauffage_avant = A - ecs_avant
    besoin = chauffage_avant / prix * rend if prix > 0 else 0.0
    chauffage_apres = besoin / scop * prix_elec
    # f) ECS : comptée seulement si réellement traitée (PAC DUO ou ballon thermodynamique)
    cop_ecs = (_num(p["cop_ecs_duo"], 2.5) if duo else _num(p["cop_ecs_cet"], 2.8)) if (duo or ballon) else None
    ecs_traitee = cop_ecs is not None and cop_ecs > 0
    ecs_actuelle = (ecs_avant if ecs_chaudiere else kwh_ecs / RENDEMENT_BALLON_ELECTRIQUE * prix_elec) if ecs_traitee else 0.0
    ecs_apres = kwh_ecs / cop_ecs * prix_elec if ecs_traitee else 0.0

    avant = chauffage_avant + ecs_actuelle
    apres = chauffage_apres + ecs_apres
    infl_energie = _inflation(p, energie)
    infl_elec = _inflation(p, "electricite")
    return {
        "ok": True,
        "energie": energie,
        "facture_annuelle": round(A, 2),
        "ecs_avant": round(ecs_avant, 2),
        "chauffage_avant": round(chauffage_avant, 2),
        "besoin_kwh": round(besoin, 1),
        "chauffage_apres": round(chauffage_apres, 2),
        "ecs_traitee": ecs_traitee,
        "ecs_actuelle": round(ecs_actuelle, 2),
        "ecs_apres": round(ecs_apres, 2),
        "economie_chauffage": round(chauffage_avant - chauffage_apres, 2),
        "economie_ecs": round(ecs_actuelle - ecs_apres, 2),
        "avant_annuel": round(avant, 2),
        "apres_annuel": round(apres, 2),
        "economie_annuelle": round(avant - apres, 2),
        "avant_mensuel": _arrondi(avant / 12),
        "apres_mensuel": _arrondi(apres / 12),
        "scop": round(scop, 2),
        "inflation_avant": infl_energie,
        # l'ECS actuelle d'un ballon électrique suit le prix de l'électricité
        "inflation_ecs_avant": infl_energie if ecs_chaudiere else infl_elec,
        "inflation_apres": infl_elec,
        "duree_ans": _arrondi(_num(p["duree_vie_pac_ans"], 20) or 20),
        # h) garde-fou, jamais bloquant
        "alerte": apres > avant or apres < 0.2 * avant,
    }


MENTION_BASE = {
    "reel": "votre facture déclarée",
    "a_confirmer": "les informations communiquées",
    "dpe": "les données théoriques du DPE",
    "audit": "les données théoriques de l'audit énergétique",
    "estime": "une estimation selon les caractéristiques du logement",
}


def source_effective(source, montant_present):
    """Source du coût enregistrée dans le lead. Lead antérieur au Lot 2 (un coût mais pas de
    source) -> « a_confirmer »."""
    s = str(source or "").strip()
    if s in SOURCES:
        return s
    return "a_confirmer" if montant_present else ""


def mention_devis(source, resultat):
    """Mention obligatoire sous les économies du devis / pré-devis."""
    base = MENTION_BASE.get(source) or MENTION_BASE["estime"]
    hausse = round((resultat.get("inflation_avant") or 0) * 100, 1)
    hausse_txt = (f"{hausse:.1f}".rstrip("0").rstrip(".")).replace(".", ",")
    scop_txt = f"{resultat.get('scop', 0):.1f}".replace(".", ",")
    return (f"Estimation indicative calculée sur {base}, prix de l'énergie actuels + hausse de "
            f"{hausse_txt} %/an, SCOP {scop_txt}. Les économies réelles dépendent de l'usage et du climat.")
