# -*- coding: utf-8 -*-
"""Lot 7c — émettre une facture rectificative DEPUIS UN APERÇU IMPORTÉ, sans rien régénérer.

L'aperçu (PDF) porte « N° de facture : APERÇU — sans numéro ». Le serveur :
  1. lit le PDF et vérifie que c'est bien lui (la marque une seule fois, en page 1, avec son libellé) ;
  2. retire du flux de la page 1 les DEUX seules opérations de texte « N° de facture : » et « APERÇU — sans
     numéro » (rien d'autre n'est touché) ;
  3. réécrit la même ligne avec le numéro, dans les MÊMES polices (extraites de l'aperçu lui-même), la même taille,
     la même couleur, alignée sur le même bord droit et la même ligne de base.
Toutes les autres pages, et tout le reste de la page 1, sont repris tels quels. Bibliothèques : pypdf et reportlab
(licences permissives) — pas de PyMuPDF (AGPL).
"""
from __future__ import annotations

import io
import re

MARQUE = "APERÇU — sans numéro"
LIBELLE = "N° de facture :"


class ApercuInvalide(ValueError):
    """Le PDF importé n'est pas un aperçu utilisable : la raison, en clair."""


def _texte_normalise(t: str) -> str:
    return re.sub(r"[\s  ]+", " ", t or "").strip()


def _lecteur(pdf: bytes):
    from pypdf import PdfReader
    if not pdf or not pdf[:5] == b"%PDF-":
        raise ApercuInvalide("Le fichier importé n'est pas un PDF.")
    try:
        return PdfReader(io.BytesIO(pdf))
    except Exception as exc:  # pragma: no cover - PDF illisible
        raise ApercuInvalide(f"PDF illisible : {type(exc).__name__}.") from None


def _elements_texte(page) -> list[dict]:
    """Chaque opération de texte de la page : texte, position (Tm), police, taille."""
    out = []

    def visiteur(texte, cm, tm, font, taille):
        if texte and texte.strip():
            out.append({"texte": texte.strip(), "x": round(float(tm[4]), 2), "y": round(float(tm[5]), 2),
                        "police": str((font or {}).get("/BaseFont", "")), "taille": float(taille or 0),
                        "type3": str((font or {}).get("/Subtype", "")) == "/Type3"})
    page.extract_text(visitor_text=visiteur)
    return out


def _police_ttf(page, nom_ressource: str) -> bytes:
    """Le fichier TrueType embarqué d'une police de la page (Type0 → descendante → FontFile2)."""
    f = page["/Resources"]["/Font"][nom_ressource].get_object()
    if f.get("/Subtype") == "/Type0":
        f = f["/DescendantFonts"][0].get_object()
    fichier = f["/FontDescriptor"].get_object().get("/FontFile2")
    if fichier is None:
        raise ApercuInvalide("La police du numéro n'est pas embarquée dans l'aperçu : impossible d'écrire le numéro "
                             "dans la même police.")
    return fichier.get_object().get_data()


def _blocs_bt(operations) -> list[tuple[int, int, dict]]:
    """(début, fin, {Tm, Tf, rg}) de chaque bloc BT…ET."""
    blocs, i = [], 0
    while i < len(operations):
        if operations[i][1] == b"BT":
            j = i
            while j < len(operations) and operations[j][1] != b"ET":
                j += 1
            info = {}
            for ops, op in operations[i:j + 1]:
                if op in (b"Tm", b"Tf", b"rg") and op.decode() not in info:
                    info[op.decode()] = [x for x in ops]
            blocs.append((i, j, info))
            i = j
        i += 1
    return blocs


def analyser(pdf: bytes) -> dict:
    """Contrôle l'aperçu et rend ce qu'il faut pour le tamponner (et ses textes, pour les contrôles métier)."""
    from pypdf.generic import ContentStream
    r = _lecteur(pdf)
    textes = [_texte_normalise(p.extract_text() or "") for p in r.pages]
    tout = " ".join(textes)
    if tout.count(MARQUE) != 1 or MARQUE not in textes[0]:
        raise ApercuInvalide(f"L'aperçu doit porter « {MARQUE} » une seule fois, en page 1 "
                             f"(trouvé {tout.count(MARQUE)} fois).")
    p1 = r.pages[0]
    elts = _elements_texte(p1)
    valeur = next((e for e in elts if e["texte"] == MARQUE), None)
    libelle = next((e for e in elts if valeur and e["texte"] == LIBELLE and abs(e["y"] - valeur["y"]) < 0.5), None)
    if not valeur or not libelle:
        raise ApercuInvalide("La ligne « N° de facture : APERÇU — sans numéro » n'est pas écrite comme attendu "
                             "(libellé et marque sur la même ligne, en page 1).")
    ops = ContentStream(p1.get_contents(), r).operations
    cibles = []
    for debut, fin, info in _blocs_bt(ops):
        tm = info.get("Tm")
        if tm and any(abs(float(tm[4]) - e["x"]) < 0.05 and abs(float(tm[5]) - e["y"]) < 0.05 for e in (valeur, libelle)):
            cibles.append((debut, fin, info))
    if len(cibles) != 2:
        raise ApercuInvalide("La ligne du numéro n'est pas isolée dans l'aperçu : rien n'est modifié.")
    # La date d'émission de l'aperçu : écrite seule sur sa ligne (police lisible) ; les dates de l'original, en
    # polices Chromium « Type3 », ne se décodent pas en texte — seule celle de l'aperçu ressort.
    dates = [e["texte"] for e in elts if re.fullmatch(r"\d{2}/\d{2}/\d{4}", e["texte"]) and not e["type3"]]
    return {"pages": len(r.pages), "textes": textes, "texte": tout, "valeur": valeur, "libelle": libelle,
            "cibles": cibles, "date_emission": dates[0] if dates else ""}


def tamponner(pdf: bytes, numero_facture: str) -> bytes:
    """L'aperçu avec « N° de facture : {numero_facture} » à la place de la marque. Rien d'autre ne change."""
    from pypdf import PdfReader, PdfWriter
    from pypdf.generic import ContentStream
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.pdfgen import canvas

    a = analyser(pdf)
    lecteur = PdfReader(io.BytesIO(pdf))
    ecrivain = PdfWriter(clone_from=lecteur)
    p1 = ecrivain.pages[0]
    cs = ContentStream(p1.get_contents(), ecrivain)
    styles = {}
    for debut, fin, info in a["cibles"]:
        ressource, taille = str(info["Tf"][0]), float(info["Tf"][1])
        x, y = float(info["Tm"][4]), float(info["Tm"][5])
        role = "valeur" if abs(x - a["valeur"]["x"]) < 0.05 else "libelle"
        styles[role] = {"ressource": ressource, "taille": taille, "x": x, "y": y,
                        "rg": [float(v) for v in info.get("rg", [0, 0, 0])]}
    a_retirer = {k for debut, fin, _ in a["cibles"] for k in range(debut, fin + 1)}
    cs.operations = [op for k, op in enumerate(cs.operations) if k not in a_retirer]
    p1.replace_contents(cs)

    # Même police (celle de l'aperçu), même taille, même couleur, même ligne de base, même bord droit.
    polices = {}
    for role, st in styles.items():
        nom = f"Apercu{role.capitalize()}"
        pdfmetrics.registerFont(TTFont(nom, io.BytesIO(_police_ttf(lecteur.pages[0], st["ressource"]))))
        polices[role] = nom
    V, L = styles["valeur"], styles["libelle"]
    larg = lambda t, role, st: pdfmetrics.stringWidth(t, polices[role], st["taille"])  # noqa: E731
    bord_droit = V["x"] + larg(MARQUE, "valeur", V)
    ecart = V["x"] - (L["x"] + larg(LIBELLE, "libelle", L))
    xv = bord_droit - larg(numero_facture, "valeur", V)
    xl = xv - ecart - larg(LIBELLE, "libelle", L)
    boite = p1.mediabox
    tampon = io.BytesIO()
    c = canvas.Canvas(tampon, pagesize=(float(boite.width), float(boite.height)))
    for t, x, role, st in ((LIBELLE, xl, "libelle", L), (numero_facture, xv, "valeur", V)):
        c.setFillColorRGB(*st["rg"][:3])
        c.setFont(polices[role], st["taille"])
        c.drawString(x, st["y"], t)
    c.save()
    p1.merge_page(PdfReader(io.BytesIO(tampon.getvalue())).pages[0])
    sortie = io.BytesIO()
    ecrivain.write(sortie)
    resultat = sortie.getvalue()
    # Relecture : la marque a disparu, la ligne porte le numéro, le nombre de pages est le même.
    relu = PdfReader(io.BytesIO(resultat))
    t1 = _texte_normalise(relu.pages[0].extract_text() or "")
    if MARQUE in t1 or f"{LIBELLE} {numero_facture}" not in t1 or len(relu.pages) != a["pages"]:
        raise ApercuInvalide("Relecture du PDF tamponné en échec : rien n'est émis.")
    return resultat
