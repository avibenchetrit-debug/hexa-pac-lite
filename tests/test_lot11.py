# -*- coding: utf-8 -*-
"""Lot 11 : facture CEE au délégataire (ACE ; MRA GROUPE / ECAIR pour PICOTY), série FA-CEE-AAAA-NNNN distincte des
factures client (FA-CEE-2026-0001 émise hors application : la suite commence à 0002), aperçu sans numéro, émission
verrouillée, suivi envoyée / payée ; mention RAI PICOTY = texte exact de l'annexe 2 du contrat ECAIR. Fiches fabriquées."""
import io
import os
import re

import pytest
from fastapi.testclient import TestClient

import main
import test_lot9 as l9
import test_lot9c_marge_facturee as l9c
from services import facture_cee as fc

NUM = l9.LEAD["numero"]
pypdf = pytest.importorskip("pypdf")

# Annexe 2 du contrat cadre ECAIR (« Texte du RAI applicable »), recopiée ici indépendamment du code ; [•] = montant
RAI_CONTRAT = ("« Prime liée à la valorisation des certificats d’économies d’énergie versée par PICOTY, société au capital social "
               "de 1 548 360,00 €, immatriculée au RCS de Guéret sous le n°777 347 386, dont le siège social est situé rue André "
               "et Guy PICOTY – BP1 23300 LA SOUTERRAINE. Représentée par ECAIR, société au capital social de 132 970,00 €, "
               "immatriculée au RCS de Bobigny sous le n° 952862670, dont le siège social est situé 5 RUE PLEYEL, 93200 "
               "SAINT-DENIS, en qualité de mandataire, pour la somme de [•] euros »")

# Cas « type GALEA » (FA-CEE-2026-0001) : ACE, très modeste, 546 MWhc précaire, prime 5 800 €, commission 1 025 €
GALEA = {"type": "acompte", "quote_part": 60, "date_facture": "2026-09-22", "ref_appel": "HXR-AAF00001-ACT",
         "ref_contrat": "HXR-CTT00001", "ref_operation": "CEEDOS45042-01", "fiche": "BAR-TH-171",
         "fiche_libelle": "Pompe à chaleur de type air/eau", "beneficiaire": "GALEA Marine",
         "adresse_travaux": "60 avenue d'Angers, 49430 Durtal", "volume_precaire_mwh": 546, "volume_classique_mwh": 0,
         "prix_precaire": 12.5, "prix_classique": 7.5, "prime_operation": 5800, "commission_operation": "", "taux_tva": 20,
         "echeance_jours": 7, "delegataire": "ACE", "option_express": False, "mention_express": "",
         "mention_solde": "Le solde de 40 % de l'opération fera l'objet d'une facture distincte à réception de l'appel à "
                          "facturation de solde.",
         "destinataire": {k: fc.FACTURATION_DEFAUT["ACE"].get(k, "") for k in fc.CHAMPS_DESTINATAIRE}}


@pytest.fixture(autouse=True)
def _donnees_restaurees():
    chemins = (main.CATALOGUE_PATH, main.PARAMETRES_ADMIN_PATH, main.LEADS_PATH, main.FACTURES_META_PATH, main.DELEGATAIRES_PATH,
               main.DEVIS_META_PATH, main.COUNTERS_PATH, main.FACTURES_CEE_META_PATH)
    sauve = {c: open(c, "rb").read() for c in chemins if os.path.exists(c)}
    counters = main._read_json(main.COUNTERS_PATH, {}) or {}
    for k in [k for k in counters if k.startswith("facture_cee_")]:
        counters.pop(k)
    main._atomic_write_json(main.COUNTERS_PATH, counters)
    main._atomic_write_json(main.FACTURES_CEE_META_PATH, {})
    yield
    for c in chemins:
        if c in sauve:
            open(c, "wb").write(sauve[c])
        elif os.path.exists(c):
            os.remove(c)


def _c(role="admin"):
    c = TestClient(main.app)
    c.cookies.update(l9._cookies(role))
    return c


def _texte(pdf: bytes) -> str:
    t = " ".join((p.extract_text() or "") for p in pypdf.PdfReader(io.BytesIO(pdf)).pages)
    return re.sub(r"[\s  ]+", " ", t)


def _emettre(c, f):
    r = c.post(f"/api/admin/facture-cee/{NUM}/emettre", json=f)
    assert r.status_code == 200, r.text
    return r.json()


# ─────────────────────────── 1. Montants : acompte 60 % type GALEA = FA-CEE-2026-0001 ───────────────────────────
def test_acompte_60_type_galea_egal_a_fa_cee_2026_0001():
    m = fc.calculer(GALEA)
    assert (m["valorisation"], m["commission_operation"]) == (6825.0, 1025.0)
    assert (m["prime_ht"], m["commission_ht"], m["tva_commission"]) == (3480.0, 615.0, 123.0)
    assert (m["total_ht"], m["total_tva"], m["total_ttc"], m["net_a_payer"]) == (4095.0, 123.0, 4218.0, 4218.0)
    l9._preparer("sans_attente")
    c = _c()
    d = _emettre(c, GALEA)
    assert d["numero_facture"] == "FA-CEE-2026-0002" and d["facture"]["net_a_payer"] == 4218.0
    t = _texte(c.get(f"/api/admin/facture-cee/{NUM}/download", params={"numero_facture": "FA-CEE-2026-0002"}).content)
    for attendu in ("FACTURE D'ACOMPTE", "N° FA-CEE-2026-0002", "ACE ENERGIE", "24 rue Marbeuf, 75008 Paris", "SIREN 848 595 336",
                    "FR68 848 595 336", "HXR-AAF00001-ACT", "Acompte de 60 % sur opération CEE", "CEEDOS45042-01",
                    "Fiche BAR-TH-171", "GALEA Marine — 60 avenue d'Angers, 49430 Durtal",
                    "546,000 MWh cumac précaire · 0,000 MWh cumac classique · Prix unitaire précaire 12,50 €/MWhc",
                    "5 800,00 €", "3 480,00 €", "Non applicable", "1 025,00 €", "615,00 €", "123,00 €", "738,00 €",
                    "4 095,00 €", "4 218,00 €", "NET À PAYER", "Exonérée", "20,00 %",
                    "BOI-TVA-BASE-10-10-40 20120912 n°10 et 20", "BOI-TVA-BASE-10-10-10-20121115 n°210",
                    "FR76 2823 3000 0177 4777 4829 976", "REVOFRP2", "FA-CEE-2026-0002 / HXR-AAF00001-ACT",
                    "7 jours à réception", "Pas d'escompte", "40 €", "D441-5",
                    "Le solde de 40 % de l'opération fera l'objet d'une facture distincte"):
        assert attendu in t, attendu


def test_solde_40():
    f = dict(GALEA, type="solde", quote_part=40, mention_solde="Solde de l'opération après la facture d'acompte FA-CEE-2026-0002.")
    m = fc.calculer(f)
    assert (m["prime_ht"], m["commission_ht"], m["tva_commission"], m["total_ttc"]) == (2320.0, 410.0, 82.0, 2812.0)
    # acompte + solde = l'opération entière
    a = fc.calculer(GALEA)
    assert a["prime_ht"] + m["prime_ht"] == 5800 and a["commission_ht"] + m["commission_ht"] == 1025
    assert fc.contexte(f, "X")["titre"] == "FACTURE DE SOLDE"
    assert fc.contexte(f, "X")["nature"].replace(chr(160), " ").startswith("Solde de 40 % sur opération CEE")


def test_preremplissage_ace_puis_solde_propose():
    l9c._facturer("sans_attente", "attente")       # devis archivé ACE (prime 5 800 €), simulateur aujourd'hui en PICOTY
    c = _c()
    j = c.get(f"/api/admin/facture-cee/{NUM}").json()
    f = j["formulaire"]
    assert j["prochain_numero"] == f"FA-CEE-{main.datetime.now(main.PARIS_TZ).year}-" + ("0002" if main.datetime.now(main.PARIS_TZ).year == 2026 else "0001")
    assert f["delegataire"] == "ACE" and f["source"] == "devis DE2099-0001-1" and f["prime_operation"] == 5800.0
    assert (f["type"], f["quote_part"]) == ("acompte", 60.0) and f["ref_contrat"] == "HXR-CTT00002"
    assert f["volume_precaire_mwh"] == 546.0 and f["volume_classique_mwh"] == 0 and f["prix_precaire"] == 14.0
    assert f["destinataire"]["raison_sociale"] == "ACE ENERGIE" and f["beneficiaire"] == "MARGE Essai"
    assert f["adresse_travaux"] == "1 rue A, 49430 Durtal"
    _emettre(c, dict(f, ref_appel="HXR-AAF00002-ACT", ref_operation="CEEDOS1-01", date_facture="2026-10-02"))
    f2 = c.get(f"/api/admin/facture-cee/{NUM}").json()["formulaire"]
    assert (f2["type"], f2["quote_part"]) == ("solde", 40.0)
    assert f2["mention_solde"] == "Solde de l'opération après la facture d'acompte FA-CEE-2026-0002."


# ─────────────────────────── 2. PICOTY : 100 % standard, 40/60 en Traitement Express, adressée à ECAIR ───────────
def test_picoty_standard_100_adresse_a_ecair():
    l9c._facturer("attente", "attente")
    c = _c()
    f = c.get(f"/api/admin/facture-cee/{NUM}").json()["formulaire"]
    assert f["delegataire"] == "PICOTY" and (f["type"], f["quote_part"]) == ("totalite", 100.0)
    assert f["quote_parts_express"] == "40/60" and f["ref_contrat"] == "Contrat de valorisation CEE ECAIR"
    assert f["destinataire"] == {"raison_sociale": "MRA GROUPE", "forme": "SAS", "nom_commercial": "ECAIR",
                                 "adresse": "5 rue Pleyel, 93200 Saint-Denis", "immatriculation": "RCS Bobigny 952 862 670",
                                 "tva": "FR59 952 862 670", "mandataire": "Mandataire de PICOTY"}
    f.update(ref_appel="APP-ECAIR-1", ref_operation="OP-1", date_facture="2026-10-02")
    m = fc.calculer(f)
    assert m["prime_ht"] == f["prime_operation"] and m["quote_part"] == 100
    d = _emettre(c, f)
    t = _texte(c.get(f"/api/admin/facture-cee/{NUM}/download", params={"numero_facture": d["numero_facture"]}).content)
    for attendu in ("MRA GROUPE", "SAS — nom commercial ECAIR", "5 rue Pleyel, 93200 Saint-Denis", "RCS Bobigny 952 862 670",
                    "FR59 952 862 670", "Mandataire de PICOTY", "Contrat de valorisation CEE ECAIR", "Totalité (100 %)",
                    "réception de la présente facture par ECAIR"):
        assert attendu in t, attendu
    assert "FACTURE D'ACOMPTE" not in t and "Traitement Express" not in t


def test_picoty_traitement_express_40_puis_60():
    assert fc.parts("40/60") == [40.0, 60.0]
    assert fc.type_et_pourcentage("40/60", []) == ("acompte", 40.0)
    assert fc.type_et_pourcentage("40/60", [{"type": "acompte", "quote_part": 40}]) == ("solde", 60.0)
    assert fc.type_et_pourcentage("100", []) == ("totalite", 100.0)
    assert fc.type_et_pourcentage("60/40", [{"type": "acompte", "quote_part": 60}]) == ("solde", 40.0)
    dest = {k: fc.FACTURATION_DEFAUT["PICOTY"].get(k, "") for k in fc.CHAMPS_DESTINATAIRE}
    f = dict(GALEA, delegataire="PICOTY", destinataire=dest, quote_part=40, option_express=True,
             mention_express=fc.FACTURATION_DEFAUT["PICOTY"]["mention_express"], mention_solde=fc.mention_solde_defaut("acompte", 40),
             prix_precaire=12.5)
    ctx = fc.contexte(f, "FA-CEE-2026-0009")
    assert "Option Traitement Express : 200 € HT par dossier, facturée par ECAIR" in ctx["notes_bas"]
    assert "Le solde de 60 % de l'opération" in ctx["notes_bas"][0].replace(chr(160), " ")
    m = fc.calculer(f)
    assert (m["prime_ht"], m["commission_ht"]) == (2320.0, 410.0)
    # l'option est informative : elle n'entre dans aucun montant
    assert fc.calculer(dict(f, option_express=False)) == m


# ─────────────────────────── 3. Mention RAI PICOTY = annexe 2 du contrat (devis, pré-devis, facture neufs) ───────
@pytest.mark.parametrize("quoi", ["devis", "pre_devis", "facture"])
def test_mention_rai_picoty_identique_au_contrat(quoi):
    import html as _h
    l9._preparer("attente")
    if quoi == "facture":
        brut = main._render_facture_html(None, NUM, "FA-2099-0001", "DE2099-0001-1", "2026-07-30")
    else:
        ctx = main._build_devis_context(None, NUM, avec_sous_traitant=(quoi == "devis"))
        ctx["pre_devis"] = quoi == "pre_devis"
        brut = main.templates.env.get_template("devis_pac.html").render(ctx)
    t = re.sub(r"\s+", " ", _h.unescape(re.sub(r"<[^>]+>", " ", brut))).replace(" ", " ")
    montant = re.search(r"Estimation aide Prime CEE - ([\d ]+,\d\d) €", t).group(1)
    assert RAI_CONTRAT.replace("[•]", montant) in t
    assert "Mention RAI — Partenaire Picoty" in t


def test_ancienne_mention_picoty_enregistree_remplacee_mention_perso_gardee():
    l9._preparer("attente")
    main._atomic_write_json(main.DELEGATAIRES_PATH, [dict(l9.DELEG[0], mention_titre="Mention RAI — Partenaire Picoty",
                                                          mention_devis=main.MENTION_PICOTY_AVANT_LOT11), l9.DELEG[1]])
    assert main._read_delegataires()[0]["mention_devis"] == RAI_CONTRAT.replace("[•]", "{montant_cee}")
    main._atomic_write_json(main.DELEGATAIRES_PATH, [dict(l9.DELEG[0], mention_devis="Texte perso {montant_cee}"), l9.DELEG[1]])
    assert main._read_delegataires()[0]["mention_devis"] == "Texte perso {montant_cee}"


# ─────────────────────────── 4. Numérotation continue, aperçu sans numéro, échec = aucun numéro ───────────────────
def test_numerotation_continue_et_apercu_sans_numero(monkeypatch):
    l9._preparer("sans_attente")
    c = _c()
    r = c.post(f"/api/admin/facture-cee/{NUM}/apercu", json=GALEA)
    assert r.status_code == 200 and r.headers["content-type"] == "application/pdf"
    t = _texte(r.content)
    assert "APERÇU — sans numéro" in t and "FA-CEE-2026-0" not in t and "N° de facture / HXR-AAF00001-ACT" in t
    assert main._read_factures_cee_meta() == {} and "facture_cee_2026" not in main._read_json(main.COUNTERS_PATH, {})
    nums = [_emettre(c, GALEA)["numero_facture"] for _ in range(2)]
    import services.pdf_chromium as pc
    monkeypatch.setattr(pc, "html_vers_pdf", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("panne")))
    with pytest.raises(RuntimeError):
        c.post(f"/api/admin/facture-cee/{NUM}/emettre", json=GALEA)
    monkeypatch.undo()
    nums.append(_emettre(c, GALEA)["numero_facture"])
    assert nums == ["FA-CEE-2026-0002", "FA-CEE-2026-0003", "FA-CEE-2026-0004"]
    # série distincte : le compteur des factures client n'a pas bougé
    assert main._read_json(main.COUNTERS_PATH, {}).get("facture_cee_2026") == 4
    assert all(r.get("verrouillee") for r in main._factures_cee(NUM))


def test_emission_refusee_sans_references():
    l9._preparer("sans_attente")
    r = _c().post(f"/api/admin/facture-cee/{NUM}/emettre", json=dict(GALEA, ref_appel="", ref_operation=""))
    assert r.status_code == 400 and "appel à facturation" in r.json()["detail"]
    assert main._read_factures_cee_meta() == {}


# ─────────────────────────── 5. Compte commercial : refusé côté serveur ───────────────────────────────────────────
def test_compte_commercial_refuse(monkeypatch):
    l9._preparer("sans_attente")
    for auth in ("0", "1"):
        monkeypatch.setenv("AUTH_ENFORCE", auth)
        c = _c("commercial")
        assert c.get(f"/api/admin/facture-cee/{NUM}").status_code == 403
        assert c.post(f"/api/admin/facture-cee/{NUM}/apercu", json=GALEA).status_code == 403
        assert c.post(f"/api/admin/facture-cee/{NUM}/emettre", json=GALEA).status_code == 403
        assert c.post(f"/api/admin/facture-cee/{NUM}/suivi", json={"numero_facture": "x", "statut": "payee"}).status_code == 403
        assert c.get(f"/api/admin/facture-cee/{NUM}/download", params={"numero_facture": "x"}).status_code == 403
    assert main._read_factures_cee_meta() == {}


# ─────────────────────────── 6. Suivi envoyée / payée, rappel à l'échéance ────────────────────────────────────────
def test_suivi_payee_et_rappel_echeance():
    l9._preparer("sans_attente")
    c = _c()
    n = _emettre(c, dict(GALEA, date_facture="2026-01-05"))["numero_facture"]
    f = c.get(f"/api/admin/facture-cee/{NUM}").json()["factures"][0]
    assert f["statut"] == "envoyee" and f["echeance"] == "2026-01-12" and f["en_retard"] is True
    pdf_avant = open(main._factures_cee(NUM)[0]["file"], "rb").read()
    assert c.post(f"/api/admin/facture-cee/{NUM}/suivi", json={"numero_facture": n, "statut": "payee"}).status_code == 400
    r = c.post(f"/api/admin/facture-cee/{NUM}/suivi", json={"numero_facture": n, "statut": "payee", "date_paiement": "2026-01-10"})
    assert r.json()["facture"]["statut"] == "payee" and r.json()["facture"]["en_retard"] is False
    assert open(main._factures_cee(NUM)[0]["file"], "rb").read() == pdf_avant          # verrouillée : PDF inchangé


# ─────────────────────────── 7. Fiche délégataire : coordonnées de facturation ───────────────────────────────────
def test_fiche_delegataire_coordonnees_par_defaut_et_conservees():
    l9._preparer("sans_attente")
    d = {x["nom"]: x for x in main._read_delegataires()}
    assert d["ACE"]["facturation"]["raison_sociale"] == "ACE ENERGIE" and d["ACE"]["facturation"]["quote_parts"] == "60/40"
    assert d["PICOTY"]["facturation"]["nom_commercial"] == "ECAIR" and d["PICOTY"]["facturation"]["quote_parts"] == "100"
    perso = dict(fc.FACTURATION_DEFAUT["ACE"], contrat="HXR-CTT00009")
    main._atomic_write_json(main.DELEGATAIRES_PATH, [l9.DELEG[0], dict(l9.DELEG[1], facturation=perso)])
    # une sauvegarde de l'admin sans les coordonnées (ancien écran) ne les efface pas
    from test_lot6b import _jeton_admin
    r = TestClient(main.app).post("/api/admin/m3", json={"delegataires": [dict(x) for x in l9.DELEG]},
                                  headers={"X-Admin-Token": _jeton_admin()})
    assert r.status_code == 200
    assert {x["nom"]: x for x in main._read_delegataires()}["ACE"]["facturation"]["contrat"] == "HXR-CTT00009"


# ─────────────────────────── 8. Écrans (vrai Chromium) ───────────────────────────────────────────────────────────
from test_lot9 import navigateur  # noqa: E402,F401
from test_fix_pdf import serveur  # noqa: E402,F401

CAPTURES = os.environ.get("LOT11_CAPTURES", "")


def _capture(pg, nom, sel=None):
    if CAPTURES:
        os.makedirs(CAPTURES, exist_ok=True)
        (pg.locator(sel) if sel else pg).screenshot(path=os.path.join(CAPTURES, nom + ".png"))


def _documents(pg):
    pg.goto(f"{pg.base}/prospect/{NUM}")
    pg.wait_for_function("document.body.dataset.prospectNumero === %r" % NUM, timeout=15000)
    pg.evaluate("window.ouvrirDocuments(%r)" % NUM)
    pg.wait_for_timeout(1500)


def test_ecran_commercial_ne_voit_pas_les_factures_delegataire(navigateur):
    l9c._facturer("sans_attente", "sans_attente")
    pg = navigateur("commercial")
    _documents(pg)
    assert not pg.is_visible("#docs-fcee-block") and "Facturer le délégataire" not in pg.evaluate("document.body.innerText")


def test_ecran_admin_facturer_le_delegataire(navigateur):
    l9c._facturer("sans_attente", "sans_attente")
    pg = navigateur("admin")
    pg.on("dialog", lambda d: d.accept())
    _documents(pg)
    pg.wait_for_selector("#docs-fcee-block", state="visible", timeout=10000)
    pg.click("#docs-fcee-title")
    _capture(pg, "documents_bloc_vide", "#documents-panel")
    pg.click("[data-fcee-ouvrir]")
    pg.wait_for_selector(".fcee-box")
    val = lambda k: pg.input_value(f'.fcee-box [data-k="{k}"]')
    assert val("type") == "acompte" and val("quote_part") == "60" and val("prime_operation") == "5800"
    assert pg.input_value('.fcee-box [data-dest="raison_sociale"]') == "ACE ENERGIE" and val("ref_contrat") == "HXR-CTT00002"
    pg.fill('.fcee-box [data-k="prix_precaire"]', "12,5")          # tarif de FA-CEE-2026-0001
    pg.fill('.fcee-box [data-k="ref_appel"]', "HXR-AAF00002-ACT")
    pg.fill('.fcee-box [data-k="ref_operation"]', "CEEDOS1-01")
    assert pg.text_content("[data-fcee-net]").replace("\u202f", " ").replace("\u00a0", " ") == "4 218,00 €"
    _capture(pg, "formulaire_ace", ".fcee-box")
    pg.click("[data-fcee-emettre]")
    pg.wait_for_selector("[data-fcee-emise]", timeout=30000)
    num = pg.text_content("[data-fcee-emise]")
    assert num.startswith("FA-CEE-") and main._factures_cee(NUM)[0]["net_a_payer"] == 4218.0
    pg.click("[data-fcee-annuler]")
    pg.wait_for_selector(f'[data-fcee-row="{num}"]')
    _capture(pg, "documents_facture_emise", "#documents-panel")
    row = f'[data-fcee-row="{num}"]'
    pg.select_option(f"{row} [data-fcee-statut]", "payee")
    pg.fill(f"{row} [data-fcee-date-paiement]", "2026-10-05")
    pg.click(f"{row} [data-fcee-suivi-ok]")
    pg.wait_for_selector(f"{row} .fcee-payee")
    assert "Payée le 05/10/2026" in pg.text_content(row)
    _capture(pg, "documents_facture_payee", "#documents-panel")


def test_ecran_rappel_impayee_a_echeance(navigateur):
    l9c._facturer("sans_attente", "sans_attente")
    _emettre(_c(), dict(GALEA, date_facture="2026-01-05"))
    pg = navigateur("admin")
    _documents(pg)
    pg.wait_for_selector("[data-fcee-retard]", state="visible", timeout=10000)      # bloc déplié d'office
    assert "Impayée — échue le 12/01/2026" in pg.text_content("#docs-fcee-list")
    _capture(pg, "documents_impayee_echue", "#documents-panel")


def test_ecran_fiche_delegataire_coordonnees(navigateur):
    l9._preparer()
    pg = navigateur("admin")
    l9._admin(pg, "cee")
    pg.evaluate("document.querySelectorAll('.adm-del-fact').forEach(d => d.open = true)")
    vals = pg.evaluate("[...document.querySelectorAll('.adm-delegataire-row')].map(r => Object.fromEntries([...r.querySelectorAll('[data-del-fact]')].map(i => [i.dataset.delFact, i.value])))")
    assert vals[0]["raison_sociale"] == "MRA GROUPE" and vals[0]["quote_parts_express"] == "40/60"
    assert vals[1]["raison_sociale"] == "ACE ENERGIE" and vals[1]["contrat"] == "HXR-CTT00002"
    for sel in ('[data-toggle-bloc="3"]', '[data-toggle-sous-bloc="3-3"]'):
        if not pg.is_visible("#adm-delegataires-list"):
            pg.click(sel)
            pg.wait_for_timeout(300)
    pg.evaluate("document.querySelectorAll('.adm-del-fact').forEach(d => d.open = true)")
    pg.locator("#adm-delegataires-list").scroll_into_view_if_needed()
    _capture(pg, "admin_delegataires", "#adm-delegataires-list")
    # enregistrer depuis l'écran : les coordonnées modifiées sont gardées
    pg.locator('.adm-delegataire-row').nth(1).locator('[data-del-fact="contrat"]').fill("HXR-CTT00077")
    pg.click("#adm-save-delegataires")
    pg.wait_for_timeout(800)
    enreg = {d["nom"]: d for d in main._read_json(main.DELEGATAIRES_PATH, [])}
    assert enreg["ACE"]["facturation"]["contrat"] == "HXR-CTT00077" and enreg["PICOTY"]["facturation"]["nom_commercial"] == "ECAIR"
    assert enreg["ACE"]["mwh_precaire"] == 14 and enreg["PICOTY"]["mwh_precaire"] == 12.5          # tarifs inchangés
