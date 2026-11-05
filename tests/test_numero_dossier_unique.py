# -*- coding: utf-8 -*-
"""Point 0 (05/11/2026) : un numéro de dossier par lead, attribué dès le premier document (aperçu, PDF, envoi), jamais
le même pour deux leads, jamais changé ensuite ; un numéro déjà porté par un envoi est repris tel quel."""
import os
import threading

import pytest
from fastapi.testclient import TestClient

import main


@pytest.fixture(autouse=True)
def _isole():
    chemins = (main.COUNTERS_PATH, main.NUMEROS_DOSSIER_PATH, main.DEVIS_META_PATH)
    sauve = {c: open(c, "rb").read() for c in chemins if os.path.exists(c)}
    main._atomic_write_json(main.COUNTERS_PATH, {"dossier": 530, "facture_2026": 9})
    main._atomic_write_json(main.DEVIS_META_PATH, {"PR-000871": [{"version": 1, "numero_dossier": "HX26-0530"}],
                                                   "PR-000164": [{"version": 1}]})
    if os.path.exists(main.NUMEROS_DOSSIER_PATH):
        os.remove(main.NUMEROS_DOSSIER_PATH)
    yield
    for c in chemins:
        if c in sauve:
            open(c, "wb").write(sauve[c])
        elif os.path.exists(c):
            os.remove(c)


def _compteur():
    return main._read_json(main.COUNTERS_PATH, {})["dossier"]


def test_numero_deja_envoye_repris_sans_rien_consommer():
    assert main._numero_dossier_attribue("PR-000871") == "HX26-0530"          # PLUMAS garde son numéro
    assert _compteur() == 530


def test_premier_document_attribue_un_numero_propre_et_stable():
    geslot = main._numero_dossier_attribue("PR-000164")                       # envoi de juillet sans numéro
    autre = main._numero_dossier_attribue("PR-099999")
    assert (geslot, autre) == ("HX26-0531", "HX26-0532") and _compteur() == 532
    for _ in range(3):                                                         # aperçus suivants : même numéro
        assert main._numero_dossier_attribue("PR-000164") == geslot
    assert _compteur() == 532
    assert main._read_json(main.NUMEROS_DOSSIER_PATH, {}) == {"PR-000164": geslot, "PR-099999": autre}


def test_documents_simultanes_jamais_deux_fois_le_meme_numero():
    leads = [f"PR-9{i:05d}" for i in range(40)]
    res, erreurs = {}, []

    def prendre(n):
        try:
            res.setdefault(n, set()).add(main._numero_dossier_attribue(n))
        except Exception as exc:  # noqa: BLE001
            erreurs.append(exc)

    fils = [threading.Thread(target=prendre, args=(n,)) for n in leads for _ in range(3)]
    for f in fils:
        f.start()
    for f in fils:
        f.join()
    assert not erreurs
    assert all(len(v) == 1 for v in res.values())                              # un seul numéro par lead
    numeros = [next(iter(v)) for v in res.values()]
    assert len(set(numeros)) == len(leads) and _compteur() == 530 + len(leads)  # jamais deux fois le même


def test_l_apercu_du_pre_devis_imprime_le_numero_attribue(monkeypatch):
    monkeypatch.setenv("AUTH_ENFORCE", "0")
    vus = []
    origine = main._numero_dossier_attribue
    monkeypatch.setattr(main, "_numero_dossier_attribue", lambda n: vus.append(n) or origine(n))
    monkeypatch.setattr(main, "_find_lead", lambda n: {"numero": n, "nom": "X"})
    monkeypatch.setattr(main, "_load_state_simulateur", lambda n, p, c: {})
    monkeypatch.setattr(main, "validate_prospect_for_devis", lambda p, s, a=None: [])
    try:
        main._build_devis_context(None, "PR-000164")
    except Exception:  # noqa: BLE001 — seul l'appel au numéro compte ici (fiche fictive incomplète)
        pass
    assert vus == ["PR-000164"]
    assert main._read_json(main.NUMEROS_DOSSIER_PATH, {}).get("PR-000164") == "HX26-0531"
