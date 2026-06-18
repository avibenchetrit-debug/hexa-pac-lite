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


def get_prix_pac_for_devis(prospect, state_simulateur, catalogue):
    forced = value(prospect, "prix_pac_force", default=None)
    if forced not in (None, ""):
        return float_value(forced)

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


def select_default_modele(prospect, catalogue):
    phase = str(value(prospect, "phase_electrique", default="")).lower()
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


def calculer_mpr(prospect, state_simulateur, admin_params):
    categorie = value(prospect, "categorie_revenu", "categorie", default="modeste")
    forfaits = (admin_params or {}).get("forfaits_mpr") or {}
    defaults = {"tres_modeste": 5000, "modeste": 4000, "intermediaire": 3000, "superieur": 0}
    return float_value(forfaits.get(categorie), defaults.get(categorie, 4000))


def calculer_cee(prospect, state_simulateur, admin_params, with_bonification=True):
    categorie = value(prospect, "categorie_revenu", "categorie", default="modeste")
    surface = float_value(value(state_simulateur, "surface_chauffee", default=0))
    if surface <= 0:
        surface = float_value(value(prospect, "surface_habitable", "surface_logement_m2", default=90)) * 0.9
    delegataires = (admin_params or {}).get("delegataires") or []
    delegataire = next((d for d in delegataires if d.get("actif")), delegataires[0] if delegataires else {})
    unit_key = "mwh_precaire" if categorie == "tres_modeste" else "mwh_classique"
    unit = float_value(delegataire.get(unit_key), 7.2)
    cee = round(max(surface / 10, 1) * unit * 10, 2)
    bonif = (admin_params or {}).get("bonification_cee") or {}
    if with_bonification and bonif.get("actif", True):
        cee *= float_value(bonif.get("multiplicateur"), 5)
    return round(cee, 2)


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

    montant_mpr = calculer_mpr(prospect, state_simulateur, admin_params)
    montant_cee = calculer_cee(prospect, state_simulateur, admin_params, with_bonification=True)
    reste_a_charge = round(max(total_ttc - montant_mpr - montant_cee, 0), 2)

    categorie_revenu = value(prospect, "categorie_revenu", "categorie", default="")
    return {
        "prix_pac_ttc": total_ttc,
        "prix_fourniture_ht": prix_fourniture_ht,
        "prix_fourniture_ttc": prix_fourniture_ttc,
        "prix_pose_ht": prix_pose_ht,
        "prix_pose_ttc": prix_pose_ttc,
        "prix_travaux_induits_ht": prix_travaux_induits_ht,
        "prix_travaux_induits_ttc": prix_travaux_induits_ttc,
        "description_pose": pv.get("description_pose_defaut", ""),
        "tva_taux": f"{tva_rate * 100:.1f} %".replace(".", ","),
        "total_ht": total_ht,
        "total_tva": total_tva,
        "total_ttc": total_ttc,
        "montant_mpr": montant_mpr,
        "montant_cee": montant_cee,
        "montant_cee_lettres": nombre_en_lettres_euros(montant_cee),
        "reste_a_charge": reste_a_charge,
        "categorie_CEE_label": "Précaire" if categorie_revenu == "tres_modeste" else "Classique",
        "categorie_revenu_label": LABELS_ANAH.get(categorie_revenu, ""),
        "qt_fourniture": "1 u.",
        "qt_pose": "1 u.",
        "qt_travaux_induits": "1 forfait",
        "lot_titre": "Pompe à chaleur Air-Eau — chauffage + ECS intégrée",
    }


def format_devis_amounts(calculs):
    out = dict(calculs)
    for key in (
        "prix_fourniture_ht", "prix_fourniture_ttc", "prix_pose_ht", "prix_pose_ttc",
        "prix_travaux_induits_ht", "prix_travaux_induits_ttc", "total_ht", "total_tva",
        "total_ttc", "montant_mpr", "montant_cee", "reste_a_charge",
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


def generer_numero_notedim(prospect):
    annee = datetime.now().strftime("%Y")
    numero = str(value(prospect, "numero", default="PR-000000")).replace("PR-", "")
    init = str(value(prospect, "nom", default="XX"))[:2].upper().ljust(2, "X")
    return f"ND{annee}-{numero}-{init}"


def format_sous_traitant(sous_traitant):
    if not sous_traitant:
        return ""
    lines = [
        sous_traitant.get("entreprise", ""),
        f"SIRET : {sous_traitant.get('siret', '')}" if sous_traitant.get("siret") else "",
        sous_traitant.get("adresse", ""),
        f"RGE : {sous_traitant.get('rge', '')} (du {sous_traitant.get('rge_validite_du', '')} au {sous_traitant.get('rge_validite_au', '')})",
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
    if not value(prospect, "categorie_revenu", "categorie"):
        missing.append("Catégorie de revenu")
    if not value(state_simulateur, "modele_pac_id", "modele_pac"):
        missing.append("Modèle PAC (simulateur)")
    return missing


def calculer_notedim(prospect, state_simulateur, catalogue_pac):
    surface_habitable = float_value(value(prospect, "surface_habitable", "surface_logement_m2", default=100), 100)
    surface_chauffee = float_value(value(state_simulateur, "surface_chauffee", default=0), 0)
    if surface_chauffee <= 0:
        surface_chauffee = round(surface_habitable * 0.9, 1)
    hsp = float_value(value(prospect, "hsp", default=2.5), 2.5)
    volume = round(surface_chauffee * hsp, 1)
    zone = calculer_zone_climatique(
        value(prospect, "cp_chantier", "code_postal_chantier", "cp"),
        value(prospect, "zone_climatique", "zone_climatique_chantier"),
    )
    temperature_base = TEMP_BASE_ZONE.get(zone, -7)
    altitude = float_value(value(prospect, "altitude", default=0), 0)
    correction_label = "sans correction"
    if altitude > 200:
        correction = ((altitude - 200) / 100) * 0.5
        temperature_base = round(temperature_base - correction, 1)
        correction_label = f"correction altitude -{number_fr(correction)} °C"
    delta_t = round(20 - temperature_base, 1)

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
    p_chauffage = round(g_retenu * volume * delta_t)
    service = value(state_simulateur, "service", default="chauffage_ecs")
    service_ecs = service in ("chauffage_ecs", "chauffage+ecs")
    p_ecs = round(min(max(p_chauffage * 0.06, 500), 1000)) if service_ecs else 0
    p_totale = p_chauffage + p_ecs
    p_pac_reco_w = round(p_totale * 1.10)
    p_pac_reco_kw = round(p_pac_reco_w / 1000, 1)
    modele = find_modele(catalogue_pac, value(state_simulateur, "modele_pac_id", "modele_pac")) or select_default_modele(prospect, catalogue_pac)
    modele_kw = float_value(value(modele, "puiss_chauf", "puiss35", "puissance_kw", default=p_pac_reco_kw), p_pac_reco_kw)
    return {
        "surface_habitable": number_fr(surface_habitable, 0),
        "surface_chauffee": number_fr(surface_chauffee, 1),
        "hsp": number_fr(hsp, 2),
        "zone_climatique": zone,
        "temperature_base": number_fr(temperature_base, 1),
        "iso_toit_label": labels.get(iso_toit, iso_toit),
        "iso_toit_coeff": number_fr(g_toit, 2),
        "iso_mur_label": labels.get(iso_mur, iso_mur),
        "iso_mur_coeff": number_fr(g_mur, 2),
        "iso_menuiserie_label": labels.get(iso_menuiserie, iso_menuiserie),
        "iso_menuiserie_coeff": number_fr(g_menuiserie, 2),
        "methode_calcul": "NF EN 12831 simplifiée — G × V × ΔT",
        "g_base": number_fr(0.75, 2),
        "g_retenu": number_fr(g_retenu, 2),
        "volume_chauffe": number_fr(volume, 1),
        "altitude": number_fr(altitude, 0),
        "correction_altitude_label": correction_label,
        "temperature_consigne": "20",
        "delta_t": number_fr(delta_t, 1),
        "service": "Chauffage + ECS" if service_ecs else "Chauffage seul",
        "p_ecs": str(p_ecs),
        "type_emetteurs_label": TYPE_EMETTEURS_LABELS.get(value(prospect, "type_emetteurs"), value(prospect, "type_emetteurs", default="—")),
        "p_chauffage": str(p_chauffage),
        "p_totale": str(p_totale),
        "p_pac_reco_w": str(p_pac_reco_w),
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
