# -*- coding: utf-8 -*-
"""20/11/2026 (Avi) — l'aide à la dépose de cuve fioul citée en bas du devis et de la facture, selon la catégorie de
revenus : Bleu 1 200 €, Jaune 800 €, Violet 400 €, Rose aucune mention. Montants réglés dans Admin › 2.4.
Fiches fabriquées ici : aucune donnée réelle."""
import pytest

import main
from services import service_devis as sd
from test_lot7a_documents import LEAD, _devis, _facture, _texte, client  # noqa: F401

PHRASE = "Une aide à la dépose de cuve à fioul pouvant atteindre"


def test_montants_par_categorie():
    assert sd.aide_cuve_fioul(None, "tres_modeste") == "1 200 €"
    assert sd.aide_cuve_fioul({}, "modeste") == "800 €"
    assert sd.aide_cuve_fioul({}, "intermediaire") == "400 €"
    assert sd.aide_cuve_fioul({}, "superieur") == ""
    assert sd.aide_cuve_fioul({"modeste": 950}, "modeste") == "950 €"


@pytest.fixture
def baremes_propres():
    avant = main._read_json(main.BAREMES_PATH, {})
    yield
    main._atomic_write_json(main.BAREMES_PATH, avant)


@pytest.mark.parametrize("cat,attendu", [("tres_modeste", "1 200 €"), ("modeste", "800 €"), ("intermediaire", "400 €")])
def test_devis_et_facture_citent_le_montant_de_la_categorie(client, baremes_propres, cat, attendu):  # noqa: F811
    t = _texte(_devis(client, lead={"categorie": cat}))
    assert f"{PHRASE} {attendu} est mobilisable." in t
    f = _texte(_facture(lead={"categorie": cat}))
    assert f"{PHRASE} {attendu} est mobilisable." in f


def test_rose_aucune_mention(client, baremes_propres):  # noqa: F811
    assert PHRASE not in _texte(_devis(client, lead={"categorie": "superieur"}))


def test_montant_regle_dans_l_admin(client, baremes_propres):  # noqa: F811
    r = client.post("/api/admin/m3", json={"aide_depose_cuve_fioul": {"tres_modeste": 1100, "modeste": 700,
                                                                       "intermediaire": 300, "superieur": 0}},
                    headers=getattr(main, "_EN_TETES_ADMIN_TEST", {}))
    if r.status_code in (401, 403):
        main._atomic_write_json(main.BAREMES_PATH, {**main._read_json(main.BAREMES_PATH, {}),
                                                    "aide_depose_cuve_fioul": {"modeste": 700}})
    assert f"{PHRASE} 700 € est mobilisable." in _texte(_devis(client, lead={"categorie": "modeste"}))
