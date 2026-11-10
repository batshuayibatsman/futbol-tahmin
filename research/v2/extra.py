"""v2 ek ligler (Kasım 2026): 16 lig, yalnızca maç sonu skoru ve 1X2 oranı var (devre skoru, korner, alt/üst oranı yok).
Arşiv aynasından (2024 sonuna kadar): FT-only walk-forward takım güçleri, oran ağırlığı (yalnızca 2021-23'te seçilir),
lig sıklıkları ve 2024 sezonunda test. Kullanım: python research/v2/extra.py <Matches.csv>"""
import json, sys
sys.path.insert(0, 'tahmin'); sys.path.insert(0, 'research/v2')
import numpy as np, pandas as pd
from multiprocessing import Pool
from model import walk_forward
from config import CFG
from market import implied_means
from blend import blend, score_nll, hda

M2F = {'ARG': 'ARG', 'AUT': 'AUT', 'BRA': 'BRA', 'CHN': 'CHN', 'DEN': 'DNK', 'FIN': 'FIN', 'IRL': 'IRL', 'JAP': 'JPN', 'MEX': 'MEX',
       'NOR': 'NOR', 'POL': 'POL', 'ROM': 'ROU', 'RUS': 'RUS', 'SWE': 'SWE', 'SUI': 'SWZ', 'USA': 'USA'}
CALENDAR = {'ARG', 'BRA', 'CHN', 'FIN', 'IRL', 'JPN', 'NOR', 'SWE', 'USA'}      # seasons run within a calendar year (to 2025)
VAL, TEST = [2021, 2022, 2023], [2024]


def load(path):
    X = pd.read_csv(path, low_memory=False)
    X = X[X.Division.isin(M2F)].copy()
    X['div'] = X.Division.map(M2F)
    X['date'] = pd.to_datetime(X.MatchDate, errors='coerce')
    X = X.rename(columns={'HomeTeam': 'home', 'AwayTeam': 'away', 'FTHome': 'hg', 'FTAway': 'ag', 'OddHome': 'oh', 'OddDraw': 'od', 'OddAway': 'oa'})
    X = X[X.date.notna() & X.hg.notna() & X.ag.notna() & (X.date >= '2016-01-01')].copy()
    y, m = X.date.dt.year, X.date.dt.month
    X['season'] = np.where(X['div'].isin(CALENDAR), y, np.where(m >= 7, y, y - 1))
    for c in ('hthg', 'htag', 'hc', 'ac'):
        X[c] = np.nan
    X['fit_ok'] = True; X['fit_c'] = False
    X = X.drop_duplicates(['div', 'date', 'home', 'away']).sort_values(['date', 'div', 'home'], kind='stable').reset_index(drop=True)
    return X[['div', 'date', 'season', 'home', 'away', 'hg', 'ag', 'hthg', 'htag', 'hc', 'ac', 'oh', 'od', 'oa', 'fit_ok', 'fit_c']]


def run(args):
    d, df = args
    return walk_forward(df, CFG, VAL + TEST)


if __name__ == '__main__':
    if '--reuse' in sys.argv:                      # skip the walk-forward and the odds inversion (out/wf_extra.csv)
        P = pd.read_csv('out/wf_extra.csv', parse_dates=['date'])
    else:
        X = load(sys.argv[1])
        print(X.groupby(['div', 'season']).size().unstack().loc[:, 2019:].to_string())
        with Pool(2) as p:
            parts = p.map(run, [(d, X[X['div'] == d]) for d in sorted(X['div'].unique())])
        P = pd.concat(parts).reset_index(drop=True)
        P = P[(P.oh > 1) & (P.od > 1) & (P.oa > 1)].copy()
        mm = [implied_means(r.oh, r.od, r.oa) for r in P.itertuples()]     # 1X2 only: total from the draw price (draw_total.py)
        P['mh_'] = [a for a, _ in mm]; P['ma_'] = [b for _, b in mm]
        P.to_csv('out/wf_extra.csv', index=False)
    V = P[P.season.isin(VAL)]; T = P[P.season.isin(TEST)]
    grid = np.round(np.arange(0, 1.0001, 0.1), 2)
    res = {(wr, wt): float(score_nll(*blend(V.lh.values, V.la.values, V.mh_.values, V.ma_.values, wr, wt), V.hg.values, V.ag.values).mean())
           for wr in grid for wt in grid}
    best = min(res, key=res.get)
    print('VAL n=%d  model %.5f  odds only %.5f  best (wr, wt)=%s %.5f' % (len(V), res[(0.0, 0.0)], res[(1.0, 1.0)], best, res[best]))
    out = {'val_n': int(len(V)), 'test_n': int(len(T)), 'best': {'wr': float(best[0]), 'wt': float(best[1])}, 'test': {}}
    for name, (wr, wt) in (('model', (0.0, 0.0)), ('oran', (1.0, 1.0)), ('best', best)):
        bh, ba = blend(T.lh.values, T.la.values, T.mh_.values, T.ma_.values, wr, wt)
        h, dd, a = hda(bh, ba); r = np.where(T.hg > T.ag, h, np.where(T.hg == T.ag, dd, a))
        out['test'][name] = {'score_nll': float(score_nll(bh, ba, T.hg.values, T.ag.values).mean()), '1x2_logloss': float(-np.log(r).mean())}
        print('TEST', name, {k: round(v, 5) for k, v in out['test'][name].items()})
    rows = []
    for d, S in T.groupby('div'):
        a = score_nll(S.lh.values, S.la.values, S.hg.values, S.ag.values).mean()
        bh, ba = blend(S.lh.values, S.la.values, S.mh_.values, S.ma_.values, 1.0, 1.0)
        rows.append((d, len(S), round(a, 4), round(score_nll(bh, ba, S.hg.values, S.ag.values).mean(), 4)))
    print(pd.DataFrame(rows, columns=['div', 'n', 'score_model', 'score_oran']).to_string(index=False))
    json.dump(out, open('out/extra_blend.json', 'w'), indent=1)
