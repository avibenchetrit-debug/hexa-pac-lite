# hexa-pac-lite

Minimal FastAPI app that serves a single HTML page and a health check, deployable on Railway via Docker.

## Cursor Cloud specific instructions

- Stack: Python 3.12 + FastAPI, served by `uvicorn`. Single service.
- Dependencies are installed into a local virtualenv at `.venv` (gitignored). Activate with `source .venv/bin/activate` before running commands.
- Run the dev server (hot reload): `uvicorn main:app --reload --host 0.0.0.0 --port 8000`. App is then at `http://localhost:8000`.
- Smoke check: `curl localhost:8000/health` returns `{"status":"ok"}`; `GET /` returns the HTML page (200).
- The page is served by reading `templates/index.html` raw and returning it as-is (no Jinja templating), so HTML/JS curly braces are preserved verbatim. `templates/index.html` is a byte-exact copy of the real app HTML (`apercu-fiche-complete (7).html`, kept at the repo root as the source of truth) — keep them identical; do not hand-edit `templates/index.html`.
- The page's `fetch()` calls to `/api/*` routes intentionally 404 (fail silently in the browser) — these backend routes are not implemented yet; this is expected, do not "fix" them.
- Static assets are served from `static/` under `/static`; app data lives in `data/`. Both are kept in git via `.gitkeep`.
- Production/Railway uses the `Dockerfile` + `railway.json` (start command `uvicorn main:app --host 0.0.0.0 --port $PORT`). For local dev use the `--reload` command above instead.
- Persistence is flat JSON files written atomically (tmp + `os.replace`) under `data/`: `data/leads.json` (list) and `data/notes.json` (`{numero: [notes]}`). They are committed in their empty initial state (`[]` / `{}`) and `main.py` recreates them on startup if missing. Gotcha: running the app (importing leads / adding notes) rewrites these files, so `git status` will show them as modified — do not commit local test data.
- Notes are stored as `{texte, date, auteur}` but `GET /prospect/{numero}/commentaires-json` also echoes `texte_html`/`horodatage` so the existing front-end (`chargerNotes`) renders them; keep both key sets when changing the notes shape.
