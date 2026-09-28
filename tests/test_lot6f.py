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
    assert e["2"]["intro"].startswith("Pour préparer votre projet")
    assert [q["texte"][:20] for q in e["2"]["questions"]][1] == "« C'est bien une mai"
    assert "[surface]" in e["2"]["questions"][1]["texte"] and "[année]" in e["2"]["questions"][1]["texte"]
    assert e["5"]["questions"][1]["condition"] == "service=chauffage_seul & ecs_chaudiere" and e["5"]["questions"][2]["condition"] == "ballon"
    obj = [c for c in e["6"]["encarts"] if c.get("repliable")]
    assert [c["titre"] for c in obj] == ["« C'est trop cher »", "« Je dois réfléchir / en parler à mon conjoint »", "« J'ai déjà un autre devis »"]
    assert obj[1]["action"] == "rappel" and "[reste à charge]" in obj[0]["texte"] and "[économie mensuelle]" in obj[0]["texte"]
    assert e["6"]["encarts"][-1]["texte"].startswith("« Je vous envoie votre pré-devis")
    # étape 1 : texte d'origine, actions sur les boutons
    assert e["1"]["intro"].startswith("Bonjour [Civilité Nom]")
    assert e["1"]["questions"][0]["reponses"][1]["action"] == "cloturer" and e["1"]["questions"][1]["reponses"][1]["action"] == "rappel"


def test_config_ancienne_completee_une_fois_etape_1_editee_gardee(client):
    etape1 = {"titre": "Accueil maison", "intro": "Bonjour, texte édité.", "questions": [
        {"texte": "C'est vous ?", "reponses": [{"libelle": "Non", "consigne": "", "alerte": True}]}], "encarts": []}
    p = main.load_parametres_admin()
    p["script_appel"] = {"etapes": {"1": etape1, "2": {"titre": "Le logement", "intro": "", "questions": [], "encarts": []}}}
    main.save_parametres_admin_atomic(p)
    s = client.get("/api/script-appel").json()
    assert s["etapes"]["1"] == etape1                                  # étape 1 éditée : intacte
    assert s["etapes"]["2"]["intro"].startswith("Pour préparer votre projet")
    stocke = main.load_parametres_admin()["script_appel"]
    assert stocke["version"] == 2 and stocke["etapes"]["1"] == etape1
    # ensuite, une modification de l'admin sur l'étape 2 reste (plus de remplacement)
    s["etapes"]["2"]["intro"] = "Intro modifiée."
    assert client.post("/api/admin/script-appel", json=s, headers={"X-Admin-Token": _jeton_admin()}).status_code == 200
    assert client.get("/api/script-appel").json()["etapes"]["2"]["intro"] == "Intro modifiée."


def test_enregistrement_garde_les_nouveaux_champs(client):
    _params_sans_script()
    s = client.get("/api/script-appel").json()
    r = client.post("/api/admin/script-appel", json=s, headers={"X-Admin-Token": _jeton_admin()}).json()["script_appel"]
    assert r["etapes"]["2"]["questions"][2]["note"].startswith("Si loué")
    assert r["etapes"]["5"]["questions"][2]["condition"] == "ballon"
    assert r["etapes"]["6"]["encarts"][1]["repliable"] is True and r["etapes"]["6"]["encarts"][1]["action"] == "rappel"
    assert r["etapes"]["1"]["questions"][1]["reponses"][1]["action"] == "rappel"
    faux = json.loads(json.dumps(s)); faux["etapes"]["1"]["questions"][0]["reponses"][0]["action"] = "supprimer_tout"
    r2 = client.post("/api/admin/script-appel", json=faux, headers={"X-Admin-Token": _jeton_admin()}).json()["script_appel"]
    assert "action" not in r2["etapes"]["1"]["questions"][0]["reponses"][0]      # action inconnue ignorée
