# -*- coding: utf-8 -*-
"""Relances par source (Admin → Relances) : pour chaque famille (devis / pré-devis, NRP), les sources décochées ne sont
plus relancées, ni automatiquement ni à la main ; le filtre joue au moment de l'envoi. Provenance « Compleo » harmonisée
en « Compléo », import CSV sans nouvelle variante. Resend est simulé."""
import os
import re
import sys
import time
import types
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

import main


@pytest.fixture
def client():
    return TestClient(main.app)


@pytest.fixture(autouse=True)
def _donnees_restaurees():
    chemins = (main.LEADS_PATH, main.DEVIS_META_PATH, main.NOTES_PATH, main.PARAMETRES_ADMIN_PATH)
    sauve = {c: open(c, "rb").read() for c in chemins if os.path.exists(c)}
    absents = [c for c in chemins if not os.path.exists(c)]
    yield
    for c, octets in sauve.items():
        open(c, "wb").write(octets)
    for c in absents:
        if os.path.exists(c):
            os.remove(c)


# ---------- correction en base : Compleo -> Compléo ----------

def test_migration_compleo_vers_compleo_accentue_une_seule_fois():
    main._atomic_write_json(main.LEADS_PATH, [
        {"numero": "PR-1", "source": "Compleo"},
        {"numero": "PR-2", "source": " compleo "},
        {"numero": "PR-3", "source": "Compleo", "deleted_at": "2026-10-01T10:00:00+02:00"},
        {"numero": "PR-4", "source": "Compléo"},
        {"numero": "PR-5", "source": "Data Eva"},
        {"numero": "PR-6", "source": ""},
        {"numero": "PR-7"},
    ])
    assert main._migrate_sources_compleo() == 3
    sources = {l["numero"]: l.get("source") for l in main._read_leads()}
    assert sources == {"PR-1": "Compléo", "PR-2": "Compléo", "PR-3": "Compléo", "PR-4": "Compléo",
                       "PR-5": "Data Eva", "PR-6": "", "PR-7": None}
    assert main._migrate_sources_compleo() == 0                     # deuxième démarrage : rien à faire


# ---------- import CSV : l'orthographe existante, jamais une nouvelle variante ----------

def test_menu_provenance_identique_a_la_fiche():
    page = open(os.path.join(main.BASE_DIR, "templates", "index.html"), encoding="utf-8").read()
    menu = re.search(r'<select name="source" required>(.*?)</select>', page, re.S).group(1)
    assert [v for v in re.findall(r'<option value="([^"]*)"', menu) if v] == main.SOURCES_PROVENANCE


def test_import_csv_reprend_l_orthographe_existante(client):
    main._atomic_write_json(main.LEADS_PATH, [{"numero": "PR-1", "source": "Data Eva"},
                                              {"numero": "PR-2", "source": "Data"}])
    csv = ("nom;prenom;source\n"
           "A;a;compleo\nB;b;COMPLÉO \nC;c;data  eva\nD;d;DATA\nE;e;site-web\n"
           "F;f;Partenaire X\nG;g;partenaire x\nH;h;\n")
    r = client.post("/api/import-leads", files={"file": ("leads.csv", csv.encode("utf-8"), "text/csv")})
    assert r.status_code == 200 and r.json()["imported"] == 8, r.text
    sources = {l["nom"]: l["source"] for l in main._read_leads() if l.get("nom")}
    assert sources == {"A": "Compléo", "B": "Compléo", "C": "Data Eva", "D": "Data", "E": "Site web",
                       "F": "Partenaire X", "G": "Partenaire X", "H": ""}


# ---------- filtre des relances par source ----------

REQ = main._SchedulerRequest("https://exemple.invalid")


def _il_y_a(jours):
    return (datetime.now(main.PARIS_TZ) - timedelta(days=jours)).isoformat(timespec="seconds")


def _lead(numero, **k):
    base = {"numero": numero, "nom": "Essai", "prenom": "Marcel", "email": f"{numero.lower()}@example.invalid",
            "statut": "devis_envoye", "relances_actives": True}
    base.update(k)
    return base


def _semer(sources):
    """Par source : un lead avec un devis envoyé il y a 10 jours (relance devis due) et un lead NRP rappelé il y a
    5 jours (relance NRP due). None = pas de champ « source » du tout."""
    leads, meta = [], {}
    for i, src in enumerate(sources):
        champ = {} if src is None else {"source": src}
        dev, nrp = f"PR-{100 + i}", f"PR-{200 + i}"
        leads.append(_lead(dev, **champ))
        meta[dev] = [{"version": 1, "numero_devis": f"DE2026-{100 + i}-1", "variante": "devis", "sent_at": _il_y_a(10),
                      "email": f"{dev.lower()}@example.invalid", "statut": "envoye", "relance_count": 0,
                      "modele_pac": "PAC", "reste_a_charge": "1 000 €"}]
        leads.append(_lead(nrp, statut="rappeler", nrp_count=1, nrp_updated_at=_il_y_a(5), **champ))
    main._atomic_write_json(main.LEADS_PATH, leads)
    main._atomic_write_json(main.DEVIS_META_PATH, meta)
    main._atomic_write_json(main.NOTES_PATH, {})


@pytest.fixture
def envois(monkeypatch):
    out = []

    def send(msg):
        out.append(msg)
        return {"id": f"factice-{len(out)}"}

    faux = types.ModuleType("resend")
    faux.Emails = types.SimpleNamespace(send=send)
    monkeypatch.setitem(sys.modules, "resend", faux)
    monkeypatch.setenv("RESEND_API_KEY", "cle-factice-locale")
    monkeypatch.setattr(main, "_resend_dernier_evenement", lambda rid: "")
    monkeypatch.setattr(main, "_dernier_repondu", lambda numero: None)
    return out


def _admin():
    p = f"admin:{int(time.time())}"
    return {"X-Admin-Token": f"{p}.{main._sign_admin_token(p)}"}


def _decocher(client, famille, sources):
    route = "/api/admin/relances" if famille == "devis" else "/api/admin/relances-nrp"
    r = client.post(route, json={"sources_desactivees": sources}, headers=_admin())
    assert r.status_code == 200, r.text


def _a_faire():
    today = datetime.now(main.PARIS_TZ).date()
    return (sorted(it["numero"] for it in main._relances_a_faire(today)),
            sorted(it["numero"] for it in main._relances_nrp_a_faire(today)))


def _tout_envoyer():
    """Ce que fait le passage quotidien : la liste du jour, puis l'envoi de chaque relance."""
    today = datetime.now(main.PARIS_TZ).date()
    for it in main._relances_a_faire(today):
        main._send_relance(it["numero"], it["version"], REQ)
    for it in main._relances_nrp_a_faire(today):
        main._send_nrp_relance(it["numero"], REQ)


def _destinataires(envois):
    return sorted(m["to"][0].split("@")[0].upper() for m in envois)


def test_par_defaut_toutes_les_sources_sont_relancees(client, envois):
    _semer(["Compléo", "Data Eva", "", None])
    main._atomic_write_json(main.PARAMETRES_ADMIN_PATH, {})           # réglage jamais touché = comportement actuel
    assert _a_faire() == (["PR-100", "PR-101", "PR-102", "PR-103"], ["PR-200", "PR-201", "PR-202", "PR-203"])
    _tout_envoyer()
    assert len(envois) == 8


def test_source_decochee_aucune_relance_source_cochee_relance_envoyee(client, envois):
    _semer(["Compléo", "Data Eva"])
    _decocher(client, "devis", ["Compleo"])                          # n'importe quelle orthographe
    _decocher(client, "nrp", [])
    assert _a_faire() == (["PR-101"], ["PR-200", "PR-201"])
    _tout_envoyer()
    assert _destinataires(envois) == ["PR-101", "PR-200", "PR-201"]   # Compléo : NRP oui (réglages indépendants)
    assert main._read_devis_meta()["PR-100"][0]["relance_count"] == 0  # niveau non consommé


def test_familles_independantes(client, envois):
    _semer(["Compléo", "Data Eva"])
    _decocher(client, "devis", [])
    _decocher(client, "nrp", ["data eva"])
    assert _a_faire() == (["PR-100", "PR-101"], ["PR-200"])
    _tout_envoyer()
    assert _destinataires(envois) == ["PR-100", "PR-101", "PR-200"]


def test_leads_sans_source_case_a_part(client, envois):
    _semer(["Data Eva", "", None])                                   # source vide et champ absent : même case
    _decocher(client, "devis", [main.CLE_SANS_SOURCE])
    _decocher(client, "nrp", [main.CLE_SANS_SOURCE])
    assert _a_faire() == (["PR-100"], ["PR-200"])
    _tout_envoyer()
    assert _destinataires(envois) == ["PR-100", "PR-200"]
    _decocher(client, "devis", ["Data Eva"])                          # sans source recochée, Data Eva décochée
    _decocher(client, "nrp", ["Data Eva"])
    assert _a_faire() == (["PR-101", "PR-102"], ["PR-201", "PR-202"])


def test_nouvelle_source_relancee_par_defaut(client, envois):
    _semer(["Data Eva", "Partenaire X"])
    _decocher(client, "devis", ["Data Eva"])
    _decocher(client, "nrp", ["Data Eva"])
    assert _a_faire() == (["PR-101"], ["PR-201"])


def test_relance_deja_prevue_bloquee_au_moment_de_l_envoi(client, envois):
    _semer(["Data Eva"])
    _decocher(client, "devis", [])
    _decocher(client, "nrp", [])
    today = datetime.now(main.PARIS_TZ).date()
    assert len(main._relances_a_faire(today)) == 1 and len(main._relances_nrp_a_faire(today)) == 1
    _decocher(client, "devis", ["Data Eva"])                          # décochée entre la liste et l'envoi
    _decocher(client, "nrp", ["Data Eva"])
    assert main._send_relance("PR-100", 1, REQ) == {"ok": False, "skip": main.MOTIF_SOURCE_DESACTIVEE}
    assert main._send_nrp_relance("PR-200", REQ) == {"ok": False, "skip": main.MOTIF_SOURCE_DESACTIVEE}
    assert envois == []
    assert int(main._find_lead("PR-200").get("nrp_relance_count") or 0) == 0


def test_envoi_manuel_bloque_aussi(client, envois):
    _semer(["Data Eva"])
    _decocher(client, "devis", ["Data Eva"])
    _decocher(client, "nrp", ["Data Eva"])
    assert client.post("/api/relances/PR-100/send", json={"version": 1}).json()["skip"] == main.MOTIF_SOURCE_DESACTIVEE
    assert client.post("/api/relances-nrp/PR-200/send", json={}).json()["skip"] == main.MOTIF_SOURCE_DESACTIVEE
    assert envois == []
    assert client.get("/api/relances/a-faire").json()["items"] == []
    assert client.get("/api/relances-nrp/a-faire").json()["items"] == []


def test_fiche_annonce_le_motif_au_lieu_d_une_date(client, envois):
    _semer(["Data Eva"])
    _decocher(client, "devis", ["Data Eva"])
    _decocher(client, "nrp", [])
    seq = {s["type"]: s for s in main._sequences_relances(main._find_lead("PR-100"))}
    assert seq["devis"]["motif_arret"] == main.MOTIF_SOURCE_DESACTIVEE and seq["devis"]["prochaine"] == ""
    seq_nrp = {s["type"]: s for s in main._sequences_relances(main._find_lead("PR-200"))}
    assert seq_nrp["nrp"]["motif_arret"] == "" and seq_nrp["nrp"]["prochaine"]


# ---------- Admin : liste des sources et enregistrement ----------

def test_admin_liste_des_sources_et_enregistrement(client):
    main._atomic_write_json(main.LEADS_PATH, [
        _lead("PR-1", source="Data Eva"), _lead("PR-2", source="Data Eva"), _lead("PR-3", source="Compleo"),
        _lead("PR-4", source="Compléo"), _lead("PR-5", source=""), _lead("PR-6"),
        _lead("PR-7", source="Site web", deleted_at="2026-10-01T10:00:00+02:00")])
    main._atomic_write_json(main.PARAMETRES_ADMIN_PATH, {})
    dev = client.get("/api/admin/relances").json()
    sources = [(s["libelle"], s["prospects"]) for s in dev["sources"]]
    assert sources[:2] == [("Compléo", 2), ("Data Eva", 2)]          # Compleo + Compléo = une seule case
    assert sources[-1] == ("Leads sans source", 2) and dev["sources"][-1]["cle"] == main.CLE_SANS_SOURCE
    assert ("Site web", 0) in sources and ("Direct", 0) in sources   # le menu de la fiche, même sans prospect
    assert dev["sources_desactivees"] == [] and client.get("/api/admin/relances-nrp").json()["sources_desactivees"] == []

    champs = ("max", "niveaux_jours", "hour", "actif", "messages")
    avant = {k: dev[k] for k in champs}
    _decocher(client, "devis", ["Data Eva", main.CLE_SANS_SOURCE, "data eva"])
    _decocher(client, "nrp", ["Compléo"])
    dev, nrp = client.get("/api/admin/relances").json(), client.get("/api/admin/relances-nrp").json()
    assert dev["sources_desactivees"] == ["data eva", main.CLE_SANS_SOURCE]
    assert nrp["sources_desactivees"] == ["compleo"]
    assert {k: dev[k] for k in champs} == avant                      # rien d'autre ne bouge
    _decocher(client, "devis", [])                                    # tout recocher
    assert client.get("/api/admin/relances").json()["sources_desactivees"] == []
    assert client.post("/api/admin/relances", json={"sources_desactivees": []}).status_code == 401
