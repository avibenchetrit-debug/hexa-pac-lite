# -*- coding: utf-8 -*-
"""Lot 13k : prix du kWh de l'Admin en €/kWh, dans une plage réaliste (électricité 0,10-0,40 ; gaz, fioul, bois
0,03-0,30), sinon refus avec un message clair ; « Consommation estimée (type DPE) » jamais divisée par le rendement."""
import os

import pytest
from fastapi.testclient import TestClient

import main

PRIX_OK = {"electricite": 0.21, "gaz": 0.125, "fioul": 0.15, "bois": 0.075}


@pytest.fixture(autouse=True)
def _parametres_restaures():
    c = main.PARAMETRES_ADMIN_PATH
    sauve = open(c, "rb").read() if os.path.exists(c) else None
    yield
    if sauve is None:
        if os.path.exists(c):
            os.remove(c)
    else:
        open(c, "wb").write(sauve)


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(main, "_require_admin", lambda request: None)
    return TestClient(main.app)


def _payload(**prix):
    return {"conso_zone_kwh_m2_an": {"h1": 150, "h2": 130, "h3": 110}, "prix_kwh": dict(PRIX_OK, **prix)}


def test_prix_dans_la_plage_enregistres(client):
    r = client.post("/api/admin/params-eco-energie", json=_payload())
    assert r.status_code == 200
    assert main.load_parametres_admin()["params_eco_energie"]["prix_kwh"] == PRIX_OK


@pytest.mark.parametrize("cle, valeur, attendu", [
    ("fioul", 1.15, "Fioul : 1,15 €/kWh — attendu entre 0,03 et 0,3 €/kWh"),        # prix au litre
    ("gaz", 12.5, "Gaz : 12,5 €/kWh — attendu entre 0,03 et 0,3 €/kWh"),            # centimes
    ("bois", 400, "Bois : 400 €/kWh — attendu entre 0,03 et 0,3 €/kWh"),            # prix à la tonne
    ("electricite", 0.05, "Électricité : 0,05 €/kWh — attendu entre 0,1 et 0,4 €/kWh"),
    ("electricite", 0.41, "Électricité : 0,41 €/kWh — attendu entre 0,1 et 0,4 €/kWh"),
    ("gaz", "", "Gaz : vide €/kWh — attendu entre 0,03 et 0,3 €/kWh"),
    ("bois", 0.02, "Bois : 0,02 €/kWh — attendu entre 0,03 et 0,3 €/kWh"),
])
def test_prix_hors_plage_refuses_avec_message_clair(client, cle, valeur, attendu):
    avant = main.load_parametres_admin().get("params_eco_energie")
    r = client.post("/api/admin/params-eco-energie", json=_payload(**{cle: valeur}))
    assert r.status_code == 400
    detail = r.json()["detail"]
    assert detail.startswith("Prix du kWh hors plage, rien n'est enregistré. ") and attendu in detail
    assert "pas au litre, au m³ ni à la tonne" in detail
    assert main.load_parametres_admin().get("params_eco_energie") == avant      # rien n'a changé


@pytest.mark.parametrize("cle, valeur", [("electricite", 0.10), ("electricite", 0.40), ("gaz", 0.03), ("bois", 0.30)])
def test_bornes_incluses(cle, valeur):
    assert main._erreurs_prix_kwh(dict(PRIX_OK, **{cle: valeur})) == []


def test_ecran_admin_unite_et_libelle():
    html = open(os.path.join(os.path.dirname(main.__file__), "templates", "index.html"), encoding="utf-8").read()
    for champ, mini, maxi in (("elec", "0.10", "0.40"), ("gaz", "0.03", "0.30"), ("fioul", "0.03", "0.30"),
                              ("bois", "0.03", "0.30")):
        bloc = html.split(f'id="adm-eco-prix-{champ}"', 1)[1].split("</label>", 1)[0]
        assert f'min="{mini}" max="{maxi}"' in bloc and '<span class="adm-unit">€/kWh</span>' in bloc
    assert "Consommation estimée (type DPE) (kWh/m²/an)" in html and "Consommation par zone climatique" not in html
