# -*- coding: utf-8 -*-
"""Lot 14 (vrai Chromium) : à l'étape 6, la quantité de PAC (1 / 2 en cascade) à côté du modèle choisi ; prix par
défaut de 2 PAC identique au serveur ; puissance totale comparée au besoin ; la quantité survit à l'enregistrement,
au rechargement de la fiche, à « Voir le devis » et à « Régénérer ». Fiche fabriquée PR-14101, aucun service extérieur."""
import json
import re
import socket
import threading
import time

import pytest

import main

sync_api = pytest.importorskip("playwright.sync_api")
uvicorn = pytest.importorskip("uvicorn")

PHRASE = "Installation de 2 pompes à chaleur montées en cascade"
LEAD = {"numero": "PR-14101", "civilite": "Monsieur", "nom": "Cascade", "prenom": "Romaric", "email": "c@example.invalid",
        "telephone": "0600001401", "adresse_chantier": "1 RUE IMAGINAIRE", "cp_chantier": "49800",
        "code_postal_chantier": "49800", "ville_chantier": "TRELAZE", "type_logement": "maison", "surface_logement_m2": "200",
        "hsp": "2,5", "annee_construction": "1968", "type_emetteurs": "radiateurs_classiques",
        "alimentation_electrique": "monophase", "nombre_personnes": "4", "rfr": "60000", "categorie": "superieur",
        "statut": "a_rappeler", "mode_chauffage": "fioul", "ecs": "chaudiere", "cout_energetique_mensuel_eur": "268",
        "cout_energie_source": "reel"}
# Lot A (notedim-master, 04/11/2026) : 200 m² (et non plus 280) — à 280 m² le besoin (24,3 kW) dépasse ce qu'une PAC du
# catalogue de test couvre dans la plage 60–130 %, et le choix automatique propose désormais une cascade. Ce fichier
# teste la quantité changée À LA MAIN en partant d'une PAC unique.
NUM = LEAD["numero"]
PRIX_VENTE = {"prix_pose_ht": 3920, "prix_travaux_induits_ht": 2100, "prix_pose_cascade_ht": 6500,
              "travaux_induits_cascade": 1}


def _port_libre():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(autouse=True)
def _donnees_restaurees():
    chemins = (main.CATALOGUE_PATH, main.PARAMETRES_ADMIN_PATH, main.LEADS_PATH, main.COUNTERS_PATH, main.DEVIS_ENVOYES_PATH,
               main._state_simulateur_path(NUM))
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
    # aucun service extérieur : ADEME / BAN et DVF simulés (sinon le serveur attend le réseau à l'ouverture de la fiche)
    from services import dpe_audit, valeur_dvf
    mp = pytest.MonkeyPatch()
    mp.setattr(dpe_audit, "GET", lambda url, timeout: {"features": []} if "api-adresse" in url else {"results": []})
    mp.setattr(valeur_dvf, "prix_m2", lambda *a, **k: {"ok": False, "indisponible": True, "raison": "simulé"})
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
    mp.undo()
    main._atomic_write_json(main.LEADS_PATH, [])


@pytest.fixture
def page(serveur):
    main._atomic_write_json(main.CATALOGUE_PATH, json.load(open(main.REPO_CATALOGUE_PATH, encoding="utf-8")))
    main.save_parametres_admin_atomic({"prix_vente_devis": dict(PRIX_VENTE)})
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
        pg.base = serveur
        _ouvrir_etape6(pg)
        yield pg
        b.close()


def _ouvrir_etape6(pg):
    pg.goto(f"{pg.base}/prospect/{NUM}")
    pg.wait_for_function("document.body.dataset.prospectNumero === %r && typeof window.hexaParcoursEtape === 'function'" % NUM)
    pg.wait_for_timeout(700)
    pg.evaluate("window.hexaParcoursEtape(6)")
    pg.wait_for_selector("#sim-quantite")


def _prix(pg):
    return int(re.sub(r"\D", "", pg.input_value("#sim-prix")) or 0)


def _etat():
    return main.load_state_simulateur(NUM)


def _attendre_etat(pg, cle, valeur, delai=10):
    # page.wait_for_timeout (jamais time.sleep) : les requêtes de la page passent par ctx.route, traité seulement
    # pendant un appel Playwright
    fin = time.time() + delai
    while time.time() < fin:
        if _etat().get(cle) == valeur:
            return
        pg.wait_for_timeout(200)
    raise AssertionError(f"{cle} = {_etat().get(cle)!r}, attendu {valeur!r}")


def test_quantite_1_par_defaut_et_prix_du_catalogue(page):
    assert page.input_value("#sim-quantite") == "1"
    # prix du modèle présélectionné = son prix catalogue, inchangé (quantité 1)
    assert _prix(page) in {round(float(m["ttc"])) for m in main._read_catalogue_pac() if m.get("ttc")}
    assert page.locator("#sim-puissance-totale").count() == 0 and page.erreurs_js == []


def test_quantite_2_prix_puissance_et_survie(page):
    prix_1 = _prix(page)
    page.select_option("#sim-quantite", "2")
    page.wait_for_function("document.querySelector('#sim-quantite').value === '2'")
    attendu = int(main.prix_defaut_pac(prix_1, 2, main._admin_payload_with_m3()))
    page.wait_for_function(f"document.querySelector('#sim-prix').value.replace(/\\D/g, '') === '{attendu}'")
    # puissance : 2 × puissance unitaire affichée et comparée au besoin
    texte = page.inner_text("#sim-puissance-totale")
    assert re.fullmatch(r"2 × [\d,]+ kW = [\d,]+ kW installés", texte.replace(" ", " ")), texte
    # enregistrée avec la proposition (bouton « Enregistrer » de la fiche), puis rechargée
    page.click("#btn-save")
    _attendre_etat(page, "quantite_pac", 2)
    assert _etat().get("prix_pac") == attendu
    _ouvrir_etape6(page)
    assert page.input_value("#sim-quantite") == "2" and _prix(page) == attendu
    # « Voir le devis » (enregistre fiche + proposition) puis « Régénérer » : le document a la phrase cascade
    page.click("#btn-voir-devis")
    page.wait_for_selector("#devis-preview-frame")
    frame = page.frame("devis-preview-frame") or next(f for f in page.frames if f != page.main_frame)
    frame.wait_for_selector(".lot-title")
    assert frame.inner_text(".lot-title").endswith("· 2 unités en cascade") and PHRASE in frame.inner_text("body")
    page.click("#devis-regen-btn")
    page.wait_for_timeout(1500)
    frame = page.frame("devis-preview-frame") or next(f for f in page.frames if f != page.main_frame)
    frame.wait_for_selector(".lot-title")
    assert PHRASE in frame.inner_text("body") and _etat().get("quantite_pac") == 2
    assert page.erreurs_js == []


def test_retour_a_1_prix_du_catalogue(page):
    prix_1 = _prix(page)
    page.select_option("#sim-quantite", "2")
    page.wait_for_function(f"document.querySelector('#sim-prix').value.replace(/\\D/g, '') !== '{prix_1}'")
    page.select_option("#sim-quantite", "1")
    page.wait_for_function(f"document.querySelector('#sim-prix').value.replace(/\\D/g, '') === '{prix_1}'")
    page.click("#btn-save")
    _attendre_etat(page, "quantite_pac", 1)
    assert page.locator("#sim-puissance-totale").count() == 0


# ---------- alertes rouges à côté du prix (admin, sans blocage) ----------

def _saisir_prix(pg, prix):
    pg.click("#sim-prix")
    pg.fill("#sim-prix", str(prix))
    pg.wait_for_timeout(900)                           # recalcul de la marge (250 ms) + réponse du serveur


def _alertes(pg):
    return pg.evaluate("[...document.querySelectorAll('#sim-alertes-prix .sim-alerte-rouge')].map(a => a.id + '|' + a.textContent)")


def test_alertes_prix_1_pac(page):
    _saisir_prix(page, _prix(page))                    # prix du catalogue : aucune alerte
    assert _alertes(page) == []
    _saisir_prix(page, 5000)                           # bien trop bas : marge négative ET fourniture sous l'achat
    alertes = _alertes(page)
    assert [a.split("|")[0] for a in alertes] == ["sim-alerte-marge", "sim-alerte-achat"], alertes
    assert alertes[0].split("|")[1].startswith("Marge négative : −")
    assert "Fourniture sous le prix d'achat : " in alertes[1] and " HT par PAC (achat " in alertes[1]
    assert page.is_enabled("#btn-voir-devis")          # alerte seulement : rien n'est bloqué
    page.locator("#sim-prix").blur()                   # réaffichage complet : les alertes restent
    page.wait_for_timeout(900)
    assert len(_alertes(page)) == 2


def test_alertes_prix_2_pac(page):
    page.select_option("#sim-quantite", "2")
    page.wait_for_timeout(900)
    assert _alertes(page) == []                        # prix par défaut de 2 PAC
    _saisir_prix(page, 12000)                          # 2 PAC à 12 000 € : les deux alertes (cas « achat seul » : test serveur)
    alertes = _alertes(page)
    assert [a.split("|")[0] for a in alertes] == ["sim-alerte-marge", "sim-alerte-achat"], alertes
