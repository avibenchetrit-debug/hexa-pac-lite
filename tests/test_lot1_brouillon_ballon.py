# -*- coding: utf-8 -*-
"""Lot 1 : notes/échanges d'une fiche pas encore enregistrée (clé TMP-) et ballon
thermodynamique (MPR supprimée au 01/09/2026, pas de ballon en chauffage + ECS)."""
import json
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

import main
from services import service_devis

DRAFT = "TMP-0f8c2a4e-1b2c-4d5e-8f90-123456789abc"
AUTRE_DRAFT = "TMP-aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"


@pytest.fixture
def client():
    return TestClient(main.app)


@pytest.fixture(autouse=True)
def donnees_vides():
    main._atomic_write_json(main.LEADS_PATH, [{"numero": "PR-00001", "nom": "Dupont", "email": "d@x.fr"}])
    main._atomic_write_json(main.NOTES_PATH, {})
    main._atomic_write_json(main.ECHANGES_PATH, {})
    yield


def _lire(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------- brouillons N / E
def test_note_et_echange_acceptes_sur_cle_brouillon(client):
    r = client.post(f"/prospect/{DRAFT}/commentaire-ajax", data={"texte_commentaire": "note 1", "auteur": "Avi"})
    assert r.status_code == 200 and r.json()["count"] == 1
    r = client.post(f"/prospect/{DRAFT}/echanges-ajax", json={"type": "sms", "contenu": "sms 1", "auteur": "Avi"})
    assert r.status_code == 200 and r.json()["count"] == 1
    assert len(client.get(f"/api/notes/{DRAFT}").json()) == 1
    assert len(client.get(f"/prospect/{DRAFT}/echanges-json").json()["echanges"]) == 1


def test_attach_deplace_concatene_et_est_idempotent(client):
    main._atomic_write_json(main.NOTES_PATH, {
        DRAFT: [{"texte": "n1"}, {"texte": "n2"}],
        "PR-00001": [{"texte": "ancienne"}],
    })
    main._atomic_write_json(main.ECHANGES_PATH, {DRAFT: [{"contenu": "e1"}]})

    r = client.post(f"/api/drafts/{DRAFT}/attach/PR-00001")
    assert r.status_code == 200
    assert r.json() == {"ok": True, "numero": "PR-00001", "notes": 2, "echanges": 1}
    notes, echanges = _lire(main.NOTES_PATH), _lire(main.ECHANGES_PATH)
    assert DRAFT not in notes and DRAFT not in echanges
    assert [n["texte"] for n in notes["PR-00001"]] == ["ancienne", "n1", "n2"]
    assert [e["contenu"] for e in echanges["PR-00001"]] == ["e1"]

    # Second appel : rien à déplacer, rien de dupliqué.
    r = client.post(f"/api/drafts/{DRAFT}/attach/PR-00001")
    assert r.json()["notes"] == 0 and r.json()["echanges"] == 0
    assert len(_lire(main.NOTES_PATH)["PR-00001"]) == 3


def test_attach_refuse_cle_invalide_et_lead_inconnu(client):
    assert client.post("/api/drafts/PR-00002/attach/PR-00001").status_code == 400
    assert client.post(f"/api/drafts/{DRAFT}/attach/PR-99999").status_code == 404


def test_attach_protege_par_l_auth(monkeypatch):
    monkeypatch.setenv("AUTH_ENFORCE", "1")
    r = TestClient(main.app).post(f"/api/drafts/{DRAFT}/attach/PR-00001")
    assert r.status_code == 401


def test_purge_garde_les_brouillons_recents_et_purge_les_vieux(client, monkeypatch):
    monkeypatch.setattr(main, "_require_admin", lambda request: None)  # jeton admin hors sujet ici
    vieux = (datetime.now(main.PARIS_TZ) - timedelta(hours=49)).isoformat(timespec="seconds")
    recent = (datetime.now(main.PARIS_TZ) - timedelta(hours=2)).isoformat(timespec="seconds")
    main._atomic_write_json(main.NOTES_PATH, {
        DRAFT: [{"texte": "vieux", "date": vieux}],
        AUTRE_DRAFT: [{"texte": "récent", "date": recent}],
        "PR-00001": [{"texte": "lead", "date": vieux}],
    })
    main._atomic_write_json(main.ECHANGES_PATH, {
        AUTRE_DRAFT: [{"contenu": "récent", "created_at": recent}],
        "PR-ORPHELIN": [{"contenu": "x", "created_at": recent}],
    })

    dry = client.post("/api/admin/purge-echanges-orphelins", json={}).json()
    assert dry["dry_run"] is True
    assert dry["orphelins"] == ["PR-ORPHELIN"]          # brouillon récent épargné
    assert dry["notes_orphelines"] == [DRAFT]

    client.post("/api/admin/purge-echanges-orphelins", json={"confirm": True})
    notes, echanges = _lire(main.NOTES_PATH), _lire(main.ECHANGES_PATH)
    assert set(notes) == {AUTRE_DRAFT, "PR-00001"}
    assert set(echanges) == {AUTRE_DRAFT}


def test_email_modele_sur_brouillon_prend_l_email_du_formulaire(client):
    r = client.post(f"/api/modeles-email/{DRAFT}/envoyer", json={"sujet": "s", "contenu": "c", "email": ""})
    assert r.status_code == 400 and r.json()["detail"] == "Saisissez d'abord l'email"
    r = client.post(f"/api/modeles-email/{DRAFT}/envoyer", json={"sujet": "s", "contenu": "c", "email": "a@b.fr"})
    assert r.status_code == 200
    assert "a@b.fr" in _lire(main.NOTES_PATH)[DRAFT][0]["texte"]
    # Un numéro non brouillon inconnu reste un 404.
    assert client.post("/api/modeles-email/PR-99999/envoyer", json={"email": "a@b.fr"}).status_code == 404


# ---------------------------------------------------------------- ballon
ADMIN = {
    "ballon_thermo": {
        "modeles": [{"ref": "ballon-1", "nom": "B1", "fourniture_ht": 1000}],
        "prix_pose_ht": 500,
        "forfaits_mpr": {"tres_modeste": 1200, "modeste": 800, "intermediaire": 400, "superieur": 0},
    }
}


@pytest.mark.parametrize("categorie", ["tres_modeste", "modeste", "intermediaire", "superieur"])
def test_mpr_ballon_toujours_zero(categorie):
    assert service_devis.calculer_mpr_ballon({"categorie_revenu": categorie}, ADMIN) == 0


def test_ballon_resolu_en_chauffage_seul_seulement():
    assert service_devis.resoudre_ballon({"service": "chauffage_seul", "ballon_ref": "ballon-1"}, ADMIN)["ref"] == "ballon-1"
    assert service_devis.resoudre_ballon({"ballon_ref": "ballon-1"}, ADMIN)["ref"] == "ballon-1"
    for service in ("chauffage_ecs", "chauffage+ecs"):
        assert service_devis.resoudre_ballon({"service": service, "ballon_ref": "ballon-1"}, ADMIN) is None


ADMIN_TYPES = {"ballon_thermo": {"modeles": [
    {"ref": "b-compact", "type_installation": "compact"},
    {"ref": "b-split", "type_installation": "split"},
    {"ref": "b-sans-type"},
]}}
INADAPTE = "Ballon non adapté à l'emplacement indiqué (simulateur)"


@pytest.mark.parametrize("ref, emplacement, bloque", [
    ("b-compact", "piece_non_chauffee", False),   # bon type
    ("b-split", "piece_non_chauffee", True),      # split forcé dans un garage
    ("b-compact", "pas_de_place", True),          # compact sans place
    ("b-split", "pas_de_place", False),
    ("b-sans-type", "pas_de_place", False),       # type non renseigné en admin : pas de blocage
])
def test_validation_devis_bloque_un_ballon_inadapte(ref, emplacement, bloque):
    state = {"modele_pac_id": "X", "service": "chauffage_seul", "ballon_ref": ref, "ballon_emplacement": emplacement}
    assert (INADAPTE in service_devis.validate_prospect_for_devis({}, state, ADMIN_TYPES)) is bloque


def test_ballon_inadapte_ignore_en_chauffage_ecs():
    state = {"modele_pac_id": "X", "service": "chauffage_ecs", "ballon_ref": "b-split", "ballon_emplacement": "piece_non_chauffee"}
    assert INADAPTE not in service_devis.validate_prospect_for_devis({}, state, ADMIN_TYPES)


def test_route_validate_bloque_un_ballon_inadapte(client, tmp_path):
    main._atomic_write_json(main.LEADS_PATH, [{"numero": "PR-00001", "nom": "Dupont", "email": "d@x.fr"}])
    params = main.load_parametres_admin()
    params["ballon_thermo"] = dict(params.get("ballon_thermo") or {}, modeles=ADMIN_TYPES["ballon_thermo"]["modeles"])
    main.save_parametres_admin_atomic(params)
    main.save_state_simulateur_atomic("PR-00001", {"service": "chauffage_seul", "ballon_ref": "b-split",
                                                   "ballon_emplacement": "piece_non_chauffee"})
    assert INADAPTE in client.get("/api/devis/PR-00001/validate").json()["missing"]
    main.save_state_simulateur_atomic("PR-00001", {"ballon_ref": "b-compact"})
    assert INADAPTE not in client.get("/api/devis/PR-00001/validate").json()["missing"]


def test_validation_devis_exige_l_emplacement_du_ballon():
    base = {"modele_pac_id": "X", "service": "chauffage_seul"}
    manque = "Emplacement du ballon (simulateur)"
    assert manque in service_devis.validate_prospect_for_devis({}, {**base, "ballon_ref": "ballon-1"})
    assert manque not in service_devis.validate_prospect_for_devis(
        {}, {**base, "ballon_ref": "ballon-1", "ballon_emplacement": "piece_non_chauffee"})
    assert manque not in service_devis.validate_prospect_for_devis({}, {**base, "service": "chauffage_ecs", "ballon_ref": "ballon-1"})
    assert manque not in service_devis.validate_prospect_for_devis({}, base)
