# -*- coding: utf-8 -*-
"""Lot 4 : devis et pré-devis en « tout de suite » (MaPrimeRénov' avancée par le client).

Même règle que le simulateur : le montant à régler est toujours le vrai reste à charge ; l'avance
de la prime est sur une ligne à part ; elle n'entre dans le montant financé que si elle est
ajoutée au crédit."""
import pytest
from fastapi.testclient import TestClient

import main
from services.service_devis import float_value

LEAD = {"numero": "PR-00088", "civilite": "Mme", "nom": "Martin", "prenom": "Léa", "telephone": "0611121315",
        "email": "l4@x.fr", "adresse_chantier": "1 rue A", "cp_chantier": "75002", "code_postal_chantier": "75002",
        "ville_chantier": "Paris", "type_logement": "maison", "surface_logement_m2": "120", "hsp": "2,5",
        "mode_chauffage": "fioul", "ecs": "chaudiere", "type_emetteurs": "radiateurs_classiques",
        "alimentation_electrique": "monophase", "categorie": "tres_modeste", "nombre_personnes": "4",
        "cout_energetique_mensuel_eur": "400", "cout_energie_source": "reel"}
LIGNE = "Avance de la prime MaPrimeRénov'"


@pytest.fixture
def client():
    return TestClient(main.app)


def _devis(state):
    main._atomic_write_json(main.LEADS_PATH, [LEAD])
    main._atomic_write_json(main._state_simulateur_path(LEAD["numero"]), {})
    main.save_state_simulateur_atomic(LEAD["numero"], dict({"service": "chauffage_seul", "option": "opt1"}, **state))
    ctx = main._build_devis_context(None, LEAD["numero"])
    assert ctx.get("_error_template") is None, ctx.get("missing")
    return ctx


def _euros(txt):
    return round(float_value(str(txt).replace("€", "").replace(" ", "").replace(",", ".")))


def test_attente_reste_net_sans_ligne_d_avance(client):
    ctx = _devis({"mode_mpr": "attente"})
    assert ctx["avance_mpr"] == ""
    assert _euros(ctx["montant_finance"]) == _euros(ctx["reste_a_charge"])
    html = client.get(f"/api/devis/{LEAD['numero']}/preview?variante=devis").text
    assert LIGNE not in html


@pytest.mark.parametrize("variante", ["devis", "pre_devis"])
def test_tout_de_suite_de_sa_poche(client, variante):
    net = _euros(_devis({"mode_mpr": "attente"})["reste_a_charge"])
    ctx = _devis({"mode_mpr": "sans_attente", "financement_mpr": "cash"})
    mpr = _euros(ctx["avance_mpr"])
    assert mpr > 0
    assert _euros(ctx["reste_a_charge"]) == net                 # le vrai reste à charge, pas reste + avance
    assert _euros(ctx["montant_finance"]) == net                # l'avance n'est pas financée
    html = client.get(f"/api/devis/{LEAD['numero']}/preview?variante={variante}").text
    assert f"{LIGNE} <span" in html and "(rendue à l'accord de l'Anah)" in html
    assert f"Montant financé {ctx['montant_finance']}" in html
    assert "n'intègre pas MaPrimeRénov'" not in html            # l'ancienne mention contredirait le montant
    assert "vous avancez la prime (" in html and "vous démarrez sans avance" not in html   # la frise aussi


def test_tout_de_suite_ajoutee_au_credit(client):
    net = _euros(_devis({"mode_mpr": "attente"})["reste_a_charge"])
    ctx = _devis({"mode_mpr": "sans_attente", "financement_mpr": "credit"})
    mpr = _euros(ctx["avance_mpr"])
    assert _euros(ctx["reste_a_charge"]) == net
    assert _euros(ctx["montant_finance"]) == net + mpr          # avance ajoutée au crédit : financée
    assert _euros(ctx["financement_devis"]["reste_a_charge"]) == net + mpr   # la mensualité suit
    html = client.get(f"/api/devis/{LEAD['numero']}/preview?variante=devis").text
    assert f"Montant financé {ctx['montant_finance']}" in html and LIGNE in html
    assert "vous démarrez sans avance" in html                   # avance financée : rien à sortir au départ
