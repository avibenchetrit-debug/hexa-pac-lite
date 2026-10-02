# -*- coding: utf-8 -*-
"""Lot 9 — marges (admin seulement). Fonctions pures : aucune donnée écrite, aucun prix ni calcul client modifié.

Page « Marges » (par modèle, hors CEE supplémentaire et hors frais ECAIR, qui dépendent du dossier) :
  HT = TTC ÷ (1 + TVA) ; frais de dossier = VT + COFRAC + urbanisme ; acquisition = coût d'un lead ÷ taux de
  transformation ; coût de revient = achat HT + pose + accessoires ; marge brute = HT − coût de revient ;
  marge nette Hexa = marge brute − frais de dossier − acquisition ; % = part du prix de vente HT.

« Marge du dossier » (fiche, étape 6) : mêmes postes sur le devis du dossier (PAC + ballon éventuel), plus
  CEE supplémentaire RÉEL = valorisation du délégataire du dossier − prime CEE affichée (écrêtement des plafonds,
  `_cee_conserve` du calcul existant), moins frais ECAIR = taux × MPR du devis, seulement pour un dossier PICOTY
  (client qui attend l'accord MPR) ; 0 pour ACE.
"""


def _n(v, defaut=0.0):
    try:
        if v is None or v == "":
            return defaut
        return float(str(v).replace(" ", "").replace(" ", "").replace(",", "."))
    except (TypeError, ValueError):
        return defaut


def frais_dossier(p) -> float:
    return _n(p.get("vt1")) + _n(p.get("cofrac1")) + _n(p.get("urba1"))


def acquisition(p) -> float:
    conv = _n(p.get("conv"))
    return _n(p.get("lead")) / conv if conv > 0 else 0.0


def tva(p) -> float:
    t = _n(p.get("tva"), 0.055)
    return t if t > 0 else 0.055


def pct(part, total) -> float:
    return part / total if total else 0.0


def marge_modele(m: dict, p: dict) -> dict:
    ttc = _n(m.get("ttc"))
    ht = ttc / (1 + tva(p))
    achat = _n(m.get("achat"))
    pose_acc = _n(p.get("pose")) + _n(p.get("acc"))
    fd, acq = frais_dossier(p), acquisition(p)
    cout = achat + pose_acc
    brute = ht - cout
    nette = brute - fd - acq
    return {"ttc": ttc, "ht": ht, "achat": achat, "pose_acc": pose_acc, "frais_dossier": fd, "acquisition": acq,
            "cout_revient": cout, "marge_brute": brute, "marge_brute_pct": pct(brute, ht),
            "marge_nette": nette, "marge_nette_pct": pct(nette, ht)}


def marge_dossier(calc: dict, modele: dict | None, ballon: dict | None, p: dict, mode_cee: str) -> dict:
    """calc = résultat de calculer_devis (inchangé) ; mode_cee = « attente » (PICOTY) ou « tout_de_suite » (ACE)."""
    ht = _n(calc.get("recap_total_ht")) or _n(calc.get("total_ht"))
    achat = _n((modele or {}).get("achat"))
    pose_acc = _n(p.get("pose")) + _n(p.get("acc"))
    if ballon:
        achat += _n(ballon.get("cout_fourniture_ht"))
        pose_acc += _n(p.get("cout_pose_ballon"), 600.0)
    fd, acq = frais_dossier(p), acquisition(p)
    cout = achat + pose_acc
    brute = ht - cout
    cee_sup = _n(calc.get("_cee_conserve"))
    taux_ecair = _n(p.get("frais_ecair_pct"), 12.5) / 100
    ecair = round(taux_ecair * _n(calc.get("montant_mpr")), 2) if mode_cee == "attente" else 0.0
    nette = brute - fd - acq + cee_sup - ecair
    return {"ht": ht, "achat": achat, "pose_acc": pose_acc, "frais_dossier": fd, "acquisition": acq,
            "cout_revient": cout, "marge_brute": brute, "marge_brute_pct": pct(brute, ht),
            "cee_supplementaire": cee_sup, "frais_ecair": ecair, "taux_ecair": taux_ecair,
            "delegataire": "PICOTY" if mode_cee == "attente" else "ACE",
            "marge_nette": nette, "marge_nette_pct": pct(nette, ht),
            "mpr": _n(calc.get("montant_mpr")), "cee_devis": _n(calc.get("montant_cee"))}


def positionnement_defaut(m: dict) -> str:
    """Texte pré-rempli (modifiable ensuite dans la page Marges)."""
    ref = str(m.get("ref") or "").upper()
    duo = "DUO" in ref or "ECS" in str(m.get("usage") or "").upper()
    if ref.startswith("ATL-EXCELLIA-S"):
        return ("Hors marché haut (moyenne ≈ 13 900 €, max ≈ 15 000 € posé)" if duo
                else "Au-dessus du marché (moyenne ≈ 12 400 € posé)")
    if ref.startswith("DAI-ALTHERMA-3HHT"):
        return "Dans le marché, compétitif (14 000 – 18 000 € posé)"
    if ref.startswith("ARI-NIMBUS"):
        return "Haut de fourchette" if duo else "Légèrement au-dessus (marché dès ≈ 11 000 – 12 750 € posé)"
    if ref.startswith("THA-MTBL"):
        kw = _n(m.get("puiss35"), 0) or _n(m.get("puiss_chauf"), 0)
        return "Un peu cher pour la puissance" if kw and kw < 8 else "Dans le marché"
    return ""
