# -*- coding: utf-8 -*-
"""Lot 13j : chiffres de l'e-mail du devis / pré-devis (audit du 20/10/2026, cas LE BRAS).
1. Paiement comptant : aucune mensualité ; l'e-mail dit « Reste à payer : X € — puis vous économisez Y €/mois dès
   l'installation », badge = Y ÷ facture actuelle. Un mode de paiement inconnu n'est JAMAIS transformé en crédit.
2. « Moins cher dès le premier mois » : seulement si l'économie pendant le financement atteint 10 €/mois.
3. Économie nulle ou négative pendant le crédit : seulement l'économie après remboursement ; jamais de chiffre négatif.
4. « Vous démarrez sans avance » : seulement en crédit ou en Éco-PTZ.
5. Document déjà envoyé à ce client il y a moins de 24 h : confirmation obligatoire avant tout nouvel envoi.
6. Relances : modèle et montant du document réellement envoyé, pas de la fiche du jour.
Aucun service extérieur : Resend est simulé."""
import os
import re
import sys
import types
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

import main
from services.service_devis import calculer_financement_devis

NUM = "PR-13951"
LEAD = {"numero": NUM, "civilite": "Monsieur", "nom": "Essai", "prenom": "Michel", "telephone": "0611139011",
        "email": "michel@example.invalid", "adresse_chantier": "1 rue A", "cp_chantier": "75002",
        "code_postal_chantier": "75002", "ville_chantier": "Paris", "type_logement": "maison",
        "surface_logement_m2": "120", "hsp": "2,5", "mode_chauffage": "fioul", "ecs": "chaudiere",
        "type_emetteurs": "radiateurs_classiques", "alimentation_electrique": "monophase", "categorie": "tres_modeste",
        "nombre_personnes": "4", "cout_energetique_mensuel_eur": "400", "cout_energie_source": "reel",
        "statut": "pre_devis_envoye"}
NBSP = " "


@pytest.fixture(autouse=True)
def _donnees_restaurees():
    chemins = (main.LEADS_PATH, main.DEVIS_META_PATH, main.DEVIS_ENVOYES_PATH, main.NOTES_PATH,
               main.DEVIS_ECHECS_PATH, main.PARAMETRES_ADMIN_PATH, main._state_simulateur_path(NUM))
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


def _preparer(option, **state):
    main._atomic_write_json(main.LEADS_PATH, [dict(LEAD)])
    main._atomic_write_json(main._state_simulateur_path(NUM), {})
    main.save_state_simulateur_atomic(NUM, dict({"service": "chauffage_seul", "option": option}, **state))
    ctx = main._build_devis_context(None, NUM)
    assert ctx.get("_error_template") is None, ctx.get("missing")
    return ctx


def _apercu(mode, fav=214, fap=95, mens=0.0, reste=11902.0):
    return {"mode": mode, "facture_avant": fav, "facture_apres": fap, "eco_apres": fav - fap,
            "eco_pendant": main._arrondi(fav - fap - mens), "reste_a_payer": reste}


def _texte(corps):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", corps)).replace(NBSP, " ")


def _jamais_negatif(corps):
    t = _texte(corps)
    assert "--" not in t and not re.search(r"-\s*\d+\s*€", t), t


# ---------- 1. paiement comptant ----------

def test_comptant_aucune_mensualite():
    fin = calculer_financement_devis(11902, main.load_parametres_admin(), "opt3")
    assert fin["mensualite"] == 0 and fin["duree_mois"] == 0 and fin["option"] == "opt3"


@pytest.mark.parametrize("option", ["opt4", "cash", "comptant", "credit", "", "OPT1"])
def test_mode_de_paiement_inconnu_jamais_transforme_en_credit(option):
    with pytest.raises(ValueError):
        calculer_financement_devis(11902, main.load_parametres_admin(), option)


def test_mode_inconnu_dans_le_simulateur_aucun_chiffre_invente():
    ctx = _preparer("opt9")
    assert ctx["financement_devis"] is None and ctx["projet_apercu"] is None
    corps = main._email_devis_html("Michel", ctx["projet_apercu"], "https://x.invalid/d")
    assert "économisez" not in corps and "moins cher" not in corps


def test_comptant_document_et_email_meme_chiffres():
    ctx = _preparer("opt3")
    pa = ctx["projet_apercu"]
    assert pa["mode"] == "comptant" and pa["mensualite_credit"] == 0 and pa["eco_pendant"] == pa["eco_apres"]
    montant_document = float(re.sub(r"[^\d,]", "", ctx["reste_a_charge"]).replace(",", "."))
    assert pa["reste_a_payer"] == montant_document > 0                  # « Montant total à régler » du document
    t = _texte(main._email_devis_html("Michel", pa, "https://x.invalid/d"))
    assert "Reste à payer" in t and f"puis vous économisez {pa['eco_apres']} €/mois dès l'installation" in t
    assert f"-{round(pa['eco_apres'] / pa['facture_avant'] * 100)}%" in t
    assert "dès maintenant" not in t and "moins cher" not in t and "une fois l'installation remboursée" not in t


def test_comptant_cas_le_bras():
    # 214 € -> 95 €/mois, reste 9 762 € payé comptant : plus jamais « 31 € dès maintenant, -14 % »
    t = _texte(main._email_devis_html("Michel", _apercu("comptant", reste=9762.0), "https://x.invalid/d"))
    assert "Reste à payer 9 762 €" in t and "puis vous économisez 119 €/mois dès l'installation" in t
    assert "-56%" in t and "31 €" not in t and "-14%" not in t


def test_montant_avec_centimes():
    assert main._montant_email(10837.8) == f"10{NBSP}837,80{NBSP}€"
    assert main._montant_email(1290) == f"1{NBSP}290{NBSP}€"


# ---------- 2. « moins cher dès le premier mois » ----------

@pytest.mark.parametrize("mens, phrase", [(88.0, True), (109.0, True), (110.0, False), (117.0, False), (130.0, False)])
def test_phrase_moins_cher_seulement_au_dessus_de_10_euros(mens, phrase):
    corps = main._email_devis_html("Michel", _apercu("credit", mens=mens), "https://x.invalid/d")
    assert ("moins cher qu'aujourd'hui" in corps) is phrase


@pytest.mark.parametrize("apercu", [None, _apercu("comptant"), _apercu("ecoptz", mens=130.0)])
def test_phrase_moins_cher_jamais_en_comptant_ni_sans_chiffre(apercu):
    corps = main._email_devis_html("Michel", apercu, "https://x.invalid/d")
    assert "moins cher" not in corps and "Nous avons préparé votre devis sur mesure." in corps


# ---------- 3. économie nulle ou négative pendant le crédit ----------

@pytest.mark.parametrize("mens", [119.0, 124.0, 300.0])
def test_economie_nulle_ou_negative_seulement_l_economie_apres(mens):
    corps = main._email_devis_html("Michel", _apercu("credit", mens=mens), "https://x.invalid/d")
    t = _texte(corps)
    _jamais_negatif(corps)
    assert "dès maintenant" not in t and "Une fois l'installation remboursée 119 € /mois" in t and "-56%" in t


@pytest.mark.parametrize("mode", ["credit", "ecoptz", "comptant"])
@pytest.mark.parametrize("mens", [0.0, 50.0, 118.6, 119.0, 500.0])
def test_jamais_de_chiffre_negatif_ni_double_moins(mode, mens):
    _jamais_negatif(main._email_devis_html("Michel", _apercu(mode, mens=0.0 if mode == "comptant" else mens),
                                           "https://x.invalid/d"))


def test_credit_avec_economie_inchange():
    t = _texte(main._email_devis_html("Michel", _apercu("credit", mens=88.0), "https://x.invalid/d"))
    assert "Vous économisez dès maintenant 31 € /mois" in t and "puis 119 €/mois une fois l'installation remboursée" in t
    assert "-14%" in t


# ---------- 4. « vous démarrez sans avance » ----------

@pytest.mark.parametrize("option, sans_avance", [("opt1", True), ("opt2", True), ("opt3", False)])
def test_sans_avance_seulement_en_credit_ou_eco_ptz(client, option, sans_avance):
    _preparer(option)
    html = client.get(f"/api/devis/{NUM}/preview?variante=pre_devis").text
    assert ("vous démarrez sans avance" in html) is sans_avance
    assert ("vous réglez votre installation" in html) is not sans_avance


# ---------- 5. envois répétés ----------

def _faux_resend(monkeypatch):
    envois = []

    def send(msg):
        envois.append(msg)
        return {"id": f"factice-{len(envois)}"}

    faux = types.ModuleType("resend")
    faux.Emails = types.SimpleNamespace(send=send)
    monkeypatch.setitem(sys.modules, "resend", faux)
    monkeypatch.setenv("RESEND_API_KEY", "cle-factice-locale")
    monkeypatch.setattr(main, "_resend_dernier_evenement", lambda rid: "")
    return envois


def _fichier(nom, contenu):
    os.makedirs(main.DEVIS_DIR, exist_ok=True)
    chemin = os.path.join(main.DEVIS_DIR, nom)
    open(chemin, "w", encoding="utf-8").write(contenu)
    return chemin


DOC_ENVOYE = ('<html><body><div class="pac-desc-title">NIMBUS PLUS R32 DUO 12</div>'
              '<div class="recap-rac"><span class="recap-rac-label">Montant total à régler</span>'
              '<span class="recap-rac-amount">9&nbsp;762,00&nbsp;€</span></div></body></html>')


def _semer_envoi(il_y_a, **champs):
    main._atomic_write_json(main.LEADS_PATH, [dict(LEAD)])
    sent = (datetime.now(main.PARIS_TZ) - il_y_a).isoformat(timespec="seconds")
    item = dict({"version": 1, "numero_devis": "DE2026-7502-1EM", "variante": "pre_devis", "sent_at": sent,
                 "email": LEAD["email"], "file": _fichier(f"{NUM}_v1.pdf", "%PDF-1.4"),
                 "html_file": _fichier(f"{NUM}_v1.html", DOC_ENVOYE), "resend_id": "id-1", "statut": "envoye",
                 "email_file": _fichier(f"{NUM}_v1_email.html", "<html><body>corps v1</body></html>")}, **champs)
    main._atomic_write_json(main.DEVIS_META_PATH, {NUM: [item]})
    main._atomic_write_json(main.NOTES_PATH, {})
    return datetime.fromisoformat(sent)


def _envoi_sans_pdf(monkeypatch):
    monkeypatch.setattr(main, "_ensure_devis_pdf", lambda numero, request, version, st, nd: (
        _fichier(f"{numero}_v{version}.pdf", "%PDF-1.4"), _fichier(f"{numero}_v{version}.html", DOC_ENVOYE), version))
    monkeypatch.setattr(main, "_ensure_notedim_pdf", lambda numero, request, version: None)
    monkeypatch.setattr(main, "_email_devis_corps", lambda request, numero, prospect, variante, version: "<html>x</html>")
    monkeypatch.setattr(main, "_lead_numero_dossier", lambda numero: "HX26-9999")


def test_envoi_moins_de_24h_apres_confirmation_obligatoire(monkeypatch, client):
    sent = _semer_envoi(timedelta(hours=2))
    _envoi_sans_pdf(monkeypatch)
    envois = _faux_resend(monkeypatch)
    r = client.post(f"/api/devis/{NUM}/send", json={"variante": "pre_devis"})
    assert r.status_code == 409 and envois == []
    jour = "" if sent.date() == datetime.now(main.PARIS_TZ).date() else "hier "
    assert r.json()["detail"] == {"code": "envoi_recent", "message": (
        f"Un pré-devis a déjà été envoyé à ce client {jour}à {sent:%H}h{sent:%M} "
        f"(modèle NIMBUS PLUS R32 DUO 12, 9{NBSP}762,00{NBSP}€). Envoyer quand même ?")}
    assert len(main._read_devis_meta()[NUM]) == 1                       # rien n'a été généré ni enregistré
    r = client.post(f"/api/devis/{NUM}/send", json={"variante": "pre_devis", "confirmer_envoi_recent": True})
    assert r.status_code == 200 and len(main._read_devis_meta()[NUM]) == 2
    assert envois and envois[0]["to"] == [LEAD["email"]]


def test_envoi_plus_de_24h_apres_sans_confirmation(monkeypatch, client):
    _semer_envoi(timedelta(hours=25))
    _envoi_sans_pdf(monkeypatch)
    _faux_resend(monkeypatch)
    assert client.post(f"/api/devis/{NUM}/send", json={"variante": "pre_devis"}).status_code == 200


def test_renvoi_recent_compte_aussi(monkeypatch, client):
    il_y_a_30h = (datetime.now(main.PARIS_TZ) - timedelta(hours=30)).isoformat(timespec="seconds")
    il_y_a_1h = (datetime.now(main.PARIS_TZ) - timedelta(hours=1)).isoformat(timespec="seconds")
    _semer_envoi(timedelta(hours=30), sent_at=il_y_a_30h, renvois=[{"sent_at": il_y_a_1h, "email": LEAD["email"]}])
    envois = _faux_resend(monkeypatch)
    r = client.post(f"/api/devis/{NUM}/renvoyer", json={"version": 1})
    assert r.status_code == 409 and r.json()["detail"]["code"] == "envoi_recent" and envois == []
    r = client.post(f"/api/devis/{NUM}/renvoyer", json={"version": 1, "confirmer_envoi_recent": True})
    assert r.status_code == 200 and r.json()["ok"]


def test_envoi_releve_modele_et_montant_du_document(monkeypatch, client):
    _semer_envoi(timedelta(days=3))
    _envoi_sans_pdf(monkeypatch)
    _faux_resend(monkeypatch)
    assert client.post(f"/api/devis/{NUM}/send", json={"variante": "pre_devis"}).status_code == 200
    v2 = main._read_devis_meta()[NUM][-1]
    assert v2["modele_pac"] == "NIMBUS PLUS R32 DUO 12" and v2["reste_a_charge"] == f"9{NBSP}762,00{NBSP}€"


# ---------- 6. relances : le document envoyé, pas la fiche du jour ----------

def test_relance_modele_et_montant_du_document_envoye(monkeypatch):
    _semer_envoi(timedelta(days=3))                                      # ancien envoi : relu dans le HTML archivé
    envois = _faux_resend(monkeypatch)
    monkeypatch.setattr(main, "_build_devis_context", lambda *a, **k: pytest.fail("la fiche du jour ne doit pas servir"))
    main._send_relance(NUM, 1, main._SchedulerRequest("https://exemple.invalid"))
    t = _texte(envois[0]["html"])
    assert "NIMBUS PLUS R32 DUO 12" in t and "9 762,00 €" in t


def test_relance_valeurs_relevees_a_l_envoi_prioritaires(monkeypatch):
    _semer_envoi(timedelta(days=3), modele_pac="ALFÉA EXCELLIA S DUO 12", reste_a_charge=f"11{NBSP}902,00{NBSP}€")
    envois = _faux_resend(monkeypatch)
    monkeypatch.setattr(main, "_build_devis_context", lambda *a, **k: pytest.fail("la fiche du jour ne doit pas servir"))
    main._send_relance(NUM, 1, main._SchedulerRequest("https://exemple.invalid"))
    t = _texte(envois[0]["html"])
    assert "ALFÉA EXCELLIA S DUO 12" in t and "11 902,00 €" in t and "NIMBUS" not in t
