# -*- coding: utf-8 -*-
"""Lot 8f : PDF plus rapide (Chromium réutilisé, repli sur un neuf s'il plante, cache par empreinte du HTML final),
polices chargées avant d'imprimer, libellés de fiche produit jamais coupés (sauf rectificative d'une facture d'avant),
boutons d'emplacement du ballon jamais coupés. Fiches fabriquées ici : aucune donnée réelle."""
import io
import time

import pytest

import main
import test_lot7a_documents as docs
import test_lot7b as l7b
from services import pdf_chromium

pypdf = pytest.importorskip("pypdf")
pytest.importorskip("playwright.sync_api")
LIBELLE = "Classe énergétique chauffage 35°C / 55°C (kW)"
SPECS = l7b.SPECS + [{"champ": LIBELLE, "valeur": "A+++ / A++"}]


def _texte(pdf):
    return " ".join((p.extract_text() or "") for p in pypdf.PdfReader(io.BytesIO(pdf)).pages)


def _html(quoi="devis", **surcharges):
    l7b._catalogue(SPECS)
    docs._preparer()
    etat = main._load_state_simulateur(docs.LEAD["numero"], {}, main._read_catalogue_pac()) or {}
    main.save_state_simulateur_atomic(docs.LEAD["numero"], dict(etat, service="chauffage_ecs", modele_pac_id=l7b.MODELE["ref"]))
    if quoi == "facture":
        return main._render_facture_html(None, docs.LEAD["numero"], "FA-2099-0001", "DE2099-0001-1", "2026-07-30",
                                         surcharges=surcharges or None)
    ctx = main._build_devis_context(None, docs.LEAD["numero"], avec_sous_traitant=True)
    return main.templates.env.get_template("devis_pac.html").render(ctx)


def test_libelle_de_fiche_produit_jamais_coupe():
    t = _texte(main._html_to_pdf_playwright(_html(), None))
    assert LIBELLE in " ".join(t.split()) and "(…" not in t


def test_rectificative_d_une_facture_d_avant_garde_le_rendu_d_origine():
    html = _html("facture", facture_rectificative={"numero": "FA-2026-0001", "date": "30/07/2026"}, specs_libelles_tronques=True)
    assert 'class="pac-specs-table specs-tronques"' in html
    assert 'class="pac-specs-table specs-tronques"' not in _html("facture")


def test_cache_meme_html_meme_pdf_le_moindre_changement_regenere():
    pdf_chromium.vider_cache()
    html = _html()
    g0, c0 = pdf_chromium.stats["generes"], pdf_chromium.stats["cache"]
    a = main._html_to_pdf_playwright(html, None)
    t = time.time()
    b = main._html_to_pdf_playwright(html, None)
    assert b == a and time.time() - t < 0.05                                   # servi par le cache
    assert (pdf_chromium.stats["generes"], pdf_chromium.stats["cache"]) == (g0 + 1, c0 + 1)
    c = main._html_to_pdf_playwright(html.replace("CONTROLE", "CONTROLF", 1), None)   # un caractère change
    assert pdf_chromium.stats["generes"] == g0 + 2 and c != a
    assert pdf_chromium.cle(html) != pdf_chromium.cle(html + " ")


def test_navigateur_reutilise_en_panne_repli_sur_un_neuf():
    pdf_chromium.vider_cache()
    main._html_to_pdf_playwright("<p>avant</p>", None)
    r0 = pdf_chromium.stats["relances"]
    pdf_chromium.simuler_panne()
    pdf = main._html_to_pdf_playwright("<p style=\"font-family:Inter\">après la panne</p>", None)
    assert pdf[:5] == b"%PDF-" and "après la panne" in _texte(pdf)
    assert pdf_chromium.stats["relances"] == r0 + 1


def test_pdf_sans_police_inter_jamais_en_cache():
    pdf_chromium.vider_cache()
    html = "<p style=\"font-family:Arial\">sans Inter</p>"
    main._html_to_pdf_playwright(html, None)
    assert pdf_chromium._du_cache(pdf_chromium.cle(html)) is None


# ── boutons d'emplacement du ballon : jamais coupés (vrai Chromium) ─────────────────────────────────────────────
from test_lot8c_affichage import COUPE, _ouvrir, _parametres_restaures, _semer  # noqa: E402,F401
from test_fix_pdf import page, serveur  # noqa: E402,F401


@pytest.mark.parametrize("largeur", [1000, 1100, 1280])
def test_emplacements_du_ballon_jamais_coupes(page, largeur):
    _semer()
    _ouvrir(page, "PR-98001", 5, largeur)
    vues = page.evaluate(COUPE, "[data-emplacement6]")
    assert len(vues) == 3
    for v in vues:
        assert not v["deborde"] and not v["rogne"] and "…" not in v["texte"], v
