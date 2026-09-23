# -*- coding: utf-8 -*-
"""scripts/devis_ballon_depuis_septembre.py : repère les devis envoyés depuis le
01/09/2026 dont le HTML figé porte encore une MPR ballon > 0."""
import importlib.util
import json
import os
import zipfile

import pytest
from jinja2 import Environment

from services.service_devis import money

_SPEC = importlib.util.spec_from_file_location(
    "devis_ballon", os.path.join(os.path.dirname(__file__), "..", "scripts", "devis_ballon_depuis_septembre.py"))
script = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(script)

# Ligne copiée telle quelle de templates/devis_pac_template.html avant le Lot 1 (cd43b31).
ANCIENNE_LIGNE = (
    "{% if ballon_actif %}<div class=\"recap-line aide\"><span class=\"label\">Estimation aide MaPrimeRénov' — "
    "Chauffe-eau thermodynamique</span><span class=\"amount\">- {{ montant_mpr_ballon }}</span></div>{% endif %}"
)


def _devis_html(mpr_ballon):
    # autoescape comme Jinja2Templates : le rendu doit être celui réellement envoyé.
    ligne = Environment(autoescape=True).from_string(ANCIENNE_LIGNE).render(
        ballon_actif=mpr_ballon is not None, montant_mpr_ballon=money(mpr_ballon or 0))
    return f"<html><body><div class=\"recap\">{ligne}</div></body></html>"


@pytest.fixture
def data_dir(tmp_path):
    d = tmp_path / "data"
    (d / "devis").mkdir(parents=True)
    (d / "leads.json").write_text(json.dumps([
        {"numero": "PR-1", "nom": "MARTIN", "prenom": "Léa"},
        {"numero": "PR-2", "nom": "DURAND", "prenom": "Paul"},
        {"numero": "PR-3", "nom": "PETIT", "prenom": "Zoé"},
        {"numero": "PR-4", "nom": "ROUX", "prenom": "Max"},
    ]), encoding="utf-8")
    envois = [
        # août : hors période même avec MPR ballon
        {"numero_prospect": "PR-1", "version": 1, "sent_at": "2026-08-31T23:30:00+02:00", "variante": "devis",
         "html_file": "/data/devis/PR-1_v1.html"},
        # septembre, MPR ballon 1 200 € -> à reprendre
        {"numero_prospect": "PR-1", "version": 2, "sent_at": "2026-09-03T10:15:00+02:00", "variante": "devis",
         "html_file": "/data/devis/PR-1_v2.html"},
        # septembre, ballon à MPR 0 (catégorie supérieure) -> non listé
        {"numero_prospect": "PR-2", "version": 1, "sent_at": "2026-09-05T09:00:00+02:00", "variante": "pre_devis",
         "html_file": "/data/devis/PR-2_v1.html"},
        # septembre, sans ballon -> non listé
        {"numero_prospect": "PR-3", "version": 1, "sent_at": "2026-09-06T09:00:00+02:00", "variante": "devis",
         "html_file": "/data/devis/PR-3_v1.html"},
        # septembre, HTML absent -> signalé « non vérifié », jamais compté comme sain
        {"numero_prospect": "PR-4", "version": 1, "sent_at": "2026-09-07T09:00:00+02:00", "variante": "devis",
         "html_file": "/data/devis/PR-4_v1.html"},
    ]
    (d / "devis_envoyes.json").write_text(json.dumps(envois), encoding="utf-8")
    (d / "devis" / "PR-1_v1.html").write_text(_devis_html(800), encoding="utf-8")
    (d / "devis" / "PR-1_v2.html").write_text(_devis_html(1200), encoding="utf-8")
    (d / "devis" / "PR-2_v1.html").write_text(_devis_html(0), encoding="utf-8")
    (d / "devis" / "PR-3_v1.html").write_text(_devis_html(None), encoding="utf-8")
    return d


def _verifier(examines, trouves, introuvables):
    assert examines == 4
    assert [(t["numero_prospect"], t["nom"], t["date_envoi"], t["mpr_ballon"]) for t in trouves] == [
        ("PR-1", "MARTIN Léa", "03/09/2026 10:15", 1200.0)]
    assert [t["numero_prospect"] for t in introuvables] == ["PR-4"]


def test_le_motif_reconnait_la_ligne_telle_que_rendue():
    rendu = _devis_html(1200)
    # Texte littéral du gabarit : Jinja ne l'échappe pas, l'apostrophe sort brute.
    assert "MaPrimeRénov' — Chauffe-eau" in rendu
    assert script.montant_fr(script.RE_MPR_BALLON.search(rendu).group(1)) == 1200.0
    # Forme échappée (autre rendu / copie navigateur) : reconnue aussi.
    echappe = rendu.replace("MaPrimeRénov'", "MaPrimeRénov&#39;")
    assert script.montant_fr(script.RE_MPR_BALLON.search(echappe).group(1)) == 1200.0


def test_dossier(data_dir):
    _verifier(*script.analyser(script.Source(data_dir=str(data_dir)), script.datetime(2026, 9, 1, tzinfo=script.PARIS)))


def test_zip_de_sauvegarde(data_dir, tmp_path):
    archive = tmp_path / "hexa-backup.zip"
    with zipfile.ZipFile(archive, "w") as z:
        for racine, _, fichiers in os.walk(data_dir):
            for f in fichiers:
                chemin = os.path.join(racine, f)
                z.write(chemin, os.path.relpath(chemin, data_dir))
    _verifier(*script.analyser(script.Source(zip_path=str(archive)), script.datetime(2026, 9, 1, tzinfo=script.PARIS)))


def test_le_script_n_ecrit_rien(data_dir):
    avant = {p: os.path.getmtime(os.path.join(r, p)) for r, _, fs in os.walk(data_dir) for p in fs}
    script.analyser(script.Source(data_dir=str(data_dir)), script.datetime(2026, 9, 1, tzinfo=script.PARIS))
    apres = {p: os.path.getmtime(os.path.join(r, p)) for r, _, fs in os.walk(data_dir) for p in fs}
    assert avant == apres
