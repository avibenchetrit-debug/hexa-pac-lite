# -*- coding: utf-8 -*-
"""Lot 7b : mentions ACE — nettoyage (plus de « Usage » dans le bloc Solution chauffage, énergie écrite une fois),
ligne du régulateur dans la Pose (classe lue dans la fiche produit ; absente : ligne sans parenthèse + alerte à
l'écran), et les 12 éléments exigés par ACE en gras LÉGER (600, même couleur), libellé ET valeur.
Fiche et catalogue fabriqués ici : aucune donnée réelle."""
import json
import re

import pytest

import main
import test_lot7a_documents as docs

SPECS = [{"champ": "Marque", "valeur": "MARQUEFICTIVE"}, {"champ": "Gamme", "valeur": "Gamme X"},
         {"champ": "Usage", "valeur": "Chauffage + ECS"}, {"champ": "Classe du régulateur (ErP)", "valeur": "VI"},
         {"champ": "ETAS chauffage 35°C / 55°C (%)", "valeur": "178 / 151"}, {"champ": "Référence EPREL", "valeur": "1234567"},
         {"champ": "Fluide frigorigène", "valeur": "R32"}]
MODELE = {"ref": "TEST-7B-15", "nom": "PAC FICTIVE 15", "usage": "Chauffage + ECS", "alim": "Triphasé", "puiss35": 15.0,
          "puiss_chauf": 15.0, "etas35": 178, "scop35": 4.5, "cop": 4.5, "classe": "A+++", "fluide": "R32", "ballon": None,
          "achat": 5000, "ttc": 15990, "description_specs": SPECS}


def _catalogue(specs):
    main._atomic_write_json(main.CATALOGUE_PATH, [dict(MODELE, description_specs=specs)])


def _rendu(quoi="devis", specs=SPECS):
    _catalogue(specs)
    docs._preparer()
    etat = main._load_state_simulateur(docs.LEAD["numero"], {}, main._read_catalogue_pac()) or {}
    main.save_state_simulateur_atomic(docs.LEAD["numero"], dict(etat, service="chauffage_ecs", option="opt1",
                                                                mode_mpr="sans_attente", modele_pac_id=MODELE["ref"]))
    if quoi == "facture":
        return main._render_facture_html(None, docs.LEAD["numero"], "FA-2099-0001", "DE2099-0001-1", "2026-07-30")
    ctx = main._build_devis_context(None, docs.LEAD["numero"], avec_sous_traitant=(quoi == "devis"))
    return main.templates.env.get_template("devis_pac.html").render(ctx)


@pytest.mark.parametrize("quoi", ["devis", "pre_devis", "facture"])
def test_regulateur_avec_classe_et_bloc_sans_usage(quoi):
    html = _rendu(quoi)
    t = docs._texte(html)
    assert "Installation et paramétrage du régulateur (classe VI)" in t
    assert "data-regulateur-manquant" not in html
    bloc = docs._texte(re.search(r'<div class="pac-heating-note">(.*?)</section>', html, re.S).group(1))
    assert "Usage :" not in bloc
    assert "Ancien système de chauffage déposé : chaudière — énergie : fioul" in bloc and "chaudière fioul" not in bloc
    assert "Dépose et évacuation de l'ancienne chaudière fioul" in t


def test_classe_manquante_ligne_sans_parenthese_et_marqueur_pour_l_ecran():
    html = _rendu("devis", [s for s in SPECS if not s["champ"].startswith("Classe du régulateur")])
    t = docs._texte(html)
    assert "Installation et paramétrage du régulateur" in t and "régulateur (classe" not in t
    assert html.count("data-regulateur-manquant") == 1
    page = (main.os.path.join(main.os.path.dirname(main.__file__), "templates", "index.html"))
    front = open(page, encoding="utf-8").read()
    assert "querySelector('[data-regulateur-manquant]')" in front and "Classe du régulateur manquante" in front


ELEMENTS = {"reference-devis": 1, "date": 1, "depose": 1, "surface-chauffee": 1, "pac-air-eau": 1, "application": 1,
            "regulateur": 1, "sous-traitant": 1, "sous-traitant-siret": 1, "mention-cee": 1}
FICHE = ["Marque", "Référence EPREL", "Usage", "ETAS chauffage 35°C / 55°C (%)", "Classe du régulateur (ErP)"]


@pytest.mark.parametrize("quoi", ["devis", "facture"])
def test_les_12_elements_en_gras_leger_meme_couleur(quoi):
    sync_api = pytest.importorskip("playwright.sync_api")
    html = _rendu(quoi)
    for cle, n in ELEMENTS.items():
        assert html.count(f'data-ace="{cle}"') >= n, cle
    with sync_api.sync_playwright() as pw:
        b = pw.chromium.launch()
        p = b.new_page()
        p.set_content(html)
        for media in ("screen", "print"):
            p.emulate_media(media=media)
            mesures = p.evaluate("""(fiche) => {
              const out = [];
              const mesure = (e, nom) => {
                const avant = getComputedStyle(e);
                const res = {nom, poids: avant.fontWeight, couleur: avant.color};
                // même couleur qu'SANS la mise en évidence
                const el = e.closest('.ace-exige'); el.classList.remove('ace-exige');
                res.couleur_sans = getComputedStyle(e).color; el.classList.add('ace-exige');
                out.push(res);
              };
              document.querySelectorAll('[data-ace]').forEach(e => {
                if (e.dataset.ace === 'pac-air-eau') return;             // dans le titre, déjà en gras
                const cibles = e.querySelectorAll('.infos-label, .infos-value, .doc-type-num-label, td, .key, .val');
                (cibles.length ? [e, ...cibles] : [e]).forEach(x => mesure(x, e.dataset.ace + ':' + x.className));
              });
              const lignes = [...document.querySelectorAll('.pac-specs-table tr')].filter(tr => fiche.includes(tr.cells[0].textContent.trim()));
              return {out, fiche_marquees: lignes.filter(tr => tr.classList.contains('ace-exige')).length, fiche_total: lignes.length};
            }""", FICHE)
            for m in mesures["out"]:
                assert m["poids"] == "600", (media, m)
                assert m["couleur"] == m["couleur_sans"], (media, m)
            assert mesures["fiche_total"] == len(FICHE) and mesures["fiche_marquees"] == len(FICHE)
        b.close()


# ── Alerte « classe du régulateur manquante » : À L'ÉCRAN, dans la fenêtre du devis (vrai Chromium) ──────────────
from test_fix_pdf import _ouvrir_devis, page, serveur  # noqa: E402,F401  (fixtures réutilisées)


@pytest.mark.parametrize("avec_classe", [False, True])
def test_alerte_regulateur_dans_la_fenetre_du_devis(page, avec_classe):
    specs = SPECS if avec_classe else [s for s in SPECS if not s["champ"].startswith("Classe du régulateur")]
    _catalogue(specs)
    main.save_state_simulateur_atomic("PR-90001", {"service": "chauffage_seul", "modele_pac_id": MODELE["ref"],
                                                   "modele_force": True})
    _ouvrir_devis(page, "PR-90001")
    page.frame_locator("#devis-preview-frame").locator("[data-ace='regulateur']").wait_for()
    # l'alerte se décide à la fin du chargement de l'aperçu (polices et images comprises)
    page.wait_for_function("() => { const f = document.getElementById('devis-preview-frame'); "
                           "return f && f.contentDocument && f.contentDocument.readyState === 'complete'; }", timeout=30000)
    alerte = page.locator("#devis-alerte-regulateur")
    if avec_classe:
        page.wait_for_timeout(500)
        assert not alerte.is_visible()
    else:
        alerte.wait_for(state="visible", timeout=10000)
    if not avec_classe:
        assert "Classe du régulateur manquante" in alerte.inner_text()
        # le devis reste possible : les boutons sont là
        assert page.locator("#devis-pdf-btn").is_enabled() and page.locator("#devis-send-btn").is_visible()
