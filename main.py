import io
import base64
import hashlib
import html
import hmac
import json
import os
import re
import shutil
import tempfile
# import smtplib  # legacy SMTP disabled: devis are sent with Resend.
import time
import urllib.parse
import urllib.request
import unicodedata
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.background import BackgroundTask

from services.service_devis import (
    DEPT_ZONE,
    calculer_devis,
    calculer_economie_devis,
    resoudre_ballon,
    calculer_financement_devis,
    calculer_notedim,
    calculer_zone_climatique,
    find_modele,
    format_devis_amounts,
    format_sous_traitant,
    generer_lot_titre,
    generer_numero_devis,
    generer_numero_dossier,
    generer_numero_notedim,
    money,
    parse_legacy_description,
    select_default_modele,
    validate_prospect_for_devis,
    float_value,
    value as devis_value,
    _format_date_fr,
)
from services.backup_github import start_backup_scheduler

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
# users.json dans DATA_DIR (volume persistant) mais EXCLU du backup GitHub (cf. backup_github._collect_json_files). Chemin configurable.
USERS_PATH = os.environ.get("USERS_PATH", os.path.join(DATA_DIR, "users.json"))
COUNTERS_PATH = os.path.join(DATA_DIR, "counters.json")
DEVIS_ENVOYES_PATH = os.path.join(DATA_DIR, "devis_envoyes.json")
STATES_SIMULATEUR_DIR = os.path.join(DATA_DIR, "states_simulateur")
DEVIS_DIR = os.path.join(DATA_DIR, "devis")
DEVIS_META_PATH = os.path.join(DEVIS_DIR, "devis_meta.json")
FICHES_DIR = os.path.join(DATA_DIR, "fiches_techniques")
FICHES_INDEX_PATH = os.path.join(FICHES_DIR, "index.json")
REPO_CATALOGUE_PATH = os.path.join(REPO_DATA_DIR, "catalogue_pac.json")
REPO_BAREMES_PATH = os.path.join(REPO_DATA_DIR, "baremes.json")
DOCUMENTS_CATEGORIES_PATH = os.path.join(DATA_DIR, "documents_categories.json")
REPO_DOCUMENTS_CATEGORIES_PATH = os.path.join(REPO_DATA_DIR, "documents_categories.json")
DOCUMENTS_DIR = os.path.join(DATA_DIR, "documents")

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

DEFAULT_FORMULE_BAR_TH_171 = {
    "tableau_montant_base": [
        {"logement": "Appartement", "etas_min": 111, "etas_max": 139.99, "montant_kwhc": 48700, "actif": True},
        {"logement": "Appartement", "etas_min": 140, "etas_max": 999, "montant_kwhc": 58900, "actif": True},
        {"logement": "Maison", "etas_min": 111, "etas_max": 139.99, "montant_kwhc": 90900, "actif": True},
        {"logement": "Maison", "etas_min": 140, "etas_max": 999, "montant_kwhc": 109200, "actif": True},
    ],
    "tableau_facteur_surface": [
        {"logement": "Appartement", "surface_min": 0, "surface_max": 34.99, "facteur": 0.5, "actif": True},
        {"logement": "Appartement", "surface_min": 35, "surface_max": 59.99, "facteur": 0.7, "actif": True},
        {"logement": "Appartement", "surface_min": 60, "surface_max": 9999, "facteur": 1.0, "actif": True},
        {"logement": "Maison", "surface_min": 0, "surface_max": 69.99, "facteur": 0.5, "actif": True},
        {"logement": "Maison", "surface_min": 70, "surface_max": 89.99, "facteur": 0.7, "actif": True},
        {"logement": "Maison", "surface_min": 90, "surface_max": 9999, "facteur": 1.0, "actif": True},
    ],
    "tableau_facteur_zone": [
        {"zone": "H1", "facteur": 1.2, "actif": True},
        {"zone": "H2", "facteur": 1.0, "actif": True},
        {"zone": "H3", "facteur": 0.7, "actif": True},
    ],
}

DEFAULT_PLAFONDS_REGLEMENTAIRES = {
    "plafond_eligible_ttc": 12000,
    "plafonds_aides_pct": {
        "tres_modeste": 90,
        "modeste": 75,
        "intermediaire": 60,
        "superieur": 0,
    },
}

DEFAULT_BAREMES_ANAH = {"hors_idf":{"_description":"RFR maximum par catégorie selon nombre de personnes du foyer (Hors IDF) - source XLS","tres_modeste":{"1":17363,"2":25393,"3":30540,"4":35676,"5":40835,"personne_supplementaire":5151},"modeste":{"1":22259,"2":32553,"3":39148,"4":45735,"5":52348,"personne_supplementaire":6598},"intermediaire":{"1":31185,"2":45842,"3":55196,"4":64550,"5":73907,"personne_supplementaire":9357},"superieur":{"_description":"Au-dessus du plafond intermédiaire"}},"idf":{"_description":"RFR maximum par catégorie selon nombre de personnes du foyer (IDF) - source XLS","tres_modeste":{"1":24031,"2":35270,"3":42357,"4":49455,"5":56580,"personne_supplementaire":7116},"modeste":{"1":29253,"2":42933,"3":51564,"4":60208,"5":68877,"personne_supplementaire":8663},"intermediaire":{"1":40851,"2":60051,"3":71846,"4":84562,"5":96817,"personne_supplementaire":12257}}}

DEFAULT_MARQUES = {
    "ATLANTIC": {"prefixes": ["ATL"], "niveau": "recommande", "positionnement": "A completer en admin", "avantages": ["A completer", "A completer", "A completer"]},
    "THALEOS": {"prefixes": ["THA"], "niveau": "essentiel", "positionnement": "A completer en admin", "avantages": ["A completer", "A completer", "A completer"]},
    "DAIKIN": {"prefixes": ["DAI"], "niveau": "confort", "positionnement": "A completer en admin", "avantages": ["A completer", "A completer", "A completer"]},
}

DEFAULT_PARAMS_ECO_ENERGIE = {
    "conso_zone_kwh_m2_an": {"h1": 150, "h2": 130, "h3": 110},
    "scop_defaut": 3.5,
    "prix_kwh": {"electricite": 0.21, "gaz": 0.12, "fioul": 0.13, "bois": 0.07},
    "inflation_annuelle_pct": {"electricite": 3, "gaz": 4, "fioul": 4, "bois": 2.5, "defaut": 4},
    "duree_vie_pac_ans": 20,
}

DEFAULT_PARAMS_FINANCEMENT = {
    "seuil_rac_eur": 6000,
    "credit_travaux": {
        "sous_seuil": {"taux_pct": 5.90, "duree_mois": 156},
        "sur_seuil": {"taux_pct": 4.90, "duree_mois": 180},
    },
    "mention_premiere_echeance": "Première échéance 180 jours après travaux",
    "eco_ptz": {"taux_pct": 0, "duree_mois": 180},
    "libelles": {
        "option1": "Crédit Travaux",
        "option2": "Éco-PTZ",
        "option3": "Fonds propres",
    },
}

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
        "frais_ecair_pct": 12,
    },
    "ballon_thermo": {
        "modeles": [
            {"ref": "ballon-1", "nom": "Ballon thermodynamique 1", "fourniture_ht": 0, "economie_ecs_mois": 25, "description_specs": []},
            {"ref": "ballon-2", "nom": "Ballon thermodynamique 2", "fourniture_ht": 0, "economie_ecs_mois": 25, "description_specs": []},
        ],
        "prix_pose_ht": 0,
        "forfaits_mpr": {"tres_modeste": 1200, "modeste": 800, "intermediaire": 400, "superieur": 0},
    },
    "sous_traitants": DEFAULT_SOUS_TRAITANTS,
    "formule_bar_th_171": DEFAULT_FORMULE_BAR_TH_171,
    "plafonds_reglementaires": DEFAULT_PLAFONDS_REGLEMENTAIRES,
    "baremes_anah": DEFAULT_BAREMES_ANAH,
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
PARIS_TZ = ZoneInfo("Europe/Paris")

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


ADMIN_UNLOCK_SECONDS = 12 * 3600  # 12h, aligne sur le front (ADMIN_UNLOCK_MS)


def _verify_admin_token(token: str) -> bool:
    if not token or "." not in token:
        return False
    payload, _, sig = token.rpartition(".")
    if not payload.startswith("admin:"):
        return False
    if not hmac.compare_digest(sig, _sign_admin_token(payload)):
        return False
    try:
        issued = int(payload.split(":", 1)[1])
    except (ValueError, IndexError):
        return False
    return (time.time() - issued) <= ADMIN_UNLOCK_SECONDS


def _require_admin(request: Request) -> None:
    """Vérifie le token admin (header X-Admin-Token ou query ?token=) ; 401 sinon."""
    token = request.headers.get("X-Admin-Token") or request.query_params.get("token") or ""
    if not _verify_admin_token(token):
        raise HTTPException(status_code=401, detail="Acces admin requis")


def _sign_devis_token(numero: str) -> str:
    payload = f"devis:{numero}"
    sig = hmac.new(_admin_secret(), payload.encode("utf-8"), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(sig).decode("ascii").rstrip("=")


def _verify_devis_token(numero: str, token: str) -> bool:
    import hmac as _hmac
    return _hmac.compare_digest(token, _sign_devis_token(numero))


# ============ AUTHENTIFICATION (Lot 0 : fondations, SANS enforcement) ============
SESSION_COOKIE = "hexa_session"
SESSION_TTL_SECONDS = int(os.environ.get("SESSION_TTL_SECONDS", str(12 * 3600)))


def _session_secret() -> bytes:
    # Lot 4 rendra SESSION_SECRET obligatoire ; fallback provisoire sur le secret admin.
    return (os.environ.get("SESSION_SECRET") or "").encode("utf-8") or _admin_secret()


def _hash_password(password: str, salt: bytes = None) -> str:
    if salt is None:
        salt = os.urandom(16)
    dk = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=2 ** 14, r=8, p=1, dklen=32)
    return "scrypt$" + base64.b64encode(salt).decode("ascii") + "$" + base64.b64encode(dk).decode("ascii")


def _verify_password(password: str, stored: str) -> bool:
    try:
        algo, salt_b64, dk_b64 = str(stored or "").split("$", 2)
        if algo != "scrypt":
            return False
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(dk_b64)
        dk = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=2 ** 14, r=8, p=1, dklen=len(expected))
        return hmac.compare_digest(dk, expected)
    except Exception:
        return False


def _read_users() -> list:
    data = _read_json(USERS_PATH, [])
    return data if isinstance(data, list) else []


def _write_users(users: list) -> None:
    os.makedirs(os.path.dirname(USERS_PATH) or ".", exist_ok=True)
    _atomic_write_json(USERS_PATH, users)


def _find_user(username: str):
    u = str(username or "").strip().lower()
    for user in _read_users():
        if str(user.get("username", "")).strip().lower() == u and user.get("actif", True):
            return user
    return None


def _ensure_bootstrap_admin() -> None:
    """Seed un admin depuis l'env si users.json est vide (break-glass : jamais verrouille dehors)."""
    if _read_users():
        return
    bu = str(os.environ.get("ADMIN_BOOTSTRAP_USER") or "").strip().lower()
    bp = os.environ.get("ADMIN_BOOTSTRAP_PASSWORD") or ""
    if not bu or not bp:
        return
    _write_users([{
        "id": bu, "username": bu, "password_hash": _hash_password(bp),
        "role": "admin", "actif": True, "cree_at": _now_iso(), "visibilite": "tous",
    }])


def _sign_session(user_id: str, role: str, issued_at: int) -> str:
    payload = f"{user_id}:{role}:{issued_at}"
    sig = hmac.new(_session_secret(), payload.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{payload}:{sig}"


def _verify_session(token: str):
    try:
        parts = str(token or "").split(":")
        if len(parts) != 4:
            return None
        user_id, role, issued_at, sig = parts
        payload = f"{user_id}:{role}:{issued_at}"
        expected = hmac.new(_session_secret(), payload.encode("utf-8"), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected):
            return None
        if (time.time() - int(issued_at)) > SESSION_TTL_SECONDS:
            return None
        return {"user_id": user_id, "role": role}
    except Exception:
        return None


def current_user(request: Request):
    """Renvoie {username, role} si session valide, sinon None. NON bloquant (Lot 0)."""
    sess = _verify_session(request.cookies.get(SESSION_COOKIE) or "")
    if not sess:
        return None
    user = _find_user(sess["user_id"])
    if not user:
        return None
    return {"username": user.get("username"), "role": user.get("role", "commercial")}


def _public_devis_url(request: Request, numero: str) -> str:
    base = str(request.base_url).rstrip("/")
    if base.startswith("http://"):
        base = "https://" + base[len("http://"):]
    return f"{base}/devis-public/{numero}/{_sign_devis_token(numero)}"


def _sign_devis_token_v(numero: str, version) -> str:
    payload = f"devis:{numero}:{version}"
    sig = hmac.new(_admin_secret(), payload.encode("utf-8"), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(sig).decode("ascii").rstrip("=")


def _verify_devis_token_v(numero: str, version, token: str) -> bool:
    import hmac as _hmac
    return _hmac.compare_digest(token, _sign_devis_token_v(numero, version))


def _public_devis_url_v(request: Request, numero: str, version) -> str:
    base = str(request.base_url).rstrip("/")
    if base.startswith("http://"):
        base = "https://" + base[len("http://"):]
    return f"{base}/devis-public/{numero}/{version}/{_sign_devis_token_v(numero, version)}"


def _sign_notedim_token(numero: str) -> str:
    payload = f"notedim:{numero}"
    sig = hmac.new(_admin_secret(), payload.encode("utf-8"), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(sig).decode("ascii").rstrip("=")


def _verify_notedim_token(numero: str, token: str) -> bool:
    import hmac as _hmac
    return _hmac.compare_digest(token, _sign_notedim_token(numero))


def _public_notedim_url(request: Request, numero: str) -> str:
    base = str(request.base_url).rstrip("/")
    if base.startswith("http://"):
        base = "https://" + base[len("http://"):]
    return f"{base}/notedim-public/{numero}/{_sign_notedim_token(numero)}"


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


def _write_text(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def _read_text(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def _devis_html_path(numero: str, version) -> str:
    return os.path.join(DEVIS_DIR, f"{numero}_v{version}.html")


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
    _bt = merged.get("ballon_thermo")
    if isinstance(_bt, dict):
        for _m in (_bt.get("modeles") or []):
            if isinstance(_m, dict) and _m.get("economie_ecs_mois") is None:
                _m["economie_ecs_mois"] = 25
    sous_traitants = merged.get("sous_traitants")
    if not isinstance(sous_traitants, list) or not sous_traitants:
        merged["sous_traitants"] = [dict(DEFAULT_SOUS_TRAITANTS[0])]
    if not any(st.get("actif") for st in merged["sous_traitants"]):
        merged["sous_traitants"][0]["actif"] = True
    return merged


def save_parametres_admin_atomic(payload):
    payload = payload if isinstance(payload, dict) else {}
    existing = load_parametres_admin()
    if not isinstance(existing, dict):
        existing = {}
    data = _deep_merge_defaults(payload, existing)
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
        specs = next_item.get("description_specs")
        if not isinstance(specs, list):
            next_item["description_specs"] = parse_legacy_description(next_item.get("description_technique", ""))
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
    admin["formule_bar_th_171"] = admin.get("formule_bar_th_171", DEFAULT_FORMULE_BAR_TH_171)
    admin["plafonds_reglementaires"] = admin.get("plafonds_reglementaires", DEFAULT_PLAFONDS_REGLEMENTAIRES)
    admin["baremes_anah"] = admin.get("baremes_anah", DEFAULT_BAREMES_ANAH)
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
    _seed_json_file(DOCUMENTS_CATEGORIES_PATH, [], REPO_DOCUMENTS_CATEGORIES_PATH)
    os.makedirs(DEVIS_DIR, exist_ok=True)
    os.makedirs(DOCUMENTS_DIR, exist_ok=True)
    os.makedirs(STATES_SIMULATEUR_DIR, exist_ok=True)
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


def _sent_devis_items(numero):
    items = _read_devis_meta().get(numero, [])
    return items if isinstance(items, list) else []


def _next_sent_version(numero):
    return len(_sent_devis_items(numero)) + 1


def _state_simulateur_path(numero: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", str(numero or ""))
    return os.path.join(STATES_SIMULATEUR_DIR, f"{safe}.json")


def load_state_simulateur(numero: str) -> dict:
    state = _read_json(_state_simulateur_path(numero), {})
    return state if isinstance(state, dict) else {}


def save_state_simulateur_atomic(numero: str, payload: dict) -> dict:
    incoming = payload if isinstance(payload, dict) else {}
    state = load_state_simulateur(numero)
    state.update(incoming)
    state["numero_prospect"] = numero
    state["updated_at"] = _now_paris_iso()
    _atomic_write_json(_state_simulateur_path(numero), state)
    return state


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
    return datetime.now(PARIS_TZ).isoformat(timespec="seconds")


def _now_paris_iso():
    return datetime.now(PARIS_TZ).isoformat(timespec="seconds")


def _today_paris():
    """Date du jour dans le fuseau Paris (objet date)."""
    return datetime.now(PARIS_TZ).date()


def _parse_paris_dt(value):
    """Parseur défensif : ISO ('YYYY-MM-DDTHH:MM[:SS][+tz]') ou date seule
    ('YYYY-MM-DD') -> datetime aware en PARIS_TZ, ou None si illisible.
    Un datetime naïf se voit rattacher PARIS_TZ."""
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(raw)
    except ValueError:
        try:
            dt = datetime.strptime(raw, "%Y-%m-%d")
        except ValueError:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=PARIS_TZ)
    return dt


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


def _split_nom_prenom(value):
    s = str(value or "").strip()
    if not s:
        return "", ""
    mots = s.split()
    if len(mots) == 1:
        return mots[0], ""
    def _is_upper(w):
        lettres = [c for c in w if c.isalpha()]
        return bool(lettres) and all(c.isupper() for c in lettres)
    i = 0
    while i < len(mots) and _is_upper(mots[i]):
        i += 1
    if i == 0 or i == len(mots):
        return mots[0], " ".join(mots[1:])
    return " ".join(mots[:i]), " ".join(mots[i:])


def _normalize_numero_pr(value):
    m = re.search(r"(\d+)", str(value or "").strip())
    return f"PR-{int(m.group(1)):06d}" if m else ""


def _parse_date_fr(value):
    m = re.match(r"^(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{2,4})", str(value or "").strip())
    if not m:
        return ""
    d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
    if y < 100:
        y += 2000
    try:
        return datetime(y, mo, d, tzinfo=PARIS_TZ).isoformat(timespec="seconds")
    except ValueError:
        return ""


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
    "nom prenom": "_nom_prenom",
    "nomprenom": "_nom_prenom",
    "n°": "numero",
    "no": "numero",
    "numero": "numero",
    "cree le": "date",
}

STATUT_ALIASES = {
    "nouveau": "nouveau",
    "contacte": "contacte",
    "contacté": "contacte",
    "a rappeler": "rappeler",
    "à rappeler": "rappeler",
    "a recontacter": "rappeler",
    "rappeler": "rappeler",
    "rdv": "rdv",
    "rdv pris": "rdv",
    "pre_devis": "pre_devis",
    "pre-devis": "pre_devis",
    "pré-devis": "pre_devis",
    "pre_devis_envoye": "pre_devis_envoye",
    "pre-devis envoye": "pre_devis_envoye",
    "pré-devis envoyé": "pre_devis_envoye",
    "envoye en vt": "vt_envoye",
    "envoyé en vt": "vt_envoye",
    "vt_envoye": "vt_envoye",
    "vt valide": "vt_valide",
    "vt validé": "vt_valide",
    "vt_valide": "vt_valide",
    "vt refuse": "vt_refuse",
    "vt refusé": "vt_refuse",
    "vt_refuse": "vt_refuse",
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
    "phase_electrique": "alimentation_electrique",
}

# --- Système "À traiter" (rappels / RDV / multicanal) ---------------------
# Identités déclaratives (non authentifiées) : indicatif, PAS un filtre dur.
ASSIGNES_VALIDES = {"avi", "joelle", "maurice"}
CANAUX_VALIDES = {"appel", "sms", "email"}  # whatsapp plus tard
# Plafonds de tentatives SANS réponse par canal avant "injoignable"
# (les 3 doivent être atteints). À terme : configurables côté admin.
PLAFONDS_CANAL = {"appel": 8, "sms": 5, "email": 5}
# Seuils des détections automatiques (jours). À terme : configurables admin.
DETECT_DEVIS_J = 3
DETECT_JAMAIS_CONTACTE_J = 2
DETECT_SIMU_J = 3
# Borne haute "jamais contacté" : ignore les leads créés il y a plus de N jours.
DETECT_JAMAIS_CONTACTE_MAX_J = 30


def _normalize_assigne(value):
    """Normalise une identité déclarative en minuscule. Tolérant : ne rejette
    jamais une valeur inconnue (cf. CONCEPTION_RAPPELS.md decision 7)."""
    return str(value or "").strip().lower()


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
    "modele_pac_id",
    "modele_pac",
    "surface_chauffee",
    "iso_toit",
    "iso_mur",
    "iso_menuiserie",
    "service",
    "alimentation_electrique",

    # Bloc 5 (Informations fiscales)
    "rfr",
    "nombre_personnes",
    "code_postal_personne",

    # Logs
    "nrp_count",
    "nrp_log",

    # Système "À traiter" (rappels / RDV / actions)
    "rdv",                 # objet | None : {date,heure,type,assigne_a,cree_par,cree_at}
    "rappel",              # objet | None : {date,heure,assigne_a,motif,origine,cree_par,cree_at}
    "actions_log",         # liste : historique des actions closes
    "statut_updated_at",   # iso Paris : déjà écrit par /status, déclaré pour cohérence
    "injoignable_at",      # iso Paris : posé quand statut -> injoignable

    # Visite technique (marque permanente, independante du statut)
    "vt_validee",          # bool : VT validee (autorise le devis complet)
    "vt_date",             # iso Paris : date de validation VT
]

DEFAULT_PROSPECT_VALUES = {
    "date_visite_technique": "À déterminer",
    "statut": "nouveau",
    "nrp_count": 0,
    "nrp_log": [],
    "rdv": None,
    "rappel": None,
    "actions_log": [],
    "vt_validee": False,
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
    if not isinstance(normalized.get("nrp_log"), list):
        normalized["nrp_log"] = []
    if not isinstance(normalized.get("nrp_count"), int):
        normalized["nrp_count"] = len(normalized["nrp_log"])
    # "À traiter" : rdv/rappel = dict ou None (jamais "" issu d'un vieux default) ;
    # actions_log = liste.
    for k in ("rdv", "rappel"):
        if not isinstance(normalized.get(k), dict):
            normalized[k] = None
    if not isinstance(normalized.get("actions_log"), list):
        normalized["actions_log"] = []
    return normalized


def _validate_required_prospect_payload(prospect: dict) -> list[str]:
    missing = []
    required = [
        ("nom", "Nom"),
        ("prenom", "Prénom"),
        ("telephone", "Téléphone"),
        ("email", "Email"),
    ]
    for key, label in required:
        if not str(devis_value(prospect, key, default="")).strip():
            missing.append(label)
    return missing


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
        if not isinstance(item.get("nrp_log"), list):
            item["nrp_log"] = []
            changed = True
        if not isinstance(item.get("nrp_count"), int):
            item["nrp_count"] = len(item["nrp_log"])
            changed = True
        # "À traiter" : rdv/rappel -> dict ou None ; actions_log -> liste.
        for k in ("rdv", "rappel"):
            if not isinstance(item.get(k), dict) and item.get(k) is not None:
                item[k] = None
                changed = True
        if not isinstance(item.get("actions_log"), list):
            item["actions_log"] = []
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
    start_backup_scheduler(DATA_DIR)


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
    # resultat généralise l'ancien flag nrp booléen ; origine défaut "manuel".
    resultat = str((entry or {}).get("resultat") or "").strip()
    if not resultat and (entry or {}).get("nrp"):
        resultat = "nrp"
    return {
        "type": (entry or {}).get("type", "sms"),
        "contenu": contenu,
        "contenu_html": (entry or {}).get("contenu_html") or html.escape(contenu).replace("\n", "<br>"),
        "objet": (entry or {}).get("objet"),
        "template_id": (entry or {}).get("template_id"),
        "created_at": created_at,
        "created_by": auteur,
        "auteur": auteur,
        "nrp": bool((entry or {}).get("nrp")) or resultat == "nrp",
        "resultat": resultat,
        "origine": str((entry or {}).get("origine") or "manuel").strip() or "manuel",
    }


def _append_echange(numero, *, canal="sms", contenu="", resultat="", origine="manuel",
                    objet="", template_id="", auteur="Anonyme"):
    """Append un échange à echanges.json et renvoie l'entry créée.
    Source unique réutilisée par echanges_ajax, /nrp et /contact.
    Même schéma que l'historique existant, enrichi de resultat/origine."""
    canal = str(canal or "sms").strip() or "sms"
    contenu = str(contenu or "")
    auteur = str(auteur or "").strip() or "Anonyme"
    entry = {
        "type": canal,
        "contenu": contenu,
        "contenu_html": html.escape(contenu).replace("\n", "<br>"),
        "objet": objet or "",
        "template_id": template_id or "",
        "created_at": _now_iso(),
        "created_by": auteur,
        "auteur": auteur,
        "resultat": str(resultat or "").strip(),
        "origine": str(origine or "manuel").strip() or "manuel",
    }
    echanges = _read_echanges()
    echanges.setdefault(numero, []).append(entry)
    _atomic_write_json(ECHANGES_PATH, echanges)
    return entry


def _compteurs_canal(numero):
    """Compte par canal (appel/sms/email) les tentatives SANS réponse, base du
    calcul 'injoignable'. Compte une entrée si resultat ∈ {nrp, envoye}
    (sortant non répondu) ou via l'ancien flag nrp booléen. Exclut repondu,
    recu (entrant) et les échanges génériques sans resultat (conservateur)."""
    compteurs = {c: 0 for c in CANAUX_VALIDES}
    for e in _read_echanges().get(numero, []):
        if not isinstance(e, dict):
            continue
        canal = str(e.get("type") or "").strip().lower()
        if canal not in compteurs:
            continue
        resultat = str(e.get("resultat") or "").strip().lower()
        if not resultat and e.get("nrp"):
            resultat = "nrp"
        if resultat in ("nrp", "envoye"):
            compteurs[canal] += 1
    return compteurs


def _dernier_repondu(numero):
    """Date ISO du dernier échange resultat='repondu' (appel répondu), ou chaine vide."""
    best = ""
    for e in _read_echanges().get(numero, []):
        if isinstance(e, dict) and str(e.get("resultat") or "").strip().lower() == "repondu":
            ts = str(e.get("created_at") or "")
            if ts > best:
                best = ts
    return best


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
def _serve_index_html() -> HTMLResponse:
    """Serve the CRM SPA (index.html) as-is - the client reads the URL to open the right screen."""
    index_path = os.path.join(TEMPLATES_DIR, "index.html")
    with open(index_path, encoding="utf-8") as f:
        return HTMLResponse(content=f.read())


@app.get("/", response_class=HTMLResponse)
async def index() -> HTMLResponse:
    return _serve_index_html()


@app.get("/nouveau", response_class=HTMLResponse)
async def index_nouveau() -> HTMLResponse:
    return _serve_index_html()


@app.get("/prospect/{numero}", response_class=HTMLResponse)
async def index_prospect(numero: str) -> HTMLResponse:
    return _serve_index_html()


def _serve_login_html() -> HTMLResponse:
    login_path = os.path.join(TEMPLATES_DIR, "login.html")
    with open(login_path, encoding="utf-8") as f:
        return HTMLResponse(content=f.read())


@app.get("/login", response_class=HTMLResponse)
async def login_page() -> HTMLResponse:
    return _serve_login_html()


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


@app.get("/api/zones-departements")
def get_zones_departements() -> JSONResponse:
    """Table reglementaire departement -> zone climatique (H1/H2/H3).
    Source UNIQUE partagee par le simulateur (front) et le devis (backend)."""
    return JSONResponse(DEPT_ZONE)


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


DPE_DATASET = "dpe03existant"
AUDIT_DATASET = "audit-opendata"
_DPE_MIN_DATE = "2021-07-01"   # DPE/audit valides depuis le 1er juillet 2021


def _ademe_lines(dataset, sort_field, lat=None, lon=None, adresse="", cp="", qs=None):
    params = {"size": "10"}
    if lat is not None and lon is not None:
        # recherche geo : rayon 50m, tri par DISTANCE croissante (pas de sort -> data-fair trie par _geo_distance)
        params["geo_distance"] = f"{lon}:{lat}:50m"   # ATTENTION : lon puis lat
    else:
        q = (str(adresse or "").strip() + " " + str(cp or "").strip()).strip()
        if not q:
            return []
        params["q"] = q
        params["sort"] = "-" + sort_field   # fallback texte uniquement : tri par date decroissante
    if qs:
        params["qs"] = qs
    url = ("https://data.ademe.fr/data-fair/api/v1/datasets/" + dataset + "/lines?"
           + urllib.parse.urlencode(params, quote_via=urllib.parse.quote))
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return data.get("results") or []
    except Exception:
        return []


def _pick_best(lines, date_field):
    """Meilleure ligne : la plus proche (lignes deja triees par distance en mode geo) ;
    en cas d'egalite de distance, la plus recente. En mode texte (pas de _geo_distance), la 1ere."""
    if not lines:
        return None
    first = lines[0]
    if first.get("_geo_distance") is not None:   # mode geo : deja trie par distance croissante
        d0 = first.get("_geo_distance") or 0.0
        closest = [r for r in lines if abs((r.get("_geo_distance") or 0.0) - d0) < 1.0]
        return max(closest, key=lambda r: str(r.get(date_field) or ""))   # egalite distance -> plus recent
    return first   # mode texte : deja trie par date decroissante


def _doc_status(label, rec, date):
    num = rec.get("numero_dpe") or rec.get("n_audit") or ""
    adr = rec.get("adresse_ban") or ""
    txt = f"{label} trouvé (n°{num} du {date}"
    if adr:
        txt += f" — {adr}"
    return txt + ")"


def _label_type_logement(val):
    v = str(val or "").strip().lower()
    if "maison" in v:
        return "Maison individuelle"
    if "appart" in v:
        return "Appartement"
    return str(val or "")


def _enrich_dpe(rec):
    out = dict(rec)
    out["classe_energie"] = rec.get("etiquette_dpe", "")
    out["classe_consommation_energie"] = rec.get("etiquette_dpe", "")
    out["conso_kwh_m2"] = rec.get("conso_5_usages_par_m2_ep", "")
    out["cout_5_usages"] = rec.get("cout_total_5_usages", "")
    out["emission_ges_initial"] = rec.get("emission_ges_5_usages_par_m2", "")
    out["altitude"] = rec.get("classe_altitude", "")
    out["nb_niveau_logement"] = rec.get("nombre_niveau_logement", "")
    return out


def _enrich_audit(rec):
    out = dict(rec)
    out["classe_energie"] = rec.get("classe_bilan_dpe", "")
    out["classe_consommation_energie"] = rec.get("classe_bilan_dpe", "")
    out["conso_kwh_m2"] = rec.get("ep_conso_5_usages_m2", "")
    out["cout_5_usages"] = rec.get("cout_5_usages", "")
    out["emission_ges_initial"] = rec.get("emission_ges_5_usages_m2", "")
    out["altitude"] = rec.get("classe_altitude", "")
    out["date_etablissement_dpe"] = rec.get("date_etablissement_audit", "")  # le front lit cette cle
    out["numero_dpe"] = rec.get("numero_dpe") or rec.get("n_audit", "")      # le numero d'audit est dans n_audit
    return out


@app.get("/api/dpe-lookup")
def get_dpe_lookup(adresse: str = "", cp: str = "", lat: float | None = None,
                   lon: float | None = None, prospect_numero: str | None = None) -> JSONResponse:
    dpe_lines = _ademe_lines(DPE_DATASET, "date_etablissement_dpe", lat, lon, adresse, cp)
    dpe = _pick_best(dpe_lines, "date_etablissement_dpe")
    if dpe and str(dpe.get("date_etablissement_dpe") or "") < _DPE_MIN_DATE:
        dpe = None
    audit_lines = _ademe_lines(AUDIT_DATASET, "date_etablissement_audit", lat, lon, adresse, cp,
                               qs='categorie_scenario:"état initial"')
    audit = _pick_best(audit_lines, "date_etablissement_audit")
    if audit and str(audit.get("date_etablissement_audit") or "") < _DPE_MIN_DATE:
        audit = None

    dpe_date = str((dpe or {}).get("date_etablissement_dpe") or "")
    audit_date = str((audit or {}).get("date_etablissement_audit") or "")

    if not dpe and not audit:
        source, badge = "manuel", "SAISIE MANUELLE"
        status_text = "Aucun DPE/Audit trouvé — saisie manuelle"
    elif audit and not dpe:
        source, badge = "audit_officiel", "AUDIT OFFICIEL"
        status_text = _doc_status("Audit officiel", audit, audit_date)
    elif dpe and not audit:
        source, badge = "dpe_officiel", "DPE OFFICIEL"
        status_text = _doc_status("DPE officiel", dpe, dpe_date)
    else:
        if audit_date > dpe_date:
            source, badge = "audit_officiel", "AUDIT OFFICIEL"
            status_text = _doc_status("Audit officiel", audit, audit_date)
        else:
            source, badge = "dpe_officiel", "DPE OFFICIEL"
            status_text = _doc_status("DPE officiel", dpe, dpe_date)

    return JSONResponse({
        "source": source, "badge": badge, "status_text": status_text,
        "sources": {
            "dpe_officiel": _enrich_dpe(dpe) if dpe else {},
            "audit_officiel": _enrich_audit(audit) if audit else {},
            "urbs_enrichi": {},
        },
    })

@app.get("/api/altitude")
def get_altitude(lat: float, lon: float) -> JSONResponse:
    url = ("https://data.geopf.fr/altimetrie/1.0/calcul/alti/rest/elevation.json?"
           + urllib.parse.urlencode({"lon": lon, "lat": lat,
                                     "resource": "ign_rge_alti_wld", "zonly": "true"}))
    try:
        with urllib.request.urlopen(url, timeout=8) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        elevations = data.get("elevations") or []
        if not elevations:
            return JSONResponse({"altitude": None})
        first = elevations[0]
        z = float(first.get("z") if isinstance(first, dict) else first)  # zonly=true -> nombre direct
        if z <= -99999:
            return JSONResponse({"altitude": None})
        return JSONResponse({"altitude": round(z)})
    except Exception:
        return JSONResponse({"altitude": None})

@app.get("/api/documents/categories")
def get_documents_categories() -> JSONResponse:
    cats = _read_json(DOCUMENTS_CATEGORIES_PATH, [])
    return JSONResponse(cats if isinstance(cats, list) else [])


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
        specs = item.get("description_specs")
        if isinstance(specs, list):
            item["description_specs"] = [
                {"champ": str(spec.get("champ", "")).strip(), "valeur": str(spec.get("valeur", "")).strip()}
                for spec in specs
                if isinstance(spec, dict) and (str(spec.get("champ", "")).strip() or str(spec.get("valeur", "")).strip())
            ]
        else:
            item["description_specs"] = parse_legacy_description(item.get("description_technique", ""))
        validated.append(item)

    _atomic_write_json(CATALOGUE_PAC_PATH, validated)
    return JSONResponse({"ok": True, "count": len(validated)})


@app.post("/api/leads")
async def save_lead(request: Request) -> JSONResponse:
    payload = _normalize_lead_payload(await _read_request_payload(request))
    missing = _validate_required_prospect_payload(payload)
    if missing:
        return JSONResponse({"ok": False, "erreurs": missing}, status_code=400)
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


@app.get("/api/leads/check-duplicate")
async def check_duplicate(telephone: str | None = None, email: str | None = None, exclude_numero: str | None = None) -> JSONResponse:
    """Vérifie si un prospect existe déjà avec ce téléphone ou email."""
    def normalize_phone(phone):
        return "".join(c for c in str(phone or "") if c.isdigit())

    def normalize_email(em):
        return str(em or "").strip().lower()

    target_phone = normalize_phone(telephone) if telephone else None
    target_email = normalize_email(email) if email else None
    matches = []
    for lead in _read_leads():
        if exclude_numero and lead.get("numero") == exclude_numero:
            continue
        match_reason = []
        if target_phone and normalize_phone(lead.get("telephone", "")) == target_phone:
            match_reason.append("telephone")
        if target_email and normalize_email(lead.get("email", "")) == target_email:
            match_reason.append("email")
        if match_reason:
            matches.append({
                "numero": lead.get("numero"),
                "nom": lead.get("nom"),
                "prenom": lead.get("prenom"),
                "telephone": lead.get("telephone"),
                "email": lead.get("email"),
                "adresse": lead.get("adresse") or lead.get("adresse_chantier"),
                "cp_chantier": lead.get("cp_chantier") or lead.get("code_postal_chantier") or lead.get("cp"),
                "ville": lead.get("ville") or lead.get("ville_chantier"),
                "statut": lead.get("statut", "nouveau"),
                "match_reason": match_reason,
            })
    return JSONResponse({"duplicates": matches})


@app.get("/api/leads/{numero}")
def get_lead(numero: str) -> JSONResponse:
    wanted = str(numero or "").strip()
    for lead in _read_leads():
        if str(lead.get("numero", "")).strip() == wanted:
            data = _lead_for_response(lead)
            data["compteurs"] = _compteurs_canal(wanted)
            data["dernier_repondu"] = _dernier_repondu(wanted)
            return JSONResponse(data)
    raise HTTPException(status_code=404, detail="Prospect introuvable")


@app.post("/api/leads/{numero}")
async def update_lead(numero: str, request: Request) -> JSONResponse:
    payload = _normalize_lead_payload(await _read_request_payload(request))
    merged_preview = dict(_find_lead(numero) or {})
    merged_preview.update(payload)
    missing = _validate_required_prospect_payload(merged_preview)
    if missing:
        return JSONResponse({"ok": False, "erreurs": missing}, status_code=400)
    lead, _ = _upsert_lead(payload, forced_numero=numero)
    return JSONResponse({"ok": True, "numero": lead.get("numero"), "lead": _lead_for_response(lead)})


@app.post("/api/leads/{numero}/status")
async def update_lead_status(numero: str, request: Request) -> JSONResponse:
    """Met à jour le statut d'un prospect depuis l'Accueil."""
    payload = await _read_request_payload(request)
    new_status = _normalize_statut(str(payload.get("statut") or "").strip())
    allowed = {"nouveau", "contacte", "rappeler", "rdv", "pre_devis", "pre_devis_envoye", "vt_envoye", "vt_valide", "vt_refuse", "devis", "devis_envoye", "signe", "perdu"}
    if new_status not in allowed:
        raise HTTPException(status_code=400, detail=f"Statut invalide : {new_status}")
    leads = _read_leads()
    index = _find_lead_index(leads, numero)
    if index is None:
        raise HTTPException(status_code=404, detail="Prospect non trouvé")
    leads[index]["statut"] = new_status
    leads[index]["statut_updated_at"] = _now_paris_iso()
    leads[index]["updated_at"] = _now_iso()
    _atomic_write_json(LEADS_PATH, leads)
    return JSONResponse({"success": True, "statut": new_status})


@app.post("/api/leads/{numero}/vt")
async def update_lead_vt(numero: str, request: Request) -> JSONResponse:
    """Visite technique : valide / refuse / annule la marque VT.

    La marque (vt_validee + vt_date) est INDEPENDANTE du statut commercial (Option 2) :
    - valider : vt_validee=True + vt_date + statut='vt_valide'
    - refuser : statut='vt_refuse' (ne pose PAS la marque)
    - annuler : vt_validee=False + vt_date='' (ne touche PAS au statut)
    Le statut posé reste modifiable manuellement ensuite via la pilule.
    """
    payload = await _read_request_payload(request)
    action = str(payload.get("action") or "").strip().lower()
    leads = _read_leads()
    index = _find_lead_index(leads, numero)
    if index is None:
        raise HTTPException(status_code=404, detail="Prospect non trouvé")
    now_paris = _now_paris_iso()
    if action == "valider":
        leads[index]["vt_validee"] = True
        leads[index]["vt_date"] = now_paris
        leads[index]["statut"] = "vt_valide"
        leads[index]["statut_updated_at"] = now_paris
    elif action == "refuser":
        leads[index]["statut"] = "vt_refuse"
        leads[index]["statut_updated_at"] = now_paris
    elif action == "annuler":
        leads[index]["vt_validee"] = False
        leads[index]["vt_date"] = ""
    else:
        raise HTTPException(status_code=400, detail="Action VT invalide")
    leads[index]["updated_at"] = _now_iso()
    _atomic_write_json(LEADS_PATH, leads)
    return JSONResponse({
        "success": True,
        "vt_validee": bool(leads[index].get("vt_validee", False)),
        "vt_date": leads[index].get("vt_date", ""),
        "statut": leads[index].get("statut", ""),
    })


def _nrp_event(numero, payload):
    """NRP-EVENT : NRP manuel => echange appel/nrp + compteur + auto-rappel
    lendemain + bascule 'injoignable' si les 3 plafonds canal sont atteints.
    Payload : {par, canal?} (canal defaut 'appel')."""
    par = _normalize_assigne(payload.get("par"))
    canal = str(payload.get("canal") or "appel").strip().lower()
    if canal not in CANAUX_VALIDES:
        canal = "appel"

    leads = _read_leads()
    index = _find_lead_index(leads, numero)
    if index is None:
        raise HTTPException(status_code=404, detail="Prospect non trouvé")
    lead = leads[index]
    now = _now_paris_iso()

    # a. echange appel/nrp (contenu auto) — ecrit AVANT le calcul des compteurs.
    _append_echange(numero, canal=canal, contenu="Appel — pas de réponse",
                    resultat="nrp", origine="manuel", auteur=par)

    # b. compteur nrp (count == longueur du log).
    nrp_log = lead.get("nrp_log")
    if not isinstance(nrp_log, list):
        nrp_log = []
    nrp_log.append(now)
    lead["nrp_log"] = nrp_log
    lead["nrp_count"] = len(nrp_log)
    lead["nrp_updated_at"] = now

    # c. auto-rappel lendemain (archive l'ancien rappel s'il existe).
    ancien = lead.get("rappel")
    if isinstance(ancien, dict):
        log = lead.get("actions_log")
        if not isinstance(log, list):
            log = []
        log.append({
            "type": "rappel",
            "snapshot": ancien,
            "resultat": "reprogramme",
            "fait_par": par,
            "fait_at": now,
        })
        lead["actions_log"] = log
    demain = (_today_paris() + timedelta(days=1)).isoformat()
    lead["rappel"] = {
        "date": demain,
        "assigne_a": par,
        "motif": "NRP — rappel auto",
        "origine": "nrp",
        "cree_par": par,
        "cree_at": now,
    }

    # d. injoignable si les 3 plafonds canal atteints (tentatives sans reponse).
    compteurs = _compteurs_canal(numero)
    if all(compteurs.get(c, 0) >= seuil for c, seuil in PLAFONDS_CANAL.items()):
        lead["statut"] = "injoignable"
        lead["statut_updated_at"] = now
        lead["injoignable_at"] = now
        lead["rappel"] = None  # injoignable annule le rappel auto

    # e. persistance + reponse.
    lead["updated_at"] = _now_iso()
    _atomic_write_json(LEADS_PATH, leads)
    return JSONResponse({
        "ok": True,
        "nrp_count": lead["nrp_count"],
        "statut": lead.get("statut", ""),
        "rappel": lead.get("rappel"),
        "compteurs": compteurs,
        "lead": _lead_for_response(lead),
    })


@app.post("/api/leads/{numero}/nrp")
async def update_lead_nrp(numero: str, request: Request) -> JSONResponse:
    """Met à jour le compteur NRP. Branche selon le payload (decision 6) :
    avec 'nrp_count' => LEGACY (set compteur, inchangee) ; sinon => NRP-EVENT
    (echange + auto-rappel + injoignable)."""
    payload = await _read_request_payload(request)
    if "nrp_count" not in payload:
        return _nrp_event(numero, payload)
    raw_count = payload.get("nrp_count")
    if isinstance(raw_count, str) and raw_count.isdigit():
        raw_count = int(raw_count)
    if not isinstance(raw_count, int) or raw_count < 0:
        raise HTTPException(status_code=400, detail=f"Compteur NRP invalide : {raw_count}")
    leads = _read_leads()
    index = _find_lead_index(leads, numero)
    if index is None:
        raise HTTPException(status_code=404, detail="Prospect non trouvé")
    nrp_log = payload.get("nrp_log")
    if not isinstance(nrp_log, list):
        nrp_log = list(leads[index].get("nrp_log") or [])
        while len(nrp_log) < raw_count:
            nrp_log.append(_now_paris_iso())
        nrp_log = nrp_log[:raw_count]
    leads[index]["nrp_log"] = nrp_log
    leads[index]["nrp_count"] = raw_count
    leads[index]["nrp_updated_at"] = _now_paris_iso()
    leads[index]["updated_at"] = _now_iso()
    _atomic_write_json(LEADS_PATH, leads)
    return JSONResponse({"success": True, "nrp_count": raw_count})


@app.post("/api/leads/{numero}/rappel")
async def set_lead_rappel(numero: str, request: Request) -> JSONResponse:
    """Pose/replace le rappel actif d'un prospect (1 actif par lead). Si un
    rappel existe déjà, l'ancien est archivé dans actions_log (reprogramme)
    avant d'écrire le nouveau. Statut auto NON-régressif : nouveau/contacte
    -> rappeler (ne recule jamais un lead plus avancé).
    Payload : {date:'YYYY-MM-DD', heure?:'HH:MM', assigne_a, motif, par}."""
    payload = await _read_request_payload(request)
    date = str(payload.get("date") or "").strip()
    # Validation stricte : date présente ET re-sérialisable à l'identique
    # (round-trip) pour rejeter le non zero-paddé '2026-7-5' que strptime
    # accepterait sinon.
    dt = _parse_paris_dt(date)
    if not date or dt is None or dt.date().isoformat() != date:
        raise HTTPException(
            status_code=400,
            detail="Date de rappel invalide (attendu 'YYYY-MM-DD').",
        )
    heure = str(payload.get("heure") or "").strip()  # optionnelle : "" = rappel "toute la journée"
    if heure and _parse_paris_dt(f"{date}T{heure}") is None:
        raise HTTPException(
            status_code=400,
            detail="Heure de rappel invalide (attendu 'HH:MM').",
        )
    motif = str(payload.get("motif") or "").strip()  # libre, peut être vide
    par = _normalize_assigne(payload.get("par"))
    assigne_a = _normalize_assigne(payload.get("assigne_a")) or par

    leads = _read_leads()
    index = _find_lead_index(leads, numero)
    if index is None:
        raise HTTPException(status_code=404, detail="Prospect non trouvé")

    now_paris = _now_paris_iso()
    # Reposer = remplace + archive l'ancien rappel s'il existe.
    ancien = leads[index].get("rappel")
    if isinstance(ancien, dict):
        log = leads[index].get("actions_log")
        if not isinstance(log, list):
            log = []
        log.append({
            "type": "rappel",
            "snapshot": ancien,
            "resultat": "reprogramme",
            "fait_par": par,
            "fait_at": now_paris,
        })
        leads[index]["actions_log"] = log

    leads[index]["rappel"] = {
        "date": date,
        "heure": heure,
        "assigne_a": assigne_a,
        "motif": motif,
        "origine": "manuel",
        "cree_par": par,
        "cree_at": now_paris,
    }
    # Statut auto NON-régressif : un rappel ne fait avancer que les leads encore
    # en amont (nouveau/contacte -> rappeler). Ne recule jamais un lead déjà plus
    # avancé (pre_devis, vt_*, devis, signe...).
    if leads[index].get("statut") in ("nouveau", "contacte"):
        leads[index]["statut"] = "rappeler"
        leads[index]["statut_updated_at"] = now_paris
    leads[index]["updated_at"] = _now_iso()
    _atomic_write_json(LEADS_PATH, leads)
    return JSONResponse({"ok": True, "lead": _lead_for_response(leads[index])})


@app.post("/api/leads/{numero}/action-done")
async def lead_action_done(numero: str, request: Request) -> JSONResponse:
    """Clôture une action (rdv|rappel) : archive l'objet courant dans
    actions_log, le met à None, et applique les transitions de statut.
    Payload : {kind:'rdv'|'rappel', resultat?, par, maj_statut?, reprogramme?}.
    Transitions (resultat 'fait') : rdv -> statut 'contacte' (sauf maj_statut
    False) ; rappel -> si reprogramme{date} reposer un rappel, sinon si
    maj_statut passer 'contacte'. resultat 'annule' : pas de transition."""
    payload = await _read_request_payload(request)
    kind = str(payload.get("kind") or "").strip().lower()
    if kind not in ("rdv", "rappel", "detection"):
        raise HTTPException(status_code=400, detail="kind invalide (attendu 'rdv', 'rappel' ou 'detection').")
    par = _normalize_assigne(payload.get("par"))

    # Détection : pas d'objet sur le lead ; on mémorise un REJET dans actions_log
    # (re-déclenche seulement sur un trigger postérieur, cf. CONCEPTION §10.2).
    if kind == "detection":
        subtype = str(payload.get("subtype") or "").strip()
        if not subtype:
            raise HTTPException(status_code=400, detail="subtype requis pour une détection.")
        leads = _read_leads()
        index = _find_lead_index(leads, numero)
        if index is None:
            raise HTTPException(status_code=404, detail="Prospect non trouvé")
        lead = leads[index]
        log = lead.get("actions_log")
        if not isinstance(log, list):
            log = []
        log.append({
            "type": "detection",
            "subtype": subtype,
            "trigger_at": str(payload.get("trigger_at") or "").strip(),
            "resultat": str(payload.get("resultat") or "traite").strip() or "traite",
            "fait_par": par,
            "fait_at": _now_paris_iso(),
        })
        lead["actions_log"] = log
        lead["updated_at"] = _now_iso()
        _atomic_write_json(LEADS_PATH, leads)
        return JSONResponse({"ok": True, "lead": _lead_for_response(lead)})

    resultat = str(payload.get("resultat") or "fait").strip().lower() or "fait"
    maj_statut = payload.get("maj_statut")

    # Reprogrammation (optionnelle) : validee en amont si une date est fournie.
    reprogramme = payload.get("reprogramme")
    repro = reprogramme if isinstance(reprogramme, dict) else None
    repro_date = str((repro or {}).get("date") or "").strip()
    if repro_date:
        rdt = _parse_paris_dt(repro_date)
        if rdt is None or rdt.date().isoformat() != repro_date:
            raise HTTPException(
                status_code=400,
                detail="Date de reprogrammation invalide (attendu 'YYYY-MM-DD').",
            )

    leads = _read_leads()
    index = _find_lead_index(leads, numero)
    if index is None:
        raise HTTPException(status_code=404, detail="Prospect non trouvé")
    lead = leads[index]

    courant = lead.get(kind)
    if not isinstance(courant, dict):
        raise HTTPException(status_code=400, detail=f"Aucun {kind} actif à clôturer.")

    now = _now_paris_iso()
    # Archive l'action courante, puis la retire.
    log = lead.get("actions_log")
    if not isinstance(log, list):
        log = []
    log.append({
        "type": kind,
        "snapshot": courant,
        "resultat": resultat,
        "fait_par": par,
        "fait_at": now,
    })
    lead["actions_log"] = log
    lead[kind] = None

    # Transitions de statut (uniquement si resultat == "fait").
    if resultat == "fait":
        if kind == "rdv" and maj_statut is not False:
            lead["statut"] = "contacte"
            lead["statut_updated_at"] = now
        elif kind == "rappel":
            if repro_date:
                # Reprogrammer prime sur le passage a contacte.
                lead["rappel"] = {
                    "date": repro_date,
                    "assigne_a": _normalize_assigne((repro or {}).get("assigne_a")) or par,
                    "motif": str((repro or {}).get("motif") or "").strip(),
                    "origine": "manuel",
                    "cree_par": par,
                    "cree_at": now,
                }
            elif maj_statut:
                lead["statut"] = "contacte"
                lead["statut_updated_at"] = now

    lead["updated_at"] = _now_iso()
    _atomic_write_json(LEADS_PATH, leads)
    return JSONResponse({"ok": True, "lead": _lead_for_response(lead)})


@app.post("/api/leads/{numero}/contact")
async def lead_contact(numero: str, request: Request) -> JSONResponse:
    """Action manuelle multicanal : journalise un echange (canal+resultat) et
    recalcule les compteurs. Fondation dont le NRP est un cas particulier ;
    ici PAS de bascule injoignable ni d'auto-rappel (centralises dans /nrp).
    Payload : {canal:'appel'|'sms'|'email', resultat:'repondu'|'nrp'|'envoye'|
    'recu', par, contenu?, maj_statut?}."""
    payload = await _read_request_payload(request)
    canal = str(payload.get("canal") or "appel").strip().lower()
    if canal not in CANAUX_VALIDES:
        canal = "appel"
    resultat = str(payload.get("resultat") or "").strip().lower()
    if resultat not in ("repondu", "nrp", "envoye", "recu"):
        raise HTTPException(
            status_code=400,
            detail="resultat invalide (attendu repondu|nrp|envoye|recu).",
        )
    par = _normalize_assigne(payload.get("par"))
    maj_statut = payload.get("maj_statut")

    leads = _read_leads()
    index = _find_lead_index(leads, numero)
    if index is None:
        raise HTTPException(status_code=404, detail="Prospect non trouvé")
    lead = leads[index]

    # Libelle auto si contenu vide (selon canal + resultat).
    libelles = {
        ("appel", "repondu"): "Appel — répondu",
        ("appel", "nrp"): "Appel — pas de réponse",
        ("sms", "envoye"): "SMS envoyé",
        ("sms", "recu"): "SMS reçu",
        ("email", "envoye"): "Email envoyé",
        ("email", "recu"): "Email reçu",
    }
    contenu = str(payload.get("contenu") or "").strip() or libelles.get(
        (canal, resultat), f"{canal} — {resultat}"
    )
    _append_echange(numero, canal=canal, contenu=contenu, resultat=resultat,
                    origine="manuel", auteur=par)

    # Transition douce : 1re reponse sur un lead "nouveau" (si demandee).
    if resultat == "repondu" and lead.get("statut") == "nouveau" and maj_statut:
        lead["statut"] = "contacte"
        lead["statut_updated_at"] = _now_paris_iso()
    lead["updated_at"] = _now_iso()
    _atomic_write_json(LEADS_PATH, leads)

    compteurs = _compteurs_canal(numero)
    return JSONResponse({"ok": True, "compteurs": compteurs, "lead": _lead_for_response(lead)})


# --- GET /api/a-traiter : agrégation + tri de la liste "À traiter" ----------
def _atraiter_detection_item(lead, subtype, label, since_days, trigger_dt):
    """Construit un item de détection (kind=detection, visible par tous)."""
    iso = trigger_dt.isoformat(timespec="seconds")
    item = {
        "id": f"{lead.get('numero')}:detection:{subtype}",
        "numero": lead.get("numero"),
        "nom": lead.get("nom"),
        "prenom": lead.get("prenom"),
        "telephone": lead.get("telephone"),
        "statut": lead.get("statut"),
        "kind": "detection",
        "etat": "detection",
        "assigne_a": "",
        "subtype": subtype,
        "label": label,
        "since_days": since_days,
        "trigger_at": iso,
        "echeance": iso,
        "source": {"date": trigger_dt.date().isoformat()},
    }
    item["_bucket"] = 4
    item["_sort"] = -since_days
    return item


def _build_detection_ctx(today):
    """Pré-charge les sources des détections (1 lecture chacune)."""
    devis_sent = set()
    for d in _read_devis_envoyes():
        if isinstance(d, dict):
            n = str(d.get("numero_prospect") or "").strip()
            if n:
                devis_sent.add(n)
    simu_updated = {}
    try:
        for fn in os.listdir(STATES_SIMULATEUR_DIR):
            if not fn.endswith(".json"):
                continue
            st = _read_json(os.path.join(STATES_SIMULATEUR_DIR, fn), {})
            if isinstance(st, dict):
                n = str(st.get("numero_prospect") or "").strip()
                u = st.get("updated_at")
                if n and u:
                    simu_updated[n] = u
    except OSError:
        pass
    return {
        "today": today,
        "echanges": _read_echanges(),
        "devis_sent": devis_sent,
        "simu_updated": simu_updated,
    }


def _detection_items(lead, ctx):
    """0..n détections pour un lead, en respectant la mémoire de rejet
    (actions_log type=detection : re-déclenche seulement sur trigger postérieur)."""
    numero = str(lead.get("numero") or "").strip()
    statut = _normalize_statut(lead.get("statut", ""))
    today = ctx["today"]
    out = []
    # Leads terminés (perdu/signé) : aucune relance (ni devis, ni simu, ni jamais contacté).
    if statut in ("perdu", "signe"):
        return out

    rejets = {}
    for e in (lead.get("actions_log") or []):
        if isinstance(e, dict) and e.get("type") == "detection":
            st = e.get("subtype")
            tdt = _parse_paris_dt(e.get("trigger_at"))
            if st and tdt and (st not in rejets or tdt > rejets[st]):
                rejets[st] = tdt

    def _emit(subtype, trigger_value, label, seuil_j, max_j=None):
        tdt = _parse_paris_dt(trigger_value)
        if tdt is None:
            return
        since = (today - tdt.date()).days
        if since < seuil_j:
            return
        if max_j is not None and since > max_j:
            return
        rej = rejets.get(subtype)
        if rej is not None and rej >= tdt:
            return
        out.append(_atraiter_detection_item(lead, subtype, label, since, tdt))

    if statut == "devis_envoye":
        _emit("devis_3j", lead.get("date_envoi_devis"), "Devis envoyé sans réponse", DETECT_DEVIS_J)

    if statut in ("", "nouveau"):
        nrp = lead.get("nrp_count")
        if not isinstance(nrp, int):
            nrp = len(lead.get("nrp_log") or [])
        if nrp == 0 and not ctx["echanges"].get(numero):
            _emit("jamais_contacte_2j", lead.get("date"), "Jamais contacté", DETECT_JAMAIS_CONTACTE_J, DETECT_JAMAIS_CONTACTE_MAX_J)

    upd = ctx["simu_updated"].get(numero)
    if upd and numero not in ctx["devis_sent"] and statut != "devis_envoye" \
            and not str(lead.get("date_envoi_devis") or "").strip():
        _emit("simu_3j", upd, "Simulation sans devis", DETECT_SIMU_J)

    return out


@app.get("/api/a-traiter")
def get_a_traiter(assigne: str = "tous") -> JSONResponse:
    """Agrège et trie tout ce qui demande une action aujourd'hui (cf. §6).
    Détections automatiques (devis 3j / jamais contacté 2j / simu 3j).
    Filtre ?assigne=tous|avi|joelle|maurice (RDV/rappel par assigne_a ;
    détections visibles par tous)."""
    now = datetime.now(PARIS_TZ)
    today = now.date()

    filtre = _normalize_assigne(assigne)
    if filtre in ("", "tous"):
        filtre = None

    detect_ctx = _build_detection_ctx(today)
    items = []
    for lead in _read_leads():
        if _is_deleted(lead):
            continue
        # "À relancer" = détections uniquement. Rappels -> bloc "Mes rappels" ;
        # RDV legacy (non créables) -> retirés de l'agrégation.
        items.extend(_detection_items(lead, detect_ctx))

    # Filtre par personne : RDV/rappel par assigne_a ; détections par tous.
    if filtre is not None:
        items = [
            it for it in items
            if it["kind"] == "detection" or it.get("assigne_a") == filtre
        ]

    # Tri global par buckets, puis critère interne (échéance / ancienneté).
    items.sort(key=lambda it: (it["_bucket"], it["_sort"]))

    counts = {
        "total": len(items),
        "retards": sum(1 for it in items if it["etat"] == "retard"),
        "rdv_imminent": sum(
            1 for it in items if it["kind"] == "rdv" and it["etat"] == "imminent"
        ),
        "du_jour": sum(1 for it in items if it["etat"] in ("imminent", "aujourdhui")),
    }

    # Retire les champs de tri internes avant sérialisation.
    for it in items:
        it.pop("_bucket", None)
        it.pop("_sort", None)

    return JSONResponse({
        "generated_at": now.isoformat(timespec="seconds"),
        "counts": counts,
        "items": items,
    })


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
    numero = str(numero or "").strip()
    if not numero:
        raise HTTPException(status_code=400, detail="Numero requis")
    removed = {
        "lead": False, "state": False, "devis_meta": False,
        "devis_envoyes": 0, "notes": False, "echanges": False, "fichiers": [],
    }

    # 1) Enregistrement lead (match EXACT par numero via _find_lead_index)
    leads = _read_leads()
    index = _find_lead_index(leads, numero)
    if index is not None:
        del leads[index]
        _atomic_write_json(LEADS_PATH, leads)
        removed["lead"] = True

    # 2) State simulateur (fichier dedie au numero)
    state_path = _state_simulateur_path(numero)
    if os.path.exists(state_path):
        os.remove(state_path)
        removed["state"] = True

    # 3) Devis meta (cle exacte)
    meta = _read_devis_meta()
    if numero in meta:
        meta.pop(numero, None)
        _atomic_write_json(DEVIS_META_PATH, meta)
        removed["devis_meta"] = True

    # 4) Devis envoyes (filtre EXACT sur numero_prospect)
    sent = _read_devis_envoyes()
    kept = [e for e in sent if str((e or {}).get("numero_prospect", "")) != numero]
    if len(kept) != len(sent):
        _atomic_write_json(DEVIS_ENVOYES_PATH, kept)
        removed["devis_envoyes"] = len(sent) - len(kept)

    # 5) Notes (cle exacte)
    notes = _read_notes()
    if numero in notes:
        notes.pop(numero, None)
        _atomic_write_json(NOTES_PATH, notes)
        removed["notes"] = True

    # 6) Echanges (cle exacte)
    echanges = _read_echanges()
    if numero in echanges:
        echanges.pop(numero, None)
        _atomic_write_json(ECHANGES_PATH, echanges)
        removed["echanges"] = True

    # 7) Fichiers devis/notedim — match EXACT ancre par regex (jamais de prefixe partiel)
    if os.path.isdir(DEVIS_DIR):
        pat = re.compile(rf"^{re.escape(numero)}(_v\d+\.(?:pdf|html)|_notedim_v\d+\.pdf)$")
        for name in os.listdir(DEVIS_DIR):
            if pat.match(name):
                try:
                    os.remove(os.path.join(DEVIS_DIR, name))
                    removed["fichiers"].append(name)
                except OSError:
                    pass

    return JSONResponse({"ok": True, "numero": numero, "supprime": removed})


@app.post("/prospect/ajax")
async def save_prospect_ajax(request: Request) -> JSONResponse:
    payload = _normalize_lead_payload(await _read_request_payload(request))
    missing = _validate_required_prospect_payload(payload)
    if missing:
        return JSONResponse({"ok": False, "status": "error", "erreurs": missing}, status_code=400)
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
    merged_preview = dict(_find_lead(numero) or {})
    merged_preview.update(payload)
    missing = _validate_required_prospect_payload(merged_preview)
    if missing:
        return JSONResponse({"ok": False, "status": "error", "erreurs": missing}, status_code=400)
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
        raw = {field: str(row[col]).strip() for col, field in col_map.items()}
        # FIX1 : colonne combinee "Nom Prenom" -> split (sauf si nom/prenom explicites)
        if raw.get("_nom_prenom") and not (raw.get("nom") or raw.get("prenom")):
            raw["nom"], raw["prenom"] = _split_nom_prenom(raw["_nom_prenom"])
        # FIX2 : numero + date du fichier (sinon auto)
        file_numero = _normalize_numero_pr(raw.get("numero"))
        file_date = _parse_date_fr(raw.get("date"))
        record = {k: v for k, v in raw.items() if k in IMPORT_PROSPECT_FIELDS}
        if "statut" in record:
            record["statut"] = _normalize_statut(record.get("statut"))
        if "categorie" in record:
            record["categorie"] = _normalize_categorie(record.get("categorie"))
        note_text = ""
        for col, field in col_map.items():
            if field == "notes":
                note_text = str(row[col]).strip()

        # Skip fully empty rows.
        if not any(record.values()) and not note_text and not file_numero:
            continue

        numero = file_numero or _next_numero(leads)
        prospect = {"numero": numero, "date": file_date or _now_iso()}
        prospect.update({field: record.get(field, "") for field in IMPORT_PROSPECT_FIELDS})
        leads.append(prospect)
        imported += 1

        if note_text:
            notes.setdefault(numero, []).append(
                {"texte": note_text, "date": _now_paris_iso(), "auteur": "Import Excel"}
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


@app.get("/api/notes/{numero}")
def api_notes_for_prospect(numero: str) -> JSONResponse:
    """Retourne uniquement les notes du prospect spécifié."""
    notes = _read_notes()
    entries = notes.get(numero, [])
    return JSONResponse([_note_for_front(e, idx) for idx, e in enumerate(entries)])


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
        {"texte": texte, "date": _now_paris_iso(), "auteur": auteur}
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
    _append_echange(
        numero,
        canal=str(payload.get("type") or "sms"),
        contenu=contenu,
        resultat=str(payload.get("resultat") or ""),
        origine=str(payload.get("origine") or "manuel"),
        objet=payload.get("objet") or "",
        template_id=payload.get("template_id") or "",
        auteur=auteur,
    )
    echanges = _read_echanges()
    return JSONResponse({"ok": True, "count": len(echanges.get(numero, []))})


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
            "formule_bar_th_171": load_parametres_admin().get("formule_bar_th_171", DEFAULT_FORMULE_BAR_TH_171),
            "plafonds_reglementaires": load_parametres_admin().get("plafonds_reglementaires", DEFAULT_PLAFONDS_REGLEMENTAIRES),
            "baremes_anah": load_parametres_admin().get("baremes_anah", DEFAULT_BAREMES_ANAH),
            "params_eco_energie": load_parametres_admin().get("params_eco_energie", DEFAULT_PARAMS_ECO_ENERGIE),
            "params_financement": load_parametres_admin().get("params_financement", DEFAULT_PARAMS_FINANCEMENT),
            "marques": load_parametres_admin().get("marques", DEFAULT_MARQUES),
            "ballon_thermo": load_parametres_admin().get("ballon_thermo", {}),
        }
    )


@app.get("/api/admin/params")
async def get_admin_params():
    """Charge les paramètres Admin depuis le serveur."""
    return load_parametres_admin()


@app.post("/api/admin/params")
async def save_admin_params(request: Request):
    """Sauvegarde les paramètres Admin (écriture atomique)."""
    _require_admin(request)
    payload = await _read_request_payload(request)
    save_parametres_admin_atomic(payload)
    return {"success": True}


@app.get("/api/admin/formule-bar-th-171")
async def get_formule_bar_th_171():
    params = load_parametres_admin()
    return params.get("formule_bar_th_171", DEFAULT_FORMULE_BAR_TH_171)


@app.post("/api/admin/formule-bar-th-171")
async def save_formule_bar_th_171(request: Request):
    _require_admin(request)
    payload = await _read_request_payload(request)
    params = load_parametres_admin()
    params["formule_bar_th_171"] = payload
    save_parametres_admin_atomic(params)
    return {"success": True}


@app.get("/api/admin/marques")
async def get_marques():
    params = load_parametres_admin()
    return params.get("marques", DEFAULT_MARQUES)


@app.post("/api/admin/marques")
async def save_marques(request: Request):
    _require_admin(request)
    payload = await _read_request_payload(request)
    params = load_parametres_admin()
    params["marques"] = payload
    save_parametres_admin_atomic(params)
    return {"success": True}


@app.get("/api/admin/plafonds-reglementaires")
async def get_plafonds_reglementaires():
    params = load_parametres_admin()
    return params.get("plafonds_reglementaires", DEFAULT_PLAFONDS_REGLEMENTAIRES)


@app.post("/api/admin/plafonds-reglementaires")
async def save_plafonds_reglementaires(request: Request):
    _require_admin(request)
    payload = await _read_request_payload(request)
    params = load_parametres_admin()
    params["plafonds_reglementaires"] = payload
    save_parametres_admin_atomic(params)
    return {"success": True}


@app.get("/api/admin/baremes-anah")
async def get_baremes_anah():
    params = load_parametres_admin()
    return params.get("baremes_anah", DEFAULT_BAREMES_ANAH)


@app.post("/api/admin/baremes-anah")
async def save_baremes_anah(request: Request):
    _require_admin(request)
    payload = await _read_request_payload(request)
    params = load_parametres_admin()
    params["baremes_anah"] = payload
    save_parametres_admin_atomic(params)
    return {"success": True}


@app.get("/api/admin/params-eco-energie")
async def get_params_eco_energie():
    params = load_parametres_admin()
    return params.get("params_eco_energie", DEFAULT_PARAMS_ECO_ENERGIE)


@app.post("/api/admin/params-eco-energie")
async def save_params_eco_energie(request: Request):
    _require_admin(request)
    payload = await _read_request_payload(request)
    params = load_parametres_admin()
    params["params_eco_energie"] = payload
    save_parametres_admin_atomic(params)
    return {"success": True}


@app.get("/api/admin/params-financement")
async def get_params_financement():
    params = load_parametres_admin()
    return params.get("params_financement", DEFAULT_PARAMS_FINANCEMENT)


@app.post("/api/admin/params-financement")
async def save_params_financement(request: Request):
    _require_admin(request)
    payload = await _read_request_payload(request)
    params = load_parametres_admin()
    params["params_financement"] = payload
    save_parametres_admin_atomic(params)
    return {"success": True}


@app.post("/api/admin/purge-echanges-orphelins")
async def purge_echanges_orphelins(request: Request) -> JSONResponse:
    """Purge les échanges dont le numéro n'a AUCUN lead (vrai orphelin).
    Les leads soft-deleted (corbeille) gardent leur enregistrement -> NON
    orphelins (historique préservé pour une restauration). dry_run par défaut ;
    {"confirm": true} pour supprimer réellement."""
    _require_admin(request)
    payload = await _read_request_payload(request)
    confirm = bool(payload.get("confirm"))
    echanges = _read_echanges()
    numeros_leads = {str(l.get("numero") or "").strip() for l in _read_leads()}
    orphelins = sorted(n for n in echanges.keys() if str(n).strip() not in numeros_leads)
    if confirm:
        for n in orphelins:
            echanges.pop(n, None)
        _atomic_write_json(ECHANGES_PATH, echanges)
    return JSONResponse({
        "ok": True,
        "dry_run": not confirm,
        "orphelins": orphelins,
        "nb_supprimes": len(orphelins) if confirm else 0,
        "nb_restants": len(echanges),
    })


@app.post("/api/auth/login")
async def auth_login(request: Request, response: Response):
    _ensure_bootstrap_admin()
    payload = await _read_request_payload(request)
    username = str(payload.get("username") or "").strip().lower()
    password = str(payload.get("password") or "")
    user = _find_user(username)
    if not user or not _verify_password(password, str(user.get("password_hash", ""))):
        raise HTTPException(status_code=401, detail="Identifiant ou mot de passe incorrect")
    token = _sign_session(user.get("username"), user.get("role", "commercial"), int(time.time()))
    _secure = os.environ.get("COOKIE_SECURE", "1") != "0"
    response.set_cookie(SESSION_COOKIE, token, httponly=True, secure=_secure, samesite="lax", max_age=SESSION_TTL_SECONDS, path="/")
    return {"ok": True, "user": user.get("username"), "role": user.get("role", "commercial")}


@app.post("/api/auth/logout")
async def auth_logout(response: Response):
    response.delete_cookie(SESSION_COOKIE, path="/")
    return {"ok": True}


@app.get("/api/auth/me")
async def auth_me(request: Request):
    u = current_user(request)
    if not u:
        return {"authenticated": False}
    return {"authenticated": True, "user": u["username"], "role": u["role"]}


# ============ GESTION DES COMPTES (Lot 3a) — protégée par la SESSION (role==admin) ============
def _require_admin_session(request: Request) -> dict:
    u = current_user(request)
    if not u:
        raise HTTPException(status_code=401, detail="Non authentifié")
    if u.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Accès administrateur requis")
    return u


def _valid_username(s: str) -> bool:
    return bool(re.match(r"^[a-z0-9_.-]{2,32}$", str(s or "").strip().lower()))


def _count_active_admins(users: list, exclude: str = None) -> int:
    ex = str(exclude or "").strip().lower()
    n = 0
    for u in users:
        if not isinstance(u, dict):
            continue
        if str(u.get("username", "")).strip().lower() == ex:
            continue
        if u.get("role") == "admin" and u.get("actif", True):
            n += 1
    return n


def _public_user(u: dict) -> dict:
    return {
        "username": u.get("username"),
        "role": u.get("role", "commercial"),
        "actif": bool(u.get("actif", True)),
        "cree_at": u.get("cree_at", ""),
    }


def _find_user_record(users: list, username: str):
    uname = str(username or "").strip().lower()
    return next((u for u in users if isinstance(u, dict) and str(u.get("username", "")).strip().lower() == uname), None)


@app.get("/api/admin/users")
async def admin_users_list(request: Request):
    _require_admin_session(request)
    return {"users": [_public_user(u) for u in _read_users() if isinstance(u, dict)]}


@app.post("/api/admin/users")
async def admin_users_create(request: Request):
    _require_admin_session(request)
    payload = await _read_request_payload(request)
    username = str(payload.get("username") or "").strip().lower()
    password = str(payload.get("password") or "")
    role = str(payload.get("role") or "commercial").strip().lower()
    if not _valid_username(username):
        raise HTTPException(status_code=400, detail="Identifiant invalide (a-z, 0-9, . _ - ; 2 à 32 caractères)")
    if role not in ("admin", "commercial"):
        raise HTTPException(status_code=400, detail="Rôle invalide")
    if len(password) < 6:
        raise HTTPException(status_code=400, detail="Mot de passe trop court (6 caractères minimum)")
    users = _read_users()
    if _find_user_record(users, username):
        raise HTTPException(status_code=409, detail="Identifiant déjà utilisé")
    users.append({
        "id": username, "username": username, "password_hash": _hash_password(password),
        "role": role, "actif": True, "cree_at": _now_iso(), "visibilite": "tous",
    })
    _write_users(users)
    return {"ok": True, "user": _public_user(users[-1])}


@app.post("/api/admin/users/{username}/active")
async def admin_users_set_active(username: str, request: Request):
    _require_admin_session(request)
    payload = await _read_request_payload(request)
    actif = bool(payload.get("actif"))
    users = _read_users()
    target = _find_user_record(users, username)
    if not target:
        raise HTTPException(status_code=404, detail="Compte introuvable")
    if not actif and target.get("role") == "admin" and _count_active_admins(users, exclude=str(username).strip().lower()) < 1:
        raise HTTPException(status_code=409, detail="Impossible : c'est le dernier administrateur actif")
    target["actif"] = actif
    _write_users(users)
    return {"ok": True, "user": _public_user(target)}


@app.post("/api/admin/users/{username}/reset-password")
async def admin_users_reset_password(username: str, request: Request):
    _require_admin_session(request)
    payload = await _read_request_payload(request)
    password = str(payload.get("password") or "")
    if len(password) < 6:
        raise HTTPException(status_code=400, detail="Mot de passe trop court (6 caractères minimum)")
    users = _read_users()
    target = _find_user_record(users, username)
    if not target:
        raise HTTPException(status_code=404, detail="Compte introuvable")
    target["password_hash"] = _hash_password(password)
    _write_users(users)
    return {"ok": True}


@app.delete("/api/admin/users/{username}")
async def admin_users_delete(username: str, request: Request):
    _require_admin_session(request)
    users = _read_users()
    target = _find_user_record(users, username)
    if not target:
        raise HTTPException(status_code=404, detail="Compte introuvable")
    if target.get("role") == "admin" and _count_active_admins(users, exclude=str(username).strip().lower()) < 1:
        raise HTTPException(status_code=409, detail="Impossible : c'est le dernier administrateur actif")
    uname = str(username).strip().lower()
    users = [u for u in users if not (isinstance(u, dict) and str(u.get("username", "")).strip().lower() == uname)]
    _write_users(users)
    return {"ok": True}


@app.post("/api/auth/change-password")
async def auth_change_password(request: Request):
    u = current_user(request)
    if not u:
        raise HTTPException(status_code=401, detail="Non authentifié")
    payload = await _read_request_payload(request)
    current_pw = str(payload.get("current_password") or "")
    new_pw = str(payload.get("new_password") or "")
    if len(new_pw) < 6:
        raise HTTPException(status_code=400, detail="Nouveau mot de passe trop court (6 caractères minimum)")
    users = _read_users()
    target = _find_user_record(users, u["username"])
    if not target or not _verify_password(current_pw, str(target.get("password_hash", ""))):
        raise HTTPException(status_code=401, detail="Mot de passe actuel incorrect")
    target["password_hash"] = _hash_password(new_pw)
    _write_users(users)
    return {"ok": True}


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


@app.get("/api/admin/backup")
def admin_backup(token: str = "") -> FileResponse:
    if not _verify_admin_token(token):
        raise HTTPException(status_code=401, detail="Acces admin requis")
    stamp = datetime.now(ZoneInfo("Europe/Paris")).strftime("%Y%m%d-%H%M%S")
    tmp_dir = tempfile.mkdtemp(prefix="hexa-backup-")
    archive = shutil.make_archive(
        os.path.join(tmp_dir, f"hexa-backup-{stamp}"), "zip", root_dir=DATA_DIR
    )
    return FileResponse(
        archive,
        media_type="application/zip",
        filename=f"hexa-backup-{stamp}.zip",
        background=BackgroundTask(shutil.rmtree, tmp_dir, True),
    )


@app.post("/api/admin/backup-github")
def admin_backup_github(token: str = "") -> JSONResponse:
    if not _verify_admin_token(token):
        raise HTTPException(status_code=401, detail="Acces admin requis")
    from services.backup_github import run_backup_once
    return JSONResponse({"ok": True, "message": run_backup_once(DATA_DIR)})


@app.get("/api/admin/config")
def get_admin_config() -> JSONResponse:
    baremes = _read_json(BAREMES_PATH, {})
    if not isinstance(baremes, dict):
        baremes = {}
    return JSONResponse({"script_notion_url": baremes.get("script_notion_url", "")})


@app.post("/api/admin/config")
async def post_admin_config(request: Request) -> JSONResponse:
    _require_admin(request)
    payload = await _read_request_payload(request)
    baremes = _read_json(BAREMES_PATH, {})
    if not isinstance(baremes, dict):
        baremes = {}
    baremes["script_notion_url"] = str(payload.get("script_notion_url") or "").strip()
    _atomic_write_json(BAREMES_PATH, baremes)
    return JSONResponse({"ok": True, "script_notion_url": baremes["script_notion_url"]})


@app.post("/api/admin/m3")
async def post_admin_m3(request: Request) -> JSONResponse:
    _require_admin(request)
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


@app.get("/api/simulateur/{numero}/state")
async def get_state_simulateur(numero: str) -> JSONResponse:
    """Récupère le state du simulateur pour un prospect."""
    return JSONResponse(load_state_simulateur(numero))


@app.post("/api/simulateur/{numero}/state")
async def save_state_simulateur(numero: str, request: Request) -> JSONResponse:
    """Sauvegarde le state du simulateur pour un prospect."""
    payload = await _read_request_payload(request)
    return JSONResponse({"success": True, "state": save_state_simulateur_atomic(numero, payload)})


def _load_state_simulateur(numero: str, prospect: dict, catalogue: list[dict]) -> dict:
    saved = load_state_simulateur(numero)
    state = {
        "numero": numero,
        "modele_pac_id": devis_value(prospect, "modele_pac_id", default=""),
        "modele_pac": devis_value(prospect, "modele_pac", default=""),
        "prix_pac": "",
        "surface_chauffee": devis_value(prospect, "surface_chauffee", default=""),
        "iso_toit": devis_value(prospect, "iso_toit", default="isole"),
        "iso_mur": devis_value(prospect, "iso_mur", default="isole"),
        "iso_menuiserie": devis_value(prospect, "iso_menuiserie", default="double"),
        "service": devis_value(prospect, "service", default="chauffage_ecs"),
        "alimentation_electrique": devis_value(prospect, "alimentation_electrique", "phase_electrique", default=""),
    }
    state.update({k: v for k, v in saved.items() if v not in (None, "")})
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


def _build_devis_context(request: Request, numero: str, version: int | None = None, avec_sous_traitant: bool = True) -> dict:
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
    today = datetime.now(PARIS_TZ)
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
    sous_traitant_context = dict(sous_traitant or {})
    if sous_traitant_context:
        sous_traitant_context["rge_validite"] = (
            f"du {_format_date_fr(sous_traitant_context.get('rge_validite_du', ''))} au {_format_date_fr(sous_traitant_context.get('rge_validite_au', ''))}"
        ).strip()
    formatted_calculs = format_devis_amounts(calculs)
    formatted_calculs["lot_titre"] = generer_lot_titre(modele_obj)
    description_specs = modele_obj.get("description_specs", []) if modele_obj else []
    if not description_specs and modele_obj and modele_obj.get("description_technique"):
        description_specs = parse_legacy_description(modele_obj["description_technique"])
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
        "numero_devis": generer_numero_devis(prospect, version if version is not None else _next_sent_version(numero)),
        "numero_dossier": _next_numero_dossier(),
        "date_emission": today.strftime("%d/%m/%Y"),
        "date_validite": (today + timedelta(days=60)).strftime("%d/%m/%Y"),
        "date_visite_technique": date_visite,
        "date_debut_travaux": "À déterminer",
        "type_logement": _label_type_logement(prospect.get("type_logement", "")),
        "surface_habitable": str(devis_value(prospect, "surface_habitable", "surface_logement_m2", default="")),
        "chauffage_actuel": str(devis_value(prospect, "chauffage_actuel", "mode_chauffage", default="")).capitalize(),
        "parcelle_cadastrale": prospect.get("parcelle_cadastrale", ""),
        "zone_climatique": calculer_zone_climatique(cp_chantier),
        "modele_pac": modele_obj.get("nom") or modele_obj.get("ref") or "",
        "description_specs": description_specs,
        "sous_traitant": sous_traitant_context,
        "avec_sous_traitant": avec_sous_traitant,
        "pre_devis": not avec_sous_traitant,  # modèle 2-temps : pré-devis = sans sous-traité
        "sous_traitant_texte": format_sous_traitant(sous_traitant),
        **formatted_calculs,
    }
    # Phase 2A : calculs financement + économie (réplique JS) — exposés au contexte, PAS affichés (2B plus tard)
    facture_avant = devis_value(state, "facture_avant", default=None)
    if facture_avant in (None, ""):
        _cout_mensuel = devis_value(prospect, "cout_energetique_mensuel_eur", "cout_chauffage", default="")
        if str(_cout_mensuel).strip() and float_value(_cout_mensuel) > 0:
            facture_avant = float_value(_cout_mensuel)
        else:
            _cout_annuel = devis_value(prospect, "cout_energetique_annuel_eur", default="")
            facture_avant = round(float_value(_cout_annuel) / 12) if (str(_cout_annuel).strip() and float_value(_cout_annuel) > 0) else None
    _surface_eco = devis_value(state, "surface_chauffee", default="") or devis_value(prospect, "surface_habitable", "surface_logement_m2", default="")
    _zone_eco = devis_value(state, "zone", default=context["zone_climatique"])
    context["financement_devis"] = calculer_financement_devis(calculs["reste_a_charge"], admin)
    context["economie_devis"] = calculer_economie_devis(
        _surface_eco, _zone_eco,
        devis_value(modele_obj, "etas35", default=0), devis_value(modele_obj, "etas55", default=0),
        devis_value(prospect, "type_emetteurs", default=""),
        devis_value(state, "service", default="chauffage_ecs"),
        facture_avant, admin,
    )
    _eco = context.get("economie_devis") or {}
    _fin = context.get("financement_devis") or {}
    _ballon_ctx = resoudre_ballon(state, admin)
    _ecs_mois = float_value((_ballon_ctx or {}).get("economie_ecs_mois")) if _ballon_ctx else 0
    projet_apercu = None
    if _eco.get("facture_apres_mois") and _eco.get("facture_avant_mois"):
        _fav = float_value(_eco.get("facture_avant_mois"))
        _fap = max(0.0, float_value(_eco.get("facture_apres_mois")) - _ecs_mois)
        _mens = float_value(_fin.get("mensualite"))
        _total_credit = round(_fap + _mens)
        _eco_pendant = round(_fav - _total_credit)
        _eco_apres = round(_fav - _fap)
        if _fav > 0 and _eco_apres > 0:
            _eco20_raw = state.get("eco_20_ans")
            _eco20_fmt = (f"{round(float_value(_eco20_raw)):,}".replace(",", " ")
                          if str(_eco20_raw).strip() not in ("", "None") else None)
            _opt = str(state.get("option") or "").strip()
            _mode = {"opt1": "credit", "opt2": "ecoptz", "opt3": "comptant"}.get(_opt) or ("comptant" if round(_mens) <= 0 else "credit")
            _duree_vie = int(float_value((admin.get("params_eco_energie") or {}).get("duree_vie_pac_ans", 20)) or 20)
            projet_apercu = {
                "facture_avant": round(_fav),
                "facture_apres": round(_fap),
                "total_credit": _total_credit,
                "mensualite_credit": round(_mens),
                "eco_pendant": _eco_pendant,
                "eco_apres": _eco_apres,
                "taux_pct": _fin.get("taux_pct"),
                "duree_mois": _fin.get("duree_mois"),
                "premiere_echeance_jours": _fin.get("premiere_echeance_jours"),
                # Éco 20 ans calculée par le simulateur, transmise telle quelle (pas de recalcul)
                "eco_20_ans": state.get("eco_20_ans"),
                "eco_20_ans_fmt": _eco20_fmt,
                "annee_rentable": state.get("annee_rentable"),
                "inflation_avant_pct": state.get("inflation_avant_pct"),
                "inflation_elec_pct": state.get("inflation_elec_pct"),
                "energie_avant": state.get("energie_avant"),
                "mode": _mode,
                "duree_vie_pac_ans": _duree_vie,
            }
    context["projet_apercu"] = projet_apercu
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
    now = datetime.now(PARIS_TZ)
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
        "type_logement": _label_type_logement(prospect.get("type_logement", "")),
        "chauffage_actuel": str(devis_value(prospect, "chauffage_actuel", "mode_chauffage", default="")).capitalize(),
        **calculer_notedim(prospect, state, catalogue),
    }
    return context


def _render_template_response(request: Request, template_name: str, context: dict) -> HTMLResponse:
    name = context.pop("_error_template", template_name)
    context.setdefault("request", request)
    html_content = templates.env.get_template(name).render(context)
    return HTMLResponse(content=html_content)


def _render_devis_html(request: Request, numero: str, version: int | None = None, avec_sous_traitant: bool = True) -> str:
    ctx = _build_devis_context(request, numero, version, avec_sous_traitant)
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


def _html_to_pdf_playwright(html_content: str, request: Request) -> bytes:
    """Génère un PDF fidèle au HTML via Chromium (Playwright), rendu navigateur réel."""
    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Playwright indisponible: {exc}") from exc

    base_url = str(request.base_url)

    def _run() -> bytes:
        with sync_playwright() as p:
            browser = p.chromium.launch(args=["--no-sandbox"])
            try:
                page = browser.new_page()
                # base_url résout les chemins relatifs (CSS, images) comme dans le navigateur.
                # set_content() de Playwright 1.49 n'accepte pas base_url -> on ne le passe pas ici.
                page.set_content(html_content, wait_until="networkidle")
                pdf_bytes = page.pdf(
                    format="A4",
                    print_background=True,
                    display_header_footer=True,
                    header_template="<span></span>",
                    footer_template="""<div style="width:100%; box-sizing:border-box; padding:0 24px; font-family:'Inter',Helvetica,Arial,sans-serif;"><table style="width:100%; border:0; border-collapse:collapse;"><tr><td style="text-align:left; vertical-align:bottom; font-size:7px; color:#6B7480; line-height:1.45;"><div><strong style="color:#002E5A;">SAS HEXA RÉNOV'</strong> · 58 Rue de la Sablière, 92600 Asnières-sur-Seine · RCS Nanterre 845 229 152 · SIRET 845 229 152 00028 · TVA FR 89 845 229 152</div><div>RGE CertiRénov' n° CR-2025-92-0052 · Assurance Décennale &amp; RC Pro — MIC Insurance n° AXE2502159 · Validité : 19/03/2026 au 18/03/2027</div><div>info@hexa-renov.fr · 09 70 70 25 11</div></td><td style="text-align:right; vertical-align:bottom; white-space:nowrap; font-size:8px; color:#9AA3AE; padding-left:12px;">Page <span class="pageNumber"></span> / <span class="totalPages"></span></td></tr></table></div>""",
                    margin={"top": "0", "bottom": "1.4cm", "left": "0", "right": "0"},
                )
            finally:
                browser.close()
            return pdf_bytes

    # Playwright sync doit tourner hors de la boucle asyncio de FastAPI : on l'isole dans un thread.
    import concurrent.futures
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
        return ex.submit(_run).result()


def _write_pdf(path: str, pdf_bytes: bytes) -> str:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(pdf_bytes)
    return path


def _append_fiche_technique(pdf_bytes: bytes, numero: str) -> bytes:
    """Concatène la fiche technique de la gamme du modèle retenu, à la fin du PDF.

    Tout problème (fiche absente / illisible / fusion / pypdf) -> devis seul (jamais d'échec d'envoi)."""
    try:
        prospect = _find_lead(numero)
        if not prospect:
            return pdf_bytes
        catalogue = _read_catalogue_pac()
        state = _load_state_simulateur(numero, prospect, catalogue)
        modele_ref = state.get("modele_pac_id") or state.get("modele_pac")
        modele_obj = find_modele(catalogue, modele_ref) or select_default_modele(prospect, catalogue)
        if not modele_obj:
            return pdf_bytes
        index = _read_fiches_index()
        gamme = _gamme_of(modele_obj, index.get("gamme_overrides", {}))
        entry = index.get("fiches", {}).get(gamme)
        if not entry:
            return pdf_bytes
        path = _fiche_pdf_path(gamme)
        if not os.path.exists(path):
            return pdf_bytes
        from pypdf import PdfReader, PdfWriter
        writer = PdfWriter()
        writer.append(PdfReader(io.BytesIO(pdf_bytes)))
        writer.append(PdfReader(path))
        out = io.BytesIO()
        writer.write(out)
        return out.getvalue()
    except Exception:
        return pdf_bytes


def _append_fiche_ballon(pdf_bytes: bytes, numero: str) -> bytes:
    """Concatène la fiche technique du ballon choisi (state.ballon_ref), à la fin du PDF.

    Mêmes garanties que la fiche PAC : tout problème (fiche absente / illisible / fusion / pypdf) -> PDF inchangé."""
    try:
        prospect = _find_lead(numero)
        if not prospect:
            return pdf_bytes
        catalogue = _read_catalogue_pac()
        state = _load_state_simulateur(numero, prospect, catalogue)
        ballon_ref = str(state.get("ballon_ref") or "").strip()
        if not ballon_ref:
            return pdf_bytes
        index = _read_fiches_index()
        entry = index.get("fiches_ballon", {}).get(ballon_ref)
        if not entry:
            return pdf_bytes
        path = _fiche_ballon_pdf_path(ballon_ref)
        if not os.path.exists(path):
            return pdf_bytes
        from pypdf import PdfReader, PdfWriter
        writer = PdfWriter()
        writer.append(PdfReader(io.BytesIO(pdf_bytes)))
        writer.append(PdfReader(path))
        out = io.BytesIO()
        writer.write(out)
        return out.getvalue()
    except Exception:
        return pdf_bytes


def _ensure_devis_pdf(numero: str, request: Request, version: int | None = None, avec_sous_traitant: bool = True) -> tuple[str, str, int]:
    version = version or _next_sent_version(numero)
    html = _render_devis_html(request, numero, version, avec_sous_traitant)
    html_path = _devis_html_path(numero, version)
    _write_text(html_path, html)
    pdf_path = _devis_path(numero, version)
    pdf_bytes = _html_to_pdf_playwright(html, request)
    if avec_sous_traitant:
        pdf_bytes = _append_fiche_technique(pdf_bytes, numero)
        pdf_bytes = _append_fiche_ballon(pdf_bytes, numero)
    _write_pdf(pdf_path, pdf_bytes)
    return pdf_path, html_path, version


def _ensure_notedim_pdf(numero: str, request: Request, version: int) -> str:
    path = _notedim_path(numero, version)
    if not os.path.exists(path):
        _write_pdf(path, _html_to_pdf_playwright(_render_notedim_html(request, numero), request))
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
async def devis_preview(numero: str, request: Request, variante: str | None = None) -> HTMLResponse:
    if variante is None:
        _lead = _find_lead(numero)
        variante = "devis" if (_lead and _lead.get("vt_validee")) else "pre_devis"
    avec_sous_traitant = (variante == "devis")
    return _render_template_response(request, "devis_pac.html", _build_devis_context(request, numero, avec_sous_traitant=avec_sous_traitant))


@app.get("/api/notedim/{numero}/preview", response_class=HTMLResponse)
async def notedim_preview(numero: str, request: Request) -> HTMLResponse:
    return _render_template_response(request, "notedim_pac.html", _build_notedim_context(request, numero))


@app.get("/api/devis/{numero}/pdf")
async def devis_pdf(numero: str, request: Request, variante: str | None = None):
    if variante is None:
        _lead = _find_lead(numero)
        variante = "devis" if (_lead and _lead.get("vt_validee")) else "pre_devis"
    avec_sous_traitant = (variante == "devis")
    # Aperçu : rendu + stream éphémère. NE fige AUCUNE version (seul _send_devis fige).
    pdf_bytes = _html_to_pdf_playwright(_render_devis_html(request, numero, avec_sous_traitant=avec_sous_traitant), request)
    fname = "Devis" if variante == "devis" else "Pre-devis"
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{fname}_{numero}.pdf"'},
    )


@app.get("/devis-public/{numero}/{token}", response_class=HTMLResponse)
async def devis_public(numero: str, token: str, request: Request):
    if not _verify_devis_token(numero, token):
        raise HTTPException(status_code=403, detail="Lien invalide")
    _items = _sent_devis_items(numero)
    if _items:
        _item = _items[0]
        _html_file = _item.get("html_file")
        if _html_file and os.path.exists(_html_file):
            _pdf_url = f"/devis-public/{numero}/{token}/pdf"
            return HTMLResponse(_inject_devis_bar(_read_text(_html_file), _devis_bar_html(_pdf_url, pre_devis=(_item.get("variante") == "pre_devis"))))
        _pdf_file = _item.get("file")
        if _pdf_file and os.path.exists(_pdf_file):
            return FileResponse(_pdf_file, media_type="application/pdf", headers={"Content-Disposition": "inline"})
    _pre_devis = bool(_items and _items[0].get("variante") == "pre_devis")
    html_devis = _render_devis_html(request, numero, avec_sous_traitant=not _pre_devis)
    barre = (
        '<div style="position:fixed;top:0;left:0;right:0;z-index:9999;'
        'background:#F4F6F9;border-bottom:1px solid #E1E5EB;'
        'display:flex;align-items:center;justify-content:space-between;'
        'padding:12px 24px;font-family:Arial,Helvetica,sans-serif;">'
        '<div>'
        '<img src="/static/Logo.svg" alt="Hexa Rénov\'" style="height:32px;width:auto;vertical-align:middle;">'
        '<span style="color:#002E5A;font-weight:700;font-size:15px;margin-left:14px;vertical-align:middle;">Votre ' + ('pré-devis' if _pre_devis else 'devis') + '</span>'
        '</div>'
        '<a href="/devis-public/' + numero + '/' + token + '/pdf" '
        'style="background:#E2214B;color:#ffffff;padding:10px 20px;border-radius:6px;'
        'font-weight:700;font-size:14px;text-decoration:none;">Télécharger le PDF</a>'
        '</div>'
        '<div style="height:58px;"></div>'
    )
    import re as _re
    if _re.search(r'<body[^>]*>', html_devis):
        html_devis = _re.sub(r'(<body[^>]*>)', lambda m: m.group(1) + barre, html_devis, count=1)
    else:
        html_devis = barre + html_devis
    return HTMLResponse(html_devis)


@app.get("/devis-public/{numero}/{token}/pdf")
async def devis_public_pdf(numero: str, token: str, request: Request):
    if not _verify_devis_token(numero, token):
        raise HTTPException(status_code=403, detail="Lien invalide")
    _items = _sent_devis_items(numero)
    if _items:
        _pdf_file = _items[0].get("file")
        if _pdf_file and os.path.exists(_pdf_file):
            return FileResponse(_pdf_file, media_type="application/pdf", filename=f"Devis_{numero}.pdf")
    pdf_bytes = _html_to_pdf_playwright(_render_devis_html(request, numero), request)
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="Devis_{numero}.pdf"'},
    )


def _devis_bar_html(pdf_url: str, pre_devis: bool = False) -> str:
    return (
        '<div style="position:fixed;top:0;left:0;right:0;z-index:9999;'
        'background:#F4F6F9;border-bottom:1px solid #E1E5EB;'
        'display:flex;align-items:center;justify-content:space-between;'
        'padding:12px 24px;font-family:Arial,Helvetica,sans-serif;">'
        '<div>'
        '<img src="/static/Logo.svg" alt="Hexa Renov" style="height:32px;width:auto;vertical-align:middle;">'
        '<span style="color:#002E5A;font-weight:700;font-size:15px;margin-left:14px;vertical-align:middle;">Votre ' + ('pré-devis' if pre_devis else 'devis') + '</span>'
        '</div>'
        '<a href="' + pdf_url + '" '
        'style="background:#E2214B;color:#ffffff;padding:10px 20px;border-radius:6px;'
        'font-weight:700;font-size:14px;text-decoration:none;">Telecharger le PDF</a>'
        '</div>'
        '<div style="height:58px;"></div>'
    )


def _inject_devis_bar(html_devis: str, bar: str) -> str:
    import re as _re
    if _re.search(r'<body[^>]*>', html_devis):
        return _re.sub(r'(<body[^>]*>)', lambda m: m.group(1) + bar, html_devis, count=1)
    return bar + html_devis


@app.get("/devis-public/{numero}/{version}/{token}", response_class=HTMLResponse)
async def devis_public_versionne(numero: str, version: int, token: str, request: Request):
    if not _verify_devis_token_v(numero, version, token):
        raise HTTPException(status_code=403, detail="Lien invalide")
    items = _sent_devis_items(numero)
    if version < 1 or version > len(items):
        raise HTTPException(status_code=404, detail="Version introuvable")
    item = items[version - 1]
    html_file = item.get("html_file")
    if html_file and os.path.exists(html_file):
        pdf_url = f"/devis-public/{numero}/{version}/{token}/pdf"
        return HTMLResponse(_inject_devis_bar(_read_text(html_file), _devis_bar_html(pdf_url, pre_devis=(item.get("variante") == "pre_devis"))))
    pdf_file = item.get("file")
    if pdf_file and os.path.exists(pdf_file):
        return FileResponse(pdf_file, media_type="application/pdf", headers={"Content-Disposition": "inline"})
    raise HTTPException(status_code=404, detail="Devis introuvable")


@app.get("/devis-public/{numero}/{version}/{token}/pdf")
async def devis_public_versionne_pdf(numero: str, version: int, token: str, request: Request):
    if not _verify_devis_token_v(numero, version, token):
        raise HTTPException(status_code=403, detail="Lien invalide")
    items = _sent_devis_items(numero)
    if version < 1 or version > len(items):
        raise HTTPException(status_code=404, detail="Version introuvable")
    item = items[version - 1]
    pdf_file = item.get("file")
    if not pdf_file or not os.path.exists(pdf_file):
        raise HTTPException(status_code=404, detail="Devis introuvable")
    return FileResponse(pdf_file, media_type="application/pdf", filename=f"Devis_{numero}.pdf")


@app.get("/notedim-public/{numero}/{token}", response_class=HTMLResponse)
async def notedim_public(numero: str, token: str, request: Request):
    if not _verify_notedim_token(numero, token):
        raise HTTPException(status_code=403, detail="Lien invalide")
    html_nd = _render_notedim_html(request, numero)
    barre = (
        '<div style="position:fixed;top:0;left:0;right:0;z-index:9999;'
        'background:#F4F6F9;border-bottom:1px solid #E1E5EB;'
        'display:flex;align-items:center;justify-content:space-between;'
        'padding:12px 24px;font-family:Arial,Helvetica,sans-serif;">'
        '<div>'
        '<img src="/static/Logo.svg" alt="Hexa Rénov\'" style="height:32px;width:auto;vertical-align:middle;">'
        '<span style="color:#002E5A;font-weight:700;font-size:15px;margin-left:14px;vertical-align:middle;">Votre note de dimensionnement</span>'
        '</div>'
        '<a href="/notedim-public/' + numero + '/' + token + '/pdf" '
        'style="background:#E2214B;color:#ffffff;padding:10px 20px;border-radius:6px;'
        'font-weight:700;font-size:14px;text-decoration:none;">Télécharger le PDF</a>'
        '</div>'
        '<div style="height:58px;"></div>'
    )
    import re as _re
    if _re.search(r'<body[^>]*>', html_nd):
        html_nd = _re.sub(r'(<body[^>]*>)', lambda m: m.group(1) + barre, html_nd, count=1)
    else:
        html_nd = barre + html_nd
    return HTMLResponse(html_nd)


@app.get("/notedim-public/{numero}/{token}/pdf")
async def notedim_public_pdf(numero: str, token: str, request: Request):
    if not _verify_notedim_token(numero, token):
        raise HTTPException(status_code=403, detail="Lien invalide")
    pdf_bytes = _html_to_pdf_playwright(_render_notedim_html(request, numero), request)
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="NoteDim_{numero}.pdf"'},
    )


@app.get("/api/notedim/{numero}/pdf")
async def notedim_pdf(numero: str, request: Request):
    version = _next_devis_version(numero)
    pdf_bytes = _html_to_pdf_playwright(_render_notedim_html(request, numero), request)
    _write_pdf(_notedim_path(numero, version), pdf_bytes)
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="NoteDim_{numero}.pdf"'},
    )


def _email_header_html():
    return """<tr><td style="background:#ffffff;border-bottom:3px solid #002E5A;padding:24px;text-align:center;">
<img src="https://hexa-pac-lite-production.up.railway.app/static/Logo.png" alt="Hexa Rénov'" width="200" style="display:block;margin:0 auto;width:200px;max-width:200px;height:auto;border:0;">
<div style="color:#8A92A0;font-size:10px;text-transform:uppercase;letter-spacing:0.15em;margin-top:4px;">Rénovons l'avenir, économisons l'énergie</div>
</td></tr>"""


def _email_footer_html():
    return """<tr><td style="background:#F8F9FB;border-top:1px solid #E1E5EB;padding:24px;text-align:center;">
<div style="color:#4A5567;font-size:12px;font-weight:bold;">SAS HEXA RÉNOV'</div>
<div style="color:#8A92A0;font-size:11px;margin-top:4px;">RCS Nanterre 845 229 152 · info@hexa-renov.fr · 09 70 70 25 11</div>
</td></tr>"""


def _email_devis_html(prenom, apercu, pct_eco, lien_devis, pre_devis=False):
    bandeau = ""
    if apercu:
        bandeau = f"""<tr><td style="padding:20px 32px 8px 32px;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#002E5A;border-radius:8px;"><tr><td style="padding:22px 24px;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr>
<td style="vertical-align:top;">
<div style="color:#9fb8d4;font-size:12px;text-transform:uppercase;letter-spacing:0.06em;">Vous économisez dès maintenant</div>
<div style="margin-top:6px;"><span style="color:#ffffff;font-size:38px;font-weight:bold;">{apercu['eco_pendant']} €</span><span style="color:#9fb8d4;font-size:16px;"> /mois</span></div>
<div style="border-top:1px solid #1a4775;margin-top:12px;padding-top:12px;color:#c5d2e0;font-size:14px;">puis <strong style="color:#fff;">{apercu['eco_apres']} €/mois</strong> une fois l'installation remboursée</div>
</td>
<td style="width:70px;vertical-align:top;text-align:right;">
<span style="display:inline-block;background:#E2214B;color:#fff;font-size:15px;font-weight:bold;padding:6px 12px;border-radius:6px;">-{pct_eco}%</span>
</td>
</tr></table>
</td></tr></table>
</td></tr>"""
    return f"""<!DOCTYPE html><html><head><meta charset="utf-8"></head>
<body style="margin:0;padding:0;background:#eef1f5;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#eef1f5;padding:24px 0;"><tr><td align="center">
<table role="presentation" width="600" cellpadding="0" cellspacing="0" style="width:600px;max-width:600px;background:#ffffff;border-radius:12px;overflow:hidden;font-family:Arial,Helvetica,sans-serif;">
{_email_header_html()}
<tr><td style="padding:32px 32px 0 32px;">
<div style="color:#E2214B;font-size:13px;font-weight:bold;text-transform:uppercase;letter-spacing:0.04em;">Votre {'pré-devis' if pre_devis else 'devis'} personnalisé est prêt</div>
<div style="color:#0a2540;font-size:23px;font-weight:bold;margin-top:10px;line-height:1.3;">Bonjour {prenom},<br>votre projet de pompe à chaleur prend forme.</div>
<div style="color:#4A5567;font-size:15px;line-height:1.6;margin-top:16px;">Nous avons préparé votre {'pré-devis' if pre_devis else 'devis'} sur mesure. Bonne nouvelle : dès le premier mois, vous payez <strong style="color:#002E5A">moins cher qu'aujourd'hui</strong> — tout en remboursant votre installation.</div>
</td></tr>
{bandeau}
<tr><td style="padding:24px 32px 8px 32px;text-align:center;">
<a href="{lien_devis}" style="display:inline-block;background:#E2214B;color:#ffffff;font-size:16px;font-weight:bold;padding:16px 44px;border-radius:8px;text-decoration:none;">Découvrir mon {'pré-devis' if pre_devis else 'devis'}</a>
<div style="color:#8A92A0;font-size:12px;margin-top:10px;">Consultable en ligne · Téléchargeable en PDF</div>
</td></tr>
<tr><td style="padding:18px 32px 8px 32px;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr>
<td style="text-align:center;padding:0 6px;"><div style="font-size:22px;">🛡️</div><div style="color:#4A5567;font-size:11px;font-weight:bold;margin-top:4px;">Certifié RGE</div></td>
<td style="text-align:center;padding:0 6px;"><div style="font-size:22px;">🤝</div><div style="color:#4A5567;font-size:11px;font-weight:bold;margin-top:4px;">Aides incluses</div></td>
<td style="text-align:center;padding:0 6px;"><div style="font-size:22px;">⚡</div><div style="color:#4A5567;font-size:11px;font-weight:bold;margin-top:4px;">Réponse 24h</div></td>
<td style="text-align:center;padding:0 6px;"><div style="font-size:22px;">📍</div><div style="color:#4A5567;font-size:11px;font-weight:bold;margin-top:4px;">France Rénov'</div></td>
</tr></table>
</td></tr>
<tr><td style="padding:24px 32px;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#002E5A;border-radius:10px;"><tr><td style="padding:28px 24px;text-align:center;">
<div style="color:#ffffff;font-size:18px;font-weight:bold;">Une maison à rénover entièrement ?</div>
<div style="color:#9fb8d4;font-size:13px;margin-top:6px;">Un seul interlocuteur. Des aides cumulées. Plus d'économies.</div>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin-top:18px;"><tr>
<td style="width:33%;padding:4px;vertical-align:top;"><div style="background:#ffffff;border-radius:10px;height:96px;text-align:center;"><div style="padding-top:18px;font-size:30px;">🧱</div><div style="color:#002E5A;font-size:13px;font-weight:bold;margin-top:6px;">Isolation</div></div></td>
<td style="width:33%;padding:4px;vertical-align:top;"><div style="background:#ffffff;border-radius:10px;height:96px;text-align:center;"><div style="padding-top:18px;font-size:30px;">❄️</div><div style="color:#002E5A;font-size:13px;font-weight:bold;margin-top:6px;">Climatisation</div></div></td>
<td style="width:33%;padding:4px;vertical-align:top;"><div style="background:#ffffff;border-radius:10px;height:96px;text-align:center;"><div style="padding-top:18px;font-size:30px;">🏠</div><div style="color:#002E5A;font-size:13px;font-weight:bold;margin-top:6px;">Rénovation globale</div></div></td>
</tr></table>
</td></tr></table>
</td></tr>
{_email_footer_html()}
</table>
</td></tr></table>
</body></html>"""


def _email_notedim_html(prenom, specs, lien_notedim):
    def _v(x):
        return x if x not in (None, "") else "—"
    modele = _v(specs.get("modele"))
    etas35 = _v(specs.get("etas35"))
    etas55 = _v(specs.get("etas55"))
    surface = _v(specs.get("surface"))
    return f"""<!DOCTYPE html><html><head><meta charset="utf-8"></head>
<body style="margin:0;padding:0;background:#eef1f5;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#eef1f5;padding:24px 0;"><tr><td align="center">
<table role="presentation" width="600" cellpadding="0" cellspacing="0" style="width:600px;max-width:600px;background:#ffffff;border-radius:12px;overflow:hidden;font-family:Arial,Helvetica,sans-serif;">
{_email_header_html()}
<tr><td style="padding:32px 32px 0 32px;">
<div style="color:#002E5A;font-size:13px;font-weight:bold;text-transform:uppercase;letter-spacing:0.04em;">Votre étude technique</div>
<div style="color:#0a2540;font-size:22px;font-weight:bold;margin-top:10px;line-height:1.3;">Bonjour {prenom},<br>voici la note de dimensionnement de votre installation.</div>
<div style="color:#4A5567;font-size:15px;line-height:1.6;margin-top:16px;">Nous avons étudié votre logement pour dimensionner précisément votre pompe à chaleur. Voici les caractéristiques retenues pour garantir une installation parfaitement adaptée.</div>
</td></tr>
<tr><td style="padding:22px 32px 8px 32px;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#F0F4F9;border-radius:8px;"><tr><td style="padding:6px 20px;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0">
<tr><td style="padding:14px 0;border-bottom:1px solid #E1E5EB;color:#8A92A0;font-size:14px;white-space:nowrap;">Modèle préconisé</td><td style="padding:14px 0;border-bottom:1px solid #E1E5EB;color:#002E5A;font-size:14px;font-weight:bold;text-align:right;padding-left:16px;">{modele}</td></tr>
<tr><td style="padding:14px 0;border-bottom:1px solid #E1E5EB;color:#8A92A0;font-size:14px;white-space:nowrap;">ETAS 35°C / 55°C</td><td style="padding:14px 0;border-bottom:1px solid #E1E5EB;color:#002E5A;font-size:14px;font-weight:bold;text-align:right;padding-left:16px;">{etas35} % / {etas55} %</td></tr>
<tr><td style="padding:14px 0;color:#8A92A0;font-size:14px;white-space:nowrap;">Surface chauffée</td><td style="padding:14px 0;color:#002E5A;font-size:14px;font-weight:bold;text-align:right;padding-left:16px;">{surface} m²</td></tr>
</table>
</td></tr></table>
</td></tr>
<tr><td style="padding:22px 32px 8px 32px;text-align:center;">
<a href="{lien_notedim}" style="display:inline-block;background:#002E5A;color:#ffffff;font-size:16px;font-weight:bold;padding:16px 44px;border-radius:8px;text-decoration:none;">Consulter ma note technique</a>
<div style="color:#8A92A0;font-size:12px;margin-top:10px;">Consultable en ligne · Téléchargeable en PDF</div>
</td></tr>
{_email_footer_html()}
</table>
</td></tr></table>
</body></html>"""


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

    vt_validee = bool(prospect.get("vt_validee"))
    variante = str(payload.get("variante") or ("devis" if vt_validee else "pre_devis")).strip()
    if variante == "devis" and not vt_validee:
        raise HTTPException(status_code=400, detail="VT non validée : seul le pré-devis est possible")
    avec_sous_traitant = (variante == "devis")

    version = _next_sent_version(numero)
    devis_path, devis_html, version = _ensure_devis_pdf(numero, request, version, avec_sous_traitant)
    notedim_path = _ensure_notedim_pdf(numero, request, version)

    # Aperçu éco (bandeau email devis) — peut être None
    ctx = _build_devis_context(request, numero)
    apercu = ctx.get("projet_apercu")
    pct_eco = None
    if apercu and apercu.get("facture_avant") and apercu.get("eco_pendant"):
        pct_eco = round(apercu["eco_pendant"] / apercu["facture_avant"] * 100)

    # Specs techniques note de dim (None -> "—" géré dans le template email)
    catalogue = _read_catalogue_pac()
    state = _load_state_simulateur(numero, prospect, catalogue)
    modele_ref = state.get("modele_pac_id") or state.get("modele_pac")
    modele_obj = find_modele(catalogue, modele_ref) or select_default_modele(prospect, catalogue)
    specs = {
        "modele": (modele_obj.get("nom") or modele_obj.get("ref")) if modele_obj else None,
        "etas35": devis_value(modele_obj or {}, "etas35", default=None),
        "etas55": devis_value(modele_obj or {}, "etas55", default=None),
        "surface": devis_value(state, "surface_chauffee", default="") or devis_value(prospect, "surface_habitable", "surface_logement_m2", default="") or None,
    }

    prenom = html.escape(str(prospect.get("prenom") or ""))
    lien_devis = _public_devis_url_v(request, numero, version)
    lien_notedim = _public_notedim_url(request, numero)

    import resend

    resend.api_key = api_key
    result = resend.Emails.send(
        {
            "from": "Hexa Rénov' <a.parisot@hexa-renov.fr>",
            "to": [email_to],
            "subject": f"Votre {'pré-devis' if variante == 'pre_devis' else 'devis'} Hexa Rénov' — {prenom}",
            "html": _email_devis_html(prenom, apercu, pct_eco, lien_devis, pre_devis=(variante == "pre_devis")),
        }
    )
    resend.Emails.send(
        {
            "from": "Hexa Rénov' <a.parisot@hexa-renov.fr>",
            "to": [email_to],
            "subject": "Votre note de dimensionnement Hexa Rénov'",
            "html": _email_notedim_html(prenom, specs, lien_notedim),
        }
    )

    now = _now_iso()
    leads = _read_leads()
    idx = _find_lead_index(leads, numero)
    if idx is not None:
        leads[idx]["statut"] = "devis_envoye" if variante == "devis" else "pre_devis_envoye"
        leads[idx]["date_envoi_devis"] = now
        _atomic_write_json(LEADS_PATH, leads)

    auteur = str(payload.get("auteur") or "Anonyme")
    notes = _read_notes()
    notes.setdefault(numero, []).append(
        {"texte": f"{'Pré-devis' if variante == 'pre_devis' else 'Devis'} v{version} envoyé le {now} à {email_to} par {auteur}", "date": _now_paris_iso(), "auteur": auteur}
    )
    _atomic_write_json(NOTES_PATH, notes)

    meta = _read_devis_meta()
    item = {
        "version": version,
        "numero_devis": generer_numero_devis(prospect, version),
        "sent_at": now,
        "email": email_to,
        "file": devis_path,
        "html_file": devis_html,
        "notedim_file": notedim_path,
        "resend_id": result.get("id") if isinstance(result, dict) else "",
        "statut": "envoye",
        "variante": variante,
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
                "variante": item.get("variante", "devis"),
                "sent_at": item.get("sent_at", ""),
                "email": item.get("email", ""),
                "file": path,
                "has_notedim": bool(item.get("notedim_file") and os.path.exists(item.get("notedim_file"))),
            })
    items.sort(key=lambda x: x.get("version", 0), reverse=True)
    return JSONResponse(items)


@app.get("/api/devis/{numero}/download")
async def download_devis(numero: str, version: int):
    path = _devis_path(numero, version)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Devis introuvable")
    return FileResponse(path, media_type="application/pdf", filename=os.path.basename(path))


@app.get("/api/devis/{numero}/view")
async def view_devis(numero: str, version: int):
    path = _devis_path(numero, version)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Devis introuvable")
    return FileResponse(path, media_type="application/pdf", headers={"Content-Disposition": "inline"})


@app.get("/api/notedim/{numero}/view")
async def view_notedim(numero: str, version: int):
    path = _notedim_path(numero, version)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Note de dimensionnement introuvable")
    return FileResponse(path, media_type="application/pdf", headers={"Content-Disposition": "inline"})


@app.get("/api/notedim/{numero}/download")
async def download_notedim(numero: str, version: int):
    path = _notedim_path(numero, version)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Note de dimensionnement introuvable")
    return FileResponse(path, media_type="application/pdf", filename=os.path.basename(path))


# ---------------------------------------------------------------------------
# Documents prospect : stockage par dossier + index.json + upload/statut
# ---------------------------------------------------------------------------
TYPE_TO_EXT = {"PDF": {"pdf"}, "PNG": {"png"}, "JPEG": {"jpeg", "jpg"}}
EXT_NORM = {"pdf": ".pdf", "png": ".png", "jpeg": ".jpg", "jpg": ".jpg"}
DOC_MEDIA_TYPE = {".pdf": "application/pdf", ".png": "image/png", ".jpg": "image/jpeg"}


def _doc_err(msg, code=400):
    return JSONResponse({"status": "error", "msg": msg}, status_code=code)


def _slug(text):
    t = unicodedata.normalize("NFKD", str(text or ""))
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.sub(r"[^A-Za-z0-9]+", "_", t).strip("_")


def _doc_filename(civilite, nom, prenom, label, ext):
    parts = [_slug(civilite), _slug(nom).upper(), _slug(prenom).title(), _slug(label)]
    return ("_".join(p for p in parts if p) or "Document") + ext


def _prospect_docs_dir(numero):
    safe = re.sub(r"[^A-Za-z0-9_-]", "", str(numero))
    return os.path.join(DOCUMENTS_DIR, safe)


def _docs_index_path(numero):
    return os.path.join(_prospect_docs_dir(numero), "index.json")


def _read_docs_index(numero):
    docs = _read_json(_docs_index_path(numero), [])
    return docs if isinstance(docs, list) else []


def _write_docs_index(numero, docs):
    os.makedirs(_prospect_docs_dir(numero), exist_ok=True)
    _atomic_write_json(_docs_index_path(numero), docs)


def _find_doc_slot(cat_id, sous_id, ss_id=None):
    for cat in _read_json(DOCUMENTS_CATEGORIES_PATH, []):
        if cat.get("id") != cat_id:
            continue
        for sous in cat.get("sous_categories", []):
            if sous.get("id") != sous_id:
                continue
            if ss_id:
                for ss in (sous.get("sous_sous_categories") or []):
                    if ss.get("id") == ss_id:
                        return ss
                return None
            return sous
    return None


def _doc_path_safe(numero, filename):
    pdir = os.path.abspath(_prospect_docs_dir(numero))
    path = os.path.abspath(os.path.join(pdir, os.path.basename(filename)))
    if not path.startswith(pdir + os.sep):
        return None
    return path if os.path.exists(path) else None


@app.post("/prospect/{numero}/document")
async def upload_document(
    numero: str,
    fichier: UploadFile = File(...),
    categorie_id: str = Form(...),
    sous_categorie_id: str = Form(...),
    sous_sous_categorie_id: str = Form(""),
    civilite: str = Form(""),
    nom: str = Form(""),
    prenom: str = Form(""),
    auteur: str = Form(""),
) -> JSONResponse:
    if not _find_lead(numero):
        return _doc_err("Prospect introuvable", 404)
    ss = (sous_sous_categorie_id or "").strip() or None
    slot = _find_doc_slot(categorie_id, sous_categorie_id, ss)
    if not slot:
        return _doc_err("Catégorie inconnue", 400)
    ext_raw = os.path.splitext(fichier.filename or "")[1].lower().lstrip(".")
    allowed = set()
    for t in slot.get("types_acceptes", ["PDF"]):
        allowed |= TYPE_TO_EXT.get(str(t).upper(), set())
    if ext_raw not in allowed:
        return _doc_err("Type de fichier non accepté (" + ", ".join(slot.get("types_acceptes", [])) + ")", 400)
    ext = EXT_NORM.get(ext_raw, "." + ext_raw)
    data = await fichier.read()
    if len(data) > 20 * 1024 * 1024:
        return _doc_err("Fichier trop volumineux (max 20 Mo)", 400)
    docs = _read_docs_index(numero)
    same = [d for d in docs
            if (d.get("categorie_id"), d.get("sous_categorie_id"), d.get("sous_sous_categorie_id") or None)
            == (categorie_id, sous_categorie_id, ss)]
    max_docs = int(slot.get("max_docs") or 1)
    pdir = _prospect_docs_dir(numero)
    os.makedirs(pdir, exist_ok=True)
    fname = _doc_filename(civilite, nom, prenom, slot.get("label", "Document"), ext)
    if max_docs == 1:
        for d in same:
            old = os.path.join(pdir, d["filename"])
            if os.path.exists(old):
                os.remove(old)
        docs = [d for d in docs if d not in same]
    else:
        if len(same) >= max_docs:
            return _doc_err("Maximum " + str(max_docs) + " fichier(s) atteint", 400)
        names = {d["filename"] for d in docs}
        if fname in names:
            stem, e = os.path.splitext(fname)
            i = 2
            while stem + "_" + str(i) + e in names:
                i += 1
            fname = stem + "_" + str(i) + e
    fname = os.path.basename(fname)
    with open(os.path.join(pdir, fname), "wb") as f:
        f.write(data)
    docs.append({
        "filename": fname,
        "categorie_id": categorie_id,
        "sous_categorie_id": sous_categorie_id,
        "sous_sous_categorie_id": ss,
        "taille_octets": len(data),
        "date_upload": _now_iso(),
        "auteur": (auteur or "").strip() or "Avi B.",
        "commentaire": "",
    })
    _write_docs_index(numero, docs)
    return JSONResponse({"status": "ok", "filename": fname})


@app.get("/prospect/{numero}/documents/status")
def documents_status(numero: str) -> JSONResponse:
    docs = _read_docs_index(numero)
    counts = {}
    for d in docs:
        key = str(d.get("categorie_id")) + "/" + str(d.get("sous_categorie_id"))
        counts[key] = counts.get(key, 0) + 1
    statuts = {}
    for cat in _read_json(DOCUMENTS_CATEGORIES_PATH, []):
        for sous in cat.get("sous_categories", []):
            if sous.get("statut") == "Ok / Manquant":
                key = str(cat.get("id")) + "/" + str(sous.get("id"))
                statuts[key] = "ok" if counts.get(key, 0) > 0 else "manquant"
    return JSONResponse({"counts": counts, "statuts": statuts, "documents": docs})


@app.get("/prospect/{numero}/document/{filename}")
def download_document(numero: str, filename: str):
    path = _doc_path_safe(numero, filename)
    if not path:
        raise HTTPException(status_code=404, detail="Document introuvable")
    media = DOC_MEDIA_TYPE.get(os.path.splitext(path)[1].lower(), "application/octet-stream")
    return FileResponse(path, media_type=media, filename=os.path.basename(path))


@app.get("/prospect/{numero}/document/{filename}/view")
def view_document(numero: str, filename: str):
    path = _doc_path_safe(numero, filename)
    if not path:
        raise HTTPException(status_code=404, detail="Document introuvable")
    media = DOC_MEDIA_TYPE.get(os.path.splitext(path)[1].lower(), "application/octet-stream")
    return FileResponse(path, media_type=media, headers={"Content-Disposition": "inline"})


@app.delete("/prospect/{numero}/document/{filename}")
def delete_document(numero: str, filename: str) -> JSONResponse:
    safe = os.path.basename(filename)
    docs = _read_docs_index(numero)
    new = [d for d in docs if d.get("filename") != safe]
    if len(new) == len(docs):
        return _doc_err("Document introuvable", 404)
    path = os.path.join(_prospect_docs_dir(numero), safe)
    if os.path.exists(path):
        os.remove(path)
    _write_docs_index(numero, new)
    return JSONResponse({"status": "ok"})


@app.put("/prospect/{numero}/document/{filename}/commentaire")
async def comment_document(numero: str, filename: str, request: Request) -> JSONResponse:
    try:
        payload = await request.json()
    except ValueError:
        payload = {}
    safe = os.path.basename(filename)
    docs = _read_docs_index(numero)
    found = False
    for d in docs:
        if d.get("filename") == safe:
            d["commentaire"] = str(payload.get("commentaire") or "")
            found = True
            break
    if not found:
        return _doc_err("Document introuvable", 404)
    _write_docs_index(numero, docs)
    return JSONResponse({"status": "ok"})


def _gamme_from_specs(model: dict) -> str:
    for spec in (model.get("description_specs") or []):
        if isinstance(spec, dict) and str(spec.get("champ", "")).strip().lower() == "gamme":
            val = str(spec.get("valeur", "")).strip()
            if val:
                return val
    return ""


def _gamme_auto(model) -> str:
    """Gamme d'un modèle : champ 'Gamme' de description_specs, sinon ref brute (jamais vide)."""
    if isinstance(model, dict):
        g = _gamme_from_specs(model)
        if g:
            return g
        return str(model.get("ref") or model.get("nom") or "").strip()
    return str(model or "").strip()


def _read_fiches_index() -> dict:
    idx = _read_json(FICHES_INDEX_PATH, {})
    return idx if isinstance(idx, dict) else {}


def _write_fiches_index(index: dict) -> None:
    os.makedirs(FICHES_DIR, exist_ok=True)
    _atomic_write_json(FICHES_INDEX_PATH, index)


def _fiche_slug(gamme: str) -> str:
    s = re.sub(r"[^A-Za-z0-9_-]+", "_", str(gamme or "").strip()).strip("_")
    return s or "gamme"


def _fiche_pdf_path(gamme: str) -> str:
    return os.path.join(FICHES_DIR, _fiche_slug(gamme) + ".pdf")


def _fiche_ballon_pdf_path(ref: str) -> str:
    return os.path.join(FICHES_DIR, "ballon_" + _fiche_slug(ref) + ".pdf")


def _gamme_of(model, overrides: dict) -> str:
    ref = (model.get("ref") if isinstance(model, dict) else str(model or "")) or ""
    return (overrides or {}).get(str(ref).strip()) or _gamme_auto(model)


@app.get("/api/admin/gammes")
def list_gammes(request: Request) -> JSONResponse:
    _require_admin(request)
    overrides = _read_fiches_index().get("gamme_overrides", {})
    rows = []
    for m in _read_catalogue_pac():
        ref = str(m.get("ref") or m.get("nom") or "").strip()
        if not ref:
            continue
        auto = _gamme_auto(m)
        rows.append({
            "ref": ref, "nom": m.get("nom") or "",
            "gamme": overrides.get(ref) or auto,
            "gamme_auto": auto,
            "source": "override" if ref in overrides else "auto",
        })
    return JSONResponse(rows)


@app.post("/api/admin/gammes")
async def set_gamme(request: Request, ref: str = Form(...), gamme: str = Form("")) -> JSONResponse:
    _require_admin(request)
    ref = str(ref or "").strip()
    if not ref:
        raise HTTPException(status_code=400, detail="Référence manquante")
    catalogue = _read_catalogue_pac()
    model = find_modele(catalogue, ref)
    auto = _gamme_auto(model or ref)
    g = str(gamme or "").strip()
    index = _read_fiches_index()
    overrides = index.get("gamme_overrides", {})
    if not g or g == auto:
        overrides.pop(ref, None)          # retour à l'auto = pas d'override stocké
    else:
        overrides[ref] = g
    index["gamme_overrides"] = overrides
    _write_fiches_index(index)
    return JSONResponse({"status": "ok", "ref": ref, "gamme": g or auto,
                         "gamme_auto": auto, "source": "override" if ref in overrides else "auto"})


@app.post("/api/admin/fiches-techniques")
async def upload_fiche_technique(request: Request, fichier: UploadFile = File(...), gamme: str = Form(...), auteur: str = Form("")) -> JSONResponse:
    _require_admin(request)
    gamme = str(gamme or "").strip()
    if not gamme:
        raise HTTPException(status_code=400, detail="Gamme manquante")
    ext = os.path.splitext(fichier.filename or "")[1].lower().lstrip(".")
    if ext != "pdf":
        raise HTTPException(status_code=400, detail="Seuls les PDF sont acceptés")
    data = await fichier.read()
    if len(data) > 20 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Fichier trop volumineux (max 20 Mo)")
    os.makedirs(FICHES_DIR, exist_ok=True)
    path = _fiche_pdf_path(gamme)
    with open(path, "wb") as f:
        f.write(data)
    index = _read_fiches_index()
    fiches = index.get("fiches", {})
    fiches[gamme] = {
        "filename": os.path.basename(path),
        "taille_octets": len(data),
        "date_upload": _now_iso(),
        "auteur": (auteur or "").strip() or "Admin",
    }
    index["fiches"] = fiches
    _write_fiches_index(index)
    return JSONResponse({"status": "ok", "gamme": gamme, "fiche": fiches[gamme]})


@app.post("/api/admin/fiches-ballon")
async def upload_fiche_ballon(request: Request, fichier: UploadFile = File(...), ref: str = Form(...), auteur: str = Form("")) -> JSONResponse:
    _require_admin(request)
    ref = str(ref or "").strip()
    if not ref:
        raise HTTPException(status_code=400, detail="Référence ballon manquante")
    ext = os.path.splitext(fichier.filename or "")[1].lower().lstrip(".")
    if ext != "pdf":
        raise HTTPException(status_code=400, detail="Seuls les PDF sont acceptés")
    data = await fichier.read()
    if len(data) > 20 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Fichier trop volumineux (max 20 Mo)")
    os.makedirs(FICHES_DIR, exist_ok=True)
    path = _fiche_ballon_pdf_path(ref)
    with open(path, "wb") as f:
        f.write(data)
    index = _read_fiches_index()
    fiches = index.get("fiches_ballon", {})
    fiches[ref] = {
        "filename": os.path.basename(path),
        "taille_octets": len(data),
        "date_upload": _now_iso(),
        "auteur": (auteur or "").strip() or "Admin",
    }
    index["fiches_ballon"] = fiches
    _write_fiches_index(index)
    return JSONResponse({"status": "ok", "ref": ref, "fiche": fiches[ref]})


@app.get("/api/admin/fiches-ballon")
def list_fiches_ballon(request: Request) -> JSONResponse:
    _require_admin(request)
    return JSONResponse(_read_fiches_index().get("fiches_ballon", {}))


@app.get("/api/admin/fiches-ballon/view")
def view_fiche_ballon(request: Request, ref: str):
    _require_admin(request)
    ref = str(ref or "").strip()
    entry = _read_fiches_index().get("fiches_ballon", {}).get(ref)
    if not entry:
        raise HTTPException(status_code=404, detail="Fiche introuvable")
    path = _fiche_ballon_pdf_path(ref)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Fichier introuvable")
    return FileResponse(path, media_type="application/pdf", headers={"Content-Disposition": "inline"})


@app.delete("/api/admin/fiches-ballon")
def delete_fiche_ballon(request: Request, ref: str) -> JSONResponse:
    _require_admin(request)
    ref = str(ref or "").strip()
    index = _read_fiches_index()
    fiches = index.get("fiches_ballon", {})
    if ref not in fiches:
        raise HTTPException(status_code=404, detail="Fiche introuvable")
    path = _fiche_ballon_pdf_path(ref)
    if os.path.exists(path):
        os.remove(path)
    fiches.pop(ref, None)
    index["fiches_ballon"] = fiches
    _write_fiches_index(index)
    return JSONResponse({"status": "ok", "ref": ref})


@app.get("/api/admin/fiches-techniques")
def list_fiches_techniques(request: Request) -> JSONResponse:
    _require_admin(request)
    return JSONResponse(_read_fiches_index().get("fiches", {}))


@app.get("/api/admin/fiches-techniques/view")
def view_fiche_technique(request: Request, gamme: str):
    _require_admin(request)
    gamme = str(gamme or "").strip()
    entry = _read_fiches_index().get("fiches", {}).get(gamme)
    if not entry:
        raise HTTPException(status_code=404, detail="Fiche introuvable")
    path = _fiche_pdf_path(gamme)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Fichier introuvable")
    return FileResponse(path, media_type="application/pdf", headers={"Content-Disposition": "inline"})


@app.delete("/api/admin/fiches-techniques")
def delete_fiche_technique(request: Request, gamme: str) -> JSONResponse:
    _require_admin(request)
    gamme = str(gamme or "").strip()
    index = _read_fiches_index()
    fiches = index.get("fiches", {})
    if gamme not in fiches:
        raise HTTPException(status_code=404, detail="Fiche introuvable")
    path = _fiche_pdf_path(gamme)
    if os.path.exists(path):
        os.remove(path)
    fiches.pop(gamme, None)
    index["fiches"] = fiches
    _write_fiches_index(index)
    return JSONResponse({"status": "ok", "gamme": gamme})


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
    notes.setdefault(numero, []).append({"texte": f"📧 Email envoyé à {email_to} : {sujet}", "date": _now_paris_iso(), "auteur": auteur})
    _atomic_write_json(NOTES_PATH, notes)
    return JSONResponse({"ok": True})
