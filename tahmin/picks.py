"""Transparent pick log. Three append-only files, rows are never edited or deleted:
  state/picks.csv    one row per pick (BANKO / SÜRPRİZ): the pick the site showed at the LAST update before kick-off,
                     with its inputs; written at the first update after kick-off from state/pre_kickoff.json
                     (that file is committed at every update, so every pre-match pick is in the git history)
  state/odds.csv     the bookmaker prices seen at that same last pre-match update (used for ROI)
  state/results.csv  settlement from football-data.co.uk results (half-time, full-time, corners)
Qualification rules live in markets.py and are covered by the formula lock."""
import csv, os, datetime as dt
import numpy as np, pandas as pd
from markets import market_outcomes

UTC = dt.timezone.utc
from zoneinfo import ZoneInfo
TR = ZoneInfo('Europe/Istanbul')
PICK_COLS = ['id', 'kilit_utc', 'div', 'lig', 'sezon', 'baslama_utc', 'tarih_tsi', 'saat_tsi', 'ev', 'deplasman', 'ev_ad', 'dep_ad',
             'tur', 'pazar', 'olasilik', 'olagan', 'kat', 'lh', 'la', 'ch', 'ca', 'c_avg', 's1h', 's1a']
ODDS_COLS = ['id', 'gozlem_utc', 'tip', 'kaynak', 'b365', 'pinnacle', 'en_iyi', 'ortalama', 'draftkings']
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
        return f['fid']

    def locked_for(self, fid):
        if self.picks.empty:
            return []
        m = self.picks[self.picks.id.str.startswith(fid + '|')]
        return m.to_dict('records')

    # ------------------------------------------------------------------ record the last pre-match pick
    def finalize(self, pre, fixtures, now, league_names):
        """For every match that has kicked off, append the pick shown at the last update before kick-off.
        Postponed matches wait (their entry is kept until they are played)."""
        state = {f['fid']: f.get('state') for f in fixtures}
        have = set(self.picks.id) if not self.picks.empty else set()
        rows, orows = [], []
        for fid, e in sorted(pre.items()):
            ko = dt.datetime.fromisoformat(e['kickoff'])
            if ko > now or state.get(fid) == 'postponed' or not e.get('picks'):
                continue
            season, div, home, away = fid.split('|')[:4]
            ko_tr = ko.astimezone(TR)
            inp = e.get('inputs') or {}
            for typ in ('BANKO', 'SÜRPRİZ'):
                pk = e['picks'].get(typ)
                pid = f'{fid}|{typ}'
                if not pk or pid in have:
                    continue
                rows.append({'id': pid, 'kilit_utc': e.get('saved') or e['kickoff'], 'div': div, 'lig': league_names.get(div, div),
                             'sezon': int(season), 'baslama_utc': e['kickoff'], 'tarih_tsi': ko_tr.strftime('%Y-%m-%d'), 'saat_tsi': ko_tr.strftime('%H:%M'),
                             'ev': home, 'deplasman': away, 'ev_ad': e.get('home_name', home), 'dep_ad': e.get('away_name', away),
                             'tur': typ, 'pazar': pk[0], 'olasilik': round(float(pk[1]), 6),
                             'olagan': round(float(pk[3]), 6) if typ == 'SÜRPRİZ' and len(pk) > 3 and pk[3] is not None else '',
                             'kat': round(float(pk[2]), 4) if typ == 'SÜRPRİZ' else '',
                             **{k: ('' if inp.get(k) is None else round(float(inp[k]), 10)) for k in ('lh', 'la', 'ch', 'ca', 'c_avg', 's1h', 's1a')}})
                have.add(pid)
                k = MARKET_ODDS_KEY.get(pk[0]); src = e.get('odds_last') or {}
                if k and src:
                    vals = {b: (src.get(b) or {}).get(k) for b in ('b365', 'pin', 'max', 'avg', 'dk', 'b365e')}
                    best = max([v for v in vals.values() if v] or [None]) if any(vals.values()) else None
                    if best:
                        orows.append({'id': pid, 'gozlem_utc': src.get('_seen') or e.get('saved') or '', 'tip': 'maç öncesi son',
                                      'kaynak': src.get('_source', ''), 'b365': vals['b365'] or vals['b365e'] or '', 'pinnacle': vals['pin'] or '',
                                      'en_iyi': best, 'ortalama': vals['avg'] or '', 'draftkings': vals['dk'] or ''})
        _append(self.p_path, PICK_COLS, rows)
        _append(self.o_path, ODDS_COLS, orows)
        if rows:
            self.picks = pd.concat([self.picks, pd.DataFrame(rows)], ignore_index=True)
        if orows:
            self.odds = pd.concat([self.odds, pd.DataFrame(orows)], ignore_index=True)
        self.new_rows['picks'] += len(rows); self.new_rows['odds'] += len(orows)
        return rows

    def recorded_fids(self):
        return {i.rsplit('|', 1)[0] for i in self.picks.id} if not self.picks.empty else set()

    # ------------------------------------------------------------------ settle
    def settle(self, D, now):
        """Settle locked picks whose match is in the football-data results."""
        if self.picks.empty:
            return []
        done = set(self.res.id) if not self.res.empty else set()
        idx = {}
        for r in D.itertuples():               # the same pairing can be played more than once a season: match the date too
            idx.setdefault((r.div, r.home, r.away), []).append(r)
        rows = []
        for p in self.picks.to_dict('records'):
            if p['id'] in done:
                continue
            ko = pd.Timestamp(p['baslama_utc']).tz_convert(None).normalize()
            cand = [r for r in idx.get((p['div'], p['ev'], p['deplasman']), []) if abs((r.date - ko).days) <= 2]
            if not cand:
                continue
            r = min(cand, key=lambda x: abs((x.date - ko).days))
            full = r.fit_ok
            if not full and p['pazar'] not in FT_ONLY:
                durum = 'Doğrulanamadı'
                o = None
            else:
                hthg = int(r.hthg) if full else 0; htag = int(r.htag) if full else 0
                hc = None if pd.isna(r.hc) else int(r.hc); ac = None if pd.isna(r.ac) else int(r.ac)
                o = market_outcomes(int(r.hg), int(r.ag), hthg, htag, hc, ac)
                o['Sürpriz MS 1'] = o['MS 1']; o['Sürpriz MS 2'] = o['MS 2']
                durum = ('Tuttu' if o[p['pazar']] else 'Tutmadı') if p['pazar'] in o else 'Doğrulanamadı'
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
        O = self.odds.drop_duplicates('id') if not self.odds.empty else pd.DataFrame(columns=ODDS_COLS)
        if 'draftkings' not in O.columns:
            O['draftkings'] = np.nan
        P = P.merge(O[['id', 'gozlem_utc', 'kaynak', 'b365', 'pinnacle', 'en_iyi', 'ortalama', 'draftkings']], on='id', how='left')
        R = self.res.drop_duplicates('id') if not self.res.empty else pd.DataFrame(columns=RES_COLS)
        P = P.merge(R, on='id', how='left')
        for c in ('b365', 'pinnacle', 'en_iyi', 'ortalama', 'draftkings', 'olasilik'):
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
        out['first_pick'] = str(T.kilit_utc.min()); out['missing_odds'] = int(T.en_iyi.isna().sum())
        return out, T
