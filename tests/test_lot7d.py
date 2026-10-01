# -*- coding: utf-8 -*-
"""Lot 7d : facture et mentions — documents imprimés (devis, pré-devis, facture ; écran et PDF) SANS date de chantier
(ni « Début travaux », ni « Fin travaux », ni « Travaux achevés le … »), bloc identité 12 / 12 lignes alignées ;
« Application » selon les émetteurs ; ETAS 35 / 55 : seule la valeur qui compte en gras (700). Dans le CRM, la date de
fin de travaux reste saisie, enregistrée et affichée. Fiches fabriquées ici : aucune donnée réelle."""
import io
import re
import types

import pytest

import main
import test_lot7a_documents as docs
import test_lot7b as l7b

NUM = docs.LEAD["numero"]
FAUSSE_REQUETE = types.SimpleNamespace(base_url="http://127.0.0.1/")


def _rendu(quoi="facture", emetteurs="radiateurs_fonte", **surcharges):
    l7b._catalogue(l7b.SPECS)
    docs._preparer(lead={"type_emetteurs": emetteurs})
    etat = main._load_state_simulateur(NUM, {}, main._read_catalogue_pac()) or {}
    main.save_state_simulateur_atomic(NUM, dict(etat, service="chauffage_ecs", option="opt1",
                                                mode_mpr="sans_attente", modele_pac_id=l7b.MODELE["ref"]))
    if quoi == "facture":
        return main._render_facture_html(None, NUM, "FA-2099-0001", "DE2099-0001-1", "2026-07-30",
                                         surcharges=surcharges or None)
    ctx = main._build_devis_context(None, NUM, avec_sous_traitant=(quoi == "devis"))
    ctx["pre_devis"] = quoi == "pre_devis"
    return main.templates.env.get_template("devis_pac.html").render(ctx)


def _colonnes(brut):
    bloc = re.search(r'<section class="infos">(.*?)</section>', brut, re.S).group(1)
    cols = re.split(r'<div class="infos-col">', bloc)[1:]
    return [[docs._texte(l).strip() for l in re.findall(r'<span class="infos-label">(.*?)</span>', c)] for c in cols]


# ── 1. Aucune date de chantier imprimée ──────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("quoi", ["devis", "pre_devis", "facture"])
def test_aucune_date_de_chantier_imprimee(quoi):
    brut = _rendu(quoi)
    t = docs._texte(brut)
    for interdit in ("Fin travaux", "Début travaux", "Travaux achevés", "30/07/2026"):
        assert interdit not in t, interdit
    if quoi == "facture":
        assert "Solde intégral exigible à réception de la présente facture." in t


@pytest.mark.parametrize("quoi", ["devis", "pre_devis", "facture"])
def test_bloc_identite_12_lignes_de_chaque_cote(quoi):
    benef, dossier = _colonnes(_rendu(quoi))
    assert len(benef) == len(dossier) == 12, (benef, dossier)
    assert dossier[0] == "Date d'émission"
    assert dossier[1] == ("Réf. devis" if quoi == "facture" else "Durée de validité")
    assert dossier[2] == "Visite technique" and dossier[3] == "Adresse chantier"


def test_facture_ref_devis_dans_le_bloc_dossier_et_en_tete():
    brut = _rendu("facture")
    assert re.search(r'data-ref-devis><span class="infos-label">Réf\. devis</span><span class="infos-value">DE2099-0001-1<', brut)
    assert 'data-ace="reference-devis"><span class="doc-type-num-label">Réf. devis :</span> DE2099-0001-1' in brut


def test_rectificative_d_une_facture_d_avant_le_lot7d_garde_sa_mise_en_page():
    """Sinon elle ne serait plus identique ligne à ligne à l'originale (dossiers facturés intacts)."""
    t = docs._texte(_rendu("facture", facture_rectificative={"numero": "FA-2026-0001", "date": "30/07/2026"},
                           facture_mise_en_page_avant_lot7d=True))
    assert "Fin travaux 30/07/2026" in t and "Travaux achevés le 30/07/2026." in t
    assert "data-ref-devis" not in _rendu("facture", facture_mise_en_page_avant_lot7d=True)


def test_marque_de_mise_en_page_et_rectificative():
    assert main.MISE_EN_PAGE_FACTURE == "lot7d"
    src = open(main.__file__, encoding="utf-8").read()
    assert '"mise_en_page": MISE_EN_PAGE_FACTURE' in src
    assert '"facture_mise_en_page_avant_lot7d": rec.get("mise_en_page") != MISE_EN_PAGE_FACTURE' in src


# ── 1 bis. CRM : la date de fin de travaux reste saisie, enregistrée, affichée ──────────────────────────────────────
def test_crm_date_de_fin_de_travaux_toujours_saisie_et_affichee():
    front = open(main.os.path.join(main.os.path.dirname(main.__file__), "templates", "index.html"), encoding="utf-8").read()
    assert 'Fin travaux <input type="date" id="facture-date-fin"' in front
    assert "JSON.stringify({ date_fin_travaux: dat" in front
    assert "· Fin travaux ${escapeHtml(f.date_fin_travaux || '—')}" in front


def test_crm_date_de_fin_de_travaux_exigee_et_enregistree(monkeypatch):
    from fastapi.testclient import TestClient
    client = TestClient(main.app)
    docs._preparer()
    main._atomic_write_json(main.COUNTERS_PATH, {"dossier": 0})
    vus = {}

    def faux_pdf(html, request):
        vus["html"] = html
        return b"%PDF-1.4 faux"
    monkeypatch.setattr(main, "_html_to_pdf_playwright", faux_pdf)
    monkeypatch.setattr(main, "_append_fiche_technique", lambda pdf, numero: pdf)
    monkeypatch.setattr(main, "_append_fiche_ballon", lambda pdf, numero: pdf)
    assert client.post(f"/api/facture/{NUM}", json={}).status_code == 400          # toujours exigée
    r = client.post(f"/api/facture/{NUM}", json={"date_fin_travaux": "2026-09-12"})
    assert r.status_code == 200, r.text
    rec = main._read_factures_meta()[NUM][-1]
    assert rec["date_fin_travaux"] == "2026-09-12" and rec["mise_en_page"] == "lot7d"
    assert "12/09/2026" not in docs._texte(vus["html"]) and "Fin travaux" not in vus["html"]
    liste = client.get(f"/api/factures/{NUM}/list")                 # Documents → Factures : « Fin travaux 12/09/2026 »
    assert liste.status_code == 200 and "12/09/2026" in liste.text


# ── 2. Application selon les émetteurs ───────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("quoi", ["devis", "pre_devis", "facture"])
@pytest.mark.parametrize("emetteurs, attendu", [("radiateurs_fonte", "Application : haute température"),
                                                ("radiateurs_classiques", "Application : haute température"),
                                                ("radiateurs_basse_temp", "Application : haute température"),
                                                ("plancher_chauffant", "Application : basse température")])
def test_application_selon_les_emetteurs(quoi, emetteurs, attendu):
    bloc = docs._texte(re.search(r'<div class="pac-heating-note">(.*?)</section>', _rendu(quoi, emetteurs), re.S).group(1))
    assert attendu in bloc and "moyenne" not in bloc


# ── 3. ETAS : les deux valeurs, seule celle qui compte en gras ───────────────────────────────────────────────────
@pytest.mark.parametrize("quoi", ["devis", "pre_devis", "facture"])
@pytest.mark.parametrize("emetteurs, gras, normal", [("radiateurs_fonte", "151", "178"), ("plancher_chauffant", "178", "151")])
def test_etas_seule_la_valeur_qui_compte_en_gras(quoi, emetteurs, gras, normal):
    sync_api = pytest.importorskip("playwright.sync_api")
    brut = _rendu(quoi, emetteurs)
    assert brut.count('class="etas-compte"') == 1
    with sync_api.sync_playwright() as pw:
        b = pw.chromium.launch()
        p = b.new_page()
        p.set_content(brut)
        for media in ("screen", "print"):
            p.emulate_media(media=media)
            m = p.evaluate("""() => {
              const tr = [...document.querySelectorAll('.pac-specs-table tr')].find(r => r.cells[0].textContent.trim().startsWith('ETAS chauffage 35'));
              const td = tr.cells[1], s = td.querySelector('.etas-compte');
              return {texte: td.textContent.trim(), cellule: getComputedStyle(td).fontWeight, gras: s.textContent,
                      poids: getComputedStyle(s).fontWeight, libelle: getComputedStyle(tr.cells[0]).fontWeight};
            }""")
            assert m["texte"] == "178 / 151", m                     # les deux valeurs gardées
            assert (m["gras"], m["poids"], m["cellule"]) == (gras, "700", "400"), (media, m)
            assert m["libelle"] == "600"                             # le libellé reste mis en évidence (lot 7b)
        b.close()
    assert normal in brut


def test_etas_sans_emetteur_connu_ni_format_attendu_texte_tel_quel():
    assert str(main.etas_html("178 / 151", "")) == "178 / 151"
    assert str(main.etas_html("183", "55")) == "183"
    assert str(main.etas_html("<b> / 1", "35")) == '<strong class="etas-compte" data-etas="35">&lt;b&gt;</strong> / 1'
    assert main.etas_valeur_qui_compte({"type_emetteurs": "convecteurs_electriques"}) == ""


# ── Alignement : écran (vrai Chromium) et PDF ────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("quoi", ["devis", "pre_devis", "facture"])
def test_bloc_identite_aligne_a_l_ecran_et_a_l_impression(quoi):
    sync_api = pytest.importorskip("playwright.sync_api")
    brut = _rendu(quoi)
    with sync_api.sync_playwright() as pw:
        b = pw.chromium.launch()
        p = b.new_page()
        p.set_content(brut)
        for media in ("screen", "print"):
            p.emulate_media(media=media)
            cols = p.evaluate("""() => [...document.querySelectorAll('section.infos .infos-col')].map(c => ({
              lignes: [...c.querySelectorAll('.infos-row')].map(r => { const b = r.getBoundingClientRect(); return [b.top, b.bottom]; }),
              titre: c.querySelector('.infos-col-title').getBoundingClientRect().bottom}))""")
            g, d = cols
            assert len(g["lignes"]) == len(d["lignes"]) == 12
            assert abs(g["titre"] - d["titre"]) < 0.5
            for (gt, gb), (dt, db) in zip(g["lignes"], d["lignes"]):
                assert abs(gt - dt) < 0.5 and abs(gb - db) < 0.5, (media, gt, dt)   # lignes alignées
            pas = [b2[0] - b1[1] for b1, b2 in zip(d["lignes"], d["lignes"][1:])]
            assert max(pas) - min(pas) < 0.5, pas                                        # aucun espace vide
        b.close()


@pytest.mark.parametrize("quoi", ["devis", "facture"])
def test_bloc_identite_aligne_dans_le_pdf(quoi):
    pytest.importorskip("playwright.sync_api")
    fitz = pytest.importorskip("fitz")
    pdf = main._html_to_pdf_playwright(_rendu(quoi), FAUSSE_REQUETE)
    page = fitz.open(stream=pdf, filetype="pdf")[0]
    txt = page.get_text()
    assert "Fin travaux" not in txt and "Début travaux" not in txt and "Travaux achevés" not in txt
    benef, dossier = _colonnes(_rendu(quoi))
    y = {}
    for b in page.get_text("dict")["blocks"]:
        for l in b.get("lines", []):
            t = "".join(s["text"] for s in l["spans"]).strip()
            if t in benef + dossier and t not in y:
                y[t] = (round(l["bbox"][1], 1), l["bbox"][0])
    for gauche, droite in zip(benef, dossier):
        assert abs(y[gauche][0] - y[droite][0]) < 0.6, (gauche, droite, y[gauche], y[droite])
    assert y[benef[0]][1] < y[dossier[0]][1]
