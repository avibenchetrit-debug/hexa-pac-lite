# -*- coding: utf-8 -*-
"""Lot 9b : tout ce qui permet de calculer une marge est réservé aux comptes admin, côté serveur. Un commercial ne
reçoit que ce dont le parcours a besoin (prix de vente TTC, caractéristiques techniques, calculs d'aides, documents
client) ; les routes admin lui répondent par un refus ; son parcours est identique à celui d'un admin.
(Décision : le tarif €/MWh des délégataires reste lisible — il sert au calcul de la prime CEE à l'écran.)"""
import io
import re
import time

import pytest
from fastapi.testclient import TestClient
from starlette.routing import Route

import main
import test_lot9 as l9
from test_fix_pdf import serveur, sync_api  # noqa: F401


@pytest.fixture(autouse=True)
def _auth_active():
    ancien = main.os.environ.get("AUTH_ENFORCE")
    main.os.environ["AUTH_ENFORCE"] = "1"
    yield
    main.os.environ["AUTH_ENFORCE"] = ancien or "0"


def _client(role):
    c = TestClient(main.app)
    c.cookies.update(l9._cookies(role))
    return c


RESERVES = ("achat", "cession_forcee", "positionnement_marche", "cout_fourniture_ht", "surplus_mode", "taux_marge_vise_pct")


def test_catalogue_sans_prix_d_achat_pour_un_commercial():
    l9._preparer()
    cat = main._read_catalogue_pac()
    cat[0]["cession_forcee"] = 9999
    main._atomic_write_json(main.CATALOGUE_PATH, cat)
    com, adm = _client("commercial").get("/api/catalogue-pac"), _client("admin").get("/api/catalogue-pac")
    assert com.status_code == adm.status_code == 200
    assert com.headers["X-Catalogue-Version"] == adm.headers["X-Catalogue-Version"]
    for m in com.json():
        assert not any(k in m for k in RESERVES), m.keys()
        assert m["ttc"] and m["ref"] and m["description_specs"] is not None and m["puiss35"]
    assert all("achat" in m for m in adm.json()) and adm.json()[0]["cession_forcee"] == 9999
    # tout le reste est identique
    sans = [{k: v for k, v in m.items() if k not in RESERVES} for m in adm.json()]
    assert com.json() == sans


def test_m3_sans_cout_d_achat_des_ballons_pour_un_commercial():
    l9._preparer()
    com, adm = _client("commercial").get("/api/admin/m3").json(), _client("admin").get("/api/admin/m3").json()
    b_com, b_adm = com["ballon_thermo"]["modeles"][0], adm["ballon_thermo"]["modeles"][0]
    assert "cout_fourniture_ht" not in b_com and b_com["fourniture_ht"] == 2900
    assert b_adm["cout_fourniture_ht"] == 1500
    assert com["regie_active"] is False and "delegataires" in com                       # tarif CEE : décision de garder
    assert {k: v for k, v in com.items() if k != "ballon_thermo"} == {k: v for k, v in adm.items() if k != "ballon_thermo"}


def _routes_admin():
    for r in main.app.routes:
        if isinstance(r, Route) and r.path.startswith("/api/admin/"):
            for m in sorted(r.methods - {"HEAD", "OPTIONS"}):
                yield m, re.sub(r"\{[^}]+\}", "PR-99001", r.path)


def test_toutes_les_routes_admin_refusent_un_commercial():
    l9._preparer()
    c = _client("commercial")
    lues_par_le_parcours = {("GET", "/api/admin/m3"), ("GET", "/api/admin/marques"), ("GET", "/api/admin/config")}
    vues = 0
    for meth, path in _routes_admin():
        if path == "/api/admin/auth":                     # connexion admin (mot de passe) : publique par nature
            continue
        r = c.request(meth, path, json={})
        vues += 1
        if (meth, path) in lues_par_le_parcours:
            assert r.status_code == 200, (meth, path)
            assert not re.search(r'"(achat|cout_fourniture_ht|frais_ecair_pct|lead|conv|cession_eur|marge)"', r.text), (meth, path)
        else:
            assert r.status_code in (401, 403), (meth, path, r.status_code)
    assert vues > 40


def test_les_cles_de_cout_ne_sortent_d_aucune_route_lue_par_un_commercial():
    l9._preparer()
    c = _client("commercial")
    for path in ("/api/catalogue-pac", "/api/admin/m3", "/api/admin/marques", "/api/admin/config", "/api/baremes",
                 f"/api/leads/{l9.LEAD['numero']}", f"/api/simulateur/{l9.LEAD['numero']}/state"):
        r = c.get(path)
        assert r.status_code == 200, path
        assert not re.search(r'"(achat|cout_fourniture_ht|frais_ecair_pct|cout_pose_ballon|cession_eur|plafond_pct)"', r.text), path


# ───────────── parcours identique : même fiche ouverte par un commercial et par un admin (vrai Chromium) ─────────────
def _ouvrir(serveur, pw, role):
    b = pw.chromium.launch()
    ctx = b.new_context(viewport={"width": 1500, "height": 950}, accept_downloads=True)
    ctx.add_cookies([{"name": k, "value": v, "url": serveur} for k, v in l9._cookies(role).items()])
    pg = ctx.new_page()
    pg.base = serveur
    erreurs = []
    pg.on("pageerror", lambda e: erreurs.append(str(e)))
    pg.on("response", lambda r: r.status >= 400 and "/api/" in r.url and erreurs.append(f"{r.status} {r.url}"))
    pg.erreurs = erreurs
    return b, pg


ETAPE6 = """() => [...document.querySelectorAll('#sim-dynamic, #sim-fin, #sim-aides, .p6-calc, #p-sim-6 .p6-sec')]
  .map(e => e.innerText.replace(/\\s+/g, ' ').trim()).join(' | ')"""


def test_parcours_commercial_identique_a_l_admin(serveur):
    l9._preparer()
    vues = {}
    with sync_api.sync_playwright() as pw:
        for role in ("admin", "commercial"):
            b, pg = _ouvrir(serveur, pw, role)
            pg.goto(f"{pg.base}/prospect/{l9.LEAD['numero']}")
            pg.wait_for_function("document.body.dataset.prospectNumero === 'PR-99001' && !document.documentElement.classList.contains('hexa-fiche-attente')",
                                 timeout=15000)
            etapes = []
            for n in range(1, 7):
                pg.evaluate(f"window.hexaParcoursEtape({n})"); pg.wait_for_timeout(700)
                etapes.append(pg.evaluate("document.querySelector('#p-corps') ? document.querySelector('#p-corps').dataset.etape : ''"))
            texte6 = pg.evaluate(ETAPE6)
            pg.evaluate("document.getElementById('btn-voir-devis').click()")
            pg.wait_for_selector("#devis-pdf-btn", state="visible", timeout=60000)
            with pg.expect_download(timeout=90000) as dl:
                pg.click("#devis-pdf-btn")
            pdf = open(dl.value.path(), "rb").read()
            vues[role] = {"etapes": etapes, "etape6": texte6, "pdf": pdf, "nom": dl.value.suggested_filename,
                          "erreurs": [e for e in pg.erreurs if "/api/admin/marge-dossier" not in e]}
            b.close()
    a, c = vues["admin"], vues["commercial"]
    assert c["etapes"] == a["etapes"] == ["1", "2", "3", "4", "5", "6"]
    assert c["etape6"] == a["etape6"] and "€" in c["etape6"]                        # mêmes montants à l'écran
    assert c["nom"] == a["nom"]
    pypdf = pytest.importorskip("pypdf")
    texte = lambda b: " ".join((p.extract_text() or "") for p in pypdf.PdfReader(io.BytesIO(b)).pages)
    assert texte(c["pdf"]) == texte(a["pdf"])                                            # même document client
    assert c["erreurs"] == [], c["erreurs"]                                             # aucune requête refusée au commercial
