# -*- coding: utf-8 -*-
"""Lot 13g : pose de rappel évidente sur la fiche — bouton « 📅 Rappel » dans le bandeau (à côté de « Fin d'appel »)
qui ouvre le panneau sur la date, titre « Programmer un rappel » au-dessus des champs, plus de titre orphelin."""
import socket
import threading
import time

import pytest

import main

sync_api = pytest.importorskip("playwright.sync_api")
uvicorn = pytest.importorskip("uvicorn")

LEAD = {"numero": "PR-13701", "civilite": "Madame", "nom": "Rappel", "prenom": "Rose", "telephone": "0611137011",
        "email": "rappel@example.invalid", "adresse_chantier": "1 rue A", "cp_chantier": "53000",
        "code_postal_chantier": "53000", "ville_chantier": "Laval", "type_logement": "maison", "categorie": "modeste",
        "statut": "a_rappeler"}


def _port_libre():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def serveur():
    try:
        with sync_api.sync_playwright() as p:
            p.chromium.launch().close()
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"Chromium indisponible : {exc}")
    main._atomic_write_json(main.LEADS_PATH, [dict(LEAD)])
    main._write_users([{"id": "testeur", "username": "testeur", "password_hash": main._hash_password("essai-local"),
                        "role": "admin", "actif": True, "cree_at": main._now_iso(), "visibilite": "tous"}])
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
    main._atomic_write_json(main.LEADS_PATH, [])


@pytest.fixture
def page(serveur):
    with sync_api.sync_playwright() as p:
        b = p.chromium.launch()
        ctx = b.new_context(viewport={"width": 1440, "height": 900})
        ctx.route("**/*", lambda r: r.continue_() if r.request.url.startswith(serveur) else r.abort())
        pg = ctx.new_page()
        pg.goto(serveur + "/login")
        pg.fill("#username", "testeur")
        pg.fill("#password", "essai-local")
        pg.click("#login-btn")
        pg.wait_for_url(lambda u: "/login" not in u)
        pg.goto(f"{serveur}/prospect/{LEAD['numero']}")
        pg.wait_for_function("document.body.dataset.prospectNumero === %r && !!document.getElementById('p-rappel-btn')" % LEAD["numero"])
        pg.wait_for_timeout(500)
        yield pg
        b.close()


def test_bouton_rappel_ouvre_le_panneau_sur_la_date(page):
    assert page.is_hidden("#p-fin-appel-pop")
    assert page.inner_text("#p-rappel-btn") == "📅 Rappel" and page.is_visible("#p-rappel-btn")
    # à côté de « Fin d'appel » : même conteneur, juste après
    assert page.evaluate("document.getElementById('p-fin-appel-btn').nextElementSibling.id") == "p-rappel-btn"
    page.click("#p-rappel-btn")
    page.wait_for_function("document.activeElement && document.activeElement.id === 'suivi-rap-date'")
    assert page.is_visible("#p-fin-appel-pop") and page.is_visible("#suivi-rap-date")
    assert page.get_attribute("#p-fin-appel-btn", "aria-expanded") == "true"
    page.click("#p-rappel-btn")                                                 # déjà ouvert : reste ouvert, date ciblée
    page.wait_for_timeout(200)
    assert page.is_visible("#p-fin-appel-pop") and page.evaluate("document.activeElement.id") == "suivi-rap-date"


def test_titre_visible_au_dessus_des_champs_et_plus_de_titre_orphelin(page):
    page.click("#p-fin-appel-btn")
    assert page.is_visible("#suivi-rap-titre") and page.inner_text("#suivi-rap-titre") == "Programmer un rappel"
    assert page.evaluate("document.getElementById('suivi-rap-titre').nextElementSibling.classList.contains('row-rappel-compact')")
    assert page.evaluate("[...document.querySelectorAll('*')].filter(e => e.children.length === 0 && "
                         "e.textContent.trim() === 'Programmer un rappel').map(e => e.id)") == ["suivi-rap-titre"]


def test_poser_un_rappel_depuis_le_bouton(page):
    page.click("#p-rappel-btn")
    page.wait_for_function("document.activeElement && document.activeElement.id === 'suivi-rap-date'")
    page.fill("#suivi-rap-date", "2030-01-15")
    page.fill("#suivi-rap-heure", "10:30")
    page.fill("#suivi-rap-motif", "relancer devis")
    page.click("#suivi-rap-poser")
    page.wait_for_function("/2030|15\\/01/.test(document.getElementById('suivi-actif').textContent)", timeout=10000)
    lead = next(x for x in main._read_leads() if x["numero"] == LEAD["numero"])
    assert "2030-01-15" in str(lead)
