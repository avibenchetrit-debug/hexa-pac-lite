# -*- coding: utf-8 -*-
"""Lot 7a · 7 : « Émettre une facture rectificative » — admin seulement, dossier verrouillé ; nouveau numéro dans la
suite ; « Facture rectificative — annule et remplace la facture n° … du … » ; contenu IDENTIQUE à l'originale
(montants, date de fin de travaux, référence devis, mention CEE d'origine) plus l'ancien système déposé et le type
d'application ; l'originale reste inchangée. Aperçu « APERÇU — sans numéro » sans consommer de numéro.
Fiche fabriquée ici : aucune donnée réelle."""
import hashlib
import io
import json
import socket
import threading
import time

import pytest

import main
import test_lot7a_documents as docs

httpx = pytest.importorskip("httpx")
uvicorn = pytest.importorskip("uvicorn")
pypdf = pytest.importorskip("pypdf")
pytest.importorskip("playwright.sync_api")

NUM = docs.LEAD["numero"]
MENTION_ORIGINE = "Texte CEE imprimé sur l'originale : prime de {montant_cee} € (ancien libellé)."


@pytest.fixture(scope="module")
def base():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    srv = uvicorn.Server(uvicorn.Config(main.app, host="127.0.0.1", port=port, log_level="error"))
    threading.Thread(target=srv.run, daemon=True).start()
    debut = time.time()
    while not srv.started and time.time() - debut < 20:
        time.sleep(0.1)
    yield f"http://127.0.0.1:{port}"
    srv.should_exit = True


def _cookies(role):
    main._write_users([{"username": "boss", "role": "admin", "actif": True},
                       {"username": "vendeur", "role": "commercial", "actif": True}])
    user = "boss" if role == "admin" else "vendeur"
    return {main.SESSION_COOKIE: main._sign_session(user, role, int(time.time()))}


def _lignes(pdf: bytes) -> list[str]:
    r = pypdf.PdfReader(io.BytesIO(pdf))
    return [l.strip() for p in r.pages for l in (p.extract_text() or "").splitlines() if l.strip()]


@pytest.fixture
def dossier_facture(base, monkeypatch):
    """Une facture d'origine émise AVANT le lot 7a : sans les lignes « ancien système / application », avec la
    mention CEE de l'époque ; puis le dossier est verrouillé et la mention de l'admin change."""
    main._atomic_write_json(main.FACTURES_META_PATH, {})
    main._atomic_write_json(main.COUNTERS_PATH, {"dossier": 0})
    ace = dict(docs.DELEG[1], mention_titre="Mention RAI — Partenaire ACE Énergie", mention_devis=MENTION_ORIGINE)
    docs._preparer(deleg=[docs.DELEG[0], ace])
    monkeypatch.setattr(main, "lignes_solution_chauffage", lambda *a, **k: None)
    monkeypatch.setattr(main, "ligne_regulateur", lambda *a, **k: None)          # Lot 7b : absente en juillet
    r = httpx.post(f"{base}/api/facture/{NUM}", json={"date_fin_travaux": "2026-07-30"}, timeout=120)
    assert r.status_code == 200, r.text
    monkeypatch.undo()
    orig = main._read_factures_meta()[NUM][0]
    main._atomic_write_json(main.DELEGATAIRES_PATH, docs.DELEG)          # la mention de l'admin a changé depuis
    return orig


def test_reservee_a_l_admin_et_au_dossier_verrouille(base, dossier_facture):
    r = httpx.post(f"{base}/api/facture/{NUM}/rectificative", json={}, cookies=_cookies("commercial"), timeout=60)
    assert r.status_code == 403
    assert httpx.post(f"{base}/api/facture/{NUM}/rectificative", json={}, timeout=60).status_code == 401


def test_apercu_sans_numero_ne_consomme_rien(base, dossier_facture):
    avant = json.dumps(main._read_json(main.COUNTERS_PATH, {}), sort_keys=True)
    r = httpx.get(f"{base}/api/facture/{NUM}/rectificative/apercu", cookies=_cookies("admin"), timeout=120)
    assert r.status_code == 200 and r.content[:4] == b"%PDF"
    texte = " ".join(_lignes(r.content))
    assert "APERÇU — sans numéro" in texte
    assert f"annule et remplace la facture n° {dossier_facture['numero_facture']}" in texte
    assert json.dumps(main._read_json(main.COUNTERS_PATH, {}), sort_keys=True) == avant
    assert len(main._read_factures_meta()[NUM]) == 1


def test_rectificative_identique_sauf_ajouts(base, dossier_facture):
    octets_orig = open(dossier_facture["file"], "rb").read()
    empreinte = hashlib.sha256(octets_orig).hexdigest()
    r = httpx.post(f"{base}/api/facture/{NUM}/rectificative", json={}, cookies=_cookies("admin"), timeout=120)
    assert r.status_code == 200, r.text
    j = r.json()
    annee = time.strftime("%Y")
    assert j["numero_facture"] == f"FA-{annee}-0002" and j["rectifie"] == f"FA-{annee}-0001"
    assert j["mention_source"] == "lue sur la facture d'origine"
    meta = main._read_factures_meta()[NUM]
    rect = meta[1]
    assert meta[0] == dossier_facture, "la facture d'origine n'est pas touchée"
    assert hashlib.sha256(open(dossier_facture["file"], "rb").read()).hexdigest() == empreinte
    assert (rect["numero_devis_ref"], rect["date_fin_travaux"], rect["montant_ttc"]) == \
           (dossier_facture["numero_devis_ref"], "2026-07-30", dossier_facture["montant_ttc"])
    l_orig, l_rect = _lignes(octets_orig), _lignes(open(rect["file"], "rb").read())
    t_rect = " ".join(l_rect)
    assert (f"Facture rectificative — annule et remplace la facture n° {dossier_facture['numero_facture']} "
            f"du {dossier_facture['date_emission']}") in t_rect
    # La mention CEE est celle de l'ORIGINALE, pas celle de l'admin d'aujourd'hui.
    assert "Texte CEE imprimé sur l'originale" in t_rect and "offerte par ACE ÉNERGIE (SIREN" not in t_rect
    # Tout le reste est identique, aux ajouts près.
    ajouts = {"Ancien système de chauffage déposé : chaudière — énergie : fioul",
              "Application : moyenne ou haute température", "Installation et paramétrage du régulateur"}
    assert "Usage :" not in t_rect
    for a in ajouts:
        assert a in t_rect
    en_moins = [l for l in l_orig if l not in l_rect]
    en_plus = [l for l in l_rect if l not in l_orig]
    assert all(dossier_facture["numero_facture"] in l or "Dépose et évacuation des équipements remplacés" in l
               for l in en_moins), en_moins
    permis = ajouts | {"Dépose et évacuation de l'ancienne chaudière fioul"}
    assert all(any(p in l for p in permis) or "rectificative" in l.lower() or j["numero_facture"] in l
               or "annule et remplace" in l or dossier_facture["date_emission"] in l for l in en_plus), en_plus
    # Une seconde rectificative de la même facture : refusée, rien d'émis.
    r2 = httpx.post(f"{base}/api/facture/{NUM}/rectificative", json={}, cookies=_cookies("admin"), timeout=60)
    assert r2.status_code == 409 and len(main._read_factures_meta()[NUM]) == 2


def test_montant_different_refuse(base, dossier_facture):
    meta = main._read_factures_meta()
    meta[NUM][0]["montant_ttc"] = float(meta[NUM][0]["montant_ttc"]) + 100
    main._atomic_write_json(main.FACTURES_META_PATH, meta)
    r = httpx.post(f"{base}/api/facture/{NUM}/rectificative", json={}, cookies=_cookies("admin"), timeout=120)
    assert r.status_code == 409 and "différent" in r.json()["detail"]
    assert len(main._read_factures_meta()[NUM]) == 1
    assert main._read_json(main.COUNTERS_PATH, {}).get(f"facture_{time.strftime('%Y')}") == 1


def test_ecart_hors_ajouts_prevus_refuse(base, dossier_facture):
    """Le sous-traitant a changé dans l'admin depuis l'originale : la rectificative ne serait plus identique."""
    params = main.load_parametres_admin()
    st = next((x for x in params.get("sous_traitants", []) if x.get("actif")), None)
    if not st:
        pytest.skip("aucun sous-traitant actif dans les paramètres par défaut")
    ancien_nom = st.get("entreprise")
    st["entreprise"] = "AUTRE ENTREPRISE SAS"
    main.save_parametres_admin_atomic(params)
    try:
        r = httpx.post(f"{base}/api/facture/{NUM}/rectificative", json={}, cookies=_cookies("admin"), timeout=120)
        assert r.status_code == 409 and "AUTRE ENTREPRISE SAS" in r.json()["detail"]
        assert len(main._read_factures_meta()[NUM]) == 1
        assert main._read_json(main.COUNTERS_PATH, {}).get(f"facture_{time.strftime('%Y')}") == 1
    finally:
        params = main.load_parametres_admin()
        next(x for x in params.get("sous_traitants", []) if x.get("actif"))["entreprise"] = ancien_nom
        main.save_parametres_admin_atomic(params)
