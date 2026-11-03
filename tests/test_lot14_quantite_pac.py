# -*- coding: utf-8 -*-
"""Lot 14 : quantité de PAC (1 ou 2, 2 = montées en cascade) à l'étape Proposition.
Quantité 1 : documents identiques, caractère pour caractère, à ceux du code d'avant le lot 14 (photos de référence
tests/fixtures/lot14_*.html, prises avec le code d'avant). Quantité 2 : fourniture × 2, pose cascade et travaux induits
réglables dans l'Admin, aides (CEE, MaPrimeRénov') comptées UNE fois, phrase cascade dans le document.
Régénérer les photos (code d'avant seulement) : HEXA_LOT14_PHOTOS=1 pytest tests/test_lot14_quantite_pac.py -k photo"""
import os
import re

import pytest
from fastapi.testclient import TestClient

from services.service_devis import number_fr

import main

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")
NUM = "PR-14001"
LEAD = {"numero": NUM, "civilite": "Monsieur", "nom": "Cascade", "prenom": "Romaric", "telephone": "0611140011",
        "email": "romaric@example.invalid", "adresse_chantier": "1 rue A", "cp_chantier": "49800",
        "code_postal_chantier": "49800", "ville_chantier": "Trélazé", "type_logement": "maison",
        "surface_logement_m2": "280", "hsp": "2,5", "mode_chauffage": "fioul", "ecs": "chaudiere",
        "type_emetteurs": "radiateurs_classiques", "alimentation_electrique": "monophase", "categorie": "modeste",
        "nombre_personnes": "4", "cout_energetique_mensuel_eur": "268", "cout_energie_source": "reel",
        "vt_validee": True}
MODELE = "ATL-EXCELLIA-S-DUO-12"
STATE = {"service": "chauffage_ecs", "option": "opt1", "modele_pac_id": MODELE, "modele_pac": MODELE,
         "mode_mpr": "attente"}


@pytest.fixture(autouse=True)
def _donnees_restaurees():
    chemins = (main.LEADS_PATH, main.PARAMETRES_ADMIN_PATH, main._state_simulateur_path(NUM))
    sauve = {c: open(c, "rb").read() for c in chemins if os.path.exists(c)}
    absents = [c for c in chemins if not os.path.exists(c)]
    yield
    for c, octets in sauve.items():
        open(c, "wb").write(octets)
    for c in absents:
        if os.path.exists(c):
            os.remove(c)


@pytest.fixture
def client():
    return TestClient(main.app)


def _preparer(**state):
    main._atomic_write_json(main.LEADS_PATH, [dict(LEAD)])
    main._atomic_write_json(main._state_simulateur_path(NUM), {})
    modele = main.find_modele(main._read_catalogue_pac(), MODELE)
    main.save_state_simulateur_atomic(NUM, dict(STATE, **dict({"prix_pac": modele["ttc"]}, **state)))
    return modele


def _normaliser(html):
    """Seuls les éléments qui changent d'un jour ou d'un test à l'autre sont neutralisés : dates, n° de dossier."""
    html = re.sub(r"\b\d{2}/\d{2}/\d{4}\b", "JJ/MM/AAAA", html)
    return re.sub(r"\bHX\d{2}-\d{4}\b", "HXAA-NNNN", html)


def _photo(nom):
    return os.path.join(FIXTURES, f"lot14_{nom}.html")


# ---------- quantité 1 : rien ne change ----------

@pytest.mark.parametrize("variante", ["pre_devis", "devis"])
@pytest.mark.parametrize("quantite", [None, 1])
def test_photo_quantite_1_document_identique_a_avant(client, variante, quantite):
    _preparer(**({} if quantite is None else {"quantite_pac": quantite}))
    html = _normaliser(client.get(f"/api/devis/{NUM}/preview?variante={variante}").text)
    if os.environ.get("HEXA_LOT14_PHOTOS") == "1" and quantite is None:
        os.makedirs(FIXTURES, exist_ok=True)
        open(_photo(variante), "w", encoding="utf-8", newline="").write(html)
    assert html.replace("\r\n", "\n") == open(_photo(variante), encoding="utf-8").read().replace("\r\n", "\n")


# ---------- 1. réglages Admin ----------

def test_reglages_cascade_par_defaut_sans_toucher_aux_valeurs_1_pac():
    main._atomic_write_json(main.PARAMETRES_ADMIN_PATH, {
        "params": {"pose": 3000, "acc": 550},
        "prix_vente_devis": {"prix_pose_ht": 3920, "prix_travaux_induits_ht": 2100, "description_pose_defaut": "Texte"}})
    a = main.load_parametres_admin()
    assert a["params"]["pose"] == 3000 and a["params"]["acc"] == 550 and a["params"]["pose_cascade"] == 5000
    pv = a["prix_vente_devis"]
    assert (pv["prix_pose_ht"], pv["prix_travaux_induits_ht"]) == (3920, 2100)
    assert (pv["prix_pose_cascade_ht"], pv["travaux_induits_cascade"]) == (6500, 1)
    assert pv["description_pose_defaut"] == "Texte"


def test_enregistrer_les_prix_de_vente_garde_les_autres_cles(monkeypatch, client):
    main._atomic_write_json(main.PARAMETRES_ADMIN_PATH, {
        "prix_vente_devis": {"prix_pose_ht": 3920, "prix_travaux_induits_ht": 2100, "description_pose_defaut": "Texte"}})
    monkeypatch.setattr(main, "_require_admin", lambda request: None)
    r = client.post("/api/admin/params", json={"prix_vente_devis": {
        "prix_pose_ht": 3920, "prix_travaux_induits_ht": 2100, "prix_pose_cascade_ht": 7000, "travaux_induits_cascade": 2}})
    assert r.status_code == 200
    pv = main.load_parametres_admin()["prix_vente_devis"]
    assert (pv["prix_pose_cascade_ht"], pv["travaux_induits_cascade"], pv["description_pose_defaut"]) == (7000, 2, "Texte")


def test_ecran_admin_champs_cascade():
    html = open(os.path.join(os.path.dirname(main.__file__), "templates", "index.html"), encoding="utf-8").read()
    assert 'id="adm-prix-vente-pose-cascade-ht"' in html and 'id="adm-travaux-induits-cascade"' in html
    assert "'pose_cascade', fmtE(p.pose_cascade ?? 5000)" in html


# ---------- 2. calcul : fourniture × 2, pose cascade, travaux induits × 1 / × 2, aides une fois, marge ----------

ADMIN_PROD = {"params": {"pose": 3000, "pose_cascade": 5000, "acc": 550, "tva": 0.055, "lead": 30, "conv": 0.025,
                         "vt1": 200, "cofrac1": 226, "urba1": 100, "frais_ecair_pct": 15},
              "prix_vente_devis": {"prix_pose_ht": 3920, "prix_travaux_induits_ht": 2100,
                                   "prix_pose_cascade_ht": 6500, "travaux_induits_cascade": 1}}
PRIX_1 = 17097.0                                          # ALFÉA EXCELLIA S DUO 12 au catalogue de prod


def _calcul(quantite, travaux_induits=1, prix=None):
    admin_prod = dict(ADMIN_PROD, prix_vente_devis=dict(ADMIN_PROD["prix_vente_devis"],
                                                        travaux_induits_cascade=travaux_induits))
    main._atomic_write_json(main.PARAMETRES_ADMIN_PATH, admin_prod)
    admin = main._admin_payload_with_m3()
    prix = prix if prix is not None else main.prix_defaut_pac(PRIX_1, quantite, admin)
    _preparer(quantite_pac=quantite, prix_pac=prix)
    p = main._lead_for_response(main._find_lead(NUM))
    cat = main._read_catalogue_pac()
    st = main._load_state_simulateur(NUM, p, cat)
    return main.calculer_devis(p, st, admin, cat), admin


# 2 × EXCELLIA DUO 12 : 30 564,80 € / 32 780,30 € au centime (chiffrage validé), arrondis à l'euro comme tous les prix
# TTC du simulateur : 30 565 € / 32 780 €. Fourniture déduite côté TTC : (prix − pose TTC − travaux induits TTC) ÷ 2.
@pytest.mark.parametrize("ti, attendu", [(1, 30565.0), (2, 32780.0)])
def test_prix_defaut_2_pac(ti, attendu):
    c, _ = _calcul(2, ti)
    assert c["total_ttc"] == attendu and c["quantite_pac"] == 2
    unitaire_ttc = round((attendu - 6857.50 - 2215.50 * ti) / 2, 2)               # 10 746,00 / 10 745,75
    assert c["prix_fourniture_unitaire_ht"] == round(unitaire_ttc / 1.055, 2)
    assert c["prix_fourniture_ht"] == round(c["prix_fourniture_unitaire_ht"] * 2, 2)
    assert c["prix_fourniture_ttc"] == round(unitaire_ttc * 2, 2) and c["qt_fourniture"] == "2 u."
    assert c["prix_pose_ht"] == 6500 and c["qt_pose"] == "1 forfait"
    assert c["prix_travaux_induits_unitaire_ht"] == 2100 and c["prix_travaux_induits_ht"] == 2100 * ti
    assert c["qt_travaux_induits"] == ("1 forfait" if ti == 1 else "2 forfaits")
    assert round(c["prix_fourniture_ttc"] + c["prix_pose_ttc"] + c["prix_travaux_induits_ttc"], 2) == attendu
    assert c["total_ht"] == round(c["prix_fourniture_ht"] + 6500 + 2100 * ti, 2)          # lignes HT = total HT


def test_quantite_1_calcul_inchange():
    c, admin = _calcul(1)
    assert main.prix_defaut_pac(PRIX_1, 1, admin) == PRIX_1
    assert (c["total_ttc"], c["prix_fourniture_ht"], c["prix_fourniture_unitaire_ht"]) == (PRIX_1, 10185.69, 10185.69)
    assert (c["qt_fourniture"], c["qt_pose"], c["qt_travaux_induits"]) == ("1 u.", "1 u.", "1 forfait")
    assert (c["prix_pose_ht"], c["prix_travaux_induits_ht"]) == (3920, 2100)


@pytest.mark.parametrize("categorie", ["tres_modeste", "modeste", "intermediaire", "superieur"])
def test_aides_comptees_une_seule_fois(categorie):
    global LEAD
    garde = LEAD
    LEAD = dict(LEAD, categorie=categorie)
    try:
        un, _ = _calcul(1)
        deux, _ = _calcul(2)
    finally:
        LEAD = garde
    assert (deux["montant_cee"], deux["montant_mpr"]) == (un["montant_cee"], un["montant_mpr"])
    assert deux["reste_a_charge"] == round(deux["total_ttc"] - deux["montant_cee"] - deux["montant_mpr"], 2)


def test_prix_saisi_a_la_main_ecart_sur_la_fourniture():
    c, _ = _calcul(2, prix=29000.0)
    unitaire_ttc = round((29000 - round(6500 * 1.055, 2) - round(2100 * 1.055, 2)) / 2, 2)      # 9 963,50
    assert c["total_ttc"] == 29000.0 and c["prix_fourniture_ttc"] == round(2 * unitaire_ttc, 2)
    assert c["prix_fourniture_unitaire_ht"] == round(unitaire_ttc / 1.055, 2)
    assert c["total_ht"] == round(c["prix_fourniture_ht"] + 6500 + 2100, 2)
    assert c["total_tva"] == round(29000 - c["total_ht"], 2)


@pytest.mark.parametrize("valeur", [0, 3, "x", None, ""])
def test_quantite_invalide_vaut_1(valeur):
    assert main.quantite_pac({"quantite_pac": valeur}) == 1
    assert main.quantite_pac({}) == 1 and main.quantite_pac({"quantite_pac": "2"}) == 2


@pytest.mark.parametrize("ti, ht, brute, nette", [(1, 28971.38, 11507.38, 9781.38), (2, 31071.38, 13607.38, 11881.38)])
def test_marge_du_dossier_2_pac(ti, ht, brute, nette):
    from services.marges import marge_dossier
    m = marge_dossier({"recap_total_ht": ht, "quantite_pac": 2}, {"achat": 5682}, None, ADMIN_PROD["params"], "tout_de_suite")
    assert (m["achat"], m["pose_acc"], m["frais_dossier"], m["acquisition"]) == (11364, 6100, 526, 1200)
    assert round(m["marge_brute"], 2) == brute and round(m["marge_nette"], 2) == nette


def test_marge_du_dossier_1_pac_inchangee():
    from services.marges import marge_dossier
    m = marge_dossier({"recap_total_ht": 16205.69}, {"achat": 5682}, None, ADMIN_PROD["params"], "tout_de_suite")
    assert (m["achat"], m["pose_acc"]) == (5682, 3550)
    assert round(m["marge_brute"], 2) == 6973.69 and round(m["marge_nette"], 2) == 5247.69


# ---------- 3. documents : titre, encadré cascade, prix unitaire, note de dimensionnement ----------

PHRASE = ("Installation de 2 pompes à chaleur montées en cascade, pilotées par une régulation commune, dimensionnées "
          "pour couvrir l'ensemble des besoins de chauffage du logement.")
NB = " "                                                   # espaces des montants ramen\u00e9s \u00e0 une espace simple


def _esp(texte):
    return re.sub("[\u00a0\u202f]", " ", texte)


@pytest.mark.parametrize("variante", ["pre_devis", "devis"])
def test_document_2_pac(client, variante):
    _calcul(2)
    html = client.get(f"/api/devis/{NUM}/preview?variante={variante}").text
    titre = re.search(r'<div class="lot-title">(.*?)</div>', html).group(1)
    assert titre.endswith(" · 2 unités en cascade")
    assert html.count(PHRASE) == 1 and html.count("data-cascade") == 1
    assert html.index(PHRASE) > html.index('<div class="lot-title">') and html.index(PHRASE) < html.index(">Fourniture<")
    fourniture = _esp(re.search(r'<span class="sub-line-name">Fourniture</span>(.*?)</div>', html).group(1))
    assert f'sub-line-qt">2 u.<' in fourniture
    assert f'sub-line-pu">10{NB}185,78 €<' in fourniture and f'sub-line-total">21{NB}492,00 €<' in fourniture   # 30 565 €
    assert html.count('<div class="pac-desc-title">') == 1                       # le modèle n'est décrit qu'une fois


def test_document_2_pac_travaux_induits_x2(client):
    _calcul(2, travaux_induits=2)
    html = client.get(f"/api/devis/{NUM}/preview?variante=devis").text
    ti = _esp(re.search(r'<span class="sub-line-name">Travaux induits</span>(.*?)</div>', html).group(1))
    assert 'sub-line-qt">2 forfaits<' in ti and f'sub-line-pu">2{NB}100,00 €<' in ti and f'sub-line-total">4{NB}431,00 €<' in ti


def test_document_2_pac_aides_identiques_a_1_pac(client):
    _calcul(1)
    un = client.get(f"/api/devis/{NUM}/preview?variante=devis").text
    _calcul(2)
    deux = client.get(f"/api/devis/{NUM}/preview?variante=devis").text
    aide = lambda h, lib: re.search(lib + r"[^<]*</span><span class=\"amount\">([^<]*)<", h).group(1)
    for lib in ("Estimation aide Prime CEE", "Estimation aide MaPrimeRénov'[^<]*"):
        assert aide(un, lib) == aide(deux, lib)


def test_note_de_dimensionnement_puissance_totale():
    _calcul(2)
    p = main._lead_for_response(main._find_lead(NUM))
    cat = main._read_catalogue_pac()
    nd = main.calculer_notedim(p, main._load_state_simulateur(NUM, p, cat), cat)
    kw = main.find_modele(cat, MODELE)["puiss_chauf"]
    assert nd["quantite_pac"] == 2 and nd["puissance_totale_kw"] == kw * 2
    assert nd["modele_pac_specs"].startswith(f"2 × {number_fr(kw, 1)} kW = {number_fr(kw * 2, 1)} kW · ")
    assert nd["modele_pac"].startswith("2 × ") and nd["modele_pac"].endswith(" (en cascade)")
    _calcul(1)
    nd1 = main.calculer_notedim(p, main._load_state_simulateur(NUM, p, cat), cat)
    assert nd1["modele_pac_specs"].startswith(f"{number_fr(kw, 1)} kW · ") and " × " not in nd1["modele_pac"]


def test_prix_defaut_au_centime_puis_a_l_euro():
    _calcul(1)
    admin = dict(ADMIN_PROD)
    # au centime : 2 × 10 745,90 + 6 857,50 + 2 215,50 = 30 564,80 -> 30 565 € (demi vers le haut, comme Math.round)
    assert main.prix_defaut_pac(PRIX_1, 2, admin) == 30565.0
    assert main.prix_defaut_pac(PRIX_1, 1, admin) == PRIX_1


# ---------- la quantité survit à l'envoi : document archivé avec la cascade, état inchangé ----------

def test_envoi_2_pac_document_archive_avec_la_cascade(monkeypatch, client):
    import sys
    import types
    chemins = (main.DEVIS_META_PATH, main.DEVIS_ENVOYES_PATH, main.NOTES_PATH)
    sauve = {c: open(c, "rb").read() for c in chemins if os.path.exists(c)}
    envois = []
    faux = types.ModuleType("resend")
    faux.Emails = types.SimpleNamespace(send=lambda msg: envois.append(msg) or {"id": f"factice-{len(envois)}"})
    monkeypatch.setitem(sys.modules, "resend", faux)
    monkeypatch.setenv("RESEND_API_KEY", "cle-factice-locale")
    monkeypatch.setattr(main, "_html_to_pdf_playwright", lambda html, request=None: b"%PDF-1.4")
    monkeypatch.setattr(main, "_lead_numero_dossier", lambda numero: "HX26-9999")
    try:
        main._atomic_write_json(main.DEVIS_META_PATH, {})
        _calcul(2)
        r = client.post(f"/api/devis/{NUM}/send", json={"variante": "pre_devis", "auteur": "Test"})
        assert r.status_code == 200, r.text
        item = main._read_devis_meta()[NUM][-1]
        archive = open(item["html_file"], encoding="utf-8").read()
        assert PHRASE in archive and "· 2 unités en cascade" in archive
        assert main.load_state_simulateur(NUM)["quantite_pac"] == 2
        assert envois and envois[0]["to"] == [LEAD["email"]]
    finally:
        for c, octets in sauve.items():
            open(c, "wb").write(octets)
