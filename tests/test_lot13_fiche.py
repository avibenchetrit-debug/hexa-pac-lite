# -*- coding: utf-8 -*-
"""Lot 13 : la fiche (vrai Chromium) affiche les 3 tuiles Économies d'énergie / Valeur verte / Gain total, et le
pré-devis reprend exactement les mêmes chiffres. Étape 2 : valeur du bien et classe DPE pré-remplies.
Fiche fabriquée PR-95013 (gaz, Sarthe, sans DPE)."""
import re
import socket
import threading
import time

import pytest

import main

sync_api = pytest.importorskip("playwright.sync_api")
uvicorn = pytest.importorskip("uvicorn")

LEAD = {"numero": "PR-95013", "civilite": "Madame", "nom": "Fictif", "prenom": "Vera", "email": "fictif@example.invalid",
        "telephone": "0600000013", "adresse_chantier": "1 RUE IMAGINAIRE", "cp_chantier": "72300",
        "code_postal_chantier": "72300", "ville_chantier": "SOLESMES", "type_logement": "maison", "surface_logement_m2": "100",
        "hsp": "2,5", "annee_construction": "1968", "type_emetteurs": "radiateurs_classiques",
        "alimentation_electrique": "monophase", "nombre_personnes": "3", "rfr": "15000", "categorie": "tres_modeste",
        "statut": "a_rappeler", "mode_chauffage": "gaz", "ecs": "chaudiere", "cout_energetique_mensuel_eur": "150",
        "cout_energie_source": "reel", "prix_m2_estime": "1800"}
NUM = LEAD["numero"]


def _port_libre():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(autouse=True)
def _donnees_restaurees():
    chemins = (main.PARAMETRES_ADMIN_PATH, main.LEADS_PATH, main.COUNTERS_PATH, main.DEVIS_ENVOYES_PATH)
    sauve = {c: open(c, "rb").read() for c in chemins if main.os.path.exists(c)}
    absents = [c for c in chemins if not main.os.path.exists(c)]
    yield
    for c, octets in sauve.items():
        open(c, "wb").write(octets)
    for c in absents:
        if main.os.path.exists(c):
            main.os.remove(c)


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
    main._atomic_write_json(main.LEADS_PATH, [])


@pytest.fixture
def page(serveur):
    main._atomic_write_json(main.LEADS_PATH, [dict(LEAD)])
    main._atomic_write_json(main._state_simulateur_path(NUM), {})
    main.save_state_simulateur_atomic(NUM, {"service": "chauffage_seul", "option": "opt3"})
    main._write_users([{"id": "testeur", "username": "testeur", "password_hash": main._hash_password("essai-local"),
                        "role": "admin", "actif": True, "cree_at": main._now_iso(), "visibilite": "tous"}])
    with sync_api.sync_playwright() as p:
        b = p.chromium.launch()
        ctx = b.new_context(viewport={"width": 1440, "height": 900})
        ctx.route("**/*", lambda r: r.continue_() if r.request.url.startswith(serveur) else r.abort())
        pg = ctx.new_page()
        pg.erreurs_js = []
        pg.on("pageerror", lambda e: pg.erreurs_js.append(str(e)))
        pg.goto(serveur + "/login")
        pg.fill("#username", "testeur")
        pg.fill("#password", "essai-local")
        pg.click("#login-btn")
        pg.wait_for_url(lambda u: "/login" not in u)
        pg.goto(f"{serveur}/prospect/{NUM}")
        pg.wait_for_function("document.body.dataset.prospectNumero === %r && typeof window.hexaParcoursEtape === 'function'" % NUM)
        pg.wait_for_timeout(700)
        yield pg
        b.close()


def espaces(t):
    return re.sub(r"[\s  ]+", " ", t).strip()


def test_etape2_valeur_du_bien_et_classe_preremplies(page):
    page.evaluate("window.hexaParcoursEtape(2)")
    page.wait_for_function("document.querySelector('[name=valeur_bien_estimee]').value === '180000'")
    assert page.input_value("[name=classe_dpe_avant]") == "aucun"           # pas de DPE trouvé
    page.fill("[name=valeur_bien_estimee]", "210000")                        # saisie manuelle : jamais écrasée
    page.evaluate("window.hexaL6Maj()")
    assert page.input_value("[name=valeur_bien_estimee]") == "210000"


def test_tuiles_fiche_identiques_au_predevis(page):
    page.evaluate("window.hexaParcoursEtape(6)")
    page.wait_for_selector("#p6-tuile-vv")
    tuile = lambda sel: espaces(page.inner_text(sel))
    vv, total, rent = tuile("#p6-tuile-vv b"), tuile("#p6-tuile-total b"), tuile("#p6-tuile-rent")
    assert re.fullmatch(r"\+ [\d ]+ € à \+ [\d ]+ €", vv), vv              # fiche : fourchette complète
    bas = re.match(r"\+ ([\d ]+ €)", vv).group(1)
    assert "(classe estimée)" in tuile("#p6-tuile-vv") and rent.startswith("rentabilisé")
    page.click("#btn-voir-devis")
    page.wait_for_selector("#devis-preview-frame")
    frame = page.frame_locator("#devis-preview-frame")
    frame.locator(".projet-apercu-tuiles").wait_for()
    doc = espaces(frame.locator(".projet-apercu").inner_text())
    assert "à partir de " + bas in doc and vv not in doc                     # document client : bas de la fourchette
    # fiche inchangée : total au milieu ; document : économies + bas de la fourchette
    nombre = lambda t: int(re.sub(r"\D", "", t))
    eur = lambda n: f"{n:,}".replace(",", " ") + " €"
    eco20, milieu = nombre(tuile("#p-hotes .sim-roi-big")), tuile("#p6-tuile-total i")
    assert nombre(total) == eco20 + nombre(re.search(r"\+ ([\d ]+) € de valeur verte", milieu).group(1))
    assert "à partir de " + eur(eco20 + nombre(bas)) in doc and total not in doc
    assert f"dont {eur(eco20)} d'économies d'énergie + à partir de {bas} de valeur verte" in doc
    for t in (rent, espaces(page.inner_text("#p6-tuile-eco")), "Valeur verte : estimation indicative",
              tuile("#p6-tuile-vv .p6-vv-ecarts")):
        assert t in doc, (t, doc)
    assert tuile("#p6-tuile-vv .p6-vv-ecarts") in ("Source : département 72", "Source : France entière")
    assert page.erreurs_js == []          # aucune erreur JS (dont « majMargeDossier is not defined ») en admin à l'étape 6
