// Recompute every published fixture in JavaScript from its stored model inputs and compare with Python.
// Usage: node site/parity_test.js .cache/parity.json
const E = require('./engine.js');
const fs = require('fs');
const J = JSON.parse(fs.readFileSync(process.argv[2] || '.cache/parity.json', 'utf8'));
let worst = 0, worstKey = '', n = 0, pickMismatch = 0, idErr = 0;
for (const f of J.fixtures) {
  const r = E.fromInputs(f.inputs, J.leagues[f.div].base, J.meta);
  for (const [k, v] of Object.entries(f.markets)) {
    if (!(k in r.markets)) { console.log('eksik pazar', k); process.exitCode = 1; continue; }
    const d = Math.abs(r.markets[k] - v); n++;
    if (d > worst) { worst = d; worstKey = k; }
  }
  for (const k of Object.keys(r.markets)) if (!(k in f.markets)) { console.log('fazla pazar', k); process.exitCode = 1; }
  const same = (x, y) => (!x && !y) || (x && y && x[0] === y[0] && Math.abs(x[1] - y[1]) < 1e-9);
  if (!same(r.banko, f.banko) || !same(r.surpriz, f.surpriz)) pickMismatch++;
  let s = 0; for (const row of r.FT) for (const v of row) s += v; idErr = Math.max(idErr, Math.abs(s - 1));
  if ('İY/MS 1/1' in r.markets) { let s2 = 0; for (const c of E.CELLS) s2 += r.markets['İY/MS ' + c[0] + '/' + c[1]]; idErr = Math.max(idErr, Math.abs(s2 - 1)); }
}
const out = { fixtures: J.fixtures.length, checks: n, max_abs_diff: worst, worst: worstKey, pick_mismatch: pickMismatch, identity_error: idErr };
console.log(JSON.stringify(out));
if (worst > 1e-9 || pickMismatch || idErr > 1e-9) { console.log('EŞLİK TESTİ BAŞARISIZ'); process.exit(1); }
console.log('EŞLİK TAMAM');
