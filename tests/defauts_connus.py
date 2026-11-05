# -*- coding: utf-8 -*-
"""Défauts connus, marqués pour que la CI reste utile en attendant leur correction (décision d'Avi, 05/11/2026)."""
import sys

import pytest

# Sous Linux (image de production, CI), le texte des PDF générés n'a ni chiffres ni espaces (police Inter chargée
# depuis Google avec l'option « tnum ») : l'affichage est juste, la couche texte est vide. À RETIRER avec la
# correction de la police des PDF (Inter embarquée dans le document, comme le Master).
POLICE_PDF = pytest.mark.xfail(sys.platform.startswith("linux"), strict=False,
                               reason="Défaut connu, police des PDF : chiffres absents du texte des PDF sous Linux")
