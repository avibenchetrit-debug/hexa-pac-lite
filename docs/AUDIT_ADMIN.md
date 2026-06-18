# AUDIT ADMIN — hexa-pac-lite
## Date : 2026-06-18
## Commit analysé : ec058a2593b9171815d34234e7050ba1015cfe5e

## 1. Vue d'ensemble

La page Admin est essentiellement implémentée dans `templates/index.html`, dans le module JavaScript `HEXA — Panneau ADMIN (backend de pilotage)` exposé via `window.HexaAdmin`.
Elle pilote le catalogue PAC, les paramètres de marge Option 1 / Option 2, les nouveaux blocs MPR/CEE/bonification et les modèles d'emails.
Les modèles PAC sont persistés côté serveur dans `data/catalogue_pac.json` via `/api/catalogue-pac`, mais une copie locale existe aussi dans `localStorage["hexa_config_v1"]`.
Les paramètres généraux de marge (`pose`, `acc`, `tva`, prix lead, conversion, visites, COFRAC, urbanisme, cession, plafond) sont actuellement sauvegardés uniquement dans `localStorage["hexa_config_v1"].params`.
Les forfaits MPR, bonification CEE, délégataires et modèles email sont sauvegardés via `/api/admin/m3` dans `data/baremes.json`, `data/delegataires.json`, `data/modeles_email.json`.

## 2. Inventaire des champs par section

> Abréviations : LS = `localStorage["hexa_config_v1"]`, PAC = `data/catalogue_pac.json`.

### Section CONFIGURATION GÉNÉRALE

| Champ affiché | ID HTML / clé | Type | Défaut actuel | Unité | Section | Stockage |
|---|---|---:|---:|---|---|---|
| URL du script d'appel (Notion) | `#adm-script-url` / `script_notion_url` | input text | `""` | URL | Configuration générale | `data/baremes.json → script_notion_url` via `/api/admin/config` |
| Sauvegarder l'URL | `#adm-save-script-url` | button | n/a | n/a | Configuration générale | Déclenche `POST /api/admin/config` |

### Section RÉGLAGES GÉNÉRAUX

| Champ affiché | ID HTML / clé | Type | Défaut actuel | Unité | Section | Stockage |
|---|---|---:|---:|---|---|---|
| Pose HT | `.adm-p[data-p="pose"]` | input text/numeric | `3500` | € HT | Réglages généraux | `LS.params.pose` |
| Accessoires HT | `.adm-p[data-p="acc"]` | input text/numeric | `550` | € HT | Réglages généraux | `LS.params.acc` |
| TVA | `.adm-p[data-p="tva"]` | input text/decimal | `5.5` | % | Réglages généraux | `LS.params.tva` sous forme décimale `0.055` |

### Section OPTION 1 — J'ACHÈTE MES LEADS

| Champ affiché | ID HTML / clé | Type | Défaut actuel | Unité | Section | Stockage |
|---|---|---:|---:|---|---|---|
| Prix lead HT | `.adm-p[data-p="lead"]` | input text/numeric | `30` | € HT | Option 1 | `LS.params.lead` |
| Taux conversion | `.adm-p[data-p="conv"]` | input text/decimal | `5.0` | % | Option 1 | `LS.params.conv` sous forme décimale `0.05` |
| CAC | `#adm-cac` | calcul affiché | `lead / conv = 600` | € | Option 1 | Non stocké ; calculé par `cac(p)` |
| Visite technique | `.adm-p[data-p="vt1"]` | input text/numeric | `200` | € | Option 1 | `LS.params.vt1` |
| COFRAC | `.adm-p[data-p="cofrac1"]` | input text/numeric | `226` | € | Option 1 | `LS.params.cofrac1` |
| Urbanisme | `.adm-p[data-p="urba1"]` | input text/numeric | `100` | € | Option 1 | `LS.params.urba1` |

### Section OPTION 2 — RÉGIE (PRIX DE CESSION)

| Champ affiché | ID HTML / clé | Type | Défaut actuel | Unité | Section | Stockage |
|---|---|---:|---:|---|---|---|
| Visite technique | `.adm-p[data-p="vt2"]` | input text/numeric | `200` | € | Option 2 | `LS.params.vt2` |
| COFRAC | `.adm-p[data-p="cofrac2"]` | input text/numeric | `226` | € | Option 2 | `LS.params.cofrac2` |
| Urbanisme | `.adm-p[data-p="urba2"]` | input text/numeric | `100` | € | Option 2 | `LS.params.urba2` |
| Marge de cession à ajouter : en € | `.adm-seg-btn[data-cession="eur"]` | segmented button | actif | mode | Option 2 | `LS.params.cession_mode = "eur"` |
| Marge de cession à ajouter : en % | `.adm-seg-btn[data-cession="pct"]` | segmented button | inactif | mode | Option 2 | `LS.params.cession_mode = "pct"` |
| Marge cession (€) | `#adm-cession-eur .adm-p[data-p="cession_eur"]` | input text/numeric | `2500` | € | Option 2 | `LS.params.cession_eur` |
| Marge cession (%) | `#adm-cession-pct .adm-p[data-p="cession_pct"]` | input text/decimal | `20.0` | % du prix catalogue HT | Option 2 | `LS.params.cession_pct` sous forme décimale `0.20` |
| Plafond de vente régie | `.adm-p[data-p="plafond_pct"]` | input text/decimal | `60` | % au-dessus du catalogue TTC | Option 2 | `LS.params.plafond_pct` sous forme décimale `0.60` |

### Section MODÈLES & MARGES NETTES

| Champ affiché | ID HTML / clé | Type | Défaut actuel | Unité | Section | Stockage |
|---|---|---:|---:|---|---|---|
| Modèle | `m.ref`, `m.nom` | texte affiché | catalogue | n/a | Modèles & marges nettes | `data/catalogue_pac.json[].ref`, `[].nom` |
| Supprimer modèle | `.adm-del[data-i]` | button | n/a | n/a | Modèles & marges nettes | Supprime l'entrée `LS.models[i]`, puis sauvegarde possible vers `data/catalogue_pac.json` |
| Prix vente TTC | `.adm-in[data-f="ttc"]` | input text/numeric | catalogue | € TTC | Modèles & marges nettes | `data/catalogue_pac.json[].ttc` via `/api/catalogue-pac` après clic Enregistrer |
| Prix vente HT | colonne calculée | calcul | `ttc/(1+tva)` | € HT | Modèles & marges nettes | Non stocké |
| Achat HT | `.adm-in[data-f="achat"]` | input text/numeric | catalogue | € HT | Modèles & marges nettes | `data/catalogue_pac.json[].achat` via `/api/catalogue-pac` après clic Enregistrer |
| Pose + access. | colonne calculée | calcul | `pose + acc` | € HT | Modèles & marges nettes | Non stocké |
| Coût de revient | colonne calculée | calcul | `achat + pose + acc` | € HT | Modèles & marges nettes | Non stocké |
| Marge brute | colonne calculée | calcul | `prix HT - coût` | € + % | Modèles & marges nettes | Non stocké |
| Marge nette Hexa Option 1 | colonne calculée | calcul | `brute - CAC - vt1 - cofrac1 - urba1` | € + % | Modèles & marges nettes | Non stocké |
| Prix de cession | `.adm-in.adm-cess-in[data-f="cession_forcee"]` | input text/numeric | calculé | € HT | Modèles & marges nettes | `data/catalogue_pac.json[].cession_forcee` si forcé |
| Reset prix de cession | `.adm-cess-reset[data-i]` | button | caché sauf prix forcé | n/a | Modèles & marges nettes | Supprime `cession_forcee` du modèle en mémoire |
| Marge nette Hexa Option 2 | colonne calculée | calcul | `cession - baseCession` | € + % | Modèles & marges nettes | Non stocké |
| Commission régie | colonne calculée | calcul | `max(0, prix HT - cession)` | € | Modèles & marges nettes | Non stocké |
| Simuler ▾ | `.adm-sim-btn[data-sim]` | button | n/a | n/a | Modèles & marges nettes | Ouvre une ligne de simulation non stockée sauf paramètres de surplus |
| Point d'équilibre ⚖ | `.adm-eq-btn[data-eq]` | button | n/a | n/a | Modèles & marges nettes | Affiche un calcul non stocké |

### Section AJOUTER UNE POMPE À CHALEUR

| Champ affiché | ID HTML / clé | Type | Défaut actuel | Unité | Section | Stockage |
|---|---|---:|---:|---|---|---|
| Référence interne | `#af-ref` | input text | vide | n/a | Formulaire ajout PAC | Nouveau modèle `ref` dans `LS.models`, puis `data/catalogue_pac.json` après sauvegarde |
| Nom commercial | `#af-nom` | input text | vide | n/a | Formulaire ajout PAC | Nouveau modèle `nom` |
| Puissance kW (35°C) | `#af-puiss` | input decimal | vide | kW | Formulaire ajout PAC | Nouveau modèle `puiss35` |
| Alimentation | `#af-alim` | select | `mono` | mono/tri | Formulaire ajout PAC | Nouveau modèle `alim`; ajoute `TRI` au `ref` si besoin |
| Usage | `#af-usage` | select | `chauffage` | usage | Formulaire ajout PAC | Nouveau modèle `usage` |
| Prix achat HT | `#af-achat` | input numeric | vide | € HT | Formulaire ajout PAC | Nouveau modèle `achat` |
| Prix vente TTC | `#af-ttc` | input numeric | vide | € TTC | Formulaire ajout PAC | Nouveau modèle `ttc` |
| Ajouter au catalogue | `#af-add` | button | n/a | n/a | Formulaire ajout PAC | Ajoute dans `LS.models` |
| Annuler | `#af-cancel` | button | n/a | n/a | Formulaire ajout PAC | Ferme le formulaire |

### Section FORFAITS MPR MONO-GESTE

| Champ affiché | ID HTML / clé | Type | Défaut actuel | Unité | Section | Stockage |
|---|---|---:|---:|---|---|---|
| TMO (Très modeste) | `.adm-m3-mpr[data-cat="tres_modeste"]` | input text/numeric | `5000` | € | Forfaits MPR Mono-Geste | `data/baremes.json → forfaits_mpr.tres_modeste` |
| MO (Modeste) | `.adm-m3-mpr[data-cat="modeste"]` | input text/numeric | `4000` | € | Forfaits MPR Mono-Geste | `data/baremes.json → forfaits_mpr.modeste` |
| INT (Intermédiaire) | `.adm-m3-mpr[data-cat="intermediaire"]` | input text/numeric | `3000` | € | Forfaits MPR Mono-Geste | `data/baremes.json → forfaits_mpr.intermediaire` |
| SUP (Supérieur) | `.adm-m3-mpr[data-cat="superieur"]` | input text/numeric | `0` | € | Forfaits MPR Mono-Geste | `data/baremes.json → forfaits_mpr.superieur` |

### Section DÉLÉGATAIRES CEE

| Champ affiché | ID HTML / clé | Type | Défaut actuel | Unité | Section | Stockage |
|---|---|---:|---:|---|---|---|
| Actif | `.adm-del-actif` | radio | `PICOTY` actif | bool | Délégataires CEE | `data/delegataires.json[].actif` |
| Nom | `.adm-del-nom` | input text | `PICOTY` | n/a | Délégataires CEE | `data/delegataires.json[].nom` |
| MWh précaire (€) | `.adm-del-precaire` | input decimal | `12.5` | €/MWh | Délégataires CEE | `data/delegataires.json[].mwh_precaire` |
| MWh classique (€) | `.adm-del-classique` | input decimal | `7.2` | €/MWh | Délégataires CEE | `data/delegataires.json[].mwh_classique` |
| Supprimer | `.adm-del-remove` | button | n/a | n/a | Délégataires CEE | Supprime une ligne en mémoire puis sauvegarde |
| Ajouter délégataire | `#adm-add-delegataire` | button | n/a | n/a | Délégataires CEE | Ajoute une ligne en mémoire puis sauvegarde possible |

### Section BONIFICATION CEE (COUP DE POUCE)

| Champ affiché | ID HTML / clé | Type | Défaut actuel | Unité | Section | Stockage |
|---|---|---:|---:|---|---|---|
| Coup de pouce actif | `#adm-bonif-actif` | checkbox | `true` | bool | Bonification CEE | `data/baremes.json → bonification_cee.actif` |
| Multiplicateur | `#adm-bonif-mult` | input number | `5` | multiplicateur | Bonification CEE | `data/baremes.json → bonification_cee.multiplicateur` |

### Section MODÈLES D'EMAILS

| Champ affiché | ID HTML / clé | Type | Défaut actuel | Unité | Section | Stockage |
|---|---|---:|---:|---|---|---|
| Modèle 1 : Titre court | `[data-email-i="0"] .adm-email-titre` | input text | `Premier contact` | n/a | Modèles d'emails | `data/modeles_email.json[0].titre` |
| Modèle 1 : Sujet | `[data-email-i="0"] .adm-email-sujet` | input text | `Votre projet de pompe à chaleur Hexa Rénov'` | n/a | Modèles d'emails | `data/modeles_email.json[0].sujet` |
| Modèle 1 : Contenu | `[data-email-i="0"] .adm-email-contenu` | textarea | texte premier contact | n/a | Modèles d'emails | `data/modeles_email.json[0].contenu` |
| Modèle 2 : Titre court | `[data-email-i="1"] .adm-email-titre` | input text | `Relance après pré-visite` | n/a | Modèles d'emails | `data/modeles_email.json[1].titre` |
| Modèle 2 : Sujet | `[data-email-i="1"] .adm-email-sujet` | input text | `Suite à notre pré-visite Hexa Rénov'` | n/a | Modèles d'emails | `data/modeles_email.json[1].sujet` |
| Modèle 2 : Contenu | `[data-email-i="1"] .adm-email-contenu` | textarea | texte relance pré-visite | n/a | Modèles d'emails | `data/modeles_email.json[1].contenu` |
| Modèle 3 : Titre court | `[data-email-i="2"] .adm-email-titre` | input text | `Relance après devis` | n/a | Modèles d'emails | `data/modeles_email.json[2].titre` |
| Modèle 3 : Sujet | `[data-email-i="2"] .adm-email-sujet` | input text | `Votre devis Hexa Rénov'` | n/a | Modèles d'emails | `data/modeles_email.json[2].sujet` |
| Modèle 3 : Contenu | `[data-email-i="2"] .adm-email-contenu` | textarea | texte relance devis | n/a | Modèles d'emails | `data/modeles_email.json[2].contenu` |
| Enregistrer MPR/CEE/Emails | `#adm-save-m3` | button | n/a | n/a | MPR/CEE/Emails | Déclenche `POST /api/admin/m3` |

### Section CORBEILLE

| Champ affiché | ID HTML / clé | Type | Défaut actuel | Unité | Section | Stockage |
|---|---|---:|---:|---|---|---|
| Tout sélectionner | `#adm-trash-master` | checkbox | décoché | bool | Corbeille | Non stocké |
| Restaurer la sélection (X) | `#adm-trash-restore-selected` | button | caché si 0 | n/a | Corbeille | Appelle `POST /api/leads/{numero}/restore` |
| Supprimer définitivement la sélection (X) | `#adm-trash-purge-selected` | button | caché si 0 | n/a | Corbeille | Appelle `DELETE /api/leads/{numero}/purge` |
| Checkbox ligne | `.adm-trash-check[data-numero]` | checkbox | décoché | bool | Corbeille | Non stocké |
| Restaurer ligne | `.adm-trash-restore` | button | n/a | n/a | Corbeille | Appelle `POST /api/leads/{numero}/restore` |
| Supprimer définitivement ligne | `.adm-trash-purge` | button | n/a | n/a | Corbeille | Appelle `DELETE /api/leads/{numero}/purge` |

### Section ACCÈS ADMIN

| Champ affiché | ID HTML / clé | Type | Défaut actuel | Unité | Section | Stockage |
|---|---|---:|---:|---|---|---|
| Mot de passe Admin | `#admin-auth-password` | input password | vide | n/a | Modale Accès Admin | Comparé à `ADMIN_PASSWORD`, défaut `hexarenov2026` |
| Déverrouiller | `[data-act="unlock"]` | button | n/a | n/a | Modale Accès Admin | Stocke `localStorage["hexa_admin_unlocked"]` |
| Annuler | `[data-act="cancel"]` | button | n/a | n/a | Modale Accès Admin | Ferme la modale |
| Verrouiller Admin | `#adm-lock` | button | n/a | n/a | Header Admin | Supprime `localStorage["hexa_admin_unlocked"]` |

## 3. Cartographie des dépendances

### Schéma des liens entre champs

| Champ / groupe | Lecture : où utilisé | Écriture : où modifié | Dépendances |
|---|---|---|---|
| `pose`, `acc`, `tva` | `templates/index.html → calcModel(m,p)`, `recalc()`, tableau Admin | `.adm-p` listener dans `bind()` ; `saveConfig()` localStorage | `pose+acc`, coût de revient, HT, marge brute, marges nettes, commission régie |
| `lead`, `conv` | `cac(p)` puis `calcModel()` | `.adm-p[data-p]` listener | CAC, marge nette Option 1, point d'équilibre |
| `vt1`, `cofrac1`, `urba1` | `calcModel()` Option 1 | `.adm-p[data-p]` listener | Marge nette Option 1, CAC équilibre |
| `vt2`, `cofrac2`, `urba2` | `calcModel()` Option 2 | `.adm-p[data-p]` listener | Base cession, prix de cession, marge cession |
| `cession_mode`, `cession_eur`, `cession_pct` | `calcModel()` pour `margeCessionDefaut` | segmented control + `.adm-p` listener | Prix de cession calculé, marge nette Option 2, commission régie |
| `plafond_pct` | `calcModel()` et `renderSim()` | `.adm-p[data-p="plafond_pct"]` | Slider de simulation régie, plafond TTC/HT |
| `ttc` modèle | `calcModel()`, simulateur via `CATALOGUE_PAC`, PDF devis via `_devis_context()` | `.adm-in[data-f="ttc"]`, puis `POST /api/catalogue-pac` | Prix HT, marge brute, prix devis, sélection PAC |
| `achat` modèle | `calcModel()` | `.adm-in[data-f="achat"]`, puis `POST /api/catalogue-pac` | Coût de revient, marges |
| `cession_forcee` modèle | `calcModel()` | `.adm-cess-in`, `.adm-cess-reset`, puis `POST /api/catalogue-pac` | Prix de cession au lieu de calcul global |
| Ajout PAC `af-*` | Après ajout, modèle intégré à `LS.models` puis aux calculs | `openAddForm()` → bouton `#af-add` | Toutes les lignes Admin et simulateur après sauvegarde catalogue |
| `forfaits_mpr` | Simulateur `calcul()` via `/api/admin/m3`; PDF `_devis_context()` | `POST /api/admin/m3` | MPR devis, reste à charge |
| `delegataires` | Simulateur `calcul()` via `/api/admin/m3`; PDF `_devis_context()` | `POST /api/admin/m3` | CEE devis, reste à charge |
| `bonification_cee` | Simulateur `calcul()` via `/api/admin/m3`; PDF `_devis_context()` | `POST /api/admin/m3` | Multiplication de la prime CEE |
| `modeles_email` | Panneau Échanges `loadEmailTemplates()` puis `ouvrirModeleEmail()` | `POST /api/admin/m3` | Boutons modèle email dans CTA E |
| `script_notion_url` | Header bouton `#btn-script-appel` via `/api/admin/config` | `POST /api/admin/config` | Active/désactive l'ouverture Notion |
| Corbeille | `GET /api/leads/trash` | `POST /restore`, `DELETE /purge` | Rafraîchit corbeille et tableau Accueil |

### Endpoints d'écriture

- `POST /api/catalogue-pac` : sauvegarde le catalogue PAC complet (`data/catalogue_pac.json`).
- `POST /api/admin/m3` : sauvegarde `forfaits_mpr`, `bonification_cee`, `delegataires`, `modeles_email`.
- `POST /api/admin/config` : sauvegarde `script_notion_url` dans `data/baremes.json`.
- `POST /api/admin/auth` : ne sauvegarde pas de fichier ; renvoie un token stocké dans `localStorage`.
- `POST /api/leads/{numero}/restore` et `DELETE /api/leads/{numero}/purge` : actions de corbeille.

## 4. Catégorisation fonctionnelle

### Coûts internes

- Achat HT modèle PAC (`catalogue_pac[].achat`)
- Pose HT (`LS.params.pose`)
- Accessoires HT (`LS.params.acc`)
- Visite technique Option 1 (`vt1`)
- COFRAC Option 1 (`cofrac1`)
- Urbanisme Option 1 (`urba1`)
- Visite technique Option 2 (`vt2`)
- COFRAC Option 2 (`cofrac2`)
- Urbanisme Option 2 (`urba2`)

### Prix de vente

- Prix vente TTC modèle PAC (`catalogue_pac[].ttc`)
- TVA (`LS.params.tva`) : sert à convertir le prix vente TTC en HT pour la marge
- Plafond de vente régie (`plafond_pct`) : limite commerciale de prix de revente régie

### Calcul / intermédiaire

- Prix vente HT
- Pose + accessoires
- Coût de revient
- Marge brute
- CAC
- Marge nette Option 1
- Base cession
- Prix de cession calculé
- Marge nette Option 2
- Commission régie
- CAC d'équilibre
- Taux de conversion d'équilibre
- Simulations de surplus au-dessus catalogue

### Configuration

- URL du script d'appel Notion (`script_notion_url`)
- Modèles d'emails (`modeles_email`)
- Mot de passe Admin (`ADMIN_PASSWORD`)
- Mode de cession (`cession_mode`)
- Taux conversion (`conv`) : configuration commerciale utilisée en calcul

### Aides

- Forfaits MPR par catégorie (`forfaits_mpr`)
- Délégataires CEE (`delegataires`)
- Bonification CEE (`bonification_cee.actif`, `multiplicateur`)
- Ancienne grille CEE/MPR par ETAS/surface/zone/catégorie dans `data/baremes.json`

### Commercial

- Prix lead Option 1 (`lead`)
- Marge de cession globale Option 2 (`cession_eur` ou `cession_pct`)
- Prix de cession forcé par modèle (`cession_forcee`)
- Plafond de vente régie (`plafond_pct`)

## 5. Cartographie des calculs

### Tableau Modèles & Marges Nettes

#### Colonne Prix vente HT

- Formule : `ht = ttc / (1 + tva)`
- Entrées : Prix vente TTC modèle (`ttc`), TVA (`p.tva`)
- Affichage : montant `eur(r.ht)`

#### Colonne Pose + access.

- Formule : `pose = p.pose + p.acc`
- Entrées : Pose HT, Accessoires HT
- Affichage : montant `eur(r.pose)`

#### Colonne Coût de revient

- Formule : `cout = achat + pose + acc`
- Entrées : Achat HT modèle, Pose HT, Accessoires HT
- Affichage : montant `eur(r.cout)`

#### Colonne Marge brute

- Formule : `brute = ht - cout`
- Entrées : Prix vente HT, Coût de revient
- Affichage : montant `eur(r.brute)` + pourcentage `brute / ht`

#### Colonne Marge nette Hexa Option 1

- Formule : `net1 = brute - (CAC + vt1 + cofrac1 + urba1)`
- Formule CAC : `CAC = lead / conv`
- Entrées : Marge brute, prix lead, taux conversion, visite technique Option 1, COFRAC Option 1, urbanisme Option 1
- Affichage : montant `eur(r.net1)` + pourcentage `net1 / ht`
- Tooltip : détail `Marge brute - CAC - Visite - COFRAC - Urbanisme = net1`

#### Colonne Prix de cession

- Base : `baseCession = cout + vt2 + cofrac2 + urba2`
- Marge globale :
  - si `cession_mode === "pct"` : `margeCessionDefaut = ht * cession_pct`
  - sinon : `margeCessionDefaut = cession_eur`
- Prix de cession :
  - si `cession_forcee` modèle défini : `cession = cession_forcee`
  - sinon : `cession = baseCession + margeCessionDefaut`
- Entrées : coût de revient, visite technique Option 2, COFRAC Option 2, urbanisme Option 2, marge cession €, marge cession %, prix forcé
- Affichage : input modifiable en €

#### Colonne Marge nette Hexa Option 2

- Formule : `margeCession = cession - baseCession`
- Formule affichée : `net2 = margeCession`
- Entrées : Prix de cession, base cession
- Affichage : montant `eur(r.net2)` + pourcentage `net2 / ht`

#### Colonne Commission régie

- Formule : `commissionRegie = max(0, ht - cession)`
- Entrées : Prix vente HT, prix de cession
- Affichage : montant `eur(r.commissionRegie)` avec mention `au catalogue`

#### Point d'équilibre Option 1 vs Option 2

- `fixes1 = vt1 + cofrac1 + urba1`
- `cacEquilibre = brute - fixes1 - net2`
- `convEquilibre = lead / cacEquilibre` si `cacEquilibre > 0`
- Entrées : brute, vt1, cofrac1, urba1, net2, lead
- Affichage : encart déplié avec CAC d'équilibre, taux conversion d'équilibre, verdict

#### Simulation régie au-dessus catalogue

- `plafondTTC = ttc * (1 + plafond_pct)`
- `plafondHT = plafondTTC / (1 + tva)`
- `venteHT` borné entre `ht` et `plafondHT`
- `surplus = max(0, venteHT - ht)`
- Mode fixe : `hexa = net2`, `regie = (ht - cession) + surplus`
- Mode partage : `hexa = net2 + surplus * surplusPct`, `regie = (ht - cession) + surplus * (1 - surplusPct)`
- Entrées : prix catalogue, TVA, plafond, prix cession, mode surplus, part surplus
- Affichage : prix de vente TTC/HT, marge Hexa, gain régie

## 6. Cas particuliers et ambiguïtés

1. **Pose HT 3500€** : c'est un coût interne dans `calcModel()` (`cout = achat + pose + acc`), pas un prix facturé directement au client. Le nom peut prêter à confusion car il pourrait ressembler à une ligne de devis.
2. **Accessoires HT 550€** : même logique que Pose HT ; c'est un coût interne intégré au coût de revient.
3. **TVA 5,5%** : elle convertit le prix vente TTC catalogue en prix vente HT (`ht = ttc/(1+tva)`). Elle s'applique donc au prix de vente, mais sert ensuite au calcul de marge.
4. **Paramètre `marge` dans `DEFAULT.params`** : valeur `0.455` présente mais non utilisée dans `calcModel()` ni dans le rendu Admin actuel.
5. **`data/parametres_admin.json` absent** : les paramètres généraux Admin ne sont pas stockés dans un fichier JSON serveur ; ils vivent dans `localStorage["hexa_config_v1"]`.
6. **Duplications localStorage / serveur** : modèles PAC existent dans `data/catalogue_pac.json` et peuvent aussi exister dans `localStorage["hexa_config_v1"].models`.
7. **MPR/CEE ancien vs nouveau** : `data/baremes.json` contient déjà une grille historique `etas_111_139` / `etas_140_plus`, et reçoit aussi les nouvelles clés `forfaits_mpr` / `bonification_cee`.
8. **Délégataires CEE** : stockés dans `data/delegataires.json`, séparés de `data/baremes.json`, alors que les aides MPR/bonification sont dans `baremes.json`.
9. **Modèles email** : ils sont une configuration Admin, mais l'envoi effectif passe par une route SMTP existante, hors logique d'Admin elle-même.
10. **Prix de cession forcé** : l'input affiche toujours la cession calculée, mais ne devient réellement stockée que si l'utilisateur saisit une valeur dans `cession_forcee`.
11. **Suppression modèle PAC** : la suppression se fait en mémoire, puis nécessite le bouton Enregistrer pour persister vers `data/catalogue_pac.json`.

## 7. Schéma des fichiers JSON

### `data/parametres_admin.json`

Statut : **absent**.

Structure attendue si on voulait centraliser les paramètres généraux :

```jsonc
{
  "params": {
    "pose": 3500,
    "acc": 550,
    "tva": 0.055,
    "lead": 30,
    "conv": 0.05,
    "vt1": 200,
    "cofrac1": 226,
    "urba1": 100,
    "vt2": 200,
    "cofrac2": 226,
    "urba2": 100,
    "cession_mode": "eur",
    "cession_eur": 2500,
    "cession_pct": 0.20,
    "plafond_pct": 0.60
  }
}
```

Aujourd'hui ces valeurs sont hardcodées dans `templates/index.html → DEFAULT.params` et sauvegardées dans `localStorage["hexa_config_v1"].params`.

### `data/catalogue_pac.json`

Structure actuelle :

```jsonc
[
  {
    "ref": "ATL-EXCELLIA-S-DUO-9",
    "nom": "ALFÉA EXCELLIA S DUO 9",
    "usage": "Chauffage + ECS",
    "alim": "Monophasé",
    "puiss35": 10.08,
    "puiss_chauf": 10.08,
    "etas35": 183,
    "scop35": 4.66,
    "cop": 4.66,
    "classe": "A+++",
    "fluide": "R32",
    "ballon": 190,
    "db_ext": 56,
    "achat": 5367.95,
    "ttc": 14990
    // "cession_forcee": optionnel, ajouté par Admin si prix forcé
    // "surplus_mode": optionnel, "fixe" ou "partage"
    // "surplus_pct": optionnel, part Hexa du surplus
  }
]
```

Clés actuellement présentes : `ref`, `nom`, `usage`, `alim`, `puiss35`, `puiss_chauf`, `etas35`, `scop35`, `cop`, `classe`, `fluide`, `ballon`, `db_ext`, `achat`, `ttc`.

Clés attendues mais optionnelles/hardcodées : `cession_forcee`, `surplus_mode`, `surplus_pct`, `etas`.

### `data/baremes_anah_2026.json`

Statut : **absent**.

Les forfaits MPR sont actuellement attendus dans `data/baremes.json → forfaits_mpr`.

Structure attendue logique :

```jsonc
{
  "forfaits_mpr": {
    "tres_modeste": 5000,
    "modeste": 4000,
    "intermediaire": 3000,
    "superieur": 0
  }
}
```

### `data/baremes.json`

Structure actuelle hybride :

```jsonc
{
  "etas_111_139": {
    "<70": {
      "cee_devis": {
        "H1": { "superieur": 1963, "intermediaire": 1963, "modeste": 1963, "tres_modeste": 3136 }
      },
      "cee_conserve": {},
      "mpr_devis": {}
    },
    "70-90": {},
    ">=90": {}
  },
  "etas_140_plus": {
    "<70": {},
    "70-90": {},
    ">=90": {}
  },

  // Nouvelles clés Admin M3, absentes du fichier repo initial mais attendues :
  "forfaits_mpr": {
    "tres_modeste": 5000,
    "modeste": 4000,
    "intermediaire": 3000,
    "superieur": 0
  },
  "bonification_cee": {
    "actif": true,
    "multiplicateur": 5
  },
  "script_notion_url": ""
}
```

Clés actuellement présentes dans le fichier repo : `etas_111_139`, `etas_140_plus`.
Clés attendues mais absentes tant que non sauvegardées par Admin : `forfaits_mpr`, `bonification_cee`, `script_notion_url`.

### `data/delegataires.json`

Structure actuelle :

```jsonc
[
  {
    "nom": "PICOTY",
    "mwh_precaire": 12.5,
    "mwh_classique": 7.2,
    "actif": true
  }
]
```

Règle métier : un seul délégataire actif à la fois côté UI Admin.

### `data/modeles_email.json`

Structure actuelle :

```jsonc
[
  {
    "id": "modele_1",
    "label": "Premier contact",
    "titre": "Premier contact",
    "sujet": "Votre projet de pompe à chaleur Hexa Rénov'",
    "contenu": "Bonjour {prenom}..."
  },
  {
    "id": "modele_2",
    "label": "Relance après pré-visite",
    "titre": "Relance après pré-visite",
    "sujet": "Suite à notre pré-visite Hexa Rénov'",
    "contenu": "Bonjour {prenom}..."
  },
  {
    "id": "modele_3",
    "label": "Relance après devis",
    "titre": "Relance après devis",
    "sujet": "Votre devis Hexa Rénov'",
    "contenu": "Bonjour {prenom}..."
  }
]
```

Variables supportées dans le contenu : `{prenom}`, `{nom}`, `{numero}`, `{modele_pac}`, `{reste_a_charge}`.

### `data/devis/devis_meta.json`

Structure attendue à l'exécution :

```jsonc
{
  "PR-000001": [
    {
      "version": 1,
      "sent_at": "2026-06-16T12:56:51",
      "email": "client@example.com",
      "file": "/data/devis/PR-000001_v1.pdf"
    }
  ]
}
```

Le dossier `DATA_DIR/devis` est créé au startup par `_init_storage()`.

### Autres JSON pertinents

- `data/leads.json` : prospects, y compris `statut`, `date_envoi_devis`, `categorie`, `surface_logement_m2`, etc.
- `data/notes.json` : notes par prospect, utilisé pour les logs automatiques devis/email.
- `data/echanges.json` : échanges par prospect, utilisé par le panneau Échanges.

## 8. Recommandations

1. Créer un vrai `data/parametres_admin.json` pour sortir les paramètres généraux Admin de `localStorage` et les rendre persistants Railway.
2. Séparer clairement les coûts internes (`achat`, `pose`, `acc`, frais Option 1/2) des prix de vente (`ttc`, TVA, plafond régie) dans l'interface.
3. Renommer `Pose HT` et `Accessoires HT` en `Coût pose HT` / `Coût accessoires HT` pour éviter toute confusion avec une ligne facturée client.
4. Regrouper toutes les aides dans un schéma unique : `forfaits_mpr`, délégataire actif, bonification CEE, ancienne grille ETAS.
5. Décider si l'ancienne grille `etas_111_139` / `etas_140_plus` reste source de vérité ou devient un fallback.
6. Éviter la double source catalogue `localStorage` + `data/catalogue_pac.json` : privilégier le serveur comme source de vérité.
7. Documenter le cycle de sauvegarde : modifications modèle en mémoire → bouton Enregistrer → `POST /api/catalogue-pac`.
8. Ajouter une indication UI explicite que `TVA` sert à convertir le TTC client en HT marge.
9. Déplacer les paramètres de modèles email vers une section dédiée moins proche des marges PAC, car ils relèvent de la configuration CRM.
10. Ajouter une validation côté backend pour garantir un seul délégataire actif même si le payload vient d'un client externe.
