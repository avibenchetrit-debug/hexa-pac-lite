# -*- coding: utf-8 -*-
"""Lot 6f : script d'appel pré-rempli (étapes 2 à 6), étape 1 éditée conservée, nouveaux champs (note, condition,
action, objection dépliable) gardés à l'enregistrement."""
import json
import time

import pytest
from fastapi.testclient import TestClient

import main


@pytest.fixture
def client():
    return TestClient(main.app)


def _jeton_admin():
    p = f"admin:{int(time.time())}"
    return f"{p}.{main._sign_admin_token(p)}"


def _params_sans_script():
    p = main.load_parametres_admin()
    p.pop("script_appel", None)
    main._atomic_write_json(main.PARAMETRES_ADMIN_PATH, p)          # (la sauvegarde admin fusionne : une clé retirée resterait)


def test_defaut_etapes_2_a_6_pre_remplies(client):
    _params_sans_script()
    s = client.get("/api/script-appel").json()
    e = s["etapes"]
    # Lot 6i : textes définitifs (branches DPE / sans DPE, ballon, attente MPR…)
    assert e["2"]["intro"].startswith("Pour préparer votre projet")
    assert e["2"]["questions"][1]["condition"] == "dpe" and "[surface]" in e["2"]["questions"][1]["texte"]
    assert e["2"]["questions"][3]["type"] == "dire" and e["2"]["questions"][3]["condition"] == "!dpe"
    assert [q["texte"] for q in e["2"]["questions"] if q.get("condition") == "!dpe" and q.get("type") != "dire"][0] == "C'est une maison ou un appartement ?"
    assert e["3"]["questions"][3]["condition"] == "dpe" and "[X coût théorique]" in e["3"]["questions"][3]["texte"]
    assert "[année avis]" in e["4"]["questions"][1]["texte"] and "[année revenus]" in e["4"]["questions"][1]["texte"]
    assert e["4"]["explication"].startswith("Pour calculer vos aides") and e["4"]["intro"] == ""
    assert e["5"]["questions"][4]["condition"] == "q3=2 | q4=2 | ballon"
    assert [r["libelle"] for r in e["6"]["questions"][0]["reponses"]] == ["Attendre", "Tout de suite"]
    obj = [c for c in e["6"]["encarts"] if c.get("repliable")]
    assert [c["titre"] for c in obj] == ["« C'est trop cher »", "« Je dois réfléchir / en parler à mon conjoint »", "« J'ai déjà un autre devis »"]
    assert obj[1]["action"] == "rappel" and "[reste à charge]" in obj[0]["texte"] and "[économie mensuelle]" in obj[0]["texte"]
    assert e["6"]["encarts"][-1]["texte"].startswith("« Est-ce que ça vous convient ?")


def test_config_ancienne_remplacee_une_fois_puis_admin_garde(client):
    etape1 = {"titre": "Accueil maison", "intro": "Bonjour, texte édité.", "questions": [
        {"texte": "C'est vous ?", "reponses": [{"libelle": "Non", "consigne": "", "alerte": True}]}], "encarts": []}
    p = main.load_parametres_admin()
    p["script_appel"] = {"etapes": {"1": etape1, "2": {"titre": "Le logement", "intro": "", "questions": [], "encarts": []}}, "version": 2}
    main.save_parametres_admin_atomic(p)
    s = client.get("/api/script-appel").json()
    # Lot 6i : les textes définitifs remplacent tout le script (étape 1 comprise), une seule fois
    assert s["etapes"]["1"]["intro"].startswith("Bonjour [civilité nom]") and len(s["faq"]) == 13
    stocke = main.load_parametres_admin()["script_appel"]
    assert stocke["version"] == 4 and stocke["etapes"]["1"]["intro"].startswith("Bonjour [civilité nom]")
    # ensuite, une modification de l'admin reste (plus de remplacement)
    s["etapes"]["2"]["intro"] = "Intro modifiée."
    s["faq"] = [{"question": "Q ?", "reponse": "R."}]
    assert client.post("/api/admin/script-appel", json=s, headers={"X-Admin-Token": _jeton_admin()}).status_code == 200
    relu = client.get("/api/script-appel").json()
    assert relu["etapes"]["2"]["intro"] == "Intro modifiée." and relu["faq"] == [{"question": "Q ?", "reponse": "R."}]


def test_enregistrement_garde_les_nouveaux_champs(client):
    _params_sans_script()
    s = client.get("/api/script-appel").json()
    r = client.post("/api/admin/script-appel", json=s, headers={"X-Admin-Token": _jeton_admin()}).json()["script_appel"]
    assert r == s                                                         # aller-retour sans perte (textes, FAQ, champs 6i)
    assert r["etapes"]["2"]["questions"][11]["reponses"][1]["texte"] == "Quelle est l'adresse où vous habitez ?"
    assert r["etapes"]["6"]["encarts"][1]["repliable"] is True and r["etapes"]["6"]["encarts"][1]["action"] == "rappel"
    assert r["etapes"]["1"]["questions"][1]["reponses"][1]["action"] == "rappel"
    faux = json.loads(json.dumps(s)); faux["etapes"]["1"]["questions"][0]["reponses"][0]["action"] = "supprimer_tout"
    faux["etapes"]["1"]["questions"][0]["type"] = "pirate"
    r2 = client.post("/api/admin/script-appel", json=faux, headers={"X-Admin-Token": _jeton_admin()}).json()["script_appel"]
    assert "action" not in r2["etapes"]["1"]["questions"][0]["reponses"][0]      # action inconnue ignorée
    assert "type" not in r2["etapes"]["1"]["questions"][0]                      # type inconnu ignoré
    sans_faq = json.loads(json.dumps(s)); sans_faq.pop("faq")
    r3 = client.post("/api/admin/script-appel", json=sans_faq, headers={"X-Admin-Token": _jeton_admin()}).json()["script_appel"]
    assert r3["faq"] == s["faq"]                                                 # ancien écran sans FAQ : la FAQ reste