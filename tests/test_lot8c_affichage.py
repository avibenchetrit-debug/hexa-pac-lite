# -*- coding: utf-8 -*-
"""Lot 8c : petits défauts d'affichage (écran seulement, aucun calcul ni document touché). Vrai Chromium, fiches
fabriquées : légende « Encadré jaune » jamais coupée ; « Oui · prix » du ballon lisible en entier ; dossier facturé :
plus d'alerte de dimensionnement à l'étape 6 ; électricité / bois / PAC : « pas de ligne ancien système » à l'écran."""
import pytest

import main
from test_fix_pdf import BASE_LEAD, page, serveur, sync_api  # noqa: F401  (fixtures réutilisées)

@pytest.fixture(autouse=True)
def _parametres_restaures():
    """Les paramètres admin, les fiches et les factures sont partagés par toute la suite : remis en l'état après."""
    sauve = {c: main._read_json(c, None) for c in (main.PARAMETRES_ADMIN_PATH, main.LEADS_PATH, main.FACTURES_META_PATH)}
    yield
    for c, v in sauve.items():
        if v is not None:
            main._atomic_write_json(c, v)


FICHES = {"PR-98001": "fioul", "PR-98002": "electricite", "PR-98003": "bois", "PR-98004": "pac", "PR-98005": "gaz"}


def _semer(fige=False):
    params = main.load_parametres_admin()
    bt = params.setdefault("ballon_thermo", {})
    bt["modeles"] = [{"ref": "ballon-1", "nom": "BALLON FICTIF 240L", "fourniture_ht": 2900, "cout_fourniture_ht": 1500,
                      "type_installation": "", "description_specs": []}]
    bt.setdefault("prix_pose_ht", 400)
    main.save_parametres_admin_atomic(params)
    leads = [dict(BASE_LEAD, numero=n, nom="Affichage", mode_chauffage=e, statut="devis", surface_logement_m2="180",
                  iso_toit="non", iso_mur="non") for n, e in FICHES.items()]
    main._atomic_write_json(main.LEADS_PATH, leads)
    main._atomic_write_json(main.FACTURES_META_PATH, {})
    for n in FICHES:
        etat = main._load_state_simulateur(n, main._find_lead(n), main._read_catalogue_pac()) or {}
        etat.update(service="chauffage_seul", option="opt1", mode_mpr="attente")
        if n == "PR-98001":
            etat.update(ballon_ref="ballon-1", ballon_emplacement="interieur")
        main.save_state_simulateur_atomic(n, etat)
    if fige:   # dossier facturé : verrou (installation finie + facture)
        leads[-1]["statut"] = "installation_finie"
        main._atomic_write_json(main.LEADS_PATH, leads)
        main._atomic_write_json(main.FACTURES_META_PATH, {"PR-98005": [{"numero_facture": "FA-2099-0001", "file": ""}]})


def _ouvrir(pg, numero, etape, largeur=1100):
    pg.set_viewport_size({"width": largeur, "height": 950})
    pg.goto(f"{pg.base}/prospect/{numero}")
    pg.wait_for_function("document.body.dataset.prospectNumero === %r && typeof window.hexaParcoursEtape === 'function'"
                         " && !document.documentElement.classList.contains('hexa-fiche-attente')" % numero, timeout=15000)
    pg.evaluate(f"window.hexaParcoursEtape({etape})")
    pg.wait_for_timeout(800)


COUPE = """(sel) => [...document.querySelectorAll(sel)].filter(e => e.offsetParent).map(e => {
  const r = e.getBoundingClientRect();
  let p = e.parentElement, clip = null;
  while (p) { const c = getComputedStyle(p); if (c.overflow !== 'visible' || c.overflowX !== 'visible') { clip = p.getBoundingClientRect(); break; } p = p.parentElement; }
  return {texte: e.textContent.trim(), deborde: e.scrollWidth > e.clientWidth + 1,
          rogne: clip ? (r.right > clip.right + 1 || r.left < clip.left - 1) : false};
})"""


@pytest.mark.parametrize("largeur", [1100, 1280, 1400])
@pytest.mark.parametrize("etape", [2, 3, 4, 5, 6])
def test_legende_jamais_coupee(page, largeur, etape):
    _semer()
    _ouvrir(page, "PR-98001", etape, largeur)
    vues = page.evaluate(COUPE, ".p6-legende") + page.evaluate(COUPE, ".p6-legende > span:last-child")
    assert vues, "légende absente"
    for v in vues:
        assert "Vérifiez-le deux fois." in v["texte"]
        assert not v["deborde"] and not v["rogne"], v


@pytest.mark.parametrize("largeur", [1000, 1100, 1280])
def test_bouton_ballon_prix_lisible_en_entier(page, largeur):
    _semer()
    _ouvrir(page, "PR-98001", 5, largeur)
    oui = page.evaluate(COUPE, "[data-ballon6='oui']")
    assert len(oui) == 1 and oui[0]["texte"].startswith("Oui · ") and oui[0]["texte"].endswith("€")
    assert not oui[0]["deborde"] and not oui[0]["rogne"], oui


def test_dossier_facture_sans_alerte_de_dimensionnement(page):
    _semer(fige=True)
    _ouvrir(page, "PR-98005", 6, 1280)
    assert page.evaluate("document.body.classList.contains('p6-fige')")
    assert page.evaluate("[...document.querySelectorAll('.p6-alerte-dim')].every(e => !e.offsetParent)")
    _ouvrir(page, "PR-98001", 6, 1280)                                # dossier ouvert : l'alerte reste visible
    assert page.evaluate("[...document.querySelectorAll('.p6-alerte-dim')].some(e => !!e.offsetParent)")


@pytest.mark.parametrize("numero, attendu", [("PR-98002", "Électricité"), ("PR-98003", "Bois"), ("PR-98004", "PAC"),
                                             ("PR-98001", None), ("PR-98005", None)])
def test_message_pas_d_ancien_systeme(page, numero, attendu):
    _semer()
    _ouvrir(page, numero, 6, 1280)
    txt = page.evaluate("(document.querySelector('#p6-sans-ancien-systeme') || {}).textContent || ''")
    if attendu:
        assert "Pas de ligne « Ancien système de chauffage déposé » sur le devis" in txt and attendu in txt
    else:
        assert txt == ""
