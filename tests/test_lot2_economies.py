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


# ---------------------------------------------------------------- chauffage électrique (facture totale)
ELEC = dict(facture_annuelle=150 * 12, energie="electricite", ecs_chaudiere=False, personnes=4,
            service="chauffage_seul", ballon=False, scop=3.2, facture_electricite_totale=True)


def test_electrique_facture_totale_retire_les_usages_specifiques():
    r = eco.calculer_economies(ELEC, {})
    # 2 500 kWh × 0,21 € = 525 €/an (~44 €/mois) retirés avant le calcul
    assert r["hors_chauffage_annuel"] == pytest.approx(525) and r["hors_chauffage_mensuel"] == 44
    assert r["chauffage_avant"] == pytest.approx(1800 - 525)
    assert r["besoin_kwh"] == pytest.approx((1800 - 525) / 0.21, rel=1e-4)
    assert r["apres_annuel"] == pytest.approx((1800 - 525) / 3.2, abs=0.01)
    assert r["facture_annuelle"] == 1800            # le montant déclaré reste celui saisi


def test_electrique_part_retiree_plafonnee_a_50_pourcent():
    r = eco.calculer_economies(dict(ELEC, facture_annuelle=600), {})
    assert r["hors_chauffage_annuel"] == pytest.approx(300)


def test_electrique_rien_retire_hors_montant_declare():
    # estimation / DPE : pas une facture totale -> rien retiré
    assert eco.calculer_economies(dict(ELEC, facture_electricite_totale=False), {})["hors_chauffage_annuel"] == 0
    # autre énergie : l'indicateur est sans effet
    assert eco.calculer_economies(dict(REF, facture_electricite_totale=True), {})["hors_chauffage_annuel"] == 0
    assert eco.facture_electricite_totale("electricite", "reel") is True
    assert eco.facture_electricite_totale("electricite", "a_confirmer") is True
    assert eco.facture_electricite_totale("electricite", "estime") is False
    assert eco.facture_electricite_totale("fioul", "reel") is False


def test_usages_specifiques_reglables_en_admin():
    r = eco.calculer_economies(ELEC, {"usages_specifiques_kwh_an": 1000})
    assert r["hors_chauffage_annuel"] == pytest.approx(210)


# ---------------------------------------------------------------- phrases du devis
def test_phrase_aujourdhui_montant_declare_d_abord():
    r = eco.calculer_economies(REF, {})
    assert eco.phrase_aujourdhui(r, r["avant_mensuel"]) == "Aujourd'hui : 400 €/mois de fioul, dont 359 € pour le chauffage"
    duo = eco.calculer_economies(dict(REF, service="chauffage_ecs"), {})
    assert eco.phrase_aujourdhui(duo, duo["avant_mensuel"]) == ""        # rien retiré : 400 affiché tel quel
    el = eco.calculer_economies(ELEC, {})
    assert eco.phrase_aujourdhui(el, el["avant_mensuel"]) == "Aujourd'hui : 150 €/mois d'électricité, dont 106 € pour le chauffage"


@pytest.mark.parametrize("avant, apres, phrase", [
    (359, 154, "votre facture est divisée par deux"),   # -57 %
    (200, 100, "votre facture est divisée par deux"),   # -50 %
    (200, 120, "baisse de 40 %"),
    (200, 140, "baisse de 30 %"),
    (200, 150, ""),                                     # -25 % : pas de phrase
    (200, 210, ""),
])
def test_phrase_baisse_selon_la_baisse_reelle(avant, apres, phrase):
    assert eco.phrase_baisse(avant, apres) == phrase


# ---------------------------------------------------------------- projection et financement
def test_financement_net_et_projection():
    fin = main.DEFAULT_PARAMS_FINANCEMENT
    m1, n1 = eco.financement_net(3190, "opt1", fin)
    assert n1 == 156 and m1 == pytest.approx(29.33, abs=0.01)           # sous le seuil : 5,9 % / 156 mois
    assert eco.financement_net(8000, "opt1", fin)[1] == 180              # au-dessus du seuil
    assert eco.financement_net(3190, "opt2", fin) == (pytest.approx(3190 / 180), 180)   # Éco-PTZ 0 %
    assert eco.financement_net(3190, "opt3", fin) == (0.0, 0)
    r = eco.calculer_economies(REF, {})
    pr = eco.projeter(r, m1 * 12, n1 / 12, 0)
    assert pr["annee_rentable"] == 1 and round(pr["total"]) == 74085   # = simulateur (capture 02)
    comptant = eco.projeter(r, 0, 0, 3190)
    assert comptant["annee_rentable"] == 2 and comptant["total"] == pytest.approx(comptant["cumul"] - 3190)


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
    ELEC,                                                           # facture d'électricité totale
    dict(ELEC, facture_annuelle=600),                               # plafond 50 %
    dict(ELEC, ecs_chaudiere=True, service="chauffage_ecs"),        # + ECS
    dict(ELEC, facture_electricite_totale=False),                   # estimation : rien retiré
]
PARAMS_PARITE = [{}, {"rendement_pct": {"fioul": 70}, "cop_ecs_duo": 3, "prix_kwh": {"electricite": 0.25},
                      "inflation_annuelle_pct": {"fioul": 6}, "duree_vie_pac_ans": 15, "usages_specifiques_kwh_an": 1800}]
ESTIMATIONS = [(108, "H1", "1968", "fioul", True, 4), (90, "H2b", "1989-2000", "gaz", False, 2),
               (150, "H3", "après 2021", "pac", True, None), (0, "H1", "", "fioul", True, 4)]
PROJECTIONS = [(0, 0, 0), (29.33 * 12, 13, 0), (0, 0, 3190), (80 * 12, 15, 0)]

NODE_RUNNER = r"""
const fs = require('fs'), vm = require('vm');
const html = fs.readFileSync(process.argv[2], 'utf8');
const a = html.indexOf('/* HEXA-ECONOMIES:DEBUT'), b = html.indexOf('/* HEXA-ECONOMIES:FIN */');
if (a < 0 || b < 0) throw new Error('bloc HEXA-ECONOMIES introuvable');
const ctx = { window: {} }; vm.createContext(ctx); vm.runInContext(html.slice(a, b), ctx);
const E = ctx.window.HexaEconomies;
const entree = JSON.parse(fs.readFileSync(0, 'utf8'));
const calculs = entree.params.map(p => entree.cas.map(c => E.calculerEconomies(c, p)));
const out = {
  calculs,
  estimations: entree.estimations.map(e => E.estimerFactureAnnuelle(...e, {})),
  periodes: entree.periodes.map(x => E.periodeConstruction(x)),
  projections: calculs[0].filter(r => r.ok).map(r => entree.projections.map(([c, d, s]) =>
    E.projeter(r, { creditAnnuel: c, dureeCreditAns: d, debourseInitial: s }))),
  horsChauffage: [1800, 600, 0].map(x => E.horsChauffageAnnuel(x, {})),
};
process.stdout.write(JSON.stringify(out));
"""


@pytest.mark.skipif(shutil.which("node") is None, reason="node absent")
def test_parite_js_python(tmp_path):
    runner = tmp_path / "parite.js"
    runner.write_text(NODE_RUNNER, encoding="utf-8")
    html = os.path.join(os.path.dirname(__file__), "..", "templates", "index.html")
    periodes = ["1968", "avant 1948", "1948-1974", "1989-2000", "2001-2005", "après 2021", "", "inconnue"]
    entree = {"cas": CAS_PARITE, "params": PARAMS_PARITE, "estimations": [list(e) for e in ESTIMATIONS],
              "periodes": periodes, "projections": [list(x) for x in PROJECTIONS]}
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
    ok = [eco.calculer_economies(c, {}) for c in CAS_PARITE]
    ok = [r for r in ok if r["ok"]]
    for r, projs_js in zip(ok, js["projections"]):
        for (c, d, s), pj in zip(PROJECTIONS, projs_js):
            pp = eco.projeter(r, c, d, s)
            assert pj["anneeRentable"] == pp["annee_rentable"]
            assert pj["total"] == pytest.approx(pp["total"], abs=0.01)
    hors = [min(2500 * 0.21, 0.5 * x) for x in (1800, 600, 0)]
    assert js["horsChauffage"] == pytest.approx(hors)


# ---------------------------------------------------------------- zone du département (CP)
@pytest.mark.parametrize("cp, zone", [("75002", "H1"), ("13001", "H3"), ("20090", main.DEPT_ZONE["2A"]),
                                      ("20200", main.DEPT_ZONE["2B"]), ("", "")])
def test_zone_depuis_cp(cp, zone):
    assert main._zone_depuis_cp({"cp_chantier": cp}) == zone


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
    main._atomic_write_json(main._state_simulateur_path(lead["numero"]), {})   # état vierge
    main.save_state_simulateur_atomic(lead["numero"], state)


def test_devis_calcule_toujours_cote_serveur(client):
    # lead existant, simulateur jamais rouvert depuis le Lot 2 : ancienne éco dans l'état, ignorée
    _preparer(dict(LEAD, cout_energetique_mensuel_eur="400", cout_energie_source="reel"),
              {"service": "chauffage_seul", "eco_20_ans": 109662, "annee_rentable": 3})
    ctx = main._build_devis_context(None, "PR-00077")
    pa = ctx["projet_apercu"]
    assert pa is not None, ctx.get("missing")
    assert pa["facture_avant"] == 359 and pa["eco_20_ans"] not in (None, 109662)
    assert pa["eco_20_ans_fmt"] and pa["annee_rentable"] >= 1
    assert pa["mention_economies"].startswith("Estimation indicative calculée sur votre facture déclarée")
    assert pa["phrase_aujourdhui"] == "Aujourd'hui : 400 €/mois de fioul, dont 359 € pour le chauffage"
    html = client.get("/api/devis/PR-00077/preview").text
    bloc = html.split('<div class="projet-apercu">')[1].split('<div class="anah-mention-block')[0]
    assert "Vous gagnez" in bloc and "Rentabilisé en" in bloc      # on examine bien le bloc économies
    assert "—" not in bloc
    assert "Aujourd'hui : 400 €/mois de fioul, dont 359 € pour le chauffage" in html.replace("&#39;", "'")


def test_devis_accord_an_ans(client):
    _preparer(dict(LEAD, cout_energetique_mensuel_eur="400", cout_energie_source="reel"), {"service": "chauffage_seul"})
    pa = main._build_devis_context(None, "PR-00077")["projet_apercu"]
    html = client.get("/api/devis/PR-00077/preview").text
    n = pa["annee_rentable"]
    unite = "an" if n == 1 else "ans"
    assert f">{n} {unite}</div>" in html
    assert "1 ans" not in html and "1ᵉ année" not in html


def test_devis_bloc_masque_si_donnee_manquante(client):
    # énergie actuelle non reconnue (réseau de chaleur) : aucun calcul possible -> bloc entièrement
    # masqué (pas de tiret, pas de trou), devis toujours générable
    _preparer(dict(LEAD, mode_chauffage="reseau_chaleur", cout_energetique_mensuel_eur="300", cout_energie_source="reel"),
              {"service": "chauffage_seul"})
    ctx = main._build_devis_context(None, "PR-00077")
    assert ctx["projet_apercu"] is None and ctx.get("_error_template") is None
    html = client.get("/api/devis/PR-00077/preview").text
    assert '<div class="projet-apercu">' not in html


def test_devis_bloc_masque_si_non_rentable(monkeypatch):
    _preparer(dict(LEAD, cout_energetique_mensuel_eur="400", cout_energie_source="reel"), {"service": "chauffage_seul"})
    monkeypatch.setattr(main, "projeter", lambda *a, **k: {"annee_rentable": None, "total": -500, "cumul": -500})
    assert main._build_devis_context(None, "PR-00077")["projet_apercu"] is None


def test_devis_jamais_de_surcout_pendant_le_credit(client, monkeypatch):
    _preparer(dict(LEAD, cout_energetique_mensuel_eur="400", cout_energie_source="reel"),
              {"service": "chauffage_seul", "option": "opt1"})
    reel = main.calculer_financement_devis
    monkeypatch.setattr(main, "calculer_financement_devis", lambda b, a: dict(reel(b, a), mensualite=400))
    pa = main._build_devis_context(None, "PR-00077")["projet_apercu"]
    assert pa["eco_pendant"] < 0
    html = client.get("/api/devis/PR-00077/preview").text
    assert "Pendant le crédit" not in html and "Après le crédit" in html


def test_devis_sans_cout_estime_avec_la_zone_du_cp(client):
    # pas de zone dans l'état ni de coût : estimation avec la zone du département (75 -> H1)
    _preparer(dict(LEAD, annee_construction="1968"), {"service": "chauffage_seul"})
    res, source = main._economies_devis(main._lead_for_response(main._find_lead("PR-00077")),
                                        main._load_state_simulateur("PR-00077", {}, []), None,
                                        main._admin_payload_with_m3(), "")
    params = main._admin_payload_with_m3().get("params_eco_energie") or {}
    attendu_h1 = eco.estimer_facture_annuelle(108, "H1", "1968", "fioul", True, 4, params)
    assert source == "estime" and res["facture_annuelle"] == pytest.approx(attendu_h1, abs=0.01)
    pa = main._build_devis_context(None, "PR-00077")["projet_apercu"]
    assert pa is not None and "une estimation selon les caractéristiques du logement" in pa["mention_economies"]
    assert client.get("/api/devis/PR-00077/validate").json()["ok"] is True


def test_devis_electrique_facture_totale(client):
    _preparer(dict(LEAD, mode_chauffage="electricite", ecs="independant", cout_energetique_mensuel_eur="150",
                   cout_energie_source="reel"), {"service": "chauffage_seul"})
    pa = main._build_devis_context(None, "PR-00077")["projet_apercu"]
    assert pa is not None
    assert pa["phrase_aujourdhui"] == "Aujourd'hui : 150 €/mois d'électricité, dont 106 € pour le chauffage"


def test_devis_garde_fou_ne_bloque_pas(client):
    _preparer(dict(LEAD, cout_energetique_mensuel_eur="20", cout_energie_source="reel"), {"service": "chauffage_seul"})
    ctx = main._build_devis_context(None, "PR-00077")
    assert ctx.get("_error_template") is None
    assert client.get("/api/devis/PR-00077/validate").json()["ok"] is True
    assert client.get("/api/devis/PR-00077/preview").status_code == 200


# ---------------------------------------------------------------- lead jamais simulé : chauffage seul
CATALOGUE = [
    {"ref": "ATL-EXCELLIA-S-DUO-9", "nom": "ALFEA EXCELLIA S DUO 9", "puiss_chauf": 10.08, "ttc": 14990},
    {"ref": "ATL-EXCELLIA-S-9", "nom": "ALFEA EXCELLIA S 9", "puiss_chauf": 10.08, "ttc": 12990},
]


def test_lead_jamais_simule_chauffage_seul_et_modele_non_duo():
    main._atomic_write_json(main.LEADS_PATH, [dict(LEAD, alimentation_electrique="monophase")])
    main._atomic_write_json(main._state_simulateur_path("PR-00077"), {})
    state = main._load_state_simulateur("PR-00077", main._find_lead("PR-00077"), CATALOGUE)
    assert state["service"] == "chauffage_seul"                 # = DEFAULT_SIM_STATE du simulateur
    assert state["modele_pac_id"] == "ATL-EXCELLIA-S-9"          # jamais un DUO en chauffage seul


def test_modele_par_defaut_suit_le_service():
    from services.service_devis import select_default_modele
    assert select_default_modele({}, CATALOGUE)["ref"] == "ATL-EXCELLIA-S-9"
    assert select_default_modele({}, CATALOGUE, "chauffage_seul")["ref"] == "ATL-EXCELLIA-S-9"
    assert select_default_modele({}, CATALOGUE, "chauffage_ecs")["ref"] == "ATL-EXCELLIA-S-DUO-9"


def test_devis_lead_jamais_simule_ecs_non_comptee():
    _preparer(dict(LEAD, cout_energetique_mensuel_eur="400", cout_energie_source="reel"), {})
    main._atomic_write_json(main._state_simulateur_path("PR-00077"), {})   # aucun état simulateur
    pa = main._build_devis_context(None, "PR-00077")["projet_apercu"]
    assert pa is not None
    assert pa["facture_avant"] == 359                            # chauffage seul : part ECS retirée
    assert pa["phrase_aujourdhui"] == "Aujourd'hui : 400 €/mois de fioul, dont 359 € pour le chauffage"
