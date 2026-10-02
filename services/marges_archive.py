# -*- coding: utf-8 -*-
"""Lot 9c — dossier facturé : les montants RÉELLEMENT facturés, lus dans le document archivé (facture la plus récente,
à défaut le devis archivé). Lecture seule : rien n'est écrit, rien n'est régénéré."""
import html as _html
import re

_ESPACES = r"[   ]"
_MONTANT = r"([\d   ]+,\d\d)\s*€"


def _n(s):
    return float(re.sub(_ESPACES, "", s).replace(",", ".")) if s else 0.0


def montants_du_document(texte: str) -> dict | None:
    """Total HT / TTC, prime CEE et MPR imprimés, délégataire nommé dans la mention RAI. None si illisible.
    (Certains PDF rendent les espaces en caractères nuls à l'extraction : ramenés à des espaces.)"""
    t = re.sub(r"[\s\x00]+", " ", texte or "")
    ht = re.search(r"\bTotal HT " + _MONTANT, t)
    ttc = re.search(r"\bTotal TTC " + _MONTANT, t)
    if not ht or not ttc:
        return None
    cee = re.search(r"Estimation aide Prime CEE\s*[-−–]\s*" + _MONTANT, t)
    # « Estimation aide MaPrimeRénov' — Pompe à chaleur air-eau - 5 000,00 € » (jamais au-delà de la ligne suivante)
    mpr = re.search(r"Estimation aide MaPrimeRénov'(?:(?!Estimation).){0,90}?\s[-−–]\s" + _MONTANT, t)
    m = re.search(r"Mention RAI\s*[-—–]\s*Partenaire\s+(\w+)", t, re.I)
    nom = (m.group(1) if m else "").upper()
    delegataire = "PICOTY" if nom.startswith("PICOTY") else ("ACE" if nom.startswith("ACE") else "")
    return {"total_ht": _n(ht.group(1)), "total_ttc": _n(ttc.group(1)), "cee": _n(cee.group(1)) if cee else 0.0,
            "mpr": _n(mpr.group(1)) if mpr else 0.0, "delegataire": delegataire}


def texte_html(contenu: str) -> str:
    sans = re.sub(r"<(style|script)\b.*?</\1>", " ", contenu or "", flags=re.S | re.I)
    return _html.unescape(re.sub(r"<[^>]+>", " ", sans))
