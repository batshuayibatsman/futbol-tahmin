/* Tahmin motoru – JavaScript port of model.py / probs.py / markets.py (probability layer).
   The goal means in each fixture's inputs already include the bookmaker odds (market.py, Python side).
   Deterministic: no random numbers. Parity with the Python reference is checked by parity_test.js. */
(function (root) {
  'use strict';
  const MAXG = 10;
  const LG = [0.99999999999980993, 676.5203681218851, -1259.1392167224028, 771.32342877765313, -176.61502916214059,
    12.507343278686905, -0.13857109526572012, 9.9843695780195716e-6, 1.5056327351493116e-7];
  function lgamma(x) {
    if (x < 0.5) return Math.log(Math.PI / Math.abs(Math.sin(Math.PI * x))) - lgamma(1 - x);
    x -= 1;
    let a = LG[0];
    const t = x + 7.5;
    for (let i = 1; i < 9; i++) a += LG[i] / (x + i);
    return 0.5 * Math.log(2 * Math.PI) + (x + 0.5) * Math.log(t) - t + Math.log(a);
  }
  const LF = (() => { const a = [0]; let s = 0; for (let k = 1; k <= 60; k++) { s += Math.log(k); a.push(s); } return a; })();

  function poisVec(lam, n = MAXG) {
    const p = new Array(n + 1); let s = 0;
    const ll = Math.log(lam);
    for (let k = 0; k <= n; k++) { p[k] = Math.exp(-lam + k * ll - LF[k]); s += p[k]; }
    for (let k = 0; k <= n; k++) p[k] /= s;
    return p;
  }
  function outer(a, b) { return a.map(x => b.map(y => x * y)); }
  function stateOf(i, j, K) { const c = (K - 1) / 2; return Math.min(Math.max(i - j, -c), c) + c; }

  function matchDistribution(lh, la, s1h, s1a, cal) {
    const l1h = lh * s1h, l1a = la * s1a, l2h = lh - l1h, l2a = la - l1a;
    const M1 = outer(poisVec(l1h), poisVec(l1a));
    const K = cal.st.length, n = MAXG + 1;
    const S = []; const ps = new Array(K).fill(0);
    for (let i = 0; i < n; i++) { S.push([]); for (let j = 0; j < n; j++) { const k = stateOf(i, j, K); S[i].push(k); ps[k] += M1[i][j]; } }
    let nh = 0, na = 0;
    for (let k = 0; k < K; k++) { nh += ps[k] * cal.st[k][0]; na += ps[k] * cal.st[k][1]; }
    const M2 = [];
    for (let k = 0; k < K; k++) M2.push(outer(poisVec(l2h * cal.st[k][0] / nh), poisVec(l2a * cal.st[k][1] / na)));
    return { M1, M2, S };
  }

  function summarize(M1, M2, S) {
    const n = MAXG + 1, N = 2 * n - 1, z = 2 * (n - 1);
    const FT = Array.from({ length: N }, () => new Array(N).fill(0));
    const htft = [[0, 0, 0], [0, 0, 0], [0, 0, 0]];
    // distribution of 2nd-half goal difference for each state
    const D2 = M2.map(B => { const d = new Array(N).fill(0); for (let a = 0; a < n; a++) for (let b = 0; b < n; b++) d[a - b + n - 1] += B[a][b]; return d; });
    for (let i = 0; i < n; i++) for (let j = 0; j < n; j++) {
      const p = M1[i][j]; if (p <= 0) continue;
      const k = S[i][j], B = M2[k];
      for (let a = 0; a < n; a++) { const row = FT[i + a], Ba = B[a]; for (let b = 0; b < n; b++) row[j + b] += p * Ba[b]; }
      const r = i > j ? 0 : (i === j ? 1 : 2);
      const d = D2[k]; let w = 0, dr = 0, l = 0;
      for (let t = 0; t < N; t++) { const tot = (i - j) + (t - (n - 1)); if (tot > 0) w += d[t]; else if (tot === 0) dr += d[t]; else l += d[t]; }
      htft[r][0] += p * w; htft[r][1] += p * dr; htft[r][2] += p * l;
    }
    return { FT, htft };
  }

  function applyHtftCal(FT, htft, F) {
    const adj = htft.map((row, r) => { const a = row.map((v, c) => v * F[r][c]); const s = a.reduce((x, y) => x + y, 0), s0 = row.reduce((x, y) => x + y, 0); return a.map(v => v / s * s0); });
    const raw = [0, 1, 2].map(c => htft[0][c] + htft[1][c] + htft[2][c]);
    const nw = [0, 1, 2].map(c => adj[0][c] + adj[1][c] + adj[2][c]);
    const g = [nw[0] / raw[0], nw[1] / raw[1], nw[2] / raw[2]];
    const FT2 = FT.map((row, i) => row.map((v, j) => v * (i > j ? g[0] : (i === j ? g[1] : g[2]))));
    return { FT: FT2, htft: adj };
  }

  function nbPmf(mean, k, n = 40) {
    const p = new Array(n + 1); let s = 0;
    for (let x = 0; x <= n; x++) {
      const lp = lgamma(x + k) - lgamma(k) - lgamma(x + 1) + k * Math.log(k / (k + mean)) + x * Math.log(mean / (k + mean));
      p[x] = Math.exp(lp); s += p[x];
    }
    return p.map(v => v / s);
  }
  const tail = (p, from) => { let s = 0; for (let i = from; i < p.length; i++) s += p[i]; return s; };
  function cornerMean(ch, ca, cavg, beta) { return Math.pow(cavg, 1 - beta) * Math.pow(ch + ca, beta); }

  const CELLS = ['11', '1X', '12', 'X1', 'XX', 'X2', '21', '2X', '22'];
  const hasNum = x => x !== null && x !== undefined && x === x;

  function rawProbs(lh, la, ch, ca, cavg, s1h, s1a, cal, hasHT) {
    const { M1, M2, S } = matchDistribution(lh, la, s1h, s1a, cal);
    let { FT, htft } = summarize(M1, M2, S);
    if (cal.F) ({ FT, htft } = applyHtftCal(FT, htft, cal.F));
    const n = MAXG + 1, N = 2 * n - 1;
    const d = { ht: hasHT !== false && hasHT !== 0 };    // false: league without half-time scores (full-time markets only)
    let p1 = 0, px = 0, p2 = 0, eg = 0; const tot = new Array(2 * N - 1).fill(0);
    for (let i = 0; i < N; i++) for (let j = 0; j < N; j++) { const v = FT[i][j]; if (i > j) p1 += v; else if (i === j) px += v; else p2 += v; tot[i + j] += v; eg += (i + j) * v; }
    d.p1 = p1; d.px = px; d.p2 = p2;
    for (const L of [0.5, 1.5, 2.5, 3.5, 4.5]) d['o' + L] = tail(tot, Math.round(L + 0.5));
    let c0 = 0, r0 = 0; for (let k = 0; k < N; k++) { c0 += FT[0][k]; r0 += FT[k][0]; }
    d.btts = 1 - c0 - r0 + FT[0][0];
    let h1 = 0, hx = 0, h2 = 0, eg1 = 0; const t1 = new Array(2 * n - 1).fill(0);
    for (let i = 0; i < n; i++) for (let j = 0; j < n; j++) { const v = M1[i][j]; if (i > j) h1 += v; else if (i === j) hx += v; else h2 += v; t1[i + j] += v; eg1 += (i + j) * v; }
    d.h1 = h1; d.hx = hx; d.h2 = h2;
    d['ho0.5'] = tail(t1, 1); d['ho1.5'] = tail(t1, 2); d['ho2.5'] = tail(t1, 3);
    const lab = '1X2';
    for (let a = 0; a < 3; a++) for (let b = 0; b < 3; b++) d['hf' + lab[a] + lab[b]] = htft[a][b];
    d.exp_g = eg; d.exp_g1 = eg1;
    let pc = null, pc1 = null;
    if (hasNum(ch) && hasNum(ca) && hasNum(cavg)) {          // leagues without corner statistics have no corner markets
      const mc = cornerMean(ch, ca, cavg, cal.c_beta);
      pc = nbPmf(mc, cal.nb_k); pc1 = nbPmf(mc * cal.c1_share, cal.nb_k);
      d.exp_c = mc; d.exp_c1 = mc * cal.c1_share;
      for (const L of [7.5, 8.5, 9.5, 10.5, 11.5, 12.5]) d['co' + L] = tail(pc, Math.round(L + 0.5));
      for (const L of [3.5, 4.5, 5.5]) d['hco' + L] = tail(pc1, Math.round(L + 0.5));
    } else { d.exp_c = null; d.exp_c1 = null; }
    // top scores (stable: probability desc, then row-major index asc)
    const ft = []; for (let i = 0; i < N; i++) for (let j = 0; j < N; j++) ft.push([i, j, FT[i][j], i * N + j]);
    ft.sort((x, y) => (y[2] - x[2]) || (x[3] - y[3]));
    const ht = []; for (let i = 0; i < n; i++) for (let j = 0; j < n; j++) ht.push([i, j, M1[i][j], i * n + j]);
    ht.sort((x, y) => (y[2] - x[2]) || (x[3] - y[3]));
    return { d, FT, M1, htft, pc, pc1, ft_top: ft.slice(0, 10).map(r => r.slice(0, 3)), ht_top: ht.slice(0, 6).map(r => r.slice(0, 3)) };
  }

  function marketProbs(d) {
    const m = {
      'MS 1': d.p1, 'MS X': d.px, 'MS 2': d.p2,
      'ÇŞ 1X': d.p1 + d.px, 'ÇŞ X2': d.px + d.p2, 'ÇŞ 12': d.p1 + d.p2,
      'KG Var': d.btts, 'KG Yok': 1 - d.btts,
    };
    if (d.ht !== false) Object.assign(m, {
      'İY 1': d.h1, 'İY X': d.hx, 'İY 2': d.h2,
      'İY 0.5 Üst': d['ho0.5'], 'İY 0.5 Alt': 1 - d['ho0.5'],
      'İY 1.5 Üst': d['ho1.5'], 'İY 1.5 Alt': 1 - d['ho1.5'],
      'İY 2.5 Üst': d['ho2.5'], 'İY 2.5 Alt': 1 - d['ho2.5'],
    });
    for (const L of ['1.5', '2.5', '3.5', '4.5']) { m[L + ' Üst'] = d['o' + L]; m[L + ' Alt'] = 1 - d['o' + L]; }
    if (hasNum(d['co7.5'])) {
      for (const L of ['7.5', '8.5', '9.5', '10.5', '11.5', '12.5']) { m['Korner ' + L + ' Üst'] = d['co' + L]; m['Korner ' + L + ' Alt'] = 1 - d['co' + L]; }
      for (const L of ['3.5', '4.5', '5.5']) if (hasNum(d['hco' + L])) { m['İY Korner ' + L + ' Üst'] = d['hco' + L]; m['İY Korner ' + L + ' Alt'] = 1 - d['hco' + L]; }
    }
    if (d.ht !== false) for (const c of CELLS) m['İY/MS ' + c[0] + '/' + c[1]] = d['hf' + c];
    if (d.p1 < d.p2) m['Sürpriz MS 1'] = d.p1; else m['Sürpriz MS 2'] = d.p2;
    return m;
  }

  function pickBanko(m, R) {
    let best = null;
    for (const k of R.banko_menu) { const p = m[k]; if (p === undefined || p > R.banko_max) continue; if (!best || p > best[1] + 1e-12) best = [k, p]; }
    return best && best[1] >= R.banko_min ? best : null;
  }
  function pickSurprise(m, base, R) {
    let best = null;
    for (const k of R.surprise_menu) {
      const p = m[k], b = base[k]; if (p === undefined || b === undefined || p < R.surprise_min_p) continue;
      const lift = p / b; if (lift < R.surprise_min_lift) continue;
      if (!best || lift > best[2] + 1e-12) best = [k, p, lift];
    }
    return best;
  }

  // all probabilities from the seven model inputs stored with every fixture
  function fromInputs(inp, base, meta) {
    const r = rawProbs(inp.lh, inp.la, inp.ch, inp.ca, inp.c_avg, inp.s1h, inp.s1a, meta.cal, inp.ht);
    const m = marketProbs(r.d);
    return Object.assign({ lh: inp.lh, la: inp.la, ch: inp.ch, ca: inp.ca }, r,
      { markets: m, banko: pickBanko(m, meta.rules), surpriz: pickSurprise(m, base || {}, meta.rules) });
  }
  // Asian handicap for the home side (line = home handicap, e.g. -0.5, -0.25, 0, +1).
  // Returns expected profit per unit for home and away at the given odds, from the full score matrix.
  function ahEV(FT, line, oddsHome, oddsAway) {
    const N = FT.length, dif = new Map();
    for (let i = 0; i < N; i++) for (let j = 0; j < N; j++) dif.set(i - j, (dif.get(i - j) || 0) + FT[i][j]);
    const q = Math.round(line * 4);
    const halves = (q % 2 !== 0) ? [(q - 1) / 4, (q + 1) / 4] : [line];
    function side(sign, odds) {
      if (!odds) return null;
      let ev = 0, win = 0, push = 0;
      for (const L of halves) {
        for (const [d, p] of dif) {
          const v = sign * d + (sign > 0 ? L : -L);
          if (v > 1e-9) { ev += p * (odds - 1) / halves.length; win += p / halves.length; }
          else if (v < -1e-9) ev -= p / halves.length;
          else push += p / halves.length;
        }
      }
      return { ev, win, push };
    }
    return { home: side(1, oddsHome), away: side(-1, oddsAway) };
  }
  function teamMeans(L, h, a) {
    const c = hasNum(L.cmu) && hasNum(h.catt) && hasNum(a.catt);
    return {
      lh: Math.exp(L.mu + L.gamma + h.att - a.de), la: Math.exp(L.mu + a.att - h.de),
      ch: c ? Math.exp(L.cmu + L.cgamma + h.catt - a.cde) : null, ca: c ? Math.exp(L.cmu + a.catt - h.cde) : null,
    };
  }
  function predict(L, h, a, meta) {
    const t = teamMeans(L, h, a);
    const r = rawProbs(t.lh, t.la, t.ch, t.ca, L.c_avg, L.s1h, L.s1a, meta.cal, L.ht);
    const m = marketProbs(r.d);
    return Object.assign({}, t, r, { markets: m, banko: pickBanko(m, meta.rules), surpriz: pickSurprise(m, L.base, meta.rules) });
  }
  // probability of over / push / under for any line (whole lines can push) from a pmf over totals
  function lineProbs(pmf, line) {
    let o = 0, u = 0, push = 0;
    for (let t = 0; t < pmf.length; t++) { if (t > line + 1e-9) o += pmf[t]; else if (Math.abs(t - line) < 1e-9) push += pmf[t]; else u += pmf[t]; }
    return { over: o, push, under: u };
  }
  function totalGoalsPmf(FT) { const N = FT.length; const t = new Array(2 * N - 1).fill(0); for (let i = 0; i < N; i++) for (let j = 0; j < N; j++) t[i + j] += FT[i][j]; return t; }
  function parseOdds(s) {
    if (s === null || s === undefined) return null;
    s = String(s).trim().replace(',', '.');
    if (!s) return null;
    if (/^[+-]\d+(\.\d+)?$/.test(s)) { const v = parseFloat(s); if (Math.abs(v) < 100) return null; return v > 0 ? 1 + v / 100 : 1 + 100 / Math.abs(v); }
    const v = parseFloat(s); return (isFinite(v) && v > 1) ? v : null;
  }
  function ev(pWin, pPush, odds) { return pWin * (odds - 1) - (1 - pWin - pPush); }

  const api = { MAXG, lgamma, poisVec, matchDistribution, summarize, applyHtftCal, nbPmf, cornerMean, rawProbs, marketProbs,
    pickBanko, pickSurprise, teamMeans, predict, fromInputs, ahEV, lineProbs, totalGoalsPmf, parseOdds, ev, CELLS };
  if (typeof module !== 'undefined' && module.exports) module.exports = api; else root.Engine = api;
})(typeof window !== 'undefined' ? window : globalThis);
