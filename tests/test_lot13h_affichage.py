# -*- coding: utf-8 -*-
"""Lot 13h (affichage) : le menu Statut du panneau « Suivi du dossier » s'affiche au-dessus de tout (il passait sous
le bloc « Date de visite technique ») et s'ouvre vers le haut quand la place manque en bas ; le bandeau de la fiche
reste dans son cadre à toute largeur (commandes en 2e ligne si besoin, N / E / D / S toujours cliquables, email
raccourci « … » avec l'adresse complète au survol). Vrai Chromium, fiche fabriquée."""
import socket
import threading
import time

import pytest

import main

sync_api = pytest.importorskip("playwright.sync_api")
uvicorn = pytest.importorskip("uvicorn")

EMAIL = "marcel.jean.montaroup.delacroix.famille@orange.fr"
LEAD = {"numero": "PR-13802", "civilite": "Monsieur", "nom": "Montaroup-Delacroix", "prenom": "Marcel-Jean",
        "telephone": "0611138021", "email": EMAIL, "adresse_chantier": "35 rue des Lilas", "cp_chantier": "35000",
        "code_postal_chantier": "35000", "ville_chantier": "Saint-Jacques-de-la-Lande", "type_logement": "maison",
        "categorie": "modeste", "statut": "pre_devis_envoye"}

# chaque cible : son centre est-il bien l'élément lui-même (rien par-dessus, dans l'écran) ?
VISIBLES = """sel => [...document.querySelectorAll(sel)].filter(e => e.checkVisibility()).map(e => {
  const r = e.getBoundingClientRect(), x = r.left + Math.min(12, r.width / 2), y = r.top + r.height / 2;
  if (x < 0 || y < 0 || x > innerWidth || y > innerHeight) return (e.textContent || e.id).trim() + ' hors écran';
  const t = document.elementFromPoint(x, y);
  return (t === e || e.contains(t)) ? '' : (e.textContent || e.id).trim() + ' masqué';
}).filter(Boolean)"""


def _port_libre():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def serveur():
    try:
        with sync_api.sync_playwright() as p:
            p.chromium.launch().close()
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"Chromium indisponible : {exc}")
    main._atomic_write_json(main.LEADS_PATH, [dict(LEAD)])
    main._write_users([{"id": "testeur", "username": "testeur", "password_hash": main._hash_password("essai-local"),
                        "role": "admin", "actif": True, "cree_at": main._now_iso(), "visibilite": "tous"}])
    port = _port_libre()
    srv = uvicorn.Server(uvicorn.Config(main.app, host="127.0.0.1", port=port, log_level="warning"))
    th = threading.Thread(target=srv.run, daemon=True)
    th.start()
    for _ in range(200):
        if srv.started:
            break
        time.sleep(0.05)
    yield f"http://127.0.0.1:{port}"
    srv.should_exit = True
    th.join(timeout=10)
    main._atomic_write_json(main.LEADS_PATH, [])


def _fiche(p, serveur, largeur, hauteur):
    b = p.chromium.launch()
    ctx = b.new_context(viewport={"width": largeur, "height": hauteur})
    ctx.route("**/*", lambda r: r.continue_() if r.request.url.startswith(serveur) else r.abort())
    pg = ctx.new_page()
    pg.goto(serveur + "/login")
    pg.fill("#username", "testeur")
    pg.fill("#password", "essai-local")
    pg.click("#login-btn")
    pg.wait_for_url(lambda u: "/login" not in u)
    pg.goto(f"{serveur}/prospect/{LEAD['numero']}")
    pg.wait_for_function("document.body.dataset.prospectNumero === %r && !!document.getElementById('p-suivi-btn')" % LEAD["numero"])
    pg.wait_for_timeout(800)
    return b, pg


@pytest.mark.parametrize("largeur,hauteur", [(1440, 900), (1366, 520)])
def test_menu_statut_du_suivi_au_dessus_du_bloc_visite_technique(serveur, largeur, hauteur):
    with sync_api.sync_playwright() as p:
        b, pg = _fiche(p, serveur, largeur, hauteur)
        pg.click("#p-suivi-btn")
        pg.wait_for_selector("#fp-date-visite-tech", state="visible")      # le bloc qui masquait le menu est là
        pg.click("#p-suivi-pop .pv-statut")
        pg.wait_for_selector(".pv-statut-menu.open")
        assert pg.evaluate(VISIBLES, ".pv-statut-menu.open .pv-statut-opt") == []
        pg.click(".pv-statut-menu.open .pv-statut-opt[data-k=vt_valide]")    # le choix s'applique
        pg.wait_for_function("document.getElementById('p-suivi-statut').textContent.includes('VT validé')")
        b.close()


def test_menu_statut_s_ouvre_vers_le_haut_sans_place_en_bas(serveur):
    with sync_api.sync_playwright() as p:
        b, pg = _fiche(p, serveur, 1366, 768)
        pg.click("#p-suivi-btn")
        pg.evaluate("""() => { const w = document.querySelector('#p-suivi-pop .pv-statut-wrap');
                               w.style.position = 'fixed'; w.style.top = (innerHeight / 0.9 - 60) + 'px'; }""")
        pg.click("#p-suivi-pop .pv-statut")
        pg.wait_for_selector(".pv-statut-menu.open")
        assert pg.get_attribute(".pv-statut-menu.open", "data-sens") == "haut"
        assert pg.evaluate(VISIBLES, ".pv-statut-menu.open .pv-statut-opt") == []
        b.close()


@pytest.mark.parametrize("largeur", [1920, 1366, 1280, 1024, 960, 683])
def test_bandeau_dans_son_cadre_et_boutons_cliquables(serveur, largeur):
    with sync_api.sync_playwright() as p:
        b, pg = _fiche(p, serveur, largeur, 800)
        bilan = pg.evaluate("""() => {
          const bar = document.querySelector('.prospect-sticky-bar'), rb = bar.getBoundingClientRect();
          const dehors = [...bar.querySelectorAll('button, span')].filter(e => { const r = e.getBoundingClientRect();
            return r.width > 0 && (r.right > rb.right + 0.5 || r.left < rb.left - 0.5); }).map(e => e.id || e.textContent.trim());
          return {deborde: bar.scrollWidth > bar.clientWidth, dehors, page: document.documentElement.scrollWidth > innerWidth};
        }""")
        assert bilan == {"deborde": False, "dehors": [], "page": False}
        assert pg.evaluate(VISIBLES, ".prospect-sticky-bar button") == []
        assert [pg.locator(f".psb-actions [data-cta={c}]").is_visible() for c in "NEDS"] == [True] * 4
        email = pg.evaluate("""() => { const e = document.getElementById('psb-email');
          return {texte: e.textContent, title: e.title, lignes: Math.round(e.getBoundingClientRect().height / 18),
                  points: getComputedStyle(e).textOverflow}; }""")
        assert email == {"texte": EMAIL, "title": EMAIL, "lignes": 1, "points": "ellipsis"}
        hauteur = pg.evaluate("document.querySelector('.prospect-sticky-bar').getBoundingClientRect().height")
        if largeur >= 1280:                                                 # une seule rangée, comme avant
            assert hauteur < 60, hauteur
        b.close()


def test_menu_referme_revient_a_sa_place_pour_la_cloture_perdu(serveur):
    """Ouvert, le menu est rattaché à <body> ; refermé, il revient dans #fiche-statut-slot, où la clôture « Perdu »
    de l'accompagnateur (Lot 6f) va chercher l'option."""
    with sync_api.sync_playwright() as p:
        b, pg = _fiche(p, serveur, 1366, 768)
        pg.click("#p-suivi-btn")
        pg.click("#p-suivi-pop .pv-statut")
        pg.wait_for_selector("body > .pv-statut-menu.open")
        pg.click("#p-suivi-pop .pv-statut")                                   # refermé par le même bouton
        pg.wait_for_selector("#fiche-statut-slot .pv-statut-opt[data-k=perdu]", state="attached")
        assert pg.evaluate("document.querySelectorAll('body > .pv-statut-menu').length") == 0
        pg.click("#p-suivi-pop .pv-statut")                                   # choix d'un statut : nouveau rendu
        pg.click(".pv-statut-menu.open .pv-statut-opt[data-k=devis]")
        pg.wait_for_function("document.getElementById('p-suivi-statut').textContent.includes('Devis')")
        assert pg.evaluate("document.querySelectorAll('.pv-statut-menu').length") == 1   # l'ancien menu supprimé
        pg.evaluate("document.querySelector('#fiche-statut-slot .pv-statut-opt[data-k=perdu]').click()")
        pg.wait_for_function("document.getElementById('p-suivi-statut').textContent.includes('Perdu')")
        b.close()
