# -*- coding: utf-8 -*-
"""Lot 10 : libellé de fiche produit corrigé (« Classe énergétique chauffage 35°C / 55°C », sans « (kW) ») et ligne
« Volume CEE : X kWh cumac (précaire / classique) » sur devis, pré-devis et facture — le volume EXACT de la valorisation
(kWh cumac × bonification), aucun calcul modifié. Fiches fabriquées ici."""
import re

import pytest

import main
import test_lot7a_documents as docs
import test_lot9 as l9
from services import import_catalogue_pac
from services.service_devis import calculer_cee_bar_th_171

FAUX, JUSTE = "Classe énergétique chauffage 35°C / 55°C (kW)", "Classe énergétique chauffage 35°C / 55°C"
ABREGE = "Classe éner. chauffage 35°C / 55°C (kW)"


def _catalogue_avec_libelle_faux():
    cat = []
    for m in l9.CATALOGUE:
        specs = list(m.get("description_specs") or []) + [{"champ": FAUX, "valeur": "A+++ / A++"}]
        cat.append(dict(m, description_specs=specs))
    cat[2]["description_specs"] = [s if s["champ"] != FAUX else {"champ": ABREGE, "valeur": "A+++ / A+"} for s in cat[2]["description_specs"]]
    main._atomic_write_json(main.CATALOGUE_PATH, cat)


def test_migration_libelle_corrige_valeurs_inchangees_idempotente():
    l9._preparer()
    _catalogue_avec_libelle_faux()
    corriges = main._migrate_lot10()
    assert sorted(corriges) == sorted(m["ref"] for i, m in enumerate(l9.CATALOGUE) if i != 2)
    for m in main._read_catalogue_pac():
        champs = {s["champ"]: s["valeur"] for s in m["description_specs"]}
        assert FAUX not in champs
        if m["ref"] != l9.CATALOGUE[2]["ref"]:
            assert champs[JUSTE] == "A+++ / A++"
        else:
            assert champs[ABREGE] == "A+++ / A+"                 # libellé abrégé : signalé, pas modifié
    avant = open(main.CATALOGUE_PATH, "rb").read()
    assert main._migrate_lot10() == [] and open(main.CATALOGUE_PATH, "rb").read() == avant


def test_import_excel_ne_reintroduit_pas_le_kw():
    assert import_catalogue_pac._spec_label(FAUX) == JUSTE and import_catalogue_pac._spec_label("Techno") == "Technologie"


@pytest.mark.parametrize("ref", ["ATL-EXCELLIA-S-9", "DAI-ALTHERMA-3HHT-R32-16 TRI", "ARI-NIMBUS-NET-R32-DUO-15 TRI"])
def test_libelle_corrige_sur_un_devis(ref):
    l9._preparer()
    _catalogue_avec_libelle_faux()
    main._migrate_lot10()
    etat = main._read_json(main._state_simulateur_path(l9.LEAD["numero"]), {})
    etat.update(modele_pac_id=ref, prix_pac=None)
    main._atomic_write_json(main._state_simulateur_path(l9.LEAD["numero"]), etat)
    ctx = main._build_devis_context(None, l9.LEAD["numero"], avec_sous_traitant=True)
    t = docs._texte(main.templates.env.get_template("devis_pac.html").render(ctx))
    assert JUSTE + " A+++ / A++" in t and "(kW) A+++" not in t and FAUX not in t


CAS = [("tres_modeste", "sans_attente", "ACE", 14, "précaire"),
       ("modeste", "attente", "PICOTY", 7.2, "classique"),
       ("intermediaire", "attente", "PICOTY", 7.2, "classique")]


@pytest.mark.parametrize("categorie, mode, deleg, tarif, type_prix", CAS)
@pytest.mark.parametrize("quoi", ["devis", "pre_devis", "facture"])
def test_volume_cee_present_et_coherent(categorie, mode, deleg, tarif, type_prix, quoi):
    l9._preparer(mode)
    leads = main._read_json(main.LEADS_PATH, [])
    leads[0]["categorie"] = categorie
    main._atomic_write_json(main.LEADS_PATH, leads)
    prospect = main._lead_for_response(main._find_lead(l9.LEAD["numero"]))
    state = main._load_state_simulateur(l9.LEAD["numero"], prospect, main._read_catalogue_pac())
    admin = main._admin_payload_with_m3()
    cee = calculer_cee_bar_th_171(prospect, state, admin)
    assert cee["details"]["delegataire"] == deleg and cee["details"]["prix_unitaire"] == tarif
    calc = main.calculer_devis(prospect, state, admin, main._read_catalogue_pac())
    volume = calc["volume_cee_kwhc"]
    # le volume est exactement celui de la valorisation : valorisation ÷ tarif × 1000 (kWh cumac)
    assert abs(volume - cee["montant"] / tarif * 1000) <= 0.5
    assert calc["volume_cee_type"] == type_prix
    # prime affichée = valorisation, sauf écrêtement réglementaire (plafond des aides) : jamais au-dessus
    assert calc["montant_cee"] <= cee["montant"] + 0.01
    if quoi == "facture":
        html = main._render_facture_html(None, l9.LEAD["numero"], "FA-2099-0001", "DE2099-0001-1", "2026-07-30")
    else:
        ctx = main._build_devis_context(None, l9.LEAD["numero"], avec_sous_traitant=(quoi == "devis"))
        ctx["pre_devis"] = quoi == "pre_devis"
        html = main.templates.env.get_template("devis_pac.html").render(ctx)
    t = docs._texte(html)
    attendu = "Volume CEE : " + f"{volume:,}".replace(",", " ") + f" kWh cumac ({type_prix})"
    assert attendu in t, re.findall(r"Volume CEE[^)]*\)", t)
    assert t.index("Estimation aide Prime CEE") < t.index("Volume CEE :")
