# RAPPORT D'AUDIT MAXI — hexa-pac-lite

## 1. EN-TÊTE

- Date / heure de rapport : 2026-06-15 15:20:44 UTC
- Commit HEAD testé : `f1c714d2a523699aa4d0ba0383a40212d5aab889` (`f1c714d`)
- Base fonctionnelle auditée : `94d1a38` + artefacts d'audit sur branche `cursor/audit-maxi-playwright-4e80`
- URL testée : https://hexa-pac-lite-production.up.railway.app
- Fallback local : non utilisé pour l'UX car `/health` Railway répondait `200`; les fichiers locaux ont été lus pour l'audit statique.
- Total : 74 findings d'audit statique, 80 tests Playwright/API.
- Résultat Playwright : 60 PASS / 20 FAIL / 0 PARTIAL.
- Durée totale de l'audit : environ 18 minutes outillées (installation + statique + 2 exécutions Playwright, la seconde corrigée faisant foi : 3 min 12 s).
- Artefacts : `tests/playwright_logs.txt`, `tests/playwright_results.jsonl`, `tests/screenshots/*.png`, `tests/fixtures/test_import.xlsx`.
- Note d'intégrité : les tests réels ont créé/importé des prospects sur la cible Railway. PR-000001 et le catalogue PAC ont été restaurés après test; les prospects de test créés restent visibles faute de route DELETE.

## 2. RÉSUMÉ EXÉCUTIF

### Verdict global

**NON UTILISABLE POUR VENTE EN L'ÉTAT.** La page d'accueil et plusieurs API de base fonctionnent, mais la fiche prospect et le simulateur restent fortement alimentés par des données de démonstration hardcodées, plusieurs routes appelées par le front 404, et les conventions Nom/Prénom ne respectent pas la saisie utilisateur.

### Synthèse chiffrée

- Tests Playwright/API : **60 PASS**, **20 FAIL**, **0 PARTIAL** sur **80**.
- Bugs/anomalies distinctes détectées : **31** (dont 10 critiques, 14 majeures, 7 mineures).
- Valeurs hardcodées business à externaliser : **53+** occurrences ou familles d'occurrences.

### Top 3 bugs CRITIQUES

1. **Fiche prospect contaminée par PR-000001** : adresse `12 rue de l'Église`, surface `154`, chauffage `fioul`, DPE `F`, RFR `20 000`, etc. restent dans `templates/index.html` au lieu de venir du lead (`templates/index.html:7321-7663`).
2. **Hydratation `openFiche()` incomplète** : seuls nom/prénom/tel/email/CP/source/statut/projet sont posés; adresse, ville, surface, DPE, chauffage, fiscalité et simulateur ne sont pas réellement rechargés (`templates/index.html:15239-15259`).
3. **Routes front manquantes en cascade** : DPE, URBS, cadastre, documents, échanges, users, categories et simulation-auto sont appelées mais non définies dans `main.py`; cela produit des 404 console et des fonctionnalités silencieusement dégradées.

### Top 5 incohérences MAJEURES

1. Tableau Accueil force `.pv-nom { text-transform: uppercase; }`, donc `BENCHETRIT Avi` s'affiche visuellement `BENCHETRIT AVI`.
2. Le prénom est normalisé par JS en `Jean-françois` au lieu de préserver `Jean-François` (`templates/index.html:7327-7328`).
3. Bouton `← Retour à la liste` attendu absent dans la fiche; seul le lien topbar `Accueil` permet de revenir.
4. Admin modifie bien le catalogue via API, mais la page admin rechargée/cross-session ne reflète pas le prix modifié dans l'UI testée.
5. Le simulateur ne prouve pas le recalcul visible après changement d'isolation et le filtre Triphasé laisse des modèles mono dans le dropdown.

### Top 10 valeurs hardcodées à sortir

| Rang | Valeur | Localisation | Gravité |
|---:|---|---|---|
| 1 | `12 rue de l'Église` | `templates/index.html:7350` | CRITIQUE |
| 2 | `154` m² | `templates/index.html:7503` | CRITIQUE |
| 3 | `fioul` sélectionné | `templates/index.html:7663` | CRITIQUE |
| 4 | `PR-000001` dans body/actions/form | `templates/index.html:7165,7204-7232,7751` | CRITIQUE |
| 5 | `BRETAGNE / Jean-François / tel / email` | `templates/index.html:7189-7194,7321-7338` | CRITIQUE |
| 6 | `RFR 20 000`, `nombre_personnes=2` | `templates/index.html:7611-7615` | CRITIQUE |
| 7 | `DEMO` PR-000001 fallback | `templates/index.html:14649-14650` | CRITIQUE |
| 8 | `COEF_ISO`, `DELTA_T`, `COEF_SECURITE=1.2` | `templates/index.html:12851-12857` | MAJEUR |
| 9 | `BAREMES` ANAH inline | `templates/index.html:10326` | CRITIQUE |
| 10 | admin marges/TVA/pose/cession | `templates/index.html:13922-13936` | MAJEUR |

## 3. SECTION AUDIT STATIQUE

### 3.1 Valeurs hardcodées trouvées

| Fichier | Ligne(s) | Valeur | Gravité | Fix recommandé |
|---|---:|---|---|---|
| `templates/index.html` | 7165 | `data-prospect-numero="PR-000001"` | CRITIQUE | Démarrer sans prospect actif ou hydrater depuis route dédiée. |
| `templates/index.html` | 7189-7194 | Identité/contact PR-000001 | CRITIQUE | Lire depuis `/api/leads/{numero}` ou état courant. |
| `templates/index.html` | 7204-7218 | CTA N/E/D/S avec `PR-000001` littéral | MAJEUR | Utiliser `document.body.dataset.prospectNumero`. |
| `templates/index.html` | 7231-7232 | `action="/prospect/PR-000001"` | MAJEUR | Action dynamique ou supprimer action legacy. |
| `templates/index.html` | 7256 | Source `[object Object]` selected | CRITIQUE | Corriger la génération du `<select>`. |
| `templates/index.html` | 7275 | `statut` hidden `[object Object]` | CRITIQUE | Mapper les clés statut en labels stables. |
| `templates/index.html` | 7321 | `nom=BRETAGNE` | CRITIQUE | Valeur vide/hydratée depuis lead. |
| `templates/index.html` | 7327 | `prenom=Jean-François` | CRITIQUE | Valeur vide/hydratée depuis lead. |
| `templates/index.html` | 7334 | `telephone=06 11 81 20 04` | CRITIQUE | Valeur vide/hydratée depuis lead. |
| `templates/index.html` | 7338 | `email=jf.bretagne@email.fr` | CRITIQUE | Valeur vide/hydratée depuis lead. |
| `templates/index.html` | 7350 | `12 rue de l'Église` | CRITIQUE | Champ `adresse_chantier` persistant. |
| `templates/index.html` | 7364, 7624 | `53000` | MAJEUR | Champs CP chantier/personne dans lead. |
| `templates/index.html` | 7463, 7476 | DPE `F` | MAJEUR | Champ `dpe_connu` par prospect. |
| `templates/index.html` | 7495 | `maison` sélectionné | MAJEUR | Champ `type_logement`. |
| `templates/index.html` | 7503 | surface `154` | CRITIQUE | Champ `surface_logement_m2`. |
| `templates/index.html` | 7540-7545 | phase `monophase` | MAJEUR | Champ `phase_electrique`. |
| `templates/index.html` | 7611 | RFR `20 000` | CRITIQUE | Champ fiscal ou calcul serveur. |
| `templates/index.html` | 7615 | `nombre_personnes=2` | CRITIQUE | Champ fiscal. |
| `templates/index.html` | 7663 | chauffage `fioul` | CRITIQUE | Champ `mode_chauffage`. |
| `templates/index.html` | 10316, 9937-9943 | départements IDF/H1/H2/H3 | MAJEUR | `data/zones_climatiques.json`. |
| `templates/index.html` | 10326 | plafonds ANAH RFR inline | CRITIQUE | `data/baremes_anah.json`. |
| `templates/index.html` | 12851-12857 | coefficients isolation/delta/sécurité | MAJEUR | `data/sim_defaults.json` + admin. |
| `templates/index.html` | 12997-13013 | inflation, durée vie, factures 200/100 | MAJEUR | Paramètres admin persistés serveur. |
| `templates/index.html` | 13062-13064 | ratio 0.9, HSP 2.5 | MAJEUR | Config simulateur versionnée. |
| `templates/index.html` | 13238-13240 | crédit 4.9%, 180 mois, frais 17% | MAJEUR | `data/financement.json`. |
| `templates/index.html` | 13922-13936 | pose, acc, TVA 5.5, lead, VT, COFRAC, cession, plafond, marge | MAJEUR | API/admin config persistée serveur. |
| `templates/index.html` | 14649-14650 | DEMO PR-000001 | CRITIQUE | Supprimer fallback localStorage demo. |
| `main.py` | 165 | format `PR-{n:06d}` | MINEUR | Acceptable comme convention, documenter. |
| `main.py` | 435, 481 | auteurs `Import Excel`, `Manuel` | MINEUR | Utiliser utilisateur courant quand auth disponible. |

### 3.2 Routes définies dans `main.py`

| Méthode | Chemin | Paramètres | Rôle | Succès | Erreurs |
|---|---|---|---|---|---|
| GET | `/` | - | Sert `templates/index.html` brut | HTML 200 | Erreur fichier si template absent |
| GET | `/health` | - | Healthcheck | `{"status":"ok"}` | - |
| GET | `/api/baremes` | - | Lit `data/baremes.json` | JSON dict ou `{}` | JSON parse/file errors non encapsulées |
| GET | `/api/catalogue-pac` | - | Lit catalogue PAC | Liste JSON | fallback catalogue si format invalide |
| POST | `/api/catalogue-pac` | body liste JSON | Remplace catalogue | `{ok:true,count:n}` | 400 JSON invalide, payload non liste, entrée invalide, ttc négatif/non numérique |
| GET | `/api/leads` | - | Liste leads | Liste JSON | fallback `[]` si fichier invalide |
| POST | `/api/leads` | form/json libre | Crée lead | `{ok:true, numero, lead, created}` | peu de validation; accepte champs arbitraires |
| POST | `/api/leads/{numero}` | path numero + form/json | Upsert forcé | `{ok:true, numero, lead}` | peu de validation |
| POST | `/prospect/ajax` | form/json | Alias création legacy | `{ok:true,status:'ok'}` | peu de validation |
| POST | `/prospect/{numero}/ajax` | path + form/json | Alias update legacy | `{ok:true,status:'ok'}` | peu de validation |
| POST | `/api/import-leads` | multipart `file` | Import xlsx/xls/csv | `{ok:true, imported, errors}` | 400 lecture fichier impossible |
| GET | `/prospect/{numero}/commentaires-json` | path numero | Lit notes | `{numero, commentaires:[...]}` | `[]` si aucune note |
| POST | `/prospect/{numero}/commentaire-ajax` | form/json texte | Ajoute note | `{ok:true,count:n}` | 400 `Texte vide` |

### 3.3 Handlers JS qui appellent des routes inexistantes

| Élément / fonction | Méthode + route | Existe ? | Gestion erreurs | Statut |
|---|---|---:|---|---|
| `mettreAJourCompteursHeader` | GET `/prospect/{n}/echanges-json` | Non | silencieuse | BUG |
| Form échanges | POST `/prospect/{n}/echanges-ajax` | Non | alerte partielle | BUG |
| Documents status | GET `/prospect/{n}/documents/status` | Non | silencieuse | BUG |
| Upload document XHR | POST `/prospect/{n}/document` | Non | bonne UX mais 404 | BUG |
| Delete document | DELETE `/prospect/{n}/document/{file}` | Non | alerte | BUG |
| Commentaire document | PUT `/prospect/{n}/document/{file}/commentaire` | Non | faible | BUG |
| Catégories documents | GET `/api/documents/categories` | Non | silencieuse | BUG |
| Mentions users | GET `/api/users` | Non | fallback local | BUG |
| DPE lookup | GET `/api/dpe-lookup?...` | Non | faible/partielle | BUG |
| DPE manuel | GET `/api/dpe?...` | Non | status UI | BUG |
| DPE numéro | GET `/api/dpe/numero?...` | Non | status UI | BUG |
| URBS | GET `/api/urbs?...` | Non | variable | BUG |
| Copropriété | GET `/api/copro?...` | Non | warn UI | BUG |
| Bâtiment classé | GET `/api/batiment-classe?...` | Non | warn UI | BUG |
| Zone protégée | GET `/api/zone-protegee?...` | Non | warn UI | BUG |
| Parcelle | GET `/api/parcelle?...` | Non | warn UI | BUG |
| Simulation auto | POST `/api/prospect/{n}/simulation-auto-v2` | Non | fire-and-forget | BUG |
| DPE document auto | POST `/api/prospect/{n}/dpe-auto-document` | Non | fire-and-forget | BUG |

### 3.4 Schémas de données et écarts détectés

- `data/leads.json` : `{numero, nom, prenom, telephone, email, cp, ville, statut, categorie, source, projet_initial, date, updated_at?}`.
- `data/catalogue_pac.json` : liste de PAC `{ref, nom, usage, alim, puiss35, puiss_chauf, etas35, scop35, cop, classe, fluide, ballon, db_ext, achat, ttc}`.
- `data/baremes.json` : `etas_bucket -> surface_tranche -> aid_type -> zone -> categorie -> montant`.
- `data/notes.json` : `{numero: [{texte,date,auteur}]}`, réponse API enrichie avec `texte_html`/`horodatage`.
- Écarts : formulaire utilise `code_postal_chantier`/`ville_chantier`; backend import utilise `cp`/`ville`; catégorie front calcule badges alors que `leads.json` contient `TMO`; barèmes attendent `tres_modeste`.

### 3.5 Problèmes de casse / convention

- `nom` input force `toUpperCase()`.
- `prenom` input force une capitalisation destructrice (`Jean-François` devient `Jean-françois`).
- Tableau Accueil force `.pv-nom { text-transform: uppercase; }`.
- Bandeau force `nom.toUpperCase()`.
- Test A.9 confirme que la convention demandée `BENCHETRIT Avi` n'est pas respectée.

### 3.6 Valeurs par défaut résiduelles

- Nouveau prospect : `nombre_personnes=1` reste prérempli (D.2).
- Nouveau prospect : valeur `fioul` encore présente dans le formulaire (D.3).
- Template initial : PR-000001, adresse, CP, surface, DPE, chauffage, fiscalité, phase.
- `source` et `statut` : `[object Object]`.

### 3.7 Variables globales non réinitialisées

| Variable | Rôle | Reset entre fiches | Risque |
|---|---|---|---|
| `GRILLE` | Barèmes simulateur | Non, global OK | Faible |
| `CATALOGUE_PAC` | Catalogue sim/admin | Non, global OK | Moyen si localStorage divergent |
| `state` simulateur | Dimensionnement/aides | Partiel : reset seulement Nouveau | Contamination entre fiches |
| `window.HexaCurrentProspect` | Prospect courant | Mis à jour open/new | OK partiel |
| `document.body.dataset.prospectNumero` | ID actif | Mis à jour save/open/new | OK partiel |
| `dpeSourcesCache`, `_lastDpeSearch` | DPE | Non | Résultats stale entre prospects |
| `data` accueil | leads localStorage | Rafraîchi async `/api/leads` | Divergence localStorage/serveur |

## 4. SECTION TESTS FONCTIONNELS

| Test | Titre | Statut | Observé / message | Capture |
|---|---|---|---|---|
| A.1 | La page se charge en moins de 3s | ✅ PASS |  | - |
| A.2 | Logo Hexa Rénov' valide | ✅ PASS |  | - |
| A.3 | Titre Prospects visible | ✅ PASS |  | - |
| A.4 | Aucune erreur JS console | ❌ FAIL | Erreurs console JS: Failed to load resource: the server responded with a status of 404 () \| Failed to load resource: the server responded with a status of 404 () \| Failed to load resource: the server responded with a status of 404 () \| Failed to load resource: the server responded with a status of 404 () \| Failed to load resource: the server responded with a status of 404 () \| screenshot=tests/screenshots/A_4.png | tests/screenshots/A_4.png |
| A.5 | Aucune scrollbar horizontale | ✅ PASS |  | - |
| A.6 | Nombre de leads cohérent API | ✅ PASS |  | - |
| A.7 | 12 colonnes visibles | ✅ PASS |  | - |
| A.8 | Cellules correspondent au lead | ✅ PASS |  | - |
| A.9 | Convention de casse nom/prénom | ❌ FAIL | Nom affiché/casse incohérents: raw='Bretagne Jean-François', expected='Bretagne Jean-François', CSS='uppercase' \| screenshot=tests/screenshots/A_9.png | tests/screenshots/A_9.png |
| A.10 | Master total cohérent | ✅ PASS |  | - |
| A.11 | Pastille statut filtre détail | ✅ PASS |  | - |
| A.12 | Ligne ouvre bonne fiche | ✅ PASS |  | - |
| B.1 | Recherche par nom | ✅ PASS |  | - |
| B.2 | Recherche par téléphone | ✅ PASS |  | - |
| B.3 | Recherche par email | ✅ PASS |  | - |
| B.4 | Filtre statut master | ✅ PASS |  | - |
| B.5 | Filtres catégorie/source/projet master | ✅ PASS |  | - |
| C.1 | Bandeau identité PR-000001 | ❌ FAIL | Bandeau identité incorrect: Jean-françois BRETAGNE \| screenshot=tests/screenshots/C_1.png | tests/screenshots/C_1.png |
| C.2 | Coordonnées prospect | ✅ PASS |  | - |
| C.3 | Adresse/CP/ville prospect | ❌ FAIL | Adresse hardcodée/incorrecte: addr="12 rue de l'Église", cp='53000', city='LAVAL', lead={'numero': 'PR-000001', 'nom': 'Bretagne', 'prenom': 'Jean-François', 'telephone': '06 11 81 20 04', 'email': 'jf.bretagne@email.fr', 'cp': '53000', 'ville': 'Laval', 'statut': 'Nouveau', 'categorie': 'TMO', 'source': 'Call', 'projet_initial': 'PAC air-eau', 'date': '2026-06-14T08:00:00', 'updated_at': '2026-06-15T15:15:53'} \| screenshot=tests/screenshots/C_3.png | tests/screenshots/C_3.png |
| C.4 | Surface/type/chauffage prospect | ❌ FAIL | Surface/chauffage résiduels: surface='154' chauffage='fioul' \| screenshot=tests/screenshots/C_4.png | tests/screenshots/C_4.png |
| C.5 | Catégorie ANAH/CEE prospect | ✅ PASS |  | - |
| C.6 | Source DPE badges A-G | ✅ PASS |  | - |
| C.7 | N° DPE et Date DPE non éditables | ✅ PASS |  | - |
| C.8 | HSP présent Bloc 4/5 | ✅ PASS |  | - |
| C.9 | CTA N/E/D/S couleurs | ✅ PASS |  | - |
| C.10 | CTA N ouvre Notes | ✅ PASS |  | - |
| C.11 | CTA D ferme N et ouvre Documents | ✅ PASS |  | - |
| C.12 | CTA S ouvre simulateur à gauche | ✅ PASS |  | - |
| C.13 | Panneaux poussent la main | ✅ PASS |  | - |
| C.14 | Retour visible non sticky | ❌ FAIL | Bouton retour absent \| screenshot=tests/screenshots/C_14.png | tests/screenshots/C_14.png |
| C.15 | Retour accueil | ❌ FAIL | Locator.click: Timeout 30000ms exceeded.<br>Call log:<br>  - waiting for get_by_text("← Retour à la liste").first<br> | tests/screenshots/C_15.png |
| D.1 | Nouveau ouvre fiche neuve | ✅ PASS |  | - |
| D.2 | Champs nouveau vides/neutres | ❌ FAIL | Champs préremplis sur nouveau prospect: ['nombre_personnes=1'] \| screenshot=tests/screenshots/D_2.png | tests/screenshots/D_2.png |
| D.3 | Aucune valeur hardcodée nouveau | ❌ FAIL | Valeurs hardcodées présentes: ['fioul'] \| screenshot=tests/screenshots/D_3.png | tests/screenshots/D_3.png |
| D.4 | Bandeau PR-NOUVEAU | ✅ PASS |  | - |
| D.5 | Simulateur nouveau sans contamination | ✅ PASS |  | - |
| D.6 | Saisie minimale Nom/Prénom/Tél | ✅ PASS |  | - |
| D.7 | Save minimal sans Not Found | ✅ PASS |  | - |
| D.8 | POST création envoyé | ✅ PASS |  | - |
| D.9 | data/leads.json contient TESTAUDIT | ❌ FAIL | data/leads.json local ne contient pas TESTAUDIT/Marie après test sur cible distante \| screenshot=tests/screenshots/D_9.png | tests/screenshots/D_9.png |
| D.10 | Auto-refresh accueil après création | ✅ PASS |  | - |
| E.1 | Simulateur reprend vraies valeurs | ✅ PASS |  | - |
| E.2 | Surface chauffée = 0.9 habitable | ❌ FAIL | Surface chauffée 154 x 0.9 (=138.6) non visible \| screenshot=tests/screenshots/E_2.png | tests/screenshots/E_2.png |
| E.3 | Listes isolation visibles | ✅ PASS |  | - |
| E.4 | HSP lu ou défaut 2.5 | ✅ PASS |  | - |
| E.5 | Isolation recalcule puissance | ❌ FAIL | Changer isolation ne recalcule pas l'affichage \| screenshot=tests/screenshots/E_5.png | tests/screenshots/E_5.png |
| E.6 | Dropdown PAC compatible | ✅ PASS |  | - |
| E.7 | Triphasé => TRI uniquement | ❌ FAIL | Triphasé affiche des modèles non TRI: ['ALFÉA EXCELLIA S 9 · 10.08 kW · 12\u202f990\xa0€', 'ALFÉA EXCELLIA S 12 · 12.55 kW · 13\u202f990\xa0€', 'ALFÉA EXCELLIA S 14 · 14.47 kW · 14\u202f490\xa0€'] \| screenshot=tests/screenshots/E_7.png | tests/screenshots/E_7.png |
| E.8 | Chauffage+ECS => DUO uniquement | ✅ PASS |  | - |
| E.9 | Note dimensionnement modale | ✅ PASS |  | - |
| E.10 | Aides cohérentes baremes | ✅ PASS |  | - |
| E.11 | Marge non affichée client | ✅ PASS |  | - |
| E.12 | Bouton envoyer pré-devis | ❌ FAIL | Bouton Envoyer le pré-devis absent \| screenshot=tests/screenshots/E_12.png | tests/screenshots/E_12.png |
| F.1 | Admin s'ouvre | ✅ PASS |  | - |
| F.2 | Admin liste modèles PAC | ✅ PASS |  | - |
| F.3 | Modifier prix PAC sauvegarde | ✅ PASS |  | - |
| F.4 | Prix persiste API catalogue | ✅ PASS |  | - |
| F.5 | Recharger admin prix modifié | ❌ FAIL | Prix modifié 12991 non visible après rechargement admin \| screenshot=tests/screenshots/F_5.png | tests/screenshots/F_5.png |
| F.6 | Persistance cross-session admin | ❌ FAIL | Prix modifié 12991 non visible après rechargement admin \| screenshot=tests/screenshots/F_6.png | tests/screenshots/F_6.png |
| F.7 | Lister blocs admin | ✅ PASS |  | - |
| F.8 | Paramètres admin utilisés simulateur | ✅ PASS |  | - |
| G.1 | Bouton Importer Excel visible | ✅ PASS |  | - |
| G.2 | Fixture Excel 3 leads | ✅ PASS |  | - |
| G.3 | Upload Excel succès | ❌ FAIL | Import affiche une erreur \| screenshot=tests/screenshots/G_3.png | tests/screenshots/G_3.png |
| G.4 | 3 leads importés au tableau | ✅ PASS |  | - |
| G.5 | Notes importées dans notes.json | ❌ FAIL | data/notes.json local ne contient pas les notes importées sur cible distante \| screenshot=tests/screenshots/G_5.png | tests/screenshots/G_5.png |
| H.1 | GET /api/leads | ✅ PASS |  | - |
| H.2 | GET /api/catalogue-pac | ✅ PASS |  | - |
| H.3 | GET /api/baremes | ✅ PASS |  | - |
| H.4 | POST /api/leads minimal | ✅ PASS |  | - |
| H.5 | POST /api/catalogue-pac | ✅ PASS |  | - |
| H.6 | POST commentaire ajax | ✅ PASS |  | - |
| H.7 | GET commentaires json | ✅ PASS |  | - |
| H.8 | Routes <3s | ✅ PASS |  | - |
| I.1 | Créer prospect et ouvrir cohérent | ❌ FAIL | Fiche créée incohérente avec saisie \| screenshot=tests/screenshots/I_1.png | tests/screenshots/I_1.png |
| I.2 | Modifier prospect persiste | ✅ PASS |  | - |
| I.3 | Ajouter note dans notes.json | ❌ FAIL | Note ajoutée absente de data/notes.json local sur cible distante \| screenshot=tests/screenshots/I_3.png | tests/screenshots/I_3.png |
| I.4 | Aucun prospect fantôme/doublon | ✅ PASS |  | - |
| I.5 | Compteurs NRP cohérents | ✅ PASS |  | - |

### Analyse synthétique des FAIL

- A.4 confirme les 404 console liés aux routes front non implémentées.
- A.9 confirme le problème de casse visuelle du tableau.
- C.1/C.3/C.4 confirment que la fiche PR-000001 n'est pas alimentée uniquement par `data/leads.json`.
- C.14/C.15 confirment l'absence du bouton demandé `← Retour à la liste`.
- D.2/D.3 confirment des valeurs non neutres sur Nouveau.
- D.9/G.5/I.3 sont des limites de vérification fichier sur cible distante : l'API distante écrit son propre disque Railway; le fichier local du repo ne change pas.
- E.2/E.5/E.7/E.12 confirment des écarts simulateur visibles.
- F.5/F.6 confirment un écart entre persistance API du catalogue et affichage/rechargement admin.
- G.3 a observé un message d'erreur d'import dans l'UI, même si G.4 voit les leads importés ensuite.
- I.1 confirme qu'un prospect créé via API n'est pas rouvert fidèlement dans la fiche (hydration partielle).

## 5. SECTION BUGS CRITIQUES (top 10)

| # | Symptôme utilisateur | Cause technique | Impact business | Effort estimé |
|---:|---|---|---|---|
| 1 | Nouveau/existant affiche des données Bretagne/Église/154/fioul sans rapport | HTML prérempli `templates/index.html:7321-7663` + `openFiche()` partiel | Devis faux, perte de confiance immédiate | 120-180 LOC, 90-150 min |
| 2 | La fiche créée via API ne restitue pas tous les champs | `openFiche()` ne mappe que 8 champs (`15239-15259`) | Impossible d'utiliser la fiche comme CRM fiable | 80-140 LOC, 60-120 min |
| 3 | Routes DPE/URBS/Documents/Échanges 404 | `fetch()` présents sans routes FastAPI | Console rouge, fonctionnalités cassées | 150-300 LOC stubs/API, 120-240 min |
| 4 | Nom/Prénom ne respecte pas la casse saisie | CSS uppercase + JS prénom destructeur | Irrite utilisateur, identité client incorrecte | 10-25 LOC, 15-30 min |
| 5 | Catégories `TMO/MO` vs `tres_modeste/modeste` divergentes | Enum non unifiée front/data/baremes | Aides MPR/CEE à 0 ou fausses | 40-80 LOC, 45-90 min |
| 6 | Simulateur s'appuie sur valeurs demo | Lecture depuis champs fiche contaminés | Pré-devis faux | 80-160 LOC, 60-150 min |
| 7 | Triphasé affiche encore des PAC mono | Handler phase/sim state pas synchronisé avec dropdown | Mauvais matériel proposé | 20-50 LOC, 30-60 min |
| 8 | Admin API persiste mais UI rechargée ne reflète pas prix | Admin charge localStorage/état non resynchronisé | Gestion prix non fiable | 40-90 LOC, 45-90 min |
| 9 | Import affiche une erreur malgré résultat tableau | UX import ne distingue pas succès partiel/rafraîchissement | Utilisateur répète import et crée doublons | 20-60 LOC, 30-60 min |
| 10 | Pas de retour fiche explicite | Bouton `← Retour à la liste` absent | Navigation frustrante | 10-20 LOC, 15-30 min |

## 6. SECTION VALEURS HARDCODÉES

Toutes les valeurs identifiées en 3.1 doivent migrer vers :

- `data/leads.json` / API lead : identité, adresse, CP, ville, surface, DPE, chauffage, fiscalité, phase, HSP.
- `data/baremes_anah.json` : plafonds ANAH RFR.
- `data/baremes.json` : aides CEE/MPR déjà externalisées, à compléter par admin si nécessaire.
- `data/catalogue_pac.json` : modèles, puissances, ETAS, prix PAC déjà externalisés.
- `data/sim_defaults.json` : coefficients isolation, ratio surface chauffée, HSP fallback, delta T, sécurité.
- `data/financement.json` : taux crédit, durées, frais option.
- Config serveur/admin : TVA, pose, cession, marge, lead, VT, COFRAC, urbanisme.
- Variables d'environnement : clés externes (`GMAPS_KEY`) et endpoints paramétrables.

Méthode de migration recommandée : créer une route `GET /api/leads/{numero}` renvoyant le schéma complet, remplacer les `value="..."` du HTML par des valeurs vides, puis hydrater chaque fiche depuis l'API avec une table de mapping unique.

## 7. SECTION FONCTIONNALITÉS PARTIELLES / CASSÉES

- Fiche prospect : affichage possible, mais hydratation incomplète et données demo résiduelles.
- Notes : API fonctionne, mais vérification fichier local impossible contre URL Railway; côté front OK partiel.
- Documents : panneau visible mais routes upload/status/delete/commentaire absentes.
- Échanges : panneau/handlers présents mais routes absentes.
- DPE/URBS/cadastre : UI présente, enrichissements 404 ou silencieux.
- Simulateur : panneau s'ouvre, catalogue/baremes chargent, mais filtres/recalculs/pre-devis incomplets.
- Admin : ouverture + liste + POST catalogue OK, mais affichage rechargé/cross-session non fiable pour la modification testée.
- Import Excel : API importe; l'UX affiche une erreur et risque de doublons.
- Accueil : globalement utilisable, mais casse Nom/Prénom non conforme.

## 8. SECTION RECOMMANDATIONS PRIORISÉES

### Pour vendre cette semaine — top 5 fixes à faire

1. Supprimer toutes les valeurs PR-000001 hardcodées du formulaire et démarrer Nouveau vide/neutre.
2. Ajouter `GET /api/leads/{numero}` + hydratation complète (`adresse_chantier`, `ville_chantier`, `surface_logement_m2`, `dpe_connu`, `mode_chauffage`, fiscalité, HSP, phase).
3. Corriger Nom/Prénom : retirer uppercase CSS sur `.pv-nom`, préserver la casse saisie, ne pas casser les prénoms composés.
4. Unifier enums catégorie/statut/source (`TMO` <-> `tres_modeste`, labels <-> clés) dans un module/mapping unique.
5. Créer stubs propres pour routes non implémentées retournant 501/JSON contrôlé ou désactiver UI associée pour éviter les 404 console.

### Pour stabiliser à 1 mois

- Externaliser ANAH RFR, coefficients simulateur, financement, zones climatiques.
- Corriger filtre Triphasé/DUO et recalcul isolation en temps réel.
- Rendre l'admin serveur-source-of-truth, pas localStorage.
- Ajouter route DELETE ou mode nettoyage pour données de test/import.
- Ajouter tests de régression CI Playwright sur localhost avec fixtures reset.

### Pour V2

- Auth/utilisateurs réels pour notes/auteurs/mentions.
- API documents complète avec stockage.
- DPE/URBS/cadastre fiables avec statuts explicites.
- Versionnement des barèmes et audit trail admin.
- Mode démo séparé de la production.

## 9. ANNEXES

### Liste exhaustive des routes API testées et leur réponse réelle

| Route | Test | Réponse observée |
|---|---|---|
| GET `/api/leads` | H.1 | 200, liste valide, <3s |
| GET `/api/catalogue-pac` | H.2 | 200, catalogue valide, <3s |
| GET `/api/baremes` | H.3 | 200, grille valide, <3s |
| POST `/api/leads` | H.4 | 200, `ok:true`, création minimale |
| POST `/api/catalogue-pac` | H.5 | 200, `ok:true` |
| POST `/prospect/PR-000001/commentaire-ajax` | H.6 | 200, `ok:true` |
| GET `/prospect/PR-000001/commentaires-json` | H.7 | 200, tableau commentaires |
| Routes principales | H.8 | toutes <3s |

### Captures d'écran de tous les tests FAIL

- `tests/screenshots/A_4.png` — A.4 Aucune erreur JS console
- `tests/screenshots/A_9.png` — A.9 Convention de casse nom/prénom
- `tests/screenshots/C_1.png` — C.1 Bandeau identité PR-000001
- `tests/screenshots/C_3.png` — C.3 Adresse/CP/ville prospect
- `tests/screenshots/C_4.png` — C.4 Surface/type/chauffage prospect
- `tests/screenshots/C_14.png` — C.14 Retour visible non sticky
- `tests/screenshots/C_15.png` — C.15 Retour accueil
- `tests/screenshots/D_2.png` — D.2 Champs nouveau vides/neutres
- `tests/screenshots/D_3.png` — D.3 Aucune valeur hardcodée nouveau
- `tests/screenshots/D_9.png` — D.9 data/leads.json contient TESTAUDIT
- `tests/screenshots/E_2.png` — E.2 Surface chauffée = 0.9 habitable
- `tests/screenshots/E_5.png` — E.5 Isolation recalcule puissance
- `tests/screenshots/E_7.png` — E.7 Triphasé => TRI uniquement
- `tests/screenshots/E_12.png` — E.12 Bouton envoyer pré-devis
- `tests/screenshots/F_5.png` — F.5 Recharger admin prix modifié
- `tests/screenshots/F_6.png` — F.6 Persistance cross-session admin
- `tests/screenshots/G_3.png` — G.3 Upload Excel succès
- `tests/screenshots/G_5.png` — G.5 Notes importées dans notes.json
- `tests/screenshots/I_1.png` — I.1 Créer prospect et ouvrir cohérent
- `tests/screenshots/I_3.png` — I.3 Ajouter note dans notes.json

### Logs Playwright complets

- Logs complets : `tests/playwright_logs.txt`
- Résultats structurés : `tests/playwright_results.jsonl`

### Commandes de reproduction

```bash
source .venv/bin/activate
pytest tests/test_audit_maxi.py --browser chromium --tb=short -q
```

### Conclusion opérationnelle

Le socle FastAPI répond et les API minimales fonctionnent, mais la surface utilisateur contient encore trop de données de démonstration et de fonctionnalités partielles pour être vendue sans corrections ciblées.
