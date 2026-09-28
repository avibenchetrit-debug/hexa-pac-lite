# -*- coding: utf-8 -*-
"""Contrôle final : parcours complet d'un vrai appel, en local, sur une fiche FABRIQUÉE.
ADEME / BAN / DVF simulés (monkeypatch en mémoire + page.route), envoi e-mail simulé (module resend factice :
aucun message ne part). Usage, depuis la racine du dépôt : python scripts/e2e_appel_local.py
Écrit un rapport OK/KO par étape, les erreurs de console, et tout texte anglais ou date ISO vu à l'écran."""
import json
import os
import re
import socket
import sys
import tempfile
import threading
import time
import types
from datetime import date, timedelta

REPO = sys.argv[1] if len(sys.argv) > 1 else os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TMP = tempfile.mkdtemp(prefix="hexa-e2e-")
os.environ.update(DATA_DIR=TMP, USERS_PATH=os.path.join(TMP, "users.json"), AUTH_ENFORCE="0", RESEND_API_KEY="cle-factice-locale")
os.environ.pop("RAILWAY_ENVIRONMENT", None)
os.chdir(REPO)
sys.path.insert(0, REPO)
ENVOIS = []
resend = types.ModuleType("resend")
resend.Emails = types.SimpleNamespace(send=lambda msg: ENVOIS.append(msg) or {"id": f"factice-{len(ENVOIS)}"})
sys.modules["resend"] = resend

import main  # noqa: E402
import uvicorn  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402
from services import dpe_audit, valeur_dvf  # noqa: E402

LAT, LON = 48.8660, 2.3410
DPE = {"numero_dpe": "2475E0000001A", "date_etablissement_dpe": "2024-03-15", "etiquette_dpe": "F", "type_batiment": "maison",
       "methode_application_dpe": "dpe maison individuelle", "surface_habitable_logement": 118.4, "hauteur_sous_plafond": 2.5,
       "nombre_niveau_logement": 2, "annee_construction": "", "periode_construction": "1948-1974", "conso_5_usages_par_m2_ep": 331,
       "emission_ges_5_usages_par_m2": 70, "cout_chauffage": 2280, "cout_ecs": 360, "type_energie_principale_chauffage": "Fioul domestique",
       "qualite_isolation_murs": "insuffisante", "qualite_isolation_plancher_haut_comble_perdu": "moyenne", "qualite_isolation_menuiseries": "bonne",
       "adresse_ban": "12 Rue Imaginaire 75002 Paris", "numero_voie_ban": "12", "nom_rue_ban": "Rue Imaginaire", "_geopoint": f"{LAT},{LON}"}
BAN = {"features": [{"type": "Feature", "geometry": {"type": "Point", "coordinates": [LON, LAT]},
                     "properties": {"label": "12 Rue Imaginaire 75002 Paris", "housenumber": "12", "street": "Rue Imaginaire",
                                    "name": "12 Rue Imaginaire", "postcode": "75002", "city": "Paris", "citycode": "75102"}}]}
dpe_audit.GET = lambda url, timeout: BAN if "api-adresse" in url else {"results": [] if "audit-opendata" in url else [DPE]}
valeur_dvf.prix_m2 = lambda *a, **k: {"ok": True, "prix_m2": 10500, "q1": 9250, "q3": 11750, "nb": 6, "commune": "Paris 2e Arrondissement",
                                      "type": "Maison", "periode": "2024-2026", "source": "médiane de 6 ventes de maisons à Paris 2e Arrondissement, 2024-2026"}
# délégataires comme au lot 6e : PICOTY (attente MPR) et ACE (tout de suite)
main._atomic_write_json(main.DELEGATAIRES_PATH, [{"nom": "PICOTY", "mwh_precaire": 12.5, "mwh_classique": 7.2, "actif": False},
                                                 {"nom": "ACE", "mwh_precaire": 14, "mwh_classique": 7.5, "actif": True}])
main._write_users([{"id": "testeur", "username": "testeur", "password_hash": main._hash_password("essai-local"),
                    "role": "admin", "actif": True, "cree_at": main._now_iso(), "visibilite": "tous"}])

with socket.socket() as so:
    so.bind(("127.0.0.1", 0))
    PORT = so.getsockname()[1]
BASE = f"http://127.0.0.1:{PORT}"
srv = uvicorn.Server(uvicorn.Config(main.app, host="127.0.0.1", port=PORT, log_level="warning"))
threading.Thread(target=srv.run, daemon=True).start()
while not srv.started:
    time.sleep(0.05)

RAPPORT, CONSOLE, ECRAN, PG = [], [], [], []
ANGLAIS = re.compile(r"\b(undefined|null|NaN|Invalid Date|Loading|Error|Save|Cancel|Submit|Close|Delete|Search|Settings|Next|Previous|Download|Upload)\b")
ISO = re.compile(r"\b\d{4}-\d{2}-\d{2}(?:T\d{2}:\d{2})?\b")


def etape(nom, fn):
    t0 = time.time()
    try:
        detail = fn() or ""
        RAPPORT.append(("OK", nom, str(detail)))
    except Exception as exc:  # noqa: BLE001
        RAPPORT.append(("KO", nom, f"{exc.__class__.__name__}: {str(exc).splitlines()[0][:200]}"))
        try:
            PG[0].screenshot(path=os.path.join(TMP, f"ko_{len(RAPPORT)}.png"))
        except Exception:  # noqa: BLE001
            pass
    print(f"[{RAPPORT[-1][0]}] {nom} ({time.time() - t0:.1f}s) {RAPPORT[-1][2]}", flush=True)


def lire_ecran(pg, ou):
    txt = pg.evaluate("document.body.innerText")
    for m in set(ANGLAIS.findall(txt)):
        ECRAN.append((ou, "anglais", m))
    for m in set(ISO.findall(txt)):
        ECRAN.append((ou, "date ISO", m))


def val(pg, n):
    return pg.evaluate("n => String(document.querySelector(`#form-prospect [name='${n}']`)?.value ?? '')", n)


REMPLIR = """(vals) => { for (const [n, v] of Object.entries(vals)) { const el = document.querySelector(`#form-prospect [name="${n}"]`);
  if (!el) continue; el.value = v; el.dispatchEvent(new Event('input', { bubbles: true })); el.dispatchEvent(new Event('change', { bubbles: true })); } }"""

with sync_playwright() as p:
    b = p.chromium.launch()
    ctx = b.new_context(accept_downloads=True, viewport={"width": 1440, "height": 900})

    def exterieur(route):
        u = route.request.url
        if u.startswith(BASE):
            return route.continue_()
        if "api-adresse.data.gouv.fr" in u:
            return route.fulfill(status=200, content_type="application/json", body=json.dumps(BAN))
        if "geo.api.gouv.fr" in u:
            return route.fulfill(status=200, content_type="application/json", body='[{"nom":"Paris","code":"75056","codesPostaux":["75002"]}]')
        return route.abort()
    ctx.route("**/*", exterieur)
    pg = ctx.new_page()
    PG.append(pg)
    pg.on("console", lambda m: m.type == "error" and CONSOLE.append(m.text[:200]))
    pg.on("pageerror", lambda e: CONSOLE.append("pageerror: " + str(e)[:200]))
    pg.on("dialog", lambda d: d.accept())
    pg.goto(BASE + "/login")
    pg.fill("#username", "testeur"); pg.fill("#password", "essai-local"); pg.click("#login-btn")
    pg.wait_for_url(lambda u: "/login" not in u)
    etat = {}

    def aller(n):
        for _ in range(10):
            pg.evaluate(f"window.hexaParcoursEtape({n})")
            pg.wait_for_timeout(300)
            if pg.query_selector("#p6-aside .p6-aside-mini"):
                pg.click("#p6-aside .p6-aside-mini")
            if pg.evaluate(f"(document.querySelector('#p6-aside .p6-ak') || {{}}).textContent === \"ACCOMPAGNATEUR D'APPEL · ÉTAPE {n}\""):
                return
        raise AssertionError(f"étape {n} non affichée")

    def s1():
        pg.goto(BASE + "/nouveau")
        pg.wait_for_function("typeof window.hexaParcoursEtape === 'function'")
        pg.wait_for_timeout(800)
        aller(1)
        pg.click("#p6-aside-corps [data-p6-nrp]")
        pg.wait_for_selector("#p6-aside-corps .p6-nrp-msg")
        assert pg.inner_text("#p6-aside-corps .p6-nrp-msg") == "Enregistrez la fiche pour compter le NRP."
        pg.evaluate(REMPLIR, {"civilite": "Madame", "nom": "Fabrique", "prenom": "Fanny", "telephone": "0600000051",
                              "email": "fabrique@example.invalid"})
        assert pg.evaluate("window.hexaEnregistrerFiche()") is not False
        pg.wait_for_function("(document.body.dataset.prospectNumero || '').startsWith('PR-')")
        etat["n"] = pg.evaluate("document.body.dataset.prospectNumero")
        lire_ecran(pg, "étape 1 (nouvelle fiche)")
        return f"fiche {etat['n']} créée ; NRP avant enregistrement : message clair"
    etape("1. Nouvelle fiche", s1)

    def s2():
        aller(1)
        pg.click("#p6-aside-corps [data-p6-nrp]")
        pg.wait_for_function("(document.querySelector('#p6-aside-corps .p6-nrp-msg') || {}).textContent === 'NRP enregistré (1/8)'", timeout=15000)
        return pg.inner_text("#p6-aside-corps .p6-nrp-cpt")
    etape("2. NRP depuis l'accompagnateur", s2)

    def s3():
        pg.click("#p6-aside-corps .p6-nrp-msg + [data-p6-rappel]")
        pg.wait_for_function("document.activeElement && document.activeElement.id === 'suivi-rap-date'")
        demain = (date.today() + timedelta(days=1)).isoformat()
        pg.fill("#suivi-rap-date", demain); pg.fill("#suivi-rap-heure", "10:00"); pg.fill("#suivi-rap-motif", "Rappel test")
        pg.click("#suivi-rap-poser")
        pg.wait_for_timeout(800)
        lead = pg.request.get(f"{BASE}/api/leads/{etat['n']}").json()
        assert (lead.get("rappel") or {}).get("date") == demain, lead.get("rappel")
        lire_ecran(pg, "fin d'appel (rappel)")
        return f"rappel du {date.fromisoformat(demain):%d/%m/%Y} à 10h00 enregistré"
    etape("3. Rappel", s3)

    def s4():
        pg.goto(f"{BASE}/prospect/{etat['n']}")
        pg.wait_for_function(f"document.body.dataset.prospectNumero === '{etat['n']}' && typeof window.hexaParcoursEtape === 'function'")
        pg.wait_for_timeout(800)
        aller(1)
        assert pg.inner_text("#p6-aside-corps .p6-nrp-cpt") == "1 / 8 appels"
        assert "Bonjour Madame Fabrique" in pg.inner_text("#p6-aside-corps")
        lire_ecran(pg, "reprise de la fiche")
        return "compteur 1 / 8 et accroche personnalisée retrouvés"
    etape("4. Reprise de la fiche", s4)

    def s5():
        aller(2)
        pg.fill("#input-adresse", "12 rue imaginaire")
        pg.wait_for_selector("#ban-suggestions .ban-suggestion-item")
        pg.dispatch_event("#ban-suggestions .ban-suggestion-item", "mousedown")
        pg.wait_for_selector("#dpe-banner .hx-dpe--auto", timeout=20000)
        pg.keyboard.press("Escape")
        pg.evaluate("window.closeParcelDrawer && window.closeParcelDrawer()")
        assert (val(pg, "dpe_numero"), val(pg, "surface_logement_m2"), val(pg, "mode_chauffage")) == ("2475E0000001A", "118", "fioul")
        pg.wait_for_function("document.querySelector('[name=prix_m2_estime]').value === '10500'")
        lire_ecran(pg, "étape 2 (DPE)")
        return "DPE retenu, champs remplis, prix au m² DVF, coût " + val(pg, "cout_energetique_mensuel_eur") + " €/mois"
    etape("5. Adresse avec DPE trouvé", s5)

    def s6():
        pg.evaluate(REMPLIR, {"type_emetteurs": "radiateurs_classiques", "ecs": "chaudiere", "alimentation_electrique": "monophase",
                              "nombre_personnes": "4", "rfr": "15000", "usage_bien": "proprietaire_occupant"})
        vus = []
        for n in range(1, 7):
            aller(n)
            vus.append(pg.inner_text("#p6-aside .p6-at"))
            lire_ecran(pg, f"étape {n}")
            assert pg.evaluate("document.scrollingElement.scrollHeight <= window.innerHeight + 1"), f"défilement à l'étape {n}"
        return " → ".join(vus)
    etape("6. Les 6 étapes", s6)

    def mention(variante):
        return pg.request.get(f"{BASE}/api/devis/{etat['n']}/preview?variante={variante}").text()

    def mode_mpr(m):
        aller(6)
        pg.click(f"[data-mode-mpr={m}]")
        fin = time.time() + 15
        while time.time() < fin and pg.request.get(f"{BASE}/api/simulateur/{etat['n']}/state").json().get("mode_mpr") != m:
            time.sleep(0.3)

    def s7():
        aller(6)
        assert pg.evaluate("window.hexaEnregistrerFiche()") is not False      # la fiche complétée est enregistrée
        pg.wait_for_timeout(1500)
        mode_mpr("attente")
        h_att = mention("pre_devis")
        mode_mpr("sans_attente")
        h_sans = mention("pre_devis")
        mode_mpr("attente")
        aller(6)
        pg.click("#btn-voir-devis")
        pg.wait_for_selector("#devis-pdf-btn", timeout=30000)
        titre = pg.inner_text(".devis-modal-title")
        import html as _h
        txt = lambda h: re.sub(r"\s+", " ", _h.unescape(re.sub(r"<[^>]+>", " ", h)))
        qui = lambda h: [x for x in ("PICOTY", "ACE ÉNERGIE", "Picoty", "ACE Énergie") if x in txt(h)]
        etat["mention"] = (qui(h_att), qui(h_sans), pg.request.get(f"{BASE}/api/simulateur/{etat['n']}/state").json().get("mode_mpr"))
        assert "Picoty" in txt(h_att) and "ACE" not in txt(h_att), f"attente : PICOTY attendu, trouvé {etat['mention']}"
        assert "ACE" in txt(h_sans) and "Picoty" not in txt(h_sans), f"tout de suite : ACE attendu, trouvé {etat['mention']}"
        lire_ecran(pg, "fenêtre du pré-devis")
        return f"{titre} ; attente MPR → PICOTY, tout de suite → ACE"
    etape("7. Voir le devis (pré-devis, PICOTY / ACE)", s7)

    def s8():
        with pg.expect_download(timeout=90000) as dl:
            pg.click("#devis-pdf-btn")
        d = dl.value
        assert re.fullmatch(r"Pre-devis_PD\d{4}-[0-9A-Z-]+\.pdf", d.suggested_filename) and os.path.getsize(d.path()) > 1000
        pg.click("#devis-close-btn")
        return d.suggested_filename
    etape("8. PDF du pré-devis", s8)

    def s9():
        pg.click("#p-suivi-btn")
        pg.wait_for_selector("#p-suivi-pop .fiche-vt-valider", state="visible")
        pg.click("#p-suivi-pop .fiche-vt-valider")
        pg.wait_for_function("document.body.dataset.vtValidee === '1'", timeout=15000)
        pg.wait_for_timeout(800)
        if pg.is_visible("#p-suivi-pop"):
            pg.click("#p-suivi-pop .p6-pop-fermer")
        return "VT validée"
    etape("9. Validation de la VT dans Suivi", s9)

    def s10():
        aller(6)
        pg.wait_for_selector("#btn-note-definitive", state="visible")
        pg.click("#btn-note-definitive")
        pg.wait_for_selector("#devis-pdf-btn", timeout=30000)
        assert pg.inner_text(".devis-tab.active") == "📐 Note de dim définitive" and pg.is_visible("#devis-note-definitive")
        with pg.expect_download(timeout=90000) as dl:
            pg.click("#devis-pdf-btn")
        lire_ecran(pg, "note de dim définitive")
        return dl.value.suggested_filename
    etape("10. Note de dim définitive", s10)

    def s11():
        pg.click("#devis-send-btn")
        pg.wait_for_selector("#btn-send-devis:not([disabled])")
        pg.click("#btn-send-devis")
        pg.wait_for_function("!document.getElementById('modal-envoi-mail')", timeout=120000)
        items = pg.request.get(f"{BASE}/api/devis/{etat['n']}/list").json()
        assert items and items[0]["variante"] == "devis" and items[0]["has_notedim"], items
        assert len(ENVOIS) == 2, len(ENVOIS)
        pg.click("#devis-close-btn") if pg.query_selector("#devis-close-btn") else None
        return f"devis {items[0]['numero_devis']} + note archivés ; 2 e-mails SIMULÉS (aucun envoi réel)"
    etape("11. Envoi (simulé)", s11)

    def s12():
        pg.click("#p-suivi-btn") if pg.is_hidden("#p-suivi-pop") else None
        pg.click("#fiche-statut-slot .pv-statut-btn, #fiche-statut-slot button") if pg.query_selector("#fiche-statut-slot button") else None
        pg.click("#fiche-statut-slot .pv-statut-opt[data-k=installation_finie]")
        pg.wait_for_function(f"fetch('/api/leads/{etat['n']}').then(r => r.json()).then(l => l.statut === 'installation_finie')", timeout=15000)
        return "statut « Installation finie »"
    etape("12. Installation finie", s12)

    def s13():
        pg.goto(f"{BASE}/prospect/{etat['n']}")
        pg.wait_for_function(f"document.body.dataset.prospectNumero === '{etat['n']}'")
        pg.wait_for_timeout(1000)
        pg.click("#p-suivi-btn")
        pg.wait_for_selector("#p-suivi-pop .fiche-facture-generer", state="visible")
        pg.click("#p-suivi-pop .fiche-facture-generer")
        pg.wait_for_selector("#documents-panel .docs-facture-row", state="visible")
        pg.fill("#facture-date-fin", date.today().isoformat())
        pg.click("#facture-generate-btn")
        fin = time.time() + 120
        while time.time() < fin and not pg.request.get(f"{BASE}/api/factures/{etat['n']}/list").json():
            time.sleep(1)
        f = pg.request.get(f"{BASE}/api/factures/{etat['n']}/list").json()[0]
        lire_ecran(pg, "panneau Documents (facture)")
        return f"facture {f['numero_facture']} émise"
    etape("13. Générer la facture", s13)

    def s14():
        lead = pg.request.get(f"{BASE}/api/leads/{etat['n']}").json()
        r = pg.request.post(f"{BASE}/api/leads/{etat['n']}", data={"surface_logement_m2": "90"})
        assert lead["dossier_fige"] is True and r.status == 423, (lead.get("dossier_fige"), r.status)
        pg.goto(f"{BASE}/prospect/{etat['n']}")
        pg.wait_for_timeout(1500)
        fige = pg.evaluate("document.body.classList.contains('p6-fige')")
        return f"dossier_fige, écriture refusée (423), page verrouillée : {fige}"
    etape("14. Dossier verrouillé", s14)
    b.close()

print("\n=== RAPPORT ===")
for r in RAPPORT:
    print(f"{r[0]} | {r[1]} | {r[2]}")
print("\n=== CONSOLE (erreurs) ===")
for c in sorted(set(CONSOLE)):
    print("-", c)
print("\n=== ÉCRAN : anglais / dates ISO ===")
for e in sorted(set(ECRAN)):
    print("-", e)
sys.exit(1 if any(r[0] == "KO" for r in RAPPORT) else 0)
