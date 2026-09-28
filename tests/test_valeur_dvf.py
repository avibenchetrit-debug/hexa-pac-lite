# -*- coding: utf-8 -*-
"""Partie B : prix au m² DVF (services/valeur_dvf) — médiane, quartiles, source, cache, indisponibilité.
Aucun appel réseau : geo.api.gouv.fr et les fichiers DVF sont simulés."""
import json

import pytest
from fastapi.testclient import TestClient

import main
from services import valeur_dvf as vd

COMMUNES = json.dumps([{"nom": "Paris 2e Arrondissement", "code": "75102", "codeDepartement": "75"},
                       {"nom": "Paris", "code": "75056", "codeDepartement": "75"}])
ENTETE = "id_mutation,nature_mutation,valeur_fonciere,type_local,surface_reelle_bati\n"


def csv_ventes(prix_m2, type_local="Maison", surface=100, prefixe="m"):
    lignes = [f"{prefixe}{i},Vente,{p * surface},{type_local},{surface}" for i, p in enumerate(prix_m2)]
    return ENTETE + "\n".join(lignes) + "\n"


@pytest.fixture
def reseau(monkeypatch):
    rep = {"communes": COMMUNES, "annees": {}, "appels": []}

    def get(url, timeout=20.0):
        rep["appels"].append(url)
        if "geo.api.gouv.fr" in url:
            return rep["communes"]
        for annee, texte in rep["annees"].items():
            if f"/{annee}/communes/75/75102.csv" in url:
                return texte
        return None if rep.get("panne") else "<html>404</html>"
    monkeypatch.setattr(vd, "GET", get)
    return rep


def test_mediane_quartiles_et_phrase_de_source(reseau, tmp_path):
    reseau["annees"] = {2026: csv_ventes([8000, 9000, 10000]), 2025: csv_ventes([11000, 12000], prefixe="n"),
                        2024: csv_ventes([13000, 50000], prefixe="o")}           # 50 000 €/m² : aberrant, écarté
    r = vd.prix_m2("75002", "PARIS", "maison", cache=str(tmp_path), annee=2026)
    assert r["ok"] and r["nb"] == 6 and r["prix_m2"] == 10500
    assert (r["q1"], r["q3"]) == (9250, 11750)
    assert r["source"] == "médiane de 6 ventes de maisons à Paris 2e Arrondissement, 2024-2026"


def test_vente_de_plusieurs_locaux_ou_autre_type_ignoree(reseau):
    reseau["annees"] = {2026: ENTETE + "x,Vente,300000,Maison,100\nx,Vente,300000,Maison,90\n"
                              + csv_ventes([5000] * 5, type_local="Appartement", surface=50)[len(ENTETE):]}
    assert vd.prix_m2("75002", "Paris", "maison", annee=2026)["ok"] is False
    assert vd.prix_m2("75002", "Paris", "appartement", annee=2026)["prix_m2"] == 5000


def test_trop_peu_de_ventes_n_est_pas_une_panne(reseau):
    reseau["annees"] = {2026: csv_ventes([8000, 9000])}
    r = vd.prix_m2("75002", "Paris", "maison", annee=2026)
    assert r == {"ok": False, "indisponible": False,
                 "raison": "trop peu de ventes de maisons à Paris 2e Arrondissement dans les données DVF (2)"}


def test_dvf_indisponible(reseau):
    reseau["communes"] = None
    assert vd.prix_m2("75002", "Paris", "maison") == {"ok": False, "indisponible": True,
                                                      "raison": "données DVF indisponibles pour le moment"}
    reseau["communes"], reseau["panne"] = COMMUNES, True                   # la commune répond, pas les fichiers
    assert vd.prix_m2("75002", "Paris", "maison", annee=2026)["indisponible"] is True


def test_cache_30_jours(reseau, tmp_path):
    reseau["annees"] = {2026: csv_ventes([8000, 9000, 10000, 11000, 12000])}
    vd.prix_m2("75002", "Paris", "maison", cache=str(tmp_path), annee=2026)
    n = len(reseau["appels"])
    assert vd.prix_m2("75002", "Paris", "maison", cache=str(tmp_path), annee=2026)["prix_m2"] == 10000
    assert len(reseau["appels"]) == n                                        # tout vient du cache


def test_route_valeur_bien_dvf(reseau):
    reseau["annees"] = {2026: csv_ventes([8000, 9000, 10000, 11000, 12000])}
    r = TestClient(main.app).get("/api/valeur-bien/dvf", params={"cp": "75002", "ville": "PARIS", "type_logement": "maison"})
    assert r.status_code == 200 and r.json()["ok"] is True


def test_cache_dvf_hors_sauvegarde_github(tmp_path):
    from services import backup_github
    (tmp_path / "cache_dvf").mkdir()
    (tmp_path / "cache_dvf" / "75102_Maison.json").write_text("{}", encoding="utf-8")
    (tmp_path / "leads.json").write_text("[]", encoding="utf-8")
    assert list(backup_github._collect_json_files(str(tmp_path))) == ["leads.json"]
