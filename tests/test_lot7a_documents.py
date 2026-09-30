# -*- coding: utf-8 -*-
"""Lot 7a · 2, 3, 4 : mention CEE exigée par ACE (montant en chiffres = ligne « Prime CEE », raison sociale + SIRET
du sous-traitant juste après) ; ancien système de chauffage déposé, type d'application et usage dans le bloc
« Solution chauffage » du devis ET de la facture. Fiches fabriquées ici : aucune donnée réelle."""
import html
import re

import pytest
from fastapi.testclient import TestClient

import main

LEAD = {"numero": "PR-07701", "civilite": "Madame", "nom": "Controle", "prenom": "Carla", "telephone": "0611121331",
        "email": "c@x.fr", "adresse_chantier": "1 rue A", "cp_chantier": "53000", "code_postal_chantier": "53000",
        "ville_chantier": "Laval", "type_logement": "maison", "surface_logement_m2": "120", "hsp": "2,5",
        "mode_chauffage": "fioul", "ecs": "chaudiere", "type_emetteurs": "radiateurs_fonte",
        "alimentation_electrique": "monophase", "categorie": "modeste", "nombre_personnes": "4",
        "cout_energetique_mensuel_eur": "400", "cout_energie_source": "reel"}
DELEG = [{"nom": "PICOTY", "mwh_precaire": 12.5, "mwh_classique": 7.2, "actif": False},
         {"nom": "ACE", "mwh_precaire": 14, "mwh_classique": 7.5, "actif": True}]
MENTION = "« La présente offre comprend une prime de {m} € offerte par ACE ÉNERGIE (SIREN : 848 595 336) dans le cadre du dispositif des CEE »"


@pytest.fixture
def client():
    return TestClient(main.app)


def _preparer(lead=None, service="chauffage_seul", mode="sans_attente", deleg=DELEG):
    lead = dict(LEAD, **(lead or {}))
    main._atomic_write_json(main.DELEGATAIRES_PATH, deleg)
    main._atomic_write_json(main.LEADS_PATH, [lead])
    main._atomic_write_json(main._state_simulateur_path(lead["numero"]), {})
    main.save_state_simulateur_atomic(lead["numero"], {"service": service, "option": "opt1", "mode_mpr": mode})
    return lead


def _texte(brut):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", brut))).replace(" ", " ")


def _devis(client, variante="devis", **kw):
    _preparer(**kw)
    return client.get(f"/api/devis/{LEAD['numero']}/preview?variante={variante}").text


def _facture(**kw):
    _preparer(**kw)
    return main._render_facture_html(None, LEAD["numero"], "FA-2099-0001", "DE2099-0001-1", "2026-07-30")


def _ligne_cee(t):
    return re.search(r"Estimation aide Prime CEE - ([\d ]+,\d\d) €", t).group(1)


def _sous_traitant():
    admin = main._admin_payload_with_m3() if hasattr(main, "_admin_payload_with_m3") else {}
    return next((st for st in admin.get("sous_traitants", []) if st.get("actif")), {})


@pytest.mark.parametrize("quoi", ["devis", "pre_devis", "facture"])
def test_mention_ace_texte_exact_et_montant_de_la_ligne_cee(client, quoi):
    brut = _facture() if quoi == "facture" else _devis(client, quoi)
    t = _texte(brut)
    montant = _ligne_cee(t)
    assert "Mention RAI — Partenaire ACE Énergie " + MENTION.format(m=montant) in t
    assert "en lettres" not in t and "rôle actif et incitatif" not in t


def test_sous_traitant_juste_apres_la_mention(client):
    st = _sous_traitant()
    if not st.get("entreprise"):
        pytest.skip("aucun sous-traitant actif dans les paramètres par défaut")
    t = _texte(_devis(client, "devis"))
    attendu = f"dans le cadre du dispositif des CEE » Sous-traitant : {st['entreprise']} — SIRET {st.get('siret') or '—'}"
    assert attendu in t
    assert "Sous-traitant :" not in _texte(_devis(client, "pre_devis")).split("Mention RAI")[1][:400]


def test_ancienne_mention_enregistree_telle_quelle_est_remplacee():
    ancien = dict(DELEG[1], mention_titre="Mention RAI — Partenaire ACE Énergie", mention_devis=main.MENTION_ACE_AVANT_LOT7A)
    main._atomic_write_json(main.DELEGATAIRES_PATH, [DELEG[0], ancien])
    ace = next(d for d in main._read_delegataires() if d["nom"] == "ACE")
    assert ace["mention_devis"] == main.MENTION_CEE_DEFAUT["ACE"][1]
    perso = dict(ancien, mention_devis="Texte ACE à moi : {montant_cee} €")
    main._atomic_write_json(main.DELEGATAIRES_PATH, [DELEG[0], perso])
    assert next(d for d in main._read_delegataires() if d["nom"] == "ACE")["mention_devis"] == "Texte ACE à moi : {montant_cee} €"


@pytest.mark.parametrize("quoi", ["devis", "facture"])
def test_ancien_systeme_et_application_dans_la_solution_chauffage(client, quoi):
    brut = _facture() if quoi == "facture" else _devis(client, "devis")
    bloc = _texte(re.search(r'<div class="pac-heating-note">(.*?)</section>', brut, re.S).group(1))
    # Lot 7b : l'énergie écrite une seule fois ; plus de ligne « Usage » dans le bloc
    assert bloc.index("BAR-TH-171") < bloc.index("Ancien système de chauffage déposé : chaudière — énergie : fioul")
    assert "Application : moyenne ou haute température" in bloc and "Usage :" not in bloc
    assert "Dépose et évacuation de l'ancienne chaudière fioul" in _texte(brut)


def test_plancher_chauffant_basse_temperature_et_ecs(client):
    bloc = _texte(re.search(r'<div class="pac-heating-note">(.*?)</section>',
                            _facture(lead={"type_emetteurs": "plancher_chauffant", "mode_chauffage": "gaz"},
                                     service="chauffage_ecs"), re.S).group(1))
    assert "Application : basse température" in bloc and "moyenne" not in bloc
    assert "Usage :" not in bloc and "chaudière — énergie : gaz" in bloc


def test_pas_de_chaudiere_inventee_hors_fioul_gaz_charbon(client):
    brut = _devis(client, "devis", lead={"mode_chauffage": "electricite"})
    assert "Ancien système de chauffage déposé" not in brut
    assert "Dépose et évacuation des équipements remplacés - chaudière" in _texte(brut)
    assert main.lignes_solution_chauffage({"mode_chauffage": "bois"})["energie_non_mentionnee"] == "bois"
