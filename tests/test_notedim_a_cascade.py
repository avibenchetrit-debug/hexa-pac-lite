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
        "type_emetteurs": "radiateurs_fonte", "alimentation_electrique": "triphase", "nombre_personnes": "4",
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


# ---------- GESLOT : cascade proposée, cohérente ----------

def _cartes(pg):
    return pg.evaluate("""[...document.querySelectorAll('.p6-pcard.sim-mod-row')].map(b => ({ niv: b.dataset.pacNiv,
        id: b.dataset.modeleId, q: b.dataset.qte, texte: b.innerText.replace(/\s+/g, ' ') }))""")


def test_geslot_cascade_proposee_et_coherente(navigateur):
    pg = navigateur
    _ouvrir_etape6(pg, ETAT_GESLOT)
    assert pg.inner_text("#sim-puissance-reco") == "33,4 kW"
    assert pg.locator(".p6-alerte-dim").count() == 0                      # plus d'alerte « Aucune PAC »
    cartes = {c["niv"]: c for c in _cartes(pg)}
    assert set(cartes) == {"essentiel", "recommande", "confort"} and all(c["q"] == "2" for c in cartes.values())
    # Confort = DAIKIN (marque réglée Confort dans l'Admin) : 2 × ALTHERMA 18 TRI = 36 kW, 108 %
    assert cartes["confort"]["id"] == ALTHERMA_18 + " TRI"
    assert "2 × ALTHERMA 3H HT R32 18 TRI" in cartes["confort"]["texte"] and "2 × 18 = 36 kW · 108 %" in cartes["confort"]["texte"]
    # aucune NIMBUS (60 °C max < 65 °C requis pour des radiateurs fonte)
    assert not any("NIMBUS" in c["texte"] for c in cartes.values())
    # Essentiel = la moins chère des options valables ; les 3 sont différentes
    opts = pg.evaluate("window.optionsValables(33.4).options.map(o => ({ id: o.id, prix: o.prix, q: o.quantite }))")
    assert all(o["q"] == 2 for o in opts) and cartes["essentiel"]["id"] == min(opts, key=lambda o: o["prix"])["id"]
    assert len({c["id"] for c in cartes.values()}) == 3
    # choisir la Confort : quantité 2, prix de 2 PAC, en-tête « 2 × 18 kW = 36 kW installés · 108 % · cohérent »
    pg.click('.p6-pcard[data-pac-niv="confort"]')
    pg.wait_for_function("document.querySelector('#sim-quantite').value === '2'")
    attendu = int(main.prix_defaut_pac(17882.0, 2, main._admin_payload_with_m3()))
    pg.wait_for_function(f"document.querySelector('#sim-prix').value.replace(/\D/g, '') === '{attendu}'")
    entete = (pg.inner_text("#sim-puissance-totale") + " · " + pg.inner_text("#sim-puissance-coherence")).replace(" ", " ")
    assert entete == "2 × 18 kW = 36 kW installés · 108 % · cohérent", entete
    assert pg.locator("#sim-selection-alerte").count() == 0 and pg.locator("#sim-puissance-alerte").count() == 0
    assert pg.inner_text("#sim-puissance-origine") == "Puissance à 35 °C, valeur à −7 °C / 55 °C non renseignée."
    assert pg.erreurs_js == []


def test_geslot_nimbus_choisie_a_la_main_alerte_temperature(navigateur):
    pg = navigateur
    _ouvrir_etape6(pg, dict(ETAT_GESLOT, modele_pac_id="ARI-NIMBUS-NET-R32-15 TRI", quantite_pac=2))
    pg.wait_for_selector("#sim-alerte-temperature")
    assert pg.inner_text("#sim-alerte-temperature") ==         "⚠ Température max 60 °C : insuffisante pour des radiateurs fonte (65 °C requis)"
    assert pg.locator(".p6-alerte-dim").count() == 0                      # des options valables existent
    assert pg.inner_text("#sim-puissance-coherence") == "90 % · cohérent"
    assert pg.erreurs_js == []


def test_une_pac_suffit_pas_de_cascade(navigateur):
    pg = navigateur
    _ouvrir_etape6(pg, dict(ETAT_GESLOT, iso_toit="tres_bien", iso_mur="bien", surface_chauffee=120))
    kw = float(pg.inner_text("#sim-puissance-reco").replace(" kW", "").replace(",", "."))
    assert kw < 12
    cartes = _cartes(pg)
    assert cartes and all(c["q"] == "1" for c in cartes)                  # une PAC unique convient : pas de cascade
    assert pg.input_value("#sim-quantite") == "1"
    assert pg.locator("#sim-puissance-totale").count() == 0
    assert pg.erreurs_js == []


def test_geslot_comparer_toutes_les_options_et_choisir(navigateur):
    pg = navigateur
    _ouvrir_etape6(pg, ETAT_GESLOT)
    nb = pg.evaluate("window.optionsValables(33.4).options.length")
    assert pg.inner_text("#sim-comparer") == f"Comparer les {nb} options valables"
    pg.click("#sim-comparer")
    pg.wait_for_selector("#sim-cmp-modal .sim-cmp-table tbody tr")
    # reste à charge et marge (compte admin) calculés par le serveur
    pg.wait_for_function("![...document.querySelectorAll('#sim-cmp-modal td')].some(td => td.textContent === '…')")
    lignes = pg.evaluate("""[...document.querySelectorAll('#sim-cmp-modal tbody tr')].map(tr =>
        [...tr.querySelectorAll('td')].map(td => td.innerText.replace(/\s+/g, ' ').trim()))""")
    assert len(lignes) == nb and all(l[0].startswith("2 × ") for l in lignes)
    entetes = pg.evaluate("[...document.querySelectorAll('#sim-cmp-modal th')].map(th => th.innerText)")
    assert entetes[:7] == ["Modèle × quantité", "Marque", "Temp. max", "Puissance installée · couverture",
                           "Prix TTC client", "Reste à charge", "Marge du dossier"]
    assert not any("NIMBUS" in l[0] for l in lignes)
    # le reste à charge vient du calcul du devis : prix − aides
    ref = ALTHERMA_18 + " TRI"
    st = dict(main.load_state_simulateur(NUM), modele_pac_id=ref, quantite_pac=2,
              prix_pac=main.prix_defaut_pac(17882.0, 2, main._admin_payload_with_m3()), user_modified_price=True)
    calc = main.calculer_devis(main._lead_for_response(main._find_lead(NUM)), st, main._admin_payload_with_m3(),
                               main._read_catalogue_pac())
    ligne = next(l for l in lignes if "ALTHERMA 3H HT R32 18 TRI" in l[0])
    attendu = f"{round(calc['reste_a_charge']):,}".replace(",", " ")
    assert ligne[5].replace(" ", " ").replace("\xa0", " ").startswith(attendu), (ligne, attendu)
    pg.click(f'#sim-cmp-modal tr[data-ref="{ref}"] .sim-cmp-choisir')
    pg.wait_for_function("document.querySelector('#sim-quantite').value === '2' && !document.querySelector('#sim-cmp-modal')")
    assert pg.evaluate("document.querySelector('.p6-pcard.on')?.dataset.modeleId") == ref
    assert pg.erreurs_js == []
