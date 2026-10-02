# -*- coding: utf-8 -*-
"""Lot 9 : page « Marges » (admin), marge du dossier (fiche, admin seulement), régie masquée + « Réactiver la régie »,
frais ECAIR 12,5 % (une seule source), filtres et recherche du catalogue. Aucun prix ni calcul client modifié.
Fiches fabriquées ici : aucune donnée réelle (le cas « type GALEA » reprend seulement des caractéristiques techniques)."""
import io
import json
import time

import pytest
from fastapi.testclient import TestClient

import main
from services import marges
from test_fix_pdf import _port_libre, serveur, sync_api  # noqa: F401

P = {"pose": 3000, "acc": 550, "tva": 0.055, "lead": 30, "conv": 0.025, "vt1": 200, "cofrac1": 226, "urba1": 100,
     "frais_ecair_pct": 12.5, "cout_pose_ballon": 600}
DELEG = [{"nom": "PICOTY", "mwh_precaire": 12.5, "mwh_classique": 7.2, "actif": False},
         {"nom": "ACE", "mwh_precaire": 14, "mwh_classique": 7.5, "actif": True}]
MODELE = {"ref": "ARI-NIMBUS-NET-R32-DUO-15 TRI", "nom": "NIMBUS FICTIVE DUO 15 TRI", "usage": "Chauffage + ECS",
          "alim": "Triphasé", "puiss35": 15, "puiss_chauf": 15, "etas35": 178, "etas55": 151, "achat": 7000, "ttc": 15990,
          "description_specs": [{"champ": "Marque", "valeur": "ARISTON"}]}
CATALOGUE = [MODELE,
             dict(MODELE, ref="ATL-EXCELLIA-S-9", nom="EXCELLIA FICTIVE 9", usage="Chauffage seul", alim="Monophasé", puiss35=9,
                  puiss_chauf=9, achat=4261, ttc=13694, description_specs=[{"champ": "Marque", "valeur": "ATLANTIC"}]),
             dict(MODELE, ref="THA-MTBL-R290-4", nom="MONTBLANC FICTIVE 4", marque="THALEOS", usage="Chauffage", alim="Monophasé",
                  puiss35=4.5, puiss_chauf=4.5, achat=2100, ttc=11191, description_specs=[]),
             dict(MODELE, ref="DAI-ALTHERMA-3HHT-R32-16 TRI", nom="ALTHERMA FICTIVE 16 TRI", usage="Chauffage seul", puiss35=16,
                  puiss_chauf=16, achat=6900, ttc=17990, description_specs=[{"champ": "Marque", "valeur": "DAIKIN"}])]
# Cas « type GALEA » : maison 185 m², 49430, très modeste, PAC DUO 15 TRI à 15 990 €, chauffage + ECS
LEAD = {"numero": "PR-99001", "civilite": "Madame", "nom": "Marge", "prenom": "Essai", "telephone": "0600000000",
        "email": "m@x.fr", "type_logement": "maison", "surface_logement_m2": "185", "cp_chantier": "49430",
        "code_postal_chantier": "49430", "ville_chantier": "Durtal", "adresse_chantier": "1 rue A", "categorie": "tres_modeste",
        "mode_chauffage": "fioul", "type_emetteurs": "radiateurs_classiques", "nombre_personnes": "1", "hsp": "2,7",
        "alimentation_electrique": "triphase", "ecs": "chaudiere", "statut": "devis", "source": "Régie commerciale"}


def _preparer(mode_mpr="attente", ballon=False):
    main._atomic_write_json(main.CATALOGUE_PATH, [dict(m) for m in CATALOGUE])
    main._atomic_write_json(main.DELEGATAIRES_PATH, DELEG)
    main._atomic_write_json(main.FACTURES_META_PATH, {})
    main._atomic_write_json(main.LEADS_PATH, [dict(LEAD)])
    params = main.load_parametres_admin()
    params["params"] = dict(params.get("params") or {}, **P, regie_active=False)
    params.setdefault("ballon_thermo", {})["modeles"] = [{"ref": "ballon-1", "nom": "BALLON FICTIF", "fourniture_ht": 2900,
                                                          "cout_fourniture_ht": 1500, "description_specs": []}]
    main.save_parametres_admin_atomic(params)
    main._atomic_write_json(main._state_simulateur_path(LEAD["numero"]), {})
    etat = {"modele_pac_id": MODELE["ref"], "surface_chauffee": 151, "service": "chauffage_ecs", "mode_mpr": mode_mpr,
            "option": "opt3", "prix_pac": 15990}
    if ballon:
        etat.update(service="chauffage_seul", ballon_ref="ballon-1", ballon_emplacement="interieur")
    main.save_state_simulateur_atomic(LEAD["numero"], etat)
    main._migrate_lot9()                       # comme au démarrage : positionnement pré-rempli


def _cookies(role):
    main._write_users([{"id": "boss", "username": "boss", "role": "admin", "actif": True, "password_hash": main._hash_password("x"),
                        "cree_at": main._now_iso(), "visibilite": "tous"},
                       {"id": "vendeur", "username": "vendeur", "role": "commercial", "actif": True,
                        "password_hash": main._hash_password("x"), "cree_at": main._now_iso(), "visibilite": "tous"}])
    u = "boss" if role == "admin" else "vendeur"
    return {main.SESSION_COOKIE: main._sign_session(u, role, int(time.time()))}


# ─────────────────────────────── 1. Marges : calcul = calcul manuel (3 modèles) ───────────────────────────────
@pytest.mark.parametrize("m, attendu", [
    # HT = TTC/1,055 ; coût = achat + 3000 + 550 ; frais dossier 526 ; acquisition 30/0,025 = 1200
    (CATALOGUE[0], {"ht": 15990 / 1.055, "cout_revient": 7000 + 3550, "marge_brute": 15990 / 1.055 - 10550,
                    "marge_nette": 15990 / 1.055 - 10550 - 526 - 1200}),
    (CATALOGUE[1], {"ht": 13694 / 1.055, "cout_revient": 4261 + 3550, "marge_brute": 13694 / 1.055 - 7811,
                    "marge_nette": 13694 / 1.055 - 7811 - 1726}),
    (CATALOGUE[2], {"ht": 11191 / 1.055, "cout_revient": 2100 + 3550, "marge_brute": 11191 / 1.055 - 5650,
                    "marge_nette": 11191 / 1.055 - 5650 - 1726}),
])
def test_marges_egales_au_calcul_manuel(m, attendu):
    r = marges.marge_modele(m, P)
    for k, v in attendu.items():
        assert abs(r[k] - v) < 0.01, (k, r[k], v)
    assert r["frais_dossier"] == 526 and r["acquisition"] == 1200
    assert abs(r["marge_nette_pct"] - r["marge_nette"] / r["ht"]) < 1e-9


def test_positionnement_pre_rempli():
    pos = {m["ref"]: marges.positionnement_defaut(m) for m in CATALOGUE}
    assert pos["ATL-EXCELLIA-S-9"] == "Au-dessus du marché (moyenne ≈ 12 400 € posé)"
    assert pos["ARI-NIMBUS-NET-R32-DUO-15 TRI"] == "Haut de fourchette"
    assert pos["THA-MTBL-R290-4"] == "Un peu cher pour la puissance"
    assert pos["DAI-ALTHERMA-3HHT-R32-16 TRI"] == "Dans le marché, compétitif (14 000 – 18 000 € posé)"
    assert marges.positionnement_defaut(dict(MODELE, ref="ATL-EXCELLIA-S-DUO-9")).startswith("Hors marché haut")
    assert marges.positionnement_defaut(dict(MODELE, ref="THA-MTBL-R290-12", puiss35=12)) == "Dans le marché"


# ─────────────────────────────── 3. Frais ECAIR : 12,5 %, une seule source ───────────────────────────────
def test_frais_ecair_une_seule_source_a_12_5():
    brut = main._read_json(main.PARAMETRES_ADMIN_PATH, {})
    brut.setdefault("params", {})["frais_ecair_pct"] = 15
    brut["params"].pop("frais_ecair_lot9", None)
    brut.setdefault("prix_vente_devis", {})["frais_ecair_pct"] = 15
    main._atomic_write_json(main.PARAMETRES_ADMIN_PATH, brut)
    main._migrate_lot9()
    apres = main._read_json(main.PARAMETRES_ADMIN_PATH, {})
    assert apres["params"]["frais_ecair_pct"] == 12.5 and "frais_ecair_pct" not in apres["prix_vente_devis"]
    # une valeur changée ensuite n'est jamais réécrasée ; l'ancienne copie renvoyée par un navigateur est ignorée
    main.save_parametres_admin_atomic({"params": {"frais_ecair_pct": 13}, "prix_vente_devis": {"frais_ecair_pct": 15}})
    main._migrate_lot9()
    apres = main._read_json(main.PARAMETRES_ADMIN_PATH, {})
    assert apres["params"]["frais_ecair_pct"] == 13 and "frais_ecair_pct" not in apres["prix_vente_devis"]


def test_frais_ecair_n_entre_dans_aucun_calcul_client():
    """Ni le devis, ni les aides, ni les économies, ni le financement ne lisent ce paramètre (marge interne seulement)."""
    for f in ("services/service_devis.py", "services/economies.py", "services/dpe_audit.py"):
        assert "frais_ecair" not in open(f, encoding="utf-8").read(), f
    lignes = [l.strip() for l in open("main.py", encoding="utf-8").read().splitlines() if "frais_ecair" in l]
    permis = ('"frais_ecair_pct": 12.5,', 'if isinstance(data.get("prix_vente_devis"), dict):', 'data["prix_vente_devis"].pop(',
              'params["frais_ecair_pct"] = 12.5', 'params["frais_ecair_lot9"] = True', 'if params is not None and not params.get("frais_ecair_lot9")',
              'if "frais_ecair_pct" in pvd:', 'pvd.pop("frais_ecair_pct", None)', '"""Lot 9, au démarrage', 'changée ensuite')
    assert all(any(l.startswith(x) or x in l for x in permis) for l in lignes), lignes


# ─────────────────────────────── 4. Marge du dossier : admin seulement, CEE supplémentaire réel ────────────────
def test_marge_du_dossier_refusee_aux_comptes_utilisateurs():
    _preparer()
    c = TestClient(main.app)
    os_auth = main.os.environ.get("AUTH_ENFORCE")
    main.os.environ["AUTH_ENFORCE"] = "1"
    try:
        r = c.post(f"/api/admin/marge-dossier/{LEAD['numero']}", json={}, cookies=_cookies("commercial"))
        assert r.status_code == 403
        r = c.post("/api/admin/marges/export", json={"entetes": ["a"], "lignes": [[1]]}, cookies=_cookies("commercial"))
        assert r.status_code == 403
    finally:
        main.os.environ["AUTH_ENFORCE"] = os_auth or "0"


@pytest.mark.parametrize("mode, deleg, cee_sup, ecair", [("attente", "PICOTY", 1025.0, 625.0),          # 12,5 % × 5 000
                                                          ("sans_attente", "ACE", 1844.0, 0.0)])
def test_cee_supplementaire_reel_type_galea(mode, deleg, cee_sup, ecair):
    _preparer(mode)
    r = TestClient(main.app).post(f"/api/admin/marge-dossier/{LEAD['numero']}", json={}, cookies=_cookies("admin"))
    assert r.status_code == 200, r.text
    d = r.json()
    assert (d["delegataire"], d["cee_supplementaire"], d["frais_ecair"]) == (deleg, cee_sup, ecair)
    calc = main.calculer_devis(main._lead_for_response(main._find_lead(LEAD["numero"])),
                               main._load_state_simulateur(LEAD["numero"], LEAD, main._read_catalogue_pac()),
                               main._admin_payload_with_m3(), main._read_catalogue_pac())
    assert d["cee_supplementaire"] == calc["_cee_conserve"] and d["mpr"] == calc["montant_mpr"]
    assert abs(d["marge_nette"] - (d["marge_brute"] - 526 - 1200 + cee_sup - ecair)) < 0.01


def test_marge_du_dossier_suit_l_etat_envoye_sans_rien_enregistrer():
    _preparer("attente")
    c = TestClient(main.app)
    avant = main._read_json(main._state_simulateur_path(LEAD["numero"]), {})
    a = c.post(f"/api/admin/marge-dossier/{LEAD['numero']}", json={}, cookies=_cookies("admin")).json()
    b = c.post(f"/api/admin/marge-dossier/{LEAD['numero']}", json={"mode_mpr": "sans_attente"}, cookies=_cookies("admin")).json()
    d = c.post(f"/api/admin/marge-dossier/{LEAD['numero']}", json={"modele_pac_id": "ATL-EXCELLIA-S-9", "service": "chauffage_seul",
                                                                    "ballon_ref": "ballon-1", "ballon_emplacement": "interieur"},
               cookies=_cookies("admin")).json()
    assert a["delegataire"] == "PICOTY" and b["delegataire"] == "ACE"
    assert d["modele"] == "ATL-EXCELLIA-S-9" and d["ballon"] == "BALLON FICTIF" and d["achat"] == 4261 + 1500
    assert main._read_json(main._state_simulateur_path(LEAD["numero"]), {}) == avant      # rien d'enregistré


def test_export_excel():
    openpyxl = pytest.importorskip("openpyxl")
    r = TestClient(main.app).post("/api/admin/marges/export", json={"entetes": ["Référence", "Marge"], "lignes": [["X-1", 1234.5]]},
                                  cookies=_cookies("admin"))
    assert r.status_code == 200 and "spreadsheetml" in r.headers["content-type"]
    ws = openpyxl.load_workbook(io.BytesIO(r.content)).active
    assert [c.value for c in ws[1]] == ["Référence", "Marge"] and [c.value for c in ws[2]] == ["X-1", 1234.5]


# ─────────────────────────────── écrans (vrai Chromium) ───────────────────────────────
@pytest.fixture
def navigateur(serveur):
    with sync_api.sync_playwright() as pw:
        b = pw.chromium.launch()

        def ouvrir(role="admin", largeur=1500):
            ctx = b.new_context(viewport={"width": largeur, "height": 950}, accept_downloads=True)
            ctx.add_cookies([{"name": k, "value": v, "url": serveur} for k, v in _cookies(role).items()])
            pg = ctx.new_page()
            pg.base = serveur
            return pg
        yield ouvrir
        b.close()


def _admin(pg, onglet):
    pg.goto(pg.base + "/")
    pg.wait_for_selector("#pv-admin", state="attached")
    pg.evaluate("document.getElementById('pv-admin').click()")
    pg.wait_for_selector("#admin-auth-password, #adm-roottabs", timeout=10000)
    if pg.query_selector("#admin-auth-password"):
        pg.fill("#admin-auth-password", main.os.environ.get("ADMIN_PASSWORD", "hexarenov2026"))
        pg.click('[data-act="unlock"]')
    pg.wait_for_selector("#adm-roottabs", timeout=15000)
    pg.click(f'.adm-roottab[data-roottab="{onglet}"]')
    pg.wait_for_timeout(400)


def _fiche_etape6(pg):
    pg.goto(f"{pg.base}/prospect/{LEAD['numero']}")
    pg.wait_for_function("document.body.dataset.prospectNumero === %r && !document.documentElement.classList.contains('hexa-fiche-attente')"
                         % LEAD["numero"], timeout=15000)
    pg.evaluate("window.hexaParcoursEtape(6)")
    pg.wait_for_timeout(1500)


def test_bloc_marge_du_dossier_invisible_pour_un_compte_utilisateur(navigateur):
    _preparer()
    pg = navigateur("commercial")
    _fiche_etape6(pg)
    assert pg.query_selector("#sim-marge-dossier") is None
    assert "Marge du dossier" not in pg.evaluate("document.body.innerText")


def test_bloc_marge_du_dossier_admin_replie_et_a_jour(navigateur):
    _preparer("attente")
    pg = navigateur("admin")
    _fiche_etape6(pg)
    pg.wait_for_function("document.querySelector('#sim-marge-resume') && document.querySelector('#sim-marge-resume').textContent.includes('€')",
                         timeout=10000)
    assert not pg.evaluate("document.getElementById('sim-marge-dossier').open")           # replié par défaut
    corps = pg.text_content("#sim-marge-corps").replace(" ", " ").replace(" ", " ")
    assert "CEE supplémentaire réel (PICOTY)" in corps and "1 025" in corps and "625" in corps
    pg.evaluate("document.querySelector('[data-mode-mpr=sans_attente]').click()")         # délégataire : tout de suite -> ACE
    pg.wait_for_function("document.getElementById('sim-marge-corps').textContent.includes('(ACE)')", timeout=10000)
    assert "1 844" in pg.text_content("#sim-marge-corps").replace(" ", " ").replace(" ", " ")


def test_regie_invisible_puis_reapparue(navigateur):
    _preparer()
    pg = navigateur("admin")
    pg.goto(pg.base + "/")
    pg.wait_for_selector("#pv-regie", state="attached")
    pg.wait_for_timeout(800)
    assert not pg.is_visible("#pv-regie")
    _admin(pg, "marge")
    regie = "getComputedStyle(document.querySelector('.regie-only')).display"
    assert pg.evaluate(regie) == "none" and not pg.is_visible('th.header-option2')
    pg.check('.adm-p[data-p="regie_active"]')
    pg.wait_for_timeout(800)
    assert pg.evaluate("document.body.classList.contains('regie-active')") and pg.evaluate(regie) != "none"
    assert main.load_parametres_admin()["params"]["regie_active"] is True
    pg2 = navigateur("commercial")                                                       # pour tous les comptes
    _fiche_etape6(pg2)
    assert pg2.evaluate("getComputedStyle(document.querySelector('option[value=\"Régie commerciale\"]')).display") != "none"
    pg.uncheck('.adm-p[data-p="regie_active"]')
    pg.wait_for_timeout(800)
    assert main.load_parametres_admin()["params"]["regie_active"] is False and pg.evaluate(regie) == "none"
    lead = main._find_lead(LEAD["numero"])
    assert lead["source"] == "Régie commerciale"                                         # rien n'est supprimé


def test_prix_modifie_dans_marges_meme_prix_au_catalogue_et_sur_un_nouveau_devis(navigateur):
    _preparer()
    pg = navigateur("admin")
    _admin(pg, "marge")
    ligne = 'tr.adm-marge-row[data-f-texte*="excellia"]'
    champ = f'{ligne} .adm-in[data-f="ttc"]'
    pg.click(champ); pg.keyboard.press("Control+A"); pg.keyboard.type("13999")              # comme une vraie saisie
    pg.wait_for_timeout(300)
    ht = pg.inner_text(f'{ligne} [data-c="ht"]')
    assert ht.replace(" ", " ").replace("\xa0", " ").startswith("13 269")              # 13 999 / 1,055
    pg.click("#adm-marges-save")
    pg.wait_for_timeout(1500)
    m = next(x for x in main._read_catalogue_pac() if x["ref"] == "ATL-EXCELLIA-S-9")
    assert m["ttc"] == 13999 and m["positionnement_marche"] is not None
    main._atomic_write_json(main._state_simulateur_path(LEAD["numero"]), {})          # nouveau devis : aucun prix enregistré
    main.save_state_simulateur_atomic(LEAD["numero"], {"modele_pac_id": "ATL-EXCELLIA-S-9", "service": "chauffage_seul",
                                                       "mode_mpr": "attente", "option": "opt3"})
    calc = main.calculer_devis(main._lead_for_response(main._find_lead(LEAD["numero"])),
                               main._load_state_simulateur(LEAD["numero"], LEAD, main._read_catalogue_pac()),
                               main._admin_payload_with_m3(), main._read_catalogue_pac())
    assert round(calc["total_ttc"]) == 13999


def test_recherche_et_filtres_du_catalogue(navigateur):
    _preparer()
    pg = navigateur("admin")
    _admin(pg, "catalogue")
    pg.evaluate("document.querySelector('[data-toggle-bloc=\"5-2\"]').click()")
    pg.wait_for_timeout(300)
    box = '.adm-filtres[data-filtres="catalogue"]'
    compteur = lambda: pg.inner_text(f"{box} .adm-f-compteur")
    visibles = lambda: pg.evaluate("[...document.querySelectorAll('[data-filtre-table=catalogue] tbody tr[data-f-marque]')].filter(t => !t.hidden).map(t => t.dataset.fMarque + ':' + t.dataset.fTranche + ':' + t.dataset.fDuo + ':' + t.dataset.fPhase)")
    assert compteur() == "4 modèles affichés sur 4"
    pg.fill(f"{box} .adm-f-recherche", "montblanc")                                        # insensible à la casse
    assert compteur() == "1 modèle affiché sur 4"
    pg.fill(f"{box} .adm-f-recherche", "ALFÉA") if False else pg.fill(f"{box} .adm-f-recherche", "excellià")
    assert compteur() == "1 modèle affiché sur 4"                                          # insensible aux accents
    pg.click(f"{box} .adm-f-reset")
    pg.click(f'{box} .adm-f-btn[data-f="marque"][data-v="ARISTON"]')
    pg.click(f'{box} .adm-f-btn[data-f="marque"][data-v="DAIKIN"]')
    assert sorted(v.split(":")[0] for v in visibles()) == ["ARISTON", "DAIKIN"]            # plusieurs marques
    pg.click(f'{box} .adm-f-btn[data-f="tranche"][data-v="15-16"]')
    assert len(visibles()) == 2
    pg.click(f'{box} .adm-f-btn[data-f="duo"][data-v="oui"]')
    assert visibles() == ["ARISTON:15-16:oui:tri"] and compteur() == "1 modèle affiché sur 4"
    pg.click(f'{box} .adm-f-btn[data-f="phase"][data-v="mono"]')
    assert visibles() == [] and compteur() == "0 modèle affiché sur 4"
    # conservés en revenant sur la page (même session)
    pg.reload()
    _admin(pg, "catalogue")
    assert compteur() == "0 modèle affiché sur 4"
    pg.click(f"{box} .adm-f-reset")
    assert compteur() == "4 modèles affichés sur 4"
    pg.click(f'{box} .adm-f-btn[data-f="tranche"][data-v="le6"]')
    assert [v.split(":")[0] for v in visibles()] == ["THALEOS"]
