# -*- coding: utf-8 -*-
"""Lot A (notedim-master) : la QUANTITÉ prise en compte partout, avec la plage de cohérence du Master (60–130 % de la
puissance requise, puissance installée = quantité × puissance unitaire).

1. Choix automatique des 3 gammes : si aucune PAC unique ne convient, cascades « 2 × modèle » dans la plage, au prix de
   2 PAC (pose cascade de l'Admin). Si une PAC unique convient, RIEN NE CHANGE (grille témoin enregistrée avant le lot).
2. Alerte de l'étape 6 seulement si ni 1 ni 2 PAC n'entrent dans la plage ; « 2 × 18 kW = 36 kW installés · 108 % ·
   cohérent ».
3. Pré-note : « 2 × modèle (en cascade) », puissance totale, prix réellement saisi. Note définitive : quantité, puissance
   totale, % et statut.

Cas de référence GESLOT (PR-000164), données fabriquées : besoin 33,4 kW (245 m² chauffés, 2,70 m, toit et murs peu
isolés, 49800) -> cascade 2 × ALTHERMA 3H HT R32 18 = 36 kW, cohérent. Catalogue : les 38 modèles de la prod (prix et
puissances seulement, sans prix d'achat), marques et prix de vente de l'Admin de prod. Aucun service extérieur."""
import json
import os
import re
import socket
import threading
import time

import pytest

import main
from services import service_devis

sync_api = pytest.importorskip("playwright.sync_api")
uvicorn = pytest.importorskip("uvicorn")

FIX = os.path.join(os.path.dirname(__file__), "fixtures")
CATALOGUE = json.load(open(os.path.join(FIX, "catalogue_pac_38.json"), encoding="utf-8"))
ADMIN = json.load(open(os.path.join(FIX, "admin_marques_prix.json"), encoding="utf-8"))
GRILLE_TEMOIN = os.path.join(FIX, "notedim_a_grille_1pac.json")

NUM = "PR-16401"
LEAD = {"numero": NUM, "civilite": "Monsieur", "nom": "Cascadegeslot", "prenom": "Test", "email": "g@example.invalid",
        "telephone": "0600001641", "adresse_chantier": "1 RUE IMAGINAIRE", "cp_chantier": "49800",
        "code_postal_chantier": "49800", "ville_chantier": "TRELAZE", "type_logement": "maison",
        "surface_logement_m2": "280", "hsp": "2,7", "altitude": "28", "annee_construction": "1968",
        "type_emetteurs": "radiateurs_fonte", "alimentation_electrique": "monophase", "nombre_personnes": "4",
        "rfr": "60000", "categorie": "superieur", "statut": "a_rappeler", "mode_chauffage": "fioul", "ecs": "chaudiere",
        "cout_energetique_mensuel_eur": "268", "cout_energie_source": "reel"}
ETAT_GESLOT = {"service": "chauffage_seul", "option": "opt3", "iso_toit": "peu", "iso_mur": "peu",
               "iso_menuiserie": "double", "surface_chauffee": 245, "surface_forcee": True}
ALTHERMA_18 = "DAI-ALTHERMA-3HHT-R32-18"


def _port_libre():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(autouse=True)
def _donnees_restaurees():
    chemins = (main.CATALOGUE_PATH, main.PARAMETRES_ADMIN_PATH, main.LEADS_PATH, main.COUNTERS_PATH,
               main.DEVIS_ENVOYES_PATH, main._state_simulateur_path(NUM))
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


def _preparer(etat):
    main._atomic_write_json(main.CATALOGUE_PATH, CATALOGUE)
    main.save_parametres_admin_atomic(json.loads(json.dumps(ADMIN)))
    main._atomic_write_json(main.LEADS_PATH, [dict(LEAD)])
    main._atomic_write_json(main._state_simulateur_path(NUM), {})
    main.save_state_simulateur_atomic(NUM, dict(etat))
    main._write_users([{"id": "testeur", "username": "testeur", "password_hash": main._hash_password("essai-local"),
                        "role": "admin", "actif": True, "cree_at": main._now_iso(), "visibilite": "tous"}])


@pytest.fixture
def navigateur(serveur):
    with sync_api.sync_playwright() as p:
        b = p.chromium.launch()
        ctx = b.new_context(viewport={"width": 1440, "height": 900})
        ctx.route("**/*", lambda r: r.continue_() if r.request.url.startswith(serveur) else r.abort())
        pg = ctx.new_page()
        pg.erreurs_js = []
        pg.on("pageerror", lambda e: pg.erreurs_js.append(str(e)))
        pg.base = serveur
        yield pg
        b.close()


def _ouvrir_etape6(pg, etat):
    _preparer(etat)
    if "/login" not in pg.url and not getattr(pg, "connecte", False):
        pg.goto(pg.base + "/login")
        pg.fill("#username", "testeur")
        pg.fill("#password", "essai-local")
        pg.click("#login-btn")
        pg.wait_for_url(lambda u: "/login" not in u)
        pg.connecte = True
    pg.goto(f"{pg.base}/prospect/{NUM}")
    pg.wait_for_function("document.body.dataset.prospectNumero === %r && typeof window.hexaParcoursEtape === 'function'"
                         % NUM)
    pg.wait_for_timeout(700)
    pg.evaluate("window.hexaParcoursEtape(6)")
    pg.wait_for_selector("#sim-quantite")


# ---------- Admin → Catalogue PAC → 15. Dimensionnement ----------

def test_admin_saisie_et_validation_m7_55(navigateur):
    pg = navigateur
    _preparer(ETAT_GESLOT)
    main._atomic_write_json(main.CATALOGUE_PATH, main.json.loads(main.json.dumps(CATALOGUE)))
    main._migrate_catalogue_dimensionnement()
    pg.goto(pg.base + "/login")
    pg.fill("#username", "testeur")
    pg.fill("#password", "essai-local")
    pg.click("#login-btn")
    pg.wait_for_url(lambda u: "/login" not in u)
    pg.goto(pg.base + "/")
    pg.wait_for_selector("#pv-admin", state="attached")
    pg.evaluate("document.getElementById('pv-admin').click()")
    pg.wait_for_selector("#admin-auth-password, #adm-roottabs", timeout=10000)
    if pg.query_selector("#admin-auth-password"):
        pg.fill("#admin-auth-password", main.os.environ.get("ADMIN_PASSWORD", "hexarenov2026"))
        pg.click('[data-act="unlock"]')
    pg.wait_for_selector("#adm-roottabs", timeout=15000)
    pg.click('.adm-roottab[data-roottab="catalogue"]')
    pg.click('[data-toggle-bloc="15"]')
    ligne = f'.adm-dim-table tr[data-ref="{ALTHERMA_18} TRI"]'
    pg.wait_for_selector(ligne)
    assert pg.input_value(ligne + " .adm-dim-kw") == "9,21"            # valeur du Master, non validée
    assert not pg.is_checked(ligne + " .adm-dim-ok")
    assert pg.input_value('.adm-dim-temp[data-emetteur="radiateurs_fonte"]') == "65"
    pg.fill(ligne + " .adm-dim-kw", "17,4")
    pg.check(ligne + " .adm-dim-ok")
    pg.click("#adm-dim-pac-save")
    pg.wait_for_function("document.querySelector('%s .adm-dim-ok') && document.querySelector('%s').style.background === ''"
                         % (ligne, ligne))
    m = next(x for x in main._read_catalogue_pac() if x["ref"] == ALTHERMA_18 + " TRI")
    assert (m["puissance_m7_55_kw"], m["puissance_m7_55_valide"]) == (17.4, True)
    assert pg.erreurs_js == []


# ---------- étape Chauffage : température de départ ----------

def test_temperature_depart_preremplie_et_modifiable(navigateur):
    pg = navigateur
    _ouvrir_etape6(pg, ETAT_GESLOT)
    pg.evaluate("window.hexaParcoursEtape(3)")
    pg.wait_for_selector('[name="temperature_depart_c"]', state="visible")
    assert pg.get_attribute('[name="temperature_depart_c"]', "placeholder") == "65"       # radiateurs fonte
    assert pg.evaluate("window.hexaTemperatureRequise()") == {"t": 65, "origine": "emetteur", "emetteur": "radiateurs_fonte"}
    sel = '#form-prospect [name="type_emetteurs"]'
    pg.evaluate(f"(() => {{ const s = document.querySelector('{sel}'); s.value = 'plancher_chauffant';"
                " s.dispatchEvent(new Event('change', { bubbles: true })); })()")
    assert pg.input_value('[name="temperature_depart_c"]') == "35"                       # pré-rempli
    pg.fill('[name="temperature_depart_c"]', "45")                                       # modifié à la main
    pg.evaluate(f"(() => {{ const s = document.querySelector('{sel}'); s.value = 'radiateurs_fonte';"
                " s.dispatchEvent(new Event('change', { bubbles: true })); })()")
    assert pg.input_value('[name="temperature_depart_c"]') == "45"                       # saisie gardée
    pg.click("#btn-save")
    fin = time.time() + 10
    while time.time() < fin and main._find_lead(NUM).get("temperature_depart_c") != "45":
        pg.wait_for_timeout(200)
    assert main._find_lead(NUM).get("temperature_depart_c") == "45"
    assert pg.erreurs_js == []
