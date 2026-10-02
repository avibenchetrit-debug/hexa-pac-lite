# -*- coding: utf-8 -*-
"""Lot 11c : importer une facture délégataire déjà émise (hors CRM). PDF rangé tel quel, numéro réservé dans la série
FA-CEE (doublon refusé) sans décaler la numérotation, même suivi que les factures du CRM, et le solde du dossier reprend
ses données. Cas GALEA (FA-CEE-2026-0001) reproduit sur une fiche fabriquée."""
import json
import os

import pytest

import main
import test_lot9 as l9
import test_lot9c_marge_facturee as l9c
import test_lot11 as l11
from services import facture_cee as fc
from test_lot11 import _donnees_restaurees  # noqa: F401  (fixture autouse : données remises en l'état)

NUM = l9.LEAD["numero"]
PDF_GALEA = b"%PDF-1.4\n% facture FA-CEE-2026-0001 emise hors CRM\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"
GALEA = {"numero_facture": "FA-CEE-2026-0001", "date_facture": "2026-08-18", "delegataire": "ACE", "type": "acompte",
         "quote_part": "60", "ref_appel": "HXR-AAF00001-ACT", "ref_contrat": "HXR-CTT00001", "ref_operation": "CEEDOS45042-01",
         "beneficiaire": "GALEA Marine", "adresse_travaux": "60 avenue d'Angers, 49430 Durtal",
         "volume_precaire_mwh": "546", "volume_classique_mwh": "0", "prix_precaire": "12,50", "prix_classique": "7.5",
         "prime_ht": "3 480,00", "commission_ht": "615", "tva": "123", "total_ttc": "4218", "statut": "envoyee",
         "destinataire": {k: fc.FACTURATION_DEFAUT["ACE"].get(k, "") for k in fc.CHAMPS_DESTINATAIRE}}


def _importer(c, donnees=None, pdf=PDF_GALEA, **maj):
    d = dict(donnees or GALEA, **maj)
    return c.post(f"/api/admin/facture-cee/{NUM}/importer", data={"donnees": json.dumps(d)},
                  files={"fichier": ("facture.pdf", pdf, "application/pdf")})


def _form(c):
    return c.get(f"/api/admin/facture-cee/{NUM}").json()


def test_galea_import_puis_solde_40():
    l9c._facturer("sans_attente", "sans_attente")
    c = l11._c()
    r = _importer(c)
    assert r.status_code == 200, r.text
    assert r.json()["numero_facture"] == "FA-CEE-2026-0001" and r.json()["facture"]["importee"] is True
    # PDF rangé tel quel
    assert c.get(f"/api/admin/facture-cee/{NUM}/download", params={"numero_facture": "FA-CEE-2026-0001"}).content == PDF_GALEA
    j = _form(c)
    s = j["formulaire"]
    assert (s["type"], s["quote_part"]) == ("solde", 40.0) and s["source"] == "facture d'acompte FA-CEE-2026-0001"
    assert s["prix_precaire"] == 12.5 and s["ref_contrat"] == "HXR-CTT00001" and s["volume_precaire_mwh"] == 546.0
    assert s["ref_operation"] == "CEEDOS45042-01" and s["delegataire"] == "ACE" and s["destinataire"]["raison_sociale"] == "ACE ENERGIE"
    assert s["beneficiaire"] == "GALEA Marine" and s["mention_solde"].endswith("FA-CEE-2026-0001.")
    assert (s["prime_operation"], s["commission_operation"], s["taux_tva"]) == (5800.0, 1025.0, 20.0)
    m = fc.calculer(s)
    assert (m["prime_ht"], m["commission_ht"], m["tva_commission"], m["total_ttc"]) == (2320.0, 410.0, 82.0, 2812.0)
    # la numérotation ne bouge pas : le CRM émet ensuite la 0002
    if main.datetime.now(main.PARIS_TZ).year == 2026:
        assert j["prochain_numero"] == "FA-CEE-2026-0002"
    assert "facture_cee_2026" not in main._read_json(main.COUNTERS_PATH, {})
    s.update(ref_appel="HXR-AAF00001-ACS", date_facture="2026-10-02")
    assert l11._emettre(c, s)["numero_facture"] == "FA-CEE-2026-0002"
    t = l11._texte(c.get(f"/api/admin/facture-cee/{NUM}/download", params={"numero_facture": "FA-CEE-2026-0002"}).content)
    for attendu in ("FACTURE DE SOLDE", "Solde de 40 %", "HXR-CTT00001", "CEEDOS45042-01", "12,50 €/MWhc", "2 320,00 €",
                    "410,00 €", "82,00 €", "2 812,00 €", "après la facture d'acompte FA-CEE-2026-0001"):
        assert attendu in t, attendu


def test_doublon_refuse_et_numeros_importes_jamais_reattribues():
    l9c._facturer("sans_attente", "sans_attente")
    c = l11._c()
    assert _importer(c).status_code == 200
    r = _importer(c)
    assert r.status_code == 409 and "existe déjà" in r.json()["detail"]
    assert _importer(c, numero_facture="FA-CEE-2026-0004").status_code == 200        # réservé en avance
    f = dict(l11.GALEA)
    nums = [l11._emettre(c, f)["numero_facture"] for _ in range(3)]
    assert nums == ["FA-CEE-2026-0002", "FA-CEE-2026-0003", "FA-CEE-2026-0005"]
    assert _importer(c, numero_facture="FA-CEE-2026-0003").status_code == 409        # numéro émis par le CRM
    assert len(main._factures_cee(NUM)) == 5


def test_meme_suivi_et_rappel_d_echeance():
    l9c._facturer("sans_attente", "sans_attente")
    c = l11._c()
    _importer(c)
    f = _form(c)["factures"][0]
    assert f["statut"] == "envoyee" and f["echeance"] == "2026-08-25" and f["en_retard"] is True
    r = c.post(f"/api/admin/facture-cee/{NUM}/suivi", json={"numero_facture": "FA-CEE-2026-0001", "statut": "payee",
                                                           "date_paiement": "2026-08-24"})
    assert r.json()["facture"]["statut"] == "payee" and r.json()["facture"]["en_retard"] is False
    _importer(c, numero_facture="FA-CEE-2026-0007", statut="payee", date_paiement="2026-08-20")
    assert {x["numero_facture"]: x["statut"] for x in _form(c)["factures"]}["FA-CEE-2026-0007"] == "payee"


@pytest.mark.parametrize("maj, message", [
    ({"total_ttc": "4300"}, "Total TTC incohérent"),
    ({"numero_facture": "FA-2026-0001"}, "format FA-CEE"),
    ({"quote_part": "0"}, "quote-part"),
    ({"statut": "payee"}, "date de paiement"),
])
def test_saisies_refusees(maj, message):
    l9c._facturer("sans_attente", "sans_attente")
    r = _importer(l11._c(), **maj)
    assert r.status_code == 400 and message in r.json()["detail"]
    assert main._read_factures_cee_meta() == {}


def test_fichier_qui_n_est_pas_un_pdf_refuse():
    l9c._facturer("sans_attente", "sans_attente")
    r = _importer(l11._c(), pdf=b"<html>pas un pdf</html>")
    assert r.status_code == 400 and main._read_factures_cee_meta() == {}


def test_compte_commercial_refuse(monkeypatch):
    l9c._facturer("sans_attente", "sans_attente")
    for auth in ("0", "1"):
        monkeypatch.setenv("AUTH_ENFORCE", auth)
        assert _importer(l11._c("commercial")).status_code == 403
    assert main._read_factures_cee_meta() == {}


# ─────────────────────────── écran ───────────────────────────
from test_lot9 import navigateur  # noqa: E402,F401
from test_fix_pdf import serveur  # noqa: E402,F401


def test_ecran_importer_galea(navigateur, tmp_path):
    l9c._facturer("sans_attente", "sans_attente")
    pdf = tmp_path / "FA-CEE-2026-0001.pdf"
    pdf.write_bytes(PDF_GALEA)
    pg = navigateur("admin")
    l11._documents(pg)
    pg.wait_for_selector("#docs-fcee-block", state="visible", timeout=10000)
    pg.click("#docs-fcee-title")
    pg.click("[data-fcee-importer]")
    pg.wait_for_selector("#fcee-import-overlay .fcee-box")
    k = lambda n: f'#fcee-import-overlay [data-k="{n}"]'
    assert pg.input_value('#fcee-import-overlay [data-dest="raison_sociale"]') == "ACE ENERGIE"
    pg.set_input_files("#fcee-import-overlay [data-fcee-fichier]", str(pdf))
    for n, v in (("numero_facture", "FA-CEE-2026-0001"), ("date_facture", "2026-08-18"), ("quote_part", "60"),
                 ("ref_appel", "HXR-AAF00001-ACT"), ("ref_contrat", "HXR-CTT00001"), ("ref_operation", "CEEDOS45042-01"),
                 ("prix_precaire", "12,50"), ("prime_ht", "3480"), ("commission_ht", "615"), ("tva", "123")):
        pg.fill(k(n), v)
    assert pg.input_value(k("total_ttc")) == "4218"                    # total recalculé
    l11._capture(pg, "import_galea", "#fcee-import-overlay .fcee-box")
    pg.click("[data-fcee-importer-ok]")
    pg.wait_for_selector("[data-fcee-importee-ok]", timeout=15000)
    pg.click("#fcee-import-overlay [data-fcee-annuler]")
    pg.wait_for_selector('[data-fcee-row="FA-CEE-2026-0001"] [data-fcee-importee]')
    l11._capture(pg, "documents_importee", "#documents-panel")
    assert main._factures_cee(NUM)[0]["formulaire"]["prix_precaire"] == 12.5
    pg.click("[data-fcee-ouvrir]")                                     # le solde proposé
    pg.wait_for_selector(".fcee-box [data-fcee-net]")
    assert pg.input_value('.fcee-box [data-k="type"]') == "solde" and pg.input_value('.fcee-box [data-k="quote_part"]') == "40"
    assert pg.text_content("[data-fcee-net]").replace(" ", " ").replace(" ", " ") == "2 812,00 €"
    l11._capture(pg, "solde_galea", ".fcee-box")
