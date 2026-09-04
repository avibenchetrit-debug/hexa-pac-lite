/**
 * Test de non-regression : la categorie de la fiche doit piloter les montants
 * MPR/CEE du simulateur a CHAQUE ouverture.
 *
 * Scenario (celui du ticket) :
 *   1. prospect TMO -> on ouvre le simulateur (un state est sauvegarde,
 *      contenant categorie_revenu: "tres_modeste")
 *   2. on passe la fiche en SUPERIEUR (RFR eleve)
 *   3. on rouvre le simulateur -> les montants MPR/CEE doivent refleter SUPERIEUR
 *
 * Le test extrait et execute le VRAI code livre (lireContexteFiche,
 * loadSimulatorState et la sequence d'ouverture de ouvrir()) depuis le HTML,
 * dans un bac a sable avec un DOM minimal. Il peut etre lance sur n'importe
 * quelle version du fichier, ce qui permet de comparer avant/apres correctif.
 *
 * Usage (depuis la racine du depot) :
 *   node scripts/test_categorie_simulateur.mjs [chemin_html]
 * Sans argument, teste templates/index.html (le fichier reellement servi).
 * Sortie 0 si le simulateur suit la fiche, 1 sinon.
 */
import fs from 'node:fs';
import vm from 'node:vm';

const FILE = process.argv[2] || 'templates/index.html';
const html = fs.readFileSync(FILE, 'utf8');

// --- Config reelle (data/ + /api/admin/m3) -------------------------------
const M3_CONFIG = {
  forfaits_mpr: { tres_modeste: 5000, modeste: 4000, intermediaire: 3000, superieur: 0 },
  bonification_cee: { actif: true, multiplicateur: 5 },
  delegataires: [{ nom: 'PICOTY', mwh_precaire: 12.5, mwh_classique: 7.2, actif: true }],
  formule_bar_th_171: null, // rempli plus bas depuis le serveur si fourni
};

// --- Extraction du code source reel --------------------------------------
function extractFunction(src, name) {
  let start = src.indexOf(`function ${name}(`);
  if (start === -1) throw new Error(`fonction introuvable : ${name}`);
  // conserve le mot-cle `async` s'il precede la declaration
  if (src.slice(Math.max(0, start - 6), start) === 'async ') start -= 6;
  let depth = 0, lastSig = '';
  for (let i = src.indexOf('{', start); i < src.length; i++) {
    const c = src[i], next = src[i + 1];
    // commentaires
    if (c === '/' && next === '/') { i = src.indexOf('\n', i); if (i === -1) break; continue; }
    if (c === '/' && next === '*') { i = src.indexOf('*/', i) + 1; continue; }
    // chaines et litteraux de gabarit
    if (c === '"' || c === "'" || c === '`') {
      const quote = c;
      for (i++; i < src.length; i++) {
        if (src[i] === '\\') { i++; continue; }
        if (src[i] === quote) break;
      }
      lastSig = quote;
      continue;
    }
    // litteral d'expression reguliere (heuristique sur le contexte precedent)
    if (c === '/' && '(,=:[!&|?{};+-*%~^'.includes(lastSig)) {
      for (i++; i < src.length; i++) {
        if (src[i] === '\\') { i++; continue; }
        if (src[i] === '[') { while (i < src.length && src[i] !== ']') { if (src[i] === '\\') i++; i++; } continue; }
        if (src[i] === '/') break;
      }
      lastSig = '/';
      continue;
    }
    if (c === '{') depth++;
    else if (c === '}') { depth--; if (depth === 0) return src.slice(start, i + 1); }
    if (!/\s/.test(c)) lastSig = c;
  }
  throw new Error(`accolade non fermee pour ${name}`);
}

function extractBetween(src, from, to, label) {
  const a = src.indexOf(from);
  if (a === -1) throw new Error(`marqueur absent (${label}) : ${from}`);
  const b = src.indexOf(to, a);
  if (b === -1) throw new Error(`marqueur de fin absent (${label}) : ${to}`);
  return src.slice(a, b);
}

// Sequence d'ouverture reelle du tiroir simulateur (le coeur du bug).
const SEQUENCE_OUVERTURE = extractBetween(
  html,
  "const sub = document.getElementById('sim-drawer-prospect');",
  '// PAS de fermeture des panneaux droits',
  'ouvrir()'
);

const SOURCES = [
  'num', 'normaliserZone', 'zoneReglementaireFromCp',
  'lireContexteFiche', 'loadSimulatorState', 'simulatorPayload',
  'calculerCeeBarTh171',
].map(n => extractFunction(html, n)).join('\n\n');

// --- DOM minimal : la fiche prospect --------------------------------------
function makeFiche({ categorie, rfr, surface }) {
  const byId = {
    'categorie-input': { value: categorie },
    'cat-anah-badge': { textContent: { tres_modeste: 'TMO', modeste: 'MO', intermediaire: 'INT', superieur: 'SUP' }[categorie] },
    'cp-chantier': { value: '53000' },
    'surface-input': { value: String(surface) },
    'altitude-input': { value: '100' },
    'phase-input': { value: 'monophase' },
    'hsp-input': { value: '2.5' },
    'cout_chauffage': { value: '200' },
    'rfr-input': { value: String(rfr) },
  };
  const byQuery = {
    '[name="type_logement"]': { value: 'maison' },
    'select[name="mode_chauffage"]': { value: 'fioul' },
    '[name="alimentation_electrique"]': { value: 'monophase' },
    '[name="surface_logement_m2"]': { value: String(surface) },
  };
  return {
    getElementById: id => byId[id] || null,
    querySelector: sel => byQuery[sel] || null,
  };
}

// --- Le "backend" : le state simulateur persiste --------------------------
let savedState = {};

function makeSandbox(fiche) {
  const state = {
    niveau_actif: 'recommande', numero: 'PR-000001', categorie: '', zone: '',
    zone_detail: '', cp_chantier: '', energie_avant: '', type_logement: '',
    surface_habitable: null, surface_chauffee: null, surface_forcee: false,
    service: 'chauffage_seul', prix_pac: null, facture_avant: 200,
    facture_avant_defaut: true, option: 'opt1', iso_toit: 'isole',
    iso_mur: 'isole', iso_menuiserie: 'double', modele_pac: '', modele_pac_id: '',
    modele_force: false, user_modified_price: false, mode_mpr: 'attente',
    financement_mpr: 'cash', phase_electrique: '', altitude: null, hsp: 2.5,
  };
  const sandbox = {
    state, document: fiche, M3_CONFIG,
    DEPT_ZONE_BACKEND: { '53': 'H2' },
    lastRoi: null,
    console: { warn(){}, debug(){}, log(){} },
    // effets de bord neutralises : on ne teste que l'etat resultant
    syncDimensionnement(){}, refresh(){}, chargerBaremes: async () => {},
    requestAnimationFrame(){}, clearTimeout(){}, setTimeout(){}, queueMicrotask,
    fetch: async (url, opts) => {
      if (opts && opts.method === 'POST') {
        Object.assign(savedState, JSON.parse(opts.body));
        return { ok: true, json: async () => ({ ok: true }) };
      }
      return { ok: true, json: async () => savedState };
    },
  };
  sandbox.window = sandbox;
  vm.createContext(sandbox);
  vm.runInContext(SOURCES, sandbox, { filename: 'sim-sources.js' });
  return sandbox;
}

/** Ouvre le simulateur exactement comme le fait ouvrir(). */
async function ouvrirSimulateur(fiche) {
  const sb = makeSandbox(fiche);
  // ouvrir() commence par un lireContexteFiche(), puis lance la sequence.
  vm.runInContext('lireContexteFiche();', sb);
  await vm.runInContext(
    `(async () => { ${SEQUENCE_OUVERTURE}
       // laisse la chaine de promesses d'ouverture se resoudre entierement
       for (let i = 0; i < 20; i++) await new Promise(r => queueMicrotask(r));
     })()`,
    sb
  );
  await new Promise(r => setTimeout(r, 20));
  // sauvegarde du state (debounce neutralise -> on appelle directement)
  vm.runInContext('Object.assign(globalThis.__payload = {}, simulatorPayload());', sb);
  Object.assign(savedState, sb.__payload);
  return sb;
}

// --- Montants MPR / CEE a partir de l'etat obtenu -------------------------
function montants(sb) {
  const cat = sb.state.categorie;
  const mpr = Number(M3_CONFIG.forfaits_mpr[cat] ?? 0);
  const deleg = M3_CONFIG.delegataires.find(d => d.actif);
  const prixMwh = cat === 'tres_modeste' ? deleg.mwh_precaire : deleg.mwh_classique;
  return { categorie: cat, mpr_eur: mpr, cee_prix_mwhc: prixMwh };
}

// --- Scenario -------------------------------------------------------------
const ficheTMO = makeFiche({ categorie: 'tres_modeste', rfr: 15000, surface: 100 });
const ficheSUP = makeFiche({ categorie: 'superieur', rfr: 150000, surface: 100 });

console.log(`Fichier teste : ${FILE}\n`);

// 1. prospect TMO : premiere ouverture du simulateur
savedState = {};
const sb1 = await ouvrirSimulateur(ficheTMO);
const m1 = montants(sb1);
console.log('1. Prospect TMO, ouverture du simulateur');
console.log('   ->', JSON.stringify(m1));
console.log('   state persiste categorie_revenu =', JSON.stringify(savedState.categorie_revenu));

// 2. la fiche passe en SUPERIEUR, 3. on rouvre le simulateur
const sb2 = await ouvrirSimulateur(ficheSUP);
const m2 = montants(sb2);
console.log('\n2. La fiche passe en SUPERIEUR (RFR 150 000)');
console.log('3. Reouverture du simulateur');
console.log('   ->', JSON.stringify(m2));

// --- Verdict 1 : les champs de la fiche sont resynchronises ---------------
const attendu = { categorie: 'superieur', mpr_eur: 0, cee_prix_mwhc: 7.2 };
const okCategorie = JSON.stringify(m2) === JSON.stringify(attendu);
console.log('\nAttendu apres passage en SUPERIEUR :', JSON.stringify(attendu));
console.log(okCategorie
  ? 'OK   - le simulateur suit la categorie de la fiche.'
  : `ECHEC - le simulateur reste fige sur "${m2.categorie}" (montants MPR/CEE perimes).`);

// --- Verdict 2 : les choix propres a la simulation sont conserves ---------
// (modele de PAC choisi a la main + surface forcee dans le simulateur)
savedState = {
  ...savedState,
  modele_pac_id: 'PAC-TEST-12KW',
  modele_pac_nom: 'Modele choisi a la main',
  service: 'chauffage_ecs',
  option: 'opt3',
  surface_chauffee: 142,
  surface_forcee: true,
};
const sb3 = await ouvrirSimulateur(ficheSUP);
const choix = {
  modele_pac_id: sb3.state.modele_pac_id,
  modele_pac: sb3.state.modele_pac,
  service: sb3.state.service,
  option: sb3.state.option,
  surface_chauffee: sb3.state.surface_chauffee,
};
const attenduChoix = {
  modele_pac_id: 'PAC-TEST-12KW',
  modele_pac: 'Modele choisi a la main',
  service: 'chauffage_ecs',
  option: 'opt3',
  surface_chauffee: 142,
};
const okChoix = JSON.stringify(choix) === JSON.stringify(attenduChoix);
console.log('\n4. Choix propres a la simulation apres reouverture');
console.log('   ->', JSON.stringify(choix));
console.log(okChoix
  ? 'OK   - modele PAC, service, option et surface forcee sont conserves.'
  : `ECHEC - choix perdus, attendu ${JSON.stringify(attenduChoix)}`);

const ok = okCategorie && okChoix;
console.log(ok ? '\nRESULTAT : OK' : '\nRESULTAT : ECHEC');
process.exit(ok ? 0 : 1);
