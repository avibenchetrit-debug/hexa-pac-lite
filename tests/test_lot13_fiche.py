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


LIRE_FICHE = """() => [...document.querySelectorAll('#p-hotes .p6-tuiles3 > .p6-tuile3')].map(t => ({
  titre: t.querySelector('.t3-titre').textContent, pre: t.querySelector('.t3-pre').textContent.replace(/^\\u00a0$/, ''),
  montant: t.querySelector('.t3-montant').textContent,
  details: [...t.querySelectorAll('.t3-details > i')].map(i => i.textContent)}))"""
LIRE_DOC = """() => { const c = (k) => [...document.querySelectorAll('.projet-apercu-tuiles td.pa-t3-' + k)];
  return c('titre').map((td, i) => ({ titre: td.textContent.trim(), pre: c('pre')[i].textContent.trim().replace(/^\\u00a0$/, ''),
    montant: c('montant')[i].textContent.trim(), details: [...c('details')[i].children].map(d => d.textContent) })); }"""


def test_tuiles_fiche_identiques_au_predevis(page):
    page.evaluate("window.hexaParcoursEtape(6)")
    page.wait_for_selector("#p6-tuile-vv")
    fiche = page.evaluate(LIRE_FICHE)
    assert [t["titre"] for t in fiche] == ["Économies d'énergie", "Valeur verte", "Gain total sur 20 ans"]
    vv_t, total_t = fiche[1], fiche[2]
    assert vv_t["pre"] == "à partir de" and re.fullmatch(r"\d{1,3}(\u00a0\d{3})*\u00a0€", vv_t["montant"]), vv_t
    assert total_t["pre"] == "à partir de" and total_t["details"][0].startswith("dont ")
    assert " à " not in vv_t["montant"] and "(classe estimée)" in vv_t["details"]
    page.click("#btn-voir-devis")
    page.wait_for_selector("#devis-preview-frame")
    frame = page.frame("devis-preview-frame") or next(f for f in page.frames if f != page.main_frame)
    frame.wait_for_selector(".projet-apercu-tuiles")
    doc = frame.evaluate(LIRE_DOC)
    assert doc == fiche                                                  # strictement identiques (titres, montants, détails)
    texte_doc = frame.inner_text(".projet-apercu")
    assert "Valeur verte : estimation indicative" in texte_doc
    # mise en forme : montants sur une ligne, montants alignés, tuiles de même hauteur (fiche et document)
    for cible in (page, frame):
        mesures = cible.evaluate("""() => { const sel = document.querySelector('.p6-tuiles3')
              ? ['#p-hotes .p6-tuile3', '#p-hotes .p6-tuile3 .t3-montant'] : ['.projet-apercu-tuiles td.pa-t3-montant', '.projet-apercu-tuiles td.pa-t3-montant > div'];
          const b = (s) => [...document.querySelectorAll(s)].map(e => e.getBoundingClientRect());
          const m = b(sel[1]);
          return { tops: m.map(r => Math.round(r.top)), hauteurs: m.map(r => Math.round(r.height)),
                   tuiles: document.querySelector('.p6-tuiles3') ? b(sel[0]).map(r => Math.round(r.height)) : [] }; }""")
        assert len(set(mesures["tops"])) == 1, mesures                   # montants sur la même ligne horizontale
        assert max(mesures["hauteurs"]) <= 30, mesures                   # une seule ligne
        assert len(set(mesures["tuiles"])) <= 1, mesures                 # même hauteur (fiche)
    assert page.erreurs_js == []          # aucune erreur JS (dont « majMargeDossier is not defined ») en admin à l'étape 6
