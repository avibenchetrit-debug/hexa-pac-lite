# -*- coding: utf-8 -*-
"""DATA_DIR temporaire fixe AVANT l'import de main (les chemins y sont des constantes module)."""
import os
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix="hexa-tests-")
os.environ["DATA_DIR"] = _TMP
os.environ["USERS_PATH"] = os.path.join(_TMP, "users.json")
os.environ.setdefault("AUTH_ENFORCE", "0")
os.environ.pop("RAILWAY_ENVIRONMENT", None)

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Lot 8b — tests instables sous Windows : un test réécrit un fichier JSON (fiches, paramètres…) pendant que le serveur
# de test le lit ; Windows refuse alors de remplacer un fichier ouvert (PermissionError [WinError 5], d'autant plus
# souvent que la machine est chargée). En test, et sous Windows seulement, le remplacement est retenté quelques fois.
# La prod (Linux) remplace toujours un fichier ouvert : rien n'y change.
if os.name == "nt":
    import time as _time
    _replace_os = os.replace

    def _replace_patient(src, dst, *a, **k):
        for essai in range(40):
            try:
                return _replace_os(src, dst, *a, **k)
            except PermissionError:
                if essai == 39:
                    raise
                _time.sleep(0.05)
    os.replace = _replace_patient
