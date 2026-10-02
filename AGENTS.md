# hexa-pac-lite

Minimal FastAPI app that serves a single HTML page and a health check, deployable on Railway via Docker.

## Cursor Cloud specific instructions

- Stack: Python 3.12 + FastAPI, served by `uvicorn`. Single service.
- Dependencies are installed into a local virtualenv at `.venv` (gitignored). Activate with `source .venv/bin/activate` before running commands.
- Run the dev server (hot reload): `uvicorn main:app --reload --host 0.0.0.0 --port 8000`. App is then at `http://localhost:8000`.
- Smoke check: `curl localhost:8000/health` returns `{"status":"ok"}`; `GET /` returns the HTML page (200).
- The page is served by reading `templates/index.html` raw and returning it as-is (no Jinja templating), so HTML/JS curly braces are preserved verbatim.
- **`templates/index.html` is the ONLY source of truth for the front.** Edit it directly. (The old snapshot `apercu-fiche-complete (7).html` was removed in Lot 8d: never served, out of date.)
- The fiche's ECS field is `select[name="ecs"]` (id `ecs`), NOT `gestion_ecs`: block 7 is rebuilt at load time and the original `<select name="gestion_ecs">` no longer exists in the live DOM; saved leads store it under `ecs` too.
- Static assets are served from `static/` under `/static`; app data lives in `data/`. Both are kept in git via `.gitkeep`.
- Production/Railway uses the `Dockerfile` + `railway.json` (start command `uvicorn main:app --host 0.0.0.0 --port $PORT`). For local dev use the `--reload` command above instead.
- Persistence is flat JSON files written atomically (tmp + `os.replace`) under `data/`: `data/leads.json` (list) and `data/notes.json` (`{numero: [notes]}`). They are committed in their empty initial state (`[]` / `{}`) and `main.py` recreates them on startup if missing. Gotcha: running the app (importing leads / adding notes) rewrites these files, so `git status` will show them as modified — do not commit local test data.
- Notes are stored as `{texte, date, auteur}` but `GET /prospect/{numero}/commentaires-json` also echoes `texte_html`/`horodatage` so the existing front-end (`chargerNotes`) renders them; keep both key sets when changing the notes shape.
- Lot 6 : la fiche est un parcours télépro en 6 étapes (Contact · Logement · Chauffage · Foyer · Besoin · Proposition), d'après `docs/maquette-parcours-v2.html`. Présentation seulement : la couche `<script id="hexa-lot6-parcours-js">` range les champs existants (jamais recréés ni renommés) dans des sections ; les morceaux du simulateur sont rendus dans `#p-sim-surf` (dans la fiche, sans name), `#p-sim-2`, `#p-sim-4`, `#p-sim-5`, `#p-sim-6a/6b/6r-*`. Le seul calcul ajouté est l'échéancier d'affichage `echeancier(c)` (acompte 30 % / solde 70 % sur la part payée par le client, crédit travaux versé par la banque). Les textes de l'« Accompagnateur d'appel » sont dans la config admin (`/api/script-appel`, Admin → Script d'appel).

## État final de pac-lite (28/09/2026, lots 6 à 6i)

Prod : https://parcours-pac.hexa-renov.fr (Railway, **déploie automatiquement `main`**). `GET /health` est public et renvoie
`{"status":"ok","version":"<12 premiers caractères du commit>"}` : c'est la preuve de déploiement (le reste de la prod est
derrière la connexion ; `/api/...` répond 401 même pour une route inexistante).

- **Parcours télépro en 6 étapes** (Contact · Logement · Chauffage · Foyer · Besoin · Proposition) : présentation seulement,
  les champs historiques sont rangés par `<script id="hexa-lot6-parcours-js">`, jamais recréés ni renommés.
- **Accompagnateur d'appel** (panneau bleu à droite) : textes dans `parametres_admin.json` → `script_appel` (version 3,
  défaut `DEFAULT_SCRIPT_APPEL` de `main.py`), éditables dans Admin → Script d'appel. Une config enregistrée en version < 3
  est remplacée une fois par les textes définitifs, ensuite l'admin fait foi. Question en gras, consigne (`note`) petite et
  grise, texte « à dire » (`type: "dire"`), réponse à boutons (`texte`, `consigne`, `explication` repliée « ▸ Expliquer au
  client », `action` rappel / clôturer), encadrés conditionnels. Conditions : `qN=R`, `dpe`, `!dpe`, `dpe_classe=`, `energie=`,
  `emetteurs=`, `ecs=`, `ecs_chaudiere`, `categorie=`, `service=`, `ballon`, `age<15`, `rfr`, `a & b`, `a | b`. Variables :
  `[civilité nom]`, `[prénom utilisateur]`, `[surface]`, `[année]`, `[année du DPE]`, `[X coût théorique]`, `[catégorie]`,
  `[aides]`, `[MPR]`, `[CEE]`, `[reste à charge]`, `[économie mensuelle]`, `[année avis]` (année en cours), `[année revenus]`.
- **FAQ client** : `script_appel.faq`, bouton « ❓ Questions du client » à chaque étape (recherche sans accents).
- **NRP** : bouton en haut de l'étape 1 = clic sur `#suivi-nrp` (panneau « Fin d'appel ») — même compteur, même échange, mêmes
  relances. Fiche jamais enregistrée : « Enregistrez la fiche pour compter le NRP. »
- **Délégataire CEE** : pré-devis / devis — client qui **attend** MaPrimeRénov' → mention **PICOTY** ; travaux **tout de
  suite** → mention **ACE Énergie** (textes modifiables dans l'admin, `data/delegataires.json`).
- **Zone climatique** : la zone officielle CEE (H1/H2/H3, table du ministère) ne sert qu'à la prime ; la **puissance** utilise
  depuis le Lot 7a, la table **NF P52-612/CN du guide ACE** (zones A à I, paliers d'altitude exacts ; départements à deux zones :
  la plus froide, sauf le 06 : A sous 400 m, E au-dessus), `temperature_base_nf()` côté serveur et le MÊME littéral JSON côté
  front (`tests/test_lot7a_temperature.py` compare les deux).
- **Lot 7a** : mention CEE ACE exacte (montant en chiffres) + sous-traitant ; « Ancien système de chauffage déposé » et
  « Application » dans le bloc Solution chauffage (devis et facture) ; « Émettre une facture rectificative » (admin, dossier
  verrouillé ; comparée ligne à ligne au PDF d'origine avant émission, aperçu « APERÇU — sans numéro »).
- **Lot 7c** : « 📄 Émettre la rectificative depuis un aperçu » (Documents → Factures, admin, dossier verrouillé) : l'aperçu
  PDF importé est contrôlé, le numéro qui sera attribué est montré (`…/rectificative-apercu/verifier`, rien n'est écrit),
  puis `…/emettre` l'inscrit à la place de « APERÇU — sans numéro » (`services/rectificative_apercu.py`, pypdf +
  reportlab, polices reprises de l'aperçu) sans rien régénérer. PyMuPDF (AGPL) n'est volontairement PAS utilisé en
  production ; il ne sert qu'aux tests, pour fabriquer un aperçu d'essai.
- **Lot 7d** : documents imprimés (devis, pré-devis, facture ; écran et PDF) SANS date de chantier — ni « Début travaux », ni
  « Fin travaux », ni « Travaux achevés le … » ; bloc identité 12 / 12 lignes alignées (la facture met « Réf. devis » dans
  DOSSIER). Le CRM garde la date de fin de travaux (saisie à la génération, enregistrée, affichée dans Documents → Factures).
  Les nouvelles factures portent `"mise_en_page": "lot7d"` ; la rectificative d'une facture SANS cette marque garde la mise
  en page d'origine (`facture_mise_en_page_avant_lot7d`), sinon elle ne serait plus identique ligne à ligne. « Application :
  haute température » (radiateurs) / « basse température » (plancher chauffant). ETAS 35 / 55 : les deux valeurs, seule celle
  qui compte en gras 700 (radiateurs → 55 °C, plancher → 35 °C, `etas_html`), l'autre en normal.
- **Catalogue — régulateur** (`services/catalogue_regulateur.py`) : au démarrage (`_migrate_catalogue_regulateur`,
  idempotente, écrit avec sauvegarde seulement si besoin), chaque fiche PAC porte « Classe du régulateur (ErP) » puis
  « Contribution à l'efficacité saisonnière (%) » juste après « Alimentation ». Ligne absente / vide : valeur du Master
  (`VALEURS_MASTER`, par n° EPREL, relevée dans hexa-simulateur-2) ; valeur déjà saisie : gardée, seulement replacée.
  Sans équivalent certain : rien n'est inventé (journal `[catalogue] … sans valeur`).
- **Lot 8d (nettoyage)** : retirés car jamais appelés (preuve : aucune référence dans le code, les modèles, les e-mails
  ni les tests ; écrans identiques au pixel sur 34 vues ; documents identiques au banc de 10 fiches) — 44 fonctions et
  10 variables JS d'`index.html`, 667 règles CSS sans élément correspondant (anciennes barres latérale / du haut, thème,
  éditeur, étiquettes…), 7 fonctions Python (dont `_html_to_pdf` WeasyPrint et `_generate_devis_pdf` ReportLab),
  les dépendances `weasyprint` et `pydyf`, la copie `apercu-fiche-complete (7).html`. Une classe construite à la volée
  (`'prefixe-' + x`, `` `prefixe-${x}` ``, `x + '-suffixe'`) compte comme utilisée.
- **Verrou « dossier facturé »** : installation finie ou facture émise → `dossier_fige` (jamais stocké), toute écriture du
  lead / du simulateur refusée en 423, fiche en lecture seule ; le devis et la note de dim servis sont ceux archivés à
  l'envoi (`data/devis/devis_meta.json`), rien n'est régénéré.
- **DPE / audit** (`services/dpe_audit.py`, logique du Master hexa-simulateur-2) : point BAN, 50 m, documents depuis le
  01/07/2021, audits à l'état initial ; autre numéro, bis/ter ou autre voie écartés. Même logement à adresse confirmée (hors
  appartement / immeuble) : le **plus récent** est retenu, l'audit à date égale ; sinon choix dans `#dpe-banner`. Une seule
  fonction de remplissage (`<script id="hexa-dpe-master-js">`) : n'écrit que dans un champ vide ou rempli par elle — une
  saisie manuelle n'est jamais écrasée ; pas de relance à l'ouverture d'une fiche. Coût = chauffage + eau chaude du document
  (`setCoutEnergieAuto`, DPE et audit au même rang, facture réelle toujours prioritaire).
- **Valeur du bien** (`services/valeur_dvf.py`, DVF Etalab, méthode du Master) : médiane → `prix_m2_estime`, Q1 / Q3 →
  `prix_m2_min` / `prix_m2_max` (si vides ou remplis automatiquement) ; valeur = `prix_m2_estime × surface` ; seule clé
  ajoutée au lead : `valeur_bien_source`. Cache `DATA_DIR/cache_dvf` (30 jours, exclu de la sauvegarde GitHub).
- **Note de dim** : avant la VT, « Pré-note de dim (provisoire) » (fenêtre du simulateur, filigrane à l'impression) ; après,
  bouton vert « 📐 Note de dim définitive » (onglet de la fenêtre du devis). Noms des PDF : interne `NoteDim-DEFINITIVE_ND…`,
  `Pre-devis_PD…`, `Devis_DE…` ; côté client (liens e-mail) `Note-de-dimensionnement_ND…`, `Pre-devis_PD…`, `Devis_DE…`.
- **Facture** : panneau Suivi → « 🧾 Générer la facture » (installation finie, pas de facture) ou « 🧾 Voir la facture ».
- Clés DocuSeal / Resend : seulement sur Railway. En local, l'envoi réel est impossible (le script de bout en bout le simule).

### Tests
- `python -m pytest tests -q` — toute la suite, dont les tests Playwright (vrai Chromium, fiches fabriquées, aucun service
  extérieur). Prérequis : `python -m pip install -r requirements.txt` puis `python -m playwright install chromium`.
- `node scripts/test_render_race_simulateur.mjs` et `node scripts/test_categorie_simulateur.mjs` — tests statiques du simulateur.
- `python scripts/e2e_appel_local.py` — parcours complet d'un appel (nouvelle fiche → NRP → rappel → DPE → 6 étapes → devis →
  VT → note définitive → envoi simulé → installation finie → facture → verrou), rapport OK/KO par étape.
- Un test qui passe doit aussi échouer sur l'ancien code : rejouer les nouveaux tests sur `git show origin/main:…` avant de
  conclure.

### Retour arrière
Chaque lot arrive par un commit de merge sur `main`. Pour l'annuler :
`git revert -m 1 <sha du merge> --no-edit && git push origin main` — Railway redéploie `main` ; vérifier ensuite que
`/health` renvoie le nouveau hash.
