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
