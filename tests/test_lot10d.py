# -*- coding: utf-8 -*-
"""Lot 10d : la ligne « Volume CEE (classique / précaire) … kWh cumac » a EXACTEMENT la mise en forme de « Estimation aide
Prime CEE » (police, taille, couleur du libellé ; valeur alignée au même bord droit, même graisse, mais couleur de texte
normale ; même hauteur, même centrage vertical, même trait dessous) — devis, pré-devis, facture ; écran et impression."""
import pytest

import main
import test_lot9 as l9

sync_api = pytest.importorskip("playwright.sync_api")

MESURE = """() => {
  const lignes = [...document.querySelectorAll('.recap-line')];
  const cee = lignes.find(l => (l.querySelector('.label') || {}).textContent === 'Estimation aide Prime CEE');
  const vol = document.querySelector('.recap-line.recap-volume-cee');
  const total = lignes.find(l => (l.querySelector('.label') || {}).textContent === 'Total HT');
  const m = (ligne) => {
    const lab = ligne.querySelector('.label'), val = ligne.querySelector('.amount');
    const cl = getComputedStyle(lab), cv = getComputedStyle(val), cg = getComputedStyle(ligne);
    const rl = ligne.getBoundingClientRect(), rv = val.getBoundingClientRect(), rt = lab.getBoundingClientRect();
    return {police: cl.fontFamily, taille: cl.fontSize, couleur_lib: cl.color, graisse_lib: cl.fontWeight,
            taille_val: cv.fontSize, graisse_val: cv.fontWeight, couleur_val: cv.color, droite_val: Math.round(rv.right * 10) / 10,
            hauteur: Math.round(rl.height * 10) / 10, centre_lib: Math.round((rt.top + rt.height / 2 - rl.top) * 10) / 10,
            centre_val: Math.round((rv.top + rv.height / 2 - rl.top) * 10) / 10,
            trait: cg.borderBottomWidth + ' ' + cg.borderBottomStyle + ' ' + cg.borderBottomColor, interligne: cl.lineHeight,
            texte_lib: lab.textContent, texte_val: val.textContent};
  };
  return {cee: m(cee), vol: m(vol), couleur_texte_normale: getComputedStyle(total.querySelector('.amount')).color};
}"""


def _html(quoi):
    l9._preparer("attente")
    if quoi == "facture":
        return main._render_facture_html(None, l9.LEAD["numero"], "FA-2099-0001", "DE2099-0001-1", "2026-07-30")
    ctx = main._build_devis_context(None, l9.LEAD["numero"], avec_sous_traitant=(quoi == "devis"))
    ctx["pre_devis"] = quoi == "pre_devis"
    return main.templates.env.get_template("devis_pac.html").render(ctx)


@pytest.mark.parametrize("quoi", ["devis", "pre_devis", "facture"])
def test_volume_cee_meme_mise_en_forme_que_la_prime_cee(quoi):
    html = _html(quoi)
    with sync_api.sync_playwright() as pw:
        b = pw.chromium.launch()
        p = b.new_page(viewport={"width": 1200, "height": 900})
        p.set_content(html)
        for media in ("screen", "print"):
            p.emulate_media(media=media)
            r = p.evaluate(MESURE)
            cee, vol = r["cee"], r["vol"]
            for k in ("police", "taille", "couleur_lib", "graisse_lib", "taille_val", "graisse_val", "droite_val", "hauteur",
                      "centre_lib", "centre_val", "trait", "interligne"):
                assert cee[k] == vol[k], (media, k, cee[k], vol[k])
            assert vol["graisse_val"] == "700"
            assert vol["couleur_val"] == r["couleur_texte_normale"] != cee["couleur_val"]      # pas en vert
            assert vol["texte_lib"] in ("Volume CEE (classique)", "Volume CEE (précaire)")
            assert vol["texte_val"].endswith(" kWh cumac") and vol["texte_val"][0].isdigit()
        b.close()
