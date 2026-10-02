# -*- coding: utf-8 -*-
"""Lot 9c : « Marge du dossier » sur un dossier FACTURÉ (verrouillé) — admin seulement, lecture seule, calculée à partir
du devis archivé (prix de vente, prime CEE et MPR facturés, délégataire nommé sur le document) et des coûts ACTUELS de
l'admin (« Marge indicative »). Rien ne change sur le dossier ni sur ses documents. Fiches fabriquées ici."""
import hashlib
import os
import time

import pytest
from fastapi.testclient import TestClient

import main
import test_lot9 as l9
from test_fix_pdf import serveur, sync_api  # noqa: F401

NUM = l9.LEAD["numero"]


def _empreintes():
    chemins = [main.LEADS_PATH, main.FACTURES_META_PATH, main.DEVIS_META_PATH, main._state_simulateur_path(NUM),
               main.CATALOGUE_PATH, os.path.join(main.DEVIS_DIR, f"{NUM}_v1.html")]
    return {c: hashlib.sha256(open(c, "rb").read()).hexdigest() for c in chemins if os.path.exists(c)}


def _facturer(mode_archive="sans_attente", mode_actuel="attente"):
    """Devis envoyé (archivé) avec mode_archive (ACE si tout de suite), facture qui s'y réfère, dossier verrouillé ;
    puis l'état actuel du simulateur diffère (mode_actuel) pour prouver que c'est l'archive qui compte."""
    l9._preparer(mode_archive)
    ctx = main._build_devis_context(None, NUM, avec_sous_traitant=True)
    html = main.templates.env.get_template("devis_pac.html").render(ctx)
    os.makedirs(main.DEVIS_DIR, exist_ok=True)
    chemin = os.path.join(main.DEVIS_DIR, f"{NUM}_v1.html")
    open(chemin, "w", encoding="utf-8").write(html)
    main._atomic_write_json(main.DEVIS_META_PATH, {NUM: [{"version": "1", "numero_devis": "DE2099-0001-1", "variante": "devis",
                                                          "html_file": chemin, "file": "", "statut": "envoye"}]})
    etat = main._read_json(main._state_simulateur_path(NUM), {})
    etat["mode_mpr"] = mode_actuel
    main._atomic_write_json(main._state_simulateur_path(NUM), etat)
    leads = main._read_json(main.LEADS_PATH, [])
    leads[0]["statut"] = "installation_finie"
    main._atomic_write_json(main.LEADS_PATH, leads)
    main._atomic_write_json(main.FACTURES_META_PATH, {NUM: [{"numero_facture": "FA-2099-0007", "numero_devis_ref": "DE2099-0001-1",
                                                             "montant_ttc": 15990.0, "file": ""}]})
    assert main._dossier_fige(NUM)


def _marge(role="admin", corps=None):
    c = TestClient(main.app)
    return c.post(f"/api/admin/marge-dossier/{NUM}", json=corps or {}, cookies=l9._cookies(role))


def test_dossier_facture_marge_lue_dans_le_devis_archive():
    _facturer("sans_attente", "attente")                 # facturé ACE ; le simulateur dirait aujourd'hui PICOTY
    d = _marge().json()
    assert d["indicative"] is True and d["source"] == "devis archivé DE2099-0001-1" and d["facture"] == "FA-2099-0007"
    assert d["delegataire"] == "ACE" and d["cee_devis"] == 5800.0 and d["mpr"] == 5000.0 and d["frais_ecair"] == 0.0   # ACE : 0
    assert abs(d["ht"] - 15990 / 1.055) < 0.01 and d["ecart_ttc"] == 0.0
    assert d["cee_supplementaire"] == 1844.0 and d["valorisation_cee"] == 7644.0      # valorisation ACE − prime facturée
    assert abs(d["marge_nette"] - (d["marge_brute"] - 526 - 1200 + 1844.0)) < 0.01


def test_dossier_facture_picoty_avec_mpr_prefinancee():
    _facturer("attente", "sans_attente")                 # facturé PICOTY (MPR préfinancée imprimée)
    d = _marge().json()
    assert d["delegataire"] == "PICOTY" and d["mpr"] == 5000.0 and d["cee_supplementaire"] == 1025.0
    assert d["frais_ecair"] == 625.0                       # 12,5 % × 5 000


def test_couts_actuels_de_l_admin():
    _facturer()
    avant = _marge().json()
    params = main.load_parametres_admin()
    params["params"]["pose"] = params["params"]["pose"] + 500
    main.save_parametres_admin_atomic(params)
    apres = _marge().json()
    assert abs((avant["marge_nette"] - apres["marge_nette"]) - 500) < 0.01 and apres["ht"] == avant["ht"]


def test_rien_ne_change_sur_le_dossier_ni_ses_documents():
    _facturer()
    avant = _empreintes()
    _marge(corps={"modele_pac_id": "ATL-EXCELLIA-S-9", "mode_mpr": "attente", "prix_pac": 1})   # état envoyé : ignoré
    d = _marge().json()
    assert _empreintes() == avant
    assert d["modele"] == l9.MODELE["ref"]                 # le modèle facturé, pas celui envoyé


def test_archive_illisible_signalee():
    _facturer()
    os.remove(os.path.join(main.DEVIS_DIR, f"{NUM}_v1.html"))
    d = _marge().json()
    assert d["indicative"] is True and d["source"] == "archive illisible : calcul actuel du dossier"


def test_refuse_a_un_commercial():
    _facturer()
    ancien = os.environ.get("AUTH_ENFORCE")
    os.environ["AUTH_ENFORCE"] = "1"
    try:
        assert _marge("commercial").status_code == 403
    finally:
        os.environ["AUTH_ENFORCE"] = ancien or "0"


# ───────────── écran (vrai Chromium) : visible pour un admin, en lecture seule, avec la mention ; jamais pour un commercial
def _etape6(serveur, pw, role):
    b = pw.chromium.launch()
    ctx = b.new_context(viewport={"width": 1500, "height": 950})
    ctx.add_cookies([{"name": k, "value": v, "url": serveur} for k, v in l9._cookies(role).items()])
    pg = ctx.new_page()
    pg.goto(f"{serveur}/prospect/{NUM}")
    pg.wait_for_function("document.body.dataset.prospectNumero === %r && !document.documentElement.classList.contains('hexa-fiche-attente')" % NUM,
                         timeout=15000)
    pg.evaluate("window.hexaParcoursEtape(6)")
    pg.wait_for_timeout(1500)
    return b, pg


def test_ecran_dossier_facture_admin_et_commercial(serveur):
    _facturer()
    with sync_api.sync_playwright() as pw:
        b, pg = _etape6(serveur, pw, "admin")
        assert pg.evaluate("window.__hexaDossierFige") is True
        pg.wait_for_function("(document.getElementById('sim-marge-corps') || {}).textContent && document.getElementById('sim-marge-corps').textContent.includes('Marge indicative')",
                             timeout=10000)
        txt = pg.text_content("#sim-marge-corps").replace(" ", " ").replace("\xa0", " ")
        assert "Marge indicative : calculée avec les coûts actuels de l'admin." in txt
        assert "devis archivé DE2099-0001-1" in txt and "CEE supplémentaire réel (ACE)" in txt and "1 844" in txt
        assert pg.evaluate("document.querySelectorAll('#sim-marge-dossier input, #sim-marge-dossier select, #sim-marge-dossier button').length") == 0
        b.close()
        b, pg = _etape6(serveur, pw, "commercial")
        assert pg.query_selector("#sim-marge-dossier") is None
        b.close()
