# -*- coding: utf-8 -*-
"""Numéros EPREL et d'agrément du 05/11/2026 : seules ces deux lignes changent, une seule fois par modèle."""
import copy

from services import catalogue_eprel_0511 as e


def _cat():
    return [{"ref": "ATL-EXCELLIA-S-9", "nom": "a", "ttc": 12990.0,
             "description_specs": [{"champ": "Marque", "valeur": "ATLANTIC"}, {"champ": "Référence EPREL", "valeur": "520556"},
                                   {"champ": "Numéro d'agrément", "valeur": "11-2026-000095"}]},
            {"ref": "DAI-ALTHERMA-4H-R290-10 TRI", "nom": "b", "ttc": 13990.0,
             "description_specs": [{"champ": "Marque", "valeur": "DAIKIN"}]},
            {"ref": "AUTRE-MODELE", "nom": "c", "ttc": 1.0, "description_specs": [{"champ": "Référence EPREL", "valeur": "x"}]}]


def test_seules_les_deux_lignes_changent_et_une_seule_fois():
    cat, change = e.migrer_catalogue(_cat())
    assert change
    assert cat[0]["description_specs"] == [{"champ": "Marque", "valeur": "ATLANTIC"},
                                           {"champ": "Référence EPREL", "valeur": "2216896"},
                                           {"champ": "Numéro d'agrément", "valeur": "11-2026-000095"}]
    assert cat[0]["ttc"] == 12990.0
    assert cat[1]["description_specs"][1:] == [{"champ": "Référence EPREL", "valeur": "2333792"},
                                               {"champ": "Numéro d'agrément", "valeur": "36-2026-000278"}]
    assert cat[2] == _cat()[2]
    cat[0]["description_specs"][1]["valeur"] = "corrigé à la main"
    cat2, change2 = e.migrer_catalogue(copy.deepcopy(cat))
    assert change2 is False and cat2 == cat


def test_tableau_complet_et_coherent():
    assert len(e.NUMEROS) == 44
    eprels = [v[0] for v in e.NUMEROS.values()]
    agrements = [v[1] for v in e.NUMEROS.values()]
    assert len(set(eprels)) == 44 and len(set(agrements)) == 44
    assert e.NUMEROS["DAI-ALTHERMA-4H-R290-8"] == ("2313553", "36-2026-000281")
