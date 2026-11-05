# -*- coding: utf-8 -*-
"""Point 7 (05/11/2026) : jamais d'aide MaPrimeRénov' à 0 € sur un pré-devis / devis — client non éligible
(catégorie Supérieur) : pas de ligne « Estimation aide MaPrimeRénov' », pas de « Condition MaPrimeRénov' »,
phrase du reste à payer adaptée. Client éligible : inchangé."""
import pytest

import main
from tests.test_lot14_quantite_pac import NUM, _donnees_restaurees, _preparer, client  # noqa: F401


def _apercu(client, variante, categorie):
    _preparer()
    leads = main._read_leads()
    for l in leads:
        if l["numero"] == NUM:
            l["categorie"] = categorie
            l["categorie_revenu"] = categorie
    main._atomic_write_json(main.LEADS_PATH, leads)
    return client.get(f"/api/devis/{NUM}/preview?variante={variante}").text


@pytest.mark.parametrize("variante", ["pre_devis", "devis"])
def test_non_eligible_aucune_aide_mpr_a_zero(client, variante):
    html = _apercu(client, variante, "superieur")
    assert "Estimation aide MaPrimeRénov'" not in html and "Condition MaPrimeRénov'" not in html
    assert "Le reste à payer correspond au total TTC diminué de l'estimation de la Prime CEE." in html
    assert "Estimation aide Prime CEE" in html


@pytest.mark.parametrize("variante", ["pre_devis", "devis"])
def test_eligible_inchange(client, variante):
    html = _apercu(client, variante, "modeste")
    assert "Estimation aide MaPrimeRénov' — Pompe à chaleur air-eau" in html and "Condition MaPrimeRénov'" in html
    assert "diminué des estimations d'aides MaPrimeRénov' et Prime CEE." in html
