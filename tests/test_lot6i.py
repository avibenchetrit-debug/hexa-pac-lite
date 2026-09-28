# -*- coding: utf-8 -*-
"""Lot 6i : accompagnateur définitif (textes, branches, variables), NRP en haut de l'étape 1, FAQ client, noms des PDF
côté client, zéro défilement. Vrai Chromium, fiches fabriquées :
PR-94001 (DPE F, fioul, eau chaude par la chaudière), PR-94002 (sans DPE, électricité, ballon électrique),
PR-94003 / PR-94004 (identiques, pour comparer le NRP de l'accompagnateur à celui de « Fin d'appel »)."""
import copy
import json
import os
import re
import socket
import threading
import time
from datetime import date

import pytest

import main

sync_api = pytest.importorskip("playwright.sync_api")
uvicorn = pytest.importorskip("uvicorn")

BASE = {"civilite": "Madame", "nom": "Fictif", "prenom": "Faustine", "email": "fictif@example.invalid",
        "adresse_chantier": "12 RUE IMAGINAIRE", "cp_chantier": "75002", "code_postal_chantier": "75002", "ville_chantier": "PARIS",
        "type_logement": "maison", "surface_logement_m2": "118", "hsp": "2,5", "annee_construction": "1968",
        "type_emetteurs": "radiateurs_classiques", "alimentation_electrique": "monophase", "nombre_personnes": "4",
        "rfr": "15000", "categorie": "tres_modeste", "statut": "a_rappeler"}
AVEC_DPE = dict(BASE, numero="PR-94001", telephone="0600000041", mode_chauffage="fioul", ecs="chaudiere", dpe_connu="F",
                dpe_numero="2475E0000001A", dpe_date="15/03/2024", dpe_source="ademe",
                cout_energetique_mensuel_eur="220", cout_energie_source="dpe")
SANS_DPE = dict(BASE, numero="PR-94002", telephone="0600000042", mode_chauffage="electricite", ecs="independant",
                annee_construction="", surface_logement_m2="")
NRP_A = dict(BASE, numero="PR-94003", telephone="0600000043", mode_chauffage="gaz", ecs="chaudiere")
NRP_B = dict(NRP_A, numero="PR-94004", telephone="0600000044")
AN = date.today().year


def _port_libre():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _semer():
    main._atomic_write_json(main.LEADS_PATH, [dict(x) for x in (AVEC_DPE, SANS_DPE, NRP_A, NRP_B)])
    for x in (AVEC_DPE, SANS_DPE, NRP_A, NRP_B):
        main._atomic_write_json(main._state_simulateur_path(x["numero"]), {})
        main.save_state_simulateur_atomic(x["numero"], {"service": "chauffage_seul"})
    p = main.load_parametres_admin()
    p.pop("script_appel", None)                                           # textes par défaut du lot 6i
    main._atomic_write_json(main.PARAMETRES_ADMIN_PATH, p)
    main._write_users([{"id": "testeur", "username": "testeur", "password_hash": main._hash_password("essai-local"),
                        "role": "admin", "actif": True, "cree_at": main._now_iso(), "visibilite": "tous"}])


@pytest.fixture(scope="module")
def serveur():
    try:
        with sync_api.sync_playwright() as p:
            p.chromium.launch().close()
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"Chromium indisponible : {exc}")
    _semer()
    port = _port_libre()
    srv = uvicorn.Server(uvicorn.Config(main.app, host="127.0.0.1", port=port, log_level="warning"))
    th = threading.Thread(target=srv.run, daemon=True)
    th.start()
    for _ in range(200):
        if srv.started:
            break
        time.sleep(0.05)
    yield f"http://127.0.0.1:{port}"
    srv.should_exit = True
    th.join(timeout=10)
    main._atomic_write_json(main.LEADS_PATH, [])


@pytest.fixture
def page(serveur):
    with sync_api.sync_playwright() as p:
        b = p.chromium.launch()
        ctx = b.new_context(accept_downloads=True, viewport={"width": 1440, "height": 900})
        ctx.route("**/*", lambda r: r.continue_() if r.request.url.startswith(serveur) else r.abort())
        pg = ctx.new_page()
        pg.goto(serveur + "/login")
        pg.fill("#username", "testeur")
        pg.fill("#password", "essai-local")
        pg.click("#login-btn")
        pg.wait_for_url(lambda u: "/login" not in u)
        pg.base = serveur
        yield pg
        b.close()


def ouvrir(pg, numero, etape=1):
    pg.goto(f"{pg.base}/prospect/{numero}")
    pg.wait_for_function("document.body.dataset.prospectNumero === %r && typeof window.hexaParcoursEtape === 'function'" % numero)
    pg.wait_for_timeout(700)
    aller(pg, etape)


def aller(pg, etape):
    pg.evaluate(f"window.hexaParcoursEtape({etape})")
    pg.wait_for_timeout(300)
    if pg.query_selector("#p6-aside .p6-aside-mini"):                     # étape 6 : panneau replié par défaut
        pg.click("#p6-aside .p6-aside-mini")
    pg.wait_for_function(f"(document.querySelector('#p6-aside .p6-ak') || {{}}).textContent === 'ACCOMPAGNATEUR D\\'APPEL · ÉTAPE {etape}'")
    pg.wait_for_timeout(200)


def aside(pg):
    return re.sub(r"[  ]", " ", pg.inner_text("#p6-aside-corps"))


def reponse(pg, libelle):
    pg.click(f'#p6-aside-corps .p6-arow button:text-is("{libelle}")')
    pg.wait_for_timeout(150)


def pas_de_defilement(pg):
    return pg.evaluate("document.scrollingElement.scrollHeight <= window.innerHeight + 1")


# ---------------------------------------------------------------- textes de chaque étape, variables, branches DPE
def test_textes_et_variables_fiche_avec_dpe(page):
    ouvrir(page, "PR-94001", 1)
    t = aside(page)
    assert "Bonjour Madame Fictif, Testeur de la société Hexa-Rénov'." in t
    assert "Le client ne décroche pas ?" in t and t.index("Le client ne décroche pas ?") < t.index("Bonjour")   # NRP avant l'accroche
    assert "1. Êtes-vous bien à l'origine de cette demande ?" in t and "3. Où en êtes-vous dans votre projet ?" in t
    reponse(page, "Découverte")
    assert page.is_visible("#p6-aside-corps .p6-expl > summary") and page.inner_text("#p6-aside-corps .p6-expl > summary") == "Expliquer au client"
    assert page.is_hidden("text=Le fioul et le gaz coûtent de plus en plus cher.")        # replié par défaut
    page.click("#p6-aside-corps .p6-expl > summary")
    assert "1 kWh acheté = 3,5 kWh de chaleur" in aside(page) and "Prime CEE : uniquement si" in aside(page)
    couleur = page.eval_on_selector("#p6-aside-corps .p6-consigne", "e => getComputedStyle(e).color")
    assert couleur == "rgb(175, 192, 214)"                                                # consigne grise
    assert pas_de_defilement(page)
    reponse(page, "Sait ce qu'il veut")
    assert "« Très bien. Vous avez déjà un devis ?" in aside(page)

    aller(page, 2)
    t = aside(page)
    assert "C'est bien une maison ou un appartement ? Elle fait environ 118 m², construite vers 1968 ?" in t
    assert "Depuis 2024, avez-vous fait des travaux d'isolation : toit, murs ou fenêtres ?" in t
    assert "Je n'ai pas trouvé de diagnostic" not in t
    assert "Votre maison consomme beaucoup" in t                                         # DPE F : encadré
    reponse(page, "Oui")
    assert "« Qu'avez-vous fait exactement ? »" in aside(page) and "Corriger le bloc 4." in aside(page)
    reponse(page, "Je le loue à quelqu'un")
    assert "« Quelle est l'adresse où vous habitez ? »" in aside(page)

    aller(page, 3)
    t = aside(page)
    assert "votre chauffage coûte environ 2 640 € par an" in t and "Combien payez-vous pour votre fioul" not in t
    assert "Et vous avez droit à la prime CEE, parce qu'on remplace votre chaudière." in t     # fioul
    assert "Pas de prime CEE dans ce cas" not in t

    aller(page, 4)
    assert page.inner_text("#p6-aside-corps .p6-expl > summary") == "Expliquer au client"
    t = aside(page)
    assert f"celui de {AN} sur vos revenus de {AN - 1}" in t
    page.wait_for_function("/vous avez droit à [0-9]/i.test(document.querySelector('#p6-aside-corps').textContent.replace(/\\s/g, ' '))",
                           timeout=15000)
    t = aside(page)
    m = re.search(r"catégorie très modestes\. Vous avez droit à ([\d ]+) € d'aides : ([\d ]+) € de MaPrimeRénov' et ([\d ]+) € de prime CEE", t)
    assert m, t
    aides, mpr, cee = (int(x.replace(" ", "")) for x in m.groups())
    assert aides == mpr + cee and mpr > 0 and cee > 0 and "[" not in m.group(0)

    aller(page, 5)
    t = aside(page)
    assert "Quand on enlève votre chaudière, il faut une autre solution pour l'eau chaude" in t
    assert "Avez-vous une pièce non chauffée" not in t
    reponse(page, "DUO")
    assert "Choisir « Chauffage + eau chaude »." in aside(page) and "Avez-vous une pièce non chauffée" not in aside(page)
    reponse(page, "Ballon")
    assert "Avez-vous une pièce non chauffée de plus de 15 m²" in aside(page)
    assert "n'a plus droit à MaPrimeRénov' depuis le 01/09/2026" in aside(page)

    aller(page, 6)
    reponse(page, "Attendre")
    assert "« L'accord prend environ 5 mois." in aside(page)
    reponse(page, "Tout de suite")
    t = aside(page)
    assert "l'État vous la reverse sur votre compte bancaire" in t and "L'accord prend environ 5 mois" not in t
    reponse(page, "Éco-PTZ")
    assert "« C'est un prêt à taux zéro, sans intérêts." in aside(page)
    assert "Lire au client l'encadré jaune « À dire au client »." in aside(page)
    assert "« Est-ce que ça vous convient ?" in aside(page)
    assert pas_de_defilement(page)


def test_branches_sans_dpe_et_ballon_existant(page):
    ouvrir(page, "PR-94002", 2)
    t = aside(page)
    assert "« Je n'ai pas trouvé de diagnostic pour votre logement. Pas de souci, on va le remplir ensemble. »" in t
    for q in ("C'est une maison ou un appartement ?", "Quelle est la surface habitable, à peu près ?",
              "Elle a été construite vers quelle année ? Même approximativement.", "Quelle est la hauteur sous plafond ? Environ 2,50 m ?",
              "Les combles ou le toit sont isolés ?", "Et les murs ?", "Vos fenêtres sont en simple ou en double vitrage ?"):
        assert q in t
    assert "Depuis [année du DPE]" not in t and "Depuis 20" not in t
    aller(page, 3)
    t = aside(page)
    assert "Combien payez-vous pour votre fioul ou votre gaz, à peu près ?" in t and "coûte environ" not in t
    assert "Pas de prime CEE dans ce cas : elle est réservée au remplacement d'une chaudière fioul ou gaz." in t
    aller(page, 5)
    t = aside(page)
    assert "Vous pouvez garder votre ballon électrique" in t and "Quand on enlève votre chaudière" not in t
    reponse(page, "Il garde")
    assert "Avez-vous une pièce non chauffée" not in aside(page)
    reponse(page, "Il remplace")
    assert "Avez-vous une pièce non chauffée de plus de 15 m²" in aside(page)
    reponse(page, "Pas de place")
    assert "→ split : une partie dehors, une partie dedans." in aside(page)


def test_chaque_etape_a_des_textes_et_la_faq(page):
    ouvrir(page, "PR-94001", 1)
    for n in range(1, 7):
        aller(page, n)
        page.wait_for_selector("#p6-aside-corps .p6-aq, #p6-aside-corps .p6-quote")
        assert page.inner_text("#p6-aside .p6-faq-btn") == "❓ Questions du client"
        assert pas_de_defilement(page), n
        assert page.eval_on_selector("#p6-aside-corps", "e => getComputedStyle(e).overflowY") == "auto"


# ---------------------------------------------------------------- FAQ
def test_faq_ouverture_recherche_et_reponse(page):
    ouvrir(page, "PR-94001", 3)
    page.click("#p6-aside [data-p6-faq]")
    page.wait_for_selector("#p6-faq .p6-faq-q")
    assert len(page.query_selector_all("#p6-faq .p6-faq-i")) == 13
    assert page.evaluate("document.activeElement.classList.contains('p6-faq-q')")
    page.fill("#p6-faq .p6-faq-q", "froid")
    visibles = [e.inner_text() for e in page.query_selector_all("#p6-faq .p6-faq-i:not([hidden]) > summary")]
    assert visibles == ["Est-ce que ça marche quand il fait très froid ?"]
    assert "fonctionnent jusqu'à −20 °C" in page.inner_text("#p6-faq .p6-faq-i:not([hidden])")
    page.fill("#p6-faq .p6-faq-q", "garanti")                              # sans accents / majuscules : trouvé
    assert len(page.query_selector_all("#p6-faq .p6-faq-i:not([hidden])")) == 2
    page.fill("#p6-faq .p6-faq-q", "zzz")
    assert page.is_visible("#p6-faq .p6-faq-aucun")
    page.keyboard.press("Escape")
    assert page.query_selector("#p6-faq") is None
    assert pas_de_defilement(page)


def test_faq_edition_admin(page):
    p = f"admin:{int(time.time())}"
    jeton = f"{p}.{main._sign_admin_token(p)}"
    page.goto(page.base + "/")
    page.wait_for_function("window.HexaAdmin && typeof window.HexaAdmin.open === 'function'")
    page.evaluate("t => localStorage.setItem('hexa_admin_unlocked', JSON.stringify({ token: t, unlocked_at: Date.now() }))", jeton)
    page.evaluate("window.HexaAdmin.open()")
    page.click(".adm-roottab[data-roottab=script]")                        # onglet « Script d'appel »
    page.click("[data-toggle-bloc='12']")                                  # « 12. Script d'appel »
    faq = page.wait_for_selector("#sa-editeur details[data-sa-ouvert=faq]", state="visible")
    page.click("#sa-editeur details[data-sa-ouvert=faq] > summary")
    page.wait_for_selector("#sa-editeur [data-sa-f='0']", state="visible")
    assert faq.query_selector("summary").inner_text() == "FAQ client (13 questions)"
    page.click("#sa-editeur [data-sa-action=bas-f][data-f='0']")               # réordonner : la 1re descend
    page.fill("#sa-editeur [data-sa-f='0'] [data-sa=f-reponse]", "Réponse modifiée dans l'admin.")
    page.click("#sa-editeur [data-sa-action=ajout-f]")
    page.fill("#sa-editeur [data-sa-f='13'] [data-sa=f-question]", "Question ajoutée ?")
    page.fill("#sa-editeur [data-sa-f='13'] [data-sa=f-reponse]", "Réponse ajoutée.")
    page.click("#sa-editeur [data-sa-action=suppr-f][data-f='12']")            # « Vous êtes certifiés ? » retirée
    page.click("#btn-save-script-appel")
    page.wait_for_selector("text=Script d'appel enregistré")
    f = main._script_appel()["faq"]
    assert [x["question"] for x in f[:2]] == ["Est-ce que ça marche quand il fait très froid ?", "Est-ce que ça fait du bruit ?"]
    assert f[0]["reponse"] == "Réponse modifiée dans l'admin." and f[-1] == {"question": "Question ajoutée ?", "reponse": "Réponse ajoutée."}
    assert len(f) == 13 and "Vous êtes certifiés ?" not in [x["question"] for x in f]
    p2 = main.load_parametres_admin(); p2.pop("script_appel", None)            # remise des textes par défaut
    main._atomic_write_json(main.PARAMETRES_ADMIN_PATH, p2)


# ---------------------------------------------------------------- NRP : exactement l'action de « Fin d'appel »
def _sans_horodatage(v):
    if isinstance(v, dict):
        return {k: _sans_horodatage(x) for k, x in v.items() if not re.search(r"(^|_)(at|date|horodatage|le)$|updated|created|_log$", k)}
    if isinstance(v, list):
        return [_sans_horodatage(x) for x in v]
    if isinstance(v, str) and re.match(r"^\d{4}-\d{2}-\d{2}", v):
        return "<date>"
    return v


def _lead(numero):
    return copy.deepcopy(next(x for x in main._read_leads() if x.get("numero") == numero))


def test_nrp_identique_a_fin_d_appel(page):
    avant_a, avant_b = _lead("PR-94003"), _lead("PR-94004")
    ouvrir(page, "PR-94003", 1)
    cpt = page.inner_text("#p6-aside-corps .p6-nrp-cpt")
    assert cpt == "0 / 8 appels" and "p6-nrp-cpt--0" in page.get_attribute("#p6-aside-corps .p6-nrp-cpt", "class")
    page.click("#p6-aside-corps [data-p6-nrp]")
    page.wait_for_selector("#p6-aside-corps .p6-nrp-msg")
    assert page.inner_text("#p6-aside-corps .p6-nrp-msg") == "NRP enregistré (1/8)"
    assert page.inner_text("#p6-aside-corps .p6-nrp-cpt") == "1 / 8 appels"
    assert "p6-nrp-cpt--n" in page.get_attribute("#p6-aside-corps .p6-nrp-cpt", "class")
    page.click("#p6-aside-corps .p6-nrp-msg + [data-p6-rappel]")               # « Programmer un rappel »
    page.wait_for_function("document.activeElement && document.activeElement.id === 'suivi-rap-date'")
    # même action côté serveur que le bouton NRP du panneau « Fin d'appel » (#suivi-nrp)
    ouvrir(page, "PR-94004", 1)
    page.click("#p-fin-appel-btn")
    page.click("#suivi-nrp")
    page.wait_for_function("/1\\/8/.test(document.querySelector('#suivi-cpt-appel').textContent)")
    apres_a, apres_b = _lead("PR-94003"), _lead("PR-94004")
    diff = lambda av, ap: {k: _sans_horodatage(ap.get(k)) for k in set(av) | set(ap) if av.get(k) != ap.get(k)
                           and k not in ("numero", "telephone", "updated_at")}
    da, db = diff(avant_a, apres_a), diff(avant_b, apres_b)
    assert da and da == db, (da, db)
    cpt = lambda n: page.request.get(f"{page.base}/api/leads/{n}").json()["compteurs"]["appel"]
    assert cpt("PR-94003") == cpt("PR-94004") == 1
    ech = lambda n: [e.get("type") or e.get("canal") for e in (main._read_json(main.ECHANGES_PATH, {}) or {}).get(n, [])]
    assert ech("PR-94003") == ech("PR-94004") and ech("PR-94003")


def test_nrp_fiche_jamais_enregistree(page):
    page.goto(page.base + "/nouveau")
    page.wait_for_function("typeof window.hexaParcoursEtape === 'function'")
    aller(page, 1)
    page.click("#p6-aside-corps [data-p6-nrp]")
    page.wait_for_selector("#p6-aside-corps .p6-nrp-msg")
    assert page.inner_text("#p6-aside-corps .p6-nrp-msg") == "Enregistrez la fiche pour compter le NRP."


# ---------------------------------------------------------------- noms des PDF côté client (lot 6h, choix 3)
def test_noms_des_pdf_cote_client(page, tmp_path):
    os.makedirs(main.DEVIS_DIR, exist_ok=True)
    fichiers = []
    for v in (1, 2):
        f = os.path.join(main.DEVIS_DIR, f"PR-94001_v{v}.pdf")
        with open(f, "wb") as fh:
            fh.write(b"%PDF-1.4 devis fabrique\n%%EOF")
        fichiers.append(f)
    main._atomic_write_json(main.DEVIS_META_PATH, {"PR-94001": [
        {"version": 1, "numero_devis": "DE2026-7512-1FF", "variante": "pre_devis", "file": fichiers[0], "sent_at": "2026-09-01T10:00:00"},
        {"version": 2, "numero_devis": "DE2026-7512-2FF", "variante": "devis", "file": fichiers[1], "sent_at": "2026-09-20T10:00:00"}]})
    try:
        cd = lambda u: page.request.get(page.base + u).headers.get("content-disposition", "")
        assert cd(f"/devis-public/PR-94001/1/{main._sign_devis_token_v('PR-94001', 1)}/pdf") == 'attachment; filename="Pre-devis_PD2026-7512-1FF.pdf"'
        assert cd(f"/devis-public/PR-94001/2/{main._sign_devis_token_v('PR-94001', 2)}/pdf") == 'attachment; filename="Devis_DE2026-7512-2FF.pdf"'
        # lien sans numéro de version : la dernière version envoyée (tests/test_lien_devis_client.py)
        assert cd(f"/devis-public/PR-94001/{main._sign_devis_token('PR-94001')}/pdf") == 'attachment; filename="Devis_DE2026-7512-2FF.pdf"'
        r = page.request.get(page.base + f"/notedim-public/PR-94001/{main._sign_notedim_token('PR-94001')}/pdf", timeout=90000)
        assert r.status == 200 and r.headers["content-disposition"] == f'attachment; filename="Note-de-dimensionnement_ND{AN}-94001-FI.pdf"'
        assert "DEFINITIVE" not in r.headers["content-disposition"]
    finally:
        main._atomic_write_json(main.DEVIS_META_PATH, {})
