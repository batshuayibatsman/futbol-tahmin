"""v2 ek ligler: banko / sürpriz ve maç sonu pazarları, 2024 sezonu (arşivin sonu: Aralık 2024).
Gol beklentisi oranlardan (1X2; toplam gol istatistikten), devre/İY pazarları gösterilmez. Lig sıklıkları 2021-23'ten.
Kullanım: python research/v2/extra_eval.py  ->  out/extra_base_rates.json, out/extra_backtest.json"""
import json, sys
sys.path.insert(0, 'tahmin')
import numpy as np, pandas as pd
from probs import predict_all
from markets import market_probs, market_outcomes, pick_banko, pick_surprise, base_rates

cal = json.load(open('data/frozen/cal_val.json'))
P = pd.read_csv('out/wf_extra.csv', parse_dates=['date'])
P['lh'] = P['mh_']; P['la'] = P['ma_']; P['ht'] = False
P['hthg'] = np.nan; P['htag'] = np.nan
V = P[P.season.isin([2021, 2022, 2023])].copy(); T = P[P.season == 2024].copy()
Qv = predict_all(V, cal); Qt = predict_all(T, cal)
nz = lambda x: None if x != x else x
base = {d: base_rates([market_outcomes(int(r.hg), int(r.ag), None, None, None, None, r.p1, r.p2) for r in V.join(Qv[['p1', 'p2']])[V['div'] == d].itertuples()])
        for d in sorted(V['div'].unique())}
TT = T.join(Qt, rsuffix='_q')
recs = []
for r in TT.to_dict('records'):
    m = market_probs(r); o = market_outcomes(int(r['hg']), int(r['ag']), None, None, None, None, r['p1'], r['p2'])
    bk = pick_banko(m); sp = pick_surprise(m, base[r['div']])
    if bk: recs.append({'type': 'banko', 'div': r['div'], 'market': bk[0], 'p': bk[1], 'hit': bool(o[bk[0]])})
    if sp: recs.append({'type': 'surpriz', 'div': r['div'], 'market': sp[0], 'p': sp[1], 'hit': bool(o[sp[0]]), 'base': base[r['div']][sp[0]]})
R = pd.DataFrame(recs)
y = np.where(TT.hg > TT.ag, 0, np.where(TT.hg == TT.ag, 1, 2))
pm = TT[['p1', 'px', 'p2']].values; io = 1 / TT[['oh', 'od', 'oa']].values; mk = io / io.sum(1, keepdims=True)
B = R[R.type == 'banko']; S = R[R.type == 'surpriz']
out = {'test_season': '2024 (Aralık 2024a kadar)', 'n': int(len(TT)), 'n_leagues': int(TT['div'].nunique()),
       'ms': {'model': float(-np.log(pm[np.arange(len(y)), y]).mean()), 'odds': float(-np.log(mk[np.arange(len(y)), y]).mean())},
       'banko': {'n': int(len(B)), 'pred': float(B.p.mean()), 'hit': float(B.hit.mean())},
       'surpriz': {'n': int(len(S)), 'pred': float(S.p.mean()), 'hit': float(S.hit.mean()), 'base': float(S.base.mean())},
       'by_div': {d: {'n': int((TT['div'] == d).sum()), 'banko_hit': float(g[g.type == 'banko'].hit.mean()), 'banko_p': float(g[g.type == 'banko'].p.mean())}
                  for d, g in R.groupby('div')}}
json.dump(base, open('out/extra_base_rates.json', 'w'), indent=1, ensure_ascii=False)
json.dump(out, open('out/extra_backtest.json', 'w'), indent=1, ensure_ascii=False)
print(json.dumps({k: v for k, v in out.items() if k != 'by_div'}, ensure_ascii=False))
print(B.groupby('market').agg(n=('p', 'size'), p=('p', 'mean'), hit=('hit', 'mean')).round(3).to_string())
print(S.groupby('market').agg(n=('p', 'size'), p=('p', 'mean'), hit=('hit', 'mean'), base=('base', 'mean')).round(3).to_string())
