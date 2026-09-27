# -*- coding: utf-8 -*-
"""Lot 6c : la température de base (puissance) reste sur la table d'avant, la zone CEE officielle ne sert qu'à la
prime ; verrou « dossier facturé » (installation finie ou facture émise) : rien ne réécrit le lead."""
import json
import os
import time

import pytest
from fastapi.testclient import TestClient

import main
from services import service_devis as sd

LEAD = {"numero": "PR-07070", "civilite": "Madame", "nom": "Fige", "prenom": "Fanny", "telephone": "0611121318", "email": "f@x.fr",
        "adresse_chantier": "1 rue A", "cp_chantier": "49430", "code_postal_chantier": "49430", "ville_chantier": "Durtal",
        "type_logement": "maison", "surface_logement_m2": "120", "annee_construction": "19481974", "mode_chauffage": "fioul",
        "categorie": "tres_modeste", "statut": "installation_finie"}


@pytest.fixture
def client():
    return TestClient(main.app)


def _jeton_admin():
    p = f"admin:{int(time.time())}"
    return f"{p}.{main._sign_admin_token(p)}"


# ---------------------------------------------------------------- 1. température de base = table d'avant
# valeurs de main avant le Lot 6b (192b50f) : sous-zone du département -> TEMP_BASE_SOUS_ZONE
@pytest.mark.parametrize("cp, sous_zone, temperature, zone_cee", [
    ("35000", "H1C", -7, "H2"), ("49430", "H1C", -7, "H2"), ("38000", "H2B", -5, "H1"),
    ("75002", "H1B", -8, "H1"), ("06000", "H2D", -2, "H3"), ("33000", "H2A", -4, "H2"), ("67000", "H1A", -9, "H1")])
def test_temperature_base_table_d_avant(cp, sous_zone, temperature, zone_cee):
    t = sd._temperature_base_notedim({"cp_chantier": cp})
    assert (t["zone"], t["temperature"]) == (sous_zone, temperature)
    assert sd.calculer_zone_climatique(cp) == zone_cee          # la zone CEE officielle, elle, ne bouge pas


def test_correction_altitude_conservee():
    t = sd._temperature_base_notedim({"cp_chantier": "38000", "altitude": "400"})
    assert t["temperature"] == -6 and "altitude" in t["correction_label"]


# ---------------------------------------------------------------- 2. verrou « dossier facturé »
def _octets_du_lead(numero):
    return json.dumps(next(x for x in main._read_leads() if x.get("numero") == numero), sort_keys=True, ensure_ascii=False)


def test_installation_finie_fiche_et_simulateur_refuses(client):
    main._atomic_write_json(main.LEADS_PATH, [dict(LEAD)])
    main._atomic_write_json(main._state_simulateur_path(LEAD["numero"]), {"prix_pac": 15990})
    avant = _octets_du_lead(LEAD["numero"])
    assert client.get(f"/api/leads/{LEAD['numero']}").json()["dossier_fige"] is True
    r = client.post(f"/api/leads/{LEAD['numero']}", json={"surface_logement_m2": "90"})
    assert r.status_code == 423 and r.json()["detail"] == "Dossier facturé — montants figés"
    assert client.post(f"/prospect/{LEAD['numero']}/ajax", json={"surface_logement_m2": "90"}).status_code == 423
    assert client.post("/prospect/ajax", json=dict(LEAD, surface_logement_m2="90")).status_code == 423
    assert client.post(f"/api/simulateur/{LEAD['numero']}/state", json={"prix_pac": 1}).status_code == 423
    assert _octets_du_lead(LEAD["numero"]) == avant
    assert main.load_state_simulateur(LEAD["numero"])["prix_pac"] == 15990
    assert client.post(f"/api/devis/{LEAD['numero']}/envoyer", json={}).status_code == 423


def test_facture_emise_suffit_et_lead_libre_inchange(client):
    libre = dict(LEAD, numero="PR-07071", statut="devis_envoye", telephone="0611121319")
    facture = dict(LEAD, numero="PR-07072", statut="devis_envoye", telephone="0611121320")
    main._atomic_write_json(main.LEADS_PATH, [libre, facture])
    os.makedirs(main.FACTURES_DIR, exist_ok=True)
    main._atomic_write_json(main.FACTURES_META_PATH, {"PR-07072": [{"numero_facture": "FA-2026-0001"}]})
    try:
        assert client.get("/api/leads/PR-07072").json()["dossier_fige"] is True
        assert client.post("/api/leads/PR-07072", json={"surface_logement_m2": "90"}).status_code == 423
        assert client.get("/api/leads/PR-07071").json()["dossier_fige"] is False
        assert client.post("/api/leads/PR-07071", json={"surface_logement_m2": "90"}).status_code == 200
    finally:
        main._atomic_write_json(main.FACTURES_META_PATH, {})


def test_reprise_et_migration_ne_touchent_pas_un_dossier_fige(client):
    brut = {k: v for k, v in LEAD.items()}                     # année à 8 chiffres, champs du schéma absents
    main._atomic_write_json(main.LEADS_PATH, [brut, dict(LEAD, numero="PR-07073", statut="devis", telephone="0611121321")])
    avant = _octets_du_lead(LEAD["numero"])
    r = client.post("/api/admin/reprise-annee", json={"appliquer": True}, headers={"X-Admin-Token": _jeton_admin()}).json()
    assert [x["numero"] for x in r["leads"]] == ["PR-07073"]
    main._migrate_leads_schema()
    assert _octets_du_lead(LEAD["numero"]) == avant
    assert "nrp_log" in next(x for x in main._read_leads() if x["numero"] == "PR-07073")      # l'autre lead, lui, est migré


def test_devis_affiche_celui_archive(client):
    main._atomic_write_json(main.LEADS_PATH, [dict(LEAD)])
    os.makedirs(main.DEVIS_DIR, exist_ok=True)
    html = os.path.join(main.DEVIS_DIR, "PR-07070_v1.html")
    with open(html, "w", encoding="utf-8") as f:
        f.write("<html><body>DEVIS ARCHIVE DE2026-0001 15 990,00</body></html>")
    main._atomic_write_json(main.DEVIS_META_PATH, {"PR-07070": [{"version": 1, "numero_devis": "DE2026-0001", "html_file": html,
                                                                  "variante": "devis", "statut": "envoye"}]})
    try:
        assert "DEVIS ARCHIVE DE2026-0001" in client.get("/api/devis/PR-07070/preview?variante=devis").text
    finally:
        main._atomic_write_json(main.DEVIS_META_PATH, {})
