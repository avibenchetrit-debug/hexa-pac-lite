# -*- coding: utf-8 -*-
"""Lot 12 : le pré-devis / devis / PDF suivent le modèle, le prix et le financement affichés à l'écran au moment
du clic ; bouton « Régénérer » ; case « Projet en un coup d'œil » ; bouton « Enregistrer » explicite.
Vrai Chromium, fiche fabriquée PR-95001 (gaz, 4 pers., chauffage + eau chaude)."""
import copy
import io
import json
import re
import socket
import sys
import threading
import time
import types

import pytest

import main

pypdf = pytest.importorskip("pypdf")
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
    chemins = (main.CATALOGUE_PATH, main.PARAMETRES_ADMIN_PATH, main.LEADS_PATH, main.COUNTERS_PATH,
               main.DEVIS_ENVOYES_PATH, main.DEVIS_META_PATH, main.ECHANGES_PATH)
    sauve = {c: open(c, "rb").read() for c in chemins if main.os.path.exists(c)}
    absents = [c for c in chemins if not main.os.path.exists(c)]
    yield
    for c, octets in sauve.items():
        open(c, "wb").write(octets)
    for c in absents:
        if main.os.path.exists(c):
            main.os.remove(c)


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


# ---------------------------------------------------------------- 2 : « Régénérer »
def texte_pdf(pg):
    with pg.expect_download(timeout=90000) as dl:
        pg.click("#devis-pdf-btn")
    pdf = open(dl.value.path(), "rb").read()
    return espaces(" ".join((p.extract_text() or "") for p in pypdf.PdfReader(io.BytesIO(pdf)).pages))


def test_regenerer_reconstruit_depuis_l_ecran_et_le_pdf_suit(page):
    ouvrir_etape6(page)
    choisir_nimbus_et_prix(page, 17321)
    vu = ecran(page)
    page.click("#btn-voir-devis")
    page.wait_for_selector("#devis-preview-frame")
    page.wait_for_timeout(2500)
    # état serveur devenu périmé (ex. autre onglet resté sur l'ancien modèle) : l'aperçu rechargé le montrerait
    page.evaluate("""n => fetch('/api/simulateur/' + n + '/state', {method: 'POST', headers: {'Content-Type': 'application/json'},
                         body: JSON.stringify({modele_pac_id: 'ATL-EXCELLIA-S-DUO-12', modele_pac_nom: 'ALFÉA EXCELLIA S DUO 12', prix_pac: 15490})})""", NUM)
    avant = page.get_attribute("#devis-preview-frame", "src")
    page.click("#devis-regen-btn")
    page.wait_for_function("document.querySelector('#devis-regen-btn').textContent === 'Régénéré ✓'")
    assert page.get_attribute("#devis-preview-frame", "src") != avant
    assert page.is_hidden("#devis-pdf-erreur")
    etat = etat_serveur(page)
    assert etat.get("modele_pac_id") == NIMBUS and int(etat.get("prix_pac")) == 17321, etat
    verifier_document(apercu(page), vu)
    pdf = texte_pdf(page)
    assert NIMBUS_NOM in pdf and "ALFÉA" not in pdf and "17 321" in pdf, pdf[:500]
    assert vu["pendant_credit"].replace(" ", "") in pdf.replace(" ", "")        # mensualité du crédit comprise
    assert vu["total20"].replace(" ", "") in pdf.replace(" ", "")               # bloc coup d'œil


def test_regenerer_absent_sur_dossier_facture(page):
    ouvrir_etape6(page)
    page.evaluate("window.__hexaDossierFige = true")
    page.click("#btn-voir-devis")
    page.wait_for_selector("#devis-preview-frame")
    assert page.query_selector("#devis-regen-btn") is None and page.is_visible("#devis-pdf-btn")


# ---------------------------------------------------------------- 3 : case « Projet en un coup d'œil »
COUP_D_OEIL = "VOTRE PROJET EN UN COUP D'ŒIL"


def test_case_projet_en_un_coup_d_oeil_masque_le_bloc_partout(page):
    ouvrir_etape6(page)
    case = page.locator("#sim-afficher-apercu")
    assert page.inner_text("label:has(#sim-afficher-apercu)").strip() == "Projet en un coup d'œil"
    assert "Économies sur le devis" not in page.inner_text("#p-hotes")
    assert case.is_checked()
    page.click("label:has(#sim-afficher-apercu)")
    assert not case.is_checked()
    page.click("#btn-voir-devis")
    page.wait_for_selector("#devis-preview-frame")
    page.wait_for_timeout(1500)
    assert COUP_D_OEIL not in apercu(page).upper()
    assert COUP_D_OEIL not in texte_pdf(page).upper()
    ouvrir_etape6(page)                                            # réglage enregistré pour ce prospect
    assert etat_serveur(page).get("afficher_apercu") is False and not page.locator("#sim-afficher-apercu").is_checked()
    page.click("label:has(#sim-afficher-apercu)")
    page.click("#btn-voir-devis")
    page.wait_for_selector("#devis-preview-frame")
    page.wait_for_timeout(1500)
    assert COUP_D_OEIL in apercu(page).upper()


# ---------------------------------------------------------------- 4 : « Enregistrer » dans le bandeau
def toast(pg, texte):
    pg.wait_for_function("t => Array.from(document.querySelectorAll('.pv-toast')).some(x => x.textContent.includes(t))", arg=texte)


def test_enregistrer_visible_aux_6_etapes_et_navigation_intacte(page):
    ouvrir_etape6(page)
    page.evaluate("window.hexaParcoursEtape(1)")
    page.wait_for_timeout(300)
    for n in range(1, 7):
        assert page.is_visible("#prospect-sticky-bar #btn-save"), n
        assert page.inner_text("#btn-save").strip() == "Enregistrer"
        assert page.query_selector("#p-carte .p-nav #btn-save") is None
        assert page.evaluate("document.body.dataset.p6Etape") == str(n)
        if n < 6:
            page.click("#p-suiv")                                   # « Suivant » : sans rapport avec l'enregistrement
            page.wait_for_timeout(250)
    assert page.is_hidden("#form-actions-bar")


def test_enregistrer_nimbus_et_prix_puis_recharger(page):
    ouvrir_etape6(page)
    choisir_nimbus_et_prix(page, 17321)
    page.click("#btn-save")
    toast(page, "Enregistré ✓ — fiche et proposition")
    etat = etat_serveur(page)                                       # tout de suite, sans attendre l'envoi différé
    assert etat.get("modele_pac_id") == NIMBUS and int(etat.get("prix_pac")) == 17321, etat
    ouvrir_etape6(page)
    vu = ecran(page)
    assert vu["modele"] == NIMBUS_NOM and vu["prix"] == "17 321"


def test_enregistrer_un_champ_de_la_fiche_puis_recharger(page):
    ouvrir_etape6(page)
    page.evaluate("window.hexaParcoursEtape(1)")
    page.fill('[name="prenom"]', "Faustina")
    assert page.eval_on_selector("#btn-save", "b => b.classList.contains('is-modifie')")      # pastille « non enregistré »
    page.click("#btn-save")
    toast(page, "Enregistré ✓")
    assert not page.eval_on_selector("#btn-save", "b => b.classList.contains('is-modifie')")
    ouvrir_etape6(page)
    assert page.input_value('[name="prenom"]') == "Faustina"
    assert main._find_lead(NUM)["prenom"] == "Faustina"


def test_enregistrer_dit_quand_la_proposition_n_est_pas_enregistree(page):
    ouvrir_etape6(page)
    choisir_nimbus_et_prix(page, 17321)
    page.route("**/api/simulateur/*/state", lambda r: r.fulfill(status=500, body="{}") if r.request.method == "POST" else r.continue_())
    page.click("#btn-save")
    toast(page, "la proposition (étape 6) n'a pas pu l'être")
    assert page.inner_text("#btn-save").strip() == "Enregistrer" and page.is_enabled("#btn-save")



# ---------------------------------------------------------------- 5 : « Envoyer » part avec l'état affiché
@pytest.fixture
def envoi_simule(monkeypatch):
    """Envoi e-mail simulé (comme scripts/e2e_appel_local.py) : aucun service extérieur."""
    envois = []
    faux = types.ModuleType("resend")
    faux.Emails = types.SimpleNamespace(send=lambda msg: envois.append(msg) or {"id": f"factice-{len(envois)}"})
    monkeypatch.setitem(sys.modules, "resend", faux)
    monkeypatch.setenv("RESEND_API_KEY", "cle-factice-locale")
    return envois


def test_envoyer_enregistre_l_ecran_avant_de_figer_la_version(page, envoi_simule):
    ouvrir_etape6(page)
    choisir_nimbus_et_prix(page, 17321)
    page.click("#btn-voir-devis")
    page.wait_for_selector("#devis-preview-frame")
    page.wait_for_timeout(2500)
    # état serveur devenu périmé pendant que la fenêtre est ouverte (ex. traitement en arrière-plan, autre onglet)
    page.evaluate("""n => fetch('/api/simulateur/' + n + '/state', {method: 'POST', headers: {'Content-Type': 'application/json'},
                         body: JSON.stringify({modele_pac_id: 'ATL-EXCELLIA-S-DUO-12', modele_pac_nom: 'ALFÉA EXCELLIA S DUO 12', prix_pac: 15490})})""", NUM)
    page.click("#devis-send-btn")
    messages = []
    page.on("dialog", lambda d: (messages.append(d.message), d.accept()))
    page.click("#btn-send-predevis")
    page.wait_for_function("!document.getElementById('modal-envoi-mail')", timeout=120000)
    assert messages == ["Pré-devis envoyé au client."], messages
    assert len(envoi_simule) >= 1
    fige = main._read_devis_meta()[NUM][-1]                       # la version figée (v1) envoyée au client
    html_fige = espaces(open(fige["html_file"], encoding="utf-8").read())
    assert NIMBUS_NOM in html_fige and "ALFÉA" not in html_fige and "17 321" in html_fige
    assert etat_serveur(page).get("modele_pac_id") == NIMBUS


def test_envoyer_n_envoie_rien_si_la_proposition_n_est_pas_enregistree(page, envoi_simule):
    ouvrir_etape6(page)
    page.click("#btn-voir-devis")
    page.wait_for_selector("#devis-preview-frame")
    page.wait_for_timeout(2000)
    page.route("**/api/simulateur/*/state", lambda r: r.fulfill(status=500, body="{}") if r.request.method == "POST" else r.continue_())
    page.click("#devis-send-btn")
    messages = []
    page.on("dialog", lambda d: (messages.append(d.message), d.accept()))
    page.click("#btn-send-predevis")
    page.wait_for_function("document.getElementById('btn-send-predevis').textContent.includes('Envoyer')")
    page.wait_for_timeout(300)
    assert messages and "rien n'a été envoyé" in messages[0], messages
    assert envoi_simule == [] and not main._read_devis_meta().get(NUM)
