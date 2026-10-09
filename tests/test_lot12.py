# -*- coding: utf-8 -*-
"""Lot 12 : le pré-devis / devis / PDF suivent le modèle, le prix et le financement affichés à l'écran au moment
du clic ; bouton « Régénérer » ; case « Projet en un coup d'œil » ; bouton « Enregistrer » explicite.
Vrai Chromium, fiche fabriquée PR-95001 (gaz, 4 pers., chauffage + eau chaude)."""
import copy
import json
import re
import socket
import threading
import time

import pytest

import main

sync_api = pytest.importorskip("playwright.sync_api")
uvicorn = pytest.importorskip("uvicorn")

LEAD = {"numero": "PR-95001", "civilite": "Madame", "nom": "Fictif", "prenom": "Faustine", "email": "fictif@example.invalid",
        "telephone": "0600000051", "adresse_chantier": "12 RUE IMAGINAIRE", "cp_chantier": "75002",
        "code_postal_chantier": "75002", "ville_chantier": "PARIS", "type_logement": "maison", "surface_logement_m2": "118",
        "hsp": "2,5", "annee_construction": "1968", "type_emetteurs": "radiateurs_classiques",
        "alimentation_electrique": "monophase", "nombre_personnes": "4", "rfr": "15000", "categorie": "tres_modeste",
        "statut": "a_rappeler", "mode_chauffage": "gaz", "ecs": "chaudiere", "cout_energetique_mensuel_eur": "220"}
NUM = LEAD["numero"]
NIMBUS = "ARI-NIMBUS-PLUS-R32-DUO-12"
NIMBUS_NOM = "NIMBUS PLUS R32 DUO 12"


def _port_libre():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _catalogue_avec_nimbus():
    cat = json.load(open(main.REPO_CATALOGUE_PATH, encoding="utf-8"))
    base = next(m for m in cat if m["ref"] == "ATL-EXCELLIA-S-DUO-12")
    nimbus = dict(copy.deepcopy(base), ref=NIMBUS, nom=NIMBUS_NOM, ttc=14798, achat=5200)
    nimbus["description_specs"] = [{"champ": "Marque", "valeur": "ARISTON"}]
    return cat + [nimbus]


@pytest.fixture(autouse=True)
def _donnees_restaurees():
    """Catalogue, fiches et paramètres partagés par la suite : remis en l'état après chaque test."""
    chemins = (main.CATALOGUE_PATH, main.PARAMETRES_ADMIN_PATH, main.LEADS_PATH)
    sauve = {c: open(c, "rb").read() for c in chemins if main.os.path.exists(c)}
    yield
    for c, octets in sauve.items():
        open(c, "wb").write(octets)


def _semer():
    main._atomic_write_json(main.CATALOGUE_PATH, _catalogue_avec_nimbus())
    main._atomic_write_json(main.LEADS_PATH, [dict(LEAD)])
    params = main.load_parametres_admin()
    params["marques"] = dict(copy.deepcopy(main.DEFAULT_MARQUES),
                             ARISTON={"prefixes": ["ARI"], "niveau": "essentiel", "positionnement": "", "avantages": ["", "", ""]})
    main._atomic_write_json(main.PARAMETRES_ADMIN_PATH, params)
    main._atomic_write_json(main._state_simulateur_path(NUM), {})
    main.save_state_simulateur_atomic(NUM, {"service": "chauffage_ecs"})
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
    main._atomic_write_json(main.LEADS_PATH, [])


@pytest.fixture
def page(serveur):
    _semer()
    with sync_api.sync_playwright() as p:
        b = p.chromium.launch()
        ctx = b.new_context(accept_downloads=True, viewport={"width": 1440, "height": 900})
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


def ouvrir_etape6(pg):
    pg.goto(f"{pg.base}/prospect/{NUM}")
    pg.wait_for_function("document.body.dataset.prospectNumero === %r && typeof window.hexaParcoursEtape === 'function'" % NUM)
    pg.wait_for_timeout(700)
    pg.evaluate("window.hexaParcoursEtape(6)")
    pg.wait_for_selector("#p-hotes .p6-pcard.sim-mod-row")
    pg.wait_for_timeout(300)


def cartes(pg):
    return pg.eval_on_selector_all("#p-hotes .p6-pcard.sim-mod-row",
                                   "els => els.map(e => ({id: e.dataset.modeleId, niv: e.dataset.pacNiv, on: e.classList.contains('on'), txt: e.innerText}))")


def choisir_nimbus_et_prix(pg, prix):
    pg.click(f'#p-hotes .p6-pcard.sim-mod-row[data-modele-id="{NIMBUS}"]')    # carte ESSENTIEL, comme sur PR-000854
    pg.wait_for_timeout(300)
    pg.click("#sim-prix")
    pg.fill("#sim-prix", str(prix))
    pg.locator("#sim-prix").blur()
    pg.wait_for_timeout(300)


def espaces(t):
    return re.sub(r"[  ]", " ", t)


def ecran(pg):
    """Chiffres affichés à l'étape 6 : modèle choisi, prix, mensualité du crédit, économies sur la durée de vie."""
    return {"modele": pg.eval_on_selector("#sim-modele-select", "s => s.options[s.selectedIndex].text.split(' · ')[0]"),
            "prix": espaces(pg.input_value("#sim-prix")),
            "credit": espaces(pg.eval_on_selector("#sim-mensualite", "e => e.parentElement.parentElement.innerText")),                  # « … 4,9 % · 180 mois … 51 €/mois »
            "pendant_credit": espaces(pg.inner_text("#p-hotes .p6-tuile i")),     # « 220 € → 156 €/mois » (crédit compris)
            "total20": espaces(pg.inner_text("#p-hotes .sim-roi-big"))}


def etat_serveur(pg):
    return pg.evaluate("n => fetch('/api/simulateur/' + n + '/state', {cache: 'no-store'}).then(r => r.json())", NUM)


def apercu(pg):
    frame = pg.frame_locator("#devis-preview-frame")
    frame.locator("body").wait_for()
    return espaces(frame.locator("body").inner_text())


def verifier_document(texte, vu):
    assert NIMBUS_NOM in texte and "ALFÉA" not in texte
    assert "17 321" in texte                                                 # prix TTC posé modifié
    assert vu["pendant_credit"] in texte                                     # facture + mensualité du crédit, comme à l'écran
    taux_duree = re.search(r"\d+,\d+ % · \d+ mois", vu["credit"]).group(0)
    assert taux_duree in texte                                               # même taux, même durée
    assert "Votre projet en un coup d'œil".upper() in texte.upper()
    assert vu["total20"].replace(" €", "") in texte                          # bloc coup d'œil : économies sur la durée de vie


# ---------------------------------------------------------------- bug 1 : le document suit l'écran
def test_voir_le_devis_garde_le_modele_et_le_prix_choisis(page):
    ouvrir_etape6(page)
    choisir_nimbus_et_prix(page, 17321)
    vu = ecran(page)
    assert vu["modele"] == NIMBUS_NOM and vu["prix"] == "17 321"
    page.click("#btn-voir-devis")
    page.wait_for_selector("#devis-preview-frame")
    page.wait_for_timeout(2500)                                   # au-delà de l'enregistrement différé (1,5 s)
    etat = etat_serveur(page)
    assert etat.get("modele_pac_id") == NIMBUS and int(etat.get("prix_pac")) == 17321, etat
    verifier_document(apercu(page), vu)
    page.click("#devis-close-btn")
    assert ecran(page) == vu                                      # l'écran n'a pas basculé sur le modèle recommandé


def test_modele_et_prix_conserves_apres_rechargement(page):
    ouvrir_etape6(page)
    choisir_nimbus_et_prix(page, 17321)
    page.click("#btn-voir-devis")
    page.wait_for_selector("#devis-preview-frame")
    page.wait_for_timeout(2500)
    ouvrir_etape6(page)
    vu = ecran(page)
    assert vu["modele"] == NIMBUS_NOM and vu["prix"] == "17 321"


def test_changer_la_surface_recalcule_le_modele(page):
    """Comportement voulu conservé : une donnée de la fiche qui change la puissance relance le choix du modèle."""
    ouvrir_etape6(page)
    choisir_nimbus_et_prix(page, 17321)
    page.evaluate("window.hexaParcoursEtape(2)")
    page.wait_for_timeout(300)
    page.fill("#surface-input", "150")
    page.wait_for_timeout(600)
    page.evaluate("window.hexaParcoursEtape(6)")
    page.wait_for_timeout(600)
    vu = ecran(page)
    assert vu["modele"] != NIMBUS_NOM and vu["prix"] != "17 321", vu
