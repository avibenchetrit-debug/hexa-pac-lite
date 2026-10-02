# -*- coding: utf-8 -*-
"""Lot 10b : les 4 libellés de fiche produit signalés au lot 10, corrigés (valeurs inchangées), dans le catalogue PAC,
dans la fiche des ballons (paramètres admin) et à l'import Excel. Migration idempotente. Fiches fabriquées ici."""
import pytest

import main
import test_lot7a_documents as docs
import test_lot9 as l9
from services import import_catalogue_pac

RENOMMES = {"Classe éner. chauffage 35°C / 55°C (kW)": "Classe énergétique chauffage 35°C / 55°C",
            "Volume ballon ECS / Profil soutirage": "Volume ballon ECS (L) / Profil soutirage",
            "Poids module ext. / int. en fonction (kg)": "Poids module ext. en fonction (kg)"}
BALLON = ("Poids à vide unité extérieure(kg)", "Poids à vide unité extérieure (kg)")


def _semer():
    l9._preparer()
    cat = main._read_catalogue_pac()
    cat[0]["description_specs"] = list(cat[0]["description_specs"]) + [
        {"champ": "Classe éner. chauffage 35°C / 55°C (kW)", "valeur": "A+++ / A++"},
        {"champ": "Volume ballon ECS / Profil soutirage", "valeur": "180 / L"},
        {"champ": "Poids module ext. / int. en fonction (kg)", "valeur": "119"}]
    main._atomic_write_json(main.CATALOGUE_PATH, cat)
    params = main.load_parametres_admin()
    params["ballon_thermo"]["modeles"][0]["description_specs"] = [{"champ": BALLON[0], "valeur": "24"},
                                                                  {"champ": "Capacité ballon (L)", "valeur": "270"}]
    main.save_parametres_admin_atomic(params)


def test_migration_catalogue_et_ballons_valeurs_inchangees_idempotente():
    _semer()
    corriges = main._migrate_lot10()
    assert l9.MODELE["ref"] in corriges and "ballon-1" in corriges
    specs = {s["champ"]: s["valeur"] for s in main._read_catalogue_pac()[0]["description_specs"]}
    assert specs == dict(specs, **{"Classe énergétique chauffage 35°C / 55°C": "A+++ / A++",
                                   "Volume ballon ECS (L) / Profil soutirage": "180 / L",
                                   "Poids module ext. en fonction (kg)": "119"})
    assert not any(k in specs for k in RENOMMES)
    b = {s["champ"]: s["valeur"] for s in main.load_parametres_admin()["ballon_thermo"]["modeles"][0]["description_specs"]}
    assert b == {BALLON[1]: "24", "Capacité ballon (L)": "270"}
    cat, adm = open(main.CATALOGUE_PATH, "rb").read(), open(main.PARAMETRES_ADMIN_PATH, "rb").read()
    assert main._migrate_lot10() == []
    assert open(main.CATALOGUE_PATH, "rb").read() == cat and open(main.PARAMETRES_ADMIN_PATH, "rb").read() == adm


@pytest.mark.parametrize("ancien, nouveau", list(RENOMMES.items()) + [BALLON])
def test_import_excel_aligne(ancien, nouveau):
    assert import_catalogue_pac._spec_label(ancien) == nouveau


def test_libelles_corriges_sur_un_devis_duo_avec_ballon():
    _semer()
    main._migrate_lot10()
    etat = main._read_json(main._state_simulateur_path(l9.LEAD["numero"]), {})
    etat.update(service="chauffage_seul", ballon_ref="ballon-1", ballon_emplacement="interieur", prix_pac=None)
    main._atomic_write_json(main._state_simulateur_path(l9.LEAD["numero"]), etat)
    ctx = main._build_devis_context(None, l9.LEAD["numero"], avec_sous_traitant=True)
    t = docs._texte(main.templates.env.get_template("devis_pac.html").render(ctx))
    for nouveau in list(RENOMMES.values()) + [BALLON[1]]:
        assert nouveau in t, nouveau
    for ancien in list(RENOMMES) + [BALLON[0]]:
        assert ancien not in t, ancien
