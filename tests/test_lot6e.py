# -*- coding: utf-8 -*-
"""Lot 6e : mention CEE du devis et du pré-devis selon le délégataire (PICOTY en attente MPR, ACE tout de suite),
texte stocké sur le délégataire (Admin), montant = ligne « Prime CEE » du devis."""
import html
import re

import pytest
from fastapi.testclient import TestClient

import main

LEAD = {"numero": "PR-06260", "civilite": "Madame", "nom": "Mention", "prenom": "Mia", "telephone": "0611121330", "email": "m@x.fr",
        "adresse_chantier": "1 rue A", "cp_chantier": "53000", "code_postal_chantier": "53000", "ville_chantier": "Laval",
        "type_logement": "maison", "surface_logement_m2": "120", "hsp": "2,5", "mode_chauffage": "fioul", "ecs": "chaudiere",
        "type_emetteurs": "radiateurs_classiques", "alimentation_electrique": "monophase", "categorie": "modeste",
        "nombre_personnes": "4", "cout_energetique_mensuel_eur": "400", "cout_energie_source": "reel"}
DELEG = [{"nom": "PICOTY", "mwh_precaire": 12.5, "mwh_classique": 7.2, "actif": False},
         {"nom": "ACE", "mwh_precaire": 14, "mwh_classique": 7.5, "actif": True}]
PICOTY = ("Prime liée à la valorisation des certificats d'économies d'énergie versée par PICOTY, société au capital social de "
          "1 548 360,00 €, immatriculée au RCS de Guéret sous le n° 777 347 386, dont le siège social est situé rue André et Guy "
          "PICOTY – BP1 23300 LA SOUTERRAINE. Représentée par ECAIR, société au capital social de 132 970,00 €, immatriculée au RCS "
          "de Bobigny sous le n° 952 862 670, dont le siège social est situé 5 rue Pleyel, 93200 SAINT-DENIS, en qualité de "
          "mandataire, pour la somme de {m} euros.")
ACE = ("« La présente offre comprend une Prime d'un montant de {l} euros, qui vous est offerte par ACE ÉNERGIE (SIREN : 848 595 336) "
       "dans le cadre de son rôle actif et incitatif, au titre du dispositif des certificats d'économies d'énergie »")


ACE_LOT7A = ("« La présente offre comprend une prime de {m} € offerte par ACE ÉNERGIE (SIREN : 848 595 336) dans le cadre "
             "du dispositif des CEE »")


@pytest.fixture
def client():
    return TestClient(main.app)


def _texte(client, mode, variante="devis", deleg=DELEG):
    main._atomic_write_json(main.DELEGATAIRES_PATH, deleg)
    main._atomic_write_json(main.LEADS_PATH, [dict(LEAD)])
    main._atomic_write_json(main._state_simulateur_path(LEAD["numero"]), {})
    main.save_state_simulateur_atomic(LEAD["numero"], {"service": "chauffage_seul", "option": "opt1", "mode_mpr": mode})
    brut = client.get(f"/api/devis/{LEAD['numero']}/preview?variante={variante}").text
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", brut)))


def _ligne_cee(t):
    return re.search(r"Estimation aide Prime CEE - ([\d  ]+,\d\d) €", t).group(1)


@pytest.mark.parametrize("variante", ["devis", "pre_devis"])
def test_attente_mention_picoty_montant_de_la_ligne_cee(client, variante):
    t = _texte(client, "attente", variante).replace(" ", " ")
    montant = _ligne_cee(t)                               # la ligne « Estimation aide Prime CEE » du devis
    assert float(montant.replace(" ", "").replace(",", ".")) > 0
    assert "Mention RAI — Partenaire Picoty " + PICOTY.format(m=montant) in t   # texte exact, même montant
    assert "Mention RAI — Partenaire Picoty" in t and "ACE ÉNERGIE" not in t


@pytest.mark.parametrize("variante", ["devis", "pre_devis"])
def test_tout_de_suite_mention_ace(client, variante):
    # Lot 7a : texte exigé par ACE, montant en chiffres = la ligne « Prime CEE » (test_lot7a_documents.py)
    t = _texte(client, "sans_attente", variante).replace(" ", " ")
    assert "Mention RAI — Partenaire ACE Énergie " + ACE_LOT7A.format(m=_ligne_cee(t)) in t
    assert "PICOTY" not in t


def test_montant_format_francais():
    assert main._montant_fr(11893.8) == "11 893,80"
    assert main._montant_fr(950) == "950,00"


def test_mention_modifiable_dans_l_admin(client):
    perso = [dict(DELEG[0], mention_titre="Mention RAI — Partenaire Picoty", mention_devis="Texte PICOTY modifié : {montant_cee} € ({montant_cee_lettres})."),
             DELEG[1]]
    t = _texte(client, "attente", deleg=perso)
    assert re.search(r"Texte PICOTY modifié : [\d  ]+,\d\d € \(\D+\)\.", t)
    lus = main._read_delegataires()
    assert lus[0]["mention_devis"].startswith("Texte PICOTY modifié")
    # délégataires sans mention enregistrée : pré-remplis pour l'admin
    main._atomic_write_json(main.DELEGATAIRES_PATH, DELEG)
    d = {x["nom"]: x for x in main._read_delegataires()}
    assert d["PICOTY"]["mention_devis"] == main.MENTION_CEE_DEFAUT["PICOTY"][1] and "{montant_cee}" in d["PICOTY"]["mention_devis"]
    assert d["ACE"]["mention_titre"] == "Mention RAI — Partenaire ACE Énergie"
