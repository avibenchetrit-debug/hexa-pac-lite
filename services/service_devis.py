import math
import re
from datetime import datetime


LABELS_ANAH = {
    "tres_modeste": "Très modeste (TMO)",
    "modeste": "Modeste (MO)",
    "intermediaire": "Intermédiaire (INT)",
    "superieur": "Supérieur (SUP)",
}

TYPE_EMETTEURS_LABELS = {
    "plancher_chauffant": "Plancher chauffant",
    "radiateurs_basse_temp": "Radiateurs basse température",
    "radiateurs_classiques": "Radiateurs classiques (acier récent)",
    "radiateurs_fonte": "Radiateurs fonte (anciens)",
    "convecteurs_electriques": "Convecteurs électriques",
}

# Lot 7a (30/09/2026) — exigé par le bureau de contrôle ACE, dans le bloc « Solution chauffage » du devis ET
# de la facture, sous le libellé BAR-TH-171 : l'ancien système DÉPOSÉ (chaudière fioul / gaz / charbon : rien
# d'autre n'est écrit), le type d'application (termes EXACTS d'ACE, deux cas) et l'usage.
ENERGIES_CHAUDIERE_DEPOSEE = ("fioul", "gaz", "charbon")


def lignes_solution_chauffage(prospect, state=None) -> dict:
    energie = str(value(prospect, "mode_chauffage", "chauffage_actuel", default="") or "").strip().lower()
    emetteurs = str(value(prospect, "type_emetteurs", default="") or "").strip().lower()
    service = str(value(state or {}, "service", default="chauffage_seul") or "").strip().lower()
    ancien = (f"Ancien système de chauffage déposé : chaudière {energie} — énergie : {energie}"
              if energie in ENERGIES_CHAUDIERE_DEPOSEE else "")
    if emetteurs == "plancher_chauffant":
        application = "Application : basse température"
    elif emetteurs.startswith("radiateurs"):
        application = "Application : moyenne ou haute température"
    else:
        application = ""
    usage = ("Usage : chauffage + eau chaude sanitaire" if service in ("chauffage_ecs", "chauffage+ecs")
             else "Usage : chauffage")
    return {"ancien_systeme": ancien, "application": application, "usage": usage,
            "depose_induits": (f"Dépose et évacuation de l'ancienne chaudière {energie}" if ancien
                               else "Dépose et évacuation des équipements remplacés - chaudière"),
            "energie_non_mentionnee": "" if ancien else (energie or "non renseignée")}


TEMP_BASE_ZONE = {"H1": -7, "H2": -4, "H3": 0}
# Zone climatique H1 / H2 / H3 par département : répartition OFFICIELLE utilisée par les fiches d'opérations
# standardisées CEE (dont BAR-TH-171 « Pompe à chaleur de type air/eau », facteur de zone H1 1,2 · H2 1 · H3 0,7).
# Source : ministère de la Transition écologique, « Répartition des départements par zone climatique » (tableau d'une
# page, sans date), https://www.ecologie.gouv.fr/sites/default/files/documents/La%20r%C3%A9partition%20des%20d%C3%A9partements%20par%20zone%20climatique.pdf
# — lu le 27/09/2026 ; mêmes listes que l'arrêté du 5 avril 1988, annexe I « Définition des zones climatiques »
# (https://www.legifrance.gouv.fr/codes/section_lc/JORFTEXT000000322499/LEGISCTA000006128878/). La Corse y est
# une seule ligne « 20 Corse » (H3) : « 20 », « 2A » et « 2B ». Outre-mer : arrêté du 22 décembre 2014 définissant
# les opérations standardisées d'économies d'énergie, article 4 (https://www.legifrance.gouv.fr/loda/id/JORFTEXT000029953752/) :
# France d'outre-mer en H3, sauf Saint-Pierre-et-Miquelon (975) en H1.
# La zone écrite dans un DPE / audit (sous-zones H1a…H3) ne sert jamais au calcul (affichage seulement).
DEPT_ZONE = {
    "01": "H1", "02": "H1", "03": "H1", "05": "H1", "08": "H1", "10": "H1", "14": "H1", "15": "H1", "19": "H1",
    "21": "H1", "23": "H1", "25": "H1", "27": "H1", "28": "H1", "38": "H1", "39": "H1", "42": "H1", "43": "H1",
    "45": "H1", "51": "H1", "52": "H1", "54": "H1", "55": "H1", "57": "H1", "58": "H1", "59": "H1", "60": "H1",
    "61": "H1", "62": "H1", "63": "H1", "67": "H1", "68": "H1", "69": "H1", "70": "H1", "71": "H1", "73": "H1",
    "74": "H1", "75": "H1", "76": "H1", "77": "H1", "78": "H1", "80": "H1", "87": "H1", "88": "H1", "89": "H1",
    "90": "H1", "91": "H1", "92": "H1", "93": "H1", "94": "H1", "95": "H1",
    "04": "H2", "07": "H2", "09": "H2", "12": "H2", "16": "H2", "17": "H2", "18": "H2", "22": "H2", "24": "H2",
    "26": "H2", "29": "H2", "31": "H2", "32": "H2", "33": "H2", "35": "H2", "36": "H2", "37": "H2", "40": "H2",
    "41": "H2", "44": "H2", "46": "H2", "47": "H2", "48": "H2", "49": "H2", "50": "H2", "53": "H2", "56": "H2",
    "64": "H2", "65": "H2", "72": "H2", "79": "H2", "81": "H2", "82": "H2", "84": "H2", "85": "H2", "86": "H2",
    "06": "H3", "11": "H3", "13": "H3", "20": "H3", "2A": "H3", "2B": "H3", "30": "H3", "34": "H3", "66": "H3", "83": "H3",
    "971": "H3", "972": "H3", "973": "H3", "974": "H3", "976": "H3", "975": "H1",
}
def value(obj, *keys, default=""):
    for key in keys:
        val = (obj or {}).get(key)
        if val not in (None, ""):
            return val
    return default


def float_value(raw, default=0.0):
    try:
        if raw is None or raw == "":
            return default
        return float(str(raw).replace("\u202f", "").replace(" ", "").replace(",", "."))
    except (TypeError, ValueError):
        return default


def money(value):
    amount = float_value(value)
    return f"{amount:,.2f}".replace(",", " ").replace(".", ",") + " €"


def number_fr(value, digits=1):
    try:
        return f"{float(value):.{digits}f}".replace(".", ",")
    except (TypeError, ValueError):
        return "0"


def normalize_zone(zone, cp=""):
    raw = str(zone or "").strip().upper().replace(" ", "")
    if raw.startswith("H1"):
        return "H1"
    if raw.startswith("H2"):
        return "H2"
    if raw.startswith("H3"):
        return "H3"
    cp = str(cp or "").strip()
    dept = cp[:3] if cp.startswith("97") else cp[:2].upper()
    return DEPT_ZONE.get(dept, "H1")


def calculer_zone_climatique(cp, zone=""):
    return normalize_zone(zone, cp)


# LOT 7a (30/09/2026) — TEMPÉRATURE EXTÉRIEURE DE BASE : table NF P52-612/CN du guide ACE (annexe 1),
# exigée par le bureau de contrôle. Zone A à I par département, puis palier d'altitude EXACT de la table
# (0-200 / 201-400 / … / 2001-2200 m). Au-delà du dernier palier donné pour une zone : la dernière valeur.
# RÉPLIQUÉE À L'IDENTIQUE dans le front (templates/index.html, même littéral JSON) : la note (document) == l'aperçu ;
# un témoin compare les deux. La zone CEE officielle (DEPT_ZONE, H1/H2/H3) ne sert toujours QU'À la prime.
ZONES_TEMP_NF = {"A": [-2, -4, -6, -8, -10, -12, -14, -16, -18, -20], "B": [-4, -5, -6, -7, -8, -9, -10], "C": [-5, -6, -7, -8, -9, -10, -11, -12, -13, -14, -15], "D": [-7, -8, -9, -11, -13, -14, -15], "E": [-8, -9, -11, -13, -15, -17, -19, -21, -23, -25, -27], "F": [-9, -10, -11, -12, -13], "G": [-10, -11, -13, -14, -17, -19, -21, -23, -24, -25, -29], "H": [-12, -13, -15, -17, -19, -21, -23, -24], "I": [-15, -15, -19, -21, -23, -24, -25]}
DEPT_ZONE_NF = {"2A": "A", "2B": "A", "20": "A", "06": "A", "22": "B", "29": "B", "56": "B", "35": "C", "44": "C", "85": "C", "16": "C", "17": "C", "24": "C", "33": "C", "40": "C", "47": "C", "32": "C", "64": "C", "65": "C", "31": "C", "09": "C", "82": "C", "81": "C", "11": "C", "34": "C", "30": "C", "13": "C", "83": "C", "66": "C", "14": "D", "27": "D", "76": "D", "61": "D", "60": "D", "95": "D", "78": "D", "91": "D", "77": "D", "75": "D", "92": "D", "93": "D", "94": "D", "28": "D", "45": "D", "41": "D", "72": "D", "53": "D", "49": "D", "37": "D", "18": "D", "79": "D", "86": "D", "36": "D", "02": "D", "50": "D", "46": "D", "12": "D", "07": "D", "26": "D", "84": "D", "03": "E", "23": "E", "87": "E", "63": "E", "19": "E", "15": "E", "43": "E", "48": "E", "04": "E", "59": "F", "62": "F", "80": "F", "08": "G", "51": "G", "10": "G", "89": "G", "58": "G", "21": "G", "71": "G", "39": "G", "01": "G", "69": "G", "42": "G", "74": "G", "73": "G", "38": "G", "05": "G", "55": "H", "52": "H", "70": "H", "25": "H", "57": "I", "54": "I", "67": "I", "68": "I", "88": "I", "90": "I"}
# Départements à DEUX zones dans la table : la plus froide est retenue (83, 44, 85, 17, 33, 40, 66, 11 -> C ;
# 50 -> D), sauf le 06 (décision d'Avi, 30/09/2026) : A sous 400 m (littoral), E à partir de 400 m
# (arrière-pays) — altitude inconnue : E. La note de dim le DIT : « département à deux zones, vérifier ».
DEPTS_DEUX_ZONES_NF = ["06", "11", "17", "33", "40", "44", "50", "66", "83", "85"]
SEUIL_06_M = 400
PALIERS_NF = ["0-200", "201-400", "401-600", "601-800", "801-1000", "1001-1200", "1201-1400", "1401-1600", "1601-1800", "1801-2000", "2001-2200"]


def _dept_du_cp(cp) -> str:
    cp = "".join(c for c in str(cp or "") if c.isdigit())[:5]
    return cp[:3] if cp.startswith("97") else cp[:2]


def temperature_base_nf(cp, altitude=None) -> dict:
    """Température de base NF P52-612/CN : `{temperature, zone, palier, altitude, deux_zones, hors_table}`.
    `altitude` : mètres, ou None / "" si inconnue (compte alors comme 0-200 m, sauf la règle du 06)."""
    dept = _dept_du_cp(cp)
    alt = None
    if altitude not in (None, ""):
        try:
            alt = float(str(altitude).replace(",", "."))
        except ValueError:
            alt = None
    zone = DEPT_ZONE_NF.get(dept)
    if dept == "06":
        zone = "A" if (alt is not None and alt < SEUIL_06_M) else "E"
    if zone is None:
        # Hors table (outre-mer, CP inconnu) : pas de valeur NF ; l'ancienne base de zone, et la note le dit.
        return {"temperature": 0 if dept.startswith("97") else -7, "zone": "hors table", "palier": "",
                "altitude": alt or 0, "deux_zones": False, "hors_table": True}
    valeurs = ZONES_TEMP_NF[zone]
    a = alt or 0
    brut = 0 if a <= 200 else int(-(-(a - 200) // 200))
    i = min(brut, len(valeurs) - 1)
    palier = f"{PALIERS_NF[i]} m" if brut == i else f"au-delà de {PALIERS_NF[i].split('-')[1]} m (dernière valeur de la table)"
    return {"temperature": valeurs[i], "zone": zone, "palier": palier, "altitude": a,
            "deux_zones": dept in DEPTS_DEUX_ZONES_NF, "hors_table": False}


MENTION_DEUX_ZONES = "département à deux zones, vérifier"


def _fmt_fr_num(x):
    """Affichage identique au modal : entier -> groupé espace (fr-FR) ; sinon virgule décimale."""
    try:
        f = float(x)
    except (TypeError, ValueError):
        return "0"
    if f == int(f):
        return f"{int(f):,}".replace(",", " ")
    return f"{f:g}".replace(".", ",")


def _temperature_base_notedim(prospect):
    # Lot 7a : table NF P52-612/CN (guide ACE, annexe 1) — la MÊME que l'aperçu du simulateur.
    cp = value(prospect, "cp_chantier", "code_postal_chantier", "cp", default="")
    t = temperature_base_nf(cp, value(prospect, "altitude", default=None))
    if t["hors_table"]:
        label = "hors table NF, à vérifier"
    else:
        label = f"palier {t['palier']}" + (f" — {MENTION_DEUX_ZONES}" if t["deux_zones"] else "")
    return {"temperature": t["temperature"], "zone": ("Zone " + t["zone"]) if not t["hors_table"] else "Hors table NF",
            "altitude": t["altitude"], "correction_label": label, "deux_zones": t["deux_zones"],
            "mention_deux_zones": MENTION_DEUX_ZONES if t["deux_zones"] else ""}


def get_prix_pac_for_devis(prospect, state_simulateur, catalogue):
    state_price = value(state_simulateur, "prix_pac", default=None)
    if state_price not in (None, ""):
        return float_value(state_price)

    modele_ref = value(state_simulateur, "modele_pac_id", "modele_pac", default="")
    modele = find_modele(catalogue, modele_ref)
    if modele:
        return float_value(value(modele, "ttc", "prix_ttc", default=0))
    return 0


def find_modele(catalogue, modele_ref):
    ref = str(modele_ref or "").strip()
    if not ref:
        return None
    for modele in catalogue or []:
        candidates = [
            str(modele.get("ref", "")).strip(),
            str(modele.get("id", "")).strip(),
            str(modele.get("nom", "")).strip(),
            str(modele.get("modele", "")).strip(),
        ]
        if ref in candidates:
            return modele
    return None


def parse_legacy_description(text):
    """Parse l'ancien format texte libre en liste de specs structurées."""
    specs = []
    for raw_line in str(text or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        for sep in (":", "="):
            if sep in line:
                champ, valeur = line.split(sep, 1)
                specs.append({"champ": champ.strip(), "valeur": valeur.strip()})
                break
        else:
            specs.append({"champ": "", "valeur": line})
    return specs


def select_default_modele(prospect, catalogue, service=None):
    """Modèle par défaut d'un lead jamais simulé. Suit le service comme le simulateur : DUO en
    chauffage + ECS, jamais de DUO en chauffage seul (défaut, aligné sur le simulateur)."""
    phase = str(value(prospect, "alimentation_electrique", "phase_electrique", default="")).lower()
    wants_tri = "tri" in phase
    service = service or value(prospect, "service", default="chauffage_seul")
    service_ecs = service in ("chauffage_ecs", "chauffage+ecs")
    compatibles = []
    for modele in catalogue or []:
        nom_ref = f"{modele.get('nom', '')} {modele.get('ref', '')}".upper()
        if service_ecs and "DUO" not in nom_ref:
            continue
        if not service_ecs and "DUO" in nom_ref:
            continue
        if wants_tri and "TRI" not in nom_ref:
            continue
        if not wants_tri and "TRI" in nom_ref:
            continue
        puissance = float_value(value(modele, "puiss_chauf", "puiss35", "puissance_kw", default=0))
        if puissance > 0:
            compatibles.append((puissance, modele))
    compatibles.sort(key=lambda item: item[0])
    if compatibles:
        return compatibles[0][1]
    return (catalogue or [{}])[0] if catalogue else {}


def generer_lot_titre(modele_pac):
    """Génère le titre du lot selon l'usage de la PAC."""
    if not modele_pac:
        return "Pompe à chaleur Air-Eau"
    usage = str(modele_pac.get("usage", "Chauffage"))
    if "ecs" in usage.lower():
        return "Pompe à chaleur Air-Eau — chauffage + ECS intégrée"
    return "Pompe à chaleur Air-Eau — chauffage"


def calculer_mpr(prospect, state_simulateur, admin_params):
    categorie = value(prospect, "categorie_revenu", "categorie", default="modeste")
    forfaits = (admin_params or {}).get("forfaits_mpr") or {}
    defaults = {"tres_modeste": 5000, "modeste": 4000, "intermediaire": 3000, "superieur": 0}
    return float_value(forfaits.get(categorie), defaults.get(categorie, 4000))


def resoudre_ballon(state_simulateur, admin_params):
    """Résout le ballon choisi (state.ballon_ref) depuis admin_params['ballon_thermo'].
    Retourne {ref, nom, fourniture_ht, prix_pose_ht, description_specs} ou None si Aucun.

    En chauffage + ECS la PAC produit l'eau chaude : pas de ballon, même si un ancien
    état sauvegardé porte encore un ballon_ref."""
    if service_avec_ecs(state_simulateur):
        return None
    ref = str(value(state_simulateur, "ballon_ref", default="") or "").strip()
    if not ref:
        return None
    bt = (admin_params or {}).get("ballon_thermo") or {}
    modeles = bt.get("modeles") if isinstance(bt.get("modeles"), list) else []
    modele = next((m for m in modeles if isinstance(m, dict) and str(m.get("ref", "")).strip() == ref), None)
    if not modele:
        return None
    specs = modele.get("description_specs")
    return {
        "ref": ref,
        "nom": str(modele.get("nom", "") or ""),
        "fourniture_ht": float_value(modele.get("fourniture_ht"), 0),
        "prix_pose_ht": float_value(bt.get("prix_pose_ht"), 0),
        "economie_ecs_mois": float_value(modele.get("economie_ecs_mois"), 0),
        "description_specs": specs if isinstance(specs, list) else [],
    }


def service_avec_ecs(state_simulateur):
    """Vrai seulement si le service est explicitement « chauffage + ECS »."""
    service = str(value(state_simulateur, "service", default="") or "").strip()
    return service in ("chauffage_ecs", "chauffage+ecs")


def calculer_mpr_ballon(prospect, admin_params):
    """MPR ballon : toujours 0.

    Depuis le 01/09/2026 (décret 2026-822), le chauffe-eau thermodynamique n'est plus
    financé par MaPrimeRénov' par geste. Le paramètre admin ballon_thermo.forfaits_mpr
    est conservé (masqué) mais n'est plus lu."""
    return 0


# Lot 6b : délégataire CEE selon le choix de démarrage (règle métier). Client qui ATTEND l'accord MaPrimeRénov'
# -> délégataire réglé « attente » (PICOTY, qui préfinance la prime) ; travaux TOUT DE SUITE ou foyer sans
# MaPrimeRénov' -> délégataire réglé « tout de suite » (ACE). Tarif du délégataire « tout de suite » vide -> repli sur
# celui de l'attente, avec une alerte. Réglage absent (ancien fichier) : PICOTY = attente, ACE = tout de suite.
# Précaire = Très modestes, classique pour tous les autres (inchangé). Même règle dans la page (choisirDelegataire).
USAGES_DELEGATAIRE = ("attente", "tout_de_suite")
_USAGE_PAR_NOM = {"PICOTY": "attente", "ACE": "tout_de_suite"}


def usage_delegataire(d):
    u = str((d or {}).get("usage") or "").strip()
    if u in USAGES_DELEGATAIRE:
        return u
    return _USAGE_PAR_NOM.get(str((d or {}).get("nom") or "").strip().upper(), "")


def tarif_delegataire(d, categorie):
    """Tarif €/MWh cumac du délégataire pour la catégorie (précaire = Très modestes), None si vide."""
    v = (d or {}).get("mwh_precaire" if categorie == "tres_modeste" else "mwh_classique")
    if v in (None, ""):
        return None
    f = float_value(v, 0)
    return f if f > 0 else None


def mode_cee(prospect, state_simulateur, admin_params):
    """« attente » si le client attend l'accord MaPrimeRénov' et a droit à une prime ; sinon « tout_de_suite »."""
    categorie = value(prospect, "categorie_revenu", "categorie", default="modeste")
    mpr = 0 if categorie == "superieur" else calculer_mpr(prospect, state_simulateur, admin_params)
    mode_mpr = str(value(state_simulateur, "mode_mpr", default="attente") or "attente")
    return "tout_de_suite" if (mode_mpr == "sans_attente" or mpr <= 0) else "attente"


def choisir_delegataire(delegataires, mode, categorie):
    """(délégataire, alerte) pour le mode « attente » / « tout_de_suite »."""
    liste = [d for d in (delegataires or []) if isinstance(d, dict)]
    ancien = next((d for d in liste if d.get("actif")), liste[0] if liste else None)
    d = next((x for x in liste if usage_delegataire(x) == mode), None)
    if mode == "tout_de_suite" and (d is None or tarif_delegataire(d, categorie) is None):
        repli = next((x for x in liste if usage_delegataire(x) == "attente"), None) or ancien
        nom = (d or {}).get("nom") or "tout de suite"
        return repli, f"Tarif CEE du délégataire {nom} non renseigné dans l'Admin : prime calculée avec {(repli or {}).get('nom', '—')}."
    return (d or ancien), None


def calculer_cee_bar_th_171(prospect, state_simulateur, admin_params, mode=None):
    """Calcule le montant CEE selon la formule officielle BAR-TH-171."""
    formule = (admin_params or {}).get("formule_bar_th_171", {})
    type_logement = value(prospect, "type_logement", "type", default="")
    if "maison" in str(type_logement).lower():
        type_logement = "Maison"
    elif "appart" in str(type_logement).lower():
        type_logement = "Appartement"

    categorie = value(prospect, "categorie_revenu", "categorie", default="modeste")
    etas = float_value(value(state_simulateur, "etas", default=140), 140)
    if etas <= 0:
        etas = 140
    surface = float_value(value(state_simulateur, "surface_chauffee", default=0))
    if surface <= 0:
        surface = float_value(value(prospect, "surface_habitable", "surface_logement_m2", default=90))
    zone = normalize_zone("", value(prospect, "cp_chantier", "code_postal_chantier", "cp"))

    if etas < 111:
        return {"montant": 0, "erreur": "Non éligible / ETAS insuffisant", "details": {"etas": etas}}

    montant_base = None
    for ligne in formule.get("tableau_montant_base", []):
        if not ligne.get("actif"):
            continue
        if ligne.get("logement") != type_logement:
            continue
        if float_value(ligne.get("etas_min")) <= etas <= float_value(ligne.get("etas_max")):
            montant_base = float_value(ligne.get("montant_kwhc"))
            break
    if montant_base is None:
        return {"montant": 0, "erreur": f"Barème montant base non trouvé pour {type_logement} ETAS {etas}", "details": {}}

    facteur_surface = None
    for ligne in formule.get("tableau_facteur_surface", []):
        if not ligne.get("actif"):
            continue
        if ligne.get("logement") != type_logement:
            continue
        if float_value(ligne.get("surface_min")) <= surface <= float_value(ligne.get("surface_max")):
            facteur_surface = float_value(ligne.get("facteur"))
            break
    if facteur_surface is None:
        return {"montant": 0, "erreur": f"Facteur surface non trouvé pour {type_logement} {surface}m²", "details": {}}

    facteur_zone = None
    for ligne in formule.get("tableau_facteur_zone", []):
        if not ligne.get("actif"):
            continue
        if ligne.get("zone") == zone:
            facteur_zone = float_value(ligne.get("facteur"))
            break
    if facteur_zone is None:
        return {"montant": 0, "erreur": f"Facteur zone non trouvé pour {zone}", "details": {}}

    kwhc = montant_base * facteur_surface * facteur_zone
    mwhc = kwhc / 1000

    mode = mode or mode_cee(prospect, state_simulateur, admin_params)
    delegataire, alerte_delegataire = choisir_delegataire((admin_params or {}).get("delegataires") or [], mode, categorie)
    if not delegataire:
        return {"montant": 0, "erreur": "Aucun délégataire CEE actif", "details": {}}

    if categorie == "tres_modeste":
        prix_unitaire = float_value(delegataire.get("mwh_precaire"), 0)
        type_prix = "précaire"
    else:
        prix_unitaire = float_value(delegataire.get("mwh_classique"), 0)
        type_prix = "classique"

    bonif = (admin_params or {}).get("bonification_cee") or {}
    multiplicateur = float_value(bonif.get("multiplicateur"), 1) if bonif.get("actif", True) else 1
    montant = round(mwhc * prix_unitaire * multiplicateur, 2)

    return {
        "montant": montant,
        "erreur": None,
        "details": {
            "type_logement": type_logement,
            "categorie": categorie,
            "etas": etas,
            "surface": surface,
            "zone": zone,
            "montant_base_kwhc": montant_base,
            "facteur_surface": facteur_surface,
            "facteur_zone": facteur_zone,
            "kwhc": kwhc,
            "mwhc": round(mwhc, 2),
            "prix_unitaire": prix_unitaire,
            "type_prix": type_prix,
            "delegataire": delegataire.get("nom", ""),
            "mode": mode,
            "alerte_delegataire": alerte_delegataire,
            "bonification": multiplicateur,
        },
    }


def calculer_cee(prospect, state_simulateur, admin_params, with_bonification=True):
    """Calcule le montant CEE avec la formule BAR-TH-171."""
    result = calculer_cee_bar_th_171(prospect, state_simulateur, admin_params)
    if result.get("erreur"):
        print(f"[CEE] Erreur calcul : {result['erreur']}")
        return 0
    return result["montant"]


def appliquer_plafonds_reglementaires(prix_pac_ttc, montant_mpr_brut, montant_cee_brut, prospect, admin_params):
    """Applique les plafonds réglementaires sur MPR + CEE."""
    plafonds = (admin_params or {}).get("plafonds_reglementaires", {})
    plafond_eligible = float_value(plafonds.get("plafond_eligible_ttc"), 12000)
    plafonds_pct = plafonds.get("plafonds_aides_pct", {})
    categorie = value(prospect, "categorie_revenu", "categorie", default="modeste")
    base_eligible = min(float_value(prix_pac_ttc), plafond_eligible)

    if categorie == "superieur":
        return {
            "mpr_final": 0,
            "cee_final": montant_cee_brut,
            "cee_conserve": 0,
            "reste_a_charge": round(max(prix_pac_ttc - montant_cee_brut, 0), 2),
            "details": {
                "categorie": categorie,
                "base_eligible": base_eligible,
                "mpr_brut": montant_mpr_brut,
                "cee_brut": montant_cee_brut,
                "ecretement": False,
                "raison_no_ecretement": "SUP : pas de plafond cumulé",
            },
        }

    plafond_pct = float_value(plafonds_pct.get(categorie), 0) / 100
    plafond_aides = base_eligible * plafond_pct
    total_brut = montant_mpr_brut + montant_cee_brut

    if total_brut <= plafond_aides:
        return {
            "mpr_final": montant_mpr_brut,
            "cee_final": montant_cee_brut,
            "cee_conserve": 0,
            "reste_a_charge": round(max(prix_pac_ttc - total_brut, 0), 2),
            "details": {
                "categorie": categorie,
                "base_eligible": base_eligible,
                "plafond_pct": plafond_pct * 100,
                "plafond_aides": plafond_aides,
                "mpr_brut": montant_mpr_brut,
                "cee_brut": montant_cee_brut,
                "total_brut": total_brut,
                "ecretement": False,
            },
        }

    mpr_final = montant_mpr_brut
    cee_final = max(plafond_aides - mpr_final, 0)
    cee_conserve = montant_cee_brut - cee_final
    return {
        "mpr_final": round(mpr_final, 2),
        "cee_final": round(cee_final, 2),
        "cee_conserve": round(cee_conserve, 2),
        "reste_a_charge": round(max(prix_pac_ttc - mpr_final - cee_final, 0), 2),
        "details": {
            "categorie": categorie,
            "base_eligible": base_eligible,
            "plafond_pct": plafond_pct * 100,
            "plafond_aides": plafond_aides,
            "mpr_brut": montant_mpr_brut,
            "cee_brut": montant_cee_brut,
            "total_brut": total_brut,
            "ecretement": True,
        },
    }


def calculer_devis(prospect, state_simulateur, admin_params, catalogue_pac):
    prix_pac_ttc = get_prix_pac_for_devis(prospect, state_simulateur, catalogue_pac)
    tva_rate = float_value(((admin_params or {}).get("params") or {}).get("tva"), 0.055)
    if tva_rate <= 0:
        tva_rate = 0.055

    total_ttc = round(prix_pac_ttc, 2)
    total_ht = round(total_ttc / (1 + tva_rate), 2)

    pv = (admin_params or {}).get("prix_vente_devis") or {}
    prix_pose_ht = float_value(pv.get("prix_pose_ht"), 3500)
    prix_travaux_induits_ht = float_value(pv.get("prix_travaux_induits_ht"), 1200)

    prix_pose_ttc = round(prix_pose_ht * (1 + tva_rate), 2)
    prix_travaux_induits_ttc = round(prix_travaux_induits_ht * (1 + tva_rate), 2)
    prix_fourniture_ht = round(max(total_ht - prix_pose_ht - prix_travaux_induits_ht, 0), 2)
    prix_fourniture_ttc = round(prix_fourniture_ht * (1 + tva_rate), 2)
    total_tva = round(total_ttc - total_ht, 2)

    montant_mpr_brut = calculer_mpr(prospect, state_simulateur, admin_params)
    montant_cee_brut = calculer_cee(prospect, state_simulateur, admin_params, with_bonification=True)
    result_plafonds = appliquer_plafonds_reglementaires(
        prix_pac_ttc=total_ttc,
        montant_mpr_brut=montant_mpr_brut,
        montant_cee_brut=montant_cee_brut,
        prospect=prospect,
        admin_params=admin_params,
    )
    montant_mpr = result_plafonds["mpr_final"]
    montant_cee = result_plafonds["cee_final"]
    reste_a_charge = result_plafonds["reste_a_charge"]

    # --- Couche BALLON thermo (optionnelle, APRÈS plafonds -> CEE/écrêtement intacts) ---
    ballon = resoudre_ballon(state_simulateur, admin_params)
    ballon_actif = ballon is not None
    if ballon_actif:
        b_four_ht = round(ballon["fourniture_ht"], 2)
        b_pose_ht = round(ballon["prix_pose_ht"], 2)
        b_four_ttc = round(b_four_ht * (1 + tva_rate), 2)
        b_pose_ttc = round(b_pose_ht * (1 + tva_rate), 2)
        b_total_ht = round(b_four_ht + b_pose_ht, 2)
        b_total_ttc = round(b_four_ttc + b_pose_ttc, 2)
        montant_mpr_ballon = calculer_mpr_ballon(prospect, admin_params)
        reste_a_charge = round(max(reste_a_charge + b_total_ttc - montant_mpr_ballon, 0), 2)
        recap_total_ht = round(total_ht + b_total_ht, 2)
        recap_total_ttc = round(total_ttc + b_total_ttc, 2)
        recap_total_tva = round(recap_total_ttc - recap_total_ht, 2)
        ballon_nom = ballon["nom"]
        ballon_description_specs = ballon["description_specs"]
    else:
        b_four_ht = b_four_ttc = b_pose_ht = b_pose_ttc = b_total_ht = b_total_ttc = 0
        montant_mpr_ballon = 0
        recap_total_ht, recap_total_ttc, recap_total_tva = total_ht, total_ttc, total_tva
        ballon_nom = ""
        ballon_description_specs = []

    recap_fourniture_ht = round(prix_fourniture_ht + b_four_ht, 2)
    recap_pose_ht = round(prix_pose_ht + b_pose_ht, 2)
    categorie_revenu = value(prospect, "categorie_revenu", "categorie", default="")
    return {
        "prix_pac_ttc": total_ttc,
        "prix_fourniture_ht": prix_fourniture_ht,
        "prix_fourniture_ttc": prix_fourniture_ttc,
        "prix_pose_ht": prix_pose_ht,
        "prix_pose_ttc": prix_pose_ttc,
        "prix_travaux_induits_ht": prix_travaux_induits_ht,
        "prix_travaux_induits_ttc": prix_travaux_induits_ttc,
        "tva_taux": f"{tva_rate * 100:.1f} %".replace(".", ","),
        "total_ht": total_ht,
        "total_tva": total_tva,
        "total_ttc": total_ttc,
        "montant_mpr": montant_mpr,
        "montant_cee": montant_cee,
        "montant_cee_lettres": nombre_en_lettres_euros(montant_cee),
        "reste_a_charge": reste_a_charge,
        "_cee_conserve": result_plafonds["cee_conserve"],
        "_details_plafonds": result_plafonds["details"],
        "categorie_CEE_label": "Précaire" if categorie_revenu == "tres_modeste" else "Classique",
        "categorie_revenu_label": LABELS_ANAH.get(categorie_revenu, ""),
        "qt_fourniture": "1 u.",
        "qt_pose": "1 u.",
        "qt_travaux_induits": "1 forfait",
        "lot_titre": generer_lot_titre(find_modele(catalogue_pac, value(state_simulateur, "modele_pac_id", "modele_pac"))),
        "ballon_actif": ballon_actif,
        "ballon_titre": "Chauffe-eau thermodynamique — ECS",
        "ballon_nom": ballon_nom,
        "ballon_description_specs": ballon_description_specs,
        "prix_ballon_fourniture_ht": b_four_ht,
        "prix_ballon_fourniture_ttc": b_four_ttc,
        "prix_ballon_pose_ht": b_pose_ht,
        "prix_ballon_pose_ttc": b_pose_ttc,
        "ballon_total_ht": b_total_ht,
        "ballon_total_ttc": b_total_ttc,
        "montant_mpr_ballon": montant_mpr_ballon,
        "montant_mpr_ballon_label": LABELS_ANAH.get(categorie_revenu, ""),
        "qt_ballon_fourniture": "1 u.",
        "qt_ballon_pose": "1 u.",
        "recap_fourniture_ht": recap_fourniture_ht,
        "recap_pose_ht": recap_pose_ht,
        "recap_total_ht": recap_total_ht,
        "recap_total_ttc": recap_total_ttc,
        "recap_total_tva": recap_total_tva,
    }


def _pmt(taux_annuel, n_mois, capital):
    """Mensualité de crédit — réplique fidèle du pmt() JS du simulateur."""
    capital = float_value(capital)
    n_mois = float_value(n_mois)
    if capital <= 0 or n_mois <= 0:
        return 0.0
    i = float_value(taux_annuel) / 12
    if i == 0:
        return capital / n_mois
    return capital * i / (1 - (1 + i) ** (-n_mois))


def calculer_financement_devis(reste_a_charge, admin_params, option="opt1"):
    """Financement choisi dans le simulateur — réplique JS (mensO1 / mensO2) :
    opt1 Crédit Travaux (taux/durée selon le seuil), opt2 Éco-PTZ (barème eco_ptz)."""
    fin = (admin_params or {}).get("params_financement") or {}
    libelles = fin.get("libelles") or {}
    rac = float_value(reste_a_charge)
    if option == "opt2":
        bareme = fin.get("eco_ptz") or {}
        taux_pct = float_value(bareme.get("taux_pct"), 0)
        duree_mois = int(float_value(bareme.get("duree_mois"), 180))
        libelle = libelles.get("option2") or "Éco-PTZ"
    else:
        option = "opt1"
        seuil = float_value(fin.get("seuil_rac_eur"), 6000)
        credit = fin.get("credit_travaux") or {}
        sous = rac < seuil
        bareme = (credit.get("sous_seuil") if sous else credit.get("sur_seuil")) or {}
        taux_pct = float_value(bareme.get("taux_pct"), 5.90 if sous else 4.90)
        duree_mois = int(float_value(bareme.get("duree_mois"), 156 if sous else 180))
        libelle = libelles.get("option1") or "Crédit Travaux"
    mensualite = _pmt(taux_pct / 100, duree_mois, rac)
    return {
        "option": option,
        "libelle": libelle,
        "mensualite": round(mensualite, 2),
        "taux_pct": taux_pct,
        "duree_mois": duree_mois,
        "reste_a_charge": round(rac, 2),
        # comme le simulateur : l'échéance différée n'est annoncée que pour le Crédit Travaux
        "premiere_echeance_jours": int(float_value(fin.get("premiere_echeance_jours"), 180)) if option == "opt1" else None,
    }


def calculer_economie_devis(surface, zone, etas35, etas55, emetteur, service, facture_avant, admin_params):
    """OBSOLÈTE — remplacé par calculerEconomies / services/economies.py (Lot 2).

    Facture après PAC (€/mois) + économie — réplique fidèle de calculerFactureApresPac() JS."""
    params = (admin_params or {}).get("params_eco_energie") or {}
    surface = float_value(surface)
    if surface <= 0:
        return {"facture_apres_mois": None, "facture_avant_mois": facture_avant, "economie_mois": None}
    z = str(zone or "").lower()
    zone_red = "h1" if z.startswith("h1") else ("h3" if z.startswith("h3") else "h2")
    conso = float_value((params.get("conso_zone_kwh_m2_an") or {}).get(zone_red), 130) or 130
    etas_retenu = float_value(etas35) if (emetteur == "plancher_chauffant" and service == "chauffage_seul") else float_value(etas55)
    scop = (etas_retenu / 100) * 2.5 if etas_retenu > 0 else 0
    if scop <= 0:
        scop = float_value(params.get("scop_defaut"), 3.5) or 3.5
    prix_elec = float_value((params.get("prix_kwh") or {}).get("electricite"), 0.21)
    cout_annuel = (surface * conso / scop) * prix_elec
    facture_apres = round(cout_annuel / 12)
    if facture_apres <= 0:
        facture_apres = None
    economie = None
    if facture_apres is not None and facture_avant not in (None, "") and float_value(facture_avant) > 0:
        economie = round(float_value(facture_avant) - facture_apres)
    return {
        "facture_apres_mois": facture_apres,
        "facture_avant_mois": facture_avant,
        "economie_mois": economie,
    }


def format_devis_amounts(calculs):
    out = dict(calculs)
    for key in (
        "prix_fourniture_ht", "prix_fourniture_ttc", "prix_pose_ht", "prix_pose_ttc",
        "prix_travaux_induits_ht", "prix_travaux_induits_ttc", "total_ht", "total_tva",
        "total_ttc", "montant_mpr", "montant_cee", "reste_a_charge",
        "prix_ballon_fourniture_ht", "prix_ballon_fourniture_ttc",
        "prix_ballon_pose_ht", "prix_ballon_pose_ttc",
        "ballon_total_ht", "ballon_total_ttc", "montant_mpr_ballon",
        "recap_fourniture_ht", "recap_pose_ht",
        "recap_total_ht", "recap_total_ttc", "recap_total_tva",
    ):
        out[key] = money(calculs.get(key))
    return out


def generer_numero_devis(prospect, ordre=1):
    annee = datetime.now().strftime("%Y")
    cp = str(value(prospect, "cp_chantier", "code_postal_chantier", "cp", default="00"))
    cp_2 = cp[:2] if cp else "00"
    adresse = str(value(prospect, "adresse", "adresse_chantier", default=""))
    match = re.match(r"^(\d+)", adresse)
    rue_2 = match.group(1)[:2] if match else "00"
    rue_2 = rue_2.zfill(2)
    init_nom = str(value(prospect, "nom", default="X"))[:1].upper()
    prenom = str(value(prospect, "prenom", default="X"))
    init_prenom = prenom[:1].upper() or "X"
    init_prenom_2 = ""
    if "-" in prenom:
        parts = prenom.split("-")
        if len(parts) > 1 and parts[1]:
            init_prenom_2 = parts[1][:1].upper()
    return f"DE{annee}-{cp_2}{rue_2}-{ordre}{init_nom}{init_prenom}{init_prenom_2}"


def generer_numero_dossier(counters):
    annee_court = datetime.now().strftime("%y")
    counters["dossier"] = int(counters.get("dossier") or 0) + 1
    return f"HX{annee_court}-{counters['dossier']:04d}", counters


def generer_numero_facture(counters, annee):
    """Numero de facture GAPLESS par annee : FA-AAAA-NNNN. Mute counters (a persister par l'appelant)."""
    key = f"facture_{annee}"
    counters[key] = int(counters.get(key) or 0) + 1
    return f"FA-{annee}-{counters[key]:04d}", counters


def generer_numero_notedim(prospect):
    annee = datetime.now().strftime("%Y")
    numero = str(value(prospect, "numero", default="PR-000000")).replace("PR-", "")
    init = str(value(prospect, "nom", default="XX"))[:2].upper().ljust(2, "X")
    return f"ND{annee}-{numero}-{init}"


def _format_date_fr(date_str):
    """Convertit une date ISO (yyyy-mm-dd) en format FR (dd/mm/yyyy)."""
    if not date_str:
        return ""
    try:
        raw = str(date_str)
        if len(raw) >= 10 and raw[4] == "-":
            return datetime.fromisoformat(raw[:10]).strftime("%d/%m/%Y")
        return raw
    except (TypeError, ValueError):
        return str(date_str)


def format_sous_traitant(sous_traitant):
    if not sous_traitant:
        return ""
    rge_du_fr = _format_date_fr(sous_traitant.get("rge_validite_du", ""))
    rge_au_fr = _format_date_fr(sous_traitant.get("rge_validite_au", ""))
    lines = [
        sous_traitant.get("entreprise", ""),
        f"SIRET : {sous_traitant.get('siret', '')}" if sous_traitant.get("siret") else "",
        sous_traitant.get("adresse", ""),
        f"RGE : {sous_traitant.get('rge', '')} (du {rge_du_fr} au {rge_au_fr})",
        f"Assurance : {sous_traitant.get('assurance', '')}" if sous_traitant.get("assurance") else "",
    ]
    return "\n".join(line for line in lines if line)


# Réponse à « Où sera installé le ballon ? » -> type de ballon exigé (miroir de
# BALLON_EMPLACEMENTS dans templates/index.html).
BALLON_TYPE_PAR_EMPLACEMENT = {
    "piece_non_chauffee": "compact",
    "petite_piece_gaines": "compact_gainable",
    "pas_de_place": "split",
}


def ballon_inadapte(state_simulateur, admin_params):
    """Vrai si le ballon retenu n'est pas du type exigé par l'emplacement indiqué.
    Faux quand une des infos manque (pas de ballon, emplacement ou type non renseigné) :
    l'emplacement manquant est signalé à part."""
    if service_avec_ecs(state_simulateur):
        return False
    ref = str(value(state_simulateur, "ballon_ref", default="") or "").strip()
    attendu = BALLON_TYPE_PAR_EMPLACEMENT.get(str(value(state_simulateur, "ballon_emplacement", default="") or ""))
    if not ref or not attendu:
        return False
    bt = (admin_params or {}).get("ballon_thermo") or {}
    modeles = bt.get("modeles") if isinstance(bt.get("modeles"), list) else []
    modele = next((m for m in modeles if isinstance(m, dict) and str(m.get("ref", "")).strip() == ref), None)
    type_modele = str((modele or {}).get("type_installation") or "").strip()
    return bool(type_modele) and type_modele != attendu


def validate_prospect_for_devis(prospect, state_simulateur, admin_params=None):
    missing = []
    checks = [
        ("civilite", "Civilité"),
        ("nom", "Nom"),
        ("prenom", "Prénom"),
        ("telephone", "Téléphone"),
        ("email", "Email"),
    ]
    for key, label in checks:
        if not value(prospect, key):
            missing.append(label)

    if not value(prospect, "adresse", "adresse_chantier"):
        missing.append("Adresse chantier")
    if not value(prospect, "cp_chantier", "code_postal_chantier", "cp"):
        missing.append("Code postal chantier")
    if not value(prospect, "ville", "ville_chantier"):
        missing.append("Ville chantier")

    if value(prospect, "usage_bien") == "bailleur":
        if not value(prospect, "adresse_personne"):
            missing.append("Adresse du propriétaire")
        if not value(prospect, "cp_personne", "code_postal_personne"):
            missing.append("CP du propriétaire")
        if not value(prospect, "ville_personne"):
            missing.append("Ville du propriétaire")

    if not value(prospect, "type_logement"):
        missing.append("Type de logement")
    if not value(prospect, "surface_habitable", "surface_logement_m2"):
        missing.append("Surface habitable")
    if not value(prospect, "hsp"):
        missing.append("HSP")
    if not value(prospect, "chauffage_actuel", "mode_chauffage"):
        missing.append("Chauffage actuel")
    if not value(prospect, "type_emetteurs"):
        missing.append("Type d'émetteurs")
    if not value(prospect, "alimentation_electrique", "phase_electrique"):
        missing.append("Type d'alimentation électrique")
    if not value(prospect, "categorie_revenu", "categorie"):
        missing.append("Catégorie de revenu")
    if not value(state_simulateur, "modele_pac_id", "modele_pac"):
        missing.append("Modèle PAC (simulateur)")
    if (value(state_simulateur, "ballon_ref") and not service_avec_ecs(state_simulateur)
            and not value(state_simulateur, "ballon_emplacement")):
        missing.append("Emplacement du ballon (simulateur)")
    if ballon_inadapte(state_simulateur, admin_params):
        missing.append("Ballon non adapté à l'emplacement indiqué (simulateur)")
    return missing


def calculer_notedim(prospect, state_simulateur, catalogue_pac):
    surface_habitable = float_value(value(prospect, "surface_habitable", "surface_logement_m2", default=100), 100)
    surface_chauffee = float_value(value(state_simulateur, "surface_chauffee", default=0), 0)
    if surface_chauffee <= 0:
        surface_chauffee = surface_habitable * 0.9
    hsp = float_value(value(prospect, "hsp", default=2.5), 2.5)
    if hsp <= 0:
        hsp = 2.5
    volume = surface_chauffee * hsp
    # Température de base : logique fine par sous-zone, identique à l'aperçu simulateur.
    _temp = _temperature_base_notedim(prospect)
    zone = _temp["zone"]
    temperature_base = _temp["temperature"]
    altitude = _temp["altitude"]
    correction_label = _temp["correction_label"]
    delta_t = 20 - temperature_base

    iso_toit = value(state_simulateur, "iso_toit", default="isole")
    iso_mur = value(state_simulateur, "iso_mur", default="isole")
    iso_menuiserie = value(state_simulateur, "iso_menuiserie", default="double")
    coeffs = {
        "toit": {"tres_bien": 0.00, "bien": 0.10, "isole": 0.20, "peu": 0.35, "non": 0.50},
        "mur": {"tres_bien": 0.00, "bien": 0.15, "isole": 0.30, "peu": 0.55, "non": 0.80},
        "menuiserie": {"double": 0.05, "sur_vitrage": 0.20, "simple": 0.40},
    }
    labels = {
        "tres_bien": "Très bien isolé", "bien": "Bien isolé", "isole": "Isolé",
        "peu": "Peu isolé", "non": "Non isolé", "double": "Double vitrage",
        "sur_vitrage": "Survitrage", "simple": "Simple vitrage",
    }
    g_toit = coeffs["toit"].get(iso_toit, 0.20)
    g_mur = coeffs["mur"].get(iso_mur, 0.30)
    g_menuiserie = coeffs["menuiserie"].get(iso_menuiserie, 0.05)
    g_retenu = min(max(0.75 + g_toit + g_mur + g_menuiserie, 0.75), 2.50)
    # Puissances : répliquées à l'identique du front (aucun arrondi intermédiaire ;
    # facteur de sécurité appliqué au chauffage puis ajout de l'ECS).
    p_chauffage = g_retenu * volume * delta_t
    service = value(state_simulateur, "service", default="chauffage_seul")
    service_ecs = service in ("chauffage_ecs", "chauffage+ecs")
    p_ecs = min(max(p_chauffage * 0.06, 500), 1000) if service_ecs else 0
    p_totale = p_chauffage + p_ecs
    p_chauffage_secu = p_chauffage * 1.10
    p_pac_w = p_chauffage_secu + p_ecs
    p_pac_reco_w = int(p_pac_w + 0.5)
    p_pac_reco_kw = int(p_pac_w / 1000 * 10 + 0.5) / 10
    modele = find_modele(catalogue_pac, value(state_simulateur, "modele_pac_id", "modele_pac")) or select_default_modele(prospect, catalogue_pac)
    modele_kw = float_value(value(modele, "puiss_chauf", "puiss35", "puissance_kw", default=p_pac_reco_kw), p_pac_reco_kw)
    return {
        "surface_habitable": number_fr(surface_habitable, 0),
        "surface_chauffee": number_fr(surface_chauffee, 0),
        "hsp": _fmt_fr_num(hsp),
        "zone_climatique": zone,
        "temperature_base": _fmt_fr_num(temperature_base),
        "iso_toit_label": labels.get(iso_toit, iso_toit),
        "iso_toit_coeff": number_fr(g_toit, 2),
        "iso_mur_label": labels.get(iso_mur, iso_mur),
        "iso_mur_coeff": number_fr(g_mur, 2),
        "iso_menuiserie_label": labels.get(iso_menuiserie, iso_menuiserie),
        "iso_menuiserie_coeff": number_fr(g_menuiserie, 2),
        "methode_calcul": "NF EN 12831 simplifiée — G × V × ΔT",
        "g_base": number_fr(0.75, 2),
        "g_retenu": number_fr(g_retenu, 2),
        "volume_chauffe": _fmt_fr_num(int(volume + 0.5)),
        "altitude": number_fr(altitude, 0),
        "correction_altitude_label": correction_label,
        "mention_deux_zones": _temp["mention_deux_zones"],
        "temperature_consigne": "20",
        "delta_t": _fmt_fr_num(delta_t),
        "service": "Chauffage + ECS" if service_ecs else "Chauffage seul",
        "p_ecs": _fmt_fr_num(int(p_ecs + 0.5)),
        "type_emetteurs_label": TYPE_EMETTEURS_LABELS.get(value(prospect, "type_emetteurs"), value(prospect, "type_emetteurs", default="—")),
        "p_chauffage": _fmt_fr_num(int(p_chauffage + 0.5)),
        "p_totale": _fmt_fr_num(int(p_totale + 0.5)),
        "p_chauffage_secu": _fmt_fr_num(int(p_chauffage_secu + 0.5)),
        "p_pac_reco_w": _fmt_fr_num(p_pac_reco_w),
        "p_pac_reco_kw": number_fr(p_pac_reco_kw, 1),
        "gamme_min": number_fr(max(p_pac_reco_kw * 0.8, 0), 1),
        "gamme_max": number_fr(p_pac_reco_kw * 1.2, 1),
        "modele_pac": value(modele, "nom", "ref", default="—"),
        "modele_pac_specs": f"{number_fr(modele_kw, 1)} kW · {value(modele, 'alim', default='')} · COP {value(modele, 'cop', 'scop35', default='—')}",
    }

def nombre_en_lettres_euros(amount):
    euros = int(round(float_value(amount)))
    if euros == 0:
        return "zéro"
    units = [
        "zéro", "un", "deux", "trois", "quatre", "cinq", "six", "sept", "huit", "neuf",
        "dix", "onze", "douze", "treize", "quatorze", "quinze", "seize",
    ]
    tens = {20: "vingt", 30: "trente", 40: "quarante", 50: "cinquante", 60: "soixante"}

    def under_hundred(n):
        if n < 17:
            return units[n]
        if n < 20:
            return "dix-" + units[n - 10]
        if n < 70:
            d, u = divmod(n, 10)
            base = tens[d * 10]
            return base + (" et un" if u == 1 else ("-" + units[u] if u else ""))
        if n < 80:
            return "soixante-" + under_hundred(n - 60)
        if n == 80:
            return "quatre-vingts"
        return "quatre-vingt-" + under_hundred(n - 80)

    def under_thousand(n):
        c, r = divmod(n, 100)
        if c == 0:
            return under_hundred(r)
        prefix = "cent" if c == 1 else units[c] + " cent"
        if r == 0:
            return prefix + ("s" if c > 1 else "")
        return prefix + " " + under_hundred(r)

    parts = []
    thousands, rest = divmod(euros, 1000)
    if thousands:
        parts.append("mille" if thousands == 1 else under_thousand(min(thousands, 999)) + " mille")
    if rest:
        parts.append(under_thousand(rest))
    if euros >= 1_000_000:
        return str(euros)
    return " ".join(parts)
