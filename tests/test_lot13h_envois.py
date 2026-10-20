# -*- coding: utf-8 -*-
"""Lot 13h : envois de devis / pré-devis contrôlés.
« Envoyé » seulement si Resend accepte (sinon « Échec d'envoi » visible), statut de livraison Resend à côté de
« Ouvert / Pas encore ouvert », bouton « Renvoyer » réel (même version, lien, pixel, destinataire ; ni compteur ni
calendrier de relances touchés), copie séparée sans pixel à info@, objet des relances = référence imprimée + prénom.
Aucun service extérieur : Resend est simulé."""
import os
import socket
import sys
import threading
import time
import types
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

import main

NUM = "PR-13801"
LEAD = {"numero": NUM, "civilite": "Monsieur", "nom": "Essai", "prenom": "Marcel", "email": "marcel@example.invalid",
        "telephone": "0611138011", "adresse_chantier": "35 rue A", "cp_chantier": "35000", "code_postal_chantier": "35000",
        "ville_chantier": "Rennes", "type_logement": "maison", "categorie": "modeste", "statut": "pre_devis_envoye",
        "vt_validee": True, "surface_logement_m2": "100", "mode_chauffage": "gaz", "type_emetteurs": "radiateurs_classiques"}


@pytest.fixture(autouse=True)
def _donnees_restaurees():
    chemins = (main.LEADS_PATH, main.DEVIS_META_PATH, main.DEVIS_ENVOYES_PATH, main.NOTES_PATH,
               main.DEVIS_ECHECS_PATH, main.PARAMETRES_ADMIN_PATH)
    sauve = {c: open(c, "rb").read() for c in chemins if os.path.exists(c)}
    absents = [c for c in chemins if not os.path.exists(c)]
    yield
    for c, octets in sauve.items():
        open(c, "wb").write(octets)
    for c in absents:
        if os.path.exists(c):
            os.remove(c)


def _fichier(nom, contenu):
    chemin = os.path.join(main.DEVIS_DIR, nom)
    os.makedirs(main.DEVIS_DIR, exist_ok=True)
    open(chemin, "w", encoding="utf-8").write(contenu)
    return chemin


def _semer(relance_count=2):
    """v1 pré-devis (envoyé il y a 10 jours, 2 relances) et v2 devis, documents archivés présents."""
    main._atomic_write_json(main.LEADS_PATH, [dict(LEAD)])
    il_y_a_10j = (datetime.now(main.PARIS_TZ) - timedelta(days=10)).isoformat(timespec="seconds")
    il_y_a_2j = (datetime.now(main.PARIS_TZ) - timedelta(days=2)).isoformat(timespec="seconds")
    v1 = {"version": 1, "numero_devis": "DE2026-3535-1EM", "variante": "pre_devis", "sent_at": il_y_a_10j,
          "email": LEAD["email"], "file": _fichier(f"{NUM}_v1.pdf", "%PDF-1.4"), "resend_id": "id-initial-1",
          "statut": "envoye", "relance_count": relance_count, "last_relance_at": il_y_a_2j,
          "relances": [{"niveau": n + 1, "sent_at": il_y_a_2j} for n in range(relance_count)],
          "email_file": _fichier(f"{NUM}_v1_email.html", "<html><body><p>Corps archivé v1</p></body></html>")}
    v2 = {"version": 2, "numero_devis": "DE2026-3535-2EM", "variante": "devis", "sent_at": il_y_a_2j,
          "email": LEAD["email"], "file": _fichier(f"{NUM}_v2.pdf", "%PDF-1.4"), "resend_id": "id-initial-2",
          "statut": "envoye", "notedim_file": None,
          "email_file": _fichier(f"{NUM}_v2_email.html", "<html><body><p>Corps archivé v2</p></body></html>")}
    main._atomic_write_json(main.DEVIS_META_PATH, {NUM: [v1, v2]})
    main._atomic_write_json(main.NOTES_PATH, {})
    if os.path.exists(main.DEVIS_ECHECS_PATH):
        os.remove(main.DEVIS_ECHECS_PATH)


def _faux_resend(monkeypatch, refus=None, sans_id=False):
    envois = []

    def send(msg):
        if refus and msg["to"] != [main.COPIE_INTERNE_DEVIS]:
            raise Exception(refus)
        envois.append(msg)
        return {} if sans_id else {"id": f"factice-{len(envois)}"}

    faux = types.ModuleType("resend")
    faux.Emails = types.SimpleNamespace(send=send)
    monkeypatch.setitem(sys.modules, "resend", faux)
    monkeypatch.setenv("RESEND_API_KEY", "cle-factice-locale")
    monkeypatch.setattr(main, "_resend_dernier_evenement", lambda rid: "")   # aucune lecture réseau
    return envois


@pytest.fixture
def client():
    return TestClient(main.app)


def _item(version):
    return next(it for it in main._read_devis_meta()[NUM] if it["version"] == version)


def _notes():
    return [n["texte"] for n in main._read_notes().get(NUM, [])]


# ---------- envoi initial ----------

def _envoi_sans_pdf(monkeypatch):
    """Envoi initial sans Chromium : le PDF et le corps de l'e-mail sont fabriqués (leur contenu n'est pas testé ici)."""
    monkeypatch.setattr(main, "_ensure_devis_pdf", lambda numero, request, version, st, nd: (
        _fichier(f"{numero}_v{version}.pdf", "%PDF-1.4"), _fichier(f"{numero}_v{version}.html", "<html></html>"), version))
    monkeypatch.setattr(main, "_ensure_notedim_pdf", lambda numero, request, version: None)
    monkeypatch.setattr(main, "_email_devis_corps", lambda request, numero, prospect, variante, version:
                        f"<html><body><a href='{main._public_devis_url_v(request, numero, version)}'>voir</a></body></html>")
    monkeypatch.setattr(main, "_lead_numero_dossier", lambda numero: "HX26-9999")


def test_envoi_refuse_rien_n_est_marque_envoye_et_l_echec_est_visible(monkeypatch, client, capsys):
    _semer()
    main._atomic_write_json(main.DEVIS_META_PATH, {})
    _envoi_sans_pdf(monkeypatch)
    _faux_resend(monkeypatch, refus="The to field contains an invalid email address")
    r = client.post(f"/api/devis/{NUM}/send", json={"variante": "pre_devis", "auteur": "Avi"})
    assert r.status_code == 502
    assert "invalid email address" in r.json()["detail"] and "Rien n'a été marqué « Envoyé »" in r.json()["detail"]
    assert main._read_devis_meta().get(NUM) in (None, [])
    assert main._find_lead(NUM)["statut"] == LEAD["statut"]                 # statut du lead inchangé
    echecs = client.get(f"/api/devis/{NUM}/envois-echoues").json()
    assert len(echecs) == 1 and echecs[0]["email"] == LEAD["email"] and "invalid" in echecs[0]["raison"]
    assert any(t.startswith("Échec d'envoi du pré-devis") for t in _notes())
    assert "[envoi] ECHEC" in capsys.readouterr().out


def test_sans_identifiant_resend_l_envoi_n_est_pas_confirme(monkeypatch, client):
    _semer()
    main._atomic_write_json(main.DEVIS_META_PATH, {})
    _envoi_sans_pdf(monkeypatch)
    _faux_resend(monkeypatch, sans_id=True)
    r = client.post(f"/api/devis/{NUM}/send", json={"variante": "pre_devis"})
    assert r.status_code == 502 and "pas confirmé" in r.json()["detail"]
    assert main._read_devis_meta().get(NUM) in (None, [])


def test_envoi_accepte_copie_interne_separee_et_sans_pixel(monkeypatch, client):
    _semer()
    main._atomic_write_json(main.DEVIS_META_PATH, {})
    _envoi_sans_pdf(monkeypatch)
    envois = _faux_resend(monkeypatch)
    r = client.post(f"/api/devis/{NUM}/send", json={"variante": "pre_devis", "auteur": "Avi"})
    assert r.status_code == 200, r.text
    au_client, copie = envois
    assert au_client["to"] == [LEAD["email"]] and "bcc" not in au_client and "cc" not in au_client
    assert au_client["subject"] == "Votre pré-devis Hexa Rénov' — Marcel"
    assert f"/devis-public/{NUM}/1/" in au_client["html"] and "/o.gif" in au_client["html"]
    assert copie["to"] == ["info@hexa-renov.fr"]
    assert copie["subject"] == f"[Copie] Votre pré-devis Hexa Rénov' — Marcel — envoyé à {LEAD['email']}"
    assert "/o.gif" not in copie["html"] and f"/devis-public/{NUM}/1/" in copie["html"]
    it = _item(1)
    assert it["resend_id"] == "factice-1" and it["livraison"] == {"evenement": "sent"}
    assert open(it["email_file"], encoding="utf-8").read() == copie["html"]
    assert main._find_lead(NUM)["statut"] == "pre_devis_envoye"


# ---------- renvoi ----------

def test_renvoi_pre_devis_meme_version_meme_pixel_relances_intactes(monkeypatch, client):
    _semer()
    envois = _faux_resend(monkeypatch)
    avant = _item(1)
    a_faire_avant = main._relances_a_faire(datetime.now(main.PARIS_TZ).date())
    r = client.post(f"/api/devis/{NUM}/renvoyer", json={"version": 1, "auteur": "Avi"})
    assert r.status_code == 200, r.text
    assert r.json()["message"] == f"Pré-devis PD2026-3535-1EM renvoyé à {LEAD['email']}"
    au_client, copie = envois                                               # pré-devis : pas de note de dim
    assert au_client["to"] == [LEAD["email"]] and au_client["subject"] == "Votre pré-devis Hexa Rénov' — Marcel"
    assert "Corps archivé v1" in au_client["html"]
    assert main._pixel_devis_url(types.SimpleNamespace(base_url="http://testserver/"), NUM, 1) in au_client["html"]
    assert copie["to"] == ["info@hexa-renov.fr"] and "/o.gif" not in copie["html"]
    apres = _item(1)
    for cle in ("sent_at", "relance_count", "last_relance_at", "relances", "resend_id", "email"):
        assert apres.get(cle) == avant.get(cle), cle
    assert len(main._read_devis_meta()[NUM]) == 2                          # aucune nouvelle version
    assert apres["renvois"][0]["email"] == LEAD["email"] and apres["renvois"][0]["resend_id"] == "factice-1"
    assert main._relances_a_faire(datetime.now(main.PARIS_TZ).date()) == a_faire_avant
    assert main._find_lead(NUM)["statut"] == LEAD["statut"]
    assert any(t.startswith("Pré-devis PD2026-3535-1EM renvoyé le ") and LEAD["email"] in t for t in _notes())
    ligne = client.get(f"/api/devis/{NUM}/list").json()[1]["renvois"][0]
    assert ligne["libelle"] == f"Renvoyé le {main._date_heure_fr(apres['renvois'][0]['sent_at'])} à {LEAD['email']}"


def test_renvoi_devis_renvoie_aussi_la_note_de_dim(monkeypatch, client):
    _semer()
    envois = _faux_resend(monkeypatch)
    r = client.post(f"/api/devis/{NUM}/renvoyer", json={"version": 2})
    assert r.status_code == 200, r.text
    assert [e["subject"] for e in envois] == ["Votre devis Hexa Rénov' — Marcel", "Votre note de dimensionnement Hexa Rénov'",
                                              f"[Copie] Votre devis Hexa Rénov' — Marcel — envoyé à {LEAD['email']}"]
    assert "Corps archivé v2" in envois[0]["html"] and f"/devis-public/{NUM}/2/" in envois[0]["html"]


def test_renvoi_refuse_erreur_visible_et_rien_d_enregistre(monkeypatch, client, capsys):
    _semer()
    _faux_resend(monkeypatch, refus="You can only send testing emails")
    r = client.post(f"/api/devis/{NUM}/renvoyer", json={"version": 1})
    assert r.status_code == 502 and "You can only send testing emails" in r.json()["detail"]
    assert "renvois" not in _item(1)
    assert not any("renvoyé" in t for t in _notes())
    assert "[envoi] ECHEC renvoi Pré-devis PD2026-3535-1EM" in capsys.readouterr().out


def test_renvoi_version_inconnue(monkeypatch, client):
    _semer()
    _faux_resend(monkeypatch)
    assert client.post(f"/api/devis/{NUM}/renvoyer", json={"version": 9}).status_code == 404
    assert client.post(f"/api/devis/{NUM}/renvoyer", json={}).status_code == 400


# ---------- statut de livraison ----------

def test_statut_de_livraison_echec_livre_et_relecture_limitee(monkeypatch, client):
    _semer()
    _faux_resend(monkeypatch)
    lectures = []
    reponses = {"id-initial-1": "bounced", "id-initial-2": "delivery_delayed"}
    monkeypatch.setattr(main, "_resend_dernier_evenement", lambda rid: lectures.append(rid) or reponses[rid])
    monkeypatch.setattr(main.time, "sleep", lambda s: None)
    items = {it["version"]: it for it in client.get(f"/api/devis/{NUM}/list").json()}
    assert items[1]["livraison"]["code"] == "echec" and items[1]["livraison"]["libelle"] == "Échec d'envoi"
    assert "adresse refusée" in items[1]["livraison"]["raison"]
    assert items[2]["livraison"]["code"] == "differe" and items[2]["livraison"]["libelle"] == "Différé"
    assert any("non reçu par" in t for t in _notes())                      # l'échec constaté est tracé une fois
    assert sorted(lectures) == ["id-initial-1", "id-initial-2"]
    client.get(f"/api/devis/{NUM}/list")
    assert len(lectures) == 2                                              # échec définitif, différé relu dans 10 min
    reponses["id-initial-2"] = "delivered"
    main._actualiser_livraisons(NUM, forcer=True)
    items = {it["version"]: it for it in client.get(f"/api/devis/{NUM}/list").json()}
    assert items[2]["livraison"]["code"] == "livre" and items[2]["livraison"]["libelle"] == "Livré"
    assert sum("non reçu par" in t for t in _notes()) == 1


def test_controle_envois_liste_les_envois_a_revoir(monkeypatch, client):
    _semer()
    _faux_resend(monkeypatch)
    monkeypatch.setattr(main, "_resend_dernier_evenement", lambda rid: {"id-initial-1": "bounced"}.get(rid, "delivered"))
    monkeypatch.setattr(main.time, "sleep", lambda s: None)
    page = client.get("/api/admin/controle-envois").text
    assert "PD2026-3535-1EM" in page and "DE2026-3535-2EM" in page and LEAD["email"] in page
    assert "<b>1 à revoir</b>" in page


# ---------- relances : objet ----------

def test_relance_objet_reference_imprimee_et_prenom(monkeypatch):
    _semer(relance_count=0)
    envois = _faux_resend(monkeypatch)
    monkeypatch.setattr(main, "_build_devis_context", lambda request, numero: {"modele_pac": "PAC", "reste_a_charge": "1 000 €"})
    main._send_relance(NUM, 1, main._SchedulerRequest("https://exemple.invalid"))
    assert envois[0]["subject"] == "Votre pré-devis Hexa Rénov' — Marcel (PD2026-3535-1EM)"
    assert "PD2026-3535-1EM" in envois[0]["html"] and "DE2026-3535-1EM" not in envois[0]["html"]


def test_relance_prenom_avec_apostrophe_ni_echappe_ni_double_echappe(monkeypatch):
    _semer(relance_count=0)
    main._atomic_write_json(main.LEADS_PATH, [dict(LEAD, prenom="Jean-Rémi d'Artois")])
    envois = _faux_resend(monkeypatch)
    monkeypatch.setattr(main, "_build_devis_context", lambda request, numero: {})
    main._send_relance(NUM, 1, main._SchedulerRequest("https://exemple.invalid"))
    assert envois[0]["subject"] == "Votre pré-devis Hexa Rénov' — Jean-Rémi d'Artois (PD2026-3535-1EM)"
    assert "&amp;#x27;" not in envois[0]["html"]


def test_migration_objet_relances(monkeypatch):
    params = main.load_parametres_admin()
    params["relances"] = {"messages": {"non_ouvert": {"sujet": main.SUJET_RELANCE_AVANT_LOT13H, "contenu": "x"},
                                       "ouvert": {"sujet": "Mon objet à moi", "contenu": "y"}}}
    main._atomic_write_json(main.PARAMETRES_ADMIN_PATH, params)
    assert main._migrate_lot13h() is True
    msgs = main._read_json(main.PARAMETRES_ADMIN_PATH, {})["relances"]["messages"]
    assert msgs["non_ouvert"]["sujet"] == "Votre {type_document} Hexa Rénov' — {prenom} ({numero})"
    assert msgs["ouvert"]["sujet"] == "Mon objet à moi"                    # objet personnalisé : jamais touché
    assert main._migrate_lot13h() is False


# ---------- écran : bouton Renvoyer ----------

sync_api = pytest.importorskip("playwright.sync_api")
uvicorn = pytest.importorskip("uvicorn")


def _port_libre():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def ecran(monkeypatch):
    try:
        with sync_api.sync_playwright() as p:
            p.chromium.launch().close()
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"Chromium indisponible : {exc}")
    _semer()
    envois = _faux_resend(monkeypatch)
    main._write_users([{"id": "testeur", "username": "testeur", "password_hash": main._hash_password("essai-local"),
                        "role": "admin", "actif": True, "cree_at": main._now_iso(), "visibilite": "tous"}])
    port = _port_libre()
    srv = uvicorn.Server(uvicorn.Config(main.app, host="127.0.0.1", port=port, log_level="warning"))
    th = threading.Thread(target=srv.run, daemon=True)
    th.start()
    for _ in range(200):
        if srv.started:
            break
        time.sleep(0.05)
    base = f"http://127.0.0.1:{port}"
    with sync_api.sync_playwright() as p:
        b = p.chromium.launch()
        ctx = b.new_context(viewport={"width": 1440, "height": 900})
        ctx.route("**/*", lambda r: r.continue_() if r.request.url.startswith(base) else r.abort())
        pg = ctx.new_page()
        pg.goto(base + "/login")
        pg.fill("#username", "testeur")
        pg.fill("#password", "essai-local")
        pg.click("#login-btn")
        pg.wait_for_url(lambda u: "/login" not in u)
        pg.goto(f"{base}/prospect/{NUM}")
        pg.wait_for_function("document.body.dataset.prospectNumero === %r" % NUM)
        pg.wait_for_timeout(500)
        pg.evaluate("n => window.ouvrirDocuments(n)", NUM)
        pg.wait_for_selector("#docs-devis-list [data-devis-resend]", state="attached")
        pg.click("#docs-devis-title")                                    # accordéon replié à l'ouverture
        pg.wait_for_selector("#docs-devis-list [data-devis-resend]")
        yield pg, envois
        b.close()
    srv.should_exit = True
    th.join(timeout=10)


def test_ecran_renvoyer_confirme_envoie_et_trace(ecran):
    page, envois = ecran
    ligne = page.locator("#docs-devis-list .docs-devis-row").nth(1)       # v1 (liste triée de la plus récente)
    assert "PD2026-3535-1EM" in ligne.inner_text()
    assert "Pas encore ouvert" in ligne.inner_text() and ligne.locator(".docs-livraison").count() == 1
    dialogues = []
    page.once("dialog", lambda d: (dialogues.append(d.message), d.dismiss()))
    ligne.locator("[data-devis-resend]").click()
    page.wait_for_timeout(300)
    assert dialogues == [f"Renvoyer à {LEAD['email']} ?"] and envois == []  # annulé : rien n'est parti
    page.once("dialog", lambda d: d.accept())
    ligne.locator("[data-devis-resend]").click()
    page.wait_for_selector(".hexa-toast-success")
    assert "renvoyé à " + LEAD["email"] in page.inner_text(".hexa-toast-success")
    page.wait_for_selector("#docs-devis-list .docs-renvois li")
    assert page.inner_text("#docs-devis-list .docs-renvois li").startswith("📧 Renvoyé le ")
    assert [e["to"] for e in envois] == [[LEAD["email"]], ["info@hexa-renov.fr"]]
    assert not page.evaluate("!!document.getElementById('sim-drawer')")   # plus d'ouverture du simulateur


def test_ecran_renvoi_refuse_toast_d_erreur(ecran, monkeypatch):
    page, _ = ecran
    def refus(msg):
        raise Exception("Domain not verified")
    monkeypatch.setattr(sys.modules["resend"].Emails, "send", refus)
    page.once("dialog", lambda d: d.accept())
    page.locator("#docs-devis-list [data-devis-resend]").first.click()
    page.wait_for_selector(".hexa-toast-error")
    assert "Renvoi impossible" in page.inner_text(".hexa-toast-error") and "Domain not verified" in page.inner_text(".hexa-toast-error")


# ---------- relances suspendues quand l'adresse est en échec ----------

def _dernier_envoi(livraison, renvois=None):
    """v2 (dernier envoi) envoyé il y a 40 jours, aucune relance encore : une relance est due… sauf adresse en échec."""
    _semer()
    meta = main._read_devis_meta()
    v2 = meta[NUM][1]
    v2["sent_at"] = (datetime.now(main.PARIS_TZ) - timedelta(days=40)).isoformat(timespec="seconds")
    v2["livraison"] = livraison
    if renvois is not None:
        v2["renvois"] = renvois
    main._atomic_write_json(main.DEVIS_META_PATH, meta)


def _a_relancer():
    return [it["numero"] for it in main._relances_a_faire(datetime.now(main.PARIS_TZ).date())]


def test_adresse_en_echec_suspend_les_relances(monkeypatch, client):
    envois = _faux_resend(monkeypatch)
    _dernier_envoi({"evenement": "delivered"})
    assert _a_relancer() == [NUM]                                           # témoin : livré -> relance due
    _dernier_envoi({"evenement": "bounced"})
    assert _a_relancer() == []
    assert main._send_relance(NUM, 2, main._SchedulerRequest("https://exemple.invalid")) == \
        {"ok": False, "skip": "relances suspendues : adresse en échec"}
    assert envois == [] and int(_item(2).get("relance_count") or 0) == 0   # rien d'envoyé, niveau non consommé
    etat = client.get(f"/api/leads/{NUM}/relances").json()
    assert etat["adresse_en_echec"]["email"] == LEAD["email"] and "adresse refusée" in etat["adresse_en_echec"]["raison"]
    assert etat["sequences"][0]["motif_arret"] == "relances suspendues : adresse en échec"
    assert client.get(f"/api/devis/{NUM}/list").json()[0]["relances_suspendues"] is True


def test_plainte_spam_suspend_aussi_et_renvoi_livre_leve_la_suspension(monkeypatch, client):
    _faux_resend(monkeypatch)
    _dernier_envoi({"evenement": "complained"})
    assert _a_relancer() == []
    _dernier_envoi({"evenement": "bounced"}, renvois=[{"sent_at": main._now_iso(), "email": LEAD["email"],
                                                       "resend_id": "r1", "livraison": {"evenement": "delivered"}}])
    assert _a_relancer() == [NUM]                                           # le renvoi (plus récent) a été livré
    assert client.get(f"/api/leads/{NUM}/relances").json()["adresse_en_echec"] is None
    _dernier_envoi({"evenement": "bounced"}, renvois=[{"sent_at": main._now_iso(), "email": LEAD["email"],
                                                       "resend_id": "r1", "livraison": {"evenement": "sent"}}])
    assert _a_relancer() == []                                              # renvoi pas encore livré : échec connu


def test_passage_des_relances_relit_les_statuts_avant_d_envoyer(monkeypatch):
    envois = _faux_resend(monkeypatch)
    _dernier_envoi({"evenement": "sent"})                                  # échec pas encore connu du CRM
    monkeypatch.setattr(main, "_resend_dernier_evenement", lambda rid: "bounced")
    monkeypatch.setattr(main.time, "sleep", lambda s: None)
    monkeypatch.setattr(main, "_relances_actives_global", lambda: True)
    monkeypatch.setattr(main, "_relances_nrp_a_faire", lambda today: [])
    lundi = datetime(2026, 10, 19, 10, 0, tzinfo=main.PARIS_TZ)
    monkeypatch.setattr(main, "datetime", type("D", (datetime,), {"now": classmethod(lambda cls, tz=None: lundi)}))
    main._run_relances_once()
    assert envois == [] and _item(2)["livraison"]["evenement"] == "bounced"


def test_ecran_relances_suspendues_sur_la_fiche(ecran):
    page, _ = ecran
    meta = main._read_devis_meta()
    meta[NUM][1]["livraison"] = {"evenement": "bounced", "verifie_at": main._now_iso()}
    main._atomic_write_json(main.DEVIS_META_PATH, meta)
    page.reload()
    page.wait_for_function("document.body.dataset.prospectNumero === %r" % NUM)
    page.wait_for_function("(document.getElementById('fiche-relances-slot') || {}).textContent"
                           " && document.getElementById('fiche-relances-slot').textContent.includes('Relances suspendues')")
    texte = page.inner_text("#fiche-relances-slot") if page.is_visible("#fiche-relances-slot") else \
        page.evaluate("document.getElementById('fiche-relances-slot').textContent")
    assert "Relances suspendues : adresse en échec" in texte and LEAD["email"] in texte
