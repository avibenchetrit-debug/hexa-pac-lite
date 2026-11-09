"""Outil interne : en-tête X-Robots-Tag sur toutes les réponses et robots.txt « Allow: / » (Google doit explorer pour lire le noindex) (09/11/2026)."""
from fastapi.testclient import TestClient

import main

client = TestClient(main.app)


def test_robots_txt_public_et_autorise_tout():
    r = client.get("/robots.txt")
    assert r.status_code == 200
    assert "User-agent: *" in r.text
    assert "Allow: /" in r.text
    assert "Disallow" not in r.text
    assert r.headers["x-robots-tag"] == "noindex, nofollow"


def test_en_tete_sur_toutes_les_reponses():
    for chemin in ("/health", "/login", "/", "/api/inexistante", "/static/inexistant.css"):
        r = client.get(chemin, follow_redirects=False)
        assert r.headers.get("x-robots-tag") == "noindex, nofollow", chemin
