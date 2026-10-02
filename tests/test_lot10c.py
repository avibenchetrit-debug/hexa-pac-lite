# -*- coding: utf-8 -*-
"""Lot 10c : groupes extérieurs des Ariston Nimbus Compact (DUO) — poids du module extérieur et dimensions du groupe,
corrigés d'après la doc Ariston « Doc Pro Nimbus Plus Net R32 » (mêmes groupes 80 / 120 / 150 S NET). Migration
idempotente, import Excel aligné ; une valeur ressaisie ensuite n'est jamais réécrasée."""
import copy

import main
import test_lot9 as l9
from services import import_catalogue_pac as imp

POIDS, DIM = imp.POIDS_EXT, imp.DIM_EXT


def _duo(ref, poids, dims="1106 x 1016 x 380"):
    specs = [{"champ": "Marque", "valeur": "ARISTON"}, {"champ": "Puissance acoustique int. / ext. (dBA)", "valeur": "41 / 57"}]
    if poids is not None:
        specs.append({"champ": POIDS, "valeur": poids})
    specs += [{"champ": DIM, "valeur": dims}, {"champ": "Dimensions module intérieur (HxLxP) (mm)", "valeur": "1818 x 600 x 612"},
              {"champ": "Référence EPREL", "valeur": "123"}]
    return dict(l9.MODELE, ref=ref, description_specs=specs)


CATALOGUE = [_duo("ARI-NIMBUS-NET-R32-DUO-8", "83"), _duo("ARI-NIMBUS-NET-R32-DUO-12", "83"), _duo("ARI-NIMBUS-NET-R32-DUO-15", "119"),
             _duo("ARI-NIMBUS-NET-R32-DUO-12 TRI", None), _duo("ARI-NIMBUS-NET-R32-DUO-15 TRI", "83")]
ATTENDU = {"ARI-NIMBUS-NET-R32-DUO-8": ("83", "1106 x 1016 x 380"), "ARI-NIMBUS-NET-R32-DUO-12": ("111", "1506 x 1016 x 380"),
           "ARI-NIMBUS-NET-R32-DUO-15": ("119", "1506 x 1016 x 380"), "ARI-NIMBUS-NET-R32-DUO-12 TRI": ("111", "1506 x 1016 x 380"),
           "ARI-NIMBUS-NET-R32-DUO-15 TRI": ("119", "1506 x 1016 x 380")}


def _valeurs(m):
    s = {x["champ"]: x["valeur"] for x in m["description_specs"]}
    return s.get(POIDS), s.get(DIM)


def test_migration_valeurs_de_la_doc_ariston_idempotente():
    l9._preparer()
    main._atomic_write_json(main.CATALOGUE_PATH, copy.deepcopy(CATALOGUE))
    corriges = main._migrate_lot10c()
    assert sorted(corriges) == sorted(r for r in ATTENDU if r != "ARI-NIMBUS-NET-R32-DUO-8")
    cat = {m["ref"]: m for m in main._read_catalogue_pac()}
    for ref, attendu in ATTENDU.items():
        assert _valeurs(cat[ref]) == attendu, ref
    # ligne insérée au même endroit que chez les autres DUO (juste avant les dimensions du groupe extérieur)
    champs = [x["champ"] for x in cat["ARI-NIMBUS-NET-R32-DUO-12 TRI"]["description_specs"]]
    assert champs.index(POIDS) + 1 == champs.index(DIM) and len(champs) == 6
    avant = open(main.CATALOGUE_PATH, "rb").read()
    assert main._migrate_lot10c() == [] and open(main.CATALOGUE_PATH, "rb").read() == avant


def test_valeur_ressaisie_jamais_reecrasee():
    m = copy.deepcopy(_duo("ARI-NIMBUS-NET-R32-DUO-12", "110", "1500 x 1016 x 380"))
    assert imp.corriger_groupes_exterieurs_ariston(m) is False and _valeurs(m) == ("110", "1500 x 1016 x 380")


def test_autres_modeles_jamais_touches():
    m = copy.deepcopy(dict(_duo("ARI-NIMBUS-NET-R32-12", "83"), ref="ARI-NIMBUS-NET-R32-12"))
    assert imp.corriger_groupes_exterieurs_ariston(m) is False


def test_import_excel_aligne():
    """L'import applique la même correction (le fichier fournisseur porte encore les anciennes valeurs)."""
    m = copy.deepcopy(_duo("ARI-NIMBUS-NET-R32-DUO-15 TRI", "83"))
    assert imp.corriger_groupes_exterieurs_ariston(m) is True and _valeurs(m) == ("119", "1506 x 1016 x 380")
    src = open(imp.__file__, encoding="utf-8").read()
    assert "corriger_groupes_exterieurs_ariston(model)" in src.split("def _parse_sheet")[1]
    assert "Doc Pro Nimbus Plus Net R32" in src
