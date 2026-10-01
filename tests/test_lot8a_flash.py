# -*- coding: utf-8 -*-
"""Lot 8a : plus de flash à l'ouverture d'une fiche. Avant : l'ancienne présentation (accordéon), puis une fiche vide
à l'étape 1, puis la bonne fiche à la bonne étape. Désormais, à CHAQUE image où la fiche est visible, c'est la bonne
fiche, construite en étapes, déjà sur son étape définitive. Vrai Chromium ; fiches fabriquées (test_fix_pdf)."""
import pytest

from test_fix_pdf import page, serveur, sync_api  # noqa: F401  (fixtures réutilisées)

# Relevé à chaque image (requestAnimationFrame) : ce que l'utilisateur voit quand le contenu n'est pas masqué.
RELEVE = """
  window.__images = [];
  const releve = () => {
    const c = document.querySelector('.hexa-page-pending');
    if (c && document.body) {
      const cs = getComputedStyle(c);
      const visible = cs.opacity !== '0' && cs.visibility !== 'hidden';
      const corps = document.querySelector('#p-corps');
      window.__images.push({visible, numero: document.body.dataset.prospectNumero || '',
                            etapes: !!corps, etape: corps ? corps.dataset.etape : null,
                            accordeon: !!document.querySelector('.hexa-page-pending .section-header-bar:not([hidden])')
                                       && !corps});
    }
    requestAnimationFrame(releve);
  };
  requestAnimationFrame(releve);
"""


def _images(pg, numero):
    pg.add_init_script(RELEVE)
    pg.goto(f"{pg.base}/prospect/{numero}")
    pg.wait_for_function("document.body.dataset.prospectNumero === %r && !document.documentElement.classList.contains('hexa-fiche-attente')" % numero,
                         timeout=10000)
    pg.wait_for_timeout(1500)
    return pg.evaluate("window.__images")


def test_ouverture_directe_aucune_image_intermediaire(page):
    images = _images(page, "PR-90001")
    vues = [i for i in images if i["visible"]]
    assert vues, "la fiche ne s'affiche jamais"
    finale = vues[-1]
    assert finale["numero"] == "PR-90001" and finale["etapes"]
    for i in vues:
        assert i["numero"] == "PR-90001", i          # jamais une fiche vide / une autre fiche
        assert i["etapes"], i                         # jamais l'ancienne présentation
        assert i["etape"] == finale["etape"], i       # jamais une étape provisoire
    assert any(not i["visible"] for i in images)     # elle était bien masquée pendant le chargement


def test_masquage_jamais_bloque(page):
    """Fiche introuvable : la page se montre (pas d'écran blanc) ; filet de 3 s de toute façon."""
    page.goto(f"{page.base}/prospect/PR-INEXISTANT")
    page.wait_for_timeout(3500)
    assert not page.evaluate("document.documentElement.classList.contains('hexa-fiche-attente')")


def test_ouverture_depuis_la_liste(page):
    page.goto(page.base + "/")
    page.wait_for_selector("text=PR-90001")
    page.add_init_script("")                         # (rien : navigation interne, pas de rechargement)
    page.evaluate(RELEVE)
    page.click("text=PR-90001")
    page.wait_for_function("document.body.dataset.prospectNumero === 'PR-90001' && !document.documentElement.classList.contains('hexa-fiche-attente')",
                           timeout=10000)
    page.wait_for_timeout(1500)
    vues = [i for i in page.evaluate("window.__images") if i["visible"] and i["numero"]]
    finale = vues[-1]
    assert finale["numero"] == "PR-90001"
    assert all(i["numero"] == "PR-90001" and i["etape"] == finale["etape"] for i in vues), vues[:5]
