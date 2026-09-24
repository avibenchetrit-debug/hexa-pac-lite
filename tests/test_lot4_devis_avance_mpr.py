# -*- coding: utf-8 -*-
"""Devis et pré-devis en « tout de suite » : retour à l'état d'avant les demandes sur l'avance
MaPrimeRénov' (Lot 5, A). « Montant total à régler » = reste à charge + prime avancée, mention
« Option retenue : démarrage sans attente — Ce montant n'intègre pas MaPrimeRénov' … », frise
« vous démarrez sans avance », pas de ligne « Avance de la prime », pas de « Montant financé ».
Conservé : le financement du devis suit l'option du simulateur (Éco-PTZ)."""
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
MENTION = ("Option retenue : démarrage sans attente</strong> — Ce montant n'intègre pas MaPrimeRénov' "
           "(<strong>{mpr} €</strong>), qui vous sera versée directement par l'Anah après travaux. Cette option, "
           "retenue à votre demande, permet un démarrage immédiat du chantier.")
RETIRES = ("Avance de la prime MaPrimeRénov'", "Montant financé", "remboursée au versement de la prime",
           "vous avancez la prime", "tient déjà compte de cette prime")


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


def test_attente_montant_a_regler_net(client):
    ctx = _devis({"mode_mpr": "attente"})
    assert "avance_mpr" not in ctx and "montant_finance" not in ctx
    html = client.get(f"/api/devis/{LEAD['numero']}/preview?variante=devis").text
    assert all(t not in html for t in RETIRES)
    assert "vous démarrez sans avance" in html


@pytest.mark.parametrize("variante", ["devis", "pre_devis"])
@pytest.mark.parametrize("fin_mpr", ["cash", "credit"])
def test_tout_de_suite_etat_d_avant(client, variante, fin_mpr):
    net = _euros(_devis({"mode_mpr": "attente"})["reste_a_charge"])
    ctx = _devis({"mode_mpr": "sans_attente", "financement_mpr": fin_mpr})
    mpr = _euros(ctx["montant_mpr_affiche"])
    assert mpr > 0
    assert _euros(ctx["reste_a_charge"]) == net + mpr            # montant à régler : prime non déduite
    base = _euros(ctx["financement_devis"]["reste_a_charge"])
    assert base == (net + mpr if fin_mpr == "credit" else net)    # base de la mensualité : inchangée
    html = client.get(f"/api/devis/{LEAD['numero']}/preview?variante={variante}").text
    assert MENTION.format(mpr=ctx["montant_mpr_affiche"]) in html
    assert "vous démarrez sans avance" in html
    assert all(t not in html for t in RETIRES)


@pytest.mark.parametrize("option, taux, duree", [("opt1", None, None), ("opt2", 0, 180)])
def test_financement_du_devis_suit_l_option_du_simulateur(client, option, taux, duree):
    ctx = _devis({"mode_mpr": "attente", "option": option})
    fin = ctx["financement_devis"]
    admin = main.load_parametres_admin().get("params_financement") or main.DEFAULT_PARAMS_FINANCEMENT
    mens, n = main.financement_net(float_value(fin["reste_a_charge"]), option, admin)   # miroir du simulateur
    assert fin["option"] == option and fin["duree_mois"] == n and round(fin["mensualite"], 2) == round(mens, 2)
    if option == "opt2":
        assert fin["taux_pct"] == taux and fin["duree_mois"] == duree and fin["premiere_echeance_jours"] is None
    html = client.get(f"/api/devis/{LEAD['numero']}/preview?variante=pre_devis").text
    assert f"{fin['libelle']}</span> · " in html and f" · {fin['duree_mois']} mois" in html
    assert (" · 0 % · 180 mois" in html) == (option == "opt2")
