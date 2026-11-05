# -*- coding: utf-8 -*-
"""A.3 (05/11/2026) : libellé exact des notes archivées (pré-dimensionnement / dimensionnement / définitive, date,
ancien modèle) ; note toujours régénérée à l'envoi ; le PDF téléchargé n'est plus rangé sous le numéro d'envoi ;
l'ancien gabarit v5 n'existe plus."""
import os

import pytest
from fastapi.testclient import TestClient

import main

LEAD_SANS_VT = {"numero": "PR-000164", "vt_validee": False, "vt_date": ""}
LEAD_VT = {"numero": "PR-000175", "vt_validee": True, "vt_date": "2026-07-15T10:00:00+02:00"}


def test_libelles():
    pre = {"variante": "pre_devis", "numero_devis": "DE2026-4932-1GR", "sent_at": "2026-07-06T16:58:46+02:00"}
    assert main._note_archivee(pre, LEAD_SANS_VT)["libelle"] == (
        "Note de pré-dimensionnement — envoyée avec le pré-devis DE2026-4932-1GR le 06/07/2026 — ancien modèle")
    devis_avant_vt = {"variante": "devis", "numero_devis": "DE2026-1", "sent_at": "2026-06-22T13:15:12"}
    a = main._note_archivee(devis_avant_vt, {"vt_validee": False})
    assert a["libelle"] == "Note de dimensionnement — envoyée avec le devis DE2026-1 le 22/06/2026 — ancien modèle"
    assert a["definitive"] is False and a["nom_fichier"] == "Note-dimensionnement"
    apres_vt = {"variante": "devis", "numero_devis": "DE2026-2", "sent_at": "2026-07-16T09:00:00+02:00"}
    b = main._note_archivee(apres_vt, LEAD_VT)
    assert b["definitive"] and b["libelle"].startswith("Note de dimensionnement définitive — envoyée avec le devis DE2026-2")
    recent = {"variante": "pre_devis", "numero_devis": "DE2026-3", "sent_at": "2026-11-04T18:05:00+01:00"}
    assert "ancien modèle" not in main._note_archivee(recent, LEAD_SANS_VT)["libelle"]
    # après le 07/07/2026 un devis ne part qu'avec la VT validée : définitive, même si vt_date a été réécrite après
    assert main._note_archivee({"variante": "devis", "sent_at": "2026-07-15T17:55:00+02:00"},
                               {"vt_validee": True, "vt_date": "2026-07-16T10:41:06+02:00"})["definitive"] is True
    # avant le 07/07 : définitive seulement si la VT précédait l'envoi
    assert main._note_archivee({"variante": "devis", "sent_at": "2026-07-01T13:08:00+02:00"},
                               {"vt_validee": False})["definitive"] is False


def test_ancien_gabarit_supprime_et_jamais_servi():
    racine = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "templates")
    assert not os.path.exists(os.path.join(racine, "notedim_pac_template_v5.html"))
    gabarit = open(os.path.join(racine, "notedim_pac.html"), encoding="utf-8").read()
    assert '{% include "note_dim/note_dimensionnement_pdf.html" %}' in gabarit and "v5.html\" %}" not in gabarit


def test_note_toujours_regeneree_a_l_envoi(monkeypatch):
    chemin = main._notedim_path("PR-77001", 2)
    os.makedirs(os.path.dirname(chemin), exist_ok=True)
    open(chemin, "wb").write(b"%PDF ANCIENNE NOTE")                  # un PDF déjà là (téléchargé plus tôt)
    monkeypatch.setattr(main, "_render_notedim_html", lambda request, numero: "<html>NOUVELLE</html>")
    monkeypatch.setattr(main, "_html_to_pdf_playwright", lambda html, request: b"%PDF " + html.encode())
    try:
        assert main._ensure_notedim_pdf("PR-77001", None, 2) == chemin
        assert open(chemin, "rb").read() == b"%PDF <html>NOUVELLE</html>"
    finally:
        os.remove(chemin)


def test_pdf_telecharge_pas_range_sous_le_numero_d_envoi(monkeypatch):
    monkeypatch.setenv("AUTH_ENFORCE", "0")
    monkeypatch.setattr(main, "_notedim_archivee", lambda numero: (None, None))
    monkeypatch.setattr(main, "_build_notedim_context", lambda request, numero: {"numero_notedim": "ND-TEST"})
    monkeypatch.setattr(main, "_html_to_pdf_playwright", lambda html, request: b"%PDF-1.4 note")
    monkeypatch.setattr(main, "_find_lead", lambda numero: {"numero": numero})
    monkeypatch.setattr(main, "_next_devis_version", lambda numero: 9)
    import types
    monkeypatch.setattr(main.templates.env, "get_template", lambda nom: types.SimpleNamespace(render=lambda ctx: "<html/>"))
    avant = os.path.exists(main._notedim_path("PR-77002", 9))
    r = TestClient(main.app).get("/api/notedim/PR-77002/pdf")
    assert r.status_code == 200 and r.content == b"%PDF-1.4 note"
    assert os.path.exists(main._notedim_path("PR-77002", 9)) is avant is False
