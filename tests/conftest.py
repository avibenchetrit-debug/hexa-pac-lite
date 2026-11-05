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
# de données PARTAGÉS sont photographiés au début de chaque fichier de test et remis à l'identique à la fin (créés
# pendant le fichier = supprimés). Le contenu et l'ordre des tests ne changent pas.
import pytest  # noqa: E402

_PARTAGES = ("catalogue_pac.json", "parametres_admin.json", "leads.json", "notes.json", "counters.json",
             "baremes.json", "delegataires.json", "devis_envoyes.json", "echanges.json", "modeles_email.json",
             "numeros_dossier.json", "users.json", os.path.join("devis", "devis_meta.json"))


@pytest.fixture(autouse=True, scope="module")
def _donnees_partagees_par_fichier():
    chemins = [os.path.join(_TMP, n) for n in _PARTAGES]
    photo = {c: open(c, "rb").read() for c in chemins if os.path.exists(c)}
    yield
    for c in chemins:
        if c in photo:
            os.makedirs(os.path.dirname(c), exist_ok=True)
            with open(c, "wb") as f:
                f.write(photo[c])
        elif os.path.exists(c):
            try:
                os.remove(c)
            except OSError:
                pass
