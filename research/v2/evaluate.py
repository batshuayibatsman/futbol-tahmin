"""v2 out-of-sample evaluation on the untouched TEST seasons 2024-25 and 2025-26, 22 leagues.
Same measures as v1 (research/evaluate.py). Usage: python research/v2/evaluate.py <variant>   (model | oran)
Writes out/v2_<variant>_backtest.json in the format the page reads (data/frozen/backtest.json) and the base rates."""
import json, sys
sys.path.insert(0, 'tahmin')
import numpy as np, pandas as pd
from markets import market_probs, market_outcomes, pick_banko, pick_surprise, base_rates, CELLS, BANKO_MIN, BANKO_MAX, SURPRISE_MIN_LIFT

variant = sys.argv[1] if len(sys.argv) > 1 else 'oran'
V = pd.read_pickle(f'out/v2_{variant}_val.pkl'); T = pd.read_pickle(f'out/v2_{variant}_test.pkl')
L22 = sorted(T['div'].unique())


def nz(x):
    return None if x is None or x != x else x


def outcome_frame(D):
    return pd.DataFrame([market_outcomes(int(r.hg), int(r.ag), int(r.hthg), int(r.htag), nz(r.hc), nz(r.ac), r.p1, r.p2)
                         for r in D.itertuples()], index=D.index)


def prob_frame(D):
    return pd.DataFrame([market_probs(r) for r in D.to_dict('records')], index=D.index)


OT, OV, MT, MV = outcome_frame(T), outcome_frame(V), prob_frame(T), prob_frame(V)


def ll_bin(p, y):
    p = np.clip(np.asarray(p, float), 1e-9, 1 - 1e-9); y = np.asarray(y, float)
    return float(-(y * np.log(p) + (1 - y) * np.log(1 - p)).mean())


def block(sel):
    t, ot, mt = T[sel], OT[sel], MT[sel]
    vsel = V['div'].isin(t['div'].unique())
    ov = OV[vsel]
    r = {'n': int(sel.sum())}
    pm = t[['p1', 'px', 'p2']].values; y = ot[['MS 1', 'MS X', 'MS 2']].values.astype(float)
    base = np.array([ov['MS 1'].mean(), ov['MS X'].mean(), ov['MS 2'].mean()])
    io = 1 / t[['oh', 'od', 'oa']].values; mk = io / io.sum(1, keepdims=True); ok = np.isfinite(mk).all(1)
    r['ms'] = {'model': float(-(y * np.log(pm)).sum(1).mean()), 'baseline': float(-(y * np.log(base)).sum(1).mean()),
               'bet365': float(-(y[ok] * np.log(mk[ok])).sum(1).mean()), 'model_same_rows': float(-(y[ok] * np.log(pm[ok])).sum(1).mean()),
               'hit_model': float((pm.argmax(1) == y.argmax(1)).mean()), 'hit_bet365': float((mk[ok].argmax(1) == y[ok].argmax(1)).mean()),
               'hit_baseline': float(y[:, 0].mean()), 'margin': float((io[ok].sum(1) - 1).mean()), 'n_odds': int(ok.sum())}
    keys = ['1.5 Üst', '2.5 Üst', '3.5 Üst', 'KG Var', 'İY 0.5 Üst', 'İY 1.5 Üst', 'İY 1', 'İY X', 'İY 2',
            'Korner 8.5 Üst', 'Korner 9.5 Üst', 'Korner 10.5 Üst', 'Korner 11.5 Üst']
    r['binary'] = {}
    for k in keys:
        if k not in mt or k not in ot:
            continue
        g = mt[k].notna() & ot[k].notna()
        if g.sum() < 50:
            continue
        r['binary'][k] = {'rate': float(ot.loc[g, k].astype(float).mean()), 'pred': float(mt.loc[g, k].mean()),
                          'model': ll_bin(mt.loc[g, k], ot.loc[g, k].astype(float)),
                          'baseline': ll_bin(np.full(int(g.sum()), ov[k].dropna().astype(float).mean()), ot.loc[g, k].astype(float))}
    ok2 = t.o25.notna() & t.u25.notna()
    io2 = 1 / t.loc[ok2, ['o25', 'u25']].values
    r['binary']['2.5 Üst']['bet365'] = ll_bin(io2[:, 0] / io2.sum(1), ot.loc[ok2, '2.5 Üst'].astype(float))
    cells = ['İY/MS ' + c[0] + '/' + c[1] for c in CELLS]
    act = ot[cells].values.astype(float).argmax(1); pr = mt[cells].values; bf = ov[cells].astype(float).mean().values
    r['htft'] = {'model': float(-np.log(pr[np.arange(len(pr)), act]).mean()), 'baseline': float(-np.log(bf[act]).mean()),
                 'hit_model': float((pr.argmax(1) == act).mean()), 'hit_baseline': float((act == 0).mean()),
                 'cells': {c: {'actual': float(ot[c].astype(float).mean()), 'pred': float(mt[c].mean())} for c in cells}}
    for c in ('İY/MS 1/2', 'İY/MS 2/1'):
        p = mt[c]; q = p.quantile(0.9)
        r['htft'][c] = {'top10_pred': float(p[p >= q].mean()), 'top10_actual': float(ot.loc[p >= q, c].astype(float).mean()),
                        'rest_actual': float(ot.loc[p < q, c].astype(float).mean()), 'n_top10': int((p >= q).sum())}
    def topk(col, hcol, acol, k):
        return float(np.mean([(int(a), int(b)) in tp[:k] for a, b, tp in zip(t[hcol], t[acol], t[col])]))
    vv = V[vsel]
    sc = t.hg.astype(int).astype(str) + '-' + t.ag.astype(int).astype(str)
    hsc = t.hthg.astype(int).astype(str) + '-' + t.htag.astype(int).astype(str)
    vsc = (vv.hg.astype(int).astype(str) + '-' + vv.ag.astype(int).astype(str)).value_counts(normalize=True)
    vhs = (vv.hthg.astype(int).astype(str) + '-' + vv.htag.astype(int).astype(str)).value_counts(normalize=True)
    r['score'] = {'model': float(-np.log(t.p_score).mean()), 'baseline': float(-np.log(sc.map(vsc).fillna(1e-4)).mean()),
                  'top1': topk('top3', 'hg', 'ag', 1), 'top3': topk('top3', 'hg', 'ag', 3),
                  'top1_baseline': float((sc == vsc.index[0]).mean()), 'top3_baseline': float(sc.isin(vsc.index[:3]).mean()),
                  'ht_model': float(-np.log(t.p_htscore).mean()), 'ht_baseline': float(-np.log(hsc.map(vhs).fillna(1e-4)).mean()),
                  'ht_top1': topk('httop3', 'hthg', 'htag', 1), 'ht_top3': topk('httop3', 'hthg', 'htag', 3),
                  'ht_top1_baseline': float((hsc == vhs.index[0]).mean()), 'ht_top3_baseline': float(hsc.isin(vhs.index[:3]).mean())}
    V2 = vv.assign(tg=vv.hg + vv.ag, t1=vv.hthg + vv.htag, tc=vv.hc + vv.ac)
    lgv = lambda tt, col: tt['div'].map(V2.groupby('div')[col].mean())
    tg = t.hg + t.ag; t1 = t.hthg + t.htag
    r['means'] = {'goals': [float(tg.mean()), float(t.exp_g.mean()), float((tg - t.exp_g).abs().mean()), float((tg - lgv(t, 'tg')).abs().mean())],
                  'ht_goals': [float(t1.mean()), float(t.exp_g1.mean()), float((t1 - t.exp_g1).abs().mean()), float((t1 - lgv(t, 't1')).abs().mean())]}
    tcm = t[t.exp_c.notna() & t.hc.notna()] if 'exp_c' in t else t.iloc[:0]
    if len(tcm) >= 50:
        tc = tcm.hc + tcm.ac
        r['means']['corners'] = [float(tc.mean()), float(tcm.exp_c.mean()), float((tc - tcm.exp_c).abs().mean()), float((tc - lgv(tcm, 'tc')).abs().mean())]
    else:
        r['means']['corners'] = None
    return r


res = {'test_seasons': '2024-25, 2025-26', 'validation_seasons': '2021-22, 2022-23, 2023-24', 'variant': variant}
allsel = np.ones(len(T), bool)
A = block(allsel)
BD = {d: block((T['div'] == d).values) for d in L22}
rel_keys = [k for k in MT.columns if k in OT.columns and not k.startswith('İY/MS')]
pp = MT[rel_keys].values.astype(float).ravel(); yy = OT[rel_keys].astype(float).values.ravel()
okm = ~np.isnan(pp) & ~np.isnan(yy); pp, yy = pp[okm], yy[okm]
bins = np.array([0, .1, .2, .3, .4, .5, .6, .7, .8, .9, 1.0001]); b = np.digitize(pp, bins) - 1
res['reliability'] = [{'bin': f'{int(bins[i]*100)}-{int(min(bins[i+1],1)*100)}%', 'n': int((b == i).sum()),
                       'pred': float(pp[b == i].mean()), 'actual': float(yy[b == i].mean())} for i in range(10) if (b == i).sum() > 0]
base = {d: base_rates([market_outcomes(int(r.hg), int(r.ag), int(r.hthg), int(r.htag), nz(r.hc), nz(r.ac), r.p1, r.p2)
                       for r in V[V['div'] == d].itertuples()]) for d in L22}
recs = []
for i, r in T.iterrows():
    m = {k: v for k, v in MT.loc[i].to_dict().items() if v == v}; o = {k: v for k, v in OT.loc[i].to_dict().items() if v == v}
    bk = pick_banko(m); sp = pick_surprise(m, base[r['div']])
    if bk:
        recs.append({'type': 'banko', 'div': r['div'], 'date': r.date, 'market': bk[0], 'p': bk[1], 'hit': bool(o[bk[0]]), 'base': base[r['div']].get(bk[0]),
                     'odds_b365': {'MS 1': r.oh, 'MS 2': r.oa, '2.5 Üst': r.o25, '2.5 Alt': r.u25}.get(bk[0], np.nan),
                     'odds_max': {'MS 1': r.mh, 'MS 2': r.ma}.get(bk[0], np.nan)})
    if sp:
        recs.append({'type': 'surpriz', 'div': r['div'], 'date': r.date, 'market': sp[0], 'p': sp[1], 'lift': sp[2], 'hit': bool(o[sp[0]]), 'base': base[r['div']].get(sp[0]),
                     'odds_b365': {'Sürpriz MS 1': r.oh, 'Sürpriz MS 2': r.oa, 'MS X': r.od}.get(sp[0], np.nan),
                     'odds_max': {'Sürpriz MS 1': r.mh, 'Sürpriz MS 2': r.ma, 'MS X': r.md}.get(sp[0], np.nan)})
R = pd.DataFrame(recs); R.to_csv(f'out/v2_{variant}_picks.csv', index=False)


def summ(d):
    out = {'n': int(len(d)), 'pred': float(d.p.mean()), 'hit': float(d.hit.mean()), 'base': float(d.base.mean())}
    for oc in ('odds_b365', 'odds_max'):
        e = d[d[oc].notna()]
        if len(e) >= 30:
            pnl = np.where(e.hit, e[oc] - 1, -1.0); cum = np.cumsum(pnl[np.argsort(e.date.values, kind='stable')])
            out[oc] = {'n': int(len(e)), 'units': float(pnl.sum()), 'roi': float(pnl.mean()),
                       'max_dd': float((np.maximum.accumulate(np.concatenate([[0], cum]))[1:] - cum).max())}
    return out


Bk = R[R.type == 'banko']; Sp = R[R.type == 'surpriz']
res['banko'] = {'rule': f'en olası pazar ({BANKO_MIN:.0%}–{BANKO_MAX:.0%})', 'all': summ(Bk),
                'by_market': {k: summ(g) for k, g in Bk.groupby('market') if len(g) >= 20},
                'by_div': {k: summ(g) for k, g in Bk.groupby('div')},
                'by_band': {str(k): summ(g) for k, g in Bk.groupby(pd.cut(Bk.p, [0.70, 0.75, 0.80, 0.85, 0.901]), observed=True)}}
res['surpriz'] = {'rule': f'olağan sıklığının ≥{SURPRISE_MIN_LIFT}× üstü', 'all': summ(Sp),
                  'by_market': {k: summ(g) for k, g in Sp.groupby('market') if len(g) >= 20},
                  'by_div': {k: summ(g) for k, g in Sp.groupby('div')}}


def sim(df, pcols, ocols, ycols, thr_edge=None, thr_p=None):
    bets = []
    for pc, oc, yc in zip(pcols, ocols, ycols):
        d = df[df[oc].notna()]; sel = np.ones(len(d), bool)
        if thr_edge is not None: sel &= (d[pc] * d[oc] >= 1 + thr_edge).values
        if thr_p is not None: sel &= (d[pc] >= thr_p).values
        d = d[sel]; bets.append(pd.DataFrame({'date': d.date, 'odds': d[oc], 'win': d[yc].astype(int)}))
    b = pd.concat(bets).sort_values('date', kind='stable')
    if len(b) == 0: return {'n': 0}
    pnl = np.where(b.win == 1, b.odds - 1, -1.0); cum = np.cumsum(pnl)
    return {'n': int(len(b)), 'hit': float(b.win.mean()), 'avg_odds': float(b.odds.mean()), 'units': float(pnl.sum()), 'roi': float(pnl.mean()),
            'max_dd': float((np.maximum.accumulate(np.concatenate([[0], cum]))[1:] - cum).max())}


X = T.copy()
for a, b_ in (('y1', 'MS 1'), ('yx', 'MS X'), ('y2', 'MS 2'), ('yo', '2.5 Üst'), ('yu', '2.5 Alt')): X[a] = OT[b_].astype(bool)
X['pu'] = 1 - X['o2.5']
res['betting'] = {
    'ms_favori_p65_b365': sim(X, ['p1', 'p2'], ['oh', 'oa'], ['y1', 'y2'], thr_p=0.65),
    'ms_favori_p65_max': sim(X, ['p1', 'p2'], ['mh', 'ma'], ['y1', 'y2'], thr_p=0.65),
    'ms_value5_b365': sim(X, ['p1', 'px', 'p2'], ['oh', 'od', 'oa'], ['y1', 'yx', 'y2'], thr_edge=0.05),
    'ms_value5_max': sim(X, ['p1', 'px', 'p2'], ['mh', 'md', 'ma'], ['y1', 'yx', 'y2'], thr_edge=0.05),
    'au25_p65_b365': sim(X, ['o2.5', 'pu'], ['o25', 'u25'], ['yo', 'yu'], thr_p=0.65),
    'au25_value5_b365': sim(X, ['o2.5', 'pu'], ['o25', 'u25'], ['yo', 'yu'], thr_edge=0.05),
    'hep_ev_sahibi_b365': sim(X, ['p1'], ['oh'], ['y1'])}
out = dict(res); out.update({k: A[k] for k in ('n', 'ms', 'binary', 'htft', 'score', 'means')})
out['by_div'] = {d: {'n': v['n'], 'ms': v['ms'], 'o25': v['binary'].get('2.5 Üst'), 'k95': v['binary'].get('Korner 9.5 Üst'),
                     'corners': v['means']['corners']} for d, v in BD.items()}
json.dump(out, open(f'out/v2_{variant}_backtest.json', 'w'), indent=1, default=float, ensure_ascii=False)
json.dump(base, open(f'out/v2_{variant}_base_rates.json', 'w'), indent=1, ensure_ascii=False)
a = out
print(variant, 'TEST n =', a['n'])
print('MS LL model %.4f | baz %.4f | Bet365 %.4f ; isabet model %.3f b365 %.3f' % (a['ms']['model'], a['ms']['baseline'], a['ms']['bet365'], a['ms']['hit_model'], a['ms']['hit_bet365']))
for k, v in a['binary'].items():
    print('  %-16s gerçek %.3f tahmin %.3f | LL %.4f baz %.4f %s' % (k, v['rate'], v['pred'], v['model'], v['baseline'], ('b365 %.4f' % v['bet365']) if 'bet365' in v else ''))
h = a['htft']; print('İY/MS LL %.4f baz %.4f hit %.3f' % (h['model'], h['baseline'], h['hit_model']))
print('  ' + ' '.join('%s %.2f/%.2f' % (c[6:], v['actual'] * 100, v['pred'] * 100) for c, v in h['cells'].items()))
for c in ('İY/MS 1/2', 'İY/MS 2/1'): print('  ', c, {k: round(v, 4) for k, v in h[c].items()})
s = a['score']; print('Skor LL %.4f top1 %.3f top3 %.3f | İY skor LL %.4f' % (s['model'], s['top1'], s['top3'], s['ht_model']))
for k, v in a['means'].items(): print('  ort', k, [round(x, 3) for x in v] if v else v)
print('BANKO', {k: v for k, v in res['banko']['all'].items() if not isinstance(v, dict)})
for k, v in res['banko']['by_band'].items(): print('   band', k, v['n'], round(v['pred'], 3), round(v['hit'], 3))
print('SÜRPRİZ', {k: v for k, v in res['surpriz']['all'].items() if not isinstance(v, dict)})
for k, v in res['surpriz']['by_market'].items(): print('   ', k, v['n'], 'p %.3f hit %.3f base %.3f' % (v['pred'], v['hit'], v['base']))
six = ['T1', 'E0', 'SP1', 'I1', 'D1', 'F1']
b6 = Bk[Bk['div'].isin(six)]; s6 = Sp[Sp['div'].isin(six)]
print('6 eski lig: banko n %d pred %.3f hit %.3f | sürpriz n %d pred %.3f hit %.3f' % (len(b6), b6.p.mean(), b6.hit.mean(), len(s6), s6.p.mean(), s6.hit.mean()))
print(pd.DataFrame({d: {'n': v['n'], 'ms': v['ms']['model'], 'ms365': v['ms']['bet365'], 'banko_hit': res['banko']['by_div'].get(d, {}).get('hit'),
                        'banko_p': res['banko']['by_div'].get(d, {}).get('pred'), 'banko_n': res['banko']['by_div'].get(d, {}).get('n'),
                        'sur_hit': res['surpriz']['by_div'].get(d, {}).get('hit'), 'sur_p': res['surpriz']['by_div'].get(d, {}).get('pred')} for d, v in BD.items()}).T.round(3).to_string())
for k, v in res['betting'].items(): print('BET', k, {a_: round(b_, 3) for a_, b_ in v.items()})
