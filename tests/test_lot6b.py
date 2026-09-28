# -*- coding: utf-8 -*-
"""Lot 6b : zone climatique officielle (CEE et puissance, jamais la zone du DPE), délégataire CEE selon le choix de
démarrage, dates en jj/mm/aaaa, reprise des années de construction à 8 chiffres."""
import re
import time

import pytest
from fastapi.testclient import TestClient

import main
from services import service_devis as sd

# Répartition officielle (ecologie.gouv.fr, « Répartition des départements par zone climatique »)
H1 = "01 02 03 05 08 10 14 15 19 21 23 25 27 28 38 39 42 43 45 51 52 54 55 57 58 59 60 61 62 63 67 68 69 70 71 73 74 75 76 77 78 80 87 88 89 90 91 92 93 94 95"
H2 = "04 07 09 12 16 17 18 22 24 26 29 31 32 33 35 36 37 40 41 44 46 47 48 49 50 53 56 64 65 72 79 81 82 84 85 86"
H3 = "06 11 13 2A 2B 30 34 66 83"
LEAD = {"numero": "PR-06060", "civilite": "Madame", "nom": "Zone", "prenom": "Zoe", "telephone": "0611121317", "email": "z@x.fr",
        "adresse_chantier": "1 rue A", "cp_chantier": "53000", "code_postal_chantier": "53000", "ville_chantier": "Laval",
        "type_logement": "maison", "surface_logement_m2": "120", "hsp": "2,5", "mode_chauffage": "fioul", "ecs": "chaudiere",
        "type_emetteurs": "radiateurs_classiques", "alimentation_electrique": "monophase", "categorie": "tres_modeste",
        "nombre_personnes": "4", "cout_energetique_mensuel_eur": "400", "cout_energie_source": "reel"}
DELEG = [{"nom": "PICOTY", "mwh_precaire": 12.5, "mwh_classique": 7.2, "actif": False},
         {"nom": "ACE", "mwh_precaire": 14, "mwh_classique": 7.5, "actif": True}]


@pytest.fixture
def client():
    return TestClient(main.app)


def _jeton_admin():
    p = f"admin:{int(time.time())}"
    return f"{p}.{main._sign_admin_token(p)}"


# ---------------------------------------------------------------- 1. zone climatique officielle
def test_table_officielle_complete():
    attendu = {**{d: "H1" for d in H1.split()}, **{d: "H2" for d in H2.split()}, **{d: "H3" for d in H3.split()}}
    assert len(attendu) == 96
    assert {d: sd.DEPT_ZONE[d] for d in attendu} == attendu
    assert sd.DEPT_ZONE["20"] == "H3"                        # « 20 Corse » dans le texte


@pytest.mark.parametrize("cp, zone", [("06000", "H3"), ("75002", "H1"), ("53000", "H2"), ("11000", "H3"), ("84000", "H2"),
                                      ("36000", "H2"), ("87000", "H1"), ("20090", "H3"), ("20200", "H3"), ("97400", "H3"),
                                      ("97500", "H1")])
def test_zone_du_code_postal(cp, zone):
    assert sd.calculer_zone_climatique(cp) == zone
    assert main._zone_depuis_cp({"cp_chantier": cp}) == zone


def test_zone_du_dpe_jamais_utilisee():
    admin = dict(main._admin_payload_with_m3(), delegataires=DELEG)
    base = dict(LEAD, cp_chantier="06000", code_postal_chantier="06000")
    r1 = sd.calculer_cee_bar_th_171(base, {}, admin)
    r2 = sd.calculer_cee_bar_th_171(dict(base, zone_climatique_chantier="H1a", zone_climatique="H1"), {}, admin)
    assert r1["details"]["zone"] == r2["details"]["zone"] == "H3" and r1["montant"] == r2["montant"]
    # Lot 6c : la puissance garde la table d'avant (sous-zone du département) — voir tests/test_lot6c.py


# ---------------------------------------------------------------- 10. délégataire CEE selon le choix de démarrage
@pytest.mark.parametrize("categorie, cle", [("tres_modeste", "mwh_precaire"), ("modeste", "mwh_classique")])
def test_delegataire_attente_picoty_tout_de_suite_ace(categorie, cle):
    admin = dict(main._admin_payload_with_m3(), delegataires=DELEG)
    lead = dict(LEAD, categorie=categorie)
    att = sd.calculer_cee_bar_th_171(lead, {"mode_mpr": "attente"}, admin)
    tds = sd.calculer_cee_bar_th_171(lead, {"mode_mpr": "sans_attente"}, admin)
    assert att["details"]["delegataire"] == "PICOTY" and tds["details"]["delegataire"] == "ACE"
    assert att["details"]["prix_unitaire"] == DELEG[0][cle] and tds["details"]["prix_unitaire"] == DELEG[1][cle]
    assert tds["montant"] > att["montant"]
    assert att["montant"] / tds["montant"] == pytest.approx(DELEG[0][cle] / DELEG[1][cle])


def test_delegataire_sans_mpr_ace_et_repli_si_tarif_vide():
    admin = dict(main._admin_payload_with_m3(), delegataires=DELEG)
    sup = sd.calculer_cee_bar_th_171(dict(LEAD, categorie="superieur"), {"mode_mpr": "attente"}, admin)
    assert sup["details"]["delegataire"] == "ACE"            # pas de MaPrimeRénov' : ACE même en « attente »
    vide = [DELEG[0], dict(DELEG[1], mwh_precaire="", mwh_classique="")]
    r = sd.calculer_cee_bar_th_171(LEAD, {"mode_mpr": "sans_attente"}, dict(admin, delegataires=vide))
    assert r["details"]["delegataire"] == "PICOTY" and "non renseigné" in r["details"]["alerte_delegataire"]


def test_delegataires_lus_avec_usage_et_ace_cree_vide():
    main._atomic_write_json(main.DELEGATAIRES_PATH, [{"nom": "PICOTY", "mwh_precaire": 12.5, "mwh_classique": 7.2, "actif": True}])
    d = main._read_delegataires()
    assert d[0]["usage"] == "attente"
    assert {k: d[1][k] for k in ("nom", "mwh_precaire", "mwh_classique", "actif", "usage")} ==         {"nom": "ACE", "mwh_precaire": "", "mwh_classique": "", "actif": False, "usage": "tout_de_suite"}
    main._atomic_write_json(main.DELEGATAIRES_PATH, DELEG)
    assert [x["usage"] for x in main._read_delegataires()] == ["attente", "tout_de_suite"]


def test_devis_suit_le_delegataire(client):
    main._atomic_write_json(main.DELEGATAIRES_PATH, DELEG)
    main._atomic_write_json(main.LEADS_PATH, [dict(LEAD, categorie="modeste")])      # modeste : pas d'écrêtement ici
    montants = {}
    for mode in ("attente", "sans_attente"):
        main._atomic_write_json(main._state_simulateur_path(LEAD["numero"]), {})
        main.save_state_simulateur_atomic(LEAD["numero"], {"service": "chauffage_seul", "option": "opt1", "mode_mpr": mode, "prix_pac": 20000})
        ctx = main._build_devis_context(None, LEAD["numero"])
        montants[mode] = float(re.sub(r"[^\d,]", "", ctx["montant_cee"]).replace(",", "."))
    assert montants["sans_attente"] > montants["attente"] > 0
    # mention RAI du devis : le délégataire qui valorise la prime
    for mode, attendu in (("attente", "versée par PICOTY"), ("sans_attente", "offerte par ACE ÉNERGIE")):   # Lot 6e : mention PICOTY complète
        main._atomic_write_json(main._state_simulateur_path(LEAD["numero"]), {})
        main.save_state_simulateur_atomic(LEAD["numero"], {"service": "chauffage_seul", "option": "opt1", "mode_mpr": mode})
        assert attendu in client.get(f"/api/devis/{LEAD['numero']}/preview?variante=devis").text


# ---------------------------------------------------------------- 4. dates en jj/mm/aaaa
def test_dates_francaises():
    # Partie B : le message de la recherche DPE (services/dpe_audit) remplace _doc_status, date toujours en jj/mm/aaaa
    c = main.dpe_audit.candidat({"numero_dpe": "2506E3080625Z", "date_etablissement_dpe": "2025-09-29"}, "dpe", "")
    assert (c["date_fr"], c["valeurs"]["dpe_date"]) == ("29/09/2025", "29/09/2025")
    assert main._date_heure_fr("2025-09-29T10:12:00+02:00") == "29/09/2025 à 10h12"


# ---------------------------------------------------------------- 6. reprise des années à 8 chiffres
def test_reprise_annee_dry_run_puis_appliquee(client):
    main._atomic_write_json(main.LEADS_PATH, [dict(LEAD, annee_construction="19481974"), dict(LEAD, numero="PR-06061", annee_construction="1968")])
    assert client.post("/api/admin/reprise-annee", json={}).status_code == 401
    h = {"X-Admin-Token": _jeton_admin()}
    r = client.post("/api/admin/reprise-annee", json={}, headers=h).json()
    assert r["appliquer"] is False and r["nombre"] == 1 and r["leads"][0]["periode"] == "1948-1974"
    assert main._read_leads()[0]["annee_construction"] == "19481974"          # dry-run : rien d'écrit
    r = client.post("/api/admin/reprise-annee", json={"appliquer": True}, headers=h).json()
    assert r["nombre"] == 1
    leads = main._read_leads()
    assert leads[0]["annee_construction"] == "" and leads[0]["periode_construction"] == "1948-1974"
    assert leads[1]["annee_construction"] == "1968"
