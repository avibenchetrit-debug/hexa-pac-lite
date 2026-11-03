# -*- coding: utf-8 -*-
"""Admin → Marges, affichage seulement (vrai Chromium) : sur un écran de portable (1 400 px), le tableau tient sans texte
coupé (« Positionnement marché » passe à la ligne dans sa case), la page ne défile jamais sur le côté ; plus étroit, le
tableau défile dans son cadre, colonne « Modèle » fixe ; champs des cartes alignés en bas ; le bandeau ECAIR reprend la
valeur du champ. Aucun calcul n'est touché."""
import json
import socket
import threading
import time

import pytest

import main

sync_api = pytest.importorskip("playwright.sync_api")
uvicorn = pytest.importorskip("uvicorn")

LONG = "Légèrement au-dessus (marché dès ≈ 11 000 – 12 750 € posé), à argumenter sur la marque et le SAV"


def _port_libre():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(autouse=True)
def _donnees_restaurees():
    chemins = (main.CATALOGUE_PATH, main.PARAMETRES_ADMIN_PATH)
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


def _ouvrir_marges(serveur, largeur):
    cat = json.load(open(main.REPO_CATALOGUE_PATH, encoding="utf-8"))
    for m in cat:
        m["positionnement_marche"] = LONG
    main._atomic_write_json(main.CATALOGUE_PATH, cat)
    params = main.load_parametres_admin()
    params["params"]["frais_ecair_pct"] = 15
    params["params"]["frais_ecair_lot9"] = True
    main._atomic_write_json(main.PARAMETRES_ADMIN_PATH, params)
    main._write_users([{"id": "testeur", "username": "testeur", "password_hash": main._hash_password("essai-local"),
                        "role": "admin", "actif": True, "cree_at": main._now_iso(), "visibilite": "tous"}])
    p = sync_api.sync_playwright().start()
    b = p.chromium.launch()
    ctx = b.new_context(viewport={"width": largeur, "height": 900})
    ctx.route("**/*", lambda r: r.continue_() if r.request.url.startswith(serveur) else r.abort())
    pg = ctx.new_page()
    pg.goto(serveur + "/login")
    pg.fill("#username", "testeur")
    pg.fill("#password", "essai-local")
    pg.click("#login-btn")
    pg.wait_for_url(lambda u: "/login" not in u)
    pg.goto(serveur + "/")
    pg.wait_for_selector("#pv-admin", state="attached")
    pg.evaluate("document.getElementById('pv-admin').click()")
    pg.wait_for_selector("#admin-auth-password, #adm-roottabs", timeout=10000)
    if pg.query_selector("#admin-auth-password"):
        pg.fill("#admin-auth-password", main.os.environ.get("ADMIN_PASSWORD", "hexarenov2026"))
        pg.click('[data-act="unlock"]')
    pg.wait_for_selector("#adm-roottabs", timeout=15000)
    pg.click('.adm-roottab[data-roottab="marge"]')
    pg.wait_for_selector(".adm-marges-table textarea.adm-pos")
    pg.wait_for_timeout(300)
    return p, b, pg


MESURES = """() => {
  const d = document.documentElement, wrap = document.querySelector('.adm-marges .adm-table-wrap');
  const t = document.querySelector('.adm-marges-table');
  const textes = [...t.querySelectorAll('textarea.adm-pos')];
  return { page_defile: d.scrollWidth > d.clientWidth,
           tableau_dans_cadre: t.getBoundingClientRect().right <= wrap.getBoundingClientRect().right + 1,
           cadre_defile: wrap.scrollWidth > wrap.clientWidth + 1,
           textes: textes.length,
           textes_coupes: textes.filter(x => x.scrollHeight > x.clientHeight + 2 || x.scrollWidth > x.clientWidth + 2).length,
           bas_champs: [...document.querySelectorAll('.adm-marges-params > .adm-field')].map(f => {
             const c = f.querySelector('.adm-euro, b'); const r = c.getBoundingClientRect();
             return [Math.round(f.getBoundingClientRect().top), Math.round(r.bottom)]; }) }; }"""


def test_tableau_lisible_sur_un_portable(serveur):
    p, b, pg = _ouvrir_marges(serveur, 1400)
    try:
        m = pg.evaluate(MESURES)
        assert m["textes"] > 0 and m["textes_coupes"] == 0, m
        assert not m["page_defile"] and m["tableau_dans_cadre"] and not m["cadre_defile"], m
        # champs alignés en bas des cartes : même bas pour toutes les cartes d'une même rangée
        rangees = {}
        for haut, bas in m["bas_champs"]:
            rangees.setdefault(haut, set()).add(bas)
        assert all(len(v) == 1 for v in rangees.values()), rangees
    finally:
        b.close()
        p.stop()


def test_ecran_etroit_le_cadre_defile_colonne_modele_fixe(serveur):
    p, b, pg = _ouvrir_marges(serveur, 980)
    try:
        m = pg.evaluate(MESURES)
        assert not m["page_defile"] and m["cadre_defile"] and m["textes_coupes"] == 0, m
        decalage = pg.evaluate("""() => { const w = document.querySelector('.adm-marges .adm-table-wrap'); w.scrollLeft = 300;
          const td = document.querySelector('.adm-marges-table tr.adm-marge-row td');
          return Math.round(td.getBoundingClientRect().left - w.getBoundingClientRect().left); }""")
        assert 0 <= decalage <= 2, decalage                  # la colonne « Modèle » reste collée à gauche du cadre
    finally:
        b.close()
        p.stop()


def test_bandeau_ecair_reprend_le_champ(serveur):
    p, b, pg = _ouvrir_marges(serveur, 1400)
    try:
        assert pg.inner_text("#adm-marges-ecair") == "15"
        champ = pg.locator('.adm-marges-params input[data-p="frais_ecair_pct"]')
        champ.fill("17,5")
        champ.dispatch_event("input")
        pg.wait_for_timeout(200)
        assert pg.inner_text("#adm-marges-ecair") == "17,5"
        assert "12,5 %" not in pg.inner_text(".adm-marges .adm-section-help")
    finally:
        b.close()
        p.stop()
