# -*- coding: utf-8 -*-
"""Relances par source : provenance « Compleo » harmonisée en « Compléo »."""
import os

import pytest

import main


@pytest.fixture(autouse=True)
def _donnees_restaurees():
    chemins = (main.LEADS_PATH, main.DEVIS_META_PATH, main.NOTES_PATH, main.PARAMETRES_ADMIN_PATH)
    sauve = {c: open(c, "rb").read() for c in chemins if os.path.exists(c)}
    absents = [c for c in chemins if not os.path.exists(c)]
    yield
    for c, octets in sauve.items():
        open(c, "wb").write(octets)
    for c in absents:
        if os.path.exists(c):
            os.remove(c)


# ---------- correction en base : Compleo -> Compléo ----------

def test_migration_compleo_vers_compleo_accentue_une_seule_fois():
    main._atomic_write_json(main.LEADS_PATH, [
        {"numero": "PR-1", "source": "Compleo"},
        {"numero": "PR-2", "source": " compleo "},
        {"numero": "PR-3", "source": "Compleo", "deleted_at": "2026-10-01T10:00:00+02:00"},
        {"numero": "PR-4", "source": "Compléo"},
        {"numero": "PR-5", "source": "Data Eva"},
        {"numero": "PR-6", "source": ""},
        {"numero": "PR-7"},
    ])
    assert main._migrate_sources_compleo() == 3
    sources = {l["numero"]: l.get("source") for l in main._read_leads()}
    assert sources == {"PR-1": "Compléo", "PR-2": "Compléo", "PR-3": "Compléo", "PR-4": "Compléo",
                       "PR-5": "Data Eva", "PR-6": "", "PR-7": None}
    assert main._migrate_sources_compleo() == 0                     # deuxième démarrage : rien à faire
