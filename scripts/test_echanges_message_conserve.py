# -*- coding: utf-8 -*-
"""Non-régression Échanges : un message tapé pendant le chargement de l'historique n'est plus effacé.

Avant le correctif, chargerHistorique() rappelait setActiveType(), qui vidait le champ Message :
tout texte tapé avant l'arrivée de /echanges-json disparaissait. La réponse est ici retardée de
1,5 s côté page pour rendre la course certaine (ce test échoue sur l'ancien code).

Prérequis : l'app lancée localement sur un DATA_DIR DE TEST, avec un compte utilisateur.
  HEXA_BASE (défaut http://127.0.0.1:8765), HEXA_USER / HEXA_PASSWORD, HEXA_SHOTS (dossier de captures, optionnel)
Usage : py -3.12 scripts/test_echanges_message_conserve.py   (sortie 0 si tout est vert)
"""
import os
import sys
import traceback

from playwright.sync_api import sync_playwright

BASE = os.environ.get("HEXA_BASE", "http://127.0.0.1:8765")
SHOTS = os.environ.get("HEXA_SHOTS", "")
RESULTS = []
TEXTE = "Message tapé pendant le chargement de l'historique"

RETARD_HISTORIQUE = """
(() => {
  const orig = window.fetch;
  window.fetch = function(url, opts) {
    const p = orig.apply(this, arguments);
    if (String(url).includes('/echanges-json')) return p.then(r => new Promise(res => setTimeout(() => res(r), 1500)));
    return p;
  };
})();
"""


def check(nom, ok, detail=""):
    RESULTS.append((nom, bool(ok), detail))
    print(("OK   " if ok else "KO   ") + nom + (f"  [{detail}]" if detail else ""), flush=True)


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(viewport={"width": 1440, "height": 1000}, locale="fr-FR")
        login = ctx.request.post(f"{BASE}/api/auth/login", data={
            "username": os.environ.get("HEXA_USER", "e2e"), "password": os.environ.get("HEXA_PASSWORD", "e2e-pass-123")})
        assert login.ok, f"connexion impossible : {login.status}"
        ctx.add_init_script(RETARD_HISTORIQUE)
        page = ctx.new_page()
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on("dialog", lambda d: (errors.append("dialog: " + d.message), d.dismiss()))

        page.goto(f"{BASE}/nouveau")
        page.wait_for_function("() => !!document.body.dataset.draftKey")
        page.fill('[name="telephone"]', "0622334455")
        draft = page.evaluate("document.body.dataset.draftKey")

        page.click('[data-cta="E"]')
        page.wait_for_selector("#exchanges-contenu", state="visible")
        page.type("#exchanges-contenu", TEXTE)                  # historique pas encore arrivé
        pendant = page.input_value("#exchanges-contenu")
        page.wait_for_timeout(2200)                              # l'historique arrive et appelle setActiveType
        apres = page.input_value("#exchanges-contenu")
        check("M1 texte saisi pendant le chargement : toujours là après l'arrivée de l'historique",
              pendant == TEXTE and apres == TEXTE, repr(apres))
        if SHOTS:
            page.screenshot(path=os.path.join(SHOTS, "07_message_conserve_apres_chargement.png"))

        page.click("#exchanges-submit")
        page.wait_for_function("t => document.getElementById('exchanges-panel').innerText.includes(t)", arg=TEXTE, timeout=8000)
        ech = page.evaluate("d => fetch('/prospect/' + d + '/echanges-json').then(r => r.json()).then(j => j.echanges.map(e => e.contenu))", draft)
        check("M2 le message est bien enregistré tel que tapé", ech == [TEXTE], str(ech))
        check("M2 champ vidé après l'enregistrement", page.input_value("#exchanges-contenu") == "")

        # Onglet changé avec un message en cours : conservé ; champ vidé par l'utilisateur : reste vide
        page.type("#exchanges-contenu", "brouillon email")
        page.click('.exchanges-tab[data-type="email"]')
        check("M3 changement d'onglet : message en cours conservé", page.input_value("#exchanges-contenu") == "brouillon email")
        page.fill("#exchanges-contenu", "")
        page.dispatch_event("#exchanges-contenu", "input")
        page.click('.exchanges-tab[data-type="sms"]')
        check("M3 champ vidé par l'utilisateur : rien de réinjecté", page.input_value("#exchanges-contenu") == "")

        # Nouvelle ouverture du panneau : repart d'un champ vierge (comportement inchangé)
        page.type("#exchanges-contenu", "texte abandonné")
        page.evaluate("window.fermerEchanges()")
        page.wait_for_timeout(400)
        page.click('[data-cta="E"]')
        page.wait_for_timeout(2200)
        check("M4 réouverture du panneau : champ vierge", page.input_value("#exchanges-contenu") == "",
              repr(page.input_value("#exchanges-contenu")))

        check("aucune erreur JS / dialog", not errors, "; ".join(errors))
        browser.close()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        RESULTS.append(("exécution complète du scénario", False, "exception"))
    ko = [r for r in RESULTS if not r[1]]
    print(f"\n{len(RESULTS) - len(ko)}/{len(RESULTS)} OK")
    sys.exit(1 if ko else 0)
