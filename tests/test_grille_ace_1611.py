"""20/11/2026 (Avi) — la grille officielle ACE (devis signés à partir du 16/11/2026, BAR-TH-171 maison, 54 cases) est
recalculée par pac-lite à chaque mise en ligne, au centime (même fichier que le CRM Master). Un devis signé le 15/11
garde l'ancien calcul."""
from __future__ import annotations

import io
import json
from contextlib import redirect_stdout
from pathlib import Path

import pytest

from services import service_devis as sd

GRILLE = json.loads((Path(__file__).parent / "fixtures" / "grille_ace_1611.json").read_text(encoding="utf-8"))
#: Les délégataires tels qu'enregistrés en production (Admin › 3.3) : ACE actif, PICOTY inactif.
DELEGATAIRES = [{"nom": "PICOTY", "mwh_precaire": 12.7, "mwh_classique": 7.2, "actif": False},
                {"nom": "ACE", "mwh_precaire": 14, "mwh_classique": 7.5, "actif": True}]


def _prime(c, date):
    import main
    admin = {"delegataires": DELEGATAIRES, "bonification_cee": {"actif": True, "multiplicateur": 5},
             "formule_bar_th_171": main.DEFAULT_FORMULE_BAR_TH_171}
    prospect = {"type_logement": "maison", "categorie": c["categorie"], "cp_chantier": c["cp"]}
    state = {"etas": c["etas"], "surface_chauffee": c["surface"], "date_engagement": date, "mode_mpr": "sans_attente"}
    with redirect_stdout(io.StringIO()):
        return sd.calculer_cee_bar_th_171(prospect, state, admin, mode="tout_de_suite")


@pytest.mark.parametrize("c", GRILLE["cases"], ids=lambda c: f"{c['zone']}-{c['etas']}-{c['surface']}-{c['categorie']}")
def test_54_cases_au_centime(c):
    p = _prime(c, GRILLE["date_engagement"])
    assert abs(float(p.get("montant") or 0) - c["ace"]) < 0.005, (p.get("montant"), c["ace"], p.get("details"))


def test_devis_signe_le_15_11_ancien_calcul():
    c = next(x for x in GRILLE["cases"] if x["categorie"] == "modeste" and x["zone"] == "H1" and x["surface"] == 100
             and x["etas"] == 150)
    assert abs(float(_prime(c, "2026-11-15")["montant"]) - 4914.0) < 0.005


def test_la_page_a_le_meme_defaut_que_le_serveur():
    src = open("templates/index.html", encoding="utf-8").read()
    i = src.index("const PERIODES_CDP_DEFAUT = [")
    bloc = src[i:src.index("];", i)]
    assert "prix: { ACE: { tres_modeste: 14, precarite: 14, autres: 7.5 } }" in bloc
    assert sd.PERIODES_COUP_DE_POUCE[-1]["prix"] == {"ACE": {"tres_modeste": 14, "precarite": 14, "autres": 7.5}}
