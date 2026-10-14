# -*- coding: utf-8 -*-
"""Classe DPE estimée avant / après PAC (Lot 13).

Avant : consommation de chauffage + eau chaude que calculer_economies() déduit de la facture
(facture ÷ prix du kWh de l'énergie), rapportée à la surface habitable.
Après : électricité de la PAC (besoin ÷ SCOP) + eau chaude, rapportée à la surface.
Double critère DPE (énergie primaire et CO2) : on retient la pire des deux classes.

Version serveur de window.HexaDpeEstime (templates/index.html, bloc HEXA-DPE-ESTIME) ; les deux
sont tenues identiques par tests/test_lot13_valeur_verte.py. Fonctions pures."""
from services import economies as eco

CLASSES = "ABCDEFG"

# Valeurs par défaut (Admin → Hypothèses économie d'énergie → « Classe DPE estimée »)
DEFAULTS = {
    "dpe_seuils_ep": {"A": 70, "B": 110, "C": 180, "D": 250, "E": 330, "F": 420},
    "dpe_seuils_co2": {"A": 6, "B": 11, "C": 30, "D": 50, "E": 70, "F": 100},
    "coef_ep": {"electricite": 1.9, "gaz": 1, "fioul": 1, "bois": 1},
    "facteur_co2": {"gaz": 0.227, "fioul": 0.324, "electricite": 0.079, "bois": 0.030},
    "valeur_verte_fourchette_pct": 30,
}


def _r1(x):
    """Arrondi au dixième, demi vers le haut (= Math.round(x * 10) / 10 du JS)."""
    return eco._arrondi(x * 10) / 10


def params_dpe(params):
    """Seuils et coefficients de l'admin (params_eco_energie) complétés par les défauts."""
    params = params if isinstance(params, dict) else {}
    out = {}
    for k, d in DEFAULTS.items():
        v = params.get(k)
        if isinstance(d, dict):
            fusion = dict(d)
            if isinstance(v, dict):
                fusion.update({kk: eco._num(vv) for kk, vv in v.items() if kk in d and eco._num(vv) is not None})
            out[k] = fusion
        else:
            out[k] = eco._num(v) if eco._num(v) is not None else d
    return out


def _cle(energie):
    return "electricite" if energie in ("pac", "electricite") else energie


def classe_seuils(valeur, seuils):
    for c in CLASSES[:-1]:
        if valeur <= (eco._num(seuils.get(c), 0) or 0):
            return c
    return "G"


def classe(ep, co2, params):
    p = params_dpe(params)
    a, b = classe_seuils(ep, p["dpe_seuils_ep"]), classe_seuils(co2, p["dpe_seuils_co2"])
    return a if CLASSES.index(a) >= CLASSES.index(b) else b


def consommations(res, personnes, ecs_chaudiere, params):
    """kWh/an par énergie, avant et après PAC, à partir du résultat de calculer_economies()."""
    p = eco.params_complets(params)
    energie = _cle(res["energie"])
    prix = eco._prix(p, res["energie"])
    prix_elec = eco._num(p["prix_kwh"].get("electricite"), 0.21) or 0.21
    n = eco._num(personnes) or eco.PERSONNES_DEFAUT
    kwh_ecs_ballon = n * (eco._num(p["ecs_kwh_par_personne"], 800) or 0) / eco.RENDEMENT_BALLON_ELECTRIQUE
    avant = {energie: (res["chauffage_avant"] + res["ecs_avant"]) / prix if prix > 0 else 0.0}
    if not ecs_chaudiere:
        avant["electricite"] = avant.get("electricite", 0.0) + kwh_ecs_ballon
    apres = {"electricite": res["besoin_kwh"] / (res["scop"] or 1)}
    if res["ecs_traitee"]:
        apres["electricite"] += res["ecs_apres"] / prix_elec
    elif ecs_chaudiere:
        apres[energie] = apres.get(energie, 0.0) + (res["ecs_avant"] / prix if prix > 0 else 0.0)
    else:
        apres["electricite"] += kwh_ecs_ballon
    return {"avant": avant, "apres": apres}


def indicateurs(conso, surface, params):
    p = params_dpe(params)
    ep = sum(kwh * (eco._num(p["coef_ep"].get(e), 1) or 0) for e, kwh in conso.items()) / surface
    co2 = sum(kwh * (eco._num(p["facteur_co2"].get(e), 0) or 0) for e, kwh in conso.items()) / surface
    return ep, co2


def estimer(res, surface, personnes, ecs_chaudiere, params):
    """Classes estimées avant / après. {'ok': False} sans économies calculées ou sans surface."""
    surface = eco._num(surface, 0) or 0
    if not (res and res.get("ok")) or surface <= 0:
        return {"ok": False}
    c = consommations(res, personnes, ecs_chaudiere, params)
    ep_av, co2_av = indicateurs(c["avant"], surface, params)
    ep_ap, co2_ap = indicateurs(c["apres"], surface, params)
    cl_av, cl_ap = classe(ep_av, co2_av, params), classe(ep_ap, co2_ap, params)
    return {"ok": True, "ep_avant": _r1(ep_av), "co2_avant": _r1(co2_av), "classe_avant": cl_av,
            "ep_apres": _r1(ep_ap), "co2_apres": _r1(co2_ap), "classe_apres": cl_ap,
            "gain": max(0, CLASSES.index(cl_av) - CLASSES.index(cl_ap))}


def classe_reelle(classe_dpe_avant, dpe_connu=""):
    """Classe du vrai DPE : choix de la fiche (A-G), sinon (champ jamais choisi) la classe DPE trouvée.
    « aucun » = Pas de DPE."""
    c = str(classe_dpe_avant or "").strip().upper()
    if len(c) == 1 and c in CLASSES:
        return c
    if c:
        return ""
    d = str(dpe_connu or "").strip().upper()
    return d if len(d) == 1 and d in CLASSES else ""


def classes_projet(reelle, estimation):
    """Classe avant / après retenues. Vrai DPE : sa classe + le gain estimé (sans dépasser A)."""
    if not (estimation and estimation.get("ok")):
        return {"ok": False}
    if reelle:
        i = CLASSES.index(reelle)
        return {"ok": True, "classe_avant": reelle, "classe_apres": CLASSES[max(0, i - estimation["gain"])], "dpe_reel": True}
    return {"ok": True, "classe_avant": estimation["classe_avant"], "classe_apres": estimation["classe_apres"], "dpe_reel": False}
