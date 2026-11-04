# -*- coding: utf-8 -*-
"""Lot B (notedim-master) — la note de pac-lite = le document du Master (gabarit de la note GIBLAIN), avec le bon
modèle, la quantité et la puissance totale ; onglet « Note de dimensionnement » dans la fenêtre du document, dès le
pré-devis ; PDF ; envoi avec le pré-devis (voir aussi test_lot13h_envois)."""
import itertools
import json
import os
import re

import pytest
from fastapi.testclient import TestClient

import main
from services import note_dim_master, service_devis
from tests.test_notedim_a_cascade import (ALTHERMA_18, CATALOGUE, ETAT_GESLOT, NUM, _donnees_restaurees,  # noqa: F401
                                          _ouvrir_etape6, _preparer, navigateur, serveur)

SECTIONS_MASTER = ("Données du logement", "Paramètres de calcul retenus", "Calcul des déperditions et de la puissance",
                   "Puissance de pompe à chaleur requise", "Plage de cohérence", "Sous-dimensionnement",
                   "Dimensionnement cohérent", "Surdimensionnement", "Méthode, portée et références",
                   "Points de vigilance", "Bénéficiaire et chantier", "Note technique de dimensionnement")


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("AUTH_ENFORCE", "0")
    return TestClient(main.app)


def _cascade_altherma():
    _preparer(dict(ETAT_GESLOT, modele_pac_id=ALTHERMA_18 + " TRI", quantite_pac=2, prix_pac=33000,
                   user_modified_price=True))


def test_calcul_identique_a_calculer_notedim():
    """Le calcul imprimé par le gabarit du Master = celui de pac-lite, au watt près, sur une grille de cas."""
    lead = {"code_postal_chantier": "49800", "cp_chantier": "49800", "altitude": "28", "surface_logement_m2": "140"}
    for cp, alt, toit, mur, men, sc, hsp, service in itertools.product(
            ("49800", "57340", "05000", "13001"), ("28", "650"), ("tres_bien", "isole", "non"), ("bien", "peu"),
            ("double", "simple"), (0, 245), ("2,5", "3,1"), ("chauffage_seul", "chauffage_ecs")):
        p = dict(lead, code_postal_chantier=cp, cp_chantier=cp, altitude=alt, hsp=hsp)
        st = {"iso_toit": toit, "iso_mur": mur, "iso_menuiserie": men, "surface_chauffee": sc, "service": service}
        c = note_dim_master.calcul_paclite(p, st)
        ref = service_devis.calculer_notedim(p, st, CATALOGUE)
        assert service_devis.number_fr(c["p_pac_recommandee_kw"], 1) == ref["p_pac_reco_kw"]
        assert service_devis._fmt_fr_num(c["p_pac_recommandee_w"]) == ref["p_pac_reco_w"]
        assert service_devis._fmt_fr_num(c["p_chauffage_w"]) == ref["p_chauffage"]


def test_note_pre_dimensionnement_document_du_master_avec_la_cascade(client):
    _cascade_altherma()
    html = client.get(f"/api/notedim/{NUM}/preview").text                 # avant la VT : visible
    assert "NOTE DE PRÉ-DIMENSIONNEMENT" in html and "Estimation — à confirmer" in html
    for s in SECTIONS_MASTER:
        assert s.upper() in html.upper(), s
    assert "Travaux d'isolation pris en compte" not in html and "Déperditions du logement, poste par poste" not in html
    import html as _html
    texte = re.sub(r"\s+", " ", _html.unescape(re.sub(r"<[^>]+>", " ", html))).replace(" ", " ").replace(" ", " ")
    assert "33,4 kW" in texte or "33,4 kW" in texte.replace(" kW", " kW")
    assert "Plage de cohérence : 20 à 43,4 kW à −7 °C / 55 °C" in texte.replace("\xa0", " ")
    assert "2 × ALTHERMA 3H HT R32 18 TRI (en cascade)" in texte
    assert "2 × 18 kW = 36 kW" in texte and "108 % · cohérent" in texte
    assert "Puissance à 35 °C, valeur à −7 °C / 55 °C non renseignée." in texte
    # correctifs du 04/11 : catégorie Supérieur -> pas de MPR ; maison de 1968 -> pas de badge RT 2012 / RE 2020 ;
    # surface chauffée (245 m², celle du calcul) d'abord, surface habitable (280 m²) en second
    assert "Document justificatif du dispositif BAR-TH-171 ." in texte and "MPR" not in texte
    assert "RT 2012" not in texte and "SAS HEXA RÉNOV'" in texte
    assert "Surface chauffée 245 m² sur 280 m² habitables" in texte
    assert "@media screen" in html and "width: 210mm" in html                     # page A4 centrée à l'écran


def test_note_definitive_apres_la_vt(client):
    _cascade_altherma()
    leads = main._read_leads()
    leads[0]["vt_validee"] = True
    main._atomic_write_json(main.LEADS_PATH, leads)
    html = client.get(f"/api/notedim/{NUM}/preview").text
    assert "NOTE DE DIMENSIONNEMENT" in html and "NOTE DE PRÉ-DIMENSIONNEMENT" not in html
    assert "Visite technique réalisée" in html


def test_onglet_note_dans_la_fenetre_du_pre_devis_et_pdf(navigateur):
    pg = navigateur
    _ouvrir_etape6(pg, dict(ETAT_GESLOT, modele_pac_id=ALTHERMA_18 + " TRI", quantite_pac=2))
    pg.click("#btn-voir-devis")
    pg.wait_for_selector("#devis-tab-notedim")
    assert pg.inner_text("#devis-tab-notedim") == "📐 Note de dimensionnement"
    pg.click("#devis-tab-notedim")
    pg.wait_for_function("document.querySelector('#devis-preview-frame').src.includes('/api/notedim/')")
    assert pg.inner_text("#devis-note-definitive") == "NOTE DE PRÉ-DIMENSIONNEMENT — envoyée avec le pré-devis"
    frame = pg.frame_locator("#devis-preview-frame")
    frame.locator("#nd-inst-modele").wait_for()
    assert frame.locator("#nd-inst-modele").inner_text() == "2 × ALTHERMA 3H HT R32 18 TRI (en cascade)"
    assert frame.locator(".doc-title").inner_text() == "NOTE DE PRÉ-DIMENSIONNEMENT"
    with pg.expect_download(timeout=90000) as dl:
        pg.click("#devis-pdf-btn")
    chemin = dl.value.path()
    assert open(chemin, "rb").read(5) == b"%PDF-" and dl.value.suggested_filename.startswith("Note-pre-dimensionnement")
    assert pg.erreurs_js == []


@pytest.mark.parametrize("categorie, avec_mpr", [("superieur", False), ("intermediaire", True), ("modeste", True),
                                                 ("tres_modeste", True)])
def test_mention_mpr_selon_la_categorie(client, categorie, avec_mpr):
    _cascade_altherma()
    leads = main._read_leads()
    leads[0]["categorie"] = categorie
    main._atomic_write_json(main.LEADS_PATH, leads)
    import html as _html
    texte = _html.unescape(re.sub(r"<[^>]+>", " ", client.get(f"/api/notedim/{NUM}/preview").text))
    assert ("BAR-TH-171 + MPR Mono-Geste" in texte) is avec_mpr


@pytest.mark.parametrize("annee, avec_rt", [("1700", False), ("1968", False), ("2012", False), ("2013", True),
                                            ("2021", True), ("", False)])
def test_badge_rt2012_seulement_apres_2012(annee, avec_rt):
    assert ("RT 2012 / RE 2020" in note_dim_master.badges_reglementaires({"annee_construction": annee})) is avec_rt
