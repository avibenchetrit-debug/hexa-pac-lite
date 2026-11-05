# -*- coding: utf-8 -*-
"""A.1 + A.2 + A.4 (05/11/2026) : à la validation de la VT, la pré-note (état juste avant) puis la note définitive
(gabarit du Master, données actuelles) sont archivées et datées, jamais écrasées ; la note porte « Visite technique
réalisée le JJ/MM/AAAA »."""
import os
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

import main
from tests.test_notedim_a_cascade import ETAT_GESLOT, NUM, _donnees_restaurees, _preparer  # noqa: F401


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("AUTH_ENFORCE", "0")
    monkeypatch.setattr(main, "_html_to_pdf_playwright", lambda html, request: html.encode("utf-8"))
    chemins = (main.NOTES_DIM_ARCHIVES_PATH,)
    sauve = {c: open(c, "rb").read() for c in chemins if os.path.exists(c)}
    if os.path.exists(main.NOTES_DIM_ARCHIVES_PATH):
        os.remove(main.NOTES_DIM_ARCHIVES_PATH)
    _preparer(dict(ETAT_GESLOT))
    yield TestClient(main.app)
    for e in main._notes_archivees_vt(NUM):
        if os.path.exists(e["file"]):
            os.remove(e["file"])
    for c in chemins:
        if c in sauve:
            open(c, "wb").write(sauve[c])
        elif os.path.exists(c):
            os.remove(c)


def _contenu(e):
    return open(e["file"], encoding="utf-8").read()


def test_validation_vt_archive_pre_note_puis_note_definitive(client):
    r = client.post(f"/api/leads/{NUM}/vt", json={"action": "valider"}).json()
    assert [n["nature"] for n in r["notes_dimensionnement"]] == ["pre", "definitive"]
    assert not any("erreur" in n for n in r["notes_dimensionnement"])
    pre, defi = main._notes_archivees_vt(NUM)
    assert "NOTE DE PRÉ-DIMENSIONNEMENT" in _contenu(pre) and "En attente de la visite technique" in _contenu(pre)
    jour = datetime.now(main.PARIS_TZ).strftime("%d/%m/%Y")
    assert "NOTE DE DIMENSIONNEMENT" in _contenu(defi) and "NOTE DE PRÉ-DIMENSIONNEMENT" not in _contenu(defi)
    assert f"Visite technique réalisée le {jour}" in _contenu(defi)                        # A.4
    assert "note_dim/" not in _contenu(defi) and "Plage de cohérence" in _contenu(defi)   # gabarit du Master
    liste = client.get(f"/api/notedim/{NUM}/archives").json()
    assert [x["nature"] for x in liste] == ["pre", "definitive"]
    assert liste[1]["libelle"].startswith("Note de dimensionnement définitive — générée à la validation de la VT (")
    pdf = client.get(f"/api/notedim/{NUM}/archives/1?telecharger=1")
    assert pdf.status_code == 200 and 'filename="NoteDim-DEFINITIVE_' in pdf.headers["content-disposition"]


def test_jamais_ecrasees_et_pas_de_doublon_si_deja_validee(client):
    client.post(f"/api/leads/{NUM}/vt", json={"action": "valider"})
    r = client.post(f"/api/leads/{NUM}/vt", json={"action": "valider"}).json()     # déjà validée : rien de plus
    assert r["notes_dimensionnement"] == [] and len(main._notes_archivees_vt(NUM)) == 2
    client.post(f"/api/leads/{NUM}/vt", json={"action": "annuler"})
    client.post(f"/api/leads/{NUM}/vt", json={"action": "valider"})                 # revalidation : 2 de plus
    archives = main._notes_archivees_vt(NUM)
    assert [a["nature"] for a in archives] == ["pre", "definitive", "pre", "definitive"]
    assert all(os.path.exists(a["file"]) for a in archives)


def test_fiche_incomplete_la_vt_est_quand_meme_validee(client, monkeypatch):
    monkeypatch.setattr(main, "validate_prospect_for_devis", lambda p, s, a=None: ["Surface"])
    r = client.post(f"/api/leads/{NUM}/vt", json={"action": "valider"}).json()
    assert r["vt_validee"] is True
    assert all(n.get("erreur", "").startswith("fiche incomplète") for n in r["notes_dimensionnement"])
    assert main._notes_archivees_vt(NUM) == []


def test_textes_methode_et_document_accompagne(client):
    """A.5 : la méthode réellement employée ; A.6 : le document accompagné est nommé (plus de phrase « tronquée »)."""
    import html as _html
    import re
    t = re.sub(r"\s+", " ", _html.unescape(re.sub(r"<[^>]+>", " ", client.get(f"/api/notedim/{NUM}/preview").text)))
    assert "déduit du questionnaire d'isolation du logement (toiture, murs, menuiseries)" in t
    assert "table NF P52-612/CN" in t and "DTU 65.11" not in t
    assert "déduit de la classe énergétique" not in t and "après l'audit énergétique" not in t
    assert re.search(r"Il accompagne le pré-devis du dossier HX\d{2}-\d{4} et peut être remis au délégataire CEE\.", t)
    assert "document commercial correspondant" not in t
