# -*- coding: utf-8 -*-
"""Devis envoyés depuis le 01/09/2026 qui affichent encore une MPR ballon > 0.

Depuis le 01/09/2026 (décret 2026-822), le chauffe-eau thermodynamique n'est plus
financé par MaPrimeRénov' par geste. Les devis envoyés avant le correctif peuvent
encore porter la ligne « Estimation aide MaPrimeRénov' — Chauffe-eau
thermodynamique » : ce script les liste pour reprise client.

LECTURE SEULE : aucun fichier n'est écrit. Le script n'importe pas main.py (dont
l'import crée des fichiers dans DATA_DIR) ; il lit directement :
  - devis_envoyes.json   (un élément par envoi : numero_prospect, sent_at, version…)
  - leads.json           (nom / prénom)
  - devis/<numero>_v<version>.html  (le devis tel qu'envoyé, figé à l'envoi)

Usage :
  python scripts/devis_ballon_depuis_septembre.py                 # DATA_DIR ou ./data
  python scripts/devis_ballon_depuis_septembre.py --data-dir /data
  python scripts/devis_ballon_depuis_septembre.py --zip hexa-backup-20260923-101500.zip
  options : --depuis 2026-09-01  --csv  (sortie CSV sur stdout)
"""
import argparse
import csv
import html
import json
import os
import re
import sys
import zipfile
from datetime import datetime
from zoneinfo import ZoneInfo

PARIS = ZoneInfo("Europe/Paris")

# Ligne du récapitulatif (templates/devis_pac_template.html, retirée par le Lot 1).
# L'apostrophe peut sortir brute ou échappée selon la version du rendu.
RE_MPR_BALLON = re.compile(
    r"MaPrimeR(?:é|&eacute;|&#233;)nov(?:'|&#39;|&#x27;|’)\s*—\s*Chauffe-eau thermodynamique"
    r"\s*</span>\s*<span[^>]*class=\"amount\"[^>]*>\s*-?\s*([^<]+?)\s*</span>"
)


class Source:
    """Lecture d'un DATA_DIR, soit dossier, soit zip de sauvegarde admin."""

    def __init__(self, data_dir=None, zip_path=None):
        self.data_dir = data_dir
        self.zip = zipfile.ZipFile(zip_path) if zip_path else None
        self.noms = set(self.zip.namelist()) if self.zip else set()

    def lire(self, relatif):
        relatif = relatif.replace("\\", "/")
        if self.zip:
            for nom in (relatif, "./" + relatif):
                if nom in self.noms:
                    return self.zip.read(nom).decode("utf-8")
            return None
        chemin = os.path.join(self.data_dir, *relatif.split("/"))
        if not os.path.exists(chemin):
            return None
        with open(chemin, encoding="utf-8") as f:
            return f.read()

    def json(self, relatif, defaut):
        brut = self.lire(relatif)
        if brut is None:
            return defaut
        try:
            return json.loads(brut)
        except ValueError:
            return defaut


def montant_fr(texte):
    """'1 200,00 €' -> 1200.0 (espaces fines / insécables tolérées)."""
    t = html.unescape(texte).replace("€", "")
    t = re.sub(r"[\s  ]", "", t).replace(",", ".")
    try:
        return float(t)
    except ValueError:
        return None


def date_envoi(valeur):
    try:
        d = datetime.fromisoformat(str(valeur or "").strip())
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=PARIS)


def html_du_devis(source, envoi):
    """Chemin enregistré à l'envoi (absolu, propre à la machine d'origine) -> relatif à DATA_DIR."""
    numero, version = envoi.get("numero_prospect"), envoi.get("version")
    candidats = []
    if envoi.get("html_file"):
        candidats.append("devis/" + os.path.basename(str(envoi["html_file"]).replace("\\", "/")))
    candidats.append(f"devis/{numero}_v{version}.html")
    for relatif in candidats:
        contenu = source.lire(relatif)
        if contenu is not None:
            return relatif, contenu
    return candidats[-1], None


def analyser(source, depuis):
    leads = {str(l.get("numero") or "").strip(): l for l in source.json("leads.json", []) if isinstance(l, dict)}
    envois = [e for e in source.json("devis_envoyes.json", []) if isinstance(e, dict)]
    trouves, introuvables, examines = [], [], 0
    for envoi in envois:
        quand = date_envoi(envoi.get("sent_at"))
        if quand is None or quand < depuis:
            continue
        examines += 1
        numero = str(envoi.get("numero_prospect") or "").strip()
        lead = leads.get(numero, {})
        nom = " ".join(x for x in (str(lead.get("nom") or "").strip(), str(lead.get("prenom") or "").strip()) if x) or "—"
        relatif, contenu = html_du_devis(source, envoi)
        ligne = {
            "numero_prospect": numero,
            "nom": nom,
            "date_envoi": quand.astimezone(PARIS).strftime("%d/%m/%Y %H:%M"),
            "version": envoi.get("version"),
            "variante": envoi.get("variante") or "",
            "fichier": relatif,
        }
        if contenu is None:
            introuvables.append(ligne)
            continue
        m = RE_MPR_BALLON.search(contenu)
        montant = montant_fr(m.group(1)) if m else None
        if montant and montant > 0:
            trouves.append({**ligne, "mpr_ballon": montant})
    return examines, trouves, introuvables


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data-dir", default=os.environ.get("DATA_DIR") or "data")
    ap.add_argument("--zip", help="sauvegarde admin (hexa-backup-*.zip) à lire à la place du dossier")
    ap.add_argument("--depuis", default="2026-09-01", help="date d'envoi minimale, AAAA-MM-JJ (heure de Paris)")
    ap.add_argument("--csv", action="store_true", help="sortie CSV sur stdout")
    args = ap.parse_args()

    depuis = datetime.fromisoformat(args.depuis).replace(tzinfo=PARIS)
    source = Source(data_dir=None if args.zip else args.data_dir, zip_path=args.zip)
    examines, trouves, introuvables = analyser(source, depuis)

    if args.csv:
        w = csv.writer(sys.stdout, delimiter=";")
        w.writerow(["numero_prospect", "nom", "date_envoi", "version", "variante", "mpr_ballon"])
        for t in trouves:
            w.writerow([t["numero_prospect"], t["nom"], t["date_envoi"], t["version"], t["variante"],
                        f"{t['mpr_ballon']:.2f}".replace(".", ",")])
        return 0

    origine = args.zip or os.path.abspath(args.data_dir)
    print(f"Source : {origine}")
    print(f"Devis envoyés depuis le {depuis:%d/%m/%Y} : {examines}")
    print(f"  dont avec MPR ballon > 0 : {len(trouves)}")
    for t in trouves:
        print(f"  - {t['numero_prospect']:<12} {t['nom']:<30} envoyé le {t['date_envoi']}  "
              f"v{t['version']} {t['variante']:<9}  MPR ballon {t['mpr_ballon']:,.2f} €".replace(",", " "))
    if introuvables:
        print(f"  ATTENTION : {len(introuvables)} devis sans HTML lisible (non vérifiés) :")
        for t in introuvables:
            print(f"  ? {t['numero_prospect']:<12} {t['nom']:<30} envoyé le {t['date_envoi']}  ({t['fichier']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
