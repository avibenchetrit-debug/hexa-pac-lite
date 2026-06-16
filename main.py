import io
import html
import json
import os
import re
import shutil
import unicodedata
from datetime import datetime

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

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
REPO_CATALOGUE_PATH = os.path.join(REPO_DATA_DIR, "catalogue_pac.json")
REPO_BAREMES_PATH = os.path.join(REPO_DATA_DIR, "baremes.json")


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

# Serve static assets (CSS/JS/images) under /static.
os.makedirs(STATIC_DIR, exist_ok=True)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


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
    _seed_json_file(CATALOGUE_PATH, DEFAULT_CATALOGUE_PAC, REPO_CATALOGUE_PATH)
    _seed_json_file(BAREMES_PATH, {}, REPO_BAREMES_PATH)


def _read_leads():
    leads = _read_json(LEADS_PATH, [])
    return leads if isinstance(leads, list) else []


def _read_notes():
    notes = _read_json(NOTES_PATH, {})
    return notes if isinstance(notes, dict) else {}


def _read_echanges():
    echanges = _read_json(ECHANGES_PATH, {})
    return echanges if isinstance(echanges, dict) else {}


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
    "devis envoye": "devis",
    "devis envoyé": "devis",
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
    "code_postal_chantier": "cp",
    "ville_chantier": "ville",
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
    "date_acquisition",

    # Bloc 2 (Informations personnelles)
    "civilite",

    # Bloc 3 (Adresse & Données réglementaires)
    "adresse_chantier",
    "code_postal_chantier",
    "ville_chantier",
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

    # Bloc 5 (Informations fiscales)
    "rfr",
    "nombre_personnes",
    "code_postal_personne",

    # Logs
    "nrp_log",
]

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
        normalized.setdefault(field, "" if field != "nrp_log" else [])
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
                item[field] = [] if field == "nrp_log" else ""
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


def _note_for_front(entry):
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
    catalogue = _read_json(CATALOGUE_PAC_PATH, DEFAULT_CATALOGUE_PAC)
    if not isinstance(catalogue, list):
        catalogue = DEFAULT_CATALOGUE_PAC
    return JSONResponse(catalogue)


@app.get("/api/gmaps-key")
def get_gmaps_key() -> JSONResponse:
    return JSONResponse({"key": os.environ.get("GMAPS_API_KEY", "")})


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
        {"numero": numero, "commentaires": [_note_for_front(e) for e in entries]}
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
