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
LIGNE = "Avance de la prime MaPrimeRénov' : <strong>"
PARENTHESE = "(remboursée au versement de la prime, après les travaux)"
MENTION = ("Démarrage sans attente</strong> : vous avancez la prime MaPrimeRénov' (<strong>{mpr} €</strong>) au démarrage du "
           "chantier. Elle vous est remboursée au versement de la prime par l'Anah, après les travaux. Le reste à charge "
           "ci-dessus tient déjà compte de cette prime.")


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
    assert f"{LIGNE}{ctx['montant_mpr_affiche']} €</strong>" in html and PARENTHESE in html
    assert MENTION.format(mpr=ctx["montant_mpr_affiche"]) in html
    assert f"Montant financé {ctx['montant_finance']}" in html
    assert "n'intègre pas MaPrimeRénov'" not in html            # l'ancienne mention contredirait le montant
    assert f"vous avancez la prime ({ctx['montant_mpr_affiche']} €), remboursée après les travaux" in html
    assert "vous démarrez sans avance" not in html and "rendue à l'accord" not in html


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
    attendu = f"{fin['libelle']}</span> · <span class=\"devis-montant-finance\">Montant financé {ctx['montant_finance']}</span> · "
    assert attendu in html and f" · {fin['duree_mois']} mois" in html
    assert (" · 0 % · 180 mois" in html) == (option == "opt2")
