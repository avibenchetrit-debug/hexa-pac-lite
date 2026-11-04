# -*- coding: utf-8 -*-
"""Lot A (notedim-master) — règles serveur : plage de cohérence 60–130 %, puissance retenue (−7 °C / 55 °C validée,
sinon 35 °C), température de départ requise / max, migration du catalogue, Admin → Dimensionnement."""
import copy
import json
import os

import pytest
from fastapi.testclient import TestClient

import main
from services import dimensionnement_pac as dp

FIX = os.path.join(os.path.dirname(__file__), "fixtures")
CATALOGUE = json.load(open(os.path.join(FIX, "catalogue_pac_38.json"), encoding="utf-8"))


def _modele(ref):
    return copy.deepcopy(next(m for m in CATALOGUE if m["ref"] == ref))


def test_plage_coherence_bornes_du_master():
    assert dp.coherence(36, 33.4) == {"pct": 108, "statut": "ok", "libelle": "cohérent"}
    assert dp.coherence(20.04, 33.4)["statut"] == "ok"                  # 60 % pile : cohérent
    assert dp.coherence(20.0, 33.4)["statut"] == "sous"
    assert dp.coherence(43.42, 33.4)["statut"] == "ok"                  # 130 % pile
    assert dp.coherence(43.5, 33.4) == {"pct": 130, "statut": "sur", "libelle": "surdimensionnement"}
    assert dp.coherence(0, 10) is None and dp.coherence(10, 0) is None
    assert dp.plage(33.4) == {"min_kw": 20.0, "max_kw": 43.4, "min_pct": 60, "max_pct": 130}


def test_puissance_retenue_valeur_a_valider_comptee_absente():
    m = _modele("DAI-ALTHERMA-3HHT-R32-18 TRI")
    assert dp.puissance_retenue(m) == (18, "35")
    m.update({dp.CHAMP_M7_55: 9.21, dp.CHAMP_M7_55_VALIDE: False})
    assert dp.puissance_retenue(m) == (18, "35")                        # « à valider » = absente (règle du Master)
    m[dp.CHAMP_M7_55_VALIDE] = True
    assert dp.puissance_retenue(m) == (9.21, "m7_55")
    assert dp.libelle_origine("35") == "puissance à 35 °C, valeur à −7 °C / 55 °C non renseignée"


def test_temperatures_requises_et_max():
    assert dp.temperatures_depart({}) == {"radiateurs_fonte": 65, "radiateurs_classiques": 55,
                                          "radiateurs_basse_temp": 55, "plancher_chauffant": 35,
                                          "convecteurs_electriques": 55}
    assert dp.temperatures_depart({"temperatures_depart": {"radiateurs_fonte": 70, "inconnu": 1}})["radiateurs_fonte"] == 70
    assert dp.temperature_requise({"type_emetteurs": "radiateurs_fonte"}, {}) == (65, "emetteur")
    assert dp.temperature_requise({"type_emetteurs": "radiateurs_fonte", "temperature_depart_c": "60"}, {}) == (60, "fiche")
    assert dp.temperature_requise({}, {}) == (None, "")
    nimbus = _modele("ARI-NIMBUS-NET-R32-15 TRI")
    assert dp.temp_max(nimbus) is None or dp.temp_max(nimbus) == 60    # fixture sans fiche produit
    nimbus["description_specs"] = [{"champ": "Temp. max de départ (°C)", "valeur": "60"}]
    assert dp.temp_max(nimbus) == 60
    assert dp.alerte_temperature(nimbus, 65, "radiateurs_fonte") == \
        "Température max 60 °C : insuffisante pour des radiateurs fonte (65 °C requis)"
    assert dp.alerte_temperature(nimbus, 55, "radiateurs_classiques") == ""
    duo = {"description_specs": [{"champ": "Plage température sortie d’eau (°C)", "valeur": "20 / 60"}]}
    assert dp.temp_max(duo) == 60


def test_migration_idempotente_et_respecte_les_saisies():
    cat = [{"ref": "DAI-ALTHERMA-3HHT-R32-18", "nom": "x", "ttc": 1,
            "description_specs": [{"champ": "Temp. max de départ (°C)", "valeur": "70"}]},
           {"ref": "ARI-NIMBUS-NET-R32-15", "nom": "y", "ttc": 1, dp.CHAMP_M7_55: 11.5, dp.CHAMP_M7_55_VALIDE: True},
           {"ref": "THA-MTBL-R290-12", "nom": "z", "ttc": 1}]
    cat, change = dp.migrer_catalogue(cat)
    assert change
    assert cat[0][dp.CHAMP_M7_55] == 9.81 and cat[0][dp.CHAMP_M7_55_VALIDE] is False and cat[0][dp.CHAMP_TEMP_MAX] == 70
    assert cat[0][dp.CHAMP_M7_55_SOURCE].startswith("Master (à valider) — Daikin")
    assert cat[1][dp.CHAMP_M7_55] == 11.5 and cat[1][dp.CHAMP_M7_55_VALIDE] is True     # saisie gardée
    assert dp.CHAMP_M7_55 not in cat[2]                                                  # pas de valeur au Master
    assert dp.migrer_catalogue(cat) == (cat, False)


@pytest.fixture
def client_admin(monkeypatch):
    monkeypatch.setenv("COOKIE_SECURE", "0")
    chemins = (main.CATALOGUE_PATH, main.PARAMETRES_ADMIN_PATH, main.USERS_PATH)
    sauve = {c: open(c, "rb").read() for c in chemins if os.path.exists(c)}
    main._atomic_write_json(main.CATALOGUE_PATH, copy.deepcopy(CATALOGUE))
    main._write_users([{"id": "adm", "username": "adm", "password_hash": main._hash_password("essai-local"),
                        "role": "admin", "actif": True, "cree_at": main._now_iso(), "visibilite": "tous"}])
    c = TestClient(main.app)
    assert c.post("/api/auth/login", json={"username": "adm", "password": "essai-local"}).status_code == 200
    yield c
    for chemin, octets in sauve.items():
        open(chemin, "wb").write(octets)


def test_admin_dimensionnement_lecture_ecriture(client_admin):
    d = client_admin.get("/api/admin/dimensionnement-pac").json()
    assert d["temperatures_depart"]["radiateurs_fonte"] == 65 and len(d["modeles"]) == 38
    r = client_admin.post("/api/admin/dimensionnement-pac", json={
        "temperatures_depart": {"radiateurs_fonte": 70},
        "modeles": [{"ref": "DAI-ALTHERMA-3HHT-R32-18 TRI", dp.CHAMP_M7_55: "17,1", dp.CHAMP_M7_55_VALIDE: True,
                     dp.CHAMP_M7_55_SOURCE: "fournisseur", dp.CHAMP_TEMP_MAX: 70}]})
    assert r.status_code == 200, r.text
    m = next(x for x in main._read_catalogue_pac() if x["ref"] == "DAI-ALTHERMA-3HHT-R32-18 TRI")
    assert (m[dp.CHAMP_M7_55], m[dp.CHAMP_M7_55_VALIDE], m[dp.CHAMP_TEMP_MAX]) == (17.1, True, 70)
    assert m["ttc"] == 17882.0                                           # rien d'autre touché
    assert client_admin.get("/api/admin/m3").json()["temperatures_depart"]["radiateurs_fonte"] == 70
    # validée sans valeur : refusée silencieusement (non validée)
    client_admin.post("/api/admin/dimensionnement-pac", json={"modeles": [
        {"ref": "DAI-ALTHERMA-3HHT-R32-18 TRI", dp.CHAMP_M7_55: "", dp.CHAMP_M7_55_VALIDE: True}]})
    m = next(x for x in main._read_catalogue_pac() if x["ref"] == "DAI-ALTHERMA-3HHT-R32-18 TRI")
    assert m[dp.CHAMP_M7_55] is None and m[dp.CHAMP_M7_55_VALIDE] is False
    assert client_admin.post("/api/admin/dimensionnement-pac",
                             json={"temperatures_depart": {"radiateurs_fonte": 300}}).status_code == 400
