# -*- coding: utf-8 -*-
"""Lot 14 : quantité de PAC (1 ou 2, 2 = montées en cascade) à l'étape Proposition.
Quantité 1 : documents identiques, caractère pour caractère, à ceux du code d'avant le lot 14 (photos de référence
tests/fixtures/lot14_*.html, prises avec le code d'avant). Quantité 2 : fourniture × 2, pose cascade et travaux induits
réglables dans l'Admin, aides (CEE, MaPrimeRénov') comptées UNE fois, phrase cascade dans le document.
Régénérer les photos (code d'avant seulement) : HEXA_LOT14_PHOTOS=1 pytest tests/test_lot14_quantite_pac.py -k photo"""
import os
import re

import pytest
from fastapi.testclient import TestClient

import main

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")
NUM = "PR-14001"
LEAD = {"numero": NUM, "civilite": "Monsieur", "nom": "Cascade", "prenom": "Romaric", "telephone": "0611140011",
        "email": "romaric@example.invalid", "adresse_chantier": "1 rue A", "cp_chantier": "49800",
        "code_postal_chantier": "49800", "ville_chantier": "Trélazé", "type_logement": "maison",
        "surface_logement_m2": "280", "hsp": "2,5", "mode_chauffage": "fioul", "ecs": "chaudiere",
        "type_emetteurs": "radiateurs_classiques", "alimentation_electrique": "monophase", "categorie": "modeste",
        "nombre_personnes": "4", "cout_energetique_mensuel_eur": "268", "cout_energie_source": "reel",
        "vt_validee": True}
MODELE = "ATL-EXCELLIA-S-DUO-12"
STATE = {"service": "chauffage_ecs", "option": "opt1", "modele_pac_id": MODELE, "modele_pac": MODELE,
         "mode_mpr": "attente"}


@pytest.fixture(autouse=True)
def _donnees_restaurees():
    chemins = (main.LEADS_PATH, main.PARAMETRES_ADMIN_PATH, main._state_simulateur_path(NUM))
    sauve = {c: open(c, "rb").read() for c in chemins if os.path.exists(c)}
    absents = [c for c in chemins if not os.path.exists(c)]
    yield
    for c, octets in sauve.items():
        open(c, "wb").write(octets)
    for c in absents:
        if os.path.exists(c):
            os.remove(c)


@pytest.fixture
def client():
    return TestClient(main.app)


def _preparer(**state):
    main._atomic_write_json(main.LEADS_PATH, [dict(LEAD)])
    main._atomic_write_json(main._state_simulateur_path(NUM), {})
    modele = main.find_modele(main._read_catalogue_pac(), MODELE)
    main.save_state_simulateur_atomic(NUM, dict(STATE, prix_pac=modele["ttc"], **state))
    return modele


def _normaliser(html):
    """Seuls les éléments qui changent d'un jour ou d'un test à l'autre sont neutralisés : dates, n° de dossier."""
    html = re.sub(r"\b\d{2}/\d{2}/\d{4}\b", "JJ/MM/AAAA", html)
    return re.sub(r"\bHX\d{2}-\d{4}\b", "HXAA-NNNN", html)


def _photo(nom):
    return os.path.join(FIXTURES, f"lot14_{nom}.html")


# ---------- quantité 1 : rien ne change ----------

@pytest.mark.parametrize("variante", ["pre_devis", "devis"])
@pytest.mark.parametrize("quantite", [None, 1])
def test_photo_quantite_1_document_identique_a_avant(client, variante, quantite):
    _preparer(**({} if quantite is None else {"quantite_pac": quantite}))
    html = _normaliser(client.get(f"/api/devis/{NUM}/preview?variante={variante}").text)
    if os.environ.get("HEXA_LOT14_PHOTOS") == "1" and quantite is None:
        os.makedirs(FIXTURES, exist_ok=True)
        open(_photo(variante), "w", encoding="utf-8", newline="").write(html)
    assert html == open(_photo(variante), encoding="utf-8").read()
