"""Transparent pick log. Three append-only files, rows are never edited or deleted:
  state/picks.csv    one row per locked pick (BANKO / SÜRPRİZ), frozen 48 hours before kick-off with its model inputs
  state/odds.csv     odds observed for the pick: 'ilk' = first prices seen after locking (used for ROI), 'kapanış' = last before kick-off
  state/results.csv  settlement from football-data.co.uk results (half-time, full-time, corners)
Qualification rules live in markets.py and are covered by the formula lock."""
import csv, os, datetime as dt
import numpy as np, pandas as pd
from markets import market_outcomes

UTC = dt.timezone.utc
LOCK_HOURS = 48
PICK_COLS = ['id', 'kilit_utc', 'div', 'lig', 'sezon', 'baslama_utc', 'tarih_tsi', 'saat_tsi', 'ev', 'deplasman', 'ev_ad', 'dep_ad',
             'tur', 'pazar', 'olasilik', 'olagan', 'kat', 'lh', 'la', 'ch', 'ca', 'c_avg', 's1h', 's1a']
ODDS_COLS = ['id', 'gozlem_utc', 'tip', 'kaynak', 'b365', 'pinnacle', 'en_iyi', 'ortalama']
RES_COLS = ['id', 'sonuc_utc', 'hg', 'ag', 'hthg', 'htag', 'hc', 'ac', 'durum']
MARKET_ODDS_KEY = {'MS 1': '1', 'Sürpriz MS 1': '1', 'MS X': 'X', 'MS 2': '2', 'Sürpriz MS 2': '2',
                   '2.5 Üst': 'Ü2.5', '2.5 Alt': 'A2.5', '1.5 Üst': 'Ü1.5', '1.5 Alt': 'A1.5', '3.5 Üst': 'Ü3.5', '3.5 Alt': 'A3.5'}
FT_ONLY = {'MS 1', 'MS X', 'MS 2', 'Sürpriz MS 1', 'Sürpriz MS 2', 'ÇŞ 1X', 'ÇŞ X2', 'ÇŞ 12', 'KG Var', 'KG Yok',
           '1.5 Üst', '1.5 Alt', '2.5 Üst', '2.5 Alt', '3.5 Üst', '3.5 Alt', '4.5 Üst', '4.5 Alt'}


def _read(path, cols):
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        return pd.DataFrame(columns=cols)
    return pd.read_csv(path, dtype={'id': str})


def _append(path, cols, rows):
    if not rows:
        return
    new = not os.path.exists(path) or os.path.getsize(path) == 0
    with open(path, 'a', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction='ignore')
        if new:
            w.writeheader()
        w.writerows(rows)


class PickLog:
    def __init__(self, state_dir):
        self.dir = state_dir
        os.makedirs(state_dir, exist_ok=True)
        self.p_path, self.o_path, self.r_path = (os.path.join(state_dir, n) for n in ('picks.csv', 'odds.csv', 'results.csv'))
        self.picks = _read(self.p_path, PICK_COLS); self.odds = _read(self.o_path, ODDS_COLS); self.res = _read(self.r_path, RES_COLS)
        self.new_rows = {'picks': 0, 'odds': 0, 'results': 0}

    @staticmethod
    def fixture_id(f):
        return f"{f['season']}|{f['div']}|{f['home']}|{f['away']}"

    def locked_for(self, fid):
        if self.picks.empty:
            return []
        m = self.picks[self.picks.id.str.startswith(fid + '|')]
        return m.to_dict('records')

    # ------------------------------------------------------------------ lock
    def lock(self, fixtures, now, league_names):
        rows = []
        for f in fixtures:
            if f.get('state') != 'pre' or not f.get('pred'):
                continue
            ko = dt.datetime.fromisoformat(f['kickoff'])
            hours = (ko - now).total_seconds() / 3600
            fid = self.fixture_id(f)
            if not (0 < hours <= LOCK_HOURS) or self.locked_for(fid):
                continue
            p = f['pred']
            for typ, pk in (('BANKO', p.get('banko')), ('SÜRPRİZ', p.get('surpriz'))):
                if not pk:
                    continue
                rows.append({'id': f'{fid}|{typ}', 'kilit_utc': now.isoformat(timespec='seconds'), 'div': f['div'], 'lig': league_names[f['div']],
                             'sezon': f['season'], 'baslama_utc': f['kickoff'], 'tarih_tsi': f['date_tr'], 'saat_tsi': f['time_tr'],
                             'ev': f['home'], 'deplasman': f['away'], 'ev_ad': f['home_name'], 'dep_ad': f['away_name'],
                             'tur': typ, 'pazar': pk[0], 'olasilik': round(float(pk[1]), 6),
                             'olagan': round(float(f['base'].get(pk[0], np.nan)), 6) if typ == 'SÜRPRİZ' and pk[0] in f['base'] else '',
                             'kat': round(float(pk[2]), 4) if typ == 'SÜRPRİZ' else '',
                             **{k: round(float(p['inputs'][k]), 10) for k in ('lh', 'la', 'ch', 'ca', 'c_avg', 's1h', 's1a')}})
        _append(self.p_path, PICK_COLS, rows)
        if rows:
            self.picks = pd.concat([self.picks, pd.DataFrame(rows)], ignore_index=True)
        self.new_rows['picks'] += len(rows)
        return rows

    # ------------------------------------------------------------------ odds
    def observe_odds(self, fixtures, now):
        """'ilk' row the first time prices exist after locking (before kick-off); 'kapanış' row once, after kick-off,
        with the last prices seen before it."""
        rows = []
        have = set(zip(self.odds.id, self.odds.tip)) if not self.odds.empty else set()
        for f in fixtures:
            fid = self.fixture_id(f)
            for p in self.locked_for(fid):
                k = MARKET_ODDS_KEY.get(p['pazar'])
                if not k:
                    continue
                pre = f.get('state') == 'pre' and dt.datetime.fromisoformat(f['kickoff']) > now
                src = f.get('odds_last') if not pre else f.get('odds')
                if not src:
                    continue
                vals = {b: (src.get(b) or {}).get(k) for b in ('b365', 'pin', 'max', 'avg')}
                if not any(vals.values()):
                    continue
                tip = 'ilk' if pre else 'kapanış'
                if (p['id'], tip) in have or (tip == 'kapanış' and (p['id'], 'ilk') not in have):
                    continue
                rows.append({'id': p['id'], 'gozlem_utc': (src.get('_seen') or now.isoformat(timespec='seconds')), 'tip': tip,
                             'kaynak': src.get('_source', ''), 'b365': vals['b365'] or '', 'pinnacle': vals['pin'] or '',
                             'en_iyi': vals['max'] or '', 'ortalama': vals['avg'] or ''})
                have.add((p['id'], tip))
        _append(self.o_path, ODDS_COLS, rows)
        if rows:
            self.odds = pd.concat([self.odds, pd.DataFrame(rows)], ignore_index=True)
        self.new_rows['odds'] += len(rows)
        return rows

    # ------------------------------------------------------------------ settle
    def settle(self, D, now):
        """Settle locked picks whose match is in the football-data results."""
        if self.picks.empty:
            return []
        done = set(self.res.id) if not self.res.empty else set()
        idx = {(r.div, int(r.season), r.home, r.away): r for r in D.itertuples()}
        rows = []
        for p in self.picks.to_dict('records'):
            if p['id'] in done:
                continue
            r = idx.get((p['div'], int(p['sezon']), p['ev'], p['deplasman']))
            if r is None:
                continue
            full = r.fit_ok
            if not full and p['pazar'] not in FT_ONLY:
                durum = 'Doğrulanamadı'
                o = None
            else:
                hthg = int(r.hthg) if full else 0; htag = int(r.htag) if full else 0
                hc = int(r.hc) if full else 0; ac = int(r.ac) if full else 0
                o = market_outcomes(int(r.hg), int(r.ag), hthg, htag, hc, ac)
                o['Sürpriz MS 1'] = o['MS 1']; o['Sürpriz MS 2'] = o['MS 2']
                durum = 'Tuttu' if o.get(p['pazar']) else 'Tutmadı'
            rows.append({'id': p['id'], 'sonuc_utc': now.isoformat(timespec='seconds'), 'hg': int(r.hg), 'ag': int(r.ag),
                         'hthg': '' if pd.isna(r.hthg) else int(r.hthg), 'htag': '' if pd.isna(r.htag) else int(r.htag),
                         'hc': '' if pd.isna(r.hc) else int(r.hc), 'ac': '' if pd.isna(r.ac) else int(r.ac), 'durum': durum})
        _append(self.r_path, RES_COLS, rows)
        if rows:
            self.res = pd.concat([self.res, pd.DataFrame(rows)], ignore_index=True)
        self.new_rows['results'] += len(rows)
        return rows

    # ------------------------------------------------------------------ performance
    def table(self):
        P = self.picks.copy()
        if P.empty:
            return P
        first = self.odds[self.odds.tip == 'ilk'].drop_duplicates('id') if not self.odds.empty else pd.DataFrame(columns=ODDS_COLS)
        close = self.odds[self.odds.tip == 'kapanış'].drop_duplicates('id') if not self.odds.empty else pd.DataFrame(columns=ODDS_COLS)
        P = P.merge(first[['id', 'gozlem_utc', 'kaynak', 'b365', 'pinnacle', 'en_iyi', 'ortalama']], on='id', how='left')
        P = P.merge(close[['id', 'b365', 'en_iyi']].rename(columns={'b365': 'kap_b365', 'en_iyi': 'kap_en_iyi'}), on='id', how='left')
        R = self.res.drop_duplicates('id') if not self.res.empty else pd.DataFrame(columns=RES_COLS)
        P = P.merge(R, on='id', how='left')
        for c in ('b365', 'pinnacle', 'en_iyi', 'ortalama', 'kap_b365', 'kap_en_iyi', 'olasilik'):
            P[c] = pd.to_numeric(P[c], errors='coerce')
        for book, col in (('b365', 'net_b365'), ('en_iyi', 'net_en_iyi')):
            P[col] = np.where(P.durum == 'Tuttu', P[book] - 1, np.where(P.durum == 'Tutmadı', -1.0, np.nan))
            P.loc[P[book].isna(), col] = np.nan
        return P.sort_values(['baslama_utc', 'id'], kind='stable').reset_index(drop=True)

    def performance(self, now):
        T = self.table()
        out = {'n_locked': int(len(T))}
        if T.empty:
            return out, T
        ko = pd.to_datetime(T.baslama_utc, utc=True)
        T['bekliyor'] = T.durum.isna() & (ko < now)
        T['gecikmeli'] = T.durum.isna() & (ko < now - pd.Timedelta(days=4))

        def summ(d):
            s = d[d.durum.isin(['Tuttu', 'Tutmadı'])]
            r = {'n': int(len(d)), 'sonuclanan': int(len(s)), 'tuttu': int((s.durum == 'Tuttu').sum()),
                 'isabet': float((s.durum == 'Tuttu').mean()) if len(s) else None, 'beklenen': float(s.olasilik.mean()) if len(s) else None,
                 'bekliyor': int(d.bekliyor.sum()), 'gecikmeli': int(d.gecikmeli.sum()), 'dogrulanamadi': int((d.durum == 'Doğrulanamadı').sum())}
            for col in ('net_b365', 'net_en_iyi'):
                e = d[d[col].notna()]
                if len(e):
                    cum = e[col].cumsum().values
                    r[col] = {'n': int(len(e)), 'birim': float(e[col].sum()), 'roi': float(e[col].mean()),
                              'max_dusus': float((np.maximum.accumulate(np.concatenate([[0], cum]))[1:] - cum).max())}
            return r
        out['all'] = summ(T)
        out['by_type'] = {t: summ(g) for t, g in T.groupby('tur')}
        out['by_div'] = {d: summ(g) for d, g in T.groupby('div')}
        s = T[T.durum.notna()].tail(40)
        out['recent'] = [{k: (None if (isinstance(v, float) and np.isnan(v)) else v) for k, v in r.items()} for r in s[
            ['tarih_tsi', 'lig', 'ev_ad', 'dep_ad', 'tur', 'pazar', 'olasilik', 'b365', 'en_iyi', 'durum', 'hg', 'ag', 'hthg', 'htag', 'hc', 'ac']].to_dict('records')]
        out['first_lock'] = str(T.kilit_utc.min()); out['missing_odds'] = int(T.en_iyi.isna().sum())
        return out, T
