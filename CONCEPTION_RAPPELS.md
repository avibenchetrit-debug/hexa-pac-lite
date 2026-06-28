# Conception — Système « Aucun lead ne m'échappe »

> État : **conception validée, avant spec d'implémentation de l'étape 1.**
> Dernière mise à jour : 2026-06-28. Aucun code applicatif écrit à ce stade.
> Ce fichier sert de reprise en session fraîche.

## 1. Vision

Une liste **« À traiter aujourd'hui »** sur l'**Accueil** (vue prospects existante) qui regroupe **tout ce qui demande une action sur un lead**, alimentée par 3 sources :

- **A. RDV** (date + **heure**, type `tel`/`visite`) → statut auto « RDV pris » → **notif 30 min avant si CRM ouvert** (bandeau + son léger), sinon affiché en rouge « imminent/dépassé » à la réouverture. Tri par heure.
- **B. Rappels** (date sans heure) :
  - **manuel** : date + assigné (`avi`/`joelle`/`maurice`) + motif,
  - **auto-NRP** : un NRP crée un rappel pour le **lendemain**, assigné à l'utilisateur courant.
  - Tri par **ancienneté** (plus ancien = priorité).
- **C. Détections automatiques** (filet de sécurité, sans rien poser), seuils configurables admin :
  - devis envoyé sans réponse depuis **3 j**,
  - lead jamais contacté depuis **2 j**,
  - simulation faite sans devis envoyé depuis **3 j**.

**Transversal** : assignation `avi/joelle/maurice` + filtre par personne (ou tous) ; liste **vue par tous, stockée serveur** ; **badge topbar** (actions du jour + retards + RDV imminent) ; « marquer fait » → archive dans un log + propose maj statut ; **tri global** = retards en haut, puis RDV du jour par heure, puis rappels par ancienneté, puis détections.

## 2. Décisions validées

- RDV : 1 actif par lead ; pose → statut auto `rdv` ; notif 30 min **uniquement CRM ouvert**.
- Rappels : 1 actif par lead ; manuel ou auto-NRP (lendemain) ; reposer **remplace + archive** l'ancien.
- **Multicanal** : compteurs par canal (appel/sms/email ; whatsapp plus tard).
  - Plafonds avant `injoignable` (configurables admin) : **8 appels, 5 sms, 5 emails**.
  - `injoignable` quand **les 3 plafonds sont atteints** (en tentatives **sans réponse**).
  - **Étape 1 = compteurs d'actions MANUELLES** (boutons cliqués). **Pas d'envoi auto** (= étape 2).
  - L'ancien `NRP max = 4` est **abandonné** (remplacé par les plafonds par canal).
- Détections auto : visibles par **tous**.
- « Marquer fait » : archive dans `actions_log` + **propose** une mise à jour de statut.
- Assignation : `avi/joelle/maurice` (identité **localStorage `hexa_user`, non authentifiée** — déclarative).
- Structure pensée pour l'**étape 2** : séquences de relance **paramétrables depuis l'admin** (ex. « relance devis = J+3 email, J+6 sms, J+9 appel »).

## 3. Audit du système Échanges existant (réutilisé, pas dupliqué)

**Storage** : `echanges.json` = `{ "<numero>": [ entry, ... ] }` (dict par prospect). Lu par `_read_echanges()` (`main.py:438`).

**Structure d'un échange** (`echanges_ajax` `main.py:1787`, `_exchange_for_front` `main.py:977`) :
```
entry = {
  "type": "sms"|"appel"|"email"|"whatsapp",   # CANAL (déjà présent)
  "contenu", "contenu_html", "objet", "template_id",
  "created_at": _now_iso(), "created_by", "auteur",
}
# lecture expose en plus : "nrp": bool(entry.nrp)  (résultat latent, jamais écrit)
```

**Création** : CTA « E » → panneau Échanges (IIFE `index.html:~13207`) → `POST /prospect/{n}/echanges-ajax` `{type, contenu, objet?, template_id?, auteur}`. `contenu` **obligatoire** (400 si vide).

**Endpoints** : `GET /prospect/{n}/echanges-json` (`main.py:1772`), `POST /prospect/{n}/echanges-ajax` (`main.py:1787`).

**`count-echanges`** = **nb total d'entrées** tous canaux (`index.html:7842-7844`).

**NRP** : champ `nrp` présent en lecture mais **jamais posé** comme résultat d'échange. ⚠️ **Correction d'audit (2026-06-28)** : la route `POST /api/leads/{numero}/nrp` **EXISTE DÉJÀ** (`main.py:1540`) et **est utilisée** par le front (`templates/index.html:18034`, payload `{nrp_count, nrp_log}` = **set de compteur absolu**, valeur calculée côté client). Elle n'écrit pas d'échange et ne pose pas de rappel. ⇒ on **ne l'écrase pas** : on la **branche selon la forme du payload** (legacy `{nrp_count}` → comportement actuel inchangé ; nouveau `{par, canal?}` → échange+auto-rappel+injoignable). Voir §10 décision 6.

### Reco : ÉTENDRE Échanges (source unique), pas de `contacts_log` séparé
- Canal déjà là ; résultat à moitié (`nrp`) → schéma déjà prévu pour porter un résultat.
- **Compteurs multicanal dérivés** des échanges (par `type` + `resultat`) → pas de désync.
- Réutilise endpoints + panneau + compteur + storage.
- Étape 2 (séquences) appendra des échanges `origine:"auto"` dans le même historique.

**Enrichissements (rétro-compatibles, optionnels) :**
- `resultat` : `"repondu" | "nrp" | "envoye" | "recu"` (généralise `nrp`).
- `origine` : `"manuel" | "auto"`.
- `sequence_id` / `etape` (réservés étape 2).

**À acter :**
- NRP = échange `{type:"appel", resultat:"nrp", origine:"manuel"}` + auto-rappel lendemain + recalcul injoignable.
- Compteurs « injoignable » = tentatives **sans réponse** par canal (`resultat:"repondu"` ne compte pas).
- Relâcher `contenu` obligatoire pour un NRP sans texte (ou contenu auto « Appel — pas de réponse »).
- `created_at` = `_now_iso()` (pas Paris) → parser défensivement pour « aujourd'hui/ancienneté ».

## 4. Modèle de données

### Contraintes d'écriture (audit)
- `_normalize_lead_payload` (`main.py:499-512`) **stringifie toute valeur** → **interdit** de faire transiter `rdv`/`rappel` (objets) par le save générique `/api/leads`. ⇒ **endpoints dédiés**.
- `_lead_for_response` (`main.py:840`) conserve tous les champs (`dict(lead)`) → la lecture des nouveaux champs est OK.
- `_upsert_lead` (`main.py:527`) fait `merged.update(payload)` **sans whitelist** (stockage OK), mais on **déclare quand même** les champs dans `PROSPECT_FIELDS` + `DEFAULT_PROSPECT_VALUES` (présence garantie + backfill `_migrate_leads_schema` `main.py:872`).

### Champs ajoutés au prospect
| Champ | Type | Contenu |
|---|---|---|
| `rdv` | objet \| null | `{date,heure,type,assigne_a,cree_par,cree_at}` |
| `rappel` | objet \| null | `{date,assigne_a,motif,origine,cree_par,cree_at}` |
| `actions_log` | liste | historique des actions closes |

Réutilisés : `nrp_count`/`nrp_log` (existants), `date_envoi_devis` (`main.py:2571`), `statut`/`statut_updated_at`.
Nouvelles valeurs `statut` : `injoignable` (et `rdv` déjà autorisé `main.py:1526`).

### Structures
```
rdv    = { date:"YYYY-MM-DD", heure:"HH:MM", type:"tel"|"visite",
           assigne_a:"avi", cree_par:"avi", cree_at:"<iso Paris>" }
rappel = { date:"YYYY-MM-DD", assigne_a:"joelle", motif:"…",
           origine:"manuel"|"nrp", cree_par:"avi", cree_at:"<iso Paris>" }
actions_log[] = { type:"rdv"|"rappel"|"detection", snapshot:{…},
                  resultat:"fait"|"injoignable"|"annule",
                  fait_par:"avi", fait_at:"<iso>",
                  subtype:"devis_3j"|… , trigger_at:"<iso>" }   # détections : mémoire de rejet
```

### Formats de dates (fuseau Paris)
- Jour : `YYYY-MM-DD` ; heure : `HH:MM` (24 h) ; horodatages : ISO Paris via `_now_paris_iso()` (`main.py:567`, `PARIS_TZ` `main.py:212`).
- « Aujourd'hui » = `datetime.now(PARIS_TZ).date()` ; datetime RDV = `date`+`heure` en `PARIS_TZ`.

## 5. Endpoints

| Endpoint | Effet |
|---|---|
| `POST /api/leads/{n}/rdv` `{date,heure,type,assigne_a,par}` | écrit `lead.rdv`, statut auto → `rdv` |
| `POST /api/leads/{n}/rappel` `{date,assigne_a,motif,par}` | écrit `lead.rappel` (origine `manuel`) |
| `POST /api/leads/{n}/nrp` `{par,canal?}` **(route existante, BRANCHÉE)** | branche selon payload : legacy `{nrp_count}` inchangé ; nouveau `{par,canal?}` → append échange `{type:appel,resultat:nrp,origine:manuel,contenu:"Appel — pas de réponse"}` ; `nrp_count++`/`nrp_log` ; pose `rappel{date:demain,assigne_a:par,origine:nrp}` ; si plafonds atteints → statut `injoignable` + `rappel=null` |
| `POST /api/leads/{n}/contact` `{canal,resultat,par,contenu?}` | (option) action manuelle multicanal = append échange + recalcul compteurs |
| `POST /api/leads/{n}/action-done` `{kind,resultat,par,maj_statut?}` | archive `rdv`/`rappel` courant dans `actions_log`, le met à null, MAJ statut si demandé. Défauts : RDV fait → `contacte` ; rappel fait → proposer **reprogrammer** ou `contacte` |
| `GET /api/a-traiter?assigne=tous\|avi\|…` | calcule + trie la liste (voir §6) |

Détections = **non stockées**, calculées dans `/api/a-traiter`. « Marquer fait » d'une détection = enregistrement de **rejet** dans `actions_log` (`type:detection`, `subtype`, `trigger_at`) ; re-déclenche seulement sur **nouveau** trigger postérieur.

## 6. Logique `/api/a-traiter`

Seuils configurables (params admin) : `devis_3j=3`, `jamais_contacte_2j=2`, `simu_3j=3`, plafonds canal `appel=8/sms=5/email=5`, `rdv_imminent=30 min`.

Pour chaque lead non supprimé, dériver 0..n items :
- **RDV** (si `lead.rdv`) → `etat` : `retard` (dt passé), `imminent` (0..30 min), `aujourdhui` (date=today), `a_venir` (exclu).
- **Rappel** (si `lead.rappel`) → `etat` : `retard` (date<today), `aujourdhui` (=today), `a_venir` (exclu).
- **Détections** (3 règles §8) → `etat:"detection"` + `since_days`, sauf si rejet postérieur.

**Filtre** `assigne` : RDV/rappel par `assigne_a` ; détections **visibles par tous** (pas de filtre par personne). **Scope** défaut = `retard|imminent|aujourdhui|detection` (futur exclu ; `?scope=semaine` plus tard).

**Tri global** (buckets) :
1. **Retards** (RDV passés + rappels `date<today`) — échéance croissante.
2. **RDV du jour** (dont imminents) — par **heure**.
3. **Rappels du jour** — par **ancienneté** (`cree_at` asc).
4. **Détections** — par `since_days` desc.

Réponse : `{ generated_at, counts:{total,retards,rdv_imminent,du_jour}, items:[…] }`.

## 7. Badge topbar + notif 30 min

**Badge** (`hexa-lite-top` `index.html:7921`) : poll `GET /api/a-traiter` ~60 s (+ au focus). Nombre = `du_jour+retards` ; **rouge si `retards>0`** ; **point pulsé si `rdv_imminent>0`**. Clic → vue « À traiter ». Toggle moi/tous.

**Notif 30 min** (CRM ouvert seulement) : timer client ~60 s (réutilise le poll). RDV `etat:"imminent"` non déjà notifié (dédup `id=numero:date:heure`, mémoire + localStorage) → **bandeau** + **son léger**. CRM fermé → pas de notif, mais RDV en rouge `retard/imminent` à la réouverture (rien perdu).

**Caveats** : (a) notifs onglet ouvert seulement (pas de push/service-worker) ; (b) autoplay son possiblement bloqué avant 1re interaction (fallback bandeau + titre clignotant) ; (c) cadence ~60 s ⇒ ±1 min sur le seuil.

## 8. Détections automatiques (sources réelles)

| Règle | Condition |
|---|---|
| Devis sans réponse ≥3 j | `statut=="devis_envoye"` ET `date_envoi_devis`>3 j ET statut ≠ signe/perdu |
| Jamais contacté ≥2 j | `statut=="nouveau"` ET `nrp_count==0` ET aucun échange ET `date`(création)>2 j |
| Simu sans devis ≥3 j | `states_simulateur/{n}.json` existe, `updated_at`>3 j, ET pas de devis envoyé |

Sources : `date_envoi_devis` (lead), `echanges.json`, `states_simulateur/{n}.json` (`updated_at` Paris `main.py:478`), `devis_envoyes.json`. Seuils dans params admin.

## 9. Étapes (chacune testable seule)

1. **Backend socle** — champs `rdv/rappel/actions_log` + statut `injoignable` (PROSPECT_FIELDS/defaults/migration) ; endpoints dédiés (`rdv`, `rappel`, **`nrp` à créer** → échange+auto-rappel, `action-done`, option `contact`) ; `GET /api/a-traiter` (agrégation+tri ; détections en stub). Enrichir l'échange (`resultat`,`origine`). *Test : curl pose RDV/rappel/NRP → `/api/a-traiter` renvoie/trie → `action-done` archive.*
2. **Bloc fiche** — section « RDV / Rappel » + boutons d'action manuelle multicanal (appel/sms/email avec résultat), bouton NRP câblé. *Test sur une fiche.*
3. **Liste Accueil** — bloc « À traiter aujourd'hui » en haut de `#hexa-prospects-view` (réutilise `pv-table`), filtre moi/tous, « marquer fait », lignes → fiche. *Test bout en bout.*
4. **Badge + notif 30 min** — badge topbar (poll) + bandeau RDV imminent + son. *Test.*
5. **Détections auto** — 3 règles + seuils admin (remplace le stub). *Test en vieillissant des données.*
6. **(Étape 2 / futur)** — séquences de relance paramétrables admin (J+3 email, J+6 sms, J+9 appel) appendant des échanges `origine:auto`.

## 10. Décisions (résolues le 2026-06-28)
1. **Détections visibles par TOUS** (pas de filtre par `cree_par`).
2. **Mémoire de rejet** des détections via `actions_log` — **OK**.
3. **NRP sans texte** : relâcher `contenu` obligatoire, **contenu auto = « Appel — pas de réponse »**.
4. **« Marquer fait » — transitions par défaut** : RDV fait → statut **`contacte`** ; rappel fait → **proposer** soit **reprogrammer un rappel**, soit passer **`contacte`**.
5. **Plafonds** : **8 appels / 5 sms / 5 emails**, `injoignable` quand **les 3 atteints** — **confirmé**. WhatsApp plus tard.
6. **Route NRP — branchement rétro-compatible** (validé 2026-06-28) : la route `/api/leads/{n}/nrp` existe déjà (set compteur) et reste utilisée par le front. On **branche** selon le payload (`nrp_count` présent → legacy inchangé ; sinon `{par,canal?}` → nouveau comportement). Pas de route séparée.
7. **`assigne`/`par` inconnu — TOLÉRANT** (validé 2026-06-28) : on normalise en minuscule, **pas de 400** (identité déclarative non authentifiée). `ASSIGNES_VALIDES` sert d'indicatif, pas de filtre dur.
8. **Endpoint `/contact` inclus dès l'étape 1, sous-étape 1** (validé 2026-06-28) : fondation multicanal générique (`{canal,resultat,par,contenu?}`) ; le NRP-event en est le cas particulier `canal=appel,resultat=nrp` + auto-rappel.
9. **Statut `injoignable` hors whitelist `/status`** : posé **uniquement** côté serveur (route nrp), jamais via `/api/leads/{n}/status`.
