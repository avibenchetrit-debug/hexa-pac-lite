# -*- coding: utf-8 -*-
"""Lot 7a · 5 : le bloc « Solution chauffage » a la MÊME largeur que les blocs du dessus et du dessous, sur le
PDF réellement généré (devis et facture). Cause trouvée : à l'impression, les blocs du document perdent leur
retrait latéral (les marges viennent de la page) ; `.legal-intro`, qui contient le bloc, gardait sa marge d'écran
de 56 px de chaque côté. Mesure : les rectangles de fond dessinés dans le PDF (PyMuPDF)."""
import socket
import threading
import time
import types

import pytest

import main
import test_lot7a_documents as docs

fitz = pytest.importorskip("fitz")
uvicorn = pytest.importorskip("uvicorn")
pytest.importorskip("playwright.sync_api")


@pytest.fixture(scope="module")
def requete():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    srv = uvicorn.Server(uvicorn.Config(main.app, host="127.0.0.1", port=port, log_level="error"))
    threading.Thread(target=srv.run, daemon=True).start()
    debut = time.time()
    while not srv.started and time.time() - debut < 20:
        time.sleep(0.1)
    yield types.SimpleNamespace(base_url=f"http://127.0.0.1:{port}/", headers={}, url=types.SimpleNamespace(scheme="http"))
    srv.should_exit = True


def _boites(pdf: bytes):
    page = fitz.open(stream=pdf, filetype="pdf")[0]
    fonds = [d["rect"] for d in page.get_drawings() if d.get("fill") is not None and d["rect"].width > 200]

    def boite(texte):
        pos = page.search_for(texte)[0].tl + (1, 1)
        return min((r for r in fonds if r.contains(pos)), key=lambda r: r.width * r.height)
    return boite("Opération n°"), boite("Numéro de dossier"), boite("Fourniture")


@pytest.mark.parametrize("quoi", ["devis", "pre_devis", "facture"])        # Lot 8c : le pré-devis aussi
def test_solution_chauffage_meme_largeur_que_ses_voisins(requete, quoi):
    docs._preparer()
    if quoi == "facture":
        html = main._render_facture_html(None, docs.LEAD["numero"], "FA-2099-0001", "DE2099-0001-1", "2026-07-30")
    else:
        html = main.templates.env.get_template("devis_pac.html").render(
            main._build_devis_context(None, docs.LEAD["numero"], avec_sous_traitant=(quoi == "devis")))
    note, dessus, dessous = _boites(main._html_to_pdf_playwright(html, requete))
    for voisin in (dessus, dessous):
        assert abs(note.x0 - voisin.x0) < 1 and abs(note.x1 - voisin.x1) < 1, (note, voisin)
