/**
 * Test de non-regression : incoherence bandeau / montants du simulateur.
 *
 * Symptome du ticket : apres passage de la fiche en SUPERIEUR, le bandeau
 * "Repris de la fiche" affiche bien SUP mais les montants MPR/CEE restent
 * calcules en TMO.
 *
 * Deux causes, deux verifications :
 *
 *  A. Rendus concurrents. render()/refresh()/patch() sont async (calcul() attend
 *     les baremes). Un rendu demarre AVANT la modification de la fiche peut
 *     resoudre APRES le rendu a jour et re-ecrire l'ancien HTML par-dessus,
 *     refigeant l'ecran sur l'ancienne categorie. Verifie ici en faisant
 *     resoudre deux rendus dans le desordre : seul le dernier DEMARRE a le
 *     droit d'ecrire dans le DOM.
 *
 *  B. Bandeau et montants doivent provenir du MEME calcul. Si le libelle lit
 *     state.categorie (valeur vivante, relue apres l'await) pendant que les
 *     montants viennent de l'objet c (fige avant l'await), les deux divergent :
 *     SUP au-dessus de chiffres TMO. Le libelle doit lire c.categorie.
 *
 * Usage : node scripts/test_render_race_simulateur.mjs [chemin_html]
 * Sortie 0 si les deux invariants tiennent, 1 sinon.
 */
import fs from 'node:fs';
import vm from 'node:vm';

const FILE = process.argv[2] || 'templates/index.html';
const html = fs.readFileSync(FILE, 'utf8');

function extractFunction(src, name) {
  let start = src.indexOf(`function ${name}(`);
  if (start === -1) throw new Error(`fonction introuvable : ${name}`);
  if (src.slice(Math.max(0, start - 6), start) === 'async ') start -= 6;
  let depth = 0;
  for (let i = src.indexOf('{', start); i < src.length; i++) {
    const c = src[i], next = src[i + 1];
    if (c === '/' && next === '/') { i = src.indexOf('\n', i); if (i === -1) break; continue; }
    if (c === '/' && next === '*') { i = src.indexOf('*/', i) + 1; continue; }
    if (c === '"' || c === "'" || c === '`') {
      const q = c;
      const BS = String.fromCharCode(92);
      for (i++; i < src.length; i++) { if (src[i] === BS) { i++; continue; } if (src[i] === q) break; }
      continue;
    }
    if (c === '{') depth++;
    else if (c === '}') { depth--; if (depth === 0) return src.slice(start, i + 1); }
  }
  throw new Error(`accolade non fermee pour ${name}`);
}

let ko = 0;
const ok = (m) => console.log('OK   - ' + m);
const ko_ = (m) => { ko++; console.log('ECHEC - ' + m); };

console.log(`Fichier teste : ${FILE}\n`);

// ---------------------------------------------------------------- A. course
console.log('A. Rendus concurrents : un rendu perime ne doit pas ecrire dans le DOM');

const refreshSrc = extractFunction(html, 'refresh');
const content = { innerHTML: '' };
const sandbox = {
  __renderSeq: 0,
  ecrits: [],
  // render() stubbe : chaque appel resout quand on le decide.
  pending: [],
  render(seq) {
    return new Promise((res) => sandbox.pending.push(() => res(`HTML#${seq}`)));
  },
  bind() {},
  document: {
    getElementById: (id) => (id === 'sim-drawer-content' ? content : null),
    querySelector: () => null,
    activeElement: null,
  },
  console,
};
sandbox.globalThis = sandbox;
vm.createContext(sandbox);
vm.runInContext(`${refreshSrc}; globalThis.__refresh = refresh;`, sandbox);

// rendu 1 (ancienne categorie) puis rendu 2 (categorie a jour), resolus a l'envers
const p1 = sandbox.__refresh();
const p2 = sandbox.__refresh();
const [r1, r2] = sandbox.pending;
await Promise.resolve();
r2();                 // le rendu a jour resout en premier
await p2;
const apresFrais = content.innerHTML;
r1();                 // le rendu perime resout ensuite
await p1;
const apresPerime = content.innerHTML;

console.log(`   apres rendu a jour   : ${JSON.stringify(apresFrais)}`);
console.log(`   apres rendu perime   : ${JSON.stringify(apresPerime)}`);
if (apresPerime === apresFrais && apresFrais === 'HTML#2') {
  ok('le rendu perime est ignore, le DOM garde le rendu a jour.');
} else {
  ko_('le rendu perime a ecrase le rendu a jour (ecran refige sur l\'ancienne categorie).');
}

// -------------------------------------------------- B. coherence du bandeau
console.log('\nB. Bandeau et montants issus du meme calcul');

const renderSrc = extractFunction(html, 'render');
const litCalcul = /LABELS_ANAH\[c\.categorie\]/.test(renderSrc) && /LABELS_CEE\[c\.categorie\]/.test(renderSrc);
const litStateVivant = /LABELS_ANAH\[state\.categorie\]/.test(renderSrc) || /LABELS_CEE\[state\.categorie\]/.test(renderSrc);

if (litCalcul && !litStateVivant) {
  ok('le bandeau lit c.categorie : il ne peut plus afficher SUP au-dessus de montants TMO.');
} else if (litStateVivant) {
  ko_('le bandeau lit state.categorie (valeur vivante) alors que les montants viennent de c : divergence possible.');
} else {
  ko_('libelles de categorie introuvables dans render().');
}

// la categorie doit effectivement etre exposee par calcul()
const calculSrc = extractFunction(html, 'calcul');
if (/categorie:\s*state\.categorie/.test(calculSrc)) {
  ok('calcul() expose la categorie ayant servi aux montants.');
} else {
  ko_('calcul() n\'expose pas sa categorie : le bandeau ne peut pas s\'y aligner.');
}

console.log(`\nRESULTAT : ${ko ? 'ECHEC' : 'OK'}`);
process.exit(ko ? 1 : 0);
