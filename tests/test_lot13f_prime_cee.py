# -*- coding: utf-8 -*-
"""Lot 13f : la prime CEE annoncée à l'étape Foyer = celle de l'étape Proposition = celle du pré-devis / devis, au
centime près, pour le choix de démarrage en cours (« attend l'accord MaPrimeRénov' » = PICOTY par défaut, « travaux tout
de suite » = ACE). Une seule fonction : primeCee() dans la page, prime_cee() côté serveur (parité testée ici).
Cas réel : PR-000857 (LE PRADO, revenus modestes) affichait 3 440 € (ACE) au Foyer et 3 302 € (PICOTY) à l'étape 6."""
import json
import os
import re
import shutil
import socket
import subprocess
import threading
import time

import pytest

import main
from services import service_devis as sd

DELEG = [{"nom": "PICOTY", "mwh_precaire": 12.7, "mwh_classique": 7.2, "actif": False},
         {"nom": "ACE", "mwh_precaire": 14, "mwh_classique": 7.5, "actif": True}]
LEAD = {"numero": "PR-13601", "civilite": "Madame", "nom": "Prado", "prenom": "Lea", "telephone": "0611131601",
        "email": "prado@example.invalid", "adresse_chantier": "1 rue A", "cp_chantier": "53000",
        "code_postal_chantier": "53000", "ville_chantier": "Laval", "type_logement": "maison",
        "surface_logement_m2": "130", "hsp": "2,5", "annee_construction": "1975", "mode_chauffage": "fioul",
        "ecs": "chaudiere", "type_emetteurs": "radiateurs_classiques", "alimentation_electrique": "monophase",
        "categorie": "modeste", "nombre_personnes": "3", "rfr": "30000", "cout_energetique_mensuel_eur": "250",
        "cout_energie_source": "reel", "statut": "a_rappeler"}
# trois leads identiques : sans choix enregistré (ancien lead), attente (PICOTY), tout de suite (ACE)
CAS = {"PR-13601": None, "PR-13602": "attente", "PR-13603": "sans_attente"}
PRIX = 20000


def _admin():
    return dict(main._admin_payload_with_m3(), delegataires=DELEG)


# ---------------------------------------------------------------- serveur : défaut, une seule fonction
def test_lead_neuf_choix_par_defaut_attente():
    main._atomic_write_json(main.LEADS_PATH, [])
    lead, cree = main._upsert_lead({k: v for k, v in LEAD.items() if k != "numero"})
    assert cree and main.load_state_simulateur(lead["numero"])["mode_mpr"] == "attente"
    main.save_state_simulateur_atomic(lead["numero"], {"mode_mpr": "sans_attente"})
    main._upsert_lead(dict(lead, nom="Autre"))                          # mise à jour : le choix n'est pas réécrit
    assert main.load_state_simulateur(lead["numero"])["mode_mpr"] == "sans_attente"


def test_devis_utilise_prime_cee():
    admin = _admin()
    for mode, deleg in ((None, "PICOTY"), ("attente", "PICOTY"), ("sans_attente", "ACE")):
        etat = {"service": "chauffage_seul", "prix_pac": PRIX, **({"mode_mpr": mode} if mode else {})}
        p = sd.prime_cee(LEAD, etat, admin, PRIX)
        brut = sd.calculer_cee_bar_th_171(LEAD, etat, admin)
        assert brut["details"]["delegataire"] == deleg and p["cee_final"] == brut["montant"] > 0
        assert sd.calculer_devis(LEAD, etat, admin, [])["montant_cee"] == p["cee_final"]


# ---------------------------------------------------------------- parité JS / Python
NODE_RUNNER = r"""
const fs = require('fs'), vm = require('vm');
const html = fs.readFileSync(process.argv[2], 'utf8');
const a = html.indexOf('/* HEXA-PRIME-CEE:DEBUT'), b = html.indexOf('/* HEXA-PRIME-CEE:FIN */');
if (a < 0 || b < 0) throw new Error('bloc HEXA-PRIME-CEE introuvable');
const ctx = { window: {} }; vm.createContext(ctx);
vm.runInContext(html.slice(a, b), ctx);
const P = ctx.window.HexaPrimeCee, e = JSON.parse(fs.readFileSync(0, 'utf8'));
process.stdout.write(JSON.stringify(e.cas.map(([st, mpr]) => P.primeCee(st, e.admin.formule_bar_th_171, e.admin, mpr))));
"""


@pytest.mark.skipif(shutil.which("node") is None, reason="node absent")
def test_parite_js_python(tmp_path):
    admin = _admin()
    cas_py, cas_js = [], []
    for cat in ("tres_modeste", "modeste", "intermediaire", "superieur"):
        for mode in (None, "attente", "sans_attente"):
            for prix, surface, cp in ((PRIX, 117, "53000"), (6000, 117, "75002"), (15000, 60, "06000")):
                lead = dict(LEAD, categorie=cat, cp_chantier=cp, code_postal_chantier=cp)
                etat = {"surface_chauffee": surface, **({"mode_mpr": mode} if mode else {})}
                mpr = sd.calculer_mpr(lead, etat, admin)
                cas_py.append(sd.prime_cee(lead, etat, admin, prix))
                st = {"categorie": cat, "type_logement": "maison", "surface_chauffee": surface, "prix_pac": prix,
                      "zone": sd.calculer_zone_climatique(cp), **({"mode_mpr": mode} if mode else {})}
                cas_js.append([st, mpr])
    runner = tmp_path / "parite13f.js"
    runner.write_text(NODE_RUNNER, encoding="utf-8")
    html = os.path.join(os.path.dirname(__file__), "..", "templates", "index.html")
    res = subprocess.run(["node", str(runner), html], input=json.dumps({"cas": cas_js, "admin": admin}),
                         capture_output=True, text=True, encoding="utf-8", check=True)
    js = json.loads(res.stdout)
    for (st, _), j, p in zip(cas_js, js, cas_py):
        assert j["mode"] == p["mode"], st
        assert round(j["cee"], 2) == round(p["cee_final"], 2) and round(j["mpr"], 2) == round(p["mpr_final"], 2), (st, j, p)
    assert any(p["details"].get("ecretement") for p in cas_py)                   # le plafond est bien exercé
    assert {j["delegataire"] for j in js} == {"PICOTY", "ACE"}


# ---------------------------------------------------------------- vrai Chromium : Foyer = Proposition = pré-devis
sync_api = pytest.importorskip("playwright.sync_api")
uvicorn = pytest.importorskip("uvicorn")


def _port_libre():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _semer():
    main._atomic_write_json(main.DELEGATAIRES_PATH, DELEG)
    main._atomic_write_json(main.LEADS_PATH, [dict(LEAD, numero=n, telephone="06111316%02d" % i)
                                              for i, n in enumerate(CAS)])
    for n, mode in CAS.items():
        main._atomic_write_json(main._state_simulateur_path(n), {})
        main.save_state_simulateur_atomic(n, {"service": "chauffage_seul", "option": "opt3", "prix_pac": PRIX,
                                              **({"mode_mpr": mode} if mode else {})})
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
        pg.base = serveur
        yield pg
        b.close()


def _txt(pg, sel):
    return re.sub(r"\s", " ", pg.inner_text(sel)).strip()


def _etape(pg, n):
    pg.evaluate(f"window.hexaParcoursEtape({n})")
    pg.wait_for_timeout(400)


def _lire(pg):
    """(prime CEE du dernier calcul, prime affichée au Foyer, total Foyer, note Foyer, prime affichée à l'étape 6)."""
    _etape(pg, 4)
    pg.wait_for_function("/\\d/.test((document.querySelector('#p6-aides-cee') || {}).textContent || '')", timeout=15000)
    foyer = (_txt(pg, "#p6-aides-cee"), _txt(pg, "#p6-aides-total"), _txt(pg, "#p6-aides-note"), _txt(pg, "#p6-aides"))
    _etape(pg, 6)
    pg.wait_for_function("/\\d/.test((document.querySelector('#sim-cee') || {}).textContent || '')", timeout=15000)
    return pg.evaluate("window.hexaSimLire().cee"), foyer, _txt(pg, "#sim-cee"), _txt(pg, "#sim-aides")


def _devis(numero):
    ctx = main._build_devis_context(None, numero)
    return float(re.sub(r"[^\d,]", "", ctx["montant_cee"]).replace(",", "."))


@pytest.mark.parametrize("numero", list(CAS))
def test_foyer_proposition_predevis_identiques(page, numero):
    page.goto(f"{page.base}/prospect/{numero}")
    page.wait_for_function("document.body.dataset.prospectNumero === %r && typeof window.hexaParcoursEtape === 'function'" % numero)
    page.wait_for_timeout(700)
    cee, (foyer_cee, foyer_total, note, bloc), prop_cee, prop_aides = _lire(page)
    assert cee == pytest.approx(_devis(numero), abs=0.005)                     # écran = pré-devis, au centime
    assert foyer_cee == prop_cee and foyer_total == prop_aides                 # Foyer = Proposition
    assert "au moins" not in bloc.lower() and "jusqu" not in bloc.lower() and "maximum" not in bloc.lower()
    if CAS[numero] == "sans_attente":
        assert note == "Prime CEE calculée pour des travaux tout de suite (modifiable à l'étape Proposition)."
    else:
        assert note == "Prime CEE calculée pour un démarrage après accord MaPrimeRénov' (modifiable à l'étape Proposition)."
    m = re.search(r"vous avez droit à ([\d ]+) € d'aides : ([\d ]+) € de MaPrimeRénov' et ([\d ]+) € de prime CEE", bloc)
    assert m and re.sub(r"\D", "", m.group(3)) == re.sub(r"\D", "", foyer_cee), bloc
    assert re.sub(r"\D", "", m.group(1)) == re.sub(r"\D", "", foyer_total)


def test_changer_le_choix_a_l_etape_6_met_a_jour_le_foyer(page):
    numero = "PR-13602"
    main.save_state_simulateur_atomic(numero, {"mode_mpr": "attente"})
    page.goto(f"{page.base}/prospect/{numero}")
    page.wait_for_function("document.body.dataset.prospectNumero === %r && typeof window.hexaParcoursEtape === 'function'" % numero)
    page.wait_for_timeout(700)
    avant, (foyer_avant, *_), _, _ = _lire(page)
    page.click('button[data-mode-mpr="sans_attente"]')
    page.wait_for_function("window.hexaSimLire().cee !== %r" % avant, timeout=15000)
    apres, (foyer_apres, _, note, _), prop_apres, _ = _lire(page)
    assert apres > avant and foyer_apres == prop_apres != foyer_avant
    assert "travaux tout de suite" in note
    page.wait_for_timeout(2000)                                                 # sauvegarde de l'état (1,5 s)
    assert main.load_state_simulateur(numero)["mode_mpr"] == "sans_attente"
    assert apres == pytest.approx(_devis(numero), abs=0.005)
