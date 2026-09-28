# -*- coding: utf-8 -*-
"""Prix au m² des ventes réelles (DVF, Etalab) — même source et même méthode que le Master
(hexa-simulateur-2/app/valeur_dvf.py, 25/09/2026), plus le 1er et le 3e quartile.

Source : https://files.data.gouv.fr/geo-dvf/latest/csv/{année}/communes/{dép}/{insee}.csv — ventes enregistrées
par la DGFiP, gratuites, sans clé. Code INSEE depuis geo.api.gouv.fr (arrondissements de Paris / Lyon / Marseille
prioritaires). Calcul : ventes d'UN SEUL local du type voulu (maison ou appartement), surface > 0, prix au m²
entre 300 et 20 000 €, sur les trois années disponibles les plus récentes ; au moins 5 ventes. Médiane, Q1, Q3.

pac-lite écrit ces prix dans les champs EXISTANTS prix_m2_estime / prix_m2_min / prix_m2_max ; la valeur du bien
reste prix_m2_estime × surface. Jamais bloquant : une panne rend {ok: False, indisponible: True}."""
from __future__ import annotations

import csv
import io
import json
import os
import statistics
import time
import urllib.request
from datetime import date

URL_COMMUNES = ("https://geo.api.gouv.fr/communes?codePostal={cp}"
                "&type=commune-actuelle,arrondissement-municipal&fields=nom,code,codeDepartement")
URL_DVF = "https://files.data.gouv.fr/geo-dvf/latest/csv/{annee}/communes/{dep}/{insee}.csv"
NB_ANNEES = 3
VENTES_MIN = 5
PRIX_M2_MIN, PRIX_M2_MAX = 300.0, 20000.0
CACHE_JOURS = 30


def _get_http(url: str, timeout: float = 20.0):
    """Texte de la réponse, ou None sur toute erreur (404 compris)."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "HexaRenov-CRM/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read().decode("utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        return None


GET = _get_http


def type_dvf(type_logement) -> str:
    return "Appartement" if "appart" in str(type_logement or "").lower() else "Maison"


def _commune(cp: str, ville: str):
    brut = GET(URL_COMMUNES.format(cp=cp))
    if brut is None:
        return None, True
    try:
        communes = json.loads(brut or "[]")
    except ValueError:
        return None, True
    if not communes:
        return None, False
    arr = [c for c in communes if "arrondissement" in str(c.get("nom", "")).lower()]
    if arr:
        return arr[0], False
    v = (ville or "").strip().lower()
    for c in communes:
        if v and str(c.get("nom", "")).lower() == v:
            return c, False
    return communes[0], False


def prix_m2_depuis_csv(textes: list, type_local: str) -> list:
    par_mutation = {}
    for texte in textes:
        for ligne in csv.DictReader(io.StringIO(texte)):
            if (ligne.get("nature_mutation") or "") != "Vente":
                continue
            m = par_mutation.setdefault(ligne.get("id_mutation") or "", {"valeur": ligne.get("valeur_fonciere"), "locaux": []})
            tl = ligne.get("type_local") or ""
            if tl in ("Maison", "Appartement", "Local industriel. commercial ou assimilé"):
                m["locaux"].append((tl, ligne.get("surface_reelle_bati")))
    prix = []
    for m in par_mutation.values():
        if len(m["locaux"]) != 1 or m["locaux"][0][0] != type_local:
            continue
        try:
            valeur, surface = float(m["valeur"] or 0), float(m["locaux"][0][1] or 0)
        except (TypeError, ValueError):
            continue
        if valeur > 0 and surface > 0 and PRIX_M2_MIN <= valeur / surface <= PRIX_M2_MAX:
            prix.append(valeur / surface)
    return prix


def _cache_lire(dossier, cle):
    if not dossier:
        return None
    f = os.path.join(dossier, cle + ".json")
    try:
        if os.path.isfile(f) and time.time() - os.path.getmtime(f) < CACHE_JOURS * 86400:
            with open(f, encoding="utf-8") as fh:
                return json.load(fh)
    except Exception:  # noqa: BLE001
        return None
    return None


def _cache_ecrire(dossier, cle, valeur):
    if not dossier:
        return
    try:
        os.makedirs(dossier, exist_ok=True)
        tmp = os.path.join(dossier, cle + ".json.tmp")
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(valeur, fh, ensure_ascii=False)
        os.replace(tmp, os.path.join(dossier, cle + ".json"))
    except Exception:  # noqa: BLE001
        pass


def phrase_source(r: dict) -> str:
    genre = "de maisons" if r["type"] == "Maison" else "d'appartements"
    return f"médiane de {r['nb']} ventes {genre} à {r['commune']}, {r['periode']}"


def prix_m2(cp: str, ville: str, type_logement, *, cache=None, annee=None) -> dict:
    """{ok, prix_m2, q1, q3, nb, commune, type, periode, source} ou {ok: False, indisponible, raison}."""
    cp = "".join(ch for ch in str(cp or "") if ch.isdigit())[:5]
    if len(cp) != 5:
        return {"ok": False, "indisponible": False, "raison": "code postal du chantier absent"}
    type_local = type_dvf(type_logement)
    cle_commune = "commune_" + cp + "_" + "".join(ch if ch.isalnum() else "-" for ch in (ville or "").strip().lower())
    commune = _cache_lire(cache, cle_commune)
    if not commune:
        commune, panne = _commune(cp, ville)
        if not commune:
            return ({"ok": False, "indisponible": True, "raison": "données DVF indisponibles pour le moment"} if panne
                    else {"ok": False, "indisponible": False, "raison": f"commune introuvable pour le code postal {cp}"})
        _cache_ecrire(cache, cle_commune, commune)
    cle = f"{commune.get('code', '')}_{type_local}"
    en_cache = _cache_lire(cache, cle)
    if en_cache and en_cache.get("ok"):
        return en_cache
    fin = annee or date.today().year
    textes, annees, pannes = [], [], 0
    for a in range(fin, fin - NB_ANNEES - 2, -1):
        t = GET(URL_DVF.format(annee=a, dep=commune.get("codeDepartement", ""), insee=commune.get("code", "")))
        if t is None:
            pannes += 1
        elif t.startswith("id_mutation"):
            textes.append(t)
            annees.append(a)
        if len(annees) == NB_ANNEES:
            break
    if not annees and pannes:
        return {"ok": False, "indisponible": True, "raison": "données DVF indisponibles pour le moment"}
    prix = prix_m2_depuis_csv(textes, type_local)
    nom = commune.get("nom", "")
    if len(prix) < VENTES_MIN:
        genre = "de maisons" if type_local == "Maison" else "d'appartements"
        return {"ok": False, "indisponible": False,
                "raison": f"trop peu de ventes {genre} à {nom} dans les données DVF ({len(prix)})"}
    q1, _mediane, q3 = statistics.quantiles(prix, n=4, method="inclusive")
    r = {"ok": True, "prix_m2": round(statistics.median(prix)), "q1": round(q1), "q3": round(q3), "nb": len(prix),
         "commune": nom, "type": type_local,
         "periode": f"{min(annees)}-{max(annees)}" if len(annees) > 1 else str(annees[0])}
    r["source"] = phrase_source(r)
    _cache_ecrire(cache, cle, r)
    return r
