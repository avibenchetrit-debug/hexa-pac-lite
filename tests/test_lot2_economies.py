# -*- coding: utf-8 -*-
"""Lot 2 : calcul des économies (services/economies.py) et parité avec le JS du simulateur.

Cas de référence : SCOP forcé à 3,2, hypothèses admin par défaut.
La parité rejoue les mêmes entrées sur le bloc HEXA-ECONOMIES de templates/index.html (Node) :
le simulateur et le devis donnent donc les mêmes chiffres."""
import json
import os
import shutil
import subprocess

import pytest
from fastapi.testclient import TestClient

import main
from services import economies as eco

REF = dict(facture_annuelle=400 * 12, energie="fioul", ecs_chaudiere=True, personnes=4,
           service="chauffage_seul", ballon=False, scop=3.2)


def proche(valeur, attendu, tol=0.03):
    return abs(valeur - attendu) <= abs(attendu) * tol


# ---------------------------------------------------------------- cas de référence
def test_reference_fioul_400_euros_4_personnes():
    r = eco.calculer_economies(REF, {})
    assert r["ok"]
    assert proche(r["ecs_avant"], 489)
    assert proche(r["chauffage_avant"], 4311)
    assert proche(r["besoin_kwh"], 28190)
    assert proche(r["chauffage_apres"], 1850)
    assert proche(r["apres_mensuel"], 154)
    # sans ECS traitée, « Aujourd'hui » = facture chauffage seule (part ECS retirée)
    assert r["ecs_traitee"] is False and r["economie_ecs"] == 0
    assert r["avant_mensuel"] == round(r["chauffage_avant"] / 12)


def test_meme_cas_en_duo_economie_ecs_calculee():
    r = eco.calculer_economies(dict(REF, service="chauffage_ecs"), {})
    assert r["ecs_traitee"] is True
    # ECS actuelle = part fioul (489 €) ; après = 4 × 800 / 2,5 × 0,21 = 268,80 €
    assert proche(r["ecs_actuelle"], 489) and proche(r["ecs_apres"], 268.8, 0.001)
    assert r["economie_ecs"] > 0
    assert proche(r["economie_ecs"] / 12, (489.41 - 268.8) / 12, 0.01)   # ≈ 18 €/mois, plus 25 € fixes
    assert r["avant_annuel"] == pytest.approx(REF["facture_annuelle"], abs=0.01)


def test_fioul_et_ballon_electrique_separe():
    r = eco.calculer_economies(dict(REF, ecs_chaudiere=False), {})
    assert r["ecs_avant"] == 0
    assert r["chauffage_avant"] == pytest.approx(4800)
    assert proche(r["besoin_kwh"], 4800 / 0.13 * 0.85)


def test_chauffage_seul_avec_ballon_thermo_utilise_le_cop_cet():
    r = eco.calculer_economies(dict(REF, ballon=True), {})
    assert r["ecs_traitee"] is True
    assert r["ecs_apres"] == pytest.approx(4 * 800 / 2.8 * 0.21, abs=0.01)
    # chauffage + ECS « DUO » : le ballon est ignoré
    duo = eco.calculer_economies(dict(REF, service="chauffage_ecs", ballon=True), {})
    assert duo["ecs_apres"] == pytest.approx(4 * 800 / 2.5 * 0.21, abs=0.01)


def test_part_ecs_plafonnee_a_30_pourcent():
    r = eco.calculer_economies(dict(REF, facture_annuelle=1000), {})
    assert r["ecs_avant"] == pytest.approx(300)


def test_garde_fou_alerte_sans_bloquer():
    # bois bon marché + SCOP faible : la PAC coûte plus que l'existant -> alerte
    r = eco.calculer_economies(dict(REF, facture_annuelle=1000, energie="bois", scop=2.0), {})
    assert r["ok"] and r["alerte"] is True and r["apres_annuel"] > r["avant_annuel"]
    assert eco.calculer_economies(REF, {})["alerte"] is False


def test_pas_de_valeur_inventee():
    assert eco.calculer_economies(dict(REF, facture_annuelle=0), {}) == {"ok": False, "raison": "facture"}
    assert eco.calculer_economies(dict(REF, energie=""), {}) == {"ok": False, "raison": "energie"}
    assert eco.estimer_facture_annuelle(0, "H1", "1968", "fioul", True, 4, {}) is None


def test_pac_existante_rendement_250():
    r = eco.calculer_economies(dict(REF, energie="pac", ecs_chaudiere=False, facture_annuelle=1200), {})
    assert r["besoin_kwh"] == pytest.approx(1200 / 0.21 * 2.5, rel=1e-3)


# ---------------------------------------------------------------- estimation et périodes
@pytest.mark.parametrize("annee, cle", [
    ("1968", "avant_1975"), ("1974", "avant_1975"), ("1975", "1975_2000"), ("2000", "1975_2000"),
    ("2001", "apres_2000"), ("avant 1948", "avant_1975"), ("1948-1974", "avant_1975"),
    ("1989-2000", "1975_2000"), ("2001-2005", "apres_2000"), ("après 2021", "apres_2000"), ("", "inconnue"),
])
def test_periode_construction(annee, cle):
    assert eco.periode_construction(annee) == cle


def test_estimation_sans_facture():
    # 108 m² chauffés (120 m² habitables), H1, 1968 : 108 × 150 × 1,3 / 0,85 × 0,13 + 4 × 800 / 0,85 × 0,13
    attendu = 108 * 150 * 1.3 / 0.85 * 0.13 + 4 * 800 / 0.85 * 0.13
    assert eco.estimer_facture_annuelle(108, "H1", "1968", "fioul", True, 4, {}) == pytest.approx(attendu, abs=0.01)
    sans_ecs = eco.estimer_facture_annuelle(108, "H1", "1968", "fioul", False, 4, {})
    assert sans_ecs == pytest.approx(108 * 150 * 1.3 / 0.85 * 0.13, abs=0.01)


def test_hypotheses_admin_prises_en_compte():
    p = {"rendement_pct": {"fioul": 70}, "cop_ecs_duo": 3, "prix_kwh": {"electricite": 0.25}}
    r = eco.calculer_economies(dict(REF, service="chauffage_ecs"), p)
    assert r["besoin_kwh"] == pytest.approx((4800 - min(3200 / 0.7 * 0.13, 1440)) / 0.13 * 0.7, rel=1e-3)
    assert r["ecs_apres"] == pytest.approx(3200 / 3 * 0.25, abs=0.01)


def test_defauts_identiques_partout():
    assert {k: main.DEFAULT_PARAMS_ECO_ENERGIE[k] for k in eco.DEFAULT_PARAMS} == eco.DEFAULT_PARAMS


# ---------------------------------------------------------------- sources et mention
def test_source_effective_et_mention():
    assert eco.source_effective("", True) == "a_confirmer"      # lead antérieur au Lot 2
    assert eco.source_effective("", False) == ""
    assert eco.source_effective("dpe", True) == "dpe"
    r = eco.calculer_economies(REF, {})
    assert eco.mention_devis("reel", r) == (
        "Estimation indicative calculée sur votre facture déclarée, prix de l'énergie actuels + hausse "
        "de 4 %/an, SCOP 3,2. Les économies réelles dépendent de l'usage et du climat.")
    assert "les informations communiquées" in eco.mention_devis("a_confirmer", r)
    assert "les données théoriques du DPE" in eco.mention_devis("dpe", r)
    assert "une estimation selon les caractéristiques du logement" in eco.mention_devis("estime", r)


# ---------------------------------------------------------------- parité JS / Python
CAS_PARITE = [
    REF,
    dict(REF, service="chauffage_ecs"),
    dict(REF, ecs_chaudiere=False),
    dict(REF, ballon=True),
    dict(REF, facture_annuelle=1000),
    dict(REF, energie="gaz", facture_annuelle=1800, personnes=None, scop=None),
    dict(REF, energie="pac", facture_annuelle=1200, ecs_chaudiere=False),
    dict(REF, energie="bois", facture_annuelle=2100, personnes=3, scop=4.1, service="chauffage_ecs"),
    dict(REF, energie="electricite", facture_annuelle=2500, ecs_chaudiere=True, personnes=1),
    dict(REF, facture_annuelle=300, energie="gaz", scop=2.0),
]
PARAMS_PARITE = [{}, {"rendement_pct": {"fioul": 70}, "cop_ecs_duo": 3, "prix_kwh": {"electricite": 0.25},
                      "inflation_annuelle_pct": {"fioul": 6}, "duree_vie_pac_ans": 15}]
ESTIMATIONS = [(108, "H1", "1968", "fioul", True, 4), (90, "H2b", "1989-2000", "gaz", False, 2),
               (150, "H3", "après 2021", "pac", True, None), (0, "H1", "", "fioul", True, 4)]

NODE_RUNNER = r"""
const fs = require('fs'), vm = require('vm');
const html = fs.readFileSync(process.argv[2], 'utf8');
const a = html.indexOf('/* HEXA-ECONOMIES:DEBUT'), b = html.indexOf('/* HEXA-ECONOMIES:FIN */');
if (a < 0 || b < 0) throw new Error('bloc HEXA-ECONOMIES introuvable');
const ctx = { window: {} }; vm.createContext(ctx); vm.runInContext(html.slice(a, b), ctx);
const E = ctx.window.HexaEconomies;
const entree = JSON.parse(fs.readFileSync(0, 'utf8'));
const out = {
  calculs: entree.params.map(p => entree.cas.map(c => E.calculerEconomies(c, p))),
  estimations: entree.estimations.map(e => E.estimerFactureAnnuelle(...e, {})),
  periodes: entree.periodes.map(x => E.periodeConstruction(x)),
};
process.stdout.write(JSON.stringify(out));
"""


@pytest.mark.skipif(shutil.which("node") is None, reason="node absent")
def test_parite_js_python(tmp_path):
    runner = tmp_path / "parite.js"
    runner.write_text(NODE_RUNNER, encoding="utf-8")
    html = os.path.join(os.path.dirname(__file__), "..", "templates", "index.html")
    periodes = ["1968", "avant 1948", "1948-1974", "1989-2000", "2001-2005", "après 2021", "", "inconnue"]
    entree = {"cas": CAS_PARITE, "params": PARAMS_PARITE, "estimations": [list(e) for e in ESTIMATIONS], "periodes": periodes}
    res = subprocess.run(["node", str(runner), html], input=json.dumps(entree), capture_output=True,
                         text=True, encoding="utf-8", check=True)
    js = json.loads(res.stdout)
    for pi, p in enumerate(PARAMS_PARITE):
        for ci, cas in enumerate(CAS_PARITE):
            py = eco.calculer_economies(cas, p)
            j = js["calculs"][pi][ci]
            assert set(py) == set(j), (cas, set(py) ^ set(j))
            for k, v in py.items():
                if isinstance(v, float):
                    assert j[k] == pytest.approx(v, abs=0.011), (k, cas, p)
                else:
                    assert j[k] == v, (k, cas, p)
    assert js["estimations"] == [pytest.approx(eco.estimer_facture_annuelle(*e, {}), abs=0.011)
                                 if eco.estimer_facture_annuelle(*e, {}) is not None else None for e in ESTIMATIONS]
    assert js["periodes"] == [eco.periode_construction(x) for x in periodes]


# ---------------------------------------------------------------- devis
@pytest.fixture
def client():
    return TestClient(main.app)


LEAD = {"numero": "PR-00077", "civilite": "Mme", "nom": "Martin", "prenom": "Léa", "telephone": "0611121314",
        "email": "l@x.fr", "adresse_chantier": "1 rue A", "cp_chantier": "75002", "code_postal_chantier": "75002",
        "ville_chantier": "Paris", "type_logement": "maison", "surface_logement_m2": "120", "hsp": "2,5",
        "mode_chauffage": "fioul", "ecs": "chaudiere", "type_emetteurs": "radiateurs_classiques",
        "alimentation_electrique": "monophase", "categorie": "tres_modeste", "nombre_personnes": "4"}


def _preparer(lead, state):
    main._atomic_write_json(main.LEADS_PATH, [lead])
    main.save_state_simulateur_atomic(lead["numero"], state)


def test_devis_reprend_le_calcul_et_la_mention(client):
    _preparer(dict(LEAD, cout_energetique_mensuel_eur="400", cout_energie_source="reel"),
              {"service": "chauffage_seul", "eco_calc_version": 2, "eco_20_ans": 31000, "annee_rentable": 4})
    ctx = main._build_devis_context(None, "PR-00077")
    pa = ctx["projet_apercu"]
    assert pa is not None, ctx.get("missing")
    assert ctx["economie_devis"]["facture_avant_mois"] == 359
    assert pa["facture_avant"] == 359
    assert pa["mention_economies"].startswith("Estimation indicative calculée sur votre facture déclarée")
    assert pa["eco_20_ans_fmt"] == "31 000"
    html = client.get("/api/devis/PR-00077/preview").text
    assert "Estimation indicative calculée sur votre facture déclarée" in html


def test_devis_ignore_une_eco_calculee_avant_le_lot_2():
    _preparer(dict(LEAD, cout_energetique_mensuel_eur="400"),
              {"service": "chauffage_seul", "eco_20_ans": 60000, "annee_rentable": 3, "eco_calc_version": ""})
    pa = main._build_devis_context(None, "PR-00077")["projet_apercu"]
    assert pa["eco_20_ans_fmt"] is None and pa["annee_rentable"] is None
    assert "les informations communiquées" in pa["mention_economies"]   # coût sans source -> à confirmer


def test_devis_sans_cout_estime_et_reste_generable(client):
    _preparer(dict(LEAD, annee_construction="1968"), {"service": "chauffage_seul"})
    pa = main._build_devis_context(None, "PR-00077")["projet_apercu"]
    assert pa is not None and "une estimation selon les caractéristiques du logement" in pa["mention_economies"]
    assert client.get("/api/devis/PR-00077/validate").json()["ok"] is True


def test_devis_garde_fou_ne_bloque_pas(client):
    _preparer(dict(LEAD, cout_energetique_mensuel_eur="20", cout_energie_source="reel"), {"service": "chauffage_seul"})
    ctx = main._build_devis_context(None, "PR-00077")
    assert ctx.get("_error_template") is None
    assert client.get("/api/devis/PR-00077/validate").json()["ok"] is True
    assert client.get("/api/devis/PR-00077/preview").status_code == 200
