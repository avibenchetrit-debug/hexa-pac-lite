# -*- coding: utf-8 -*-
"""Catalogue : « Classe du régulateur (ErP) » puis « Contribution à l'efficacité saisonnière (%) » juste après
« Alimentation » dans la fiche produit de chaque PAC (valeurs du Master si absentes ou vides, valeur saisie gardée et
seulement replacée), migration au démarrage idempotente ; devis Thaleos avec la ligne du régulateur sans alerte ;
dossiers facturés intacts. Fiches clients fabriquées ici : aucune donnée réelle."""
import copy
import hashlib
import json
import os

import pytest

import main
import test_lot7a_documents as docs
from services.catalogue_regulateur import CHAMP_CLASSE, CHAMP_CONTRIBUTION, VALEURS_MASTER, migrer_catalogue

NUM = docs.LEAD["numero"]


def _fiche(marque, ref, eprel, regulateur=None, avant=True):
    """Même forme que le catalogue de prod : Marque, Gamme, Référence, Technologie, Usage, Alimentation, …"""
    specs = [{"champ": "Marque", "valeur": marque}, {"champ": "Gamme", "valeur": "G"}, {"champ": "Référence", "valeur": ref},
             {"champ": "Technologie", "valeur": "PAC air/eau"}, {"champ": "Usage", "valeur": "Chauffage seul"},
             {"champ": "Alimentation", "valeur": "Monophasé"}, {"champ": "Temp. max de départ (°C)", "valeur": "60"},
             {"champ": "Fluide frigorigène", "valeur": "R32"}, {"champ": "ETAS chauffage 35°C / 55°C (%)", "valeur": "178 / 151"},
             {"champ": "Référence EPREL", "valeur": eprel}]
    if regulateur:
        lignes = [{"champ": CHAMP_CLASSE, "valeur": regulateur[0]}, {"champ": CHAMP_CONTRIBUTION, "valeur": regulateur[1]}]
        specs = specs[:6] + lignes + specs[6:] if avant else specs + lignes
    return {"ref": ref, "nom": ref, "marque": marque, "usage": "Chauffage seul", "alim": "Monophasé", "puiss35": 12.0,
            "puiss_chauf": 12.0, "etas35": 178, "etas55": 151, "achat": 5000, "ttc": 15990, "eprel": eprel,
            "description_technique": "", "description_specs": specs}


CATALOGUE = [
    _fiche("ATLANTIC", "ATL-EXCELLIA-S-9", "520556", ("VI", "4")),
    _fiche("DAIKIN", "DAI-ALTHERMA-3HHT-R32-14", "1627026", ("VI", "4")),
    _fiche("ARISTON", "ARI-NIMBUS-NET-R32-8", "1252273", ("VI", "4")),
    _fiche("THALEOS", "THA-MTBL-R290-12", "2639887"),                         # sans les deux lignes (état de prod)
]


def _champs(m):
    return [s["champ"] for s in m["description_specs"]]


def _apres_alimentation(m):
    c = _champs(m)
    i = c.index("Alimentation")
    return m["description_specs"][i + 1:i + 3]


# ── la règle ─────────────────────────────────────────────────────────────────────────────────────────────────────
def test_chaque_marque_les_deux_lignes_juste_apres_alimentation():
    avant = copy.deepcopy(CATALOGUE)
    neuf, change, manques = migrer_catalogue(CATALOGUE)
    assert CATALOGUE == avant and change and manques == {}
    for m in neuf:
        assert _apres_alimentation(m) == [{"champ": CHAMP_CLASSE, "valeur": "VI"}, {"champ": CHAMP_CONTRIBUTION, "valeur": "4"}], m["ref"]
        assert _champs(m).count(CHAMP_CLASSE) == 1 and _champs(m).count(CHAMP_CONTRIBUTION) == 1
    assert neuf[:3] == CATALOGUE[:3]                                    # Ariston, Atlantic, Daikin : déjà en place


def test_aucun_autre_champ_modifie():
    neuf, _, _ = migrer_catalogue(CATALOGUE)
    for a, b in zip(CATALOGUE, neuf):
        assert {k: v for k, v in a.items() if k != "description_specs"} == {k: v for k, v in b.items() if k != "description_specs"}
        hors = lambda m: [s for s in m["description_specs"] if s["champ"] not in (CHAMP_CLASSE, CHAMP_CONTRIBUTION)]
        assert hors(a) == hors(b)


def test_valeur_deja_saisie_gardee_et_seulement_replacee():
    m = _fiche("THALEOS", "THA-MTBL-R290-12", "2639887", ("V", "3"), avant=False)   # en fin de fiche, autre valeur
    neuf, change, _ = migrer_catalogue([m])
    assert change and _apres_alimentation(neuf[0]) == [{"champ": CHAMP_CLASSE, "valeur": "V"}, {"champ": CHAMP_CONTRIBUTION, "valeur": "3"}]


def test_ligne_vide_remplie_par_le_master():
    m = _fiche("THALEOS", "THA-MTBL-R290-12", "2639887", ("", "4"))
    neuf, _, manques = migrer_catalogue([m])
    assert _apres_alimentation(neuf[0])[0] == {"champ": CHAMP_CLASSE, "valeur": "VI"} and manques == {}


def test_sans_equivalent_certain_rien_n_est_invente():
    m = _fiche("THALEOS", "THA-MTBL-R290-DUO-8", "")                  # le Master n'a pas de n° EPREL pour lui
    neuf, change, manques = migrer_catalogue([m])
    assert not change and neuf[0] is m and manques == {"THA-MTBL-R290-DUO-8": [CHAMP_CLASSE, CHAMP_CONTRIBUTION]}


def test_idempotente():
    une, _, _ = migrer_catalogue(CATALOGUE)
    deux, change, _ = migrer_catalogue(une)
    assert not change and deux == une


def test_table_du_master_38_modeles_classe_vi_contribution_4():
    assert len(VALEURS_MASTER) == 38 and {(c, p) for _, c, p in VALEURS_MASTER.values()} == {("VI", "4")}
    assert sum(r.startswith("THA-MTBL-R290-") for r, _, _ in VALEURS_MASTER.values()) == 12


# ── migration au démarrage ───────────────────────────────────────────────────────────────────────────────────────
def test_migration_au_demarrage_ecrit_une_fois_avec_sauvegarde():
    main._atomic_write_json(main.CATALOGUE_PATH, CATALOGUE)
    sauvegardes = lambda: sorted(os.listdir(main.CATALOGUE_BACKUP_DIR)) if os.path.isdir(main.CATALOGUE_BACKUP_DIR) else []
    n0 = len(sauvegardes())
    assert main._migrate_catalogue_regulateur() == {}
    cat = main._read_catalogue_pac()
    assert all(_apres_alimentation(m)[0]["champ"] == CHAMP_CLASSE for m in cat)
    assert len(sauvegardes()) == n0 + 1                                 # l'ancien catalogue est sauvegardé
    octets = open(main.CATALOGUE_PATH, "rb").read()
    main._migrate_catalogue_regulateur()                                # 2e démarrage : rien ne bouge
    assert open(main.CATALOGUE_PATH, "rb").read() == octets and len(sauvegardes()) == n0 + 1
    src = open(main.__file__, encoding="utf-8").read()
    assert "    _migrate_leads_schema()\n    _migrate_catalogue_regulateur()\n" in src


# ── devis Thaleos : ligne du régulateur avec sa classe, sans alerte ─────────────────────────────────────────────
def _devis_thaleos():
    main._atomic_write_json(main.CATALOGUE_PATH, CATALOGUE)
    main._migrate_catalogue_regulateur()
    docs._preparer()
    etat = main._load_state_simulateur(NUM, {}, main._read_catalogue_pac()) or {}
    main.save_state_simulateur_atomic(NUM, dict(etat, modele_pac_id="THA-MTBL-R290-12"))
    ctx = main._build_devis_context(None, NUM, avec_sous_traitant=True)
    return main.templates.env.get_template("devis_pac.html").render(ctx)


def test_devis_thaleos_regulateur_classe_vi_sans_alerte():
    html = _devis_thaleos()
    t = docs._texte(html)
    assert "THA-MTBL-R290-12" in t or "THALEOS" in t
    assert "Installation et paramétrage du régulateur (classe VI)" in t
    assert "data-regulateur-manquant" not in html
    assert "Classe du régulateur (ErP) VI" in t and "Contribution à l'efficacité saisonnière (%) 4" in t


def test_devis_thaleos_avant_migration_avait_l_alerte():
    """Témoin : sans la migration, la fiche Thaleos de prod déclenche l'alerte orange."""
    main._atomic_write_json(main.CATALOGUE_PATH, CATALOGUE)
    docs._preparer()
    etat = main._load_state_simulateur(NUM, {}, main._read_catalogue_pac()) or {}
    main.save_state_simulateur_atomic(NUM, dict(etat, modele_pac_id="THA-MTBL-R290-12"))
    ctx = main._build_devis_context(None, NUM, avec_sous_traitant=True)
    assert "data-regulateur-manquant" in main.templates.env.get_template("devis_pac.html").render(ctx)


# ── dossiers facturés intacts ────────────────────────────────────────────────────────────────────────────────────
def test_dossier_facture_intact(monkeypatch):
    from fastapi.testclient import TestClient
    client = TestClient(main.app)
    main._atomic_write_json(main.CATALOGUE_PATH, CATALOGUE)              # catalogue d'avant la migration
    docs._preparer()
    etat = main._load_state_simulateur(NUM, {}, main._read_catalogue_pac()) or {}
    main.save_state_simulateur_atomic(NUM, dict(etat, modele_pac_id="THA-MTBL-R290-12"))
    main._atomic_write_json(main.COUNTERS_PATH, {"dossier": 0})
    monkeypatch.setattr(main, "_html_to_pdf_playwright", lambda html, request: b"%PDF-1.4 facture " + html.encode()[:64])
    monkeypatch.setattr(main, "_append_fiche_technique", lambda pdf, numero: pdf)
    monkeypatch.setattr(main, "_append_fiche_ballon", lambda pdf, numero: pdf)
    assert client.post(f"/api/facture/{NUM}", json={"date_fin_travaux": "2026-09-12"}).status_code == 200
    meta = copy.deepcopy(main._read_factures_meta())
    rec = meta[NUM][0]
    empreinte = hashlib.sha256(open(rec["file"], "rb").read()).hexdigest()
    lead = json.dumps(main._find_lead(NUM), sort_keys=True)
    assert main._dossier_fige(NUM)
    main._migrate_catalogue_regulateur()                                # le catalogue change…
    assert main._read_factures_meta() == meta                           # …la facture émise, non
    assert hashlib.sha256(open(rec["file"], "rb").read()).hexdigest() == empreinte
    assert json.dumps(main._find_lead(NUM), sort_keys=True) == lead
