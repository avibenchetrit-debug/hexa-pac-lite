# -*- coding: utf-8 -*-
"""Valeur verte : effet du gain de classe DPE sur la valeur du bien (Lot 13).

Données : « Valeur verte des logements : écarts de prix par étiquette DPE (610 000 ventes DVF x ADEME) »
(data.gouv.fr / france-dpe.fr), dans data/valeur_verte/ : écart de prix au m² de chaque classe par rapport
à la classe D (D = 0), par type de bien, en France et par département.

Valeur verte = valeur du bien × (écart[classe après] − écart[classe avant]), une seule source par calcul : le
département s'il a un écart pour la classe avant ET pour la classe après, sinon la France pour les deux. Garde-fou :
une classe qui s'améliore ne donne jamais une valeur négative (département -> France ; sinon pas de valeur verte).
Fourchette ± 30 % (admin). Montants arrondis à la centaine.

Version serveur de window.HexaValeurVerte (templates/index.html, bloc HEXA-VALEUR-VERTE) ; les deux sont
tenues identiques par tests/test_lot13_valeur_verte.py."""
import csv
import functools
import os

from services import dpe_estime
from services.economies import _arrondi, _num

DOSSIER = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "valeur_verte")
CLASSES = dpe_estime.CLASSES


@functools.lru_cache(maxsize=1)
def table():
    """{'france': {type_bien: {classe: %}}, 'departements': {dep: {type_bien: {classe: %}}}}"""
    out = {"france": {}, "departements": {}}
    with open(os.path.join(DOSSIER, "decote-dpe-par-classe-france.csv"), encoding="utf-8") as f:
        for r in csv.DictReader(f):
            out["france"].setdefault(r["type_bien"], {})[r["classe_dpe"]] = float(r["ecart_prix_m2_pct_vs_d"])
    with open(os.path.join(DOSSIER, "decote-dpe-par-departement.csv"), encoding="utf-8") as f:
        for r in csv.DictReader(f):
            out["departements"].setdefault(r["departement"], {}).setdefault(r["type_bien"], {})[r["classe_dpe"]] = \
                float(r["ecart_prix_m2_pct_vs_d"])
    return out


def type_bien(type_logement):
    return "appartement" if "appart" in str(type_logement or "").lower() else "maison"


def departement(cp):
    cp = "".join(ch for ch in str(cp or "") if ch.isdigit())[:5]
    if len(cp) < 2:
        return ""
    return cp[:3] if cp.startswith("97") else cp[:2]


def ecarts(tab, dep, tb, classe_avant, classe_apres):
    """Écarts (%) par classe d'UNE seule source, et cette source ('departement' | 'france') : le département
    s'il a un écart pour la classe avant ET la classe après (D = 0 partout), sinon la France pour les deux."""
    fr = (tab.get("france") or {}).get(tb) or {}
    dp = ((tab.get("departements") or {}).get(dep) or {}).get(tb) or {}
    a = lambda src, c: c == "D" or c in src  # noqa: E731
    src, nom = (dp, "departement") if dep and a(dp, classe_avant) and a(dp, classe_apres) else (fr, "france")
    return {c: 0.0 if c == "D" else src.get(c, 0.0) for c in CLASSES}, nom


def libelle_ecarts(source, dep):
    return f"Source : département {dep}" if source == "departement" else "Source : France entière"


def valeur_bien(valeur_bien_estimee, prix_m2_estime, surface):
    """Valeur du bien de la fiche ; à défaut prix au m² DVF × surface."""
    v = _num(valeur_bien_estimee, 0) or 0
    if v > 0:
        return v
    return (_num(prix_m2_estime, 0) or 0) * (_num(surface, 0) or 0)


def calculer(valeur, classe_avant, classe_apres, ec, fourchette_pct=30):
    valeur = _num(valeur, 0) or 0
    if valeur <= 0:
        return {"ok": False, "raison": "valeur"}
    ok = all(isinstance(c, str) and len(c) == 1 and c in CLASSES for c in (classe_avant, classe_apres))
    if not ok or CLASSES.index(classe_apres) >= CLASSES.index(classe_avant):
        return {"ok": False, "raison": "classe"}
    ecart = ec[classe_apres] - ec[classe_avant]
    if ecart <= 0:
        return {"ok": False, "raison": "ecart"}
    vv = valeur * ecart / 100
    f = (_num(fourchette_pct, 30) or 0) / 100
    return {"ok": True, "valeur": _arrondi(vv / 100) * 100, "min": _arrondi(vv * (1 - f) / 100) * 100,
            "max": _arrondi(vv * (1 + f) / 100) * 100, "ecart_pct": dpe_estime._r1(ecart),
            "ecart_avant": ec[classe_avant], "ecart_apres": ec[classe_apres]}


def projet(entree, res, params, tab=None):
    """Valeur verte d'un projet. entree : valeur_bien, classe_dpe_avant, dpe_connu, surface, cp,
    type_logement, personnes, ecs_chaudiere. res : calculer_economies()."""
    tab = tab if tab is not None else table()
    est = dpe_estime.estimer(res, entree.get("surface"), entree.get("personnes"), entree.get("ecs_chaudiere"), params)
    cls = dpe_estime.classes_projet(dpe_estime.classe_reelle(entree.get("classe_dpe_avant"), entree.get("dpe_connu")), est)
    if not cls.get("ok"):
        return {"ok": False, "raison": "economies"}
    dep, tb, av, ap = departement(entree.get("cp")), type_bien(entree.get("type_logement")), cls["classe_avant"], cls["classe_apres"]
    fourchette = dpe_estime.params_dpe(params)["valeur_verte_fourchette_pct"]
    ec, source = ecarts(tab, dep, tb, av, ap)
    r = calculer(entree.get("valeur_bien"), av, ap, ec, fourchette)
    if r.get("raison") == "ecart" and source == "departement":    # garde-fou : jamais négative -> France
        ec, source = ecarts(tab, "", tb, av, ap)
        r = calculer(entree.get("valeur_bien"), av, ap, ec, fourchette)
    r.update({"classe_avant": cls["classe_avant"], "classe_apres": cls["classe_apres"], "dpe_reel": cls["dpe_reel"],
              "libelle_classes": f"Classe {cls['classe_avant']} → {cls['classe_apres']}",
              "libelle_source": "(DPE réel)" if cls["dpe_reel"] else "(classe estimée)",
              "source_ecarts": source, "libelle_ecarts": libelle_ecarts(source, dep)})
    return r


# ---------------------------------------------------------------- Lot 13e : les 3 tuiles (fiche, pré-devis, devis)
NBSP = " "


def eur(n):
    """« 32 900 € » : espaces insécables dans les milliers et avant « € » (jamais coupé)."""
    n = _arrondi(n)
    return ("-" if n < 0 else "") + f"{abs(n):,}".replace(",", NBSP) + NBSP + "€"


def tuiles(eco, vv, duree):
    """Contenu des tuiles Économies d'énergie / Valeur verte / Gain total, identique sur la fiche et les documents.
    eco : None (facture inconnue) ou {avant_mensuel, apres_mensuel, total (cumul net sur la durée, None si non
    rentable), rentabilite (texte)} ; vv : projet() ou None. La valeur verte est TOUJOURS le bas de la fourchette.
    Chaque tuile : {cle, titre, pre, montant, details: [{cle, texte, fort?}]}."""
    vv_ok = bool(vv and vv.get("ok"))
    eco20 = _arrondi(eco["total"]) if eco and eco.get("total") is not None else None
    if eco:
        mois = _arrondi(eco["avant_mensuel"]) - _arrondi(eco["apres_mensuel"])
        details = [{"cle": "facture", "texte": f"{eur(eco['avant_mensuel'])} → {eur(eco['apres_mensuel'])}/mois"}]
        if eco20 is not None:
            details.append({"cle": "total20", "fort": eur(eco20), "texte": f" sur {duree} ans"})
        if eco.get("rentabilite"):
            details.append({"cle": "rent", "texte": eco["rentabilite"]})
        t_eco = {"cle": "eco", "titre": "Économies d'énergie", "pre": "", "montant": f"{eur(mois)}/mois",
                 "details": details, "alerte": mois < 0}
    else:
        t_eco = {"cle": "eco", "titre": "Économies d'énergie", "pre": "", "montant": "—",
                 "details": [{"cle": "facture", "texte": "facture inconnue"}], "alerte": False}
    out = [t_eco]
    if vv_ok:
        out.append({"cle": "vv", "titre": "Valeur verte", "pre": "à partir de", "montant": eur(vv["min"]),
                    "details": [{"cle": "classes", "texte": vv["libelle_classes"]},
                                {"cle": "source", "texte": vv["libelle_source"]},
                                {"cle": "ecarts", "texte": vv["libelle_ecarts"]}], "alerte": False})
    if eco20 is None:
        total = {"pre": "", "montant": "—",
                 "details": [{"cle": "dont", "texte": f"au-delà de {duree} ans" if eco else "facture inconnue"}]}
    else:
        dont = f"dont {eur(eco20)} d'économies d'énergie" + (
            f" + à partir de {eur(vv['min'])} de valeur verte" if vv_ok else " (valeur verte non estimée)")
        total = {"pre": "à partir de" if vv_ok else "", "montant": eur(eco20 + (vv["min"] if vv_ok else 0)),
                 "details": [{"cle": "dont", "texte": dont}]}
    out.append(dict(total, cle="total", titre=f"Gain total sur {duree} ans", alerte=False))
    return out
