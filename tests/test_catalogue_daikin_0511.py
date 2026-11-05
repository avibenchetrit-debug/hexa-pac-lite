# -*- coding: utf-8 -*-
"""Fiches DAIKIN du 05/11/2026 : 5 ALTHERMA 4H avec les libellés exacts de la 8 kW mono d'Avi, corrections de la 8 kW
mono, puissances de dimensionnement Keymark et températures max Daikin, référence de l'ALTHERMA 3H HT 16 mono.
Écriture unique ; prix, EPREL et agréments jamais touchés."""
import copy

from services import catalogue_daikin_0511 as d

LIBELLES_8 = ["Marque", "Gamme", "Référence", "Technologie", "Usage", "Alimentation", "Classe du régulateur (ErP)",
              "Contribution à l'efficacité saisonnière (%)", "Temp. max de départ (°C)", "Fluide frigorigène",
              "Classe énergétique chauffage 35°C / 55°C", "Puissance thermique nominale +7/35°C -7°C/55°C (kW)",
              "ETAS chauffage 35°C / 55°C (%)", "SCOP 35°C / 55°C", "COP +7°C/35°C", "Puissance appoint électrique (kW)",
              "Puissance acoustique ext. (dB(A))", "Pression sonore ext. à 5 m (dB(A))",
              "Poids module intérieur à vide (kg)", "Poids module ext. en fonction (kg)",
              "Dimensions groupe extérieur (HxLxP) (mm)", "Dimensions module intérieur (HxLxP) (mm)", "Référence EPREL",
              "Numéro d'agrément"]


def _cat():
    huit = {"ref": d.MODELE_8_MONO, "nom": "ALTHERMA 4H R290 8", "ttc": 16792.0, "achat": 7100,
            "puissance_m7_55_kw": 7.86, "puissance_m7_55_valide": True, "temp_max_depart_c": 75,
            "description_specs": [{"champ": c, "valeur": "x"} for c in LIBELLES_8]}
    huit["description_specs"][-2]["valeur"], huit["description_specs"][-1]["valeur"] = "2329484", "36-2026-000272"
    autres = [{"ref": r, "nom": r, "ttc": 13990.0, "achat": 7100, "puissance_m7_55_kw": 9.0,
               "description_specs": [{"champ": "Référence EPREL", "valeur": "EPREL-" + r},
                                     {"champ": "Numéro d'agrément", "valeur": "AGR-" + r},
                                     {"champ": "Puissance thermique 60°C / 70°C (kW)", "valeur": "ancienne"}]}
              for r in d.FICHES_4H]
    seize = {"ref": "DAI-ALTHERMA-3HHT-R32-16", "nom": "x", "ttc": 16390.0,
             "description_specs": [{"champ": "Marque", "valeur": "DAIKIN"},
                                   {"champ": "Référence", "valeur": "ETBH16E9W7 / EPRA16DW17"}]}
    autre = {"ref": "ATL-EXCELLIA-S-14", "nom": "y", "ttc": 1.0, "description_specs": [{"champ": "Marque", "valeur": "A"}]}
    return [huit, *autres, seize, autre]


def test_fiches_4h_memes_libelles_epREL_agrement_et_prix_gardes():
    cat, change = d.migrer_catalogue(_cat())
    assert change
    for m in cat[1:6]:
        assert [s["champ"] for s in m["description_specs"]] == LIBELLES_8
        v = {s["champ"]: s["valeur"] for s in m["description_specs"]}
        assert v["Référence EPREL"] == "EPREL-" + m["ref"] and v["Numéro d'agrément"] == "AGR-" + m["ref"]
        assert m["ttc"] == 13990.0 and m["achat"] == 7100
    v10t = {s["champ"]: s["valeur"] for s in cat[3]["description_specs"]}
    assert v10t["Classe du régulateur (ErP)"] == "" and v10t["Pression sonore ext. à 5 m (dB(A))"] == ""
    assert v10t["Puissance thermique nominale +7/35°C -7°C/55°C (kW)"] == "8,11 / 7,40" and v10t["Temp. max de départ (°C)"] == "70"
    v14 = {s["champ"]: s["valeur"] for s in cat[5]["description_specs"]}
    assert v14["Puissance appoint électrique (kW)"] == "9,00" and v14["Temp. max de départ (°C)"] == "75"


def test_huit_mono_trois_lignes_seulement_et_dimensionnement():
    cat, _ = d.migrer_catalogue(_cat())
    v = {s["champ"]: s["valeur"] for s in cat[0]["description_specs"]}
    assert v["Puissance thermique nominale +7/35°C -7°C/55°C (kW)"] == "7,62 / 6,60"
    assert v["Temp. max de départ (°C)"] == "70" and v["Dimensions groupe extérieur (HxLxP) (mm)"] == "1123 × 1330 × 604"
    assert v["Marque"] == "x" and v["Référence EPREL"] == "2329484" and v["Numéro d'agrément"] == "36-2026-000272"
    assert {m["ref"]: (m["puissance_m7_55_kw"], m["temp_max_depart_c"], m["puissance_m7_55_valide"]) for m in cat[:6]} == {
        r: (kw, t, True) for r, (kw, t) in d.DIMENSIONNEMENT_4H.items()}
    assert cat[0]["ttc"] == 16792.0


def test_reference_3hht_16_mono_seule_et_rien_d_autre():
    cat, _ = d.migrer_catalogue(_cat())
    assert cat[6]["description_specs"] == [{"champ": "Marque", "valeur": "DAIKIN"},
                                           {"champ": "Référence", "valeur": "ETBH16EF6V7 / EPRA16DAV37"}]
    assert cat[7] == _cat()[7]                                         # autre modèle : intact


def test_une_seule_fois_puis_les_saisies_d_avi_sont_gardees():
    cat, _ = d.migrer_catalogue(_cat())
    cat[3]["description_specs"][6]["valeur"] = "VI"                    # Avi complète une ligne vide
    cat2, change = d.migrer_catalogue(copy.deepcopy(cat))
    assert change is False and cat2 == cat
