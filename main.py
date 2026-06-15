import io
import json
import os
import re
import unicodedata
from datetime import datetime

from fastapi import FastAPI, File, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")
STATIC_DIR = os.path.join(BASE_DIR, "static")
DATA_DIR = os.path.join(BASE_DIR, "data")
LEADS_PATH = os.path.join(DATA_DIR, "leads.json")
NOTES_PATH = os.path.join(DATA_DIR, "notes.json")

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


def _init_storage():
    os.makedirs(DATA_DIR, exist_ok=True)
    if not os.path.exists(LEADS_PATH):
        _atomic_write_json(LEADS_PATH, [])
    if not os.path.exists(NOTES_PATH):
        _atomic_write_json(NOTES_PATH, {})


_init_storage()


def _read_leads():
    leads = _read_json(LEADS_PATH, [])
    return leads if isinstance(leads, list) else []


def _read_notes():
    notes = _read_json(NOTES_PATH, {})
    return notes if isinstance(notes, dict) else {}


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

PROSPECT_FIELDS = [
    "nom", "prenom", "telephone", "email", "cp",
    "ville", "statut", "categorie", "source", "projet_initial",
]


def _extract_texte(payload_form, payload_json):
    for key in ("texte_commentaire", "texte", "commentaire", "texte_html"):
        if payload_form and payload_form.get(key):
            return str(payload_form.get(key))
        if payload_json and payload_json.get(key):
            return str(payload_json.get(key))
    return ""


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
    from pathlib import Path

    p = Path(__file__).parent / "data" / "baremes.json"
    if not p.exists():
        return {}
    with open(p, encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# A) Leads
# ---------------------------------------------------------------------------
@app.get("/api/leads")
def get_leads() -> JSONResponse:
    return JSONResponse(_read_leads())


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
        record = {k: v for k, v in record.items() if k in PROSPECT_FIELDS}
        note_text = ""
        for col, field in col_map.items():
            if field == "notes":
                note_text = str(row[col]).strip()

        # Skip fully empty rows.
        if not any(record.values()) and not note_text:
            continue

        numero = _next_numero(leads)
        prospect = {"numero": numero, "date": _now_iso()}
        prospect.update({field: record.get(field, "") for field in PROSPECT_FIELDS})
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
    if not texte:
        return JSONResponse({"ok": False, "msg": "Texte vide"}, status_code=400)

    notes = _read_notes()
    notes.setdefault(numero, []).append(
        {"texte": texte, "date": _now_iso(), "auteur": "Manuel"}
    )
    _atomic_write_json(NOTES_PATH, notes)

    return JSONResponse({"ok": True, "count": len(notes[numero])})
