# -*- coding: utf-8 -*-
"""Lot 7c : « Émettre la rectificative depuis un aperçu » — admin, dossier verrouillé. Le serveur contrôle l'aperçu,
MONTRE le numéro qui sera attribué (rien n'est écrit), puis à la confirmation l'inscrit à la place de
« APERÇU — sans numéro » (même police, même taille, même place) sans rien régénérer, et range la facture.
Fiche fabriquée ici ; l'aperçu d'essai est fabriqué à partir de SA facture d'origine."""
import io
import os
import socket
import threading
import time

import pytest

import main
import test_lot7a_documents as docs

httpx = pytest.importorskip("httpx")
uvicorn = pytest.importorskip("uvicorn")
fitz = pytest.importorskip("fitz")          # seulement pour FABRIQUER l'aperçu d'essai (le serveur ne l'utilise pas)
pytest.importorskip("reportlab")
pytest.importorskip("playwright.sync_api")

NUM = docs.LEAD["numero"]
ANNEE = time.strftime("%Y")
POLICES = os.path.join(os.path.dirname(__import__("reportlab").__file__), "fonts")


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


def _cookies(role="admin"):
    main._write_users([{"username": "boss", "role": "admin", "actif": True},
                       {"username": "vendeur", "role": "commercial", "actif": True}])
    return {main.SESSION_COOKIE: main._sign_session("boss" if role == "admin" else "vendeur", role, int(time.time()))}


def fabriquer_apercu(pdf_origine: bytes, orig: str, date_orig: str, date_impr: str | None = None,
                     mention: str | None = None, mention_num: str | None = None) -> bytes:
    """Comme l'aperçu réel : la ligne du numéro réécrite (libellé + « APERÇU — sans numéro », deux blocs de texte),
    la mention de la rectificative et la date d'émission, en polices TrueType embarquées."""
    d = fitz.open(stream=pdf_origine, filetype="pdf")
    p = d[0]
    ligne = p.search_for("N° de facture")[0] | p.search_for(orig)[0]
    date_r = p.search_for(time.strftime("%d/%m/%Y"))[0]
    p.add_redact_annot(ligne + (-2, -1, 2, 1))
    p.add_redact_annot(date_r)
    p.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE, graphics=fitz.PDF_REDACT_LINE_ART_NONE)
    for nom, f in (("vera", "Vera.ttf"), ("verabd", "VeraBd.ttf")):
        p.insert_font(fontname=nom, fontfile=os.path.join(POLICES, f))
    y = ligne.y1 - 2
    marque = "APERÇU — sans numéro"
    lv = fitz.Font(fontfile=os.path.join(POLICES, "VeraBd.ttf")).text_length(marque, fontsize=9)
    ll = fitz.Font(fontfile=os.path.join(POLICES, "Vera.ttf")).text_length("N° de facture :", fontsize=9)
    xv = ligne.x1 - lv
    p.insert_text((xv - 2 - ll, y), "N° de facture :", fontsize=9, fontname="vera", color=(0.54, 0.57, 0.63))
    p.insert_text((xv, y), marque, fontsize=9, fontname="verabd", color=(0.1, 0.13, 0.2))
    texte_mention = mention or "Facture rectificative — annule et remplace la facture n°"
    p.insert_text((330, ligne.y1 + 30), texte_mention, fontsize=9, fontname="vera", color=(0.54, 0.57, 0.63))
    p.insert_text((400, ligne.y1 + 42), f"{mention_num or orig} du {date_orig}", fontsize=9, fontname="vera", color=(0.54, 0.57, 0.63))
    p.insert_text((date_r.x0, date_r.y1 - 2), date_impr or time.strftime("%d/%m/%Y"), fontsize=7.875, fontname="verabd")
    return d.tobytes()


@pytest.fixture
def dossier(base):
    main._atomic_write_json(main.FACTURES_META_PATH, {})
    main._atomic_write_json(main.COUNTERS_PATH, {"dossier": 0, f"facture_{ANNEE}": 41})
    docs._preparer()
    r = httpx.post(f"{base}/api/facture/{NUM}", json={"date_fin_travaux": "2026-07-30"}, timeout=120)
    assert r.status_code == 200, r.text
    orig = main._read_factures_meta()[NUM][0]
    apercu = fabriquer_apercu(open(orig["file"], "rb").read(), orig["numero_facture"], orig["date_emission"])
    return {"orig": orig, "apercu": apercu}


def _post(base, etape, apercu, annule, role="admin", **champs):
    return httpx.post(f"{base}/api/facture/{NUM}/rectificative-apercu/{etape}", cookies=_cookies(role), timeout=120,
                      files={"fichier": ("GALEA_rectificative_apercu.pdf", apercu, "application/pdf")},
                      data={"annule": annule, **champs})


def test_verifier_montre_le_numero_sans_rien_ecrire(base, dossier):
    orig = dossier["orig"]
    avant = (open(main.COUNTERS_PATH, encoding="utf-8").read(), open(main.FACTURES_META_PATH, encoding="utf-8").read())
    r = _post(base, "verifier", dossier["apercu"], orig["numero_facture"])
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["numero_attribue"] == f"FA-{ANNEE}-0043"                     # compteur à 42 après l'originale
    assert any("annule et remplace" in c for c in j["controles"]) and j["annule"] == orig["numero_facture"]
    assert (open(main.COUNTERS_PATH, encoding="utf-8").read(), open(main.FACTURES_META_PATH, encoding="utf-8").read()) == avant


def test_emettre_inscrit_le_numero_a_la_meme_place_sans_rien_regenerer(base, dossier):
    orig, apercu = dossier["orig"], dossier["apercu"]
    r = _post(base, "emettre", apercu, orig["numero_facture"], numero_attendu=f"FA-{ANNEE}-0043")
    assert r.status_code == 200, r.text
    assert r.json() == {"success": True, "numero_facture": f"FA-{ANNEE}-0043", "rectifie": orig["numero_facture"]}
    meta = main._read_factures_meta()[NUM]
    assert meta[0] == orig, "l'originale n'est pas touchée"
    rect = meta[1]
    assert (rect["rectifie"], rect["source"], rect["type"]) == (orig["numero_facture"], "apercu_importe", "rectificative")
    assert main._read_json(main.COUNTERS_PATH, {})[f"facture_{ANNEE}"] == 43
    final = fitz.open(rect["file"])
    avant = fitz.open(stream=apercu, filetype="pdf")
    assert len(final) == len(avant)
    for i in range(1, len(avant)):                                          # pages 2+ : inchangées
        assert final[i].get_text() == avant[i].get_text()
    t1 = final[0].get_text()
    assert "APERÇU" not in t1 and f"FA-{ANNEE}-0043" in t1
    # même police, même taille, même couleur, même ligne de base, même bord droit que la marque
    def span(d, cle):
        return next(s for b in d[0].get_text("dict")["blocks"] for l in b.get("lines", []) for s in l["spans"] if cle in s["text"])
    m, n = span(avant, "APERÇU"), span(final, f"FA-{ANNEE}-0043")
    assert (m["size"], m["color"], m["font"].split("+")[-1]) == (n["size"], n["color"], n["font"].split("+")[-1])
    assert abs(m["origin"][1] - n["origin"][1]) < 0.05 and abs(m["bbox"][2] - n["bbox"][2]) < 0.6
    lm, ln = span(avant, "N° de facture"), span(final, "N° de facture")
    assert (lm["size"], lm["color"]) == (ln["size"], ln["color"]) and abs(lm["origin"][1] - ln["origin"][1]) < 0.05
    # le reste de la page 1 : même texte, hors la ligne du numéro
    reste = lambda d: [l for l in d[0].get_text().splitlines() if "N° de facture" not in l and "APERÇU" not in l and f"FA-{ANNEE}-0043" not in l]  # noqa: E731
    assert reste(final) == reste(avant)
    # une seconde fois : refusée (déjà rectifiée), rien d'émis
    r2 = _post(base, "emettre", apercu, orig["numero_facture"], numero_attendu=f"FA-{ANNEE}-0044")
    assert r2.status_code == 409 and len(main._read_factures_meta()[NUM]) == 2


def test_refus(base, dossier):
    orig, apercu = dossier["orig"], dossier["apercu"]
    n = orig["numero_facture"]
    assert _post(base, "verifier", apercu, n, role="commercial").status_code == 403
    r = _post(base, "emettre", apercu, n, numero_attendu=f"FA-{ANNEE}-0099")      # numéro montré ≠ numéro réel
    assert r.status_code == 409 and f"FA-{ANNEE}-0043" in r.json()["detail"]
    assert _post(base, "verifier", b"pas un pdf", n).status_code == 400
    autre = fabriquer_apercu(open(orig["file"], "rb").read(), n, "01/01/2020", mention_num="FA-2020-0001")  # autre facture
    r = _post(base, "verifier", autre, n)
    assert r.status_code == 400 and "annule et remplace" in r.json()["detail"]
    hier = fabriquer_apercu(open(orig["file"], "rb").read(), n, orig["date_emission"], date_impr="01/01/2020")
    r = _post(base, "verifier", hier, n)
    assert r.status_code == 400 and "Date d'émission" in r.json()["detail"]
    assert len(main._read_factures_meta()[NUM]) == 1 and main._read_json(main.COUNTERS_PATH, {})[f"facture_{ANNEE}"] == 42


# ── L'écran : importer, voir le numéro, confirmer (vrai Chromium) ─────────────────────────────────────────────────
from test_fix_pdf import page, serveur  # noqa: E402,F401  (fixtures réutilisées)


def test_ecran_importer_voir_le_numero_confirmer(page, tmp_path):
    main._atomic_write_json(main.FACTURES_META_PATH, {})
    main._atomic_write_json(main.COUNTERS_PATH, {"dossier": 0, f"facture_{ANNEE}": 41})
    main._write_users([{"id": "testeur", "username": "testeur", "role": "admin", "actif": True,
                        "password_hash": main._hash_password("essai-local")}])
    r = page.request.post(f"{page.base}/api/facture/PR-90001", data={"date_fin_travaux": "2026-07-30"}, timeout=120000)
    assert r.ok, r.text()
    orig = main._read_factures_meta()["PR-90001"][0]
    main._atomic_write_json(main.LEADS_PATH, [dict(x, statut="installation_finie") if x.get("numero") == "PR-90001" else x
                                              for x in main._read_leads()])
    f = tmp_path / "GALEA_rectificative_apercu.pdf"
    f.write_bytes(fabriquer_apercu(open(orig["file"], "rb").read(), orig["numero_facture"], orig["date_emission"]))
    page.goto(f"{page.base}/prospect/PR-90001")
    page.wait_for_function("document.body.dataset.prospectNumero === 'PR-90001' && typeof window.refreshFacturesList === 'function'")
    # Panneau Documents → « 🧾 Factures » → bouton de la facture d'origine
    page.evaluate("() => window.ouvrirDocuments('PR-90001')")
    page.locator("#docs-factures-title").wait_for(state="visible", timeout=15000)
    page.locator("#docs-factures-title").click()
    bouton = page.locator("[data-rectif-import]")
    bouton.first.wait_for(timeout=15000)
    bouton.first.click()
    page.locator("[data-rectif-fichier]").set_input_files(str(f))
    page.locator("[data-rectif-verifier]").click()
    page.locator("[data-rectif-numero]").wait_for(timeout=60000)
    assert page.locator("[data-rectif-numero]").inner_text() == f"FA-{ANNEE}-0043"
    assert main._read_json(main.COUNTERS_PATH, {})[f"facture_{ANNEE}"] == 42        # rien d'écrit à la vérification
    assert f"FA-{ANNEE}-0043" in page.locator("[data-rectif-confirmer]").inner_text()
    page.locator("[data-rectif-confirmer]").click()
    page.locator("[data-rectif-emise]").wait_for(timeout=60000)
    assert page.locator("[data-rectif-emise]").inner_text() == f"FA-{ANNEE}-0043"
    meta = main._read_factures_meta()["PR-90001"]
    assert len(meta) == 2 and meta[1]["rectifie"] == orig["numero_facture"]
