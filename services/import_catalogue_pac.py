"""Import du catalogue PAC depuis un fichier Excel (format fixe multi-onglets).

Chaque onglet : champs en LIGNES (col. A = libellé), modèles en COLONNES.
Ligne d'en-tête = col. A "Champ" ; ligne séparatrice = col. A contient "source".
Zone du haut = specs (-> description_specs), bloc du bas = 9 champs source.
Ne fait AUCUNE écriture : renvoie la liste de modèles au format catalogue.
"""
from openpyxl import load_workbook

# Libellé source (normalisé) -> clé(s) du modèle catalogue
_SOURCE_MAP = {
    "ref interne": "ref",
    "nom commerciale": "nom",
    "usage": "usage",
    "alimentation": "alim",
    "puissance kw (35°c)": ("puiss35", "puiss_chauf"),
    "etas 35°c (%)": "etas35",
    "etas 55°c (%)": "etas55",
    "prix achat ht": "achat",
    "prix vente ttc": "ttc",
    # Champs de tracabilite : stockes tels quels, branches sur AUCUN calcul.
    "référence fabricant": "ref_fabricant",
    "référence eprel": "eprel",
    "numéro d'agrément": "agrement",
}


def _norm_label(v):
    # L'apostrophe typographique d'Excel doit matcher la cle droite ("numéro d'agrément").
    s = str(v if v is not None else "").replace("’", "'")
    return " ".join(s.strip().lower().split())


def _to_number(v):
    """virgule -> point, renvoie int si entier, float sinon, None si vide/non numérique."""
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        n = float(v)
    else:
        s = "".join(ch for ch in str(v) if not ch.isspace()).replace(",", ".")
        if not s:
            return None
        try:
            n = float(s)
        except ValueError:
            return None
    return int(n) if n == int(n) else n


def _cell_text(v):
    """Valeur 'telle quelle' pour affichage : '' si vide, entier sans '.0'."""
    if v is None:
        return ""
    if isinstance(v, float) and v == int(v):
        return str(int(v))
    return str(v).strip()


# Lot 10 : une classe énergétique n'est pas en kW (le fichier fournisseur porte encore « (kW) »)
LIBELLES_CORRIGES = {
    "Classe énergétique chauffage 35°C / 55°C (kW)": "Classe énergétique chauffage 35°C / 55°C",
    "Classe éner. chauffage 35°C / 55°C (kW)": "Classe énergétique chauffage 35°C / 55°C",           # Lot 10b
    "Volume ballon ECS / Profil soutirage": "Volume ballon ECS (L) / Profil soutirage",
    "Poids module ext. / int. en fonction (kg)": "Poids module ext. en fonction (kg)",
    "Poids à vide unité extérieure(kg)": "Poids à vide unité extérieure (kg)",
}


def _spec_label(a):
    lbl = str(a).strip()
    lbl = LIBELLES_CORRIGES.get(lbl, lbl)
    return "Technologie" if lbl.lower() == "techno" else lbl


def _parse_sheet(ws, warnings):
    rows = [list(r) for r in ws.iter_rows(values_only=True)]
    if not rows:
        return []
    header_i = separ_i = None
    for i, row in enumerate(rows):
        a = _norm_label(row[0] if row else "")
        if header_i is None and a == "champ":
            header_i = i
        elif header_i is not None and separ_i is None and "source" in a:
            separ_i = i
            break
    if header_i is None or separ_i is None:
        warnings.append(f"Onglet '{ws.title}': zones 'Champ'/'SOURCE' introuvables -> ignoré.")
        return []

    header = rows[header_i]
    model_cols = [j for j in range(1, len(header)) if _cell_text(header[j])]
    spec_rows = [rows[i] for i in range(header_i + 1, separ_i) if _cell_text(rows[i][0] if rows[i] else "")]
    source = {}
    for i in range(separ_i + 1, len(rows)):
        key = _norm_label(rows[i][0] if rows[i] else "")
        if key in _SOURCE_MAP:
            source[key] = rows[i]

    def cell(label_key, j):
        row = source.get(label_key)
        return row[j] if (row is not None and j < len(row)) else None

    out = []
    for j in model_cols:
        ref = _cell_text(cell("ref interne", j))
        ttc = _to_number(cell("prix vente ttc", j))
        col_name = _cell_text(header[j]) or f"col{j+1}"
        if not ref:
            warnings.append(f"Onglet '{ws.title}', modèle '{col_name}': ref vide -> refusé.")
            continue
        if ttc is None:
            warnings.append(f"Onglet '{ws.title}', modèle '{ref}': 'Prix vente TTC' non numérique -> refusé.")
            continue
        puiss = _to_number(cell("puissance kw (35°c)", j))
        model = {
            "ref": ref,
            "nom": _cell_text(cell("nom commerciale", j)),
            "usage": _cell_text(cell("usage", j)),
            "alim": _cell_text(cell("alimentation", j)),
            "puiss35": puiss,
            "puiss_chauf": puiss,
            "etas35": _to_number(cell("etas 35°c (%)", j)),
            "etas55": _to_number(cell("etas 55°c (%)", j)),
            "achat": _to_number(cell("prix achat ht", j)),
            "ttc": ttc,
            "ref_fabricant": _cell_text(cell("référence fabricant", j)) or None,
            "eprel": _cell_text(cell("référence eprel", j)) or None,
            "agrement": _cell_text(cell("numéro d'agrément", j)) or None,
            "description_specs": [
                {"champ": _spec_label(r[0]), "valeur": _cell_text(r[j] if j < len(r) else "")}
                for r in spec_rows
            ],
        }
        corriger_groupes_exterieurs_ariston(model)           # Lot 10c : même correction qu'à la migration
        out.append(model)
    return out


# Lot 10c — groupes extérieurs des Ariston Nimbus COMPACT (DUO). Source : Ariston, « Doc Pro Nimbus Plus Net R32 »
# (BD 03 2023), tableau UNITÉ EXTÉRIEURE : poids 83 kg (groupe 80, réf. 3301888), 111 kg (120 / 120 T, réf. 3302222 /
# 3302223), 119 kg (150 / 150 T, réf. 3302224 / 3302225) ; dimensions 1016 x 1106 x 380 (80) et 1016 x 1506 x 380
# (120 et 150). Les DUO utilisent les mêmes groupes extérieurs (80 / 120 / 150 S NET). Une valeur n'est corrigée que si
# elle est encore l'ancienne valeur fausse (une valeur ressaisie ensuite n'est jamais réécrasée).
POIDS_EXT = "Poids module ext. en fonction (kg)"
DIM_EXT = "Dimensions groupe extérieur (HxLxP) (mm)"
_DIM_120_150 = ("1106 x 1016 x 380", "1506 x 1016 x 380")
CORRECTIONS_ARISTON_DUO = {
    "ARI-NIMBUS-NET-R32-DUO-12": {POIDS_EXT: ("83", "111"), DIM_EXT: _DIM_120_150},
    "ARI-NIMBUS-NET-R32-DUO-15": {DIM_EXT: _DIM_120_150},                    # poids 119 déjà juste
    "ARI-NIMBUS-NET-R32-DUO-12 TRI": {POIDS_EXT: (None, "111"), DIM_EXT: _DIM_120_150},   # None : ligne absente
    "ARI-NIMBUS-NET-R32-DUO-15 TRI": {POIDS_EXT: ("83", "119"), DIM_EXT: _DIM_120_150},
}


def corriger_groupes_exterieurs_ariston(model: dict) -> bool:
    """Applique CORRECTIONS_ARISTON_DUO à un modèle (en place). True si quelque chose a changé. Idempotent."""
    regles = CORRECTIONS_ARISTON_DUO.get(str(model.get("ref") or "").strip())
    specs = model.get("description_specs")
    if not regles or not isinstance(specs, list):
        return False
    change = False
    for champ, (ancien, nouveau) in regles.items():
        ligne = next((s for s in specs if isinstance(s, dict) and str(s.get("champ") or "").strip() == champ), None)
        if ligne is not None and str(ligne.get("valeur") or "").strip() == ancien:
            ligne["valeur"] = nouveau
            change = True
        elif ligne is None and ancien is None:                       # ligne absente : placée avant les dimensions
            i = next((k for k, s in enumerate(specs) if isinstance(s, dict) and s.get("champ") == DIM_EXT), len(specs))
            specs.insert(i, {"champ": champ, "valeur": nouveau})
            change = True
    return change


def parse_catalogue_xlsx_report(source):
    """Renvoie (models, warnings). 'source' = chemin ou objet file-like (BytesIO)."""
    wb = load_workbook(source, data_only=True, read_only=True)
    models, warnings = [], []
    for ws in wb.worksheets:
        models.extend(_parse_sheet(ws, warnings))
    seen = {}
    for m in models:
        seen[m["ref"]] = seen.get(m["ref"], 0) + 1
    for ref, n in seen.items():
        if n > 1:
            warnings.append(f"Réf '{ref}' présente {n} fois (doublon inter-onglets).")
    return models, warnings


