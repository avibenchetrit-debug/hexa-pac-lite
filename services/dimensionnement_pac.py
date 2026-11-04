# -*- coding: utf-8 -*-
"""Lot A (notedim-master, 04/11/2026) — règles de dimensionnement communes au serveur et à l'écran (même logique que
le Master hexa-simulateur-2, décisions d'Avi du 04/11) :

* PUISSANCE RETENUE d'un modèle : sa puissance à −7 °C extérieur / 55 °C d'eau si elle est saisie ET VALIDÉE dans
  l'Admin ; sinon sa puissance à 35 °C, et la note le dit (« puissance à 35 °C, valeur à −7 °C / 55 °C non
  renseignée »). Une valeur « à valider » compte comme absente (règle du Master, `puissance_dimensionnement`).
* PLAGE DE COHÉRENCE : puissance installée (quantité × puissance retenue) entre 60 % et 130 % de la puissance requise
  (en dessous : sous-dimensionnement, l'appoint prend le relais ; au-dessus : surdimensionnement, cycles courts).
* TEMPÉRATURE DE DÉPART REQUISE : celle saisie sur la fiche (étape Chauffage), sinon celle de l'émetteur (Admin).
  Un modèle dont la température de départ maximale est inférieure n'est jamais proposé.

Fonctions pures ; la migration du catalogue au démarrage est dans main.py (`_migrate_catalogue_dimensionnement`).
"""

PLAGE_COHERENCE_MIN_PCT = 60
PLAGE_COHERENCE_MAX_PCT = 130
LIBELLES_COHERENCE = {"sous": "sous-dimensionnement", "ok": "cohérent", "sur": "surdimensionnement"}

# Température de départ requise par type d'émetteur (°C) — défauts d'Avi (04/11), réglables dans l'Admin
TEMPERATURES_DEPART_DEFAUT = {
    "radiateurs_fonte": 65,
    "radiateurs_classiques": 55,
    "radiateurs_basse_temp": 55,
    "plancher_chauffant": 35,
    "convecteurs_electriques": 55,
}
LIBELLES_EMETTEURS = {
    "radiateurs_fonte": "des radiateurs fonte",
    "radiateurs_classiques": "des radiateurs acier",
    "radiateurs_basse_temp": "des radiateurs basse température",
    "plancher_chauffant": "un plancher chauffant",
    "convecteurs_electriques": "des convecteurs électriques remplacés par des radiateurs",
}

CHAMP_M7_55 = "puissance_m7_55_kw"
CHAMP_M7_55_VALIDE = "puissance_m7_55_valide"
CHAMP_M7_55_SOURCE = "puissance_m7_55_source"
CHAMP_TEMP_MAX = "temp_max_depart_c"
ORIGINE_M7_55 = "m7_55"
ORIGINE_35 = "35"
MENTION_35 = "puissance à 35 °C, valeur à −7 °C / 55 °C non renseignée"

# Valeurs à −7 °C / 55 °C relevées dans le Master (catalogue_pac_aireau.json, sauvegarde du 04/11/2026), TOUTES
# « à valider » là-bas : importées NON VALIDÉES (elles ne comptent pas tant qu'Avi ne les a pas validées dans
# l'Admin). ⚠ ALTHERMA : même valeur pour 14, 16 et 18 kW (point de certification) — manifestement à revoir.
VALEURS_M7_55_MASTER = {
    "ATL-EXCELLIA-S-9": (7.1, "Atlantic, documentation « Alfea Excellia S » réf. DOM2906 (oct. 2025), p. 4"),
    "ATL-EXCELLIA-S-12": (8.63, "Atlantic, documentation « Alfea Excellia S » réf. DOM2906 (oct. 2025), p. 4"),
    "ATL-EXCELLIA-S-14": (10.28, "Atlantic, documentation « Alfea Excellia S » réf. DOM2906 (oct. 2025), p. 4"),
    "ATL-EXCELLIA-S-12 TRI": (8.63, "Atlantic, documentation « Alfea Excellia S » réf. DOM2906 (oct. 2025), p. 4"),
    "ATL-EXCELLIA-S-14 TRI": (10.28, "Atlantic, documentation « Alfea Excellia S » réf. DOM2906 (oct. 2025), p. 4"),
    "ATL-EXCELLIA-S-DUO-9": (7.1, "Atlantic, documentation « Alfea Excellia S » réf. DOM2906 (oct. 2025), p. 4"),
    "ATL-EXCELLIA-S-DUO-12": (8.63, "Atlantic, documentation « Alfea Excellia S » réf. DOM2906 (oct. 2025), p. 4"),
    "ATL-EXCELLIA-S-DUO-14": (10.28, "Atlantic, documentation « Alfea Excellia S » réf. DOM2906 (oct. 2025), p. 4"),
    "ATL-EXCELLIA-S-DUO-12 TRI": (8.63, "Atlantic, documentation « Alfea Excellia S » réf. DOM2906 (oct. 2025), p. 4"),
    "ATL-EXCELLIA-S-DUO-14 TRI": (10.28, "Atlantic, documentation « Alfea Excellia S » réf. DOM2906 (oct. 2025), p. 4"),
    "DAI-ALTHERMA-3HHT-R32-14": (9.81, "Daikin 4D126945J « EPRA14-18DV7 / EPRA14-18DW7 – Rated data for certification programmes »"),
    "DAI-ALTHERMA-3HHT-R32-16": (9.81, "Daikin 4D126945J « EPRA14-18DV7 / EPRA14-18DW7 – Rated data for certification programmes »"),
    "DAI-ALTHERMA-3HHT-R32-18": (9.81, "Daikin 4D126945J « EPRA14-18DV7 / EPRA14-18DW7 – Rated data for certification programmes »"),
    "DAI-ALTHERMA-3HHT-R32-14 TRI": (9.21, "Daikin 4D126945J « EPRA14-18DV7 / EPRA14-18DW7 – Rated data for certification programmes »"),
    "DAI-ALTHERMA-3HHT-R32-16 TRI": (9.21, "Daikin 4D126945J « EPRA14-18DV7 / EPRA14-18DW7 – Rated data for certification programmes »"),
    "DAI-ALTHERMA-3HHT-R32-18 TRI": (9.21, "Daikin 4D126945J « EPRA14-18DV7 / EPRA14-18DW7 – Rated data for certification programmes »"),
    "ARI-NIMBUS-NET-R32-8": (6.6, "Ariston, brochure « Nimbus Plus Net R32 » 2023 réf. DOCO21, p. 11"),
    "ARI-NIMBUS-NET-R32-12": (8.3, "Ariston, brochure « Nimbus Plus Net R32 » 2023 réf. DOCO21, p. 11"),
    "ARI-NIMBUS-NET-R32-15": (10.2, "Ariston, brochure « Nimbus Plus Net R32 » 2023 réf. DOCO21, p. 11"),
    "ARI-NIMBUS-NET-R32-12 TRI": (8.3, "Ariston, brochure « Nimbus Plus Net R32 » 2023 réf. DOCO21, p. 11"),
    "ARI-NIMBUS-NET-R32-15 TRI": (10.2, "Ariston, brochure « Nimbus Plus Net R32 » 2023 réf. DOCO21, p. 11"),
    "ARI-NIMBUS-NET-R32-DUO-8": (6.6, "Ariston, page produit « Nimbus Compact S Net R32 », onglet Données techniques"),
    "ARI-NIMBUS-NET-R32-DUO-12": (8.3, "Ariston, page produit « Nimbus Compact S Net R32 », onglet Données techniques"),
    "ARI-NIMBUS-NET-R32-DUO-15": (10.2, "Ariston, page produit « Nimbus Compact S Net R32 », onglet Données techniques"),
    "ARI-NIMBUS-NET-R32-DUO-12 TRI": (8.3, "Ariston, page produit « Nimbus Compact S Net R32 », onglet Données techniques"),
}


def _n(v):
    try:
        if v is None or v == "" or isinstance(v, bool):
            return None
        return float(str(v).replace(" ", "").replace(" ", "").replace(",", "."))
    except (TypeError, ValueError):
        return None


def coherence(total_kw, besoin_kw):
    """{pct, statut (sous / ok / sur), libelle} de la puissance installée face au besoin, ou None."""
    t, b = _n(total_kw), _n(besoin_kw)
    if not t or not b or t <= 0 or b <= 0:
        return None
    if t < b * PLAGE_COHERENCE_MIN_PCT / 100:
        statut = "sous"
    elif t > b * PLAGE_COHERENCE_MAX_PCT / 100:
        statut = "sur"
    else:
        statut = "ok"
    return {"pct": int(t / b * 100 + 0.5), "statut": statut, "libelle": LIBELLES_COHERENCE[statut]}


def plage(besoin_kw):
    """Bornes de la plage de cohérence en kW (arrondies au dixième, comme le Master)."""
    b = _n(besoin_kw)
    if not b or b <= 0:
        return None
    return {"min_kw": round(b * PLAGE_COHERENCE_MIN_PCT / 100, 1), "max_kw": round(b * PLAGE_COHERENCE_MAX_PCT / 100, 1),
            "min_pct": PLAGE_COHERENCE_MIN_PCT, "max_pct": PLAGE_COHERENCE_MAX_PCT}


def puissance_35(m):
    m = m or {}
    for cle in ("puiss_chauf", "puiss35", "puissance_kw"):
        v = _n(m.get(cle))
        if v is not None:
            return v
    return 0.0


def puissance_retenue(m):
    """(kW, origine) : −7 °C / 55 °C si saisie et validée, sinon 35 °C."""
    m = m or {}
    v = _n(m.get(CHAMP_M7_55))
    if v and v > 0 and m.get(CHAMP_M7_55_VALIDE) is True:
        return v, ORIGINE_M7_55
    return puissance_35(m), ORIGINE_35


def libelle_origine(origine):
    return "à −7 °C / 55 °C" if origine == ORIGINE_M7_55 else MENTION_35


def temp_max(m):
    """Température de départ maximale (°C) : champ du catalogue, sinon la fiche produit (« Temp. max de départ »,
    ou le haut de la « Plage température sortie d'eau »). None si inconnue."""
    m = m or {}
    v = _n(m.get(CHAMP_TEMP_MAX))
    if v:
        return v
    for spec in m.get("description_specs") or []:
        if not isinstance(spec, dict):
            continue
        champ, valeur = str(spec.get("champ", "")), str(spec.get("valeur", ""))
        if "max de départ" in champ.lower():
            return _n(valeur.split("/")[0])
        if "sortie d" in champ.lower() and "/" in valeur:
            return _n(valeur.split("/")[-1])
    return None


def temperatures_depart(admin):
    """Table émetteur -> température requise : Admin (`temperatures_depart`) par-dessus les défauts."""
    out = dict(TEMPERATURES_DEPART_DEFAUT)
    for k, v in ((admin or {}).get("temperatures_depart") or {}).items():
        n = _n(v)
        if k in out and n and 20 <= n <= 90:
            out[k] = n
    return out


def temperature_requise(prospect, admin):
    """(°C, origine « fiche » / « emetteur ») ou (None, "") : la valeur saisie à l'étape Chauffage d'abord."""
    p = prospect or {}
    saisie = _n(p.get("temperature_depart_c"))
    if saisie and 20 <= saisie <= 90:
        return saisie, "fiche"
    t = temperatures_depart(admin).get(str(p.get("type_emetteurs") or "").strip())
    return (t, "emetteur") if t else (None, "")


def alerte_temperature(m, t_requise, type_emetteurs=""):
    """« Température max 60 °C : insuffisante pour des radiateurs fonte » — vide si le modèle convient ou si une des
    deux températures est inconnue."""
    tm = temp_max(m)
    if not tm or not t_requise or tm >= t_requise:
        return ""
    pour = LIBELLES_EMETTEURS.get(str(type_emetteurs or ""), f"une température de départ de {_fmt(t_requise)} °C")
    return f"Température max {_fmt(tm)} °C : insuffisante pour {pour} ({_fmt(t_requise)} °C requis)"


def _fmt(x):
    x = float(x)
    return str(int(x)) if x == int(x) else f"{x:g}".replace(".", ",")


def migrer_catalogue(catalogue):
    """Démarrage, idempotent : ajoute aux modèles qui ne l'ont pas la valeur −7 °C / 55 °C du Master (NON validée)
    et sa source, et la température max lue sur la fiche produit. Ne touche jamais une valeur déjà présente.
    Rend (catalogue, changé)."""
    change = False
    for m in catalogue if isinstance(catalogue, list) else []:
        if not isinstance(m, dict):
            continue
        ref = str(m.get("ref") or "").strip()
        if CHAMP_M7_55 not in m and ref in VALEURS_M7_55_MASTER:
            kw, src = VALEURS_M7_55_MASTER[ref]
            m[CHAMP_M7_55] = kw
            m[CHAMP_M7_55_SOURCE] = "Master (à valider) — " + src
            m[CHAMP_M7_55_VALIDE] = False
            change = True
        if CHAMP_TEMP_MAX not in m:
            tm = temp_max(m)
            if tm:
                m[CHAMP_TEMP_MAX] = tm
                change = True
    return catalogue, change
