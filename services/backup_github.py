"""Sauvegarde quotidienne des JSON de DATA_DIR vers un depot GitHub prive.

API Git Data de GitHub (pas de binaire git, 1 commit/jour). Aucun secret en dur :
tout vient des variables d'environnement. Le token n'est jamais logge ni mis en URL.
"""
import asyncio
import base64
import json
import os
import urllib.request
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

GITHUB_API = "https://api.github.com"


def _env():
    return {
        "token": os.environ.get("GITHUB_BACKUP_TOKEN", "").strip(),
        "repo": os.environ.get("GITHUB_BACKUP_REPO", "").strip(),       # "owner/hexa-backups"
        "branch": os.environ.get("GITHUB_BACKUP_BRANCH", "main").strip() or "main",
        "hour": int(os.environ.get("BACKUP_HOUR_PARIS", "3") or "3"),
    }


def _api(method, url, token, payload=None):
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("User-Agent", "hexa-pac-lite-backup")
    if data is not None:
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=30) as resp:
        body = resp.read().decode("utf-8")
    return json.loads(body) if body else {}


def _collect_json_files(data_dir):
    """Tous les *.json sous DATA_DIR (exclut PDF/documents binaires)."""
    files = {}
    for root, _dirs, names in os.walk(data_dir):
        for name in names:
            if not name.endswith(".json"):
                continue
            if name == "users.json":  # jamais les hachages de mots de passe sur GitHub
                continue
            full = os.path.join(root, name)
            rel = os.path.relpath(full, data_dir).replace(os.sep, "/")
            try:
                with open(full, "rb") as f:
                    files[rel] = f.read()
            except OSError:
                continue
    return files


def run_backup_once(data_dir):
    """Cree un commit unique avec tous les JSON. Retourne un message de statut."""
    cfg = _env()
    if not cfg["token"] or not cfg["repo"]:
        return "desactive (secrets absents)"
    token, repo, branch = cfg["token"], cfg["repo"], cfg["branch"]
    base = f"{GITHUB_API}/repos/{repo}/git"

    ref = _api("GET", f"{base}/ref/heads/{branch}", token)
    parent_sha = ref["object"]["sha"]
    base_tree = _api("GET", f"{base}/commits/{parent_sha}", token)["tree"]["sha"]

    files = _collect_json_files(data_dir)
    if not files:
        return "aucun JSON a sauvegarder"

    entries = []
    for rel, content in files.items():
        blob = _api("POST", f"{base}/blobs", token, {
            "content": base64.b64encode(content).decode("ascii"),
            "encoding": "base64",
        })
        entries.append({"path": rel, "mode": "100644", "type": "blob", "sha": blob["sha"]})

    tree = _api("POST", f"{base}/trees", token, {"base_tree": base_tree, "tree": entries})
    if tree["sha"] == base_tree:
        return "aucun changement, rien a pousser"

    stamp = datetime.now(ZoneInfo("Europe/Paris")).strftime("%Y-%m-%d %H:%M")
    commit = _api("POST", f"{base}/commits", token, {
        "message": f"Backup auto {stamp}",
        "tree": tree["sha"],
        "parents": [parent_sha],
    })
    _api("PATCH", f"{base}/refs/heads/{branch}", token, {"sha": commit["sha"]})
    return f"{len(files)} fichiers pousses (commit {commit['sha'][:7]})"


async def _loop(data_dir):
    while True:
        cfg = _env()
        now = datetime.now(ZoneInfo("Europe/Paris"))
        target = now.replace(hour=cfg["hour"] % 24, minute=0, second=0, microsecond=0)
        if target <= now:
            target += timedelta(days=1)
        await asyncio.sleep(max(60, (target - now).total_seconds()))
        try:
            msg = await asyncio.to_thread(run_backup_once, data_dir)
            print(f"[backup] {msg}")
        except Exception as exc:  # ne jamais tuer la boucle
            print(f"[backup] echec : {type(exc).__name__}: {exc}")


def start_backup_scheduler(data_dir):
    cfg = _env()
    if not cfg["token"] or not cfg["repo"]:
        print("[backup] desactive (GITHUB_BACKUP_TOKEN / GITHUB_BACKUP_REPO absents)")
        return
    asyncio.create_task(_loop(data_dir))
    print(f"[backup] planifie a {cfg['hour']}h Paris -> {cfg['repo']}")
