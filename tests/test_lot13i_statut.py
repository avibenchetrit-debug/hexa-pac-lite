# -*- coding: utf-8 -*-
"""Lot 13i : le statut de la fiche avance tout seul avec les actions, jamais en arrière.
Cause corrigée : enregistrer une fiche EXISTANTE renvoyait le statut lu à l'ouverture (champ caché du formulaire) ;
après un envoi (statut avancé par le serveur entre-temps), il revenait en arrière (LEVESQUE, 19/10 : « Nouveau »).
Transitions : pré-devis / devis envoyé (accepté par Resend), date de VT saisie, « Valider la VT », facture générée.
Règles : vers l'avant seulement ; Signé / Perdu / À rappeler jamais écrasés (sauf Signé -> Installation finie) ;
renvoi, relance et envoi refusé ne changent rien ; le statut reste modifiable à la main ; historique « Statut → … »."""
import os
import re
import socket
import sys
import threading
import time
import types

import pytest
from fastapi.testclient import TestClient

import main

NUM = "PR-13901"
LEAD = {"numero": NUM, "civilite": "Madame", "nom": "Levesque", "prenom": "Simone", "email": "simone@example.invalid",
        "telephone": "0611139011", "adresse_chantier": "3 rue B", "cp_chantier": "53000", "code_postal_chantier": "53000",
        "ville_chantier": "Laval", "type_logement": "maison", "categorie": "modeste", "statut": "",
        "surface_logement_m2": "100", "mode_chauffage": "gaz", "type_emetteurs": "radiateurs_classiques"}
NOTE = re.compile(r"^Statut → (.+), automatique, le \d{2}/\d{2} à \d{2}h\d{2}$")


@pytest.fixture(autouse=True)
def _donnees_restaurees():
    chemins = (main.LEADS_PATH, main.DEVIS_META_PATH, main.DEVIS_ENVOYES_PATH, main.NOTES_PATH, main.DEVIS_ECHECS_PATH,
               main.FACTURES_META_PATH, main.COUNTERS_PATH, main.ECHANGES_PATH)
    sauve = {c: open(c, "rb").read() for c in chemins if os.path.exists(c)}
    absents = [c for c in chemins if not os.path.exists(c)]
    yield
    for c, octets in sauve.items():
        open(c, "wb").write(octets)
    for c in absents:
        if os.path.exists(c):
            os.remove(c)


@pytest.fixture
def client():
    return TestClient(main.app)


def _semer(statut="", **extra):
    main._atomic_write_json(main.LEADS_PATH, [dict(LEAD, statut=statut, **extra)])
    main._atomic_write_json(main.DEVIS_META_PATH, {})
    main._atomic_write_json(main.NOTES_PATH, {})
    main._atomic_write_json(main.FACTURES_META_PATH, {})


def _statut():
    return main._find_lead(NUM).get("statut", "")


def _notes_statut():
    return [n["texte"] for n in main._read_notes().get(NUM, []) if n["texte"].startswith("Statut → ")]


def _fichier(nom, contenu="x"):
    os.makedirs(main.DEVIS_DIR, exist_ok=True)
    chemin = os.path.join(main.DEVIS_DIR, nom)
    open(chemin, "w", encoding="utf-8").write(contenu)
    return chemin


@pytest.fixture
def resend_simule(monkeypatch):
    """Envoi sans Chromium ni réseau : PDF et corps fabriqués, Resend factice (refus si `etat['refus']`)."""
    etat = {"refus": None, "envois": []}

    def send(msg):
        if etat["refus"] and msg["to"] != [main.COPIE_INTERNE_DEVIS]:
            raise Exception(etat["refus"])
        etat["envois"].append(msg)
        return {"id": f"factice-{len(etat['envois'])}"}

    faux = types.ModuleType("resend")
    faux.Emails = types.SimpleNamespace(send=send)
    monkeypatch.setitem(sys.modules, "resend", faux)
    monkeypatch.setenv("RESEND_API_KEY", "cle-factice-locale")
    monkeypatch.setattr(main, "_resend_dernier_evenement", lambda rid: "")
    monkeypatch.setattr(main, "_ensure_devis_pdf", lambda numero, request, version, st, nd: (
        _fichier(f"{numero}_v{version}.pdf"), _fichier(f"{numero}_v{version}.html", "<html></html>"), version))
    monkeypatch.setattr(main, "_ensure_notedim_pdf", lambda numero, request, version: None)
    monkeypatch.setattr(main, "_email_devis_corps", lambda request, numero, prospect, variante, version: "<html><body>x</body></html>")
    monkeypatch.setattr(main, "_lead_numero_dossier", lambda numero: "HX26-9998")
    return etat


def _envoyer(client, variante="pre_devis"):
    return client.post(f"/api/devis/{NUM}/send", json={"variante": variante, "auteur": "Avi"})


# ---------- une transition par test ----------

def test_pre_devis_envoye_accepte_par_resend(client, resend_simule):
    _semer("")
    assert _envoyer(client).status_code == 200
    assert _statut() == "pre_devis_envoye"
    assert len(_notes_statut()) == 1 and NOTE.match(_notes_statut()[0]).group(1) == "Pré-devis envoyé"


def test_devis_envoye_accepte_par_resend(client, resend_simule):
    _semer("vt_valide", vt_validee=True)
    assert _envoyer(client, "devis").status_code == 200
    assert _statut() == "devis_envoye" and NOTE.match(_notes_statut()[0]).group(1) == "Devis envoyé"


def test_date_de_visite_technique_saisie_envoye_en_vt(client):
    _semer("pre_devis_envoye")
    r = client.post(f"/api/leads/{NUM}", data={"statut": "pre_devis_envoye", "date_visite_technique_date": "2026-11-04"})
    assert r.status_code == 200, r.text
    assert _statut() == "vt_envoye" and r.json()["lead"]["statut"] == "vt_envoye"
    assert NOTE.match(_notes_statut()[0]).group(1) == "Envoyé en VT"
    client.post(f"/api/leads/{NUM}", data={"date_visite_technique_date": "2026-11-04"})   # même date : rien de plus
    assert len(_notes_statut()) == 1


def test_valider_la_vt_vt_valide(client):
    _semer("vt_envoye")
    assert client.post(f"/api/leads/{NUM}/vt", json={"action": "valider"}).json()["statut"] == "vt_valide"
    assert main._find_lead(NUM)["vt_validee"] is True and NOTE.match(_notes_statut()[0]).group(1) == "VT validé"


def _facturer(client, monkeypatch):
    monkeypatch.setattr(main, "_render_facture_html", lambda *a, **k: "<html><body>facture</body></html>")
    monkeypatch.setattr(main, "_html_to_pdf_playwright", lambda html_doc, request: b"%PDF-1.4 facture")
    return client.post(f"/api/facture/{NUM}", json={"date_fin_travaux": "2026-10-15"})


def test_facture_generee_installation_finie(client, monkeypatch):
    _semer("devis_envoye", vt_validee=True)
    r = _facturer(client, monkeypatch)
    assert r.status_code == 200 and r.json()["success"], r.text
    assert _statut() == "installation_finie" and NOTE.match(_notes_statut()[0]).group(1) == "Installation finie"


def test_installation_finie_remplace_signe(client, monkeypatch):
    _semer("signe", vt_validee=True)
    assert _facturer(client, monkeypatch).status_code == 200
    assert _statut() == "installation_finie"


# ---------- règles ----------

@pytest.mark.parametrize("protege", ["signe", "perdu", "rappeler"])
def test_statuts_manuels_jamais_ecrases(client, resend_simule, protege):
    _semer(protege, vt_validee=True)
    assert _envoyer(client, "devis").status_code == 200
    client.post(f"/api/leads/{NUM}", data={"date_visite_technique_date": "2026-11-04"})
    client.post(f"/api/leads/{NUM}/vt", json={"action": "valider"})
    assert _statut() == protege and _notes_statut() == []


def test_jamais_en_arriere(client, resend_simule):
    _semer("devis_envoye", vt_validee=True)
    assert _envoyer(client, "pre_devis").status_code == 200                 # pré-devis après le devis
    client.post(f"/api/leads/{NUM}", data={"date_visite_technique_date": "2026-11-04"})
    client.post(f"/api/leads/{NUM}/vt", json={"action": "valider"})
    assert _statut() == "devis_envoye" and _notes_statut() == []


def test_envoi_refuse_par_resend_ne_change_pas_le_statut(client, resend_simule):
    _semer("")
    resend_simule["refus"] = "The to field contains an invalid email address"
    assert _envoyer(client).status_code == 502
    assert _statut() == "" and _notes_statut() == []


def test_renvoi_et_relance_ne_changent_pas_le_statut(client, resend_simule, monkeypatch):
    _semer("")
    assert _envoyer(client).status_code == 200
    client.post(f"/api/leads/{NUM}/status", json={"statut": "nouveau"})      # remis à la main
    assert client.post(f"/api/devis/{NUM}/renvoyer", json={"version": 1}).status_code == 200
    monkeypatch.setattr(main, "_build_devis_context", lambda request, numero: {})
    assert main._send_relance(NUM, 1, main._SchedulerRequest("https://exemple.invalid"))["ok"] is True
    assert _statut() == "nouveau" and len(_notes_statut()) == 1


def test_changement_manuel_toujours_possible(client, resend_simule):
    _semer("")
    assert _envoyer(client).status_code == 200
    assert client.post(f"/api/leads/{NUM}/status", json={"statut": "nouveau"}).json()["statut"] == "nouveau"
    assert _statut() == "nouveau"


# ---------- la cause (LEVESQUE) et la garde contre une future régression ----------

def test_enregistrer_la_fiche_apres_un_envoi_ne_remet_pas_le_statut_en_arriere(client, resend_simule):
    """LEVESQUE, 19/10 : fiche ouverte (statut vide), pré-devis envoyé, puis « Enregistrer » 6 min plus tard avec le
    statut lu à l'ouverture -> « Nouveau ». La fiche existante n'écrit plus jamais son statut en s'enregistrant."""
    _semer("")
    assert _envoyer(client).status_code == 200
    r = client.post(f"/api/leads/{NUM}", data={"statut": "", "nom": "Levesque", "prenom": "Simone", "telephone": "0611139011"})
    assert r.status_code == 200 and r.json()["lead"]["statut"] == "pre_devis_envoye"
    assert _statut() == "pre_devis_envoye"
    r = client.post(f"/prospect/{NUM}/ajax", data={"statut": "nouveau"})     # ancienne route d'enregistrement : idem
    assert r.status_code == 200 and _statut() == "pre_devis_envoye"


def test_garde_le_code_d_envoi_fait_toujours_avancer_le_statut(client, resend_simule):
    """Échoue si un futur changement du code d'envoi (route, _send_devis, Resend) ne fait plus avancer le statut :
    passe par la VRAIE route d'envoi des deux variantes et vérifie statut + historique."""
    _semer("", vt_validee=True)
    for variante, attendu, libelle in (("pre_devis", "pre_devis_envoye", "Pré-devis envoyé"),
                                       ("devis", "devis_envoye", "Devis envoyé")):
        r = _envoyer(client, variante)
        assert r.status_code == 200 and r.json()["ok"], r.text
        assert _statut() == attendu, (variante, _statut())
        assert NOTE.match(_notes_statut()[-1]).group(1) == libelle
    assert [m["to"] for m in resend_simule["envois"]].count([LEAD["email"]]) >= 2


def test_creation_d_une_fiche_garde_son_statut(client):
    main._atomic_write_json(main.LEADS_PATH, [])
    r = client.post("/api/leads", data=dict(LEAD, numero="", statut="rappeler", telephone="0611139099"))
    assert r.status_code == 200, r.text
    assert main._find_lead(r.json()["numero"])["statut"] == "rappeler"


def test_libelles_identiques_a_la_pilule_de_statut():
    page = open(os.path.join(main.BASE_DIR, "templates", "index.html"), encoding="utf-8").read()
    front = dict(re.findall(r'\{ k:"(\w+)",\s*label:"([^"]+)"', page))
    assert front == main.LIBELLES_STATUT


# ---------- écran : la pilule suit sans recharger ----------

sync_api = pytest.importorskip("playwright.sync_api")
uvicorn = pytest.importorskip("uvicorn")


def _port_libre():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_ecran_enregistrer_apres_envoi_la_pilule_reste_a_jour(resend_simule):
    try:
        with sync_api.sync_playwright() as p:
            p.chromium.launch().close()
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"Chromium indisponible : {exc}")
    _semer("")
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
    try:
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
            pg.wait_for_function("document.body.dataset.prospectNumero === %r && !!document.getElementById('btn-save')" % NUM)
            pg.wait_for_timeout(800)
            assert pg.inner_text("#p-suivi-statut") == "Nouveau"
            # le pré-devis part (par la route, comme le bouton) pendant que la fiche est ouverte
            r = pg.request.post(f"{base}/api/devis/{NUM}/send", data={"variante": "pre_devis", "auteur": "Avi"})
            assert r.ok, r.text()
            pg.evaluate("n => window.hexaActualiserStatutFiche(n)", NUM)   # ce que fait la fenêtre d'envoi
            pg.wait_for_function("document.getElementById('p-suivi-statut').textContent.includes('Pré-devis envoyé')")
            # 6 minutes plus tard : « Enregistrer » (le formulaire porte encore le statut lu à l'ouverture)
            pg.evaluate("document.getElementById('btn-save').click()")
            pg.wait_for_timeout(1500)
            assert _statut() == "pre_devis_envoye"
            assert "Pré-devis envoyé" in pg.inner_text("#p-suivi-statut")
            b.close()
    finally:
        srv.should_exit = True
        th.join(timeout=10)
