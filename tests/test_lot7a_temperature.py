# -*- coding: utf-8 -*-
"""Lot 7a · 1 : température de base = table NF P52-612/CN du guide ACE (annexe 1), serveur ET front.
Zones A à I par département, paliers d'altitude exacts ; départements à deux zones : la plus froide, sauf le 06
(A sous 400 m, E au-dessus) ; la note de dim le dit (« département à deux zones, vérifier »)."""
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

import services.service_devis as sd

RACINE = Path(__file__).resolve().parent.parent


@pytest.mark.parametrize("cp, altitude, attendu", [
    ("06800", 20, -2),      # 06 littoral (sous 400 m) : zone A
    ("06800", 650, -13),    # 06 arrière-pays : zone E, palier 601-800 m
    ("06800", None, -8),    # 06 altitude inconnue : E (la plus froide)
    ("38000", None, -10),   # G
    ("57000", None, -15),   # I
    ("35000", None, -5),    # C
    ("75002", 450, -9),     # zone D, palier 401-600 m
    ("83000", 150, -5),     # 83 : deux zones -> C
    ("50100", None, -7),    # 50 : deux zones -> D
    ("20000", None, -2),    # Corse
    ("05100", 2500, -29),   # G, au-delà du dernier palier : dernière valeur
    ("22300", 1500, -10),   # B s'arrête à 1 400 m
])
def test_table_nf(cp, altitude, attendu):
    assert sd.temperature_base_nf(cp, altitude)["temperature"] == attendu


def test_paliers_exacts():
    assert sd.temperature_base_nf("75002", 200)["temperature"] == -7      # 0-200
    assert sd.temperature_base_nf("75002", 201)["temperature"] == -8      # 201-400
    assert sd.temperature_base_nf("75002", 400)["temperature"] == -8
    assert sd.temperature_base_nf("75002", 401)["temperature"] == -9
    assert "dernière valeur" in sd.temperature_base_nf("22300", 1500)["palier"]


def test_tous_les_departements_metropolitains_ont_une_zone():
    depts = [f"{i:02d}" for i in range(1, 96) if i != 20] + ["2A", "2B"]
    assert [d for d in depts if d not in sd.DEPT_ZONE_NF] == []


def test_note_de_dim_dit_deux_zones():
    t = sd._temperature_base_notedim({"cp_chantier": "83000", "altitude": "150"})
    assert t["zone"] == "Zone C" and t["temperature"] == -5 and t["mention_deux_zones"] == "département à deux zones, vérifier"
    assert sd._temperature_base_notedim({"cp_chantier": "38000"})["mention_deux_zones"] == ""


def _extrait_front():
    html = (RACINE / "templates" / "index.html").read_text(encoding="utf-8")
    consts = {}
    for nom in ("ZONES_TEMP_NF", "DEPT_ZONE_NF", "DEPTS_DEUX_ZONES_NF", "PALIERS_NF"):
        m = re.search(r"const " + nom + r" = (.+?);\r?\n", html)
        consts[nom] = json.loads(m.group(1))
    fn = re.search(r"(  function temperatureExterieureBase\(state\)\{.*?\n  \}\r?\n)", html, re.S).group(1)
    return html, consts, fn


def test_front_et_serveur_ont_la_meme_table():
    _, consts, _ = _extrait_front()
    assert consts["ZONES_TEMP_NF"] == sd.ZONES_TEMP_NF and consts["DEPT_ZONE_NF"] == sd.DEPT_ZONE_NF
    assert consts["DEPTS_DEUX_ZONES_NF"] == sd.DEPTS_DEUX_ZONES_NF and consts["PALIERS_NF"] == sd.PALIERS_NF


@pytest.mark.skipif(not shutil.which("node"), reason="node absent")
def test_front_calcule_comme_le_serveur():
    html, _, fn = _extrait_front()
    entetes = "\n".join(re.search(r"(const " + n + r" = .+?;)", html).group(1)
                        for n in ("ZONES_TEMP_NF", "DEPT_ZONE_NF", "DEPTS_DEUX_ZONES_NF", "PALIERS_NF", "SEUIL_06_M"))
    cas = [("06800", 20), ("06800", 650), ("06800", None), ("38000", None), ("57000", 300), ("75002", 450),
           ("83000", 150), ("05100", 2500), ("22300", 1500), ("97400", None), ("20000", 10)]
    js = entetes + "\n" + fn + "\nconst cas = " + json.dumps(cas) + ";\nconsole.log(JSON.stringify(cas.map(([cp, a]) => "\
         "temperatureExterieureBase({cp_chantier: cp, altitude: a}).temperature)));"
    sortie = subprocess.run(["node", "-e", js], capture_output=True, text=True, check=True).stdout
    assert json.loads(sortie) == [sd.temperature_base_nf(cp, a)["temperature"] for cp, a in cas]
