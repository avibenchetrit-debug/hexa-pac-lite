# -*- coding: utf-8 -*-
"""Fix PDF : « Télécharger PDF » dans la fenêtre du pré-devis / devis, dans un vrai Chromium (Playwright).
Fiches fabriquées ici (nouvelle fiche, fiche existante, dossier facturé avec devis archivé) : aucune donnée réelle.
Pour chaque cas : PDF reçu dès le premier clic, sans nouvel onglet, non vide, nommé avec le numéro imprimé dessus ;
puis clics répétés, ouvertures successives de la fenêtre et message clair en cas d'échec."""
import io
import os
import re
import socket
import threading
import time

import pytest

import main

pypdf = pytest.importorskip("pypdf")
sync_api = pytest.importorskip("playwright.sync_api")
uvicorn = pytest.importorskip("uvicorn")

BASE_LEAD = {"civilite": "Madame", "nom": "Fictif", "prenom": "Faustine", "telephone": "0600000001",
             "email": "fictif@example.invalid", "adresse_chantier": "12 rue Imaginaire", "cp_chantier": "75002",
             "code_postal_chantier": "75002", "ville_chantier": "Paris", "type_logement": "maison",
             "surface_logement_m2": "120", "hsp": "2,5", "mode_chauffage": "fioul", "ecs": "chaudiere",
             "type_emetteurs": "radiateurs_classiques", "alimentation_electrique": "monophase",
             "categorie": "tres_modeste", "nombre_personnes": "4", "annee_construction": "1968"}
NOUVELLE = {"civilite": "Madame", "nom": "Nouvelle", "prenom": "Noemie", "telephone": "0600000003",
            "email": "nouvelle@example.invalid", "adresse_chantier": "12 rue Imaginaire", "code_postal_chantier": "75002",
            "ville_chantier": "Paris", "type_logement": "maison", "surface_logement_m2": "120", "hsp": "2,5",
            "annee_construction": "1968", "mode_chauffage": "fioul", "type_emetteurs": "radiateurs_classiques",
            "ecs": "chaudiere", "alimentation_electrique": "monophase", "nombre_personnes": "4", "rfr": "15000"}
ARCHIVE_NUM = "DE2026-7512-1AF"            # numéro stocké ; le pré-devis archivé imprime PD2026-7512-1AF
REMPLIR = """(vals) => {
  for (const [n, v] of Object.entries(vals)) {
    const el = document.querySelector(`#form-prospect [name="${n}"]`);
    if (!el) continue;
    if (el.tagName === 'SELECT' && ![...el.options].some(o => o.value === v)) el.add(new Option(v, v));
    el.value = v;
    el.dispatchEvent(new Event('input', { bubbles: true }));
    el.dispatchEvent(new Event('change', { bubbles: true }));
  }
}"""
NUM_IMPRIME = re.compile(r"(?:PD|DE)\d{4}-[0-9A-Z-]+")


def _port_libre():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _semer():
    """Fiches fabriquées : PR-90001 (existante), PR-90002 (installation finie, pré-devis archivé)."""
    existante = dict(BASE_LEAD, numero="PR-90001", statut="devis")
    facture = dict(BASE_LEAD, numero="PR-90002", nom="Archive", prenom="Fabrice", telephone="0600000002", statut="devis")
    main._atomic_write_json(main.LEADS_PATH, [existante, facture])
    for n in ("PR-90001", "PR-90002"):
        main._atomic_write_json(main._state_simulateur_path(n), {})
        main.save_state_simulateur_atomic(n, {"service": "chauffage_seul"})
    main._atomic_write_json(main.LEADS_PATH, [existante, dict(facture, statut="installation_finie")])
    os.makedirs(main.DEVIS_DIR, exist_ok=True)
    html = f"<html><body><h1>PRE-DEVIS ARCHIVE PD{ARCHIVE_NUM[2:]}</h1></body></html>"
    html_path, pdf_path = (os.path.join(main.DEVIS_DIR, "PR-90002_v1" + ext) for ext in (".html", ".pdf"))
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)
    with sync_api.sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page()
        pg.set_content(html)
        with open(pdf_path, "wb") as f:
            f.write(pg.pdf(format="A4"))
        b.close()
    main._atomic_write_json(main.DEVIS_META_PATH, {"PR-90002": [
        {"version": 1, "numero_devis": ARCHIVE_NUM, "file": pdf_path, "html_file": html_path,
         "variante": "pre_devis", "statut": "envoye"}]})
    main._write_users([{"id": "testeur", "username": "testeur", "password_hash": main._hash_password("essai-local"),
                        "role": "admin", "actif": True, "cree_at": main._now_iso(), "visibilite": "tous"}])


@pytest.fixture(scope="module")
def serveur():
    try:
        with sync_api.sync_playwright() as p:
            p.chromium.launch().close()
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"Chromium indisponible : {exc}")
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
    main._atomic_write_json(main.DEVIS_META_PATH, {})
    main._atomic_write_json(main.LEADS_PATH, [])


@pytest.fixture
def page(serveur):
    _semer()
    with sync_api.sync_playwright() as p:
        b = p.chromium.launch()
        ctx = b.new_context(accept_downloads=True, viewport={"width": 1600, "height": 1000})
        pg = ctx.new_page()
        pg.goto(serveur + "/login")
        pg.fill("#username", "testeur")
        pg.fill("#password", "essai-local")
        pg.click("#login-btn")
        pg.wait_for_url(lambda u: "/login" not in u)
        pg.base = serveur
        yield pg
        b.close()


def _ouvrir_devis(pg, numero=None):
    if numero:
        pg.goto(f"{pg.base}/prospect/{numero}")
        pg.wait_for_function("document.body.dataset.prospectNumero === %r" % numero)
    pg.evaluate("window.hexaParcoursEtape(6)")
    pg.click("#btn-voir-devis")
    pg.wait_for_selector("#devis-pdf-btn", timeout=30000)


def _telecharger(pg):
    """Un clic : le PDF arrive dans la page (aucun onglet), le bouton affiche « Génération… » pendant la création."""
    onglets = len(pg.context.pages)
    with pg.expect_download(timeout=90000) as dl:
        pg.click("#devis-pdf-btn")
        if not pg.is_visible("#devis-pdf-erreur"):
            assert pg.inner_text("#devis-pdf-btn") in ("Génération…", "📥 Télécharger PDF")
    d = dl.value
    contenu = open(d.path(), "rb").read()
    assert len(pg.context.pages) == onglets                       # pas de nouvel onglet
    pg.wait_for_function("document.querySelector('#devis-pdf-btn').textContent.includes('Télécharger PDF')")
    assert pg.is_enabled("#devis-pdf-btn") and pg.is_hidden("#devis-pdf-erreur")
    return d.suggested_filename, contenu


def _numero_dans(pdf):
    texte = "".join(pg.extract_text() or "" for pg in pypdf.PdfReader(io.BytesIO(pdf)).pages)
    return set(NUM_IMPRIME.findall(texte))


def _verifier(nom, pdf, prefixe):
    assert pdf[:5] == b"%PDF-" and len(pdf) > 1000                 # non vide
    m = re.fullmatch(prefixe + r"_((?:PD|DE)\d{4}-[0-9A-Z-]+)\.pdf", nom)
    assert m, nom                                                   # le numéro du document, pas celui du prospect
    assert m.group(1) in _numero_dans(pdf)                         # c'est bien celui imprimé dans le PDF
    return m.group(1)


def test_nouvelle_fiche_pdf_du_premier_clic(page):
    page.goto(page.base + "/nouveau")
    page.wait_for_selector("#form-prospect [name=nom]", state="attached")
    page.evaluate(REMPLIR, NOUVELLE)
    _ouvrir_devis(page)
    numero = page.evaluate("document.body.dataset.prospectNumero")
    assert numero and numero.startswith("PR-")                     # la fiche vient d'être créée
    nom, pdf = _telecharger(page)
    assert _verifier(nom, pdf, "Pre-devis").startswith("PD")


def test_fiche_existante_pdf_du_premier_clic(page):
    _ouvrir_devis(page, "PR-90001")
    nom, pdf = _telecharger(page)
    assert _verifier(nom, pdf, "Pre-devis").startswith("PD")


def test_dossier_facture_rend_le_devis_archive(page):
    _ouvrir_devis(page, "PR-90002")
    nom, pdf = _telecharger(page)
    assert nom == "Pre-devis_PD2026-7512-1AF.pdf"
    assert _verifier(nom, pdf, "Pre-devis") == "PD2026-7512-1AF"
    assert pdf == open(os.path.join(main.DEVIS_DIR, "PR-90002_v1.pdf"), "rb").read()   # l'archive, pas un nouveau rendu


def test_clics_repetes_et_ouvertures_successives(page):
    requetes = []
    page.on("request", lambda r: "/pdf" in r.url and requetes.append(r.url))
    _ouvrir_devis(page, "PR-90001")
    # rafale de clics pendant la génération : un seul PDF demandé, un seul reçu
    telechargements = []
    page.on("download", lambda d: telechargements.append(d))
    page.click("#devis-pdf-btn")
    page.wait_for_function("document.querySelector('#devis-pdf-btn').textContent === 'Génération…'")
    for _ in range(4):
        page.click("#devis-pdf-btn", force=True)
    page.wait_for_function("document.querySelector('#devis-pdf-btn').textContent.includes('Télécharger PDF')", timeout=90000)
    page.wait_for_timeout(500)
    assert len(requetes) == 1 and len(telechargements) == 1
    # fenêtre fermée puis rouverte trois fois : chaque fois, le premier clic suffit, sans recharger la page
    for _ in range(3):
        page.click("#devis-close-btn")
        page.wait_for_selector("#devis-modal-overlay", state="detached")
        _ouvrir_devis(page)
        nom, pdf = _telecharger(page)
        _verifier(nom, pdf, "Pre-devis")
    assert len(page.context.pages) == 1


def test_echec_message_clair_dans_la_fenetre(page):
    _ouvrir_devis(page, "PR-90001")
    page.route("**/api/devis/*/pdf*", lambda r: r.fulfill(status=500, content_type="application/json",
                                                          body='{"detail":"Playwright indisponible: test"}'))
    page.click("#devis-pdf-btn")
    page.wait_for_selector("#devis-pdf-erreur:not([hidden])")
    msg = page.inner_text("#devis-pdf-erreur span")
    assert msg.startswith("Le PDF du pré-devis n'a pas pu être créé : Playwright indisponible: test.")
    assert "{" not in msg and len(page.context.pages) == 1
    assert page.is_enabled("#devis-pdf-btn")                       # on peut réessayer
    page.unroute("**/api/devis/*/pdf*")
    nom, pdf = _telecharger(page)                                  # le réessai fonctionne et efface le message
    _verifier(nom, pdf, "Pre-devis")


def test_fiche_incomplete_message_et_pas_de_pdf_de_la_page_d_erreur():
    from fastapi.testclient import TestClient
    main._atomic_write_json(main.LEADS_PATH, [dict(BASE_LEAD, numero="PR-90009", hsp="")])      # HSP manquante
    r = TestClient(main.app).get("/api/devis/PR-90009/pdf?variante=pre_devis")
    assert r.status_code == 422 and r.json()["detail"].startswith("Champs à compléter : ") and "HSP" in r.json()["detail"]
