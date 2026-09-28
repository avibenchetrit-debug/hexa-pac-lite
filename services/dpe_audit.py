# -*- coding: utf-8 -*-
"""Recherche DPE / audit à la saisie d'adresse — logique de correspondance du Master (hexa-simulateur-2,
fiabilisée le 22-23/09/2026 : dpe_lookup.py, ademe_geo.py), portée ici avec une règle plus stricte :

    « jamais le voisin » : le remplissage AUTOMATIQUE n'a lieu que s'il y a UN SEUL document dont l'adresse
    est confirmée (même numéro, même suffixe bis/ter, même voie) et que ce n'est pas un appartement / immeuble.
    Sinon (plusieurs documents, adresse non vérifiable, immeuble) l'utilisateur choisit dans #dpe-banner.

Sources : open data ADEME (sans clé) — `dpe03existant` (DPE logements existants) et `audit-opendata`
(audits : une ligne par étape, on ne garde que l'« état initial »). Documents établis depuis le 01/07/2021.
Les valeurs sont renvoyées déjà traduites vers les champs EXISTANTS de la fiche (name=), pour qu'une seule
fonction de remplissage côté page les applique."""
from __future__ import annotations

import json
import math
import re
import unicodedata
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

ADEME_BASE = "https://data.ademe.fr/data-fair/api/v1/datasets"
DPE_DATASET = "dpe03existant"
AUDIT_DATASET = "audit-opendata"
BAN_URL = "https://api-adresse.data.gouv.fr/search/"
RAYON_M = 50                 # recherche géographique autour du point BAN
SEUIL_MEME_BIEN_M = 15.0     # sans numéro exploitable, au-delà ce n'est pas « le même bien »
DATE_MIN = "2021-07-01"      # DPE / audits réformés : les seuls opposables
TAILLE = 20
DELAI_ADEME_S = 12
DELAI_BAN_S = 10
_ENTETES = {"User-Agent": "Mozilla/5.0 (compatible; HexaRenov/1.0)", "Accept": "application/json",
            "Referer": "https://data.ademe.fr/"}


def _get_json(url: str, timeout: float) -> dict:
    """Lecteur réel (remplacé par les tests : aucun service extérieur dans la suite)."""
    req = urllib.request.Request(url, headers=_ENTETES)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


GET = _get_json


# ---------------------------------------------------------------- adresse : normalisation et identité (Master)
_ABREV = {"av": "avenue", "ave": "avenue", "bd": "boulevard", "bld": "boulevard", "boul": "boulevard", "r": "rue",
          "pl": "place", "imp": "impasse", "all": "allee", "ch": "chemin", "che": "chemin", "rte": "route",
          "sq": "square", "pass": "passage", "st": "saint", "ste": "sainte", "crs": "cours"}


def _sans_accents(s: object) -> str:
    x = str(s or "").strip().lower()
    return "".join(c for c in unicodedata.normalize("NFD", x) if unicodedata.category(c) != "Mn")


def normaliser_voie(s: object) -> str:
    x = re.sub(r"[^a-z0-9]+", " ", _sans_accents(s)).strip()
    return " ".join(_ABREV.get(m, m) for m in x.split())


def _numero(val: object) -> tuple[str | None, str]:
    """(numéro sans zéros de tête, suffixe bis/ter/quater) en tête d'une adresse."""
    m = re.match(r"\s*0*(\d+)\s*(bis|ter|quater)?\b", _sans_accents(val))
    return (m.group(1), m.group(2) or "") if m else (None, "")


def voie_du_prospect(adresse: object) -> str:
    """Le libellé de voie seul : on retire le code postal et la ville, puis le numéro (cause racine Master 22/09)."""
    x = normaliser_voie(adresse)
    x = re.split(r"\b\d{5}\b", x)[0].strip()
    return re.sub(r"^0*\d+\s*(bis|ter|quater)?\s*", "", x).strip()


def voies_compatibles(doc_voie: str, prospect_voie: str) -> bool:
    if not doc_voie or not prospect_voie:
        return True
    a, b = set(doc_voie.split()), set(prospect_voie.split())
    return a <= b or b <= a


def _doc_numero(row: dict) -> tuple[str | None, str]:
    num = None
    for k in ("numero_voie_ban", "n_voie_ban"):
        num = _numero(row.get(k))[0]
        if num:
            break
    for k in ("adresse_ban", "n_et_nom_voie_brut", "adresse_brut"):
        n, suffixe = _numero(row.get(k))
        if n and (num is None or n == num):
            return n, suffixe
    return num, ""


def identite(row: dict, adresse_prospect: str) -> str:
    """'veto' (autre adresse), 'adresse_ok' (même n°, même suffixe, même voie) ou 'distance' (non vérifiable)."""
    p_num, p_suf = _numero(adresse_prospect)
    d_num, d_suf = _doc_numero(row)
    if not p_num or not d_num:
        return "distance"
    if p_num != d_num or p_suf != d_suf:
        return "veto"
    d_voie = normaliser_voie(row.get("nom_rue_ban") or row.get("nom_voie_ban") or "")
    if not voies_compatibles(d_voie, voie_du_prospect(adresse_prospect)):
        return "veto"
    return "adresse_ok"


# ---------------------------------------------------------------- lecture d'une ligne ADEME -> champs pac-lite
def _v(row: dict, *cles):
    for k in cles:
        v = row.get(k)
        if v not in (None, ""):
            return v
    return None


def _num(v) -> float | None:
    try:
        return float(str(v).replace(",", ".").replace(" ", ""))
    except (TypeError, ValueError):
        return None


def _date_fr(iso: object) -> str:
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", str(iso or ""))
    return f"{m.group(3)}/{m.group(2)}/{m.group(1)}" if m else ""


def est_immeuble(row: dict) -> bool:
    t = _sans_accents(" ".join(str(row.get(k) or "") for k in ("type_batiment", "methode_application_dpe",
                                                                   "methode_application_dpe_log")))
    return "appartement" in t or "immeuble" in t


def energie_chauffage(label: object) -> str:
    e = _sans_accents(label)
    if any(x in e for x in ("gaz", "propane", "butane", "gpl")):
        return "gaz"
    if "fioul" in e or "fuel" in e:
        return "fioul"
    if "electric" in e:
        return "electricite"
    if any(x in e for x in ("bois", "granule", "biomasse")):
        return "bois"
    return ""          # réseau de chaleur, charbon… : pas d'équivalent dans la fiche, champ laissé tel quel


def niveau_isolation(q: object) -> str:
    """Toit / murs : très bonne|bonne -> bien, moyenne -> peu, insuffisante -> non."""
    q = _sans_accents(q)
    if q in ("tres bonne", "bonne"):
        return "bien"
    if q == "moyenne":
        return "peu"
    if q == "insuffisante":
        return "non"
    return ""


def vitrage(q: object) -> str:
    """Fenêtres : (très) bonne -> double, insuffisante -> simple, moyenne -> vide."""
    q = _sans_accents(q)
    if q in ("tres bonne", "bonne"):
        return "double"
    if q == "insuffisante":
        return "simple"
    return ""


def _hsp(v) -> str:
    n = _num(v)
    if n is None or n <= 0:
        return ""
    return f"{round(n, 2):g}".replace(".", ",")


def candidat(row: dict, kind: str, adresse_prospect: str) -> dict:
    """Un document lisible par la page : identité, libellé du bandeau et valeurs par champ existant."""
    audit = kind == "audit"
    numero = str(_v(row, "n_audit", "numero_rapport_audit") if audit else _v(row, "numero_dpe") or "").strip()
    date_iso = str(_v(row, "date_etablissement_audit") if audit else _v(row, "date_etablissement_dpe") or "")[:10]
    annee_brute = str(_v(row, "annee_construction") or "").strip()
    annee_brute = annee_brute[:-2] if annee_brute.endswith(".0") else annee_brute
    periode = str(_v(row, "periode_constuction", "periode_construction") or "").strip()
    annee = annee_brute if re.fullmatch(r"(1[5-9]|20)\d\d", annee_brute) else ""
    if not annee and annee_brute and not periode:
        periode = annee_brute
    tb = _sans_accents(_v(row, "type_batiment", "methode_application_dpe", "methode_application_dpe_log") or "")
    type_log = "maison" if "maison" in tb else ("appartement" if ("appartement" in tb or "immeuble" in tb) else "")
    ges = _num(_v(row, "emission_ges_5_usages_m2") if audit else
               _v(row, "emission_ges_5_usages_par_m2", "emission_ges_5_usages par_m2"))
    conso = _num(_v(row, "ep_conso_5_usages_m2") if audit else _v(row, "conso_5_usages_par_m2_ep"))
    surface = _num(_v(row, "surface_habitable_logement"))
    niveaux = _num(_v(row, "nb_niveau_logement", "nombre_niveau_logement"))
    classe = str(_v(row, "classe_bilan_dpe") if audit else _v(row, "etiquette_dpe") or "").strip().upper()[:1]
    # coût : chauffage + eau chaude du document (jamais le total 5 usages)
    ch = _num(_v(row, "cout_ch") if audit else _v(row, "cout_chauffage"))
    ecs = _num(_v(row, "cout_ecs"))
    cout = round((ch + ecs) / 12) if ch is not None and ecs is not None and ch + ecs > 0 else None
    toit = next((niveau_isolation(row.get(k)) for k in (
        "qualite_isolation_plancher_haut_comble_perdu", "qualite_isolation_plancher_haut_comble_amenage",
        "qualite_isolation_plancher_haut_toit_terrasse") if row.get(k)), "")
    valeurs = {
        "type_logement": type_log,
        "surface_logement_m2": str(round(surface)) if surface and surface > 0 else "",
        "annee_construction": annee,
        "hsp": _hsp(_v(row, "hauteur_sous_plafond", "hsp")),
        "conso_kwh_m2": str(round(conso)) if conso is not None and conso > 0 else "",
        "emissions_ges": str(round(ges)) if ges is not None and ges >= 0 else "",
        "dpe_connu": classe if re.fullmatch(r"[A-G]", classe) else "",
        "nb_niveaux": str(int(niveaux)) if niveaux and niveaux >= 1 else "",
        "mode_chauffage": energie_chauffage(_v(row, "type_energie_principale_chauffage")),
        "dpe_numero": numero,
        "dpe_date": _date_fr(date_iso),
        "dpe_source": "ademe_audit" if audit else "ademe",
    }
    return {
        "kind": kind, "numero": numero, "date": date_iso, "date_fr": _date_fr(date_iso), "classe": valeurs["dpe_connu"],
        "adresse": str(_v(row, "adresse_ban") or "").strip(),
        "complement": " ".join(str(row.get(k) or "").strip() for k in (
            "complement_adresse_batiment", "complement_adresse_logement") if row.get(k)).strip(),
        "etage": str(_v(row, "numero_etage_appartement", "n_etage_appart") or "").strip(),
        "distance_m": row.get("_distance_m"),
        "identite": identite(row, adresse_prospect),
        "immeuble": est_immeuble(row),
        "periode": periode if not annee else "",
        "valeurs": valeurs,
        "cout_mensuel": cout,
        "isolation": {"toit": toit, "mur": niveau_isolation(row.get("qualite_isolation_murs")),
                      "fenetres": vitrage(row.get("qualite_isolation_menuiseries"))},
    }


# ---------------------------------------------------------------- appels réseau
def _haversine_m(lat1, lon1, lat2, lon2) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = (math.sin(math.radians(lat2 - lat1) / 2) ** 2
         + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2)
    return 6371000.0 * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _distance(row: dict, lat: float, lon: float) -> float | None:
    gp = str(row.get("_geopoint") or "")
    if "," in gp:
        try:
            a, b = (float(x) for x in gp.split(",")[:2])
            return _haversine_m(lat, lon, a, b)
        except ValueError:
            pass
    d = _num(row.get("_geo_distance"))
    return d


def geocoder(adresse: str, cp: str) -> tuple[float | None, float | None, str]:
    """Le point BAN du numéro (là où l'ADEME place ses documents), ou une raison."""
    if not adresse or not re.fullmatch(r"\d{5}", cp or ""):
        return None, None, "adresse ou code postal absent"
    url = BAN_URL + "?" + urllib.parse.urlencode({"q": adresse, "postcode": cp, "limit": 1, "type": "housenumber"})
    try:
        feats = (GET(url, DELAI_BAN_S) or {}).get("features") or []
    except Exception as exc:  # noqa: BLE001
        return None, None, f"géocodage de l'adresse impossible ({exc.__class__.__name__})"
    if not feats:
        return None, None, "adresse introuvable dans la Base Adresse Nationale"
    lon, lat = feats[0]["geometry"]["coordinates"][:2]
    return float(lat), float(lon), ""


def _lignes(dataset: str, lat: float, lon: float, qs: str | None = None) -> list:
    params = {"geo_distance": f"{lon},{lat},{RAYON_M}m", "size": str(TAILLE)}
    if qs:
        params["qs"] = qs
    url = f"{ADEME_BASE}/{dataset}/lines?" + urllib.parse.urlencode(params, quote_via=urllib.parse.quote)
    return (GET(url, DELAI_ADEME_S) or {}).get("results") or []


def _etat_initial(row: dict) -> bool:
    etape, cat = _sans_accents(row.get("etape_travaux")), _sans_accents(row.get("categorie_scenario"))
    if not etape and not cat:
        return True               # schéma sans discriminateur d'étape : état initial (Master)
    return etape == "etat initial" or cat == "etat initial"


def _filtrer(rows: list, kind: str, lat: float, lon: float) -> list:
    champ_date, champ_num = (("date_etablissement_audit", "n_audit") if kind == "audit"
                             else ("date_etablissement_dpe", "numero_dpe"))
    vus, out = set(), []
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        if kind == "audit" and not _etat_initial(row):
            continue                                    # jamais une étape de travaux projetée
        if str(row.get(champ_date) or "")[:10] < DATE_MIN:
            continue
        d = _distance(row, lat, lon)
        if d is None or d > RAYON_M:
            continue
        num = str(row.get(champ_num) or "")
        if num and num in vus:
            continue
        vus.add(num)
        out.append(dict(row, _distance_m=round(d)))
    return out


def rechercher(adresse: str, cp: str, lat: float | None = None, lon: float | None = None,
               type_logement: str = "") -> dict:
    """{etat: auto|choix|aucun|erreur, message, candidats[], retenu, periode}."""
    cp = re.sub(r"\D", "", str(cp or ""))[:5]
    adresse = str(adresse or "").strip()
    if lat is None or lon is None:
        lat, lon, raison = geocoder(adresse, cp)
        if lat is None:
            return {"etat": "erreur", "candidats": [], "retenu": None,
                    "message": f"Recherche DPE / audit impossible : {raison}."}
    erreurs = {}

    def charger(kind):
        try:
            if kind == "audit":
                return _lignes(AUDIT_DATASET, lat, lon, qs='categorie_scenario:"état initial"')
            return _lignes(DPE_DATASET, lat, lon)
        except Exception as exc:  # noqa: BLE001
            erreurs[kind] = exc.__class__.__name__
            return []

    with ThreadPoolExecutor(max_workers=2) as ex:
        brut_dpe, brut_audit = ex.map(charger, ("dpe", "audit"))
    if len(erreurs) == 2:
        return {"etat": "erreur", "candidats": [], "retenu": None,
                "message": "Recherche DPE / audit impossible : l'ADEME ne répond pas pour le moment. "
                           "Réessayez avec « Chercher le DPE »."}
    cands = [candidat(r, "audit", adresse) for r in _filtrer(brut_audit, "audit", lat, lon)]
    cands += [candidat(r, "dpe", adresse) for r in _filtrer(brut_dpe, "dpe", lat, lon)]
    cands = [c for c in cands if c["identite"] != "veto"]                     # l'autre adresse ne revient jamais
    for c in cands:
        c["proche"] = c["identite"] == "adresse_ok" or (c["distance_m"] or 0) <= SEUIL_MEME_BIEN_M
    # ordre du bandeau : adresse confirmée, puis la plus proche ; à égalité l'audit, puis le plus récent
    cands.sort(key=lambda c: c["date"], reverse=True)
    cands.sort(key=lambda c: (c["identite"] != "adresse_ok", c["distance_m"] or 0, c["kind"] != "audit"))
    note = ""
    if erreurs:
        note = " (les " + ("audits" if "audit" in erreurs else "DPE") + " n'ont pas pu être consultés)"
    confirmes = [c for c in cands if c["identite"] == "adresse_ok"]
    appart = "appart" in _sans_accents(type_logement)
    if confirmes and not appart and not any(c["immeuble"] for c in confirmes):
        # Même logement (adresse confirmée, hors appartement) : le PLUS RÉCENT gagne ; à date égale seulement, l'audit.
        c = max(confirmes, key=lambda x: (x["date"], x["kind"] == "audit"))
        doc = f"{'Audit' if c['kind'] == 'audit' else 'DPE'} n° {c['numero']} du {c['date_fr']}"
        if len(confirmes) == 1:
            msg = f"{doc} trouvé à cette adresse"
        elif any(x is not c and x["date"] == c["date"] for x in confirmes):
            msg = f"{doc} retenu (même date qu'un autre document : l'audit prime)"
        else:
            msg = f"{doc} retenu, le plus récent des {len(confirmes)} documents à cette adresse"
        return {"etat": "auto", "candidats": cands, "retenu": cands.index(c),
                "message": f"{msg} : valeurs pré-remplies, à confirmer avec le client{note}."}
    if not cands:
        return {"etat": "aucun", "candidats": [], "retenu": None,
                "message": f"Aucun DPE ni audit établi depuis le 01/07/2021 à cette adresse : saisie manuelle{note}."}
    if any(c["immeuble"] for c in cands) or appart:
        motif = ("Immeuble / appartement : plusieurs logements peuvent partager cette adresse. "
                 "Choisissez le document du logement du client (étage, complément, surface)")
    elif len(confirmes) > 1:
        motif = f"{len(confirmes)} documents trouvés à cette adresse : choisissez celui du logement du client"
    else:
        motif = "Aucun document à l'adresse exacte, seulement à proximité : vérifiez avant de choisir"
    return {"etat": "choix", "candidats": cands, "retenu": None, "message": motif + note + "."}
