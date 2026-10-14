# -*- coding: utf-8 -*-
"""Valeur verte : effet du gain de classe DPE sur la valeur du bien (Lot 13).

Données : « Valeur verte des logements : écarts de prix par étiquette DPE (610 000 ventes DVF x ADEME) »
(data.gouv.fr / france-dpe.fr), dans data/valeur_verte/ : écart de prix au m² de chaque classe par rapport
à la classe D (D = 0), par type de bien, en France et par département.

Valeur verte = valeur du bien × (écart[classe après] − écart[classe avant]) ; écart du département s'il
existe pour cette classe, sinon écart France. Fourchette ± 30 % (admin). Montants arrondis à la centaine.

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


def ecarts(tab, dep, tb):
    """Écart (%) par classe : département si la classe y figure, sinon France ; D = 0."""
    fr = (tab.get("france") or {}).get(tb) or {}
    dp = ((tab.get("departements") or {}).get(dep) or {}).get(tb) or {}
    out = {}
    for c in CLASSES:
        out[c] = 0.0 if c == "D" else (dp[c] if c in dp else fr.get(c, 0.0))
    return out


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
    ec = ecarts(tab, departement(entree.get("cp")), type_bien(entree.get("type_logement")))
    r = calculer(entree.get("valeur_bien"), cls["classe_avant"], cls["classe_apres"], ec,
                 dpe_estime.params_dpe(params)["valeur_verte_fourchette_pct"])
    r.update({"classe_avant": cls["classe_avant"], "classe_apres": cls["classe_apres"], "dpe_reel": cls["dpe_reel"],
              "libelle_classes": f"Classe {cls['classe_avant']} → {cls['classe_apres']}",
              "libelle_source": "(DPE réel)" if cls["dpe_reel"] else "(classe estimée)"})
    return r
