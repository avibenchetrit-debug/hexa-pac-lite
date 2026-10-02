# -*- coding: utf-8 -*-
"""Lot 8e : vitesse sans rien changer au contenu. Réponses compressées (gzip) ; polices de la page servies par l'appli
(plus de feuille Google bloquante) ; une lecture identique déjà en cours est partagée (catalogue, paramètres, zones).
Vrai Chromium ; fiches fabriquées (test_fix_pdf)."""
import gzip
import os

import main
from fastapi.testclient import TestClient
from test_fix_pdf import page, serveur, sync_api  # noqa: F401  (fixtures réutilisées)


def test_index_compresse_et_identique():
    c = TestClient(main.app)
    brut = c.get("/nouveau", headers={"Accept-Encoding": "identity"})
    comp = c.get("/nouveau", headers={"Accept-Encoding": "gzip"})
    assert brut.headers.get("content-encoding") is None
    assert comp.headers.get("content-encoding") == "gzip"
    assert comp.content == brut.content                                     # même page une fois décompressée
    taille = len(gzip.compress(brut.content))
    assert taille < len(brut.content) / 3


def test_polices_de_la_page_servies_par_l_appli():
    html = open(os.path.join(os.path.dirname(main.__file__), "templates", "index.html"), encoding="utf-8").read()
    assert 'href="https://fonts.googleapis.com/css2' not in html.split("chaufferPolicesDocuments")[0].replace(
        "rel: 'stylesheet', href: CSS", "")                                  # plus de feuille Google bloquante
    assert "url(/static/fonts/" in html and 'rel="preload"' in html
    for nom in set(x.split(")")[0] for x in html.split("url(/static/fonts/")[1:]):
        assert os.path.exists(os.path.join(os.path.dirname(main.__file__), "static", "fonts", nom)), nom
    c = TestClient(main.app)
    r = c.get("/static/fonts/" + html.split("url(/static/fonts/")[1].split(")")[0])
    assert r.status_code == 200 and len(r.content) > 10000


def test_lecture_partagee_mais_jamais_perimee(page):
    """Deux lectures simultanées : une seule requête ; une lecture après coup : nouvelle requête (pas de cache)."""
    page.goto(f"{page.base}/nouveau")
    page.wait_for_selector("#form-prospect", state="attached")
    page.wait_for_load_state("networkidle")
    vues = []
    page.on("request", lambda r: r.url.endswith("/api/catalogue-pac") and vues.append(1))
    res = page.evaluate("""async () => {
      const [a, b] = await Promise.all([fetch('/api/catalogue-pac'), fetch('/api/catalogue-pac')]);
      const ja = await a.json(), jb = await b.json();
      const c = await (await fetch('/api/catalogue-pac')).json();
      return [JSON.stringify(ja) === JSON.stringify(jb), JSON.stringify(ja) === JSON.stringify(c)];
    }""")
    page.wait_for_timeout(300)
    assert res == [True, True]
    assert len(vues) == 2                     # 1 pour les deux lectures simultanées + 1 pour la lecture suivante
