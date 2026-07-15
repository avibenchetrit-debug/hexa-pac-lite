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
}

TEMP_BASE_ZONE = {"H1": -7, "H2": -4, "H3": 0}
DEPT_ZONE = {
    "01": "H1", "02": "H1", "03": "H1", "05": "H1", "08": "H1", "10": "H1", "14": "H1",
    "15": "H1", "19": "H1", "21": "H1", "23": "H1", "25": "H1", "27": "H1", "28": "H1",
    "36": "H1", "38": "H1", "39": "H1", "42": "H1", "43": "H1", "45": "H1", "51": "H1",
    "52": "H1", "54": "H1", "55": "H1", "57": "H1", "58": "H1", "59": "H1", "60": "H1",
    "61": "H1", "62": "H1", "63": "H1", "67": "H1", "68": "H1", "69": "H1", "70": "H1",
    "71": "H1", "73": "H1", "74": "H1", "75": "H1", "76": "H1", "77": "H1", "78": "H1",
    "80": "H1", "88": "H1", "89": "H1", "90": "H1", "91": "H1", "92": "H1", "93": "H1",
    "94": "H1", "95": "H1",
    "04": "H2", "07": "H2", "09": "H2", "11": "H2", "12": "H2", "16": "H2", "17": "H2",
    "18": "H2", "22": "H2", "24": "H2", "26": "H2", "29": "H2", "31": "H2", "32": "H2",
    "33": "H2", "35": "H2", "37": "H2", "40": "H2", "41": "H2", "44": "H2", "46": "H2",
    "47": "H2", "48": "H2", "49": "H2", "50": "H2", "53": "H2", "56": "H2", "64": "H2",
    "65": "H2", "72": "H2", "79": "H2", "81": "H2", "82": "H2", "85": "H2", "86": "H2",
    "87": "H2",
    "06": "H3", "13": "H3", "2A": "H3", "2B": "H3", "30": "H3", "34": "H3", "66": "H3",
    "83": "H3", "84": "H3",
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
    dept = cp[:3] if cp.startswith("97") or cp.startswith("976") else cp[:2].upper()
    return DEPT_ZONE.get(dept, "H1")


def calculer_zone_climatique(cp, zone=""):
    return normalize_zone(zone, cp)


# Température extérieure de base par SOUS-ZONE — répliquée à l'identique du front
# (temperatureExterieureBase) pour que la note (document) == l'aperçu (modal).
TEMP_BASE_SOUS_ZONE = {"H1A": -9, "H1B": -8, "H1C": -7, "H2A": -4, "H2B": -5, "H2C": -3, "H2D": -2, "H3": 0}
TEMP_BASE_CP = {}  # override par code postal — vide (identique au front)
DEPT_SOUS_ZONE = {
    "01": "H1A", "03": "H1A", "05": "H1A", "07": "H1A", "10": "H1A", "21": "H1A", "25": "H1A", "39": "H1A", "42": "H1A", "43": "H1A", "45": "H1A", "51": "H1A", "52": "H1A", "54": "H1A", "55": "H1A", "57": "H1A", "58": "H1A", "67": "H1A", "68": "H1A", "69": "H1A", "70": "H1A", "71": "H1A", "73": "H1A", "74": "H1A", "88": "H1A", "89": "H1A", "90": "H1A",
    "02": "H1B", "08": "H1B", "14": "H1B", "18": "H1B", "27": "H1B", "28": "H1B", "36": "H1B", "41": "H1B", "50": "H1B", "53": "H1B", "59": "H1B", "60": "H1B", "61": "H1B", "62": "H1B", "75": "H1B", "76": "H1B", "77": "H1B", "78": "H1B", "80": "H1B", "91": "H1B", "92": "H1B", "93": "H1B", "94": "H1B", "95": "H1B",
    "22": "H1C", "29": "H1C", "35": "H1C", "44": "H1C", "49": "H1C", "56": "H1C", "72": "H1C", "85": "H1C",
    "17": "H2A", "24": "H2A", "33": "H2A", "37": "H2A", "79": "H2A", "86": "H2A",
    "16": "H2B", "19": "H2B", "23": "H2B", "26": "H2B", "38": "H2B", "46": "H2B", "47": "H2B", "48": "H2B", "63": "H2B", "81": "H2B", "82": "H2B", "87": "H2B",
    "09": "H2C", "11": "H2C", "12": "H2C", "15": "H2C", "31": "H2C", "32": "H2C", "40": "H2C", "64": "H2C", "65": "H2C",
    "04": "H2D", "06": "H2D", "13": "H2D", "30": "H2D", "34": "H2D", "66": "H2D", "83": "H2D", "84": "H2D",
    "2A": "H3", "2B": "H3", "971": "H3", "972": "H3", "973": "H3", "974": "H3", "976": "H3",
}


def _fmt_fr_num(x):
    """Affichage identique au modal : entier -> groupé espace (fr-FR) ; sinon virgule décimale."""
    try:
        f = float(x)
    except (TypeError, ValueError):
        return "0"
    if f == int(f):
        return f"{int(f):,}".replace(",", " ")
    return f"{f:g}".replace(".", ",")


def _normaliser_sous_zone(z):
    raw = str(z or "").strip().upper().replace(" ", "")
    if not raw:
        return ""
    for sz in ("H1A", "H1B", "H1C", "H2A", "H2B", "H2C", "H2D"):
        if raw.startswith(sz):
            return sz
    if raw.startswith("H1"):
        return "H1"
    if raw.startswith("H2"):
        return "H2"
    if raw.startswith("H3"):
        return "H3"
    return ""


def _temperature_base_notedim(prospect):
    cp = "".join(c for c in str(value(prospect, "cp_chantier", "code_postal_chantier", "cp", default="") or "") if c.isdigit())[:5]
    info = None
    if cp and cp in TEMP_BASE_CP:
        info = {"temperature": TEMP_BASE_CP[cp], "zone": _normaliser_sous_zone(value(prospect, "zone_climatique_chantier", "zone_climatique", default="")) or "H1"}
    else:
        dept = cp[:3] if cp.startswith("97") else cp[:2]
        if dept and dept in DEPT_SOUS_ZONE:
            z = DEPT_SOUS_ZONE[dept]
            info = {"temperature": TEMP_BASE_SOUS_ZONE[z], "zone": z}
    if info is None:
        z_detail = _normaliser_sous_zone(value(prospect, "zone_climatique_chantier", "zone_climatique", default=""))
        if z_detail and z_detail in TEMP_BASE_SOUS_ZONE:
            info = {"temperature": TEMP_BASE_SOUS_ZONE[z_detail], "zone": z_detail}
    if info is None:
        z = normalize_zone("", cp)
        if z in TEMP_BASE_ZONE:
            info = {"temperature": TEMP_BASE_ZONE[z], "zone": z}
    if info is None:
        info = {"temperature": -7, "zone": "H1"}
    altitude = float_value(value(prospect, "altitude", default=0), 0)
    correction = ((altitude - 200) / 100) * 0.5 if altitude > 200 else 0
    correction_label = f"correction altitude -{number_fr(correction)} °C" if correction > 0 else "sans correction"
    return {"temperature": info["temperature"] - correction, "zone": info["zone"], "altitude": altitude, "correction_label": correction_label}


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


def select_default_modele(prospect, catalogue):
    phase = str(value(prospect, "alimentation_electrique", "phase_electrique", default="")).lower()
    wants_tri = "tri" in phase
    service_ecs = True
    compatibles = []
    for modele in catalogue or []:
        nom_ref = f"{modele.get('nom', '')} {modele.get('ref', '')}".upper()
        if service_ecs and "DUO" not in nom_ref:
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
    Retourne {ref, nom, fourniture_ht, prix_pose_ht, description_specs} ou None si Aucun."""
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


def calculer_mpr_ballon(prospect, admin_params):
    """Forfait MPR ballon par catégorie (indépendant de la MPR PAC)."""
    categorie = value(prospect, "categorie_revenu", "categorie", default="modeste")
    bt = (admin_params or {}).get("ballon_thermo") or {}
    forfaits = bt.get("forfaits_mpr") or {}
    defaults = {"tres_modeste": 1200, "modeste": 800, "intermediaire": 400, "superieur": 0}
    return float_value(forfaits.get(categorie), defaults.get(categorie, 0))


def calculer_cee_bar_th_171(prospect, state_simulateur, admin_params):
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

    delegataires = (admin_params or {}).get("delegataires") or []
    delegataire = next((d for d in delegataires if d.get("actif")), None)
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


def calculer_financement_devis(reste_a_charge, admin_params):
    """Financement Option 1 (Crédit Travaux) — réplique JS, taux/durée conditionnels au seuil."""
    fin = (admin_params or {}).get("params_financement") or {}
    rac = float_value(reste_a_charge)
    seuil = float_value(fin.get("seuil_rac_eur"), 6000)
    credit = fin.get("credit_travaux") or {}
    sous = rac < seuil
    bareme = (credit.get("sous_seuil") if sous else credit.get("sur_seuil")) or {}
    taux_pct = float_value(bareme.get("taux_pct"), 5.90 if sous else 4.90)
    duree_mois = int(float_value(bareme.get("duree_mois"), 156 if sous else 180))
    mensualite = _pmt(taux_pct / 100, duree_mois, rac)
    return {
        "mensualite": round(mensualite, 2),
        "taux_pct": taux_pct,
        "duree_mois": duree_mois,
        "reste_a_charge": round(rac, 2),
        "premiere_echeance_jours": int(float_value(fin.get("premiere_echeance_jours"), 180)),
    }


def calculer_economie_devis(surface, zone, etas35, etas55, emetteur, service, facture_avant, admin_params):
    """Facture après PAC (€/mois) + économie — réplique fidèle de calculerFactureApresPac() JS."""
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


def validate_prospect_for_devis(prospect, state_simulateur):
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
    service = value(state_simulateur, "service", default="chauffage_ecs")
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
        "surface_chauffee": number_fr(surface_chauffee, 1),
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
