"""v2 (Kasım 2026): 22 ligin temiz maç tablosu, GitHub aynasından (xgabora/Club-Football-Match-Data, football-data.co.uk
verisinin aynısı; takım adlarının football-data 2026-27 dosyalarıyla birebir aynı olduğu kontrol edildi).
v1 kuralları: hiçbir satır sessizce silinmez; her düzeltme rapora yazılır.
Kullanım: python research/v2/build.py <Matches.csv>   ->  out/matches22.csv, out/audit22.json, data/history.csv"""
import json, sys
import numpy as np, pandas as pd

L22 = ['E0', 'E1', 'E2', 'E3', 'EC', 'SC0', 'SC1', 'SC2', 'SC3', 'D1', 'D2', 'I1', 'I2', 'SP1', 'SP2',
       'F1', 'F2', 'N1', 'B1', 'P1', 'T1', 'G1']
REN = {'Division': 'div', 'HomeTeam': 'home', 'AwayTeam': 'away', 'FTHome': 'hg', 'FTAway': 'ag', 'HTHome': 'hthg',
       'HTAway': 'htag', 'HomeCorners': 'hc', 'AwayCorners': 'ac', 'OddHome': 'oh', 'OddDraw': 'od', 'OddAway': 'oa',
       'MaxHome': 'mh', 'MaxDraw': 'md', 'MaxAway': 'ma', 'Over25': 'o25', 'Under25': 'u25'}
KEEP = ['div', 'date', 'home', 'away', 'hg', 'ag', 'hthg', 'htag', 'hc', 'ac', 'oh', 'od', 'oa', 'mh', 'md', 'ma', 'o25', 'u25']
NUM = ['hg', 'ag', 'hthg', 'htag', 'hc', 'ac']

X = pd.read_csv(sys.argv[1], low_memory=False)
X = X[X.Division.isin(L22)].copy()
X['date'] = pd.to_datetime(X['MatchDate'], errors='coerce')
rep = {'rows_mirror_22': int(len(X)), 'issues': [], 'by_div': {}}
bad = X.date.isna()
rep['issues'].append({'what': 'unparseable date (excluded)', 'n': int(bad.sum())})
X = X[~bad].rename(columns=REN)[KEEP]
X = X[(X.date >= '2015-07-01') & (X.date < '2026-07-01')].copy()   # complete seasons 2015-16 .. 2025-26
for c in NUM:
    X[c] = pd.to_numeric(X[c], errors='coerce')
y = X.date.dt.year; m = X.date.dt.month
X['season'] = np.where(m >= 7, y, y - 1)
X.loc[(X.date >= '2020-07-01') & (X.date < '2020-08-15'), 'season'] = 2019     # covid-delayed end of 2019-20
dup = X.duplicated(['div', 'date', 'home', 'away'], keep='first')
rep['issues'].append({'what': 'exact duplicate fixtures, first copy kept', 'n': int(dup.sum())})
X = X[~dup]
hb = (X.hthg > X.hg) | (X.htag > X.ag)
rep['issues'].append({'what': 'half-time score above full-time score: HT set to missing', 'n': int(hb.sum()),
                      'rows': X.loc[hb, ['div', 'date', 'home', 'away']].astype(str).values.tolist()[:20]})
X.loc[hb, ['hthg', 'htag']] = np.nan
X['has_ft'] = X.hg.notna() & X.ag.notna()
X['has_ht'] = X.hthg.notna() & X.htag.notna()
X['has_c'] = X.hc.notna() & X.ac.notna()
nf = ~X.has_ft
rep['issues'].append({'what': 'no full-time score (excluded)', 'n': int(nf.sum())})
X = X[X.has_ft]
aw = ~X.has_ht
rep['issues'].append({'what': 'score without half-time score (awarded/administrative results): kept, not used for fitting',
                      'n': int(aw.sum()), 'by_div': {k: int(v) for k, v in X[aw].groupby('div').size().items()}})
X['fit_ok'] = X.has_ht                      # goals model: full-time + half-time score
X['fit_c'] = X.has_ht & X.has_c             # corners model
X = X.sort_values(['date', 'div', 'home'], kind='stable').reset_index(drop=True)
for d, g in X[X.season >= 2017].groupby('div'):
    rep['by_div'][d] = {'rows': int(len(g)), 'ht': round(float(g.has_ht.mean()), 4), 'corners': round(float(g.has_c.mean()), 4),
                        'odds_1x2': round(float(g.oh.notna().mean()), 4), 'odds_ou25': round(float(g.o25.notna().mean()), 4),
                        'first': str(g.date.min().date()), 'last': str(g.date.max().date())}
X.to_csv('out/matches22.csv', index=False)
H = X[X.date >= '2017-07-01'][KEEP].copy()
H['date'] = H.date.dt.strftime('%Y-%m-%d')
H.to_csv('data/history.csv', index=False)
rep['rows_out'] = int(len(X)); rep['history_rows'] = int(len(H))
json.dump(rep, open('out/audit22.json', 'w'), indent=1, default=str)
print(json.dumps({k: rep[k] for k in ('rows_mirror_22', 'rows_out', 'history_rows')}))
for i in rep['issues']:
    print(str(i)[:300])
print(pd.DataFrame(rep['by_div']).T.to_string())
