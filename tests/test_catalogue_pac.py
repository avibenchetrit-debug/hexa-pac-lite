# -*- coding: utf-8 -*-
"""Non-regression : le catalogue PAC ne doit plus pouvoir etre efface par un POST admin.

Le bug d'origine : le simulateur filtre les modeles a puissance/prix 0
(`nettoyerCatalogue`), l'admin repartait de cette liste FILTREE, et le POST suivant
ecrasait le fichier serveur -> les modeles incomplets disparaissaient definitivement,
sans sauvegarde. Les tests ci-dessous verrouillent les trois garde-fous ajoutes :
verrou optimiste (If-Match), garde anti-suppression (X-Catalogue-Deleted), sauvegardes.
"""
import io
import json
import os
import shutil
import time

import pytest
from fastapi.testclient import TestClient

import main

# 22 modeles, dont les 3 THA-MTBL-R290 incomplets (ttc=0 / puissance=0) : ce sont eux
# que le filtre du simulateur retirait, et donc eux que le POST effacait.
REFS_INCOMPLETS = ["THA-MTBL-R290-9", "THA-MTBL-R290-12", "THA-MTBL-R290-14"]


def _modele(ref, ttc, puiss):
    return {
        "ref": ref,
        "nom": f"Modele {ref}",
        "usage": "Chauffage",
        "alim": "Mono",
        "puiss35": puiss,
        "puiss_chauf": puiss,
        "ttc": ttc,
        "achat": round(ttc * 0.55) if ttc else 0,
        "description_technique": "",
        "description_specs": [],
    }


def _fixture_22():
    models = [_modele(f"ATL-EXCELLIA-S-{i}", 8000 + i * 250, 8 + i) for i in range(19)]
    models += [_modele(ref, 0, 0) for ref in REFS_INCOMPLETS]
    assert len(models) == 22
    return models


def _complets(models):
    """Ce que le simulateur laisse passer -- exactement le payload tronque d'origine."""
    return [m for m in models if m["puiss35"] > 0 and m["ttc"] > 0]


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("AUTH_ENFORCE", "0")
    os.makedirs(main.DATA_DIR, exist_ok=True)
    main._atomic_write_json(main.CATALOGUE_PAC_PATH, _fixture_22())
    shutil.rmtree(main.CATALOGUE_BACKUP_DIR, ignore_errors=True)
    return TestClient(main.app)


def _version(client):
    r = client.get("/api/catalogue-pac")
    assert r.status_code == 200
    return r.headers["X-Catalogue-Version"]


def _sur_disque():
    with open(main.CATALOGUE_PAC_PATH, encoding="utf-8") as f:
        return json.load(f)


def _nb_backups():
    try:
        return len([n for n in os.listdir(main.CATALOGUE_BACKUP_DIR) if n.endswith(".json")])
    except FileNotFoundError:
        return 0


# --------------------------------------------------------------------------
# L'invariant central
# --------------------------------------------------------------------------

def test_liste_filtree_n_efface_plus_les_modeles_incomplets(client):
    """LE test de non-regression : POSTer la liste filtree ne doit rien supprimer."""
    tronque = _complets(_fixture_22())
    assert len(tronque) == 19

    r = client.post(
        "/api/catalogue-pac",
        json=tronque,
        headers={"If-Match": _version(client)},
    )

    assert r.status_code == 409
    for ref in REFS_INCOMPLETS:
        assert ref in r.json()["detail"]
    # et surtout : le fichier est intact
    disque = _sur_disque()
    assert len(disque) == 22
    assert {m["ref"] for m in disque} >= set(REFS_INCOMPLETS)


def test_suppression_explicite_autorisee(client):
    """Une suppression VOULUE passe, via X-Catalogue-Deleted."""
    tronque = _complets(_fixture_22())
    r = client.post(
        "/api/catalogue-pac",
        json=tronque,
        headers={
            "If-Match": _version(client),
            "X-Catalogue-Deleted": ",".join(REFS_INCOMPLETS),
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["count"] == 19
    assert len(_sur_disque()) == 19


def test_modification_sans_suppression_passe(client):
    """Le cas nominal : on edite un prix, rien n'est supprime."""
    models = _fixture_22()
    models[0]["ttc"] = 9999
    r = client.post("/api/catalogue-pac", json=models, headers={"If-Match": _version(client)})
    assert r.status_code == 200, r.text
    disque = _sur_disque()
    assert len(disque) == 22
    assert disque[0]["ttc"] == 9999


# --------------------------------------------------------------------------
# Verrou optimiste
# --------------------------------------------------------------------------

def test_if_match_absent_refuse(client):
    r = client.post("/api/catalogue-pac", json=_fixture_22())
    assert r.status_code == 409
    assert "If-Match" in r.json()["detail"]
    assert len(_sur_disque()) == 22


def test_if_match_perime_refuse(client):
    v0 = _version(client)
    # quelqu'un d'autre ecrit entre-temps
    autre = _fixture_22()
    autre[1]["ttc"] = 12345
    assert client.post("/api/catalogue-pac", json=autre, headers={"If-Match": v0}).status_code == 200

    r = client.post("/api/catalogue-pac", json=_fixture_22(), headers={"If-Match": v0})
    assert r.status_code == 409
    assert "modifie ailleurs" in r.json()["detail"]
    # l'ecriture concurrente n'a pas ete ecrasee
    assert _sur_disque()[1]["ttc"] == 12345


def test_version_change_a_chaque_ecriture(client):
    v0 = _version(client)
    models = _fixture_22()
    models[2]["ttc"] = 7777
    r = client.post("/api/catalogue-pac", json=models, headers={"If-Match": v0})
    assert r.status_code == 200
    assert r.headers["X-Catalogue-Version"] != v0
    assert _version(client) == r.headers["X-Catalogue-Version"]


# --------------------------------------------------------------------------
# Sauvegardes
# --------------------------------------------------------------------------

def test_backup_cree_avant_ecriture(client):
    assert _nb_backups() == 0
    models = _fixture_22()
    models[0]["ttc"] = 8888
    assert client.post(
        "/api/catalogue-pac", json=models, headers={"If-Match": _version(client)}
    ).status_code == 200

    assert _nb_backups() == 1
    nom = os.listdir(main.CATALOGUE_BACKUP_DIR)[0]
    with open(os.path.join(main.CATALOGUE_BACKUP_DIR, nom), encoding="utf-8") as f:
        sauvegarde = json.load(f)
    # la sauvegarde contient l'ETAT D'AVANT, donc les 22 modeles
    assert len(sauvegarde) == 22


def test_rotation_conserve_30_sauvegardes(client):
    models = _fixture_22()
    for i in range(31):
        models[0]["ttc"] = 8000 + i
        r = client.post("/api/catalogue-pac", json=models, headers={"If-Match": _version(client)})
        assert r.status_code == 200, r.text
    assert _nb_backups() == 30


def test_collision_meme_seconde_ne_perd_pas_de_backup(client):
    """Deux ecritures dans la meme seconde -> deux fichiers distincts."""
    models = _fixture_22()
    for i in range(3):
        models[0]["ttc"] = 8100 + i
        assert client.post(
            "/api/catalogue-pac", json=models, headers={"If-Match": _version(client)}
        ).status_code == 200
    assert _nb_backups() == 3


# --------------------------------------------------------------------------
# Auth (correction obligatoire du point 4)
# --------------------------------------------------------------------------

def _session_non_admin():
    main._write_users([{"username": "commercial1", "role": "commercial", "actif": True}])
    token = main._sign_session("commercial1", "commercial", int(time.time()))
    return {main.SESSION_COOKIE: token}


def _session_admin():
    main._write_users([{"username": "boss", "role": "admin", "actif": True}])
    return {main.SESSION_COOKIE: main._sign_session("boss", "admin", int(time.time()))}


@pytest.fixture
def client_auth(monkeypatch):
    monkeypatch.setenv("AUTH_ENFORCE", "1")
    os.makedirs(main.DATA_DIR, exist_ok=True)
    main._atomic_write_json(main.CATALOGUE_PAC_PATH, _fixture_22())
    shutil.rmtree(main.CATALOGUE_BACKUP_DIR, ignore_errors=True)
    return TestClient(main.app)


def test_non_admin_403_sur_import_xlsx_merge(client_auth):
    """La route etait hors perimetre : _auth_is_admin_only testait l'egalite stricte du chemin."""
    r = client_auth.post(
        "/api/catalogue-pac/import-xlsx-merge",
        files={"file": ("c.xlsx", b"nonvide", "application/vnd.ms-excel")},
        cookies=_session_non_admin(),
    )
    assert r.status_code == 403
    assert r.json()["detail"] == "Accès administrateur requis"


def test_non_admin_403_sur_storage_status(client_auth):
    r = client_auth.get("/api/admin/storage-status", cookies=_session_non_admin())
    assert r.status_code == 403
    assert r.json()["detail"] == "Accès administrateur requis"


def test_non_admin_403_sur_post_catalogue(client_auth):
    r = client_auth.post(
        "/api/catalogue-pac", json=_fixture_22(), cookies=_session_non_admin()
    )
    assert r.status_code == 403


def test_admin_passe_le_middleware_sur_storage_status(client_auth):
    """Contre-epreuve : la garde ne bloque pas un admin."""
    r = client_auth.get("/api/admin/storage-status", cookies=_session_admin())
    assert r.status_code == 200
    assert r.json()["catalogue_modeles"] == 22


def test_storage_status_hors_depot_en_test(client):
    r = client.get("/api/admin/storage-status")
    assert r.status_code == 200
    body = r.json()
    assert body["dans_le_depot"] is False
    assert body["catalogue_version"]


# --------------------------------------------------------------------------
# Import Excel en fusion
# --------------------------------------------------------------------------

def _classeur(lignes_modeles):
    """Construit un xlsx au format attendu par parse_catalogue_xlsx_report."""
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.title = "PAC"
    ws.append(["Champ"] + [m["nom"] for m in lignes_modeles])
    ws.append(["Niveau sonore"] + ["42 dB" for _ in lignes_modeles])
    ws.append(["source"] + ["" for _ in lignes_modeles])
    ws.append(["Ref interne"] + [m["ref"] for m in lignes_modeles])
    ws.append(["Nom commerciale"] + [m["nom"] for m in lignes_modeles])
    ws.append(["Usage"] + ["Chauffage" for _ in lignes_modeles])
    ws.append(["Alimentation"] + ["Mono" for _ in lignes_modeles])
    ws.append(["Puissance kW (35°C)"] + [m["puiss"] for m in lignes_modeles])
    ws.append(["Prix achat HT"] + [m["ttc"] * 0.55 for m in lignes_modeles])
    ws.append(["Prix vente TTC"] + [m["ttc"] for m in lignes_modeles])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_import_merge_apercu_n_ecrit_rien(client):
    xlsx = _classeur([{"ref": "NOUVEAU-1", "nom": "Nouveau 1", "ttc": 9000, "puiss": 11}])
    r = client.post(
        "/api/catalogue-pac/import-xlsx-merge",
        files={"file": ("c.xlsx", xlsx, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["confirmed"] is False
    assert body["ajouts"] == ["NOUVEAU-1"]
    assert body["total_apres"] == 23
    assert len(_sur_disque()) == 22  # rien ecrit


def test_import_merge_ajoute_sans_supprimer(client):
    xlsx = _classeur([{"ref": "NOUVEAU-1", "nom": "Nouveau 1", "ttc": 9000, "puiss": 11}])
    r = client.post(
        "/api/catalogue-pac/import-xlsx-merge",
        files={"file": ("c.xlsx", xlsx, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        data={"confirm": "1"},
    )
    assert r.status_code == 200, r.text
    disque = _sur_disque()
    assert len(disque) == 23
    # les 3 incomplets sont toujours la : un import ne supprime jamais
    assert {m["ref"] for m in disque} >= set(REFS_INCOMPLETS)


def test_import_merge_met_a_jour_sans_doublon(client):
    xlsx = _classeur([{"ref": "ATL-EXCELLIA-S-0", "nom": "Renomme", "ttc": 11111, "puiss": 9}])
    r = client.post(
        "/api/catalogue-pac/import-xlsx-merge",
        files={"file": ("c.xlsx", xlsx, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        data={"confirm": "1"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["mises_a_jour"] == ["ATL-EXCELLIA-S-0"]
    disque = _sur_disque()
    assert len(disque) == 22
    cible = next(m for m in disque if m["ref"] == "ATL-EXCELLIA-S-0")
    assert cible["ttc"] == 11111
    assert cible["nom"] == "Renomme"


def test_import_xlsx_total_reste_desactive(client):
    r = client.post(
        "/api/catalogue-pac/import-xlsx",
        files={"file": ("c.xlsx", b"x", "application/vnd.ms-excel")},
    )
    assert r.status_code == 410


# --------------------------------------------------------------------------
# Champs de tracabilite + garde volume
# --------------------------------------------------------------------------

def test_champs_tracabilite_optionnels():
    """Les 3 champs ajoutes valent None quand l'Excel ne les fournit pas."""
    from services.import_catalogue_pac import parse_catalogue_xlsx_report

    xlsx = _classeur([{"ref": "X-1", "nom": "X 1", "ttc": 9000, "puiss": 10}])
    models, _ = parse_catalogue_xlsx_report(io.BytesIO(xlsx))
    assert models[0]["ref_fabricant"] is None
    assert models[0]["eprel"] is None
    assert models[0]["agrement"] is None


def test_norm_label_tolere_apostrophe_typographique():
    from services.import_catalogue_pac import _norm_label

    assert _norm_label("Numéro d’agrément") == _norm_label("Numéro d'agrément")


def test_garde_volume_alerte_si_data_dir_dans_le_depot(monkeypatch, capsys):
    monkeypatch.setenv("RAILWAY_ENVIRONMENT", "production")
    monkeypatch.setattr(main, "DATA_DIR", os.path.join(main.BASE_DIR, "data"))
    monkeypatch.setattr(main, "_init_storage", lambda: None)

    import asyncio

    asyncio.run(main.startup_event())
    assert "CRITICAL" in capsys.readouterr().out


def test_garde_volume_silencieuse_sur_volume_externe(monkeypatch, capsys):
    monkeypatch.setenv("RAILWAY_ENVIRONMENT", "production")
    monkeypatch.setattr(main, "DATA_DIR", main.DATA_DIR)  # le tmpdir des tests
    monkeypatch.setattr(main, "_init_storage", lambda: None)

    import asyncio

    asyncio.run(main.startup_event())
    assert "CRITICAL" not in capsys.readouterr().out
