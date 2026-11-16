# -*- coding: utf-8 -*-
"""16/11/2026 (Avi) — Thaleos à −7 °C (35 et 55 °C, COP) importés des tableaux du fabricant ; la couverture se lit à
la température d'eau du dossier, jamais sur la nominale."""
from services import dimensionnement_pac as dp


def test_referentiel_thaleos_charge():
    assert len(dp.THALEOS) == 15 and dp.THALEOS["THA-MTBL-R32-8"]["m7_35"] == {"hc_kw": 7.19, "cop": 3.03}


def test_puissance_m7_suit_la_temperature_d_eau():
    m = {"puissance_m7_55_kw": 7.09, "puissance_m7_55_valide": True, "puissance_m7_35_kw": 7.19,
         "cop_m7_35": 3.03, "cop_m7_55": 2.17, "puiss_chauf": 8}
    assert dp.puissance_m7(m, "55") == (7.09, dp.ORIGINE_M7_55) and dp.puissance_m7(m, "35") == (7.19, dp.ORIGINE_M7_35)
    assert dp.cop_m7(m, "35") == 3.03
    assert dp.puissance_m7({"puiss_chauf": 8}, "55") == (None, "")             # jamais la nominale
