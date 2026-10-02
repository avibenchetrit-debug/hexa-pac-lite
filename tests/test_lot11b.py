# -*- coding: utf-8 -*-
"""Lot 11b : tarif et contrat du formulaire « Facturer le délégataire » = ceux de l'admin ; facture de solde cohérente
avec l'acompte émis dans le CRM (tarif, contrat, volume, délégataire, destinataire, quote-part restante) ; tarif
précarité PICOTY 12,7 €/MWhc (contrat ECAIR), nouveaux calculs seulement. Fiches fabriquées."""
import copy
import os

import pytest
from fastapi.testclient import TestClient

import main
import test_lot9 as l9
import test_lot9c_marge_facturee as l9c
import test_lot11 as l11
from services import facture_cee as fc

NUM = l9.LEAD["numero"]
DELEG_127 = [dict(l9.DELEG[0], mwh_precaire=12.7), dict(l9.DELEG[1])]


from test_lot11 import _donnees_restaurees  # noqa: E402,F401  (fixture autouse : données remises en l'état)


def _form(c):
    return c.get(f"/api/admin/facture-cee/{NUM}").json()["formulaire"]


# ─────────────────────────── 1. Tarif et contrat dynamiques (admin) ───────────────────────────
def test_nouveau_dossier_ace_14_et_hxr_ctt00002():
    l9c._facturer("sans_attente", "sans_attente")
    c = l11._c()
    f = _form(c)
    assert f["delegataire"] == "ACE" and f["prix_precaire"] == 14.0 and f["prix_classique"] == 7.5
    assert f["ref_contrat"] == "HXR-CTT00002" and f["volume_precaire_mwh"] == 546.0
    # un changement dans l'admin s'applique tout de suite aux nouvelles factures
    d = main._read_json(main.DELEGATAIRES_PATH, [])
    d[1] = dict(d[1], mwh_precaire=14.5, facturation=dict(fc.FACTURATION_DEFAUT["ACE"], contrat="HXR-CTT00003"))
    main._atomic_write_json(main.DELEGATAIRES_PATH, d)
    f = _form(c)
    assert f["prix_precaire"] == 14.5 and f["ref_contrat"] == "HXR-CTT00003"


# ─────────────────────────── 2. Solde = acompte émis dans le CRM ───────────────────────────
def test_solde_reprend_tarif_contrat_volume_destinataire_de_l_acompte():
    l9c._facturer("sans_attente", "sans_attente")
    c = l11._c()
    f = _form(c)
    f.update(ref_appel="HXR-AAF00002-ACT", ref_operation="CEEDOS9-01", date_facture="2026-10-02",
             prix_precaire=13.25, ref_contrat="HXR-CTT00002-bis", volume_precaire_mwh=500.5,
             destinataire=dict(f["destinataire"], adresse="Adresse modifiée"))
    acompte = l11._emettre(c, f)["numero_facture"]
    # l'admin change ensuite tarif et contrat : le solde garde ceux de l'acompte
    d = main._read_json(main.DELEGATAIRES_PATH, [])
    d[1] = dict(d[1], mwh_precaire=15, facturation=dict(fc.FACTURATION_DEFAUT["ACE"], contrat="HXR-CTT00009"))
    main._atomic_write_json(main.DELEGATAIRES_PATH, d)
    s = _form(c)
    assert (s["type"], s["quote_part"]) == ("solde", 40.0)
    assert s["prix_precaire"] == 13.25 and s["ref_contrat"] == "HXR-CTT00002-bis" and s["volume_precaire_mwh"] == 500.5
    assert s["delegataire"] == "ACE" and s["destinataire"]["adresse"] == "Adresse modifiée" and s["ref_operation"] == "CEEDOS9-01"
    assert s["source"] == f"facture d'acompte {acompte}" and s["mention_solde"].endswith(f"{acompte}.")
    assert s["ref_appel"] == ""                                     # nouvel appel à facturation : saisi à la main
    # acompte + solde = l'opération entière
    m_a, m_s = fc.calculer(dict(f, quote_part=60)), fc.calculer(s)
    assert round(m_a["prime_ht"] + m_s["prime_ht"], 2) == s["prime_operation"]
    assert round(m_a["commission_ht"] + m_s["commission_ht"], 2) == m_s["commission_operation"]


def test_solde_picoty_express_garde_l_option():
    l9c._facturer("attente", "attente")
    main._atomic_write_json(main.DELEGATAIRES_PATH, DELEG_127)
    c = l11._c()
    f = _form(c)
    f.update(type="acompte", quote_part=40, option_express=True, ref_appel="APP-1", ref_operation="OP-1", date_facture="2026-10-02")
    l11._emettre(c, f)
    s = _form(c)
    assert (s["type"], s["quote_part"]) == ("solde", 60.0) and s["option_express"] is True
    assert s["destinataire"]["raison_sociale"] == "MRA GROUPE" and s["prix_precaire"] == 12.7


def test_acompte_hors_crm_rien_d_automatique():
    """GALEA : FA-CEE-2026-0001 émise hors CRM -> aucune facture dans le CRM, le formulaire propose l'acompte (saisie manuelle)."""
    l9c._facturer("sans_attente", "sans_attente")
    f = _form(l11._c())
    assert (f["type"], f["quote_part"]) == ("acompte", 60.0) and f["source"].startswith("devis ")


# ─────────────────────────── 3. Tarif précarité PICOTY 12,7 ───────────────────────────
def test_migration_picoty_127_une_seule_fois():
    l9._preparer()
    brut = main._read_json(main.PARAMETRES_ADMIN_PATH, {})          # fichier tel que la migration le lit
    brut.setdefault("params", {}).pop("tarif_picoty_lot11b", None)
    main._atomic_write_json(main.PARAMETRES_ADMIN_PATH, brut)
    main._atomic_write_json(main.DELEGATAIRES_PATH, copy.deepcopy(l9.DELEG))
    assert main._migrate_lot11b() is True
    d = {x["nom"]: x for x in main._read_json(main.DELEGATAIRES_PATH, [])}
    assert d["PICOTY"]["mwh_precaire"] == 12.7 and d["PICOTY"]["mwh_classique"] == 7.2 and d["ACE"]["mwh_precaire"] == 14
    # une valeur remise ensuite dans l'admin n'est jamais réécrasée
    main._atomic_write_json(main.DELEGATAIRES_PATH, copy.deepcopy(l9.DELEG))
    assert main._migrate_lot11b() is False
    assert {x["nom"]: x for x in main._read_json(main.DELEGATAIRES_PATH, [])}["PICOTY"]["mwh_precaire"] == 12.5
    assert main.DEFAULT_DELEGATAIRES[0]["mwh_precaire"] == 12.7


def test_nouveau_dossier_picoty_tres_modeste_non_plafonne_127():
    """Très modeste, 70 m², PAC 9 kW chauffage seul (prime sous le plafond) : prime = volume × 12,7."""
    l9._preparer("attente")
    etat = main._read_json(main._state_simulateur_path(NUM), {})
    etat.update(modele_pac_id="ATL-EXCELLIA-S-9", service="chauffage_seul", prix_pac=13694, surface_chauffee=70)
    main.save_state_simulateur_atomic(NUM, etat)
    leads = main._read_json(main.LEADS_PATH, [])
    leads[0]["surface_logement_m2"] = "70"
    main._atomic_write_json(main.LEADS_PATH, leads)
    p = main._lead_for_response(main._find_lead(NUM))
    resultats = {}
    for tarif in (12.5, 12.7):
        main._atomic_write_json(main.DELEGATAIRES_PATH, [dict(l9.DELEG[0], mwh_precaire=tarif), l9.DELEG[1]])
        admin = main._admin_payload_with_m3()
        calc = main.calculer_devis(p, etat, admin, main._read_catalogue_pac())
        brut = main.calculer_cee_bar_th_171(p, etat, admin, "attente")
        resultats[tarif] = (float(calc["montant_cee"]), brut)
    (prime125, b125), (prime127, b127) = resultats[12.5], resultats[12.7]
    assert b127["details"]["prix_unitaire"] == 12.7 and b127["details"]["type_prix"] == "précaire"
    assert prime127 == pytest.approx(float(b127["montant"]))           # non plafonné
    assert prime127 > prime125 and prime127 / prime125 == pytest.approx(12.7 / 12.5, rel=1e-3)
