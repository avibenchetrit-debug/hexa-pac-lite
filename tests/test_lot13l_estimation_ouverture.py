# -*- coding: utf-8 -*-
"""Lot 13l : à l'ouverture d'une fiche, une facture ESTIMÉE (source « estime ») est recalculée avec les hypothèses
du jour (cas BUISARD : 318 €/mois enregistrés avant le lot 13k). Une facture réelle, saisie à la main, à confirmer,
issue du DPE ou d'un audit n'est jamais touchée. Vrai Chromium, aucun service extérieur."""
import time

import pytest

import main
from tests.test_dpe_front import page, serveur, val  # noqa: F401 — fixtures partagées (serveur local + connexion)

LEAD = {"numero": "PR-91301", "civilite": "Monsieur", "nom": "Estime", "prenom": "Gérard", "telephone": "0600000131",
        "adresse_chantier": "12 RUE IMAGINAIRE", "code_postal_chantier": "75002", "ville_chantier": "PARIS",
        "type_logement": "maison", "surface_logement_m2": "170", "annee_construction": "1966", "mode_chauffage": "gaz",
        "ecs": "chaudiere", "nombre_personnes": "2", "cout_energetique_mensuel_eur": "318"}


def _ouvrir(pg, **champs):
    main._atomic_write_json(main.LEADS_PATH, [dict(LEAD, **champs)])
    pg.goto(pg.base + "/prospect/" + LEAD["numero"])
    pg.wait_for_function("document.body.dataset.prospectNumero === 'PR-91301' && typeof window.hexaCoutEstimationAnnuelle === 'function'"
                         " && document.querySelector('#form-prospect [name=surface_logement_m2]').value === '170'"
                         " && document.querySelector('#form-prospect [name=mode_chauffage]').value === 'gaz'")


def test_facture_estimee_recalculee_a_l_ouverture(page):
    _ouvrir(page, cout_energie_source="estime")
    attendu = str(round(page.evaluate("window.hexaCoutEstimationAnnuelle()") / 12))
    assert attendu != "318"                                   # l'ancienne estimation (rendement compté deux fois)
    page.wait_for_function(f"document.querySelector('#form-prospect [name=cout_energetique_mensuel_eur]').value === '{attendu}'",
                           timeout=10000)
    assert val(page, "cout_energie_source") == "estime"


@pytest.mark.parametrize("source", ["reel", "a_confirmer", "dpe", "audit"])
def test_facture_non_estimee_jamais_touchee(page, source):
    _ouvrir(page, cout_energie_source=source)
    time.sleep(1.5)                                           # bien au-delà du délai de l'estimation (250 ms)
    assert val(page, "cout_energetique_mensuel_eur") == "318" and val(page, "cout_energie_source") == source


def test_facture_sans_source_jamais_touchee(page):
    _ouvrir(page)                                             # fiche d'avant le Lot 2 : montant tapé à la main
    time.sleep(1.5)
    assert val(page, "cout_energetique_mensuel_eur") == "318" and val(page, "cout_energie_source") == "a_confirmer"


def test_estimation_deja_a_jour_rien_n_est_reecrit(page):
    _ouvrir(page, cout_energie_source="estime")
    attendu = str(round(page.evaluate("window.hexaCoutEstimationAnnuelle()") / 12))
    _ouvrir(page, cout_energie_source="estime", cout_energetique_mensuel_eur=attendu)
    page.evaluate("""() => { window.__ecritures = 0; const el = document.querySelector('#form-prospect [name=cout_energetique_mensuel_eur]');
                            el.addEventListener('change', () => window.__ecritures++); }""")
    time.sleep(1.5)
    assert val(page, "cout_energetique_mensuel_eur") == attendu and page.evaluate("window.__ecritures") == 0
