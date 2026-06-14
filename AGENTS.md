# hexa-pac-lite

Minimal FastAPI app that serves a single HTML page and a health check, deployable on Railway via Docker.

## Cursor Cloud specific instructions

- Stack: Python 3.12 + FastAPI, served by `uvicorn`. Single service.
- Dependencies are installed into a local virtualenv at `.venv` (gitignored). Activate with `source .venv/bin/activate` before running commands.
- Run the dev server (hot reload): `uvicorn main:app --reload --host 0.0.0.0 --port 8000`. App is then at `http://localhost:8000`.
- Smoke check: `curl localhost:8000/health` returns `{"status":"ok"}`; `GET /` returns the HTML page (200).
- The page is served by reading `templates/index.html` raw and returning it as-is (no Jinja templating), so HTML/JS curly braces are preserved verbatim. `templates/index.html` is currently a PLACEHOLDER; the intended source `apercu-fiche-complete (7).html` was not present in the repo when scaffolded and must replace the placeholder.
- The page's `fetch()` calls to routes like `/api/fiche` and `/api/data` intentionally 404 (fail silently in the browser) — this is expected at this stage; do not "fix" them.
- Static assets are served from `static/` under `/static`; app data lives in `data/`. Both are kept in git via `.gitkeep`.
- Production/Railway uses the `Dockerfile` + `railway.json` (start command `uvicorn main:app --host 0.0.0.0 --port $PORT`). For local dev use the `--reload` command above instead.
