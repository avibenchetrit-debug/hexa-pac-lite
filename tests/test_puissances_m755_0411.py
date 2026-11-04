# -*- coding: utf-8 -*-
"""Puissances à −7 °C / 55 °C validées par Avi le 04/11/2026 (18 modèles sur 38) : enregistrées une seule fois au
démarrage, jamais par-dessus une validation faite dans l'Admin ; badge « puissance à 35 °C, non validée » sur les
cartes de gammes et dans « Comparer » pour les modèles sans valeur validée."""
import copy

import main
from services import dimensionnement_pac as dp
from tests.test_notedim_a_cascade import (ALTHERMA_18, CATALOGUE, ETAT_GESLOT, _donnees_restaurees,  # noqa: F401
                                          _ouvrir_etape6, navigateur, serveur)

SANS_VALEUR = {"ATL-EXCELLIA-S-9", "ATL-EXCELLIA-S-DUO-9"} | {m["ref"] for m in CATALOGUE
                                                             if m["ref"].startswith(("DAI-", "THA-"))}


def test_dix_huit_valeurs_validees_une_seule_fois():
    cat, change = dp.migrer_catalogue(copy.deepcopy(CATALOGUE))
    assert change
    valides = {m["ref"]: m[dp.CHAMP_M7_55] for m in cat if m.get(dp.CHAMP_M7_55_VALIDE) is True}
    assert len(valides) == 18 and set(valides) == {m["ref"] for m in CATALOGUE} - SANS_VALEUR
    assert valides["ATL-EXCELLIA-S-14 TRI"] == 10.28 and valides["ARI-NIMBUS-NET-R32-15 TRI"] == 10.2
    m = next(x for x in cat if x["ref"] == "ATL-EXCELLIA-S-12")
    assert m[dp.CHAMP_M7_55_SOURCE].startswith("Atlantic Belgique") and m["puissance_m7_55_import"]
    alt = next(x for x in cat if x["ref"] == ALTHERMA_18)
    assert alt[dp.CHAMP_M7_55_VALIDE] is False                       # valeur du Master (fausse) jamais validée
    # décochée ensuite dans l'Admin : le démarrage suivant ne la recoche pas
    m[dp.CHAMP_M7_55_VALIDE] = False
    cat, change = dp.migrer_catalogue(cat)
    assert change is False and m[dp.CHAMP_M7_55_VALIDE] is False


def test_valeur_deja_validee_dans_l_admin_gardee():
    cat = [{"ref": "ATL-EXCELLIA-S-14", "nom": "x", "ttc": 1, dp.CHAMP_M7_55: 10.5, dp.CHAMP_M7_55_VALIDE: True,
            dp.CHAMP_M7_55_SOURCE: "fournisseur"}]
    cat, _ = dp.migrer_catalogue(cat)
    assert (cat[0][dp.CHAMP_M7_55], cat[0][dp.CHAMP_M7_55_SOURCE]) == (10.5, "fournisseur")


def test_badge_35_sur_les_cartes_et_dans_comparer(navigateur):
    pg = navigateur
    cat, _ = dp.migrer_catalogue(copy.deepcopy(CATALOGUE))
    import tests.test_notedim_a_cascade as a
    ancien = a.CATALOGUE
    a.CATALOGUE = cat                                                  # catalogue avec les 18 valeurs validées
    try:
        _ouvrir_etape6(pg, ETAT_GESLOT)
    finally:
        a.CATALOGUE = ancien
    cartes = pg.evaluate("""[...document.querySelectorAll('.p6-pcard.sim-mod-row')].map(b => ({ id: b.dataset.modeleId,
        badge: !!b.querySelector('.p6-badge35') }))""")
    assert cartes and all(c["badge"] == (c["id"] in SANS_VALEUR) for c in cartes), cartes
    pg.click("#sim-comparer")
    pg.wait_for_selector("#sim-cmp-modal tbody tr")
    lignes = pg.evaluate("""[...document.querySelectorAll('#sim-cmp-modal tbody tr')].map(tr => ({ id: tr.dataset.ref,
        badge: tr.innerText.includes('puissance à 35 °C, non validée') }))""")
    assert lignes and all(l["badge"] == (l["id"] in SANS_VALEUR) for l in lignes), lignes
    # EXCELLIA 14 TRI validée à 10,28 kW : 2 × 10,28 = 20,56 kW, 62 % de 33,4 kW -> toujours valable, sans badge
    exc = [l for l in lignes if l["id"] == "ATL-EXCELLIA-S-14 TRI"]
    assert exc and exc[0]["badge"] is False
    assert pg.erreurs_js == []
