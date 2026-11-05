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


# 05/11/2026 — ISOLATION ENTRE FICHIERS DE TEST. Tous les tests partagent ce DATA_DIR ; plusieurs fichiers y écrivent
# leur propre catalogue, leurs fiches ou leurs paramètres sans les remettre en place, et le fichier suivant héritait de
# cet état (24 échecs de test_lot14_quantite_pac en suite complète, alors qu'il passait seul). Désormais les fichiers
# JSON du DATA_DIR (fiches, catalogue, paramètres, compteurs, devis, factures…) sont photographiés au début de chaque fichier de test et remis à l'identique à la fin (créés
# pendant le fichier = supprimés). Le contenu et l'ordre des tests ne changent pas.
import pytest  # noqa: E402

def _fichiers_json():
    """Tous les fichiers JSON du DATA_DIR de test (fiches, catalogue, paramètres, compteurs, devis, factures…)."""
    out = []
    for racine, _dossiers, noms in os.walk(_TMP):
        out += [os.path.join(racine, n) for n in noms if n.endswith(".json")]
    return out


@pytest.fixture(autouse=True, scope="module")
def _donnees_partagees_par_fichier():
    photo = {c: open(c, "rb").read() for c in _fichiers_json()}
    yield
    for c in set(_fichiers_json()) | set(photo):
        if c in photo:
            os.makedirs(os.path.dirname(c), exist_ok=True)
            with open(c, "wb") as f:
                f.write(photo[c])
        elif os.path.exists(c):
            try:
                os.remove(c)
            except OSError:
                pass
