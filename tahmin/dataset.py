"""Match table for the model: frozen history (2017-18..2025-26) + season snapshots refreshed from football-data.co.uk.
Same rules as the research audit: nothing is deleted silently; every exclusion is counted and listed."""
import glob, os
import numpy as np, pandas as pd

NUM = ['hg', 'ag', 'hthg', 'htag', 'hc', 'ac']


def season_of(dates):
    y = dates.dt.year; m = dates.dt.month
    s = np.where(m >= 7, y, y - 1)
    covid = (dates >= '2020-07-01') & (dates < '2020-08-15')
    return np.where(covid, 2019, s)


def load(root, today):
    parts = [pd.read_csv(os.path.join(root, 'data', 'history.csv'))]
    parts[0]['src'] = 'arşiv'
    for p in sorted(glob.glob(os.path.join(root, 'data', 'seasons', '*', '*.csv'))):
        s = pd.read_csv(p)
        if len(s):
            s['src'] = 'football-data ' + os.path.basename(os.path.dirname(p))
            parts.append(s)
    D = pd.concat(parts, ignore_index=True)
    D['date'] = pd.to_datetime(D['date'], errors='coerce')
    audit = {'rows_in': int(len(D)), 'issues': []}
    bad = D.date.isna()
    if bad.any():
        audit['issues'].append({'tür': 'okunamayan tarih', 'n': int(bad.sum()), 'işlem': 'modelden çıkarıldı'})
    fut = D.date > pd.Timestamp(today)
    if fut.any():
        audit['issues'].append({'tür': 'gelecek tarihli sonuç', 'n': int(fut.sum()), 'işlem': 'modelden çıkarıldı'})
    D = D[~bad & ~fut].copy()
    for c in NUM:
        D[c] = pd.to_numeric(D[c], errors='coerce')
    dup = D.duplicated(['div', 'date', 'home', 'away'], keep='last')
    if dup.any():
        audit['issues'].append({'tür': 'yinelenen maç', 'n': int(dup.sum()), 'işlem': 'son kopya tutuldu',
                                'örnek': D.loc[dup, ['div', 'date', 'home', 'away']].astype(str).values.tolist()[:5]})
        D = D[~dup]
    D['season'] = season_of(D.date)
    htft = (D.hthg > D.hg) | (D.htag > D.ag)
    if htft.any():
        audit['issues'].append({'tür': 'devre skoru maç sonundan büyük', 'n': int(htft.sum()), 'işlem': 'devre skoru boş bırakıldı',
                                'örnek': D.loc[htft, ['div', 'date', 'home', 'away']].astype(str).values.tolist()[:5]})
        D.loc[htft, ['hthg', 'htag']] = np.nan
    D['has_ft'] = D.hg.notna() & D.ag.notna()
    D['fit_ok'] = D[NUM].notna().all(axis=1)
    nf = ~D.has_ft
    if nf.any():
        audit['issues'].append({'tür': 'skor yok', 'n': int(nf.sum()), 'işlem': 'modelden çıkarıldı'})
    aw = D.has_ft & ~D.fit_ok
    if aw.any():
        audit['issues'].append({'tür': 'devre skoru/korner eksik (hükmen ya da eksik istatistik)', 'n': int(aw.sum()), 'işlem': 'tutuldu, modelde kullanılmadı',
                                'örnek': D.loc[aw & (D.date >= '2025-07-01'), ['div', 'date', 'home', 'away']].astype(str).values.tolist()[:5]})
    D = D[D.has_ft].sort_values(['date', 'div', 'home'], kind='stable').reset_index(drop=True)
    audit['rows_out'] = int(len(D))
    audit['fit_rows'] = int(D.fit_ok.sum())
    return D, audit
