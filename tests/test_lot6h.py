# -*- coding: utf-8 -*-
"""Lot 6h : note de dim et facture — libellés sans ambiguïté, accès visibles. Vrai Chromium, fiches fabriquées :
PR-93001 (VT non validée), PR-93002 (VT validée), PR-93003 (installation finie : devis + note archivés, sans facture),
PR-93004 (facture émise)."""
import io
import os
import re
import socket
import threading
import time

import pytest

import main
from tests.test_fix_pdf import BASE_LEAD

pypdf = pytest.importorskip("pypdf")
sync_api = pytest.importorskip("playwright.sync_api")
uvicorn = pytest.importorskip("uvicorn")

ORANGE = ("Calcul provisoire, fait avec les informations données par le client au téléphone. Ne pas faire signer. "
          "La note définitive sera disponible après validation de la visite technique.")


def _port_libre():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _pdf(path, texte):
    with sync_api.sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page()
        pg.set_content(f"<html><body><h1>{texte}</h1></body></html>")
        with open(path, "wb") as f:
            f.write(pg.pdf(format="A4"))
        b.close()


def _semer():
    leads = [dict(BASE_LEAD, numero="PR-93001", telephone="0600000031", statut="devis"),
             dict(BASE_LEAD, numero="PR-93002", telephone="0600000032", statut="devis", vt_validee=True, vt_date="2026-09-20"),
             dict(BASE_LEAD, numero="PR-93003", nom="Archive", telephone="0600000033", statut="devis", vt_validee=True),
             dict(BASE_LEAD, numero="PR-93004", nom="Facture", telephone="0600000034", statut="devis", vt_validee=True)]
    main._atomic_write_json(main.LEADS_PATH, leads)
    for l in leads:
        main._atomic_write_json(main._state_simulateur_path(l["numero"]), {})
        main.save_state_simulateur_atomic(l["numero"], {"service": "chauffage_seul"})
    os.makedirs(main.DEVIS_DIR, exist_ok=True)
    meta = {}
    for n in ("PR-93003", "PR-93004"):
        devis, note = (os.path.join(main.DEVIS_DIR, f"{n}_{k}v1.pdf") for k in ("", "notedim_"))
        _pdf(devis, f"DEVIS ARCHIVE {n}")
        _pdf(note, f"NOTE DE DIM ARCHIVEE {n}")
        meta[n] = [{"version": 1, "numero_devis": "DE2025-7512-1AF", "variante": "devis", "statut": "envoye",
                    "sent_at": "2025-11-03T10:00:00+01:00", "file": devis, "notedim_file": note}]
    main._atomic_write_json(main.DEVIS_META_PATH, meta)
    os.makedirs(main.FACTURES_DIR, exist_ok=True)
    fa = os.path.join(main.FACTURES_DIR, "PR-93004_FA-2026-0001.pdf")
    _pdf(fa, "FACTURE FA-2026-0001")
    main._atomic_write_json(main.FACTURES_META_PATH, {"PR-93004": [
        {"numero_facture": "FA-2026-0001", "file": fa, "date_emission": "01/09/2026", "created_at": "2026-09-01T10:00:00"}]})
    # le dossier facturé passe ensuite en « installation finie » (verrou Lot 6c)
    leads[2]["statut"] = "installation_finie"
    main._atomic_write_json(main.LEADS_PATH, leads)
    main._write_users([{"id": "testeur", "username": "testeur", "password_hash": main._hash_password("essai-local"),
                        "role": "admin", "actif": True, "cree_at": main._now_iso(), "visibilite": "tous"}])


@pytest.fixture(scope="module")
def serveur():
    try:
        with sync_api.sync_playwright() as p:
            p.chromium.launch().close()
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"Chromium indisponible : {exc}")
    _semer()
    port = _port_libre()
    srv = uvicorn.Server(uvicorn.Config(main.app, host="127.0.0.1", port=port, log_level="warning"))
    th = threading.Thread(target=srv.run, daemon=True)
    th.start()
    for _ in range(200):
        if srv.started:
            break
        time.sleep(0.05)
    yield f"http://127.0.0.1:{port}"
    srv.should_exit = True
    th.join(timeout=10)
    main._atomic_write_json(main.FACTURES_META_PATH, {})
    main._atomic_write_json(main.DEVIS_META_PATH, {})
    main._atomic_write_json(main.LEADS_PATH, [])


@pytest.fixture
def page(serveur):
    with sync_api.sync_playwright() as p:
        b = p.chromium.launch()
        ctx = b.new_context(accept_downloads=True, viewport={"width": 1600, "height": 1000})
        ctx.route("**/*", lambda r: r.continue_() if r.request.url.startswith(serveur) else r.abort())
        pg = ctx.new_page()
        pg.goto(serveur + "/login")
        pg.fill("#username", "testeur")
        pg.fill("#password", "essai-local")
        pg.click("#login-btn")
        pg.wait_for_url(lambda u: "/login" not in u)
        pg.base = serveur
        yield pg
        b.close()


def ouvrir(pg, numero, etape=6):
    pg.goto(f"{pg.base}/prospect/{numero}")
    pg.wait_for_function("document.body.dataset.prospectNumero === %r && typeof window.hexaParcoursEtape === 'function'" % numero)
    pg.wait_for_timeout(800)
    pg.evaluate(f"window.hexaParcoursEtape({etape})")
    if etape == 6:
        pg.wait_for_selector("#btn-voir-devis", state="visible")


def definitifs_visibles(pg):
    return pg.evaluate("""[...document.querySelectorAll('button, a, [role=tab]')]
        .filter(e => e.offsetParent !== null && /définitive/i.test(e.textContent)).map(e => e.textContent.trim())""")


# ---------------------------------------------------------------- VT non validée : seule la pré-note, provisoire
def test_vt_non_validee_pre_note_seulement(page):
    ouvrir(page, "PR-93001")
    assert page.inner_text(".sim-btn-note-dim") == "Pré-note de dim (provisoire)"
    assert page.query_selector("#btn-note-definitive") is None and definitifs_visibles(page) == []
    page.click(".sim-btn-note-dim")
    page.wait_for_selector("#sim-dim-modal")
    assert page.inner_text("#sim-dim-modal h3") == "PRÉ-NOTE DE DIMENSIONNEMENT — PROVISOIRE"
    assert page.inner_text(".sim-dim-provisoire") == ORANGE
    fond = page.eval_on_selector(".sim-dim-provisoire", "e => getComputedStyle(e).backgroundColor")
    assert fond == "rgb(255, 244, 229)"                                    # bandeau orange
    assert page.is_hidden(".sim-dim-filigrane")                           # à l'écran : pas de filigrane
    page.emulate_media(media="print")
    assert page.is_visible(".sim-dim-filigrane")
    pdf = page.pdf(format="A4")                                            # impression : filigrane sur chaque page
    pages = pypdf.PdfReader(io.BytesIO(pdf)).pages
    assert all("PROVISOIRE — NE PAS SIGNER" in (p.extract_text() or "") for p in pages), len(pages)
    page.emulate_media(media="screen")
    page.click("#sim-dim-close")
    page.click("#btn-voir-devis")                                          # fenêtre du pré-devis : pas d'onglet note
    page.wait_for_selector("#devis-pdf-btn")
    assert page.query_selector("[data-kind=notedim]") is None and definitifs_visibles(page) == []


# ---------------------------------------------------------------- VT validée : bouton vert, onglet, bandeau, fichier
def test_vt_validee_note_definitive(page):
    ouvrir(page, "PR-93002")
    assert page.query_selector(".sim-btn-note-dim") is None                # plus de pré-note ambiguë
    bouton = page.wait_for_selector("#btn-note-definitive", state="visible")
    assert bouton.inner_text() == "📐 Note de dim définitive"
    assert bouton.evaluate("e => getComputedStyle(e).backgroundColor") == "rgb(21, 128, 61)"   # vert
    bouton.click()
    page.wait_for_selector("#devis-pdf-btn")
    assert page.inner_text(".devis-tab.active") == "📐 Note de dim définitive"
    assert "/api/notedim/PR-93002/preview" in page.get_attribute("#devis-preview-frame", "src")
    assert page.inner_text("#devis-note-definitive") == "NOTE DÉFINITIVE — à faire signer par le client et à envoyer au délégataire"
    with page.expect_download(timeout=90000) as dl:
        page.click("#devis-pdf-btn")
    d = dl.value
    m = re.fullmatch(r"NoteDim-DEFINITIVE_(ND2026-93002-FI)\.pdf", d.suggested_filename)
    assert m, d.suggested_filename
    texte = "".join(p.extract_text() or "" for p in pypdf.PdfReader(d.path()).pages)
    assert m.group(1) in texte and "NOTE DÉFINITIVE" not in texte             # bandeau à l'écran seulement
    page.click(".devis-tab[data-kind=devis]")                              # onglet devis : pas de bandeau vert
    assert page.is_hidden("#devis-note-definitive")


# ---------------------------------------------------------------- dossier facturé : la note archivée
def test_dossier_facture_note_archivee(page):
    archive = open(os.path.join(main.DEVIS_DIR, "PR-93003_notedim_v1.pdf"), "rb").read()
    apercu = page.request.get(page.base + "/api/notedim/PR-93003/preview")
    assert apercu.status == 200 and apercu.body() == archive
    r = page.request.get(page.base + "/api/notedim/PR-93003/pdf")
    assert r.body() == archive
    assert r.headers["content-disposition"] == 'attachment; filename="NoteDim-DEFINITIVE_ND2025-93003-AR.pdf"'
    dl = page.request.get(page.base + "/api/notedim/PR-93003/download?version=1")
    assert 'filename="NoteDim-DEFINITIVE_ND2025-93003-AR.pdf"' in dl.headers["content-disposition"]
    assert not os.path.exists(os.path.join(main.DEVIS_DIR, "PR-93003_notedim_v2.pdf"))   # rien de régénéré


# ---------------------------------------------------------------- Suivi : VT en premier ; facture à générer / à voir
def ouvrir_suivi(pg, numero):
    ouvrir(pg, numero, etape=1)
    pg.click("#p-suivi-btn")
    pg.wait_for_selector("#p-suivi-pop:not([hidden])")


def test_suivi_valider_la_vt_en_premier(page):
    ouvrir_suivi(page, "PR-93001")
    lignes = page.eval_on_selector("#p-suivi-pop .fiche-statvt-top",
                                   "e => [...e.children].filter(c => c.offsetParent !== null).sort((a, b) => a.getBoundingClientRect().top - b.getBoundingClientRect().top).map(c => c.className)")
    assert lignes[0] == "fiche-vt-row"
    valider = page.wait_for_selector("#p-suivi-pop .fiche-vt-valider", state="visible")
    assert valider.inner_text() == "✅ Valider la VT"
    assert page.is_hidden("#p-suivi-pop .fiche-fact-row")                  # ni installation finie, ni facture


def test_installation_finie_generer_la_facture(page):
    ouvrir_suivi(page, "PR-93003")
    bouton = page.wait_for_selector("#p-suivi-pop .fiche-facture-generer", state="visible")
    assert bouton.inner_text() == "🧾 Générer la facture"
    bouton.click()
    ligne = page.wait_for_selector("#documents-panel .docs-facture-row", state="visible")
    assert "Installation finie" in ligne.inner_text() and ligne.is_visible()
    assert page.evaluate("document.activeElement && document.activeElement.id") == "facture-date-fin"
    # panneau Documents : la note a son libellé sans ambiguïté
    assert page.inner_text("#documents-panel .docs-notedim-label") == "Note de dim définitive (envoyée avec le devis DE2025-7512-1AF)"


def test_facture_existante_voir_la_facture(page):
    ouvrir_suivi(page, "PR-93004")
    lien = page.wait_for_selector("#p-suivi-pop .fiche-facture-voir", state="visible")
    assert lien.inner_text() == "🧾 Voir la facture"
    assert page.query_selector("#p-suivi-pop .fiche-facture-generer") is None
    lien.click()
    bloc = page.wait_for_selector("#docs-factures-block:not(.is-collapsed) #docs-factures-list", state="visible")
    assert "FA-2026-0001" in bloc.inner_text()


# ---------------------------------------------------------------- en dernier : valider la VT fait apparaître la note définitive
def test_valider_la_vt_fait_apparaitre_la_note_definitive(page):
    ouvrir_suivi(page, "PR-93001")
    page.click("#p-suivi-pop .fiche-vt-valider")
    page.wait_for_function("document.body.dataset.vtValidee === '1'")
    page.wait_for_timeout(800)
    page.evaluate("window.hexaParcoursEtape(6)")
    page.wait_for_selector("#btn-note-definitive", state="visible")
    assert page.query_selector(".sim-btn-note-dim") is None
