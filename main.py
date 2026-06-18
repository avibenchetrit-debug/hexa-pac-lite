import io
import base64
import hashlib
import html
import hmac
import json
import os
import re
import shutil
# import smtplib  # legacy SMTP disabled: devis are sent with Resend.
import time
import urllib.parse
import urllib.request
import unicodedata
from datetime import datetime, timedelta

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from services.service_devis import (
    calculer_devis,
    calculer_notedim,
    calculer_zone_climatique,
    find_modele,
    format_devis_amounts,
    format_sous_traitant,
    generer_numero_devis,
    generer_numero_dossier,
    generer_numero_notedim,
    money,
    select_default_modele,
    validate_prospect_for_devis,
    value as devis_value,
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")
STATIC_DIR = os.path.join(BASE_DIR, "static")
REPO_DATA_DIR = os.path.join(BASE_DIR, "data")
DATA_DIR = os.environ.get("DATA_DIR", "data")
LEADS_PATH = os.path.join(DATA_DIR, "leads.json")
NOTES_PATH = os.path.join(DATA_DIR, "notes.json")
CATALOGUE_PATH = os.path.join(DATA_DIR, "catalogue_pac.json")
CATALOGUE_PAC_PATH = CATALOGUE_PATH
BAREMES_PATH = os.path.join(DATA_DIR, "baremes.json")
ECHANGES_PATH = os.path.join(DATA_DIR, "echanges.json")
DELEGATAIRES_PATH = os.path.join(DATA_DIR, "delegataires.json")
MODELES_EMAIL_PATH = os.path.join(DATA_DIR, "modeles_email.json")
PARAMETRES_ADMIN_PATH = os.path.join(DATA_DIR, "parametres_admin.json")
COUNTERS_PATH = os.path.join(DATA_DIR, "counters.json")
DEVIS_ENVOYES_PATH = os.path.join(DATA_DIR, "devis_envoyes.json")
DEVIS_DIR = os.path.join(DATA_DIR, "devis")
DEVIS_META_PATH = os.path.join(DEVIS_DIR, "devis_meta.json")
REPO_CATALOGUE_PATH = os.path.join(REPO_DATA_DIR, "catalogue_pac.json")
REPO_BAREMES_PATH = os.path.join(REPO_DATA_DIR, "baremes.json")

DEFAULT_DELEGATAIRES = [
    {"nom": "PICOTY", "mwh_precaire": 12.50, "mwh_classique": 7.20, "actif": True}
]
DEFAULT_MODELES_EMAIL = [
    {
        "id": "modele_1",
        "label": "Premier contact",
        "titre": "Premier contact",
        "sujet": "Votre projet de pompe à chaleur Hexa Rénov'",
        "contenu": "Bonjour {prenom},\n\nMerci pour votre intérêt. Nous revenons vers vous au sujet de votre projet {numero}.\n\nCordialement,\nL'équipe Hexa-Rénov'",
    },
    {
        "id": "modele_2",
        "label": "Relance après pré-visite",
        "titre": "Relance après pré-visite",
        "sujet": "Suite à notre pré-visite Hexa Rénov'",
        "contenu": "Bonjour {prenom},\n\nSuite à la pré-visite, nous restons disponibles pour finaliser votre projet.\n\nCordialement,\nL'équipe Hexa-Rénov'",
    },
    {
        "id": "modele_3",
        "label": "Relance après devis",
        "titre": "Relance après devis",
        "sujet": "Votre devis Hexa Rénov'",
        "contenu": "Bonjour {prenom},\n\nJe me permets de revenir vers vous concernant le devis {numero} pour {modele_pac}. Le reste à charge estimé est de {reste_a_charge}.\n\nCordialement,\nL'équipe Hexa-Rénov'",
    },
]

DEFAULT_SOUS_TRAITANTS = [
    {
        "id": "italisol",
        "entreprise": "ITAL-ISOL",
        "siret": "907 952 048 00037",
        "adresse": "32 Rue Clément Ader, 91280 Saint-Pierre-du-Perray",
        "rge": "QPAC / 75024",
        "rge_validite_du": "2025-08-08",
        "rge_validite_au": "2026-08-08",
        "assurance": "QBE 037.0012525-S178593",
        "actif": True,
    }
]

DEFAULT_PARAMETRES_ADMIN = {
    "params": {
        "pose": 3500,
        "acc": 550,
        "tva": 0.055,
        "lead": 30,
        "conv": 0.05,
        "vt1": 200,
        "cofrac1": 226,
        "urba1": 100,
        "vt2": 200,
        "cofrac2": 226,
        "urba2": 100,
        "cession_mode": "eur",
        "cession_eur": 2500,
        "cession_pct": 0.20,
        "plafond_pct": 0.60,
    },
    "prix_vente_devis": {
        "prix_pose_ht": 3500,
        "prix_travaux_induits_ht": 1200,
        "description_pose_defaut": "Pose et mise en service de la pompe à chaleur, raccordements hydrauliques et électriques, dépose et évacuation de l'ancien système, contrôle d'étanchéité, paramétrage de la régulation.",
    },
    "sous_traitants": DEFAULT_SOUS_TRAITANTS,
}


def _load_default_catalogue():
    """Load the committed PAC catalogue as the initialization fallback."""
    try:
        with open(REPO_CATALOGUE_PATH, encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, list) else []
    except (FileNotFoundError, ValueError):
        return []


DEFAULT_CATALOGUE_PAC = _load_default_catalogue()

app = FastAPI(title="hexa-pac-lite")
templates = Jinja2Templates(directory=TEMPLATES_DIR)

# Serve static assets (CSS/JS/images) under /static.
os.makedirs(STATIC_DIR, exist_ok=True)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


def _admin_password() -> str:
    pwd = os.environ.get("ADMIN_PASSWORD")
    if not pwd:
        print("WARNING: ADMIN_PASSWORD non défini, fallback hexarenov2026 utilisé")
        return "hexarenov2026"
    return pwd


def _admin_secret() -> bytes:
    return (os.environ.get("ADMIN_TOKEN_SECRET") or _admin_password()).encode("utf-8")


def _sign_admin_token(payload: str) -> str:
    sig = hmac.new(_admin_secret(), payload.encode("utf-8"), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(sig).decode("ascii").rstrip("=")


# ---------------------------------------------------------------------------
# JSON storage helpers (atomic writes: tmp file + os.replace)
# ---------------------------------------------------------------------------
def _read_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, ValueError):
        return default


def _atomic_write_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def _deep_merge_defaults(data, defaults):
    if isinstance(defaults, dict):
        base = dict(defaults)
        if isinstance(data, dict):
            for key, value in data.items():
                if isinstance(value, dict) and isinstance(base.get(key), dict):
                    base[key] = _deep_merge_defaults(value, base[key])
                else:
                    base[key] = value
        return base
    if data is None:
        return defaults
    return data


def load_parametres_admin():
    data = _read_json(PARAMETRES_ADMIN_PATH, DEFAULT_PARAMETRES_ADMIN)
    if not isinstance(data, dict):
        data = {}
    merged = _deep_merge_defaults(data, DEFAULT_PARAMETRES_ADMIN)
    sous_traitants = merged.get("sous_traitants")
    if not isinstance(sous_traitants, list) or not sous_traitants:
        merged["sous_traitants"] = [dict(DEFAULT_SOUS_TRAITANTS[0])]
    if not any(st.get("actif") for st in merged["sous_traitants"]):
        merged["sous_traitants"][0]["actif"] = True
    return merged


def save_parametres_admin_atomic(payload):
    data = _deep_merge_defaults(payload if isinstance(payload, dict) else {}, DEFAULT_PARAMETRES_ADMIN)
    sous_traitants = data.get("sous_traitants")
    if not isinstance(sous_traitants, list) or not sous_traitants:
        data["sous_traitants"] = [dict(DEFAULT_SOUS_TRAITANTS[0])]
    if not any(st.get("actif") for st in data["sous_traitants"]):
        data["sous_traitants"][0]["actif"] = True
    _atomic_write_json(PARAMETRES_ADMIN_PATH, data)


def _read_catalogue_pac():
    catalogue = _read_json(CATALOGUE_PAC_PATH, DEFAULT_CATALOGUE_PAC)
    if not isinstance(catalogue, list):
        catalogue = DEFAULT_CATALOGUE_PAC
    changed = False
    migrated = []
    for item in catalogue:
        if not isinstance(item, dict):
            migrated.append(item)
            continue
        next_item = dict(item)
        if "description_technique" not in next_item:
            next_item["description_technique"] = ""
            changed = True
        migrated.append(next_item)
    if changed:
        _atomic_write_json(CATALOGUE_PAC_PATH, migrated)
    return migrated


def _migrate_catalogue_pac_schema():
    _read_catalogue_pac()


def _admin_payload_with_m3():
    admin = load_parametres_admin()
    baremes = _read_json(BAREMES_PATH, {})
    if not isinstance(baremes, dict):
        baremes = {}
    admin["forfaits_mpr"] = baremes.get(
        "forfaits_mpr",
        {"tres_modeste": 5000, "modeste": 4000, "intermediaire": 3000, "superieur": 0},
    )
    admin["bonification_cee"] = baremes.get("bonification_cee", {"actif": True, "multiplicateur": 5})
    admin["delegataires"] = _read_delegataires()
    return admin


def _seed_json_file(path, default, repo_source=None):
    if os.path.exists(path):
        return
    if repo_source and os.path.exists(repo_source):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        shutil.copyfile(repo_source, path)
        return
    _atomic_write_json(path, default)


def _init_storage():
    os.makedirs(DATA_DIR, exist_ok=True)
    _seed_json_file(LEADS_PATH, [])
    _seed_json_file(NOTES_PATH, {})
    _seed_json_file(ECHANGES_PATH, {})
    _seed_json_file(DELEGATAIRES_PATH, DEFAULT_DELEGATAIRES)
    _seed_json_file(MODELES_EMAIL_PATH, DEFAULT_MODELES_EMAIL)
    _seed_json_file(PARAMETRES_ADMIN_PATH, DEFAULT_PARAMETRES_ADMIN)
    _seed_json_file(COUNTERS_PATH, {"dossier": 0})
    _seed_json_file(DEVIS_ENVOYES_PATH, [])
    _seed_json_file(CATALOGUE_PATH, DEFAULT_CATALOGUE_PAC, REPO_CATALOGUE_PATH)
    _seed_json_file(BAREMES_PATH, {}, REPO_BAREMES_PATH)
    os.makedirs(DEVIS_DIR, exist_ok=True)
    _seed_json_file(DEVIS_META_PATH, {})
    save_parametres_admin_atomic(load_parametres_admin())
    _migrate_catalogue_pac_schema()


def _read_leads():
    leads = _read_json(LEADS_PATH, [])
    return leads if isinstance(leads, list) else []


def _read_notes():
    notes = _read_json(NOTES_PATH, {})
    return notes if isinstance(notes, dict) else {}


def _read_echanges():
    echanges = _read_json(ECHANGES_PATH, {})
    return echanges if isinstance(echanges, dict) else {}


def _read_delegataires():
    delegataires = _read_json(DELEGATAIRES_PATH, DEFAULT_DELEGATAIRES)
    return delegataires if isinstance(delegataires, list) else DEFAULT_DELEGATAIRES


def _read_modeles_email():
    modeles = _read_json(MODELES_EMAIL_PATH, DEFAULT_MODELES_EMAIL)
    return modeles if isinstance(modeles, list) else DEFAULT_MODELES_EMAIL


def _read_devis_meta():
    meta = _read_json(DEVIS_META_PATH, {})
    return meta if isinstance(meta, dict) else {}


def _read_devis_envoyes():
    sent = _read_json(DEVIS_ENVOYES_PATH, [])
    return sent if isinstance(sent, list) else []


async def _read_request_payload(request: Request) -> dict:
    """Read JSON or form payload and return a flat dict."""
    ctype = request.headers.get("content-type", "")
    if "application/json" in ctype:
        data = await request.json()
        return data if isinstance(data, dict) else {}

    form = await request.form()
    payload = {}
    for key, value in form.items():
        if hasattr(value, "filename"):  # UploadFile-like
            continue
        payload[key] = value
    return payload


def _normalize_lead_payload(payload: dict) -> dict:
    normalized = {}
    for key, value in (payload or {}).items():
        if key is None:
            continue
        k = str(key).strip()
        if not k:
            continue
        if value is None:
            normalized[k] = ""
        elif isinstance(value, (str, int, float, bool)):
            normalized[k] = str(value)
        else:
            normalized[k] = str(value)

    if "statut" in normalized:
        normalized["statut"] = _normalize_statut(normalized.get("statut"))
    if "categorie" in normalized:
        normalized["categorie"] = _normalize_categorie(normalized.get("categorie"))
    for key in ("zone_climatique", "zone_climatique_chantier"):
        if key in normalized:
            normalized[key] = _normalize_zone_climatique(normalized.get(key))
    if "transfert_charge" in normalized:
        normalized["transfert_charge"] = str(normalized.get("transfert_charge", "")).strip().lower() in {"1", "true", "on", "oui", "yes"}
    if normalized.get("date_visite_technique_date") and not normalized.get("date_visite_technique"):
        normalized["date_visite_technique"] = normalized["date_visite_technique_date"]
    _apply_field_aliases(normalized)
    return normalized


def _upsert_lead(payload: dict, forced_numero: str | None = None) -> tuple[dict, bool]:
    leads = _read_leads()
    now = _now_iso()
    numero = (forced_numero or payload.get("numero") or "").strip()
    index = None
    existing = {}

    if numero:
        for i, lead in enumerate(leads):
            if str(lead.get("numero", "")).strip() == numero:
                index = i
                existing = dict(lead)
                break
    else:
        numero = _next_numero(leads)

    if not existing:
        existing = {"numero": numero, "date": now}

    merged = dict(existing)
    merged.update(payload)
    merged["numero"] = numero
    merged["date"] = existing.get("date") or now
    merged["updated_at"] = now

    if index is None:
        leads.append(merged)
        created = True
    else:
        leads[index] = merged
        created = False

    _atomic_write_json(LEADS_PATH, leads)
    return merged, created


def _now_iso():
    return datetime.now().isoformat(timespec="seconds")


def _next_numero(leads):
    """Return the next PR-000XXX numero based on the current max in leads."""
    max_n = 0
    for lead in leads:
        num = str(lead.get("numero", ""))
        m = re.search(r"(\d+)", num)
        if m:
            max_n = max(max_n, int(m.group(1)))
    return f"PR-{max_n + 1:06d}"


# ---------------------------------------------------------------------------
# Excel/CSV import : header -> field mapping (accent & case insensitive)
# ---------------------------------------------------------------------------
def _norm(text):
    text = unicodedata.normalize("NFKD", str(text))
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.strip().lower()
    return re.sub(r"[\s_\-]+", " ", text)


_FIELD_ALIASES = {
    "nom": "nom",
    "prenom": "prenom",
    "telephone": "telephone",
    "tel": "telephone",
    "phone": "telephone",
    "mobile": "telephone",
    "email": "email",
    "e mail": "email",
    "mail": "email",
    "courriel": "email",
    "cp": "cp",
    "code postal": "cp",
    "ville": "ville",
    "statut": "statut",
    "status": "statut",
    "categorie": "categorie",
    "category": "categorie",
    "source": "source",
    "provenance": "source",
    "projet initial": "projet_initial",
    "projet": "projet_initial",
    "notes": "notes",
    "note": "notes",
    "commentaire": "notes",
    "commentaires": "notes",
}

STATUT_ALIASES = {
    "nouveau": "nouveau",
    "a rappeler": "rappeler",
    "à rappeler": "rappeler",
    "a recontacter": "rappeler",
    "rappeler": "rappeler",
    "rdv": "rdv",
    "rdv pris": "rdv",
    "devis": "devis",
    "devis envoye": "devis_envoye",
    "devis envoyé": "devis_envoye",
    "devis_envoye": "devis_envoye",
    "signe": "signe",
    "signé": "signe",
    "perdu": "perdu",
}

CATEGORIE_ALIASES = {
    "tmo": "tres_modeste",
    "tm": "tres_modeste",
    "tres modeste": "tres_modeste",
    "très modeste": "tres_modeste",
    "tres_modeste": "tres_modeste",
    "mo": "modeste",
    "modeste": "modeste",
    "int": "intermediaire",
    "intermediaire": "intermediaire",
    "intermédiaire": "intermediaire",
    "sup": "superieur",
    "superieur": "superieur",
    "supérieur": "superieur",
}

ZONE_CLIMATIQUE_ALIASES = {
    "h1a": "H1",
    "h1b": "H1",
    "h1": "H1",
    "h2": "H2",
    "h3": "H3",
}

FIELD_ALIASES = {
    "adresse": "adresse_chantier",
    "cp_chantier": "code_postal_chantier",
    "ville": "ville_chantier",
    "code_postal_chantier": "cp",
    "cp_personne": "code_postal_personne",
}

PROSPECT_FIELDS = [
    # Champs existants (à conserver)
    "numero",
    "nom",
    "prenom",
    "telephone",
    "email",
    "cp",
    "ville",
    "statut",
    "categorie",
    "source",
    "projet_initial",
    "date",

    # Métadonnées
    "updated_at",
    "cree_par",
    "derniere_modification",
    "deleted_at",

    # Bloc 1 (Origine & Statut)
    "usage_bien",
    "situation_actuelle",
    "situation_propriete",
    "date_acquisition",

    # Bloc 2 (Informations personnelles)
    "civilite",

    # Bloc 3 (Adresse & Données réglementaires)
    "adresse_chantier",
    "code_postal_chantier",
    "ville_chantier",
    "adresse_personne",
    "cp_personne",
    "ville_personne",
    "zone_climatique",
    "parcelle_cadastrale",
    "registre_copro",

    # Bloc 4 (Caractéristiques du bien) - DPE
    "classe_dpe",
    "dpe_numero",
    "dpe_date",

    # Bloc 4 (Caractéristiques du bien) - Logement
    "type_logement",
    "surface_logement_m2",
    "hsp",
    "annee_construction",
    "mode_chauffage",
    "ecs",
    "cout_chauffage",
    "phase_electrique",
    "puissance_compteur",
    "altitude",
    "panneaux_solaires",
    "date_visite_technique",
    "date_visite_technique_date",
    "type_emetteurs",
    "transfert_charge",
    "prix_pac_force",
    "modele_pac_id",
    "modele_pac",
    "surface_chauffee",
    "iso_toit",
    "iso_mur",
    "iso_menuiserie",
    "service",

    # Bloc 5 (Informations fiscales)
    "rfr",
    "nombre_personnes",
    "code_postal_personne",

    # Logs
    "nrp_log",
]

DEFAULT_PROSPECT_VALUES = {
    "date_visite_technique": "À déterminer",
    "transfert_charge": False,
    "prix_pac_force": None,
    "nrp_log": [],
}

IMPORT_PROSPECT_FIELDS = [
    "nom", "prenom", "telephone", "email", "cp",
    "ville", "statut", "categorie", "source", "projet_initial",
]


def _normalize_statut(value: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    return STATUT_ALIASES.get(_norm(raw), raw)


def _normalize_categorie(value: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    return CATEGORIE_ALIASES.get(_norm(raw), raw)


def _normalize_zone_climatique(value: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    return ZONE_CLIMATIQUE_ALIASES.get(_norm(raw), raw)


def _apply_field_aliases(lead: dict) -> bool:
    changed = False
    for frontend_key, backend_key in FIELD_ALIASES.items():
        if lead.get(frontend_key) and not lead.get(backend_key):
            lead[backend_key] = lead[frontend_key]
            changed = True
        if lead.get(backend_key) and not lead.get(frontend_key):
            lead[frontend_key] = lead[backend_key]
            changed = True
    return changed


def _lead_for_response(lead: dict) -> dict:
    normalized = dict(lead or {})
    normalized["statut"] = _normalize_statut(normalized.get("statut", ""))
    normalized["categorie"] = _normalize_categorie(normalized.get("categorie", ""))
    if "zone_climatique" in normalized:
        normalized["zone_climatique"] = _normalize_zone_climatique(normalized.get("zone_climatique", ""))
    if "zone_climatique_chantier" in normalized:
        normalized["zone_climatique_chantier"] = _normalize_zone_climatique(normalized.get("zone_climatique_chantier", ""))
    _apply_field_aliases(normalized)
    for field in PROSPECT_FIELDS:
        normalized.setdefault(field, DEFAULT_PROSPECT_VALUES.get(field, ""))
    return normalized


def _migrate_leads_schema():
    leads = _read_leads()
    changed = False
    normalized_count = 0
    migrated = []
    for lead in leads:
        if not isinstance(lead, dict):
            migrated.append(lead)
            continue
        item = dict(lead)
        before = dict(item)
        statut = _normalize_statut(item.get("statut", ""))
        categorie = _normalize_categorie(item.get("categorie", ""))
        if item.get("statut") != statut:
            item["statut"] = statut
            changed = True
        if item.get("categorie") != categorie:
            item["categorie"] = categorie
            changed = True
        for key in ("zone_climatique", "zone_climatique_chantier"):
            if key in item:
                zone = _normalize_zone_climatique(item.get(key, ""))
                if item.get(key) != zone:
                    item[key] = zone
                    changed = True
        if _apply_field_aliases(item):
            changed = True
        for field in PROSPECT_FIELDS:
            if field not in item:
                item[field] = DEFAULT_PROSPECT_VALUES.get(field, "")
                changed = True
        if item != before:
            normalized_count += 1
        migrated.append(item)
    if changed:
        _atomic_write_json(LEADS_PATH, migrated)
    print(f"Migration leads.json : {normalized_count} entrées normalisées")


@app.on_event("startup")
async def startup_event():
    _init_storage()
    _migrate_leads_schema()
    _admin_password()


def _extract_texte(payload_form, payload_json):
    for key in ("texte_commentaire", "texte", "commentaire", "texte_html"):
        if payload_form and payload_form.get(key):
            return str(payload_form.get(key))
        if payload_json and payload_json.get(key):
            return str(payload_json.get(key))
    return ""


def _extract_auteur(payload_form, payload_json):
    for key in ("auteur", "created_by"):
        if payload_form and payload_form.get(key):
            return str(payload_form.get(key)).strip() or "Anonyme"
        if payload_json and payload_json.get(key):
            return str(payload_json.get(key)).strip() or "Anonyme"
    return "Anonyme"


def _note_for_front(entry, commentaire_id=None):
    """Return a note dict carrying both the stored keys and the keys the
    existing front-end (chargerNotes) reads (texte_html / horodatage)."""
    texte = entry.get("texte", "")
    date = entry.get("date", "")
    auteur = entry.get("auteur", "")
    return {
        "texte": texte,
        "texte_html": texte,
        "date": date,
        "horodatage": date,
        "auteur": auteur,
        "commentaire_id": commentaire_id,
    }


def _is_deleted(lead):
    return bool(str((lead or {}).get("deleted_at", "")).strip())


def _find_lead_index(leads, numero):
    wanted = str(numero or "").strip()
    for i, lead in enumerate(leads):
        if str((lead or {}).get("numero", "")).strip() == wanted:
            return i
    return None


def _lead_display_name(lead):
    nom = str((lead or {}).get("nom", "")).strip()
    prenom = str((lead or {}).get("prenom", "")).strip()
    return " ".join(part for part in (prenom, nom) if part)


def _exchange_for_front(entry):
    contenu = str((entry or {}).get("contenu", ""))
    created_at = (entry or {}).get("created_at", "")
    auteur = (entry or {}).get("auteur") or (entry or {}).get("created_by") or "Anonyme"
    return {
        "type": (entry or {}).get("type", "sms"),
        "contenu": contenu,
        "contenu_html": (entry or {}).get("contenu_html") or html.escape(contenu).replace("\n", "<br>"),
        "objet": (entry or {}).get("objet"),
        "template_id": (entry or {}).get("template_id"),
        "created_at": created_at,
        "created_by": auteur,
        "auteur": auteur,
        "nrp": bool((entry or {}).get("nrp")),
    }


def _find_lead(numero: str) -> dict | None:
    wanted = str(numero or "").strip()
    for lead in _read_leads():
        if str(lead.get("numero", "")).strip() == wanted:
            return lead
    return None


def _money(value) -> str:
    try:
        amount = float(value or 0)
    except (TypeError, ValueError):
        amount = 0
    return f"{amount:,.2f}".replace(",", " ").replace(".", ",") + " €"


def _float_value(value, default=0.0):
    try:
        return float(str(value or "").replace(" ", "").replace(",", "."))
    except (TypeError, ValueError):
        return default


def _active_delegataire():
    delegataires = _read_delegataires()
    return next((d for d in delegataires if d.get("actif")), delegataires[0] if delegataires else DEFAULT_DELEGATAIRES[0])


def _next_devis_version(numero: str) -> int:
    os.makedirs(DEVIS_DIR, exist_ok=True)
    versions = []
    for name in os.listdir(DEVIS_DIR):
        m = re.fullmatch(rf"{re.escape(numero)}_v(\d+)\.pdf", name)
        if m:
            versions.append(int(m.group(1)))
    return (max(versions) if versions else 0) + 1


def _devis_path(numero: str, version: int) -> str:
    return os.path.join(DEVIS_DIR, f"{numero}_v{version}.pdf")


def _devis_context(numero: str) -> dict:
    lead = _find_lead(numero)
    if not lead:
        raise HTTPException(status_code=404, detail="Prospect introuvable")
    catalogue = _read_json(CATALOGUE_PAC_PATH, DEFAULT_CATALOGUE_PAC)
    if not isinstance(catalogue, list):
        catalogue = DEFAULT_CATALOGUE_PAC
    service = "Chauffage + ECS"
    phase = str(lead.get("phase_electrique") or "monophase")
    wants_tri = "tri" in phase.lower()
    compatibles = []
    for model in catalogue:
        nom_ref = f"{model.get('nom','')} {model.get('ref','')}".upper()
        if "DUO" not in nom_ref:
            continue
        if wants_tri and "TRI" not in nom_ref:
            continue
        if not wants_tri and "TRI" in nom_ref:
            continue
        puissance = _float_value(model.get("puiss_chauf") or model.get("puiss35") or model.get("puissance_kw"))
        if puissance > 0:
            compatibles.append((puissance, model))
    compatibles.sort(key=lambda item: item[0])
    modele = compatibles[0][1] if compatibles else (catalogue[0] if catalogue else {})
    puissance = _float_value(modele.get("puiss_chauf") or modele.get("puiss35") or modele.get("puissance_kw"), 9)
    prix_ttc = _float_value(modele.get("ttc") or modele.get("prix_ttc"), 14990)
    baremes = _read_json(BAREMES_PATH, {})
    forfaits = baremes.get("forfaits_mpr") if isinstance(baremes, dict) else {}
    if not isinstance(forfaits, dict):
        forfaits = {}
    categorie = str(lead.get("categorie") or "modeste")
    mpr = _float_value(forfaits.get(categorie), {"tres_modeste": 5000, "modeste": 4000, "intermediaire": 3000, "superieur": 0}.get(categorie, 4000))
    delegataire = _active_delegataire()
    mwh = max(_float_value(lead.get("surface_logement_m2"), 90) / 10, 1)
    cee_unitaire = _float_value(delegataire.get("mwh_precaire" if categorie == "tres_modeste" else "mwh_classique"), 7.2)
    cee = round(mwh * cee_unitaire * 10, 2)
    bonif = baremes.get("bonification_cee", {"actif": True, "multiplicateur": 5}) if isinstance(baremes, dict) else {"actif": True, "multiplicateur": 5}
    if isinstance(bonif, dict) and bonif.get("actif", True):
        cee *= int(bonif.get("multiplicateur") or 5)
    reste = max(prix_ttc - mpr - cee, 0)
    mensualite_10 = reste / 120 if reste else 0
    surface_chauffee = round(_float_value(lead.get("surface_logement_m2"), 100) * 0.9, 1)
    return {
        "lead": lead,
        "numero": numero,
        "modele": modele.get("nom") or modele.get("ref") or "ATLANTIC ALFÉA EXCELLIA S DUO 9",
        "puissance": puissance,
        "prix_ttc": prix_ttc,
        "mpr": mpr,
        "cee": cee,
        "reste": reste,
        "mensualite_10": mensualite_10,
        "service": service,
        "phase": "Triphasé" if wants_tri else "Monophasé",
        "surface_chauffee": surface_chauffee,
        "zone": lead.get("zone_climatique") or lead.get("zone_climatique_chantier") or "",
        "delegataire": delegataire.get("nom", "PICOTY"),
        "categorie": categorie,
    }


def _generate_devis_pdf(numero: str) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    ctx = _devis_context(numero)
    lead = ctx["lead"]
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=36, leftMargin=36, topMargin=36, bottomMargin=36)
    styles = getSampleStyleSheet()
    story = []
    header = Table(
        [[Paragraph("<b>Hexa-Rénov'</b>", styles["Title"]), Paragraph(f"<font color='white'>{numero}</font>", styles["Normal"])]],
        colWidths=[350, 150],
        rowHeights=[60],
    )
    header.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#002E5A")),
        ("TEXTCOLOR", (0, 0), (-1, -1), colors.white),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (1, 0), (1, 0), "RIGHT"),
    ]))
    story.append(header)
    story.append(Paragraph(f"Date d'édition : {_now_iso().split('T')[0]}", styles["Normal"]))
    story.append(Spacer(1, 12))
    client = f"{lead.get('civilite','')} {lead.get('nom','')} {lead.get('prenom','')}".strip()
    adresse = " ".join(str(lead.get(k, "")).strip() for k in ("adresse_chantier", "code_postal_chantier", "ville_chantier") if lead.get(k))
    story.append(Table([[Paragraph(f"<b>CLIENT</b><br/>{client}<br/>{adresse}<br/>{lead.get('telephone','')} | {lead.get('email','')}", styles["Normal"])]], colWidths=[500], style=[("BOX", (0, 0), (-1, -1), 0.5, colors.grey), ("PADDING", (0, 0), (-1, -1), 8)]))
    story.append(Spacer(1, 12))
    story.append(Paragraph("<b>INSTALLATION POMPE À CHALEUR AIR/EAU</b>", styles["Heading2"]))
    story.append(Paragraph(f"Modèle : {ctx['modele']}<br/>Puissance : {ctx['puissance']:.1f} kW<br/>Service : {ctx['service']}<br/>Phase : {ctx['phase']}<br/>Surface chauffée : {ctx['surface_chauffee']} m²<br/>Zone climatique : {ctx['zone']}", styles["Normal"]))
    story.append(Spacer(1, 12))
    rows = [
        ["Désignation", "Montant TTC"],
        ["Fourniture et pose PAC", _money(ctx["prix_ttc"])],
        [f"MaPrimeRénov' (catégorie {ctx['categorie']})", "-" + _money(ctx["mpr"])],
        [f"Prime CEE ({ctx['delegataire']} classique)", "-" + _money(ctx["cee"] / 5 if ctx["cee"] else 0)],
        ["Bonification CEE (coup de pouce x5)", "-" + _money(ctx["cee"] - (ctx["cee"] / 5 if ctx["cee"] else 0))],
        ["RESTE À CHARGE TTC", _money(ctx["reste"])],
    ]
    table = Table(rows, colWidths=[360, 140])
    table.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EEF2F7")),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
    ]))
    story.append(table)
    story.append(Spacer(1, 12))
    story.append(Table([["Durée", "Mensualité"], ["5 ans", _money(ctx["reste"] / 60) + "/mois"], ["7 ans", _money(ctx["reste"] / 84) + "/mois"], ["10 ans", _money(ctx["mensualite_10"]) + "/mois"]], colWidths=[250, 250], style=[("GRID", (0, 0), (-1, -1), 0.5, colors.grey), ("ALIGN", (1, 0), (1, -1), "RIGHT")]))
    story.append(Spacer(1, 24))
    story.append(Paragraph("Hexa-Rénov' SAS — Asnières-sur-Seine (92)<br/>SIRET : [à compléter]<br/>RCS Nanterre<br/>Devis valable 30 jours à compter de la date d'édition", styles["Normal"]))
    story.append(Paragraph(f"<font size='8'>Document généré le {_now_iso()} via le simulateur Hexa-Rénov'</font>", styles["Normal"]))
    doc.build(story)
    return buffer.getvalue()


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
async def index() -> HTMLResponse:
    """Serve the main page exactly as provided (no templating/transformation)."""
    index_path = os.path.join(TEMPLATES_DIR, "index.html")
    with open(index_path, encoding="utf-8") as f:
        return HTMLResponse(content=f.read())


@app.get("/health")
async def health() -> JSONResponse:
    return JSONResponse({"status": "ok"})


@app.get("/api/baremes")
async def get_baremes():
    if not os.path.exists(BAREMES_PATH):
        return {}
    with open(BAREMES_PATH, encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# A) Leads
# ---------------------------------------------------------------------------


@app.get("/api/catalogue-pac")
def get_catalogue_pac() -> JSONResponse:
    return JSONResponse(_read_catalogue_pac())


@app.get("/api/gmaps-key")
def get_gmaps_key() -> JSONResponse:
    return JSONResponse({"key": os.environ.get("GMAPS_API_KEY", "")})


@app.get("/api/parcelle")
def get_parcelle(lat: float, lon: float) -> JSONResponse:
    geom = json.dumps({"type": "Point", "coordinates": [lon, lat]})
    qs = urllib.parse.urlencode({"geom": geom, "_limit": "1"})
    url = f"https://apicarto.ign.fr/api/cadastre/parcelle?{qs}"
    try:
        with urllib.request.urlopen(url, timeout=10) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception:
        return JSONResponse({"parcelle": None})

    feature = (payload.get("features") or [None])[0]
    props = (feature or {}).get("properties") or {}
    code_insee = str(props.get("code_insee") or props.get("commune") or "").strip()
    raw_section = str(props.get("section") or "").strip()
    raw_numero = str(props.get("numero") or "").strip()
    if not (code_insee and raw_section and raw_numero):
        return JSONResponse({"parcelle": None})
    prefixe = str(props.get("prefixe") or "000").strip().zfill(3)
    section = raw_section.zfill(2)
    numero = raw_numero.zfill(4)
    return JSONResponse({"parcelle": f"{code_insee}-{prefixe}-{section}-{numero}", "source": "ign"})


@app.post("/api/catalogue-pac")
async def post_catalogue_pac(request: Request) -> JSONResponse:
    try:
        payload = await request.json()
    except ValueError as exc:
        raise HTTPException(
            status_code=400, detail=f"Payload JSON invalide: {exc}"
        ) from exc

    if not isinstance(payload, list):
        raise HTTPException(status_code=400, detail="Le payload doit être un tableau JSON.")

    validated = []
    for idx, entry in enumerate(payload):
        if not isinstance(entry, dict):
            raise HTTPException(
                status_code=400,
                detail=f"Entrée #{idx + 1}: un objet JSON est attendu.",
            )

        ref = str(entry.get("ref", "")).strip()
        nom = str(entry.get("nom", "")).strip()
        if not ref and not nom:
            raise HTTPException(
                status_code=400,
                detail=f"Entrée #{idx + 1}: 'ref' ou 'nom' est obligatoire.",
            )

        raw_ttc = entry.get("ttc", entry.get("prix_ttc"))
        try:
            ttc = float(str(raw_ttc).replace(" ", "").replace(",", "."))
        except (TypeError, ValueError):
            raise HTTPException(
                status_code=400,
                detail=f"Entrée #{idx + 1}: 'ttc' doit être numérique.",
            ) from None

        if ttc < 0:
            raise HTTPException(
                status_code=400,
                detail=f"Entrée #{idx + 1}: 'ttc' doit être positif.",
            )

        item = dict(entry)
        if ref:
            item["ref"] = ref
        if nom:
            item["nom"] = nom
        item["ttc"] = round(ttc, 2)
        item.setdefault("description_technique", "")
        validated.append(item)

    _atomic_write_json(CATALOGUE_PAC_PATH, validated)
    return JSONResponse({"ok": True, "count": len(validated)})


@app.post("/api/leads")
async def save_lead(request: Request) -> JSONResponse:
    payload = _normalize_lead_payload(await _read_request_payload(request))
    lead, created = _upsert_lead(payload)
    return JSONResponse(
        {
            "ok": True,
            "numero": lead.get("numero"),
            "lead": _lead_for_response(lead),
            "created": created,
        }
    )


@app.get("/api/leads")
def get_leads(include_deleted: bool = False) -> JSONResponse:
    leads = _read_leads()
    if not include_deleted:
        leads = [lead for lead in leads if not _is_deleted(lead)]
    return JSONResponse([_lead_for_response(lead) for lead in leads])


@app.get("/api/leads/trash")
def get_leads_trash() -> JSONResponse:
    return JSONResponse([_lead_for_response(lead) for lead in _read_leads() if _is_deleted(lead)])


@app.get("/api/leads/{numero}")
def get_lead(numero: str) -> JSONResponse:
    wanted = str(numero or "").strip()
    for lead in _read_leads():
        if str(lead.get("numero", "")).strip() == wanted:
            return JSONResponse(_lead_for_response(lead))
    raise HTTPException(status_code=404, detail="Prospect introuvable")


@app.post("/api/leads/{numero}")
async def update_lead(numero: str, request: Request) -> JSONResponse:
    payload = _normalize_lead_payload(await _read_request_payload(request))
    lead, _ = _upsert_lead(payload, forced_numero=numero)
    return JSONResponse({"ok": True, "numero": lead.get("numero"), "lead": _lead_for_response(lead)})


@app.delete("/api/leads/{numero}")
def delete_lead(numero: str) -> JSONResponse:
    leads = _read_leads()
    index = _find_lead_index(leads, numero)
    if index is None:
        raise HTTPException(status_code=404, detail="Prospect introuvable")
    leads[index]["deleted_at"] = _now_iso()
    leads[index]["updated_at"] = _now_iso()
    _atomic_write_json(LEADS_PATH, leads)
    return JSONResponse({"ok": True})


@app.post("/api/leads/{numero}/restore")
def restore_lead(numero: str) -> JSONResponse:
    leads = _read_leads()
    index = _find_lead_index(leads, numero)
    if index is None:
        raise HTTPException(status_code=404, detail="Prospect introuvable")
    leads[index]["deleted_at"] = ""
    leads[index]["updated_at"] = _now_iso()
    _atomic_write_json(LEADS_PATH, leads)
    return JSONResponse({"ok": True})


@app.delete("/api/leads/{numero}/purge")
def purge_lead(numero: str) -> JSONResponse:
    leads = _read_leads()
    index = _find_lead_index(leads, numero)
    if index is None:
        raise HTTPException(status_code=404, detail="Prospect introuvable")
    del leads[index]
    _atomic_write_json(LEADS_PATH, leads)
    return JSONResponse({"ok": True})


@app.post("/prospect/ajax")
async def save_prospect_ajax(request: Request) -> JSONResponse:
    payload = _normalize_lead_payload(await _read_request_payload(request))
    lead, created = _upsert_lead(payload)
    return JSONResponse(
        {
            "ok": True,
            "status": "ok",
            "numero": lead.get("numero"),
            "lead": _lead_for_response(lead),
            "created": created,
        }
    )


@app.post("/prospect/{numero}/ajax")
async def update_prospect_ajax(numero: str, request: Request) -> JSONResponse:
    payload = _normalize_lead_payload(await _read_request_payload(request))
    lead, _ = _upsert_lead(payload, forced_numero=numero)
    return JSONResponse(
        {"ok": True, "status": "ok", "numero": lead.get("numero"), "lead": _lead_for_response(lead)}
    )


# ---------------------------------------------------------------------------
# B) Import leads from xlsx/xls/csv
# ---------------------------------------------------------------------------
@app.post("/api/import-leads")
async def import_leads(file: UploadFile = File(...)) -> JSONResponse:
    import pandas as pd

    raw = await file.read()
    name = (file.filename or "").lower()
    errors = []

    try:
        if name.endswith(".csv"):
            df = pd.read_csv(io.BytesIO(raw), sep=None, engine="python", dtype=str)
        else:
            df = pd.read_excel(io.BytesIO(raw), dtype=str)
    except Exception as exc:  # noqa: BLE001 - report parse failure to the client
        return JSONResponse(
            {"ok": False, "imported": 0, "errors": [f"Lecture du fichier impossible : {exc}"]},
            status_code=400,
        )

    df = df.fillna("")
    # Map source columns -> canonical prospect fields.
    col_map = {}
    for col in df.columns:
        field = _FIELD_ALIASES.get(_norm(col))
        if field and field not in col_map.values():
            col_map[col] = field

    leads = _read_leads()
    notes = _read_notes()
    imported = 0

    for idx, row in df.iterrows():
        record = {field: str(row[col]).strip() for col, field in col_map.items()}
        record = {k: v for k, v in record.items() if k in IMPORT_PROSPECT_FIELDS}
        if "statut" in record:
            record["statut"] = _normalize_statut(record.get("statut"))
        if "categorie" in record:
            record["categorie"] = _normalize_categorie(record.get("categorie"))
        note_text = ""
        for col, field in col_map.items():
            if field == "notes":
                note_text = str(row[col]).strip()

        # Skip fully empty rows.
        if not any(record.values()) and not note_text:
            continue

        numero = _next_numero(leads)
        prospect = {"numero": numero, "date": _now_iso()}
        prospect.update({field: record.get(field, "") for field in IMPORT_PROSPECT_FIELDS})
        leads.append(prospect)
        imported += 1

        if note_text:
            notes.setdefault(numero, []).append(
                {"texte": note_text, "date": _now_iso(), "auteur": "Import Excel"}
            )

    _atomic_write_json(LEADS_PATH, leads)
    _atomic_write_json(NOTES_PATH, notes)

    return JSONResponse({"ok": True, "imported": imported, "errors": errors})


# ---------------------------------------------------------------------------
# C) Notes / commentaires of a prospect (read)
# ---------------------------------------------------------------------------
@app.get("/prospect/{numero}/commentaires-json")
def commentaires_json(numero: str) -> JSONResponse:
    notes = _read_notes()
    entries = notes.get(numero, [])
    return JSONResponse(
        {"numero": numero, "commentaires": [_note_for_front(e, idx) for idx, e in enumerate(entries)]}
    )


# ---------------------------------------------------------------------------
# D) Add a note / commentaire to a prospect
# ---------------------------------------------------------------------------
@app.post("/prospect/{numero}/commentaire-ajax")
async def commentaire_ajax(numero: str, request: Request) -> JSONResponse:
    payload_form = None
    payload_json = None
    ctype = request.headers.get("content-type", "")
    if "application/json" in ctype:
        try:
            payload_json = await request.json()
        except ValueError:
            payload_json = None
    else:
        try:
            payload_form = await request.form()
        except Exception:  # noqa: BLE001
            payload_form = None

    texte = _extract_texte(payload_form, payload_json).strip()
    auteur = _extract_auteur(payload_form, payload_json)
    if not texte:
        return JSONResponse({"ok": False, "msg": "Texte vide"}, status_code=400)

    notes = _read_notes()
    notes.setdefault(numero, []).append(
        {"texte": texte, "date": _now_iso(), "auteur": auteur}
    )
    _atomic_write_json(NOTES_PATH, notes)

    return JSONResponse({"ok": True, "count": len(notes[numero])})


@app.delete("/prospect/{numero}/commentaire/{commentaire_id}")
def supprimer_commentaire(numero: str, commentaire_id: int) -> JSONResponse:
    notes = _read_notes()
    entries = notes.get(numero, [])
    if not isinstance(entries, list) or commentaire_id < 0 or commentaire_id >= len(entries):
        raise HTTPException(status_code=404, detail="Note introuvable")
    del entries[commentaire_id]
    notes[numero] = entries
    _atomic_write_json(NOTES_PATH, notes)
    return JSONResponse({"ok": True, "count": len(entries)})


@app.get("/prospect/{numero}/echanges-json")
def echanges_json(numero: str) -> JSONResponse:
    echanges = _read_echanges()
    leads = _read_leads()
    lead = next((lead for lead in leads if str(lead.get("numero", "")).strip() == numero), {})
    entries = echanges.get(numero, [])
    return JSONResponse(
        {
            "numero": numero,
            "nom_complet": _lead_display_name(lead),
            "echanges": [_exchange_for_front(e) for e in entries],
        }
    )


@app.post("/prospect/{numero}/echanges-ajax")
async def echanges_ajax(numero: str, request: Request) -> JSONResponse:
    payload = await _read_request_payload(request)
    contenu = str(payload.get("contenu", "")).strip()
    if not contenu:
        return JSONResponse({"ok": False, "msg": "Texte vide"}, status_code=400)

    auteur = str(payload.get("auteur") or payload.get("created_by") or "").strip() or "Anonyme"
    entry = {
        "type": str(payload.get("type") or "sms").strip() or "sms",
        "contenu": contenu,
        "contenu_html": html.escape(contenu).replace("\n", "<br>"),
        "objet": payload.get("objet") or "",
        "template_id": payload.get("template_id") or "",
        "created_at": _now_iso(),
        "created_by": auteur,
        "auteur": auteur,
    }
    echanges = _read_echanges()
    echanges.setdefault(numero, []).append(entry)
    _atomic_write_json(ECHANGES_PATH, echanges)
    return JSONResponse({"ok": True, "count": len(echanges[numero])})


@app.get("/api/admin/m3")
def get_admin_m3() -> JSONResponse:
    baremes = _read_json(BAREMES_PATH, {})
    if not isinstance(baremes, dict):
        baremes = {}
    return JSONResponse(
        {
            "forfaits_mpr": baremes.get(
                "forfaits_mpr",
                {"tres_modeste": 5000, "modeste": 4000, "intermediaire": 3000, "superieur": 0},
            ),
            "bonification_cee": baremes.get("bonification_cee", {"actif": True, "multiplicateur": 5}),
            "delegataires": _read_delegataires(),
            "modeles_email": _read_modeles_email(),
        }
    )


@app.get("/api/admin/params")
async def get_admin_params():
    """Charge les paramètres Admin depuis le serveur."""
    return load_parametres_admin()


@app.post("/api/admin/params")
async def save_admin_params(request: Request):
    """Sauvegarde les paramètres Admin (écriture atomique)."""
    payload = await _read_request_payload(request)
    save_parametres_admin_atomic(payload)
    return {"success": True}


@app.post("/api/admin/auth")
async def admin_auth(request: Request) -> JSONResponse:
    payload = await _read_request_payload(request)
    password = str(payload.get("password") or "")
    if not hmac.compare_digest(password, _admin_password()):
        raise HTTPException(status_code=401, detail="Mot de passe incorrect")
    issued = str(int(time.time()))
    token_payload = f"admin:{issued}"
    token = f"{token_payload}.{_sign_admin_token(token_payload)}"
    return JSONResponse({"ok": True, "token": token})


@app.get("/api/admin/config")
def get_admin_config() -> JSONResponse:
    baremes = _read_json(BAREMES_PATH, {})
    if not isinstance(baremes, dict):
        baremes = {}
    return JSONResponse({"script_notion_url": baremes.get("script_notion_url", "")})


@app.post("/api/admin/config")
async def post_admin_config(request: Request) -> JSONResponse:
    payload = await _read_request_payload(request)
    baremes = _read_json(BAREMES_PATH, {})
    if not isinstance(baremes, dict):
        baremes = {}
    baremes["script_notion_url"] = str(payload.get("script_notion_url") or "").strip()
    _atomic_write_json(BAREMES_PATH, baremes)
    return JSONResponse({"ok": True, "script_notion_url": baremes["script_notion_url"]})


@app.post("/api/admin/m3")
async def post_admin_m3(request: Request) -> JSONResponse:
    payload = await _read_request_payload(request)
    baremes = _read_json(BAREMES_PATH, {})
    if not isinstance(baremes, dict):
        baremes = {}
    if isinstance(payload.get("forfaits_mpr"), dict):
        baremes["forfaits_mpr"] = payload["forfaits_mpr"]
    if isinstance(payload.get("bonification_cee"), dict):
        baremes["bonification_cee"] = payload["bonification_cee"]
    _atomic_write_json(BAREMES_PATH, baremes)
    if isinstance(payload.get("delegataires"), list):
        delegataires = payload["delegataires"] or DEFAULT_DELEGATAIRES
        if not any(d.get("actif") for d in delegataires):
            delegataires[0]["actif"] = True
        _atomic_write_json(DELEGATAIRES_PATH, delegataires)
    if isinstance(payload.get("modeles_email"), list):
        _atomic_write_json(MODELES_EMAIL_PATH, payload["modeles_email"])
    return JSONResponse({"ok": True})


@app.get("/api/modeles-email")
def get_modeles_email() -> JSONResponse:
    return JSONResponse(_read_modeles_email())


def _load_state_simulateur(numero: str, prospect: dict, catalogue: list[dict]) -> dict:
    state = {
        "numero": numero,
        "modele_pac_id": devis_value(prospect, "modele_pac_id", default=""),
        "modele_pac": devis_value(prospect, "modele_pac", default=""),
        "surface_chauffee": devis_value(prospect, "surface_chauffee", default=""),
        "iso_toit": devis_value(prospect, "iso_toit", default="isole"),
        "iso_mur": devis_value(prospect, "iso_mur", default="isole"),
        "iso_menuiserie": devis_value(prospect, "iso_menuiserie", default="double"),
        "service": devis_value(prospect, "service", default="chauffage_ecs"),
    }
    if not state["modele_pac_id"] and not state["modele_pac"]:
        modele = select_default_modele(prospect, catalogue)
        state["modele_pac_id"] = modele.get("ref") or modele.get("id") or ""
        state["modele_pac"] = modele.get("nom") or modele.get("ref") or ""
    return state


def _next_numero_dossier() -> str:
    counters = _read_json(COUNTERS_PATH, {"dossier": 0})
    if not isinstance(counters, dict):
        counters = {"dossier": 0}
    numero_dossier, counters = generer_numero_dossier(counters)
    _atomic_write_json(COUNTERS_PATH, counters)
    return numero_dossier


def _notedim_path(numero: str, version: int) -> str:
    return os.path.join(DEVIS_DIR, f"{numero}_notedim_v{version}.pdf")


def _build_devis_context(request: Request, numero: str) -> dict:
    prospect = _find_lead(numero)
    if not prospect:
        raise HTTPException(status_code=404, detail="Prospect introuvable")
    prospect = _lead_for_response(prospect)
    catalogue = _read_catalogue_pac()
    state = _load_state_simulateur(numero, prospect, catalogue)
    admin = _admin_payload_with_m3()

    missing = validate_prospect_for_devis(prospect, state)
    if missing:
        return {"request": request, "missing": missing, "numero": numero, "_error_template": "erreur_champs_manquants.html"}

    modele_ref = state.get("modele_pac_id") or state.get("modele_pac")
    modele_obj = find_modele(catalogue, modele_ref) or select_default_modele(prospect, catalogue)
    today = datetime.now()
    calculs = calculer_devis(prospect, state, admin, catalogue)
    sous_traitant = next((st for st in admin.get("sous_traitants", []) if st.get("actif")), {})
    cp_chantier = devis_value(prospect, "cp_chantier", "code_postal_chantier", "cp", default="")
    ville_chantier = devis_value(prospect, "ville", "ville_chantier", default="")
    date_visite = devis_value(prospect, "date_visite_technique", default="À déterminer")
    if date_visite != "À déterminer" and re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(date_visite)):
        try:
            date_visite = datetime.strptime(str(date_visite), "%Y-%m-%d").strftime("%d/%m/%Y")
        except ValueError:
            pass
    context = {
        "request": request,
        "civilite": prospect.get("civilite", ""),
        "nom": str(prospect.get("nom", "")).upper(),
        "prenom": prospect.get("prenom", ""),
        "telephone": prospect.get("telephone", ""),
        "email": str(prospect.get("email", "")).lower(),
        "adresse_personne": devis_value(prospect, "adresse_personne", "adresse_chantier", default=""),
        "cp_personne": devis_value(prospect, "cp_personne", "code_postal_personne", "code_postal_chantier", "cp", default=""),
        "ville_personne": devis_value(prospect, "ville_personne", "ville_chantier", "ville", default=""),
        "adresse_chantier": devis_value(prospect, "adresse", "adresse_chantier", default=""),
        "cp_chantier": cp_chantier,
        "ville_chantier": ville_chantier,
        "usage_bien": prospect.get("usage_bien", "proprietaire_occupant"),
        "numero_devis": generer_numero_devis(prospect),
        "numero_dossier": _next_numero_dossier(),
        "date_emission": today.strftime("%d/%m/%Y"),
        "date_validite": (today + timedelta(days=60)).strftime("%d/%m/%Y"),
        "date_visite_technique": date_visite,
        "date_debut_travaux": "À déterminer",
        "type_logement": prospect.get("type_logement", ""),
        "surface_habitable": str(devis_value(prospect, "surface_habitable", "surface_logement_m2", default="")),
        "chauffage_actuel": devis_value(prospect, "chauffage_actuel", "mode_chauffage", default=""),
        "parcelle_cadastrale": prospect.get("parcelle_cadastrale", ""),
        "zone_climatique": calculer_zone_climatique(cp_chantier, prospect.get("zone_climatique") or prospect.get("zone_climatique_chantier")),
        "modele_pac": modele_obj.get("nom") or modele_obj.get("ref") or "",
        "description_pac": modele_obj.get("description_technique", "") if modele_obj else "",
        "sous_traitant": format_sous_traitant(sous_traitant),
        **format_devis_amounts(calculs),
    }
    return context


def _build_notedim_context(request: Request, numero: str) -> dict:
    prospect = _find_lead(numero)
    if not prospect:
        raise HTTPException(status_code=404, detail="Prospect introuvable")
    prospect = _lead_for_response(prospect)
    catalogue = _read_catalogue_pac()
    state = _load_state_simulateur(numero, prospect, catalogue)
    missing = validate_prospect_for_devis(prospect, state)
    if missing:
        return {"request": request, "missing": missing, "numero": numero, "_error_template": "erreur_champs_manquants.html"}
    now = datetime.now()
    cp_chantier = devis_value(prospect, "cp_chantier", "code_postal_chantier", "cp", default="")
    context = {
        "request": request,
        "numero_notedim": generer_numero_notedim(prospect),
        "date_emission": now.strftime("%d/%m/%Y"),
        "heure_emission": now.strftime("%H:%M"),
        "nom": str(prospect.get("nom", "")).upper(),
        "prenom": prospect.get("prenom", ""),
        "numero_prospect": numero,
        "telephone": prospect.get("telephone", ""),
        "email": str(prospect.get("email", "")).lower(),
        "adresse_chantier": devis_value(prospect, "adresse", "adresse_chantier", default=""),
        "cp_chantier": cp_chantier,
        "ville_chantier": devis_value(prospect, "ville", "ville_chantier", default=""),
        "type_logement": prospect.get("type_logement", ""),
        "chauffage_actuel": devis_value(prospect, "chauffage_actuel", "mode_chauffage", default=""),
        **calculer_notedim(prospect, state, catalogue),
    }
    return context


def _render_template_response(request: Request, template_name: str, context: dict) -> HTMLResponse:
    name = context.pop("_error_template", template_name)
    context.setdefault("request", request)
    html_content = templates.env.get_template(name).render(context)
    return HTMLResponse(content=html_content)


def _render_devis_html(request: Request, numero: str) -> str:
    ctx = _build_devis_context(request, numero)
    name = ctx.pop("_error_template", "devis_pac.html")
    ctx.setdefault("request", request)
    return templates.env.get_template(name).render(ctx)


def _render_notedim_html(request: Request, numero: str) -> str:
    ctx = _build_notedim_context(request, numero)
    name = ctx.pop("_error_template", "notedim_pac.html")
    ctx.setdefault("request", request)
    return templates.env.get_template(name).render(ctx)


def _html_to_pdf(html_content: str, request: Request) -> bytes:
    try:
        from weasyprint import HTML
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"WeasyPrint indisponible: {exc}") from exc
    return HTML(string=html_content, base_url=str(request.base_url)).write_pdf()


def _write_pdf(path: str, pdf_bytes: bytes) -> str:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(pdf_bytes)
    return path


def _ensure_devis_pdf(numero: str, request: Request, version: int | None = None) -> tuple[str, int]:
    version = version or _next_devis_version(numero)
    path = _devis_path(numero, version)
    if not os.path.exists(path):
        _write_pdf(path, _html_to_pdf(_render_devis_html(request, numero), request))
    return path, version


def _ensure_notedim_pdf(numero: str, request: Request, version: int) -> str:
    path = _notedim_path(numero, version)
    if not os.path.exists(path):
        _write_pdf(path, _html_to_pdf(_render_notedim_html(request, numero), request))
    return path


@app.get("/api/devis/{numero}/validate")
async def validate_devis(numero: str) -> JSONResponse:
    prospect = _find_lead(numero)
    if not prospect:
        raise HTTPException(status_code=404, detail="Prospect introuvable")
    catalogue = _read_catalogue_pac()
    state = _load_state_simulateur(numero, _lead_for_response(prospect), catalogue)
    missing = validate_prospect_for_devis(_lead_for_response(prospect), state)
    return JSONResponse({"ok": not missing, "missing": missing})


@app.get("/api/devis/{numero}/preview", response_class=HTMLResponse)
async def devis_preview(numero: str, request: Request) -> HTMLResponse:
    return _render_template_response(request, "devis_pac.html", _build_devis_context(request, numero))


@app.get("/api/notedim/{numero}/preview", response_class=HTMLResponse)
async def notedim_preview(numero: str, request: Request) -> HTMLResponse:
    return _render_template_response(request, "notedim_pac.html", _build_notedim_context(request, numero))


@app.get("/api/devis/{numero}/pdf")
async def devis_pdf(numero: str, request: Request):
    pdf_bytes = _html_to_pdf(_render_devis_html(request, numero), request)
    version = _next_devis_version(numero)
    _write_pdf(_devis_path(numero, version), pdf_bytes)
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="Devis_{numero}.pdf"'},
    )


@app.get("/api/notedim/{numero}/pdf")
async def notedim_pdf(numero: str, request: Request):
    version = _next_devis_version(numero)
    pdf_bytes = _html_to_pdf(_render_notedim_html(request, numero), request)
    _write_pdf(_notedim_path(numero, version), pdf_bytes)
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="NoteDim_{numero}.pdf"'},
    )


async def _send_devis(numero: str, payload: dict, request: Request) -> dict:
    prospect = _find_lead(numero)
    if not prospect:
        raise HTTPException(status_code=404, detail="Prospect introuvable")
    email_to = str(payload.get("destinataire") or prospect.get("email") or "").strip()
    if not email_to:
        raise HTTPException(status_code=400, detail="Email prospect manquant")
    api_key = os.environ.get("RESEND_API_KEY", "")
    if not api_key:
        raise HTTPException(status_code=400, detail="RESEND_API_KEY non configurée")

    devis_path, version = _ensure_devis_pdf(numero, request)
    notedim_path = _ensure_notedim_pdf(numero, request, version)
    with open(devis_path, "rb") as f:
        pdf_devis_b64 = base64.b64encode(f.read()).decode()
    with open(notedim_path, "rb") as f:
        pdf_notedim_b64 = base64.b64encode(f.read()).decode()

    import resend

    resend.api_key = api_key
    subject = payload.get("objet") or f"Votre devis Hexa Rénov' - {numero}"
    message_html = payload.get("message_html") or payload.get("message") or (
        f"Bonjour {html.escape(str(prospect.get('prenom') or ''))},<br><br>"
        "Veuillez trouver ci-joint votre devis et la note de dimensionnement.<br><br>"
        "Cordialement,<br>L'équipe Hexa Rénov'"
    )
    result = resend.Emails.send(
        {
            "from": "Hexa Rénov' <a.parisot@hexa-renov.fr>",
            "to": [email_to],
            "subject": subject,
            "html": message_html,
            "attachments": [
                {"filename": f"Devis_{numero}.pdf", "content": pdf_devis_b64},
                {"filename": f"NoteDim_{numero}.pdf", "content": pdf_notedim_b64},
            ],
        }
    )

    now = _now_iso()
    leads = _read_leads()
    idx = _find_lead_index(leads, numero)
    if idx is not None:
        leads[idx]["statut"] = "devis_envoye"
        leads[idx]["date_envoi_devis"] = now
        _atomic_write_json(LEADS_PATH, leads)

    auteur = str(payload.get("auteur") or "Anonyme")
    notes = _read_notes()
    notes.setdefault(numero, []).append(
        {"texte": f"Devis v{version} envoyé le {now} à {email_to} par {auteur}", "date": now, "auteur": auteur}
    )
    _atomic_write_json(NOTES_PATH, notes)

    meta = _read_devis_meta()
    item = {
        "version": version,
        "numero_devis": generer_numero_devis(prospect, version),
        "sent_at": now,
        "email": email_to,
        "file": devis_path,
        "notedim_file": notedim_path,
        "resend_id": result.get("id") if isinstance(result, dict) else "",
        "statut": "envoye",
    }
    meta.setdefault(numero, []).append(item)
    _atomic_write_json(DEVIS_META_PATH, meta)
    sent = _read_devis_envoyes()
    sent.append({"numero_prospect": numero, **item})
    _atomic_write_json(DEVIS_ENVOYES_PATH, sent)
    return {"success": True, "ok": True, "version": version, "resend_id": item["resend_id"]}


@app.post("/api/devis/{numero}/send")
async def send_devis_email(numero: str, request: Request) -> JSONResponse:
    payload = await _read_request_payload(request)
    return JSONResponse(await _send_devis(numero, payload, request))


@app.post("/api/devis/{numero}/envoyer")
async def envoyer_devis(numero: str, request: Request) -> JSONResponse:
    payload = await _read_request_payload(request)
    return JSONResponse(await _send_devis(numero, payload, request))


@app.get("/api/devis/{numero}/list")
async def list_devis(numero: str) -> JSONResponse:
    meta = _read_devis_meta().get(numero, [])
    items = []
    for item in meta:
        version = int(item.get("version") or 0)
        path = item.get("file") or _devis_path(numero, version)
        if version and os.path.exists(path):
            items.append({
                "version": version,
                "numero_devis": item.get("numero_devis") or f"v{version}",
                "sent_at": item.get("sent_at", ""),
                "email": item.get("email", ""),
                "file": path,
            })
    return JSONResponse(items)


@app.get("/api/devis/{numero}/download")
async def download_devis(numero: str, version: int):
    path = _devis_path(numero, version)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Devis introuvable")
    return FileResponse(path, media_type="application/pdf", filename=os.path.basename(path))


@app.post("/api/modeles-email/{numero}/envoyer")
async def envoyer_modele_email(numero: str, request: Request) -> JSONResponse:
    payload = await _read_request_payload(request)
    lead = _find_lead(numero)
    if not lead:
        raise HTTPException(status_code=404, detail="Prospect introuvable")
    email_to = str(lead.get("email") or "").strip()
    if not email_to:
        raise HTTPException(status_code=400, detail="Email prospect manquant")
    sujet = str(payload.get("sujet") or "")
    contenu = str(payload.get("contenu") or "")
    # Legacy SMTP block intentionally disabled. Devis delivery now uses Resend;
    # email-template history is still recorded for traceability.
    auteur = str(payload.get("auteur") or "Anonyme")
    notes = _read_notes()
    notes.setdefault(numero, []).append({"texte": f"📧 Email envoyé à {email_to} : {sujet}", "date": _now_iso(), "auteur": auteur})
    _atomic_write_json(NOTES_PATH, notes)
    return JSONResponse({"ok": True})
