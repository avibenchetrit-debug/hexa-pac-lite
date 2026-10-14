# -*- coding: utf-8 -*-
"""Lot 13 : classe DPE estimée (services/dpe_estime.py), valeur verte (services/valeur_verte.py),
parité avec les blocs JS de la fiche et 3 tuiles du pré-devis / devis."""
import json
import os
import shutil
import subprocess

import pytest
from fastapi.testclient import TestClient

import main
from services import dpe_estime, economies as eco, valeur_verte as vv

GAZ = dict(facture_annuelle=1800, energie="gaz", ecs_chaudiere=True, personnes=3, service="chauffage_seul",
           ballon=False, scop=3.8)


# ---------------------------------------------------------------- seuils DPE, double critère
@pytest.mark.parametrize("ep, co2, attendu", [(70, 6, "A"), (71, 6, "B"), (110, 30, "C"), (250, 5, "D"),
                                             (100, 60, "E"), (421, 1, "G"), (60, 101, "G"), (180, 50, "D")])
def test_classe_retient_la_pire_des_deux(ep, co2, attendu):
    assert dpe_estime.classe(ep, co2, {}) == attendu


def test_seuils_de_l_admin():
    p = {"dpe_seuils_ep": {"A": 100}}
    assert dpe_estime.classe(90, 1, p) == "A" and dpe_estime.classe(90, 1, {}) == "B"


def test_estimation_gaz_avant_apres():
    r = eco.calculer_economies(GAZ, {})
    e = dpe_estime.estimer(r, 100, 3, True, {})
    # avant : 1800 € / 0,12 €/kWh = 15 000 kWh de gaz -> 150 kWh/m² et 34 kg CO2/m² -> classe D
    assert e["ep_avant"] == pytest.approx(150, abs=0.1) and e["co2_avant"] == pytest.approx(34.1, abs=0.1)
    assert e["classe_avant"] == "D"
    # après : électricité PAC (besoin / SCOP) + ECS restée au gaz
    assert e["classe_apres"] in "ABC" and e["gain"] >= 1


def test_vrai_dpe_classe_plus_gain_sans_depasser_a():
    est = {"ok": True, "classe_avant": "E", "classe_apres": "B", "gain": 3}
    assert dpe_estime.classes_projet("F", est) == {"ok": True, "classe_avant": "F", "classe_apres": "C", "dpe_reel": True}
    assert dpe_estime.classes_projet("B", est)["classe_apres"] == "A"
    # sans DPE : gain plafonné à 2 classes (E -> B estimé devient E -> C) ; vrai DPE : pas de plafond (F -> C)
    assert dpe_estime.classes_projet("", est) == {"ok": True, "classe_avant": "E", "classe_apres": "C", "dpe_reel": False}
    est2 = {"ok": True, "classe_avant": "G", "classe_apres": "F", "gain": 1}
    assert dpe_estime.classes_projet("", est2)["classe_apres"] == "F"                 # sous le plafond : inchangé


@pytest.mark.parametrize("choix, dpe_connu, attendu", [("F", "", "F"), ("aucun", "F", ""), ("", "e", "E"),
                                                       ("", "", ""), ("", "AB", "")])
def test_classe_reelle(choix, dpe_connu, attendu):
    assert dpe_estime.classe_reelle(choix, dpe_connu) == attendu


# ---------------------------------------------------------------- valeur verte
def test_table_des_ecarts_versionnee():
    t = vv.table()
    assert t["france"]["maison"]["F"] == -13.0 and t["departements"]["72"]["maison"]["F"] == -21.6
    assert "D" not in t["france"]["maison"]


def test_une_seule_source_departement_si_les_deux_classes_y_sont():
    fr = vv.table()["france"]["maison"]
    ec, src = vv.ecarts(vv.table(), "72", "maison", "F", "C")         # Sarthe : F et C présents
    assert src == "departement" and (ec["F"], ec["C"], ec["D"]) == (-21.6, 6.9, 0)
    ec, src = vv.ecarts(vv.table(), "72", "maison", "F", "D")         # D = 0 partout : Sarthe
    assert src == "departement" and ec["F"] == -21.6
    ec, src = vv.ecarts(vv.table(), "72", "maison", "G", "F")         # G absent en Sarthe -> France pour les DEUX
    assert src == "france" and (ec["G"], ec["F"]) == (fr["G"], fr["F"])


def _projet_force(monkeypatch, avant, apres, cp, type_logement="maison", valeur=200000):
    """Classes forcées (estimation remplacée) : seul le choix des écarts est testé."""
    monkeypatch.setattr(dpe_estime, "estimer", lambda *a, **k: {"ok": True, "classe_avant": avant,
                                                                 "classe_apres": apres, "gain": 1})
    entree = dict(valeur_bien=valeur, classe_dpe_avant="aucun", cp=cp, type_logement=type_logement, surface=100)
    return vv.projet(entree, {"ok": True}, {})


def test_sarthe_g_vers_f_positif(monkeypatch):
    r = _projet_force(monkeypatch, "G", "F", "72300")
    assert r["ok"] and r["valeur"] > 0 and r["min"] > 0                 # France : −13,0 − (−16,4) = +3,4 %
    assert r["valeur"] == 6800 and r["ecart_avant"] == -16.4 and r["ecart_apres"] == -13.0
    assert r["source_ecarts"] == "france" and r["libelle_ecarts"] == "Source : France entière"


def test_sarthe_f_vers_c_source_departement(monkeypatch):
    # vrai DPE F + gain estimé de 3 classes : pas de plafond -> F -> C
    monkeypatch.setattr(dpe_estime, "estimer", lambda *a, **k: {"ok": True, "classe_avant": "E",
                                                                 "classe_apres": "B", "gain": 3})
    r = vv.projet(dict(valeur_bien=200000, classe_dpe_avant="F", cp="72300", type_logement="maison", surface=100),
                  {"ok": True}, {})
    assert (r["classe_avant"], r["classe_apres"], r["dpe_reel"]) == ("F", "C", True)
    assert r["source_ecarts"] == "departement" and r["libelle_ecarts"] == "Source : département 72"
    assert r["valeur"] == 57000                                        # 200 000 × (6,9 + 21,6) %


def test_sans_dpe_gain_plafonne_a_deux_classes(monkeypatch):
    r = _projet_force(monkeypatch, "F", "C", "72300")                  # estimé F -> C : plafonné à F -> D
    assert (r["classe_avant"], r["classe_apres"], r["dpe_reel"]) == ("F", "D", False)
    assert r["libelle_classes"] == "Classe F → D" and r["valeur"] == 43200   # 200 000 × 21,6 % (Sarthe)


def test_garde_fou_jamais_negative_bascule_france(monkeypatch):
    # Bouches-du-Rhône, appartement : F = +2,4 %, D = 0 -> −2,4 % ; France : F = −6,5 % -> +6,5 %
    r = _projet_force(monkeypatch, "F", "D", "13001", "appartement")
    assert r["ok"] and r["valeur"] == 13000 and r["source_ecarts"] == "france"
    # France aussi négative (appartement G -> F : −6,5 − (−5,7)) : pas de valeur verte
    r = _projet_force(monkeypatch, "G", "F", "97411", "appartement")   # pas de données : France
    assert r["ok"] is False and r["raison"] == "ecart"


def test_calcul_et_fourchette():
    r = vv.calculer(200000, "F", "D", {**{c: 0.0 for c in "ABCDEFG"}, "F": -13.0}, 30)
    assert r == {"ok": True, "valeur": 26000, "min": 18200, "max": 33800, "ecart_pct": 13.0,
                 "ecart_avant": -13.0, "ecart_apres": 0.0}
    assert vv.calculer(0, "F", "D", {}, 30)["ok"] is False
    assert vv.calculer(200000, "D", "D", {c: 0.0 for c in "ABCDEFG"}, 30)["raison"] == "classe"
    assert vv.calculer(200000, "F", "E", {**{c: 0.0 for c in "ABCDEFG"}, "F": 2.0, "E": 1.0}, 30)["raison"] == "ecart"


def test_valeur_du_bien_saisie_sinon_dvf():
    assert vv.valeur_bien("250000", "2000", "100") == 250000
    assert vv.valeur_bien("", "2000", "100") == 200000


def test_departement_et_type():
    assert vv.departement("72300") == "72" and vv.departement("97411") == "974" and vv.departement("") == ""
    assert vv.type_bien("appartement") == "appartement" and vv.type_bien("maison") == "maison"


# ---------------------------------------------------------------- délai de rentabilité (énergie seule)
def test_mois_rentabilite_52_mois():
    res = {"chauffage_avant": 299 * 12, "ecs_actuelle": 0, "apres_annuel": 120 * 12, "inflation_avant": 0.04,
           "inflation_ecs_avant": 0.04, "inflation_apres": 0.03, "duree_ans": 20}
    assert eco.mois_rentabilite(res, 9857) == 52
    assert eco.texte_rentabilite(True, 52, None, 5, 20) == "rentabilisé en 52 mois"
    assert eco.texte_rentabilite(False, None, 12, 1, 20) == "rentabilisé dès le 1er mois"
    assert eco.texte_rentabilite(False, None, -20, 3, 20) == "rentabilisé dès la 3ᵉ année"


# ---------------------------------------------------------------- parité JS / Python
NODE_RUNNER = r"""
const fs = require('fs'), vm = require('vm');
const html = fs.readFileSync(process.argv[2], 'utf8');
const bloc = (d, f) => { const a = html.indexOf(d), b = html.indexOf(f); if (a < 0 || b < 0) throw new Error(d); return html.slice(a, b); };
const ctx = { window: {} }; vm.createContext(ctx);
vm.runInContext(bloc('/* HEXA-ECONOMIES:DEBUT', '/* HEXA-ECONOMIES:FIN */'), ctx);
vm.runInContext(bloc('/* HEXA-VALEUR-VERTE:DEBUT', '/* HEXA-VALEUR-VERTE:FIN */'), ctx);
const { HexaEconomies: E, HexaDpeEstime: D, HexaValeurVerte: V } = ctx.window;
const e = JSON.parse(fs.readFileSync(0, 'utf8'));
const out = e.cas.map(([eco, entree, params]) => {
  const res = E.calculerEconomies(eco, params);
  return { estime: D.estimer(res, entree.surface, entree.personnes, entree.ecs_chaudiere, params),
           projet: V.projet(entree, res, params, e.table),
           mois: E.moisRentabilite(res.ok ? res : null, entree.debourse),
           texte: E.texteRentabilite(entree.comptant, E.moisRentabilite(res.ok ? res : null, entree.debourse), entree.delta, 3, 20) };
});
const ecarts = e.ecarts.map(([dep, tb, a, b]) => V.ecarts(e.table, dep, tb, a, b));
const tuiles = e.tuiles.map(([eco, vvr, d]) => V.tuiles(eco, vvr, d));
const eurs = e.eurs.map((n) => V.eur(n));
process.stdout.write(JSON.stringify({ out, ecarts, tuiles, eurs }));
"""
ECARTS = [["72", "maison", "F", "C"], ["72", "maison", "G", "F"], ["72", "maison", "F", "D"], ["13", "appartement", "F", "D"],
          ["", "maison", "E", "B"], ["974", "maison", "F", "C"], ["49", "appartement", "F", "C"]]
ENTREE = dict(valeur_bien=180000, classe_dpe_avant="", dpe_connu="", surface=100, cp="72300", type_logement="maison",
              personnes=3, ecs_chaudiere=True, debourse=9857, comptant=True, delta=None)
CAS = [
    (GAZ, ENTREE, {}),
    (dict(GAZ, energie="fioul", facture_annuelle=3000), dict(ENTREE, classe_dpe_avant="F", cp="49460"), {}),
    (dict(GAZ, energie="fioul", facture_annuelle=3000), dict(ENTREE, dpe_connu="E", cp="49460"), {}),
    (dict(GAZ, service="chauffage_ecs"), dict(ENTREE, type_logement="appartement", cp="75011", surface=60), {}),
    (dict(GAZ, ecs_chaudiere=False, ballon=True), dict(ENTREE, ecs_chaudiere=False, comptant=False, delta=-5), {}),
    (dict(GAZ, energie="electricite", facture_annuelle=2400, facture_electricite_totale=True),
     dict(ENTREE, classe_dpe_avant="aucun", dpe_connu="G"), {}),
    (dict(GAZ, energie="bois", facture_annuelle=1500), dict(ENTREE, cp="97411", valeur_bien=0), {}),
    (GAZ, ENTREE, {"dpe_seuils_ep": {"C": 90}, "coef_ep": {"electricite": 2.3}, "valeur_verte_fourchette_pct": 20}),
    (dict(GAZ, facture_annuelle=0), ENTREE, {}),
    (GAZ, dict(ENTREE, classe_dpe_avant="G"), {}),                                   # Sarthe : G absent -> France
    (dict(GAZ, energie="fioul", facture_annuelle=3000), dict(ENTREE, classe_dpe_avant="F", cp="13001",
                                                                type_logement="appartement", surface=70), {}),
    (dict(GAZ, energie="fioul", facture_annuelle=3000), dict(ENTREE, classe_dpe_avant="G", cp="75011",
                                                                type_logement="appartement", surface=70), {}),
    (GAZ, dict(ENTREE, surface=0), {}),
]


@pytest.mark.skipif(shutil.which("node") is None, reason="node absent")
def test_parite_js_python(tmp_path):
    runner = tmp_path / "parite13.js"
    runner.write_text(NODE_RUNNER, encoding="utf-8")
    html = os.path.join(os.path.dirname(__file__), "..", "templates", "index.html")
    vv_ok = {"ok": True, "min": 18200, "valeur": 26000, "max": 33800, "libelle_classes": "Classe F → D",
             "libelle_source": "(classe estimée)", "libelle_ecarts": "Source : France entière"}
    eco_ok = {"avant_mensuel": 299, "apres_mensuel": 120, "total": 54296.5, "rentabilite": "rentabilisé en 52 mois"}
    tuiles = [[eco_ok, vv_ok, 20], [eco_ok, None, 20], [eco_ok, {"ok": False}, 15], [dict(eco_ok, total=None), vv_ok, 20],
              [dict(eco_ok, apres_mensuel=330, rentabilite=""), vv_ok, 20], [None, None, 20]]
    eurs = [0, 7, 999, 1000, 32900, 1234567, -1500, 54296.5]
    entree = {"cas": [list(c) for c in CAS], "table": vv.table(), "ecarts": ECARTS, "tuiles": tuiles, "eurs": eurs}
    res = subprocess.run(["node", str(runner), html], input=json.dumps(entree), capture_output=True,
                         text=True, encoding="utf-8", check=True)
    sortie = json.loads(res.stdout)
    js = sortie["out"]
    assert sortie["tuiles"] == [vv.tuiles(*x) for x in tuiles]
    assert sortie["eurs"] == [vv.eur(n) for n in eurs] and vv.eur(32900) == "32\u00a0900\u00a0€"
    assert [tuple(x) for x in sortie["ecarts"]] == [tuple(vv.ecarts(vv.table(), *x)) for x in ECARTS]
    for (e, entree_cas, params), j in zip(CAS, js):
        r = eco.calculer_economies(e, params)
        assert j["estime"] == dpe_estime.estimer(r, entree_cas["surface"], entree_cas["personnes"],
                                                 entree_cas["ecs_chaudiere"], params), (e, entree_cas)
        assert j["projet"] == vv.projet(entree_cas, r, params, vv.table()), (e, entree_cas)
        mois = eco.mois_rentabilite(r if r["ok"] else None, entree_cas["debourse"])
        assert j["mois"] == mois
        assert j["texte"] == eco.texte_rentabilite(entree_cas["comptant"], mois, entree_cas["delta"], 3, 20)
    assert any(j["projet"].get("ok") for j in js) and any(j["projet"].get("dpe_reel") for j in js)
    assert {j["projet"].get("source_ecarts") for j in js} >= {"departement", "france"}


# ---------------------------------------------------------------- pré-devis / devis : 3 tuiles + mention
LEAD = {"numero": "PR-01313", "civilite": "M.", "nom": "Test", "prenom": "Vv", "telephone": "0611121314",
        "email": "v@x.fr", "adresse_chantier": "1 rue A", "cp_chantier": "72300", "code_postal_chantier": "72300",
        "ville_chantier": "Solesmes", "type_logement": "maison", "surface_logement_m2": "100", "hsp": "2,5",
        "mode_chauffage": "gaz", "ecs": "chaudiere", "type_emetteurs": "radiateurs_classiques",
        "alimentation_electrique": "monophase", "categorie": "tres_modeste", "nombre_personnes": "3",
        "cout_energetique_mensuel_eur": "150", "cout_energie_source": "reel", "valeur_bien_estimee": "180000"}
MENTION = "Valeur verte : estimation indicative et non contractuelle"


def _preparer(lead, state=None):
    main._atomic_write_json(main.LEADS_PATH, [lead])
    main._atomic_write_json(main._state_simulateur_path(lead["numero"]), {})
    main.save_state_simulateur_atomic(lead["numero"], state or {"service": "chauffage_seul", "option": "opt3"})


def test_devis_trois_tuiles_et_mention():
    _preparer(LEAD)
    pa = main._build_devis_context(None, LEAD["numero"])["projet_apercu"]
    assert pa is not None
    v = pa["valeur_verte"]
    assert v and v["ok"] and v["libelle_source"] == "(classe estimée)" and v["min"] < v["valeur"] < v["max"]
    assert pa["gain_total"] == pa["eco_20_ans"] + v["min"]                 # bas de la fourchette
    assert pa["gain_total_fmt"] == vv.eur(pa["eco_20_ans"] + v["min"])
    assert pa["rentabilite_texte"].startswith("rentabilisé")
    eco_t, vv_t, total_t = pa["tuiles"]
    assert (vv_t["pre"], vv_t["montant"]) == ("à partir de", v["min_fmt"])
    assert (total_t["pre"], total_t["montant"]) == ("à partir de", pa["gain_total_fmt"])
    assert total_t["details"][0]["texte"] == (f"dont {vv.eur(pa['eco_20_ans'])} d'économies d'énergie"
                                              f" + à partir de {v['min_fmt']} de valeur verte")
    html = TestClient(main.app).get(f"/api/devis/{LEAD['numero']}/preview").text.replace("&#39;", "'")
    bloc = html.split('<div class="projet-apercu">')[1].split('<div class="anah-mention-block')[0]
    for t in ("Économies d'énergie", "Valeur verte", "Gain total sur", "à partir de", v["min_fmt"], pa["gain_total_fmt"],
              total_t["details"][0]["texte"], v["libelle_classes"], "(classe estimée)", pa["rentabilite_texte"], MENTION):
        assert t in bloc, t
    # ni le milieu ni le haut de la fourchette, ni un montant coupable (espace normale dans un montant)
    assert vv.eur(v["valeur"]) not in bloc and vv.eur(v["max"]) not in bloc
    import re
    assert not re.search(r"\d \d{3}\b|\d €", bloc.split("projet-apercu-tuiles")[1].split("</table>")[0])


def test_devis_dpe_reel_et_tuile_masquee_sans_valeur():
    _preparer(dict(LEAD, classe_dpe_avant="F"))
    v = main._build_devis_context(None, LEAD["numero"])["projet_apercu"]["valeur_verte"]
    assert v["classe_avant"] == "F" and v["libelle_source"] == "(DPE réel)"
    _preparer(dict(LEAD, valeur_bien_estimee="", prix_m2_estime=""))
    pa = main._build_devis_context(None, LEAD["numero"])["projet_apercu"]
    assert pa["valeur_verte"] is None and pa["gain_total"] == pa["eco_20_ans"]
    assert [t["cle"] for t in pa["tuiles"]] == ["eco", "total"]
    assert pa["tuiles"][1]["pre"] == "" and pa["tuiles"][1]["details"][0]["texte"].endswith("(valeur verte non estimée)")
    html = TestClient(main.app).get(f"/api/devis/{LEAD['numero']}/preview").text
    assert MENTION not in html and "Gain total sur" in html


def test_api_ecarts():
    r = TestClient(main.app).get("/api/valeur-verte/ecarts")
    assert r.status_code == 200 and r.json()["departements"]["49"]["maison"]["F"] == -13.4
