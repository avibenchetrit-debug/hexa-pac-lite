import atexit
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import pytest


TARGET_URL = os.environ.get(
    "AUDIT_TARGET_URL", "https://hexa-pac-lite-production.up.railway.app"
).rstrip("/")
ROOT = Path(__file__).resolve().parents[1]
SCREENSHOTS = ROOT / "tests" / "screenshots"
RESULTS = ROOT / "tests" / "playwright_results.jsonl"
FIXTURE_XLSX = ROOT / "tests" / "fixtures" / "test_import.xlsx"

SCREENSHOTS.mkdir(parents=True, exist_ok=True)
RESULTS.parent.mkdir(parents=True, exist_ok=True)

_ORIGINAL_CATALOGUE = None
_CATALOGUE_CHANGED = False


def _api(path, method="GET", data=None, headers=None, timeout=10):
    url = TARGET_URL + path
    body = None
    req_headers = headers or {}
    if data is not None:
        body = json.dumps(data).encode("utf-8")
        req_headers.setdefault("Content-Type", "application/json")
    req = urllib.request.Request(url, data=body, method=method, headers=req_headers)
    started = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            try:
                parsed = json.loads(raw) if raw else None
            except json.JSONDecodeError:
                parsed = raw
            return resp.status, parsed, time.monotonic() - started
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(raw) if raw else raw
        except json.JSONDecodeError:
            parsed = raw
        return exc.code, parsed, time.monotonic() - started


def _restore_catalogue():
    global _CATALOGUE_CHANGED
    if _CATALOGUE_CHANGED and _ORIGINAL_CATALOGUE:
        try:
            _api("/api/catalogue-pac", method="POST", data=_ORIGINAL_CATALOGUE, timeout=10)
        except Exception:
            pass


atexit.register(_restore_catalogue)


def _log(case_id, title, status, message="", screenshot=""):
    with RESULTS.open("a", encoding="utf-8") as f:
        f.write(
            json.dumps(
                {
                    "case": case_id,
                    "title": title,
                    "status": status,
                    "message": message,
                    "screenshot": screenshot,
                    "target_url": TARGET_URL,
                },
                ensure_ascii=False,
            )
            + "\n"
        )


def _shot(page, case_id):
    path = SCREENSHOTS / f"{case_id}.png"
    try:
        page.screenshot(path=str(path), full_page=True)
        return str(path.relative_to(ROOT))
    except Exception:
        return ""


def _assert(page, case_id, condition, message):
    if not condition:
        screenshot = _shot(page, case_id)
        raise AssertionError(f"{message} | screenshot={screenshot}")


def _home(page):
    page.goto(TARGET_URL, wait_until="domcontentloaded", timeout=30000)
    page.evaluate("localStorage.removeItem('hexa_prospects')")
    page.reload(wait_until="networkidle", timeout=30000)
    page.wait_for_selector("#hexa-prospects-view", timeout=10000)
    try:
        page.wait_for_function("document.querySelectorAll('#pv-tbody tr').length > 0", timeout=8000)
    except Exception:
        pass


def _open_pr(page, numero="PR-000001"):
    _home(page)
    row = page.locator(f"#pv-tbody tr[data-num='{numero}']").first
    row.click(timeout=10000)
    page.wait_for_function(
        "() => !document.body.classList.contains('hexa-view-prospects')", timeout=8000
    )


def _new(page):
    _home(page)
    page.locator("#pv-new").click()
    page.wait_for_function(
        "() => !document.body.classList.contains('hexa-view-prospects')", timeout=8000
    )


def _cell_texts(page, row_selector="#pv-tbody tr:first-child"):
    return page.locator(f"{row_selector} td").all_text_contents()


def _api_leads():
    status, payload, elapsed = _api("/api/leads")
    assert status == 200 and isinstance(payload, list), f"/api/leads invalid: {status}"
    return payload, elapsed


def _first_lead():
    leads, _ = _api_leads()
    return leads[0] if leads else {}


def _case_a1(page, cid):
    start = time.monotonic()
    _home(page)
    _assert(page, cid, time.monotonic() - start < 3, "La page charge en plus de 3s")


def _case_a2(page, cid):
    _home(page)
    img = page.locator("img.logo-hexa-wordmark").first
    _assert(page, cid, img.count() == 1 and img.is_visible(), "Logo absent")
    ok = img.evaluate("(i) => i.complete && i.getBoundingClientRect().width > 0")
    _assert(page, cid, ok, "Logo image cassée ou non rendue")


def _case_a3(page, cid):
    _home(page)
    _assert(page, cid, page.get_by_role("heading", name="Prospects").is_visible(), "Titre Prospects invisible")


def _case_a4(page, cid):
    errors = []
    page.on("console", lambda msg: errors.append(msg.text) if msg.type == "error" else None)
    _home(page)
    _assert(page, cid, not errors, "Erreurs console JS: " + " | ".join(errors[:5]))


def _case_a5(page, cid):
    _home(page)
    no_scroll = page.evaluate("document.body.scrollWidth <= window.innerWidth")
    _assert(page, cid, no_scroll, "Scrollbar horizontale détectée")


def _case_a6(page, cid):
    leads, _ = _api_leads()
    _home(page)
    rows = page.locator("#pv-tbody tr").count()
    _assert(page, cid, rows == len(leads), f"Table={rows}, /api/leads={len(leads)}")


def _case_a7(page, cid):
    _home(page)
    expected = ["N°", "Statut", "Nom Prénom", "CP", "Téléphone", "E-mail", "Catégorie", "Créé le", "NRP", "Dern. NRP", "Projet initial", "Source"]
    got = [t.replace("↕", "").replace("↑", "").replace("↓", "").strip() for t in page.locator("#pv-thead th").all_text_contents()]
    _assert(page, cid, got == expected, f"Colonnes attendues {expected}, observées {got}")


def _case_a8(page, cid):
    lead = _first_lead()
    _home(page)
    row = page.locator(f"#pv-tbody tr[data-num='{lead.get('numero')}']").first
    cells = row.locator("td").all_text_contents()
    _assert(page, cid, lead.get("telephone", "") in cells[4], f"Téléphone cellule={cells[4]!r}, lead={lead.get('telephone')!r}")


def _case_a9(page, cid):
    lead = _first_lead()
    _home(page)
    row = page.locator(f"#pv-tbody tr[data-num='{lead.get('numero')}']").first
    raw = row.locator("td").nth(2).text_content().strip()
    transform = row.locator("td").nth(2).evaluate("el => getComputedStyle(el).textTransform")
    expected = f"{lead.get('nom','')} {lead.get('prenom','')}".strip()
    _assert(page, cid, raw == expected and transform != "uppercase", f"Nom affiché/casse incohérents: raw={raw!r}, expected={expected!r}, CSS={transform!r}")


def _case_a10(page, cid):
    leads, _ = _api_leads()
    _home(page)
    total = int(page.locator("#pv-stats-total").text_content().strip())
    _assert(page, cid, total == len(leads), f"Master total={total}, leads={len(leads)}")


def _case_a11(page, cid):
    _home(page)
    pill = page.locator("#pv-stats-statuts .pv-stats-statut-pill").first
    _assert(page, cid, pill.count() > 0, "Aucune pastille statut")
    pill.click()
    _assert(page, cid, page.locator("#pv-stats-detail .pv-stats-detail-row").count() > 0, "Détail statut non filtré")


def _case_a12(page, cid):
    lead = _first_lead()
    _home(page)
    page.locator(f"#pv-tbody tr[data-num='{lead.get('numero')}']").first.click()
    page.wait_for_selector("#psb-numero")
    _assert(page, cid, page.locator("#psb-numero").text_content().strip() == lead.get("numero"), "Mauvaise fiche ouverte")


def _search_case(field, cid, page):
    lead = _first_lead()
    q = lead.get(field) or lead.get("telephone") or lead.get("email") or lead.get("nom")
    _home(page)
    page.locator("#pv-search").fill(q)
    page.wait_for_timeout(250)
    texts = page.locator("#pv-tbody tr").all_text_contents()
    _assert(page, cid, texts and all(q.lower() in t.lower() or lead.get("numero", "") in t for t in texts), f"Recherche {field} ne filtre pas sur {q}")


def _case_b1(page, cid): _search_case("nom", cid, page)
def _case_b2(page, cid): _search_case("telephone", cid, page)
def _case_b3(page, cid): _search_case("email", cid, page)


def _case_b4(page, cid):
    _home(page)
    sel = page.locator("#pv-stats-filter-statut")
    options = sel.locator("option").all()
    _assert(page, cid, len(options) > 1, "Aucune option statut")
    value = options[1].get_attribute("value")
    sel.select_option(value)
    _assert(page, cid, page.locator("#pv-stats-total").text_content().strip(), "Filtre statut inopérant")


def _case_b5(page, cid):
    _home(page)
    changed = 0
    for selector in ["#pv-stats-filter-categorie", "#pv-stats-filter-source", "#pv-stats-filter-projet"]:
        sel = page.locator(selector)
        options = sel.locator("option").all()
        if len(options) > 1:
            sel.select_option(options[1].get_attribute("value"))
            changed += 1
            page.locator("#pv-stats-reset").click()
    _assert(page, cid, changed == 3, f"Filtres catégorie/source/projet incomplets: {changed}/3")


def _case_c1(page, cid):
    lead = next((l for l in _api_leads()[0] if l.get("numero") == "PR-000001"), {})
    _open_pr(page)
    banner = page.locator("#psb-nom").text_content()
    _assert(page, cid, "PR-000001" in page.locator("#psb-numero").text_content() and lead.get("prenom", "") in banner and lead.get("nom", "").upper() in banner.upper(), f"Bandeau identité incorrect: {banner}")


def _case_c2(page, cid):
    lead = next((l for l in _api_leads()[0] if l.get("numero") == "PR-000001"), {})
    _open_pr(page)
    _assert(page, cid, lead.get("telephone", "") in page.locator("#psb-tel").text_content() and lead.get("email", "") in page.locator("#psb-email").text_content(), "Coordonnées incohérentes")


def _case_c3(page, cid):
    lead = next((l for l in _api_leads()[0] if l.get("numero") == "PR-000001"), {})
    _open_pr(page)
    addr = page.locator('[name="adresse_chantier"]').input_value()
    cp = page.locator('[name="code_postal_chantier"]').input_value()
    city = page.locator('[name="ville_chantier"]').input_value()
    expected_addr = lead.get("adresse_chantier") or ""
    _assert(page, cid, addr == expected_addr and cp == lead.get("cp", "") and (not lead.get("ville") or city == lead.get("ville")), f"Adresse hardcodée/incorrecte: addr={addr!r}, cp={cp!r}, city={city!r}, lead={lead}")


def _case_c4(page, cid):
    lead = next((l for l in _api_leads()[0] if l.get("numero") == "PR-000001"), {})
    _open_pr(page)
    surface = page.locator('[name="surface_logement_m2"]').input_value()
    chauffage = page.locator('[name="mode_chauffage"]').input_value()
    _assert(page, cid, surface == str(lead.get("surface_logement_m2", "")) and chauffage == lead.get("mode_chauffage", ""), f"Surface/chauffage résiduels: {surface=} {chauffage=}")


def _case_c5(page, cid):
    lead = next((l for l in _api_leads()[0] if l.get("numero") == "PR-000001"), {})
    _open_pr(page)
    badge = page.locator("#psb-badge-categorie").text_content() if page.locator("#psb-badge-categorie").count() else ""
    _assert(page, cid, lead.get("categorie", "") in badge or lead.get("categorie", "").upper() in badge, f"Catégorie non alignée: lead={lead.get('categorie')!r}, badge={badge!r}")


def _case_c6(page, cid):
    _open_pr(page)
    buttons = page.locator(".dpe-btn").all_text_contents()
    _assert(page, cid, [b.strip() for b in buttons[:7]] == list("ABCDEFG") and page.get_by_text("Source DPE").is_visible(), "Bloc Source DPE/badges A-G incomplet")


def _case_c7(page, cid):
    _open_pr(page)
    visible_inputs = page.locator("input:visible").evaluate_all("(els) => els.map(e => e.name || e.id).filter(x => /dpe.*(numero|date)|date.*dpe/i.test(x))")
    _assert(page, cid, not visible_inputs, f"N°/Date DPE éditables visibles: {visible_inputs}")


def _case_c8(page, cid):
    _open_pr(page)
    _assert(page, cid, page.locator("#hsp, #hsp-input, [name='hsp']").count() > 0, "HSP absent")


def _case_c9(page, cid):
    _open_pr(page)
    colors = page.locator(".psb-cta-btn").evaluate_all("(els) => els.map(e => getComputedStyle(e).color + '|' + getComputedStyle(e).backgroundColor)")
    _assert(page, cid, len(colors) >= 4 and len(set(colors[:4])) >= 3, f"Couleurs CTA non différenciées: {colors[:4]}")


def _case_c10(page, cid):
    _open_pr(page)
    page.locator(".psb-cta-btn[data-cta='N']").click()
    _assert(page, cid, page.locator("#notes-panel.is-open, #notes-panel.open").count() > 0, "CTA N n'ouvre pas Notes")


def _case_c11(page, cid):
    _open_pr(page)
    page.locator(".psb-cta-btn[data-cta='N']").click()
    page.locator(".psb-cta-btn[data-cta='D']").click()
    _assert(page, cid, page.locator("#documents-panel.is-open, #documents-panel.open").count() > 0 and page.locator("#notes-panel.is-open, #notes-panel.open").count() == 0, "CTA D ne ferme pas Notes/n'ouvre pas Documents")


def _case_c12(page, cid):
    _open_pr(page)
    page.locator(".psb-cta-btn[data-cta='S']").click()
    _assert(page, cid, page.locator("#sim-drawer, .simulations-panel").count() > 0 and page.evaluate("document.body.classList.contains('sim-left-open')"), "Simulateur gauche non ouvert")


def _case_c13(page, cid):
    _open_pr(page)
    page.locator(".psb-cta-btn[data-cta='S']").click()
    left_pad = page.evaluate("parseFloat(getComputedStyle(document.querySelector('.hexa-app-shell__main')).paddingLeft || 0)")
    _assert(page, cid, left_pad > 0, "Le simulateur recouvre au lieu de pousser la fiche")


def _case_c14(page, cid):
    _open_pr(page)
    link = page.get_by_text("← Retour à la liste")
    _assert(page, cid, link.count() > 0 and link.first.is_visible(), "Bouton retour absent")
    pos = link.first.evaluate("el => getComputedStyle(el).position")
    _assert(page, cid, pos != "sticky", f"Bouton retour sticky: {pos}")


def _case_c15(page, cid):
    _open_pr(page)
    page.get_by_text("← Retour à la liste").first.click()
    page.wait_for_function("document.body.classList.contains('hexa-view-prospects')")


def _case_d1(page, cid):
    _new(page)
    _assert(page, cid, page.locator("#psb-numero").text_content().strip() == "PR-NOUVEAU", "Nouvelle fiche non ouverte")


def _case_d2(page, cid):
    _new(page)
    filled = page.locator("#form-prospect input:not([type='hidden']):visible").evaluate_all("(els) => els.filter(e => e.value).map(e => `${e.name || e.id}=${e.value}`)")
    _assert(page, cid, not filled, f"Champs préremplis sur nouveau prospect: {filled[:10]}")


def _case_d3(page, cid):
    _new(page)
    body_values = page.locator("#form-prospect").evaluate("(f) => f.innerText + ' ' + Array.from(f.elements).map(e => e.value).join(' ')")
    bad = [v for v in ["12 rue", "154", "fioul", "BRETAGNE", "Jean-François"] if v.lower() in body_values.lower()]
    _assert(page, cid, not bad, f"Valeurs hardcodées présentes: {bad}")


def _case_d4(page, cid):
    _new(page)
    _assert(page, cid, "PR-NOUVEAU" in page.locator("#psb-numero").text_content(), "Bandeau nouveau incorrect")


def _case_d5(page, cid):
    _new(page)
    page.locator(".psb-cta-btn[data-cta='S']").click()
    txt = page.locator("#sim-drawer-content, .simulations-panel").first.text_content(timeout=5000)
    bad = [v for v in ["154", "fioul", "BRETAGNE"] if v.lower() in txt.lower()]
    _assert(page, cid, not bad, f"Simulateur nouveau contaminé: {bad}")


def _fill_minimal_new(page):
    _new(page)
    page.locator('[name="nom"]').fill("TESTAUDIT")
    page.locator('[name="prenom"]').fill("Marie")
    page.locator('[name="telephone"]').fill("0611111111")


def _case_d6(page, cid):
    _fill_minimal_new(page)
    _assert(page, cid, page.locator('[name="nom"]').input_value() == "TESTAUDIT" and page.locator('[name="prenom"]').input_value() == "Marie", "Saisie minimale impossible")


def _case_d7(page, cid):
    _fill_minimal_new(page)
    page.locator("#btn-save").click()
    page.wait_for_timeout(1000)
    text = page.locator("body").text_content()
    _assert(page, cid, "Not Found" not in text, "Popup Not Found visible")


def _case_d8(page, cid):
    requests = []
    page.on("request", lambda req: requests.append((req.method, req.url)))
    _fill_minimal_new(page)
    page.locator("#btn-save").click()
    page.wait_for_timeout(1500)
    posts = [u for m, u in requests if m == "POST" and "/api/leads" in u]
    _assert(page, cid, posts, f"Aucun POST /api/leads envoyé: {requests[-5:]}")


def _case_d9(page, cid):
    local = json.loads((ROOT / "data" / "leads.json").read_text(encoding="utf-8"))
    _assert(page, cid, any(l.get("nom") == "TESTAUDIT" and l.get("prenom") == "Marie" for l in local), "data/leads.json local ne contient pas TESTAUDIT/Marie après test sur cible distante")


def _case_d10(page, cid):
    _fill_minimal_new(page)
    page.locator("#btn-save").click()
    page.wait_for_timeout(1500)
    page.get_by_text("Accueil").click()
    page.wait_for_timeout(500)
    _assert(page, cid, page.locator("#pv-tbody").text_content().find("TESTAUDIT") >= 0, "Prospect créé absent du tableau sans rechargement manuel")


def _open_sim(page):
    _open_pr(page)
    page.locator(".psb-cta-btn[data-cta='S']").click()
    page.wait_for_timeout(1000)


def _case_e1(page, cid):
    _open_sim(page)
    txt = page.locator("#sim-drawer-content, .simulations-panel").first.text_content()
    _assert(page, cid, "154" in txt and "fioul" in txt.lower(), "Sous-bloc repris fiche ne reprend pas les valeurs affichées de la fiche")


def _case_e2(page, cid):
    _open_sim(page)
    forced = page.locator("#sim-surface-chauffee, input").evaluate_all("(els) => els.map(e => [e.id, e.value]).filter(x => /surf/i.test(x[0]))")
    txt = page.locator("#sim-drawer-content, .simulations-panel").first.text_content()
    _assert(page, cid, "138" in txt or any("138" in str(v) for _, v in forced), "Surface chauffée 154 x 0.9 (=138.6) non visible")


def _case_e3(page, cid):
    _open_sim(page)
    labels = page.locator("#sim-drawer-content, .simulations-panel").first.text_content()
    _assert(page, cid, all(x in labels for x in ["Toit", "Mur", "Menuiserie"]), "Listes isolation absentes")


def _case_e4(page, cid):
    _open_sim(page)
    txt = page.locator("#sim-drawer-content, .simulations-panel").first.text_content()
    _assert(page, cid, "2.5" in txt or "2,5" in txt, "HSP ou défaut 2.5 absent")


def _case_e5(page, cid):
    _open_sim(page)
    before = page.locator("#sim-drawer-content, .simulations-panel").first.text_content()
    select = page.locator("#iso-toit, select[name='iso_toit']").first
    _assert(page, cid, select.count() > 0, "Select isolation toit absent")
    select.select_option(index=select.locator("option").count() - 1)
    page.wait_for_timeout(500)
    after = page.locator("#sim-drawer-content, .simulations-panel").first.text_content()
    _assert(page, cid, before != after, "Changer isolation ne recalcule pas l'affichage")


def _case_e6(page, cid):
    _open_sim(page)
    opts = page.locator(".sim-model-select option").all_text_contents()
    _assert(page, cid, opts and all(("TRI" not in o.upper()) and ("DUO" not in o.upper()) for o in opts if o.strip()), f"Modèles non compatibles présents: {opts}")


def _case_e7(page, cid):
    _open_sim(page)
    page.locator("[data-value='triphase']").first.click()
    page.wait_for_timeout(500)
    opts = page.locator(".sim-model-select option").all_text_contents()
    _assert(page, cid, opts and all("TRI" in o.upper() for o in opts if o.strip() and "—" not in o), f"Triphasé affiche des modèles non TRI: {opts}")


def _case_e8(page, cid):
    _open_sim(page)
    service = page.locator("#sim-service, select").filter(has_text="Chauffage").first
    if service.count():
        try:
            service.select_option("chauffage_ecs")
        except Exception:
            service.select_option(index=1)
    page.wait_for_timeout(500)
    opts = page.locator(".sim-model-select option").all_text_contents()
    _assert(page, cid, opts and all("DUO" in o.upper() for o in opts if o.strip() and "—" not in o), f"Chauffage+ECS affiche des modèles non DUO: {opts}")


def _case_e9(page, cid):
    _open_sim(page)
    page.get_by_text("Voir la note de dimensionnement").click(timeout=5000)
    _assert(page, cid, page.locator(".sim-dim-modal").count() > 0, "Modale dimensionnement absente")


def _case_e10(page, cid):
    _open_sim(page)
    baremes = _api("/api/baremes")[1]
    txt = page.locator("#sim-drawer-content, .simulations-panel").first.text_content()
    any_amount = any(str(v) in txt.replace("\u202f", " ").replace(" ", "") for bucket in baremes.values() for tranche in bucket.values() for aid in tranche.values() for zone in aid.values() for v in zone.values())
    _assert(page, cid, any_amount, "Aucune aide affichée ne correspond aux barèmes")


def _case_e11(page, cid):
    _open_sim(page)
    txt = page.locator("#sim-drawer-content, .simulations-panel").first.text_content().lower()
    _assert(page, cid, "marge" not in txt, "Marge affichée au client")


def _case_e12(page, cid):
    _open_sim(page)
    _assert(page, cid, page.get_by_text("Envoyer le pré-devis").count() > 0, "Bouton Envoyer le pré-devis absent")


def _case_f1(page, cid):
    _home(page)
    page.locator("#pv-admin").click()
    _assert(page, cid, page.locator("#hexa-admin, .adm-overlay, .adm-panel").count() > 0 or page.get_by_text("Admin").count() > 0, "Admin ne s'ouvre pas")


def _case_f2(page, cid):
    _case_f1(page, cid)
    txt = page.locator("body").text_content()
    _assert(page, cid, "ALFÉA" in txt or "EXCELLIA" in txt, "Catalogue PAC non listé dans admin")


def _case_f3(page, cid):
    global _ORIGINAL_CATALOGUE, _CATALOGUE_CHANGED
    status, cat, _ = _api("/api/catalogue-pac")
    _assert(page, cid, status == 200 and isinstance(cat, list) and cat, "Catalogue API invalide")
    _ORIGINAL_CATALOGUE = cat
    modified = json.loads(json.dumps(cat))
    modified[0]["ttc"] = float(modified[0].get("ttc", 0)) + 1
    st, payload, _ = _api("/api/catalogue-pac", method="POST", data=modified)
    _CATALOGUE_CHANGED = st == 200
    _assert(page, cid, st == 200 and payload.get("ok"), f"Sauvegarde catalogue échoue: {st} {payload}")


def _case_f4(page, cid):
    status, cat, _ = _api("/api/catalogue-pac")
    _assert(page, cid, status == 200 and _ORIGINAL_CATALOGUE and cat[0]["ttc"] == _ORIGINAL_CATALOGUE[0]["ttc"] + 1, "Prix PAC modifié non persistant via API")


def _case_f5(page, cid):
    _case_f1(page, cid)
    txt = page.locator("body").text_content()
    expected = str(int(_ORIGINAL_CATALOGUE[0]["ttc"] + 1)) if _ORIGINAL_CATALOGUE else ""
    _assert(page, cid, expected and expected in txt.replace(" ", ""), f"Prix modifié {expected} non visible après rechargement admin")


def _case_f6(page, cid):
    browser = page.context.browser
    ctx = browser.new_context()
    p = ctx.new_page()
    try:
        _case_f5(p, cid)
    finally:
        ctx.close()


def _case_f7(page, cid):
    _case_f1(page, cid)
    txt = page.locator("body").text_content().lower()
    found = [x for x in ["paramètres", "modèles", "pac", "régie", "marge", "tva"] if x in txt]
    _assert(page, cid, len(found) >= 4, f"Blocs admin incomplets: {found}")


def _case_f8(page, cid):
    _open_sim(page)
    txt = page.locator("#sim-drawer-content, .simulations-panel").first.text_content().lower()
    _assert(page, cid, "45.5" not in txt and "tva" not in txt, "Impossible de prouver l'utilisation des paramètres admin dans le simulateur client")


def _case_g1(page, cid):
    _home(page)
    _assert(page, cid, page.get_by_text("Importer Excel").is_visible(), "Bouton Importer Excel invisible")


def _case_g2(page, cid):
    _assert(page, cid, FIXTURE_XLSX.exists() and FIXTURE_XLSX.stat().st_size > 0, "Fixture xlsx absente")


def _case_g3(page, cid):
    _home(page)
    page.locator("#pv-import-file").set_input_files(str(FIXTURE_XLSX))
    page.wait_for_timeout(2000)
    _assert(page, cid, "Import impossible" not in page.locator("body").text_content(), "Import affiche une erreur")


def _case_g4(page, cid):
    _home(page)
    txt = page.locator("#pv-tbody").text_content()
    _assert(page, cid, all(x in txt for x in ["IMPORTAUDIT1", "IMPORTAUDIT2", "IMPORTAUDIT3"]), "Les 3 leads importés ne sont pas au tableau")


def _case_g5(page, cid):
    notes = json.loads((ROOT / "data" / "notes.json").read_text(encoding="utf-8"))
    found = json.dumps(notes, ensure_ascii=False)
    _assert(page, cid, "Note import audit 1" in found, "data/notes.json local ne contient pas les notes importées sur cible distante")


def _case_h1(page, cid):
    st, payload, elapsed = _api("/api/leads")
    _assert(page, cid, st == 200 and isinstance(payload, list) and elapsed < 3, f"/api/leads: {st}, {elapsed:.2f}s")


def _case_h2(page, cid):
    st, payload, elapsed = _api("/api/catalogue-pac")
    _assert(page, cid, st == 200 and isinstance(payload, list) and elapsed < 3, f"/api/catalogue-pac: {st}, {elapsed:.2f}s")


def _case_h3(page, cid):
    st, payload, elapsed = _api("/api/baremes")
    _assert(page, cid, st == 200 and isinstance(payload, dict) and elapsed < 3, f"/api/baremes: {st}, {elapsed:.2f}s")


def _case_h4(page, cid):
    payload = {"nom": "APIAUDIT", "prenom": "Mini", "telephone": "0600000000"}
    st, body, elapsed = _api("/api/leads", method="POST", data=payload)
    _assert(page, cid, st in (200, 201) and body.get("ok") and elapsed < 3, f"POST /api/leads: {st} {body}")


def _case_h5(page, cid):
    st, cat, _ = _api("/api/catalogue-pac")
    st2, body, elapsed = _api("/api/catalogue-pac", method="POST", data=cat)
    _assert(page, cid, st == 200 and st2 == 200 and body.get("ok") and elapsed < 3, f"POST catalogue: {st2} {body}")


def _case_h6(page, cid):
    data = urllib.parse.urlencode({"texte": "Note API audit"}).encode()
    req = urllib.request.Request(TARGET_URL + "/prospect/PR-000001/commentaire-ajax", data=data, method="POST", headers={"Content-Type": "application/x-www-form-urlencoded"})
    started = time.monotonic()
    with urllib.request.urlopen(req, timeout=10) as resp:
        body = json.loads(resp.read().decode())
        elapsed = time.monotonic() - started
    _assert(page, cid, resp.status == 200 and body.get("ok") and elapsed < 3, f"POST note: {resp.status} {body}")


def _case_h7(page, cid):
    st, body, elapsed = _api("/prospect/PR-000001/commentaires-json")
    _assert(page, cid, st == 200 and isinstance(body.get("commentaires"), list) and elapsed < 3, f"GET notes: {st} {body}")


def _case_h8(page, cid):
    routes = ["/api/leads", "/api/catalogue-pac", "/api/baremes", "/prospect/PR-000001/commentaires-json"]
    timings = {r: _api(r)[2] for r in routes}
    _assert(page, cid, all(v < 3 for v in timings.values()), f"Routes lentes: {timings}")


def _case_i1(page, cid):
    payload = {"nom": "COHERENCE", "prenom": "Alice", "telephone": "0601010101", "email": "alice.audit@example.test", "cp": "75001", "ville": "Paris"}
    st, body, _ = _api("/api/leads", method="POST", data=payload)
    _assert(page, cid, st == 200 and body.get("lead", {}).get("nom") == "COHERENCE", f"Création incohérente: {st} {body}")
    numero = body.get("numero")
    _home(page)
    page.locator(f"#pv-tbody tr[data-num='{numero}']").first.click()
    _assert(page, cid, page.locator('[name="nom"]').input_value() == "COHERENCE" and page.locator('[name="telephone"]').input_value() == "0601010101", "Fiche créée incohérente avec saisie")


def _case_i2(page, cid):
    st, leads, _ = _api("/api/leads")
    numero = leads[0]["numero"]
    changed = dict(leads[0])
    changed["telephone"] = "0699999999"
    st2, body, _ = _api(f"/api/leads/{numero}", method="POST", data=changed)
    st3, leads2, _ = _api("/api/leads")
    _assert(page, cid, st == st2 == st3 == 200 and any(l.get("numero") == numero and l.get("telephone") == "0699999999" for l in leads2), "Modification prospect non persistante")


def _case_i3(page, cid):
    _case_h6(page, cid)
    notes = json.loads((ROOT / "data" / "notes.json").read_text(encoding="utf-8"))
    _assert(page, cid, "Note API audit" in json.dumps(notes, ensure_ascii=False), "Note ajoutée absente de data/notes.json local sur cible distante")


def _case_i4(page, cid):
    leads, _ = _api_leads()
    nums = [l.get("numero") for l in leads]
    _assert(page, cid, len(nums) == len(set(nums)) and all(nums), "Doublons ou numéros fantômes dans /api/leads")


def _case_i5(page, cid):
    _home(page)
    counts = page.locator(".pv-nrp-count").all_text_contents()
    last = page.locator("#pv-tbody tr td:nth-child(10)").all_text_contents()
    _assert(page, cid, len(counts) == len(last) and all(c.isdigit() for c in counts), f"Compteurs NRP incohérents: counts={counts[:5]}, last={last[:5]}")


CASES = [
    ("A.1", "La page se charge en moins de 3s", _case_a1),
    ("A.2", "Logo Hexa Rénov' valide", _case_a2),
    ("A.3", "Titre Prospects visible", _case_a3),
    ("A.4", "Aucune erreur JS console", _case_a4),
    ("A.5", "Aucune scrollbar horizontale", _case_a5),
    ("A.6", "Nombre de leads cohérent API", _case_a6),
    ("A.7", "12 colonnes visibles", _case_a7),
    ("A.8", "Cellules correspondent au lead", _case_a8),
    ("A.9", "Convention de casse nom/prénom", _case_a9),
    ("A.10", "Master total cohérent", _case_a10),
    ("A.11", "Pastille statut filtre détail", _case_a11),
    ("A.12", "Ligne ouvre bonne fiche", _case_a12),
    ("B.1", "Recherche par nom", _case_b1),
    ("B.2", "Recherche par téléphone", _case_b2),
    ("B.3", "Recherche par email", _case_b3),
    ("B.4", "Filtre statut master", _case_b4),
    ("B.5", "Filtres catégorie/source/projet master", _case_b5),
    ("C.1", "Bandeau identité PR-000001", _case_c1),
    ("C.2", "Coordonnées prospect", _case_c2),
    ("C.3", "Adresse/CP/ville prospect", _case_c3),
    ("C.4", "Surface/type/chauffage prospect", _case_c4),
    ("C.5", "Catégorie ANAH/CEE prospect", _case_c5),
    ("C.6", "Source DPE badges A-G", _case_c6),
    ("C.7", "N° DPE et Date DPE non éditables", _case_c7),
    ("C.8", "HSP présent Bloc 4/5", _case_c8),
    ("C.9", "CTA N/E/D/S couleurs", _case_c9),
    ("C.10", "CTA N ouvre Notes", _case_c10),
    ("C.11", "CTA D ferme N et ouvre Documents", _case_c11),
    ("C.12", "CTA S ouvre simulateur à gauche", _case_c12),
    ("C.13", "Panneaux poussent la main", _case_c13),
    ("C.14", "Retour visible non sticky", _case_c14),
    ("C.15", "Retour accueil", _case_c15),
    ("D.1", "Nouveau ouvre fiche neuve", _case_d1),
    ("D.2", "Champs nouveau vides/neutres", _case_d2),
    ("D.3", "Aucune valeur hardcodée nouveau", _case_d3),
    ("D.4", "Bandeau PR-NOUVEAU", _case_d4),
    ("D.5", "Simulateur nouveau sans contamination", _case_d5),
    ("D.6", "Saisie minimale Nom/Prénom/Tél", _case_d6),
    ("D.7", "Save minimal sans Not Found", _case_d7),
    ("D.8", "POST création envoyé", _case_d8),
    ("D.9", "data/leads.json contient TESTAUDIT", _case_d9),
    ("D.10", "Auto-refresh accueil après création", _case_d10),
    ("E.1", "Simulateur reprend vraies valeurs", _case_e1),
    ("E.2", "Surface chauffée = 0.9 habitable", _case_e2),
    ("E.3", "Listes isolation visibles", _case_e3),
    ("E.4", "HSP lu ou défaut 2.5", _case_e4),
    ("E.5", "Isolation recalcule puissance", _case_e5),
    ("E.6", "Dropdown PAC compatible", _case_e6),
    ("E.7", "Triphasé => TRI uniquement", _case_e7),
    ("E.8", "Chauffage+ECS => DUO uniquement", _case_e8),
    ("E.9", "Note dimensionnement modale", _case_e9),
    ("E.10", "Aides cohérentes baremes", _case_e10),
    ("E.11", "Marge non affichée client", _case_e11),
    ("E.12", "Bouton envoyer pré-devis", _case_e12),
    ("F.1", "Admin s'ouvre", _case_f1),
    ("F.2", "Admin liste modèles PAC", _case_f2),
    ("F.3", "Modifier prix PAC sauvegarde", _case_f3),
    ("F.4", "Prix persiste API catalogue", _case_f4),
    ("F.5", "Recharger admin prix modifié", _case_f5),
    ("F.6", "Persistance cross-session admin", _case_f6),
    ("F.7", "Lister blocs admin", _case_f7),
    ("F.8", "Paramètres admin utilisés simulateur", _case_f8),
    ("G.1", "Bouton Importer Excel visible", _case_g1),
    ("G.2", "Fixture Excel 3 leads", _case_g2),
    ("G.3", "Upload Excel succès", _case_g3),
    ("G.4", "3 leads importés au tableau", _case_g4),
    ("G.5", "Notes importées dans notes.json", _case_g5),
    ("H.1", "GET /api/leads", _case_h1),
    ("H.2", "GET /api/catalogue-pac", _case_h2),
    ("H.3", "GET /api/baremes", _case_h3),
    ("H.4", "POST /api/leads minimal", _case_h4),
    ("H.5", "POST /api/catalogue-pac", _case_h5),
    ("H.6", "POST commentaire ajax", _case_h6),
    ("H.7", "GET commentaires json", _case_h7),
    ("H.8", "Routes <3s", _case_h8),
    ("I.1", "Créer prospect et ouvrir cohérent", _case_i1),
    ("I.2", "Modifier prospect persiste", _case_i2),
    ("I.3", "Ajouter note dans notes.json", _case_i3),
    ("I.4", "Aucun prospect fantôme/doublon", _case_i4),
    ("I.5", "Compteurs NRP cohérents", _case_i5),
]


@pytest.mark.parametrize("case_id,title,func", CASES, ids=[c[0] for c in CASES])
def test_audit_maxi_case(page, case_id, title, func):
    try:
        func(page, case_id.replace(".", "_"))
    except Exception as exc:
        screenshot = _shot(page, case_id.replace(".", "_"))
        _log(case_id, title, "FAIL", str(exc), screenshot)
        raise
    _log(case_id, title, "PASS")
