# -*- coding: utf-8 -*-
"""Lot 6 : parcours télépro en 6 étapes. Côté serveur : script d'appel (config admin, jamais dans le lead),
devis (parcelle cadastrale + surface chauffée dans le bloc « Dossier »). Côté page : l'échéancier
d'affichage (acompte / solde / banque), exécuté tel qu'il est écrit dans templates/index.html."""
import json
import os
import re
import shutil
import subprocess
import time

import pytest
from fastapi.testclient import TestClient

import main

LEAD = {"numero": "PR-00606", "civilite": "Madame", "nom": "Parcelle", "prenom": "Lina", "telephone": "0611121316",
        "email": "l6@x.fr", "adresse_chantier": "1 rue A", "cp_chantier": "53000", "code_postal_chantier": "53000",
        "ville_chantier": "Laval", "type_logement": "maison", "surface_logement_m2": "120", "hsp": "2,5",
        "mode_chauffage": "fioul", "ecs": "chaudiere", "type_emetteurs": "radiateurs_classiques",
        "alimentation_electrique": "monophase", "categorie": "tres_modeste", "nombre_personnes": "4",
        "cout_energetique_mensuel_eur": "400", "cout_energie_source": "reel"}


@pytest.fixture
def client():
    return TestClient(main.app)


def _jeton_admin():
    p = f"admin:{int(time.time())}"
    return f"{p}.{main._sign_admin_token(p)}"


@pytest.fixture(autouse=True)
def params_vierges():
    main._atomic_write_json(main.PARAMETRES_ADMIN_PATH, {})
    yield


# ---------------------------------------------------------------- script d'appel
def test_script_appel_par_defaut(client):
    s = client.get("/api/script-appel").json()
    assert sorted(s["etapes"]) == ["1", "2", "3", "4", "5", "6"] and s["version"] == 3
    e1 = s["etapes"]["1"]
    # Lot 6i : textes définitifs
    assert e1["intro"].startswith("Bonjour [civilité nom], [prénom utilisateur] de la société Hexa-Rénov'.")
    assert "pompe à chaleur air-eau" in e1["intro"]
    assert [q["texte"] for q in e1["questions"]] == ["Êtes-vous bien à l'origine de cette demande ?",
                                                      "Avez-vous un moment pour qu'on parle de votre projet ?",
                                                      "Où en êtes-vous dans votre projet ?"]
    assert [r["libelle"] for r in e1["questions"][0]["reponses"]] == ["Oui", "Non"]
    assert e1["questions"][0]["reponses"][1]["action"] == "cloturer"
    assert e1["questions"][0]["reponses"][1]["texte"] == "Excusez-moi pour le dérangement, bonne journée."
    assert [r["libelle"] for r in e1["questions"][1]["reponses"]] == ["Oui", "Non, rappeler"]
    assert e1["questions"][1]["reponses"][1]["action"] == "rappel"
    assert [r["libelle"] for r in e1["questions"][2]["reponses"]] == ["Découverte", "Sait ce qu'il veut"]
    assert e1["questions"][2]["reponses"][0]["explication"].startswith("Le fioul et le gaz coûtent de plus en plus cher.")
    e2 = s["etapes"]["2"]
    assert "Depuis [année du DPE], avez-vous fait des travaux d'isolation : toit, murs ou fenêtres ?" == e2["questions"][2]["texte"]
    for n in "3456":
        assert s["etapes"][n]["questions"]
    assert len(s["faq"]) == 13


def test_script_appel_ecriture_reservee_admin(client):
    assert client.post("/api/admin/script-appel", json={"etapes": {}}).status_code == 401


def test_script_appel_enregistre_nettoye_et_relu(client):
    envoi = {"etapes": {"3": {"titre": "Chauffage", "intro": "  Parlons chauffage.  ", "pirate": 1,
                              "questions": [{"texte": "Vous vous chauffez comment ?", "reponses": [{"libelle": "Fioul", "consigne": "Argument fioul", "alerte": 1},
                                                                                                    {"libelle": "", "consigne": "ignorée"}]},
                                            {"texte": "", "reponses": []}],
                              "encarts": [{"titre": "Si fioul :", "texte": "La CEE est maximale.", "condition": "energie=fioul"}, {"titre": "", "texte": ""}]}}}
    r = client.post("/api/admin/script-appel", json=envoi, headers={"X-Admin-Token": _jeton_admin()})
    assert r.status_code == 200
    e3 = client.get("/api/script-appel").json()["etapes"]["3"]
    assert e3 == {"titre": "Chauffage", "intro": "Parlons chauffage.",
                  "questions": [{"texte": "Vous vous chauffez comment ?", "reponses": [{"libelle": "Fioul", "consigne": "Argument fioul", "alerte": True}]}],
                  "encarts": [{"titre": "Si fioul :", "texte": "La CEE est maximale.", "condition": "energie=fioul"}]}
    # les autres étapes existent toujours (titre par défaut) ; rien n'est écrit dans les leads
    s = client.get("/api/script-appel").json()
    assert sorted(s["etapes"]) == ["1", "2", "3", "4", "5", "6"] and s["etapes"]["1"]["titre"] == "Prise de contact"
    assert "script_appel" in main.load_parametres_admin()
    assert client.get("/api/admin/m3").json()["script_appel"]["etapes"]["3"]["intro"] == "Parlons chauffage."


# ---------------------------------------------------------------- devis : parcelle cadastrale + surface chauffée
def _bloc_dossier(html):
    bloc = html.split('<div class="infos-col-title">Dossier</div>')[1].split("</div>\n</section>")[0]
    return re.findall(r'<span class="infos-label">([^<]+)</span><span class="infos-value">([^<]*)</span>', bloc)


@pytest.mark.parametrize("parcelle, attendu", [("000 AB 123", "000 AB 123"), ("", "—")])
def test_devis_parcelle_puis_surface_chauffee(client, parcelle, attendu):
    main._atomic_write_json(main.LEADS_PATH, [dict(LEAD, parcelle_cadastrale=parcelle)])
    main._atomic_write_json(main._state_simulateur_path(LEAD["numero"]), {})
    main.save_state_simulateur_atomic(LEAD["numero"], {"service": "chauffage_seul", "option": "opt1"})
    for variante in ("devis", "pre_devis"):
        html = client.get(f"/api/devis/{LEAD['numero']}/preview?variante={variante}").text
        lignes = _bloc_dossier(html.replace("\r\n", "\n"))
        libelles = [lib for lib, _ in lignes]
        i = libelles.index("Ville chantier")
        assert libelles[i + 1] == "Parcelle cadastrale" and lignes[i + 1][1] == attendu
        assert libelles[i + 2] == "Surface chauffée" and lignes[i + 2][1].strip()
        assert libelles.count("Surface chauffée") == 1 and libelles.count("Parcelle cadastrale") == 1
        # rien d'autre ne bouge : mêmes lignes qu'avant, dans le même ordre (hors les deux déplacées)
        reste = [x for x in libelles if x not in ("Parcelle cadastrale", "Surface chauffée")]
        assert reste[reste.index("Ville chantier") + 1:reste.index("Ville chantier") + 4] == ["Type de logement", "Surface habitable", "Type de chauffage"]


# ---------------------------------------------------------------- échéancier (exécuté depuis la page)
RUNNER = r"""
const fs = require('fs');
const src = fs.readFileSync(process.argv[2], 'utf8');
function extraire(nom) {
  let start = src.indexOf(`function ${nom}(`);
  if (start === -1) throw new Error('introuvable ' + nom);
  let depth = 0;
  for (let i = src.indexOf('{', start); i < src.length; i++) {
    const c = src[i];
    if (c === '{') depth++;
    else if (c === '}') { depth--; if (depth === 0) return src.slice(start, i + 1); }
  }
  throw new Error('accolade');
}
const cas = JSON.parse(fs.readFileSync(0, 'utf8'));
const out = cas.map(k => {
  const state = { option: k.option, financement_mpr: k.fin, mode_mpr: k.sans ? 'sans_attente' : 'attente' };
  const f = new Function('state', extraire('echeancier') + '; return echeancier;')(state);
  return f(k.c);
});
process.stdout.write(JSON.stringify(out));
"""


def _cas():
    R, M = 6059.4, 3000.0          # reste à charge (centimes : CEE), avance MaPrimeRénov'
    out = []
    for sans, option, fin in [(False, "opt3", "cash"), (False, "opt1", "cash"), (False, "opt2", "cash"),
                              (True, "opt3", "cash"), (True, "opt1", "cash"), (True, "opt1", "credit"),
                              (True, "opt2", "cash"), (True, "opt2", "credit")]:
        base = R + M if (sans and fin == "credit") else R
        mens, n = ((47.83, 180) if option == "opt1" else (base / 180, 180) if option == "opt2" else (0, 0))
        out.append({"sans": sans, "option": option, "fin": fin,
                    "c": {"resteAttente": R, "mprTotal": M, "sansAttente": sans, "base_credit": base, "mensOpt": mens, "nMois": n}})
    return out


@pytest.mark.skipif(shutil.which("node") is None, reason="node absent")
def test_echeancier_huit_cas_chaque_euro_une_fois(tmp_path):
    runner = tmp_path / "echeancier.js"
    runner.write_text(RUNNER, encoding="utf-8")
    html = os.path.join(os.path.dirname(__file__), "..", "templates", "index.html")
    cas = _cas()
    res = json.loads(subprocess.run(["node", str(runner), html], input=json.dumps(cas), capture_output=True, text=True,
                                    encoding="utf-8", check=True).stdout)
    assert len(res) == 8
    for k, e in zip(cas, res):
        c, sans, opt = k["c"], k["sans"], k["option"]
        total = c["resteAttente"] + (c["mprTotal"] if sans else 0)
        finance = 0 if opt == "opt3" else c["base_credit"]
        assert e["total"] == pytest.approx(total) and e["finance"] == pytest.approx(finance)
        assert e["totalE"] == round(total)
        # chaque euro payé une fois : client (acompte + solde) + banque = total à régler
        assert e["acompte"] + e["solde"] + e["ctE"] == e["totalE"], k
        # crédit travaux (affecté) : versé par la banque à la fin des travaux ; comptant et Éco-PTZ : le client
        assert e["ctE"] == (round(finance) if opt == "opt1" else 0), k
        assert e["clientE"] == e["totalE"] - e["ctE"]
        assert e["acompte"] == round(e["clientE"] * 0.3) and e["solde"] == e["clientE"] - e["acompte"]
        if opt == "opt2":
            assert e["clientE"] == e["totalE"]              # l'Éco-PTZ est reçu par le client, qui paie sur factures
        # coût final : formule inchangée (Lot 5) = comptant + mensualités − MaPrimeRénov' récupérée
        cash = max(0, total - finance)
        assert e["coutFinal"] == pytest.approx(cash + c["mensOpt"] * c["nMois"] - (c["mprTotal"] if sans else 0))
    # tout de suite + crédit travaux : avance comptant (le client paie l'avance) ou tout financé (rien pour le client)
    avance, tout_credit = res[4], res[5]
    assert avance["clientE"] == round(3000.0 + 6059.4) - round(6059.4) and tout_credit["clientE"] == 0
