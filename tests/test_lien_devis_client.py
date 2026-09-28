# -*- coding: utf-8 -*-
"""Lien client sans numéro de version (/devis-public/{n}/{jeton} et /pdf) : la DERNIÈRE version envoyée ;
dossier facturé : le devis archivé. Les liens avec numéro de version ne changent pas. Fiches fabriquées."""
import os

import pytest
from fastapi.testclient import TestClient

import main

LEAD = {"numero": "PR-95001", "civilite": "Madame", "nom": "Fictif", "prenom": "Faustine", "telephone": "0600000061",
        "email": "fictif@example.invalid", "adresse_chantier": "12 rue Imaginaire", "cp_chantier": "75002",
        "code_postal_chantier": "75002", "ville_chantier": "Paris", "statut": "devis_envoye"}
VERSIONS = [(1, "pre_devis", "DE2026-7512-1FF"), (2, "devis", "DE2026-7512-2FF"), (3, "pre_devis", "DE2026-7512-3FF")]


@pytest.fixture
def client():
    return TestClient(main.app)


def _semer(statut="devis_envoye"):
    os.makedirs(main.DEVIS_DIR, exist_ok=True)
    items = []
    for v, variante, num in VERSIONS:
        pdf, html = (os.path.join(main.DEVIS_DIR, f"PR-95001_v{v}.{ext}") for ext in ("pdf", "html"))
        with open(pdf, "wb") as f:
            f.write(f"%PDF-1.4 version {v}\n%%EOF".encode())
        with open(html, "w", encoding="utf-8") as f:
            f.write(f"<html><body>DEVIS VERSION {v} {num}</body></html>")
        items.append({"version": v, "variante": variante, "numero_devis": num, "file": pdf, "html_file": html,
                      "sent_at": f"2026-09-0{v}T10:00:00"})
    main._atomic_write_json(main.LEADS_PATH, [dict(LEAD, statut=statut)])
    main._atomic_write_json(main.DEVIS_META_PATH, {"PR-95001": items})


@pytest.fixture(autouse=True)
def _nettoyer():
    yield
    main._atomic_write_json(main.DEVIS_META_PATH, {})
    main._atomic_write_json(main.LEADS_PATH, [])


def _jeton():
    return main._sign_devis_token("PR-95001")


def test_lien_sans_version_sert_la_derniere_version(client):
    _semer()
    r = client.get(f"/devis-public/PR-95001/{_jeton()}/pdf")
    assert r.status_code == 200 and r.content.startswith(b"%PDF-1.4 version 3")
    assert r.headers["content-disposition"] == 'attachment; filename="Pre-devis_PD2026-7512-3FF.pdf"'
    page = client.get(f"/devis-public/PR-95001/{_jeton()}").text
    assert "DEVIS VERSION 3" in page and "DEVIS VERSION 1" not in page      # la page et son bouton PDF : même version


def test_liens_avec_numero_de_version_inchanges(client):
    _semer()
    for v, variante, num in VERSIONS:
        r = client.get(f"/devis-public/PR-95001/{v}/{main._sign_devis_token_v('PR-95001', v)}/pdf")
        assert r.status_code == 200 and r.content.startswith(f"%PDF-1.4 version {v}".encode())
        pre = variante == "pre_devis"
        attendu = ("Pre-devis_PD" if pre else "Devis_DE") + num[2:]
        assert r.headers["content-disposition"] == f'attachment; filename="{attendu}.pdf"'


def test_dossier_facture_sert_le_devis_archive(client):
    _semer(statut="installation_finie")
    r = client.get(f"/devis-public/PR-95001/{_jeton()}/pdf")
    assert r.content.startswith(b"%PDF-1.4 version 2")                     # le devis (v2), pas le pré-devis v3 envoyé après
    assert r.headers["content-disposition"] == 'attachment; filename="Devis_DE2026-7512-2FF.pdf"'
    assert "DEVIS VERSION 2" in client.get(f"/devis-public/PR-95001/{_jeton()}").text


def test_lien_invalide_toujours_refuse(client):
    _semer()
    assert client.get("/devis-public/PR-95001/faux-jeton/pdf").status_code == 403
