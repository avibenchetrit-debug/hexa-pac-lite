# -*- coding: utf-8 -*-
"""Partie B : recherche DPE / audit portée du Master (services/dpe_audit). Aucun appel réseau : l'ADEME et la BAN
sont remplacées par des lignes au schéma réel de l'API (clés en minuscules, relevées le 28/09/2026)."""
import urllib.parse

import pytest
from fastapi.testclient import TestClient

import main
from services import dpe_audit as da

LAT, LON = 48.8660, 2.3410          # point BAN de « 12 rue Imaginaire 75002 »
ADRESSE = "12 RUE IMAGINAIRE"


def dpe(numero, num_voie="12", rue="Rue Imaginaire", d_m=3.0, date="2024-03-15", **kw):
    lat = LAT + d_m / 111_000
    row = {"numero_dpe": numero, "date_etablissement_dpe": date, "etiquette_dpe": "E", "etiquette_ges": "E",
           "type_batiment": "maison", "methode_application_dpe": "dpe maison individuelle",
           "surface_habitable_logement": 118.4, "hauteur_sous_plafond": 2.5, "nombre_niveau_logement": 2,
           "annee_construction": "", "periode_construction": "1948-1974",
           "conso_5_usages_par_m2_ep": 287.6, "emission_ges_5_usages_par_m2": 61.2,
           "cout_total_5_usages": 3600.0, "cout_chauffage": 2280.0, "cout_ecs": 360.0,
           "type_energie_principale_chauffage": "Gaz naturel",
           "qualite_isolation_murs": "insuffisante", "qualite_isolation_plancher_haut_comble_perdu": "très bonne",
           "qualite_isolation_menuiseries": "moyenne",
           "adresse_ban": f"{num_voie} {rue} 75002 Paris", "numero_voie_ban": num_voie, "nom_rue_ban": rue,
           "_geopoint": f"{lat},{LON}"}
    row.update(kw)
    return row


def audit(numero, etape="état initial", **kw):
    row = {"n_audit": numero, "date_etablissement_audit": "2025-01-10", "classe_bilan_dpe": "F",
           "etape_travaux": etape, "categorie_scenario": etape if etape == "état initial" else 'scénario multi étapes "principal"',
           "methode_application_dpe": "dpe maison individuelle", "surface_habitable_logement": 120,
           "hauteur_sous_plafond": 2.6, "nb_niveau_logement": 1, "annee_construction": 1965,
           "ep_conso_5_usages_m2": 331, "emission_ges_5_usages_m2": 70,
           "cout_5_usages": 4100, "cout_ch": 2900, "cout_ecs": 460, "type_energie_principale_chauffage": "Fioul domestique",
           "qualite_isolation_murs": "bonne", "qualite_isolation_plancher_haut_toit_terrasse": "moyenne",
           "qualite_isolation_menuiseries": "insuffisante",
           "adresse_ban": "12 Rue Imaginaire 75002 Paris", "n_voie_ban": "12", "nom_voie_ban": "Rue Imaginaire",
           "_geopoint": f"{LAT},{LON}"}
    row.update(kw)
    return row


@pytest.fixture
def ademe(monkeypatch):
    """Réponses simulées : ademe['dpe'], ademe['audit'] (listes ou exception), ademe['ban']."""
    donnees = {"dpe": [], "audit": [], "ban": {"features": [{"geometry": {"coordinates": [LON, LAT]}}]}, "urls": []}

    def get(url, timeout):
        donnees["urls"].append(url)
        cle = "ban" if "api-adresse" in url else ("audit" if "audit-opendata" in url else "dpe")
        v = donnees[cle]
        if isinstance(v, Exception):
            raise v
        return v if cle == "ban" else {"results": v}
    monkeypatch.setattr(da, "GET", get)
    return donnees


def chercher(**kw):
    kw.setdefault("lat", LAT)
    kw.setdefault("lon", LON)
    return da.rechercher(kw.pop("adresse", ADRESSE), kw.pop("cp", "75002"), **kw)


# ---------------------------------------------------------------- un document confirmé -> rempli
def test_un_document_a_adresse_confirmee_est_retenu_et_traduit(ademe):
    ademe["dpe"] = [dpe("2475E0000001A")]
    r = chercher()
    assert r["etat"] == "auto" and r["retenu"] == 0
    c = r["candidats"][0]
    assert c["identite"] == "adresse_ok" and not c["immeuble"]
    assert c["valeurs"] == {"type_logement": "maison", "surface_logement_m2": "118", "annee_construction": "",
                            "hsp": "2,5", "conso_kwh_m2": "288", "emissions_ges": "61", "dpe_connu": "E",
                            "nb_niveaux": "2", "mode_chauffage": "gaz", "dpe_numero": "2475E0000001A",
                            "dpe_date": "15/03/2024", "dpe_source": "ademe"}
    assert c["cout_mensuel"] == round((2280 + 360) / 12) == 220           # chauffage + eau chaude, pas 3600/12
    assert c["isolation"] == {"toit": "bien", "mur": "non", "fenetres": ""}   # moyenne -> fenêtres vides
    assert c["periode"] == "1948-1974"                                       # période : année vide, période au bandeau
    assert "DPE n° 2475E0000001A du 15/03/2024" in r["message"]
    # paramètres ADEME du Master : point BAN, 50 m, audits « état initial »
    q = urllib.parse.parse_qs(urllib.parse.urlparse(ademe["urls"][-1]).query)
    assert any("geo_distance" in u for u in ademe["urls"])
    assert all(f"{LON},{LAT},50m" in urllib.parse.unquote(u) for u in ademe["urls"])
    assert q  # (lecture de l'URL possible)


def test_audit_seul_valeurs_de_l_etat_initial_jamais_une_etape(ademe):
    ademe["audit"] = [audit("A0001", etape="étape finale", classe_bilan_dpe="B", ep_conso_5_usages_m2=90),
                      audit("A0001")]
    r = chercher()
    assert r["etat"] == "auto"
    c = r["candidats"][r["retenu"]]
    assert c["kind"] == "audit" and c["classe"] == "F" and c["valeurs"]["conso_kwh_m2"] == "331"
    assert c["valeurs"]["annee_construction"] == "1965" and c["periode"] == ""
    assert c["valeurs"]["mode_chauffage"] == "fioul" and c["valeurs"]["dpe_source"] == "ademe_audit"
    assert c["cout_mensuel"] == round((2900 + 460) / 12)                     # cout_ch + cout_ecs de l'audit
    assert c["isolation"] == {"toit": "peu", "mur": "bien", "fenetres": "simple"}


def test_cout_absent_si_le_document_n_a_pas_chauffage_et_eau_chaude(ademe):
    ademe["dpe"] = [dpe("2475E0000001A", cout_chauffage=None, cout_ecs=None)]
    assert chercher()["candidats"][0]["cout_mensuel"] is None                # jamais le total 5 usages


# ---------------------------------------------------------------- plusieurs documents du même logement : le plus récent
def test_plusieurs_dpe_du_meme_logement_le_plus_recent_gagne(ademe):
    ademe["dpe"] = [dpe("2375E0000002B", date="2023-05-02"), dpe("2475E0000001A")]
    r = chercher()
    assert r["etat"] == "auto" and r["candidats"][r["retenu"]]["numero"] == "2475E0000001A"
    assert "retenu, le plus récent des 2 documents à cette adresse" in r["message"]
    assert {c["numero"] for c in r["candidats"]} == {"2475E0000001A", "2375E0000002B"}   # l'autre reste proposé


@pytest.mark.parametrize("date_dpe, date_audit, gagnant, cout", [
    ("2025-06-01", "2025-01-10", "dpe", round((2280 + 360) / 12)),      # DPE plus récent -> DPE (et son coût)
    ("2024-03-15", "2025-01-10", "audit", round((2900 + 460) / 12)),    # audit plus récent -> audit
    ("2025-01-10", "2025-01-10", "audit", round((2900 + 460) / 12)),    # même date -> audit
])
def test_dpe_et_audit_du_meme_logement_la_date_decide(ademe, date_dpe, date_audit, gagnant, cout):
    ademe["dpe"], ademe["audit"] = [dpe("2475E0000001A", date=date_dpe)], [audit("A0001", date_etablissement_audit=date_audit)]
    r = chercher()
    c = r["candidats"][r["retenu"]]
    assert r["etat"] == "auto" and c["kind"] == gagnant and c["cout_mensuel"] == cout
    assert ("l'audit prime" in r["message"]) is (date_dpe == date_audit)


def test_plusieurs_documents_dont_un_immeuble_choix(ademe):
    ademe["dpe"] = [dpe("2475E0000001A"), dpe("2375E0000002B", date="2023-05-02", type_batiment="appartement")]
    assert chercher()["etat"] == "choix"


# ---------------------------------------------------------------- immeuble -> jamais automatique
@pytest.mark.parametrize("champs", [
    {"type_batiment": "appartement", "methode_application_dpe": "dpe appartement individuel"},
    {"type_batiment": "appartement", "methode_application_dpe": "dpe appartement généré à partir des données DPE immeuble"},
    {"type_batiment": "immeuble", "methode_application_dpe": "dpe immeuble collectif"},
])
def test_immeuble_jamais_automatique(ademe, champs):
    ademe["dpe"] = [dpe("2475E0000001A", numero_etage_appartement="3", **champs)]
    r = chercher()
    assert r["etat"] == "choix" and r["retenu"] is None and "Immeuble" in r["message"]
    assert r["candidats"][0]["etage"] == "3"


def test_prospect_en_appartement_jamais_automatique(ademe):
    ademe["dpe"] = [dpe("2475E0000001A")]
    assert chercher(type_logement="appartement")["etat"] == "choix"


# ---------------------------------------------------------------- jamais le voisin
@pytest.mark.parametrize("num_voie, rue, adresse_ban", [
    ("14", "Rue Imaginaire", "14 Rue Imaginaire 75002 Paris"),               # autre numéro
    ("12", "Rue Imaginaire", "12 Bis Rue Imaginaire 75002 Paris"),           # 12 bis n'est pas 12
    ("12", "Avenue Voisine", "12 Avenue Voisine 75002 Paris"),               # même numéro, autre rue
])
def test_le_voisin_est_ecarte(ademe, num_voie, rue, adresse_ban):
    ademe["dpe"] = [dpe("2475E0000009Z", num_voie=num_voie, rue=rue, adresse_ban=adresse_ban)]
    r = chercher()
    assert r["etat"] == "aucun" and r["candidats"] == []


def test_abreviation_et_adresse_complete_avec_cp_restent_compatibles(ademe):
    ademe["dpe"] = [dpe("2475E0000001A")]
    assert chercher(adresse="12 r. Imaginaire 75002 PARIS")["etat"] == "auto"


def test_sans_numero_exploitable_proposition_a_verifier(ademe):
    ademe["dpe"] = [dpe("2475E0000001A", numero_voie_ban="", adresse_ban="Rue Imaginaire 75002 Paris", d_m=30)]
    r = chercher()
    assert r["etat"] == "choix" and r["candidats"][0]["identite"] == "distance"
    assert "seulement à proximité" in r["message"] and r["candidats"][0]["distance_m"] == 30


def test_documents_anterieurs_au_1er_juillet_2021_et_trop_loin_ignores(ademe):
    ademe["dpe"] = [dpe("2175E0000001A", date="2021-06-30"), dpe("2475E0000001A", d_m=80)]
    assert chercher()["etat"] == "aucun"


def test_annee_de_construction_reelle_gardee(ademe):
    ademe["dpe"] = [dpe("2475E0000001A", annee_construction="1972")]
    c = chercher()["candidats"][0]
    assert c["valeurs"]["annee_construction"] == "1972" and c["periode"] == ""


# ---------------------------------------------------------------- erreurs, géocodage
def test_ademe_injoignable_message_clair(ademe):
    ademe["dpe"] = ademe["audit"] = TimeoutError()
    r = chercher()
    assert r["etat"] == "erreur" and "l'ADEME ne répond pas" in r["message"]


def test_un_seul_jeu_injoignable_est_signale(ademe):
    ademe["audit"] = TimeoutError()
    ademe["dpe"] = [dpe("2475E0000001A")]
    r = chercher()
    assert r["etat"] == "auto" and "les audits n'ont pas pu être consultés" in r["message"]


def test_geocodage_ban_si_pas_de_point(ademe):
    ademe["dpe"] = [dpe("2475E0000001A")]
    r = da.rechercher(ADRESSE, "75002")
    assert r["etat"] == "auto" and any("api-adresse" in u for u in ademe["urls"])
    ademe["ban"] = {"features": []}
    r = da.rechercher(ADRESSE, "75002")
    assert r["etat"] == "erreur" and "introuvable dans la Base Adresse Nationale" in r["message"]


def test_route_dpe_lookup(ademe):
    ademe["dpe"] = [dpe("2475E0000001A")]
    r = TestClient(main.app).get("/api/dpe-lookup", params={"adresse": ADRESSE, "cp": "75002", "lat": LAT, "lon": LON})
    assert r.status_code == 200 and r.json()["etat"] == "auto"
