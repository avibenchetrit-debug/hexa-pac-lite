# -*- coding: utf-8 -*-
"""15/11/2026 (Avi) — CEE au 16/11/2026 : arrêté du 5 novembre 2026, art. 3 III 1° — Coup de pouce BAR-TH-171
× 5 très modestes, × 3 précarité énergétique (ex-« modestes »), × 5 autres ménages ; × 5 pour tous avant."""
from services import service_devis as sd


def test_coefficients_dates_par_categorie():
    for cat, avant, apres in (("tres_modeste", 5, 5), ("modeste", 5, 3), ("intermediaire", 5, 5),
                              ("superieur", 5, 5)):
        assert sd.coup_de_pouce({"actif": True}, cat, "2026-11-15")[0] == avant
        assert sd.coup_de_pouce({"actif": True}, cat, "2026-11-16")[0] == apres
    assert sd.coup_de_pouce({"actif": False}, "modeste", "2026-11-16")[0] == 1


def test_categories_renommees():
    assert sd.LIBELLES_CATEGORIE_CEE[sd.categorie_cee("tres_modeste")] == "Ménages très modestes"
    assert sd.LIBELLES_CATEGORIE_CEE[sd.categorie_cee("modeste")] == "Ménages en situation de précarité énergétique"
    assert sd.LIBELLES_CATEGORIE_CEE[sd.categorie_cee("intermediaire")] == "Autres ménages"


def test_sans_signature_la_date_est_aujourd_hui(monkeypatch):
    monkeypatch.setattr(sd, "aujourd_hui_paris", lambda: "2026-11-20")
    assert sd.coup_de_pouce({"actif": True}, "modeste")[0] == 3
    assert sd.coup_de_pouce({"actif": True}, "modeste", "2026-11-10")[0] == 5
