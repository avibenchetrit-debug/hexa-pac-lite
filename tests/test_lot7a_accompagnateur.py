# -*- coding: utf-8 -*-
"""Lot 7a · 6 : étape 2 de l'accompagnateur — l'encadré « logement < 15 ans » devient « Logement de moins de 2 ans :
pas de MaPrimeRénov' pour une pompe à chaleur air-eau. » Une config enregistrée en version 3 est corrigée UNE fois
(seulement si elle porte encore le texte d'origine) ; le reste de ce qui a été modifié dans l'admin reste."""
import json

import main


def _encarts(s):
    return s["etapes"]["2"]["encarts"]


def test_texte_par_defaut():
    c = [x for x in _encarts(main.DEFAULT_SCRIPT_APPEL) if x.get("titre") == "À SAVOIR :"]
    assert c and c[0]["texte"] == "Logement de moins de 2 ans : pas de MaPrimeRénov' pour une pompe à chaleur air-eau."
    assert c[0]["condition"] == "age<2"
    assert "15 ans" not in json.dumps(_encarts(main.DEFAULT_SCRIPT_APPEL), ensure_ascii=False)


def test_config_enregistree_en_version_3_corrigee_une_fois():
    ancien = json.loads(json.dumps(main.DEFAULT_SCRIPT_APPEL))
    ancien["version"] = 3
    for c in _encarts(ancien):
        if c.get("titre") == "À SAVOIR :":
            c.update(texte=main.ENCART_MOINS_DE_15_ANS, condition="age<15")
    ancien["etapes"]["1"]["intro"] = "Intro modifiée dans l'admin"
    params = main.load_parametres_admin()
    params["script_appel"] = ancien
    main.save_parametres_admin_atomic(params)
    s = main._script_appel()
    c = next(x for x in _encarts(s) if x.get("titre") == "À SAVOIR :")
    assert (c["texte"], c["condition"]) == (main.ENCART_MOINS_DE_2_ANS, "age<2")
    assert s["etapes"]["1"]["intro"] == "Intro modifiée dans l'admin", "le reste de l'admin reste"
    stocke = main.load_parametres_admin()["script_appel"]
    assert stocke["version"] == 4
    # Une fois en version 4, un texte modifié à la main n'est plus touché.
    next(x for x in _encarts(stocke) if x.get("titre") == "À SAVOIR :")["texte"] = main.ENCART_MOINS_DE_15_ANS
    params = main.load_parametres_admin()
    params["script_appel"] = stocke
    main.save_parametres_admin_atomic(params)
    assert main.ENCART_MOINS_DE_15_ANS in json.dumps(_encarts(main._script_appel()), ensure_ascii=False)
