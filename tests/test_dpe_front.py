# -*- coding: utf-8 -*-
"""Partie B dans un vrai Chromium : saisie d'adresse (BAN) -> recherche DPE / audit -> bandeau #dpe-banner ->
remplissage des champs EXISTANTS ; prix au m² DVF dans prix_m2_*. Fiches fabriquées, aucun service extérieur :
l'ADEME, la BAN et DVF sont simulés (côté serveur par monkeypatch, côté navigateur par page.route)."""
import json
import re
import socket
import threading
import time

import pytest

import main
from services import dpe_audit, valeur_dvf
from tests.test_dpe_audit_master import LAT, LON, audit, dpe

sync_api = pytest.importorskip("playwright.sync_api")
uvicorn = pytest.importorskip("uvicorn")

BAN = {"features": [{"type": "Feature", "geometry": {"type": "Point", "coordinates": [LON, LAT]},
                     "properties": {"label": "12 Rue Imaginaire 75002 Paris", "housenumber": "12", "street": "Rue Imaginaire",
                                    "name": "12 Rue Imaginaire", "postcode": "75002", "city": "Paris", "citycode": "75102"}}]}
DVF_OK = {"ok": True, "prix_m2": 10500, "q1": 9250, "q3": 11750, "nb": 6, "commune": "Paris 2e Arrondissement",
          "type": "Maison", "periode": "2024-2026", "source": "médiane de 6 ventes de maisons à Paris 2e Arrondissement, 2024-2026"}
SIMU = {"dpe": [], "audit": [], "dvf": DVF_OK}
REMPLIR = """(vals) => {
  for (const [n, v] of Object.entries(vals)) {
    const el = document.querySelector(`#form-prospect [name="${n}"]`);
    if (!el) continue;
    el.value = v;
    el.dispatchEvent(new Event('input', { bubbles: true }));
    el.dispatchEvent(new Event('change', { bubbles: true }));
  }
}"""


def _port_libre():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def serveur():
    try:
        with sync_api.sync_playwright() as p:
            p.chromium.launch().close()
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"Chromium indisponible : {exc}")
    mp = pytest.MonkeyPatch()

    def get_ademe(url, timeout):
        if "api-adresse" in url:
            return BAN
        v = SIMU["audit" if "audit-opendata" in url else "dpe"]
        if isinstance(v, Exception):
            raise v
        return {"results": v}
    mp.setattr(dpe_audit, "GET", get_ademe)
    mp.setattr(valeur_dvf, "prix_m2", lambda cp, ville, t, **kw: dict(SIMU["dvf"]))
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
    mp.undo()
    main._atomic_write_json(main.LEADS_PATH, [])


@pytest.fixture
def page(serveur):
    SIMU.update(dpe=[], audit=[], dvf=DVF_OK)
    main._atomic_write_json(main.LEADS_PATH, [])
    main._write_users([{"id": "testeur", "username": "testeur", "password_hash": main._hash_password("essai-local"),
                        "role": "admin", "actif": True, "cree_at": main._now_iso(), "visibilite": "tous"}])
    with sync_api.sync_playwright() as p:
        b = p.chromium.launch()
        ctx = b.new_context(viewport={"width": 1600, "height": 1000})

        def exterieur(route):
            u = route.request.url
            if u.startswith(serveur):
                return route.continue_()
            if "api-adresse.data.gouv.fr" in u:
                return route.fulfill(status=200, content_type="application/json", body=json.dumps(BAN))
            if "geo.api.gouv.fr" in u:
                return route.fulfill(status=200, content_type="application/json",
                                     body=json.dumps([{"nom": "Paris", "code": "75056", "codesPostaux": ["75002"]}]))
            return route.abort()
        ctx.route("**/*", exterieur)
        pg = ctx.new_page()
        pg.lookups = []
        pg.on("request", lambda r: "/api/dpe-lookup" in r.url and pg.lookups.append(r.url))
        pg.goto(serveur + "/login")
        pg.fill("#username", "testeur")
        pg.fill("#password", "essai-local")
        pg.click("#login-btn")
        pg.wait_for_url(lambda u: "/login" not in u)
        pg.base = serveur
        yield pg
        b.close()


def val(pg, name):
    return pg.evaluate("n => String(document.querySelector(`#form-prospect [name='${n}']`)?.value ?? '')", name)


def nouvelle_fiche(pg, avant=None):
    pg.goto(pg.base + "/nouveau")
    pg.wait_for_function("typeof window.hexaParcoursEtape === 'function' && typeof window.hexaChercherDocuments === 'function'")
    pg.evaluate("window.hexaParcoursEtape(2)")
    if avant:
        avant(pg)
    pg.fill("#input-adresse", "12 rue imaginaire")
    pg.wait_for_selector("#ban-suggestions .ban-suggestion-item")
    pg.dispatch_event("#ban-suggestions .ban-suggestion-item", "mousedown")


def bandeau(pg, etat):
    pg.wait_for_selector(f"#dpe-banner .hx-dpe--{etat}", timeout=20000)
    return pg.inner_text("#dpe-banner")


# ---------------------------------------------------------------- un document confirmé -> rempli
def test_un_document_confirme_remplit_la_fiche(page):
    SIMU["dpe"] = [dpe("2475E0000001A")]
    nouvelle_fiche(page)
    texte = bandeau(page, "auto")
    assert "DPE n° 2475E0000001A du 15/03/2024 trouvé à cette adresse" in texte
    assert "Construit 1948-1974" in texte                                  # période : dans le bandeau…
    assert val(page, "annee_construction") == ""                          # … jamais dans le champ année
    attendu = {"type_logement": "maison", "surface_logement_m2": "118", "hsp": "2,5", "conso_kwh_m2": "288",
               "emissions_ges": "61", "dpe_connu": "E", "nb_niveaux": "2", "mode_chauffage": "gaz",
               "dpe_numero": "2475E0000001A", "dpe_date": "15/03/2024", "dpe_source": "ademe"}
    assert {k: val(page, k) for k in attendu} == attendu
    assert val(page, "cout_energetique_mensuel_eur") == "220" and val(page, "cout_energie_source") == "dpe"
    assert (val(page, "iso_toit"), val(page, "iso_mur")) == ("bien", "non")
    assert "1948-1974" in page.inner_text("#p6-dpe-bande") and "15/03/2024" in page.inner_text("#p6-dpe-bande")
    # prix au m² DVF dans les champs existants, valeur = prix × surface, source sous le champ
    page.wait_for_function("document.querySelector('[name=prix_m2_estime]').value === '10500'")
    assert (val(page, "prix_m2_min"), val(page, "prix_m2_max")) == ("9250", "11750")
    assert val(page, "valeur_bien_source") == DVF_OK["source"]
    page.wait_for_function(r"document.querySelector('#p6-valeur-bien').textContent.replace(/\s/g, '') === '1239000€'")
    blanc = lambda t: re.sub(r"\s", " ", t)                               # séparateurs de milliers : espaces fines
    assert blanc(page.inner_text("#p6-valeur-bien")) == "1 239 000 €"
    assert blanc(page.inner_text("#p6-valeur-bien-src")) == "Source DVF : " + DVF_OK["source"] + " (10 500 €/m²)"
    assert len(page.lookups) == 1                                         # une seule recherche (BAN + CP + parcelle)


# ---------------------------------------------------------------- plusieurs -> choix
def test_plusieurs_documents_choix_dans_le_bandeau(page):
    SIMU["dpe"] = [dpe("2475E0000001A"), dpe("2375E0000002B", date="2023-05-02", surface_habitable_logement=96)]
    nouvelle_fiche(page)
    assert "2 documents trouvés à cette adresse" in bandeau(page, "choix")
    assert val(page, "surface_logement_m2") == "" and val(page, "dpe_numero") == ""        # rien d'automatique
    boutons = page.query_selector_all("#dpe-banner .hx-dpe-cand")
    assert len(boutons) == 2 and "adresse confirmée" in boutons[1].inner_text()
    boutons[1].click()
    assert (val(page, "surface_logement_m2"), val(page, "dpe_numero"), val(page, "dpe_date")) == ("96", "2375E0000002B", "02/05/2023")
    assert "DPE n° 2375E0000002B retenu" in page.inner_text("#dpe-banner")


# ---------------------------------------------------------------- immeuble -> jamais automatique
def test_immeuble_jamais_automatique(page):
    SIMU["dpe"] = [dpe("2475E0000001A", type_batiment="appartement", numero_etage_appartement="3",
                       methode_application_dpe="dpe appartement généré à partir des données DPE immeuble")]
    nouvelle_fiche(page)
    assert "Immeuble" in bandeau(page, "choix")
    assert val(page, "surface_logement_m2") == "" and val(page, "dpe_numero") == ""
    assert "étage 3" in page.inner_text("#dpe-banner .hx-dpe-cand")


# ---------------------------------------------------------------- saisie manuelle jamais écrasée
def test_saisie_manuelle_jamais_ecrasee(page):
    SIMU["dpe"] = [dpe("2475E0000001A"), dpe("2375E0000002B", date="2023-05-02", surface_habitable_logement=96,
                                             conso_5_usages_par_m2_ep=150)]

    def saisir(pg):
        pg.fill("[name=surface_logement_m2]", "95")                       # saisie avant la recherche
        pg.click("#p6-lien-tech")                                         # « Données techniques »
        pg.fill("[name=prix_m2_estime]", "4200")                          # prix au m² saisi à la main
        pg.click("#p6-lien-tech")
    nouvelle_fiche(page, saisir)
    bandeau(page, "choix")
    page.query_selector_all("#dpe-banner .hx-dpe-cand")[0].click()
    assert val(page, "surface_logement_m2") == "95"                        # jamais écrasée par le document
    assert val(page, "conso_kwh_m2") == "288"
    assert "Déjà remplis, conservés : surface" in page.inner_text("#dpe-banner")
    page.click("#p6-lien-tech")
    page.fill("[name=conso_kwh_m2]", "250")                               # correction après le remplissage
    page.click("#p6-lien-tech")
    assert val(page, "mode_chauffage") == "gaz"
    page.evaluate("window.hexaParcoursEtape(3)")
    page.click(".l4-choix[data-for=mode_chauffage] button[data-valeur=fioul]")   # choix par bouton : manuel aussi
    page.evaluate("window.hexaParcoursEtape(2)")
    page.query_selector_all("#dpe-banner .hx-dpe-cand")[1].click()        # autre document choisi
    assert val(page, "conso_kwh_m2") == "250" and val(page, "dpe_numero") == "2375E0000002B"
    assert val(page, "mode_chauffage") == "fioul"
    time.sleep(0.5)
    assert val(page, "prix_m2_estime") == "4200" and val(page, "valeur_bien_source") == ""   # DVF n'y touche pas
    assert page.inner_text("#p6-valeur-bien-src") == "estimation"


def test_isolation_choisie_a_la_main_jamais_ecrasee(page):
    SIMU["dpe"] = [dpe("2475E0000001A")]                                  # toit « très bonne » -> bien, murs -> non

    def isoler(pg):
        pg.wait_for_selector("#iso-mur", state="visible")
        pg.select_option("#iso-mur", "peu")                               # choix manuel dans le simulateur
    nouvelle_fiche(page, isoler)
    bandeau(page, "auto")
    page.wait_for_timeout(300)
    assert page.evaluate("window.hexaSimLire().iso_source") == "manuel"
    assert page.input_value("#iso-mur") == "peu" and val(page, "iso_mur") == "peu"


def test_isolation_du_document_sans_choix_manuel(page):
    SIMU["dpe"] = [dpe("2475E0000001A")]
    nouvelle_fiche(page)
    bandeau(page, "auto")
    page.wait_for_function("window.hexaSimLire().iso_source === 'dpe'")
    assert (page.input_value("#iso-toit"), page.input_value("#iso-mur")) == ("bien", "non")


def test_facture_reelle_jamais_ecrasee_par_le_cout_du_document(page):
    SIMU["dpe"] = [dpe("2475E0000001A")]
    nouvelle_fiche(page, lambda pg: pg.evaluate("window.hexaCoutSaisie && window.hexaCoutSaisie('310')"))
    bandeau(page, "auto")
    assert val(page, "cout_energetique_mensuel_eur") == "310" and val(page, "cout_energie_source") == "reel"


# ---------------------------------------------------------------- fiche déjà remplie : pas de relance à l'ouverture
def test_fiche_rouverte_aucune_relance_puis_choix_explicite(page):
    lead = {"numero": "PR-91001", "civilite": "Madame", "nom": "Remplie", "prenom": "Rita", "telephone": "0600000011",
            "adresse_chantier": "12 RUE IMAGINAIRE", "code_postal_chantier": "75002", "ville_chantier": "PARIS",
            "type_logement": "maison", "surface_logement_m2": "130", "dpe_numero": "2275E0000000X", "dpe_date": "01/02/2022",
            "dpe_connu": "D", "prix_m2_estime": "3000", "valeur_bien_source": "médiane de 9 ventes de maisons à Paris, 2023-2025"}
    main._atomic_write_json(main.LEADS_PATH, [lead])
    SIMU["dpe"] = [dpe("2475E0000001A")]
    SIMU["dvf"] = {"ok": False, "indisponible": True, "raison": "données DVF indisponibles pour le moment"}
    page.goto(page.base + "/prospect/PR-91001")
    page.wait_for_function("document.body.dataset.prospectNumero === 'PR-91001' && typeof window.hexaParcoursEtape === 'function'")
    page.wait_for_timeout(800)
    page.evaluate("window.hexaParcoursEtape(2)")
    page.wait_for_selector("#input-adresse", state="visible")
    page.click("#input-adresse")
    page.click("[name=surface_logement_m2]")                              # blur de l'adresse : même adresse
    time.sleep(1.5)
    assert page.lookups == [] and page.inner_text("#dpe-banner") == ""
    # « Pas le bon logement ? » : recherche explicite ; les champs déjà remplis restent
    page.click("#p6-dpe-bande [data-p6-dpe]")
    bandeau(page, "auto")
    assert len(page.lookups) == 1
    assert (val(page, "surface_logement_m2"), val(page, "dpe_numero"), val(page, "conso_kwh_m2")) == ("130", "2275E0000000X", "288")
    # DVF indisponible au changement de type : le prix existant reste, marqué « estimation »
    page.click(".l4-choix[data-for=type_logement] button[data-valeur=appartement]")      # bouton visible du type
    page.wait_for_function("document.querySelector('#p6-valeur-bien-src').textContent.startsWith('estimation')")
    assert val(page, "prix_m2_estime") == "3000"
    assert page.inner_text("#p6-valeur-bien-src") == "estimation (DVF : données DVF indisponibles pour le moment)"


# ---------------------------------------------------------------- erreurs et enregistrement
def test_ademe_injoignable_message_et_reessai(page):
    SIMU["dpe"] = SIMU["audit"] = TimeoutError()
    nouvelle_fiche(page)
    assert "l'ADEME ne répond pas" in bandeau(page, "erreur")
    SIMU["dpe"], SIMU["audit"] = [dpe("2475E0000001A")], []
    page.click("#dpe-banner [data-hx-dpe-reessayer]")
    bandeau(page, "auto")
    assert val(page, "dpe_numero") == "2475E0000001A"


def test_enregistrement_une_seule_cle_ajoutee(page):
    SIMU["audit"] = [audit("A0001")]
    nouvelle_fiche(page)
    bandeau(page, "auto")
    page.wait_for_function("document.querySelector('[name=valeur_bien_source]').value !== ''")
    avant = set(page.evaluate("[...document.querySelectorAll('#form-prospect [name]')].map(e => e.name)"))
    page.evaluate(REMPLIR, {"civilite": "Madame", "nom": "Fabrique", "prenom": "Fanny", "telephone": "0600000021",
                            "email": "fabrique@example.invalid", "hsp": "2,5", "nombre_personnes": "4", "rfr": "15000"})
    ok = page.evaluate("window.hexaEnregistrerFiche()")
    assert ok is not False, page.evaluate("[...document.querySelectorAll('#modal-erreur li')].map(l => l.textContent)")
    page.wait_for_function("(document.body.dataset.prospectNumero || '').startsWith('PR-')")
    numero = page.evaluate("document.body.dataset.prospectNumero")
    lead = next(x for x in main._read_leads() if x.get("numero") == numero)
    assert lead["dpe_numero"] == "A0001" and lead["dpe_source"] == "ademe_audit" and lead["annee_construction"] == "1965"
    assert lead["valeur_bien_source"] == DVF_OK["source"] and lead["prix_m2_estime"] == "10500"
    assert "valeur_bien_source" in avant                                   # le seul champ caché ajouté au formulaire
    assert not [k for k in lead if re.search(r"candidat|dpe_audit|valeur_bien(?!_source)", k)]
