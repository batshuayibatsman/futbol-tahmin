"""Data sources, fetched only by the scheduled job (never by visitors' browsers, except ESPN live scores when allowed).
- football-data.co.uk: season results with half-time score and corners; next-round fixtures with bookmaker odds.
- ESPN (unofficial public JSON): fixtures for the next 8 days, live status and scores.
- The Odds API (optional, needs the free ODDS_API_KEY secret): fresher 1X2 and total-goals odds, with a monthly credit budget.
Every request goes through Http: on-disk cache, minimum refresh interval per source, conditional requests,
a per-run request cap, retries, and a status record that the page shows."""
import csv, io, json, os, time, urllib.request, urllib.error, datetime as dt
from pathlib import Path

UTC = dt.timezone.utc
UA = 'futbol-tahmin/1.0 (kisisel tahmin sitesi; GitHub Actions)'

LEAGUES = {
    'T1': {'name': 'Süper Lig', 'espn': 'tur.1', 'odds': 'soccer_turkey_super_league'},
    'E0': {'name': 'Premier Lig', 'espn': 'eng.1', 'odds': 'soccer_epl'},
    'SP1': {'name': 'La Liga', 'espn': 'esp.1', 'odds': 'soccer_spain_la_liga'},
    'I1': {'name': 'Serie A', 'espn': 'ita.1', 'odds': 'soccer_italy_serie_a'},
    'D1': {'name': 'Bundesliga', 'espn': 'ger.1', 'odds': 'soccer_germany_bundesliga'},
    'F1': {'name': 'Ligue 1', 'espn': 'fra.1', 'odds': 'soccer_france_ligue_one'},
}
FD_SEASON = 'https://www.football-data.co.uk/mmz4281/{code}/{div}.csv'
FD_FIXTURES = 'https://www.football-data.co.uk/fixtures.csv'
ESPN = 'https://site.api.espn.com/apis/site/v2/sports/soccer/{slug}/scoreboard?dates={d0}-{d1}&limit=200'
ODDS_API = 'https://api.the-odds-api.com/v4/sports/{sport}/odds/?apiKey={key}&regions=eu&markets=h2h,totals&oddsFormat=decimal&dateFormat=iso'
PER_RUN_CAP = {'football-data.co.uk': 10, 'site.api.espn.com': 8, 'api.the-odds-api.com': 6}


def now_utc():
    return dt.datetime.now(UTC)


class Http:
    def __init__(self, cache_dir, state, offline=False, force=False):
        self.dir = Path(cache_dir); self.dir.mkdir(parents=True, exist_ok=True)
        self.state = state.setdefault('http', {})
        self.offline, self.force = offline, force
        self.used = {}
        self.log = []

    def _host(self, url):
        return url.split('/')[2]

    def get(self, key, url, min_interval_min, conditional=True, headers=None, redact=None):
        """Returns (bytes or None, info dict). Never raises."""
        meta = self.state.setdefault(key, {})
        path = self.dir / (key.replace('/', '_') + '.bin')
        have = path.exists()
        age = (time.time() - meta.get('checked', 0)) / 60
        shown = url if not redact else url.replace(redact, '***')
        info = {'key': key, 'url': shown}
        if self.offline or (have and not self.force and age < min_interval_min):
            info['action'] = 'önbellek' if have else 'yok'
            self.log.append(info)
            return (path.read_bytes() if have else None), info
        host = self._host(url)
        if self.used.get(host, 0) >= PER_RUN_CAP.get(host, 5):
            info['action'] = 'sınır'; self.log.append(info)
            return (path.read_bytes() if have else None), info
        self.used[host] = self.used.get(host, 0) + 1
        h = {'User-Agent': UA, 'Accept-Encoding': 'identity'}
        if headers:
            h.update(headers)
        if conditional and have and not self.force:
            if meta.get('etag'):
                h['If-None-Match'] = meta['etag']
            if meta.get('last_modified'):
                h['If-Modified-Since'] = meta['last_modified']
        err = None
        for k in range(3):
            try:
                req = urllib.request.Request(url, headers=h)
                with urllib.request.urlopen(req, timeout=60) as r:
                    data = r.read(); hdr = {a.lower(): b for a, b in r.headers.items()}
                if len(data) < 20:
                    raise RuntimeError('boş yanıt')
                tmp = path.with_suffix('.part'); tmp.write_bytes(data); tmp.replace(path)
                meta.update(checked=time.time(), ok=time.time(), status=200, etag=hdr.get('etag'), last_modified=hdr.get('last-modified'), error=None)
                info.update(action='indirildi', bytes=len(data), headers={a: hdr[a] for a in hdr if a.startswith('x-requests') or a == 'access-control-allow-origin'})
                self.log.append(info)
                return data, info
            except urllib.error.HTTPError as e:
                if e.code == 304:
                    meta.update(checked=time.time(), ok=time.time(), status=304, error=None)
                    info['action'] = 'değişmedi'; self.log.append(info)
                    return path.read_bytes(), info
                err = f'HTTP {e.code}'
                if e.code in (401, 403, 404, 429):
                    break
            except Exception as e:
                err = str(e)[:160]
            time.sleep(2 + 3 * k)
        meta.update(checked=time.time(), error=err, status='hata')
        info.update(action='hata', error=err); self.log.append(info)
        return (path.read_bytes() if have else None), info


# ---------------------------------------------------------------- football-data.co.uk
def _rows(b):
    for enc in ('utf-8-sig', 'cp1252', 'latin-1'):
        try:
            return list(csv.DictReader(io.StringIO(b.decode(enc))))
        except UnicodeDecodeError:
            continue
    return []


def _date(s):
    s = (s or '').strip()
    for f in ('%d/%m/%Y', '%d/%m/%y', '%Y-%m-%d'):
        try:
            return dt.datetime.strptime(s, f).date()
        except ValueError:
            pass
    return None


def _num(r, *keys):
    for k in keys:
        v = (r.get(k) or '').strip()
        if v:
            try:
                return float(v)
            except ValueError:
                return None
    return None


def season_code(d):
    y = d.year if d.month >= 7 else d.year - 1
    return f'{y % 100:02d}{(y + 1) % 100:02d}'


STD = ['div', 'date', 'time', 'home', 'away', 'hg', 'ag', 'hthg', 'htag', 'hc', 'ac', 'oh', 'od', 'oa', 'mh', 'md', 'ma', 'o25', 'u25']


def parse_fd_season(div, b, today, alerts):
    """Standardised rows of a football-data season file. Unreadable rows are reported, not dropped silently."""
    rows = _rows(b)
    if not rows or 'HomeTeam' not in rows[0] or 'FTHG' not in rows[0]:
        alerts.append(('HATA', div, 'football-data sezon dosyası okunamadı (sütunlar eksik)'))
        return None, []
    out, rejected = [], []
    for r in rows:
        if not (r.get('HomeTeam') or '').strip():
            continue
        d = _date(r.get('Date'))
        if d is None or d > today:
            rejected.append({'neden': 'tarih geçersiz/gelecekte', **r}); continue
        def iv(k):
            v = (r.get(k) or '').strip()
            return int(float(v)) if v not in ('', None) else None
        out.append({'div': div, 'date': d.isoformat(), 'time': (r.get('Time') or '').strip(),
                    'home': r['HomeTeam'].strip(), 'away': r['AwayTeam'].strip(),
                    'hg': iv('FTHG'), 'ag': iv('FTAG'), 'hthg': iv('HTHG'), 'htag': iv('HTAG'), 'hc': iv('HC'), 'ac': iv('AC'),
                    'oh': _num(r, 'B365H'), 'od': _num(r, 'B365D'), 'oa': _num(r, 'B365A'),
                    'mh': _num(r, 'MaxH', 'BbMxH'), 'md': _num(r, 'MaxD', 'BbMxD'), 'ma': _num(r, 'MaxA', 'BbMxA'),
                    'o25': _num(r, 'B365>2.5'), 'u25': _num(r, 'B365<2.5')})
    return out, rejected


ODDS_COLS = {'b365': ('B365H', 'B365D', 'B365A', 'B365>2.5', 'B365<2.5'), 'pin': ('PSH', 'PSD', 'PSA', 'P>2.5', 'P<2.5'),
             'max': ('MaxH', 'MaxD', 'MaxA', 'Max>2.5', 'Max<2.5'), 'avg': ('AvgH', 'AvgD', 'AvgA', 'Avg>2.5', 'Avg<2.5')}


def parse_fd_fixtures(b, divs, alerts):
    """Next-round fixtures with odds. Kick-off times in the file are UK local time."""
    from zoneinfo import ZoneInfo
    uk = ZoneInfo('Europe/London')
    out = []
    for r in _rows(b):
        div = (r.get('Div') or '').strip()
        if div not in divs:
            continue
        d = _date(r.get('Date'))
        if d is None:
            continue
        t = (r.get('Time') or '15:00').strip() or '15:00'
        try:
            hh, mm = map(int, t.split(':')[:2])
        except ValueError:
            hh, mm = 15, 0
        ko = dt.datetime(d.year, d.month, d.day, hh, mm, tzinfo=uk).astimezone(UTC)
        odds = {}
        for book, (h, x, a, o, u) in ODDS_COLS.items():
            v = {'1': _num(r, h), 'X': _num(r, x), '2': _num(r, a), 'Ü2.5': _num(r, o), 'A2.5': _num(r, u)}
            v = {k: q for k, q in v.items() if q and q > 1}
            if v:
                odds[book] = v
        ah = _num(r, 'AHh')
        if ah is not None:
            for book, (hk, ak) in {'b365': ('B365AHH', 'B365AHA'), 'pin': ('PAHH', 'PAHA'), 'max': ('MaxAHH', 'MaxAHA'), 'avg': ('AvgAHH', 'AvgAHA')}.items():
                h1, a1 = _num(r, hk), _num(r, ak)
                if h1 and a1:
                    odds.setdefault(book, {}).update({'AH': ah, 'AH1': h1, 'AH2': a1})
        out.append({'div': div, 'kickoff': ko.isoformat(), 'home': r['HomeTeam'].strip(), 'away': r['AwayTeam'].strip(), 'odds': odds})
    return out


# ---------------------------------------------------------------- ESPN
def _iso(s):
    if not s:
        return None
    s = s.replace('Z', '+00:00')
    if len(s) == 22 and s[16] == '+':            # 2026-11-21T15:00+00:00 (no seconds)
        s = s[:16] + ':00' + s[16:]
    try:
        return dt.datetime.fromisoformat(s).astimezone(UTC)
    except ValueError:
        return None


def parse_espn(b):
    try:
        J = json.loads(b)
    except Exception:
        return None
    ev_out = []
    for ev in J.get('events', []) or []:
        comp = (ev.get('competitions') or [{}])[0]
        cs = comp.get('competitors') or []
        side = {c.get('homeAway'): c for c in cs}
        if 'home' not in side or 'away' not in side:
            continue
        st = comp.get('status') or ev.get('status') or {}
        ty = st.get('type') or {}
        def team(c):
            t = c.get('team') or {}
            return {'id': str(t.get('id') or c.get('id') or ''), 'names': [t.get('displayName'), t.get('shortDisplayName'), t.get('name'), t.get('location'), t.get('abbreviation')]}
        def score(c):
            try:
                return int(float(c.get('score')))
            except (TypeError, ValueError):
                return None
        def stat(c, name):
            for s in c.get('statistics') or []:
                if s.get('name') == name:
                    try:
                        return int(float(s.get('displayValue')))
                    except (TypeError, ValueError):
                        return None
            return None
        def half(c):
            ls = c.get('linescores') or []
            try:
                return int(float(ls[0].get('value'))) if ls else None
            except (TypeError, ValueError, AttributeError):
                return None
        h, a = side['home'], side['away']
        odds = None
        for o in comp.get('odds') or []:
            try:
                odds = {'provider': (o.get('provider') or {}).get('name'), 'ml1': (o.get('homeTeamOdds') or {}).get('moneyLine'),
                        'mlx': (o.get('drawOdds') or {}).get('moneyLine'), 'ml2': (o.get('awayTeamOdds') or {}).get('moneyLine'),
                        'ou': o.get('overUnder')}
                break
            except AttributeError:
                pass
        ko = _iso(ev.get('date') or comp.get('date'))
        ev_out.append({'id': str(ev.get('id')), 'kickoff': ko.isoformat() if ko else None, 'state': ty.get('state'), 'completed': bool(ty.get('completed')),
                       'status_name': ty.get('name'), 'detail': ty.get('shortDetail') or ty.get('detail'), 'clock': st.get('displayClock'),
                       'period': st.get('period'), 'home': team(h), 'away': team(a),
                       'hs': score(h), 'as': score(a), 'hht': half(h), 'aht': half(a),
                       'hc': stat(h, 'wonCorners'), 'ac': stat(a, 'wonCorners'), 'odds': odds})
    return ev_out


# ---------------------------------------------------------------- The Odds API (optional)
def parse_oddsapi(b):
    try:
        J = json.loads(b)
    except Exception:
        return None
    out = []
    for ev in J if isinstance(J, list) else []:
        home, away = ev.get('home_team'), ev.get('away_team')
        books = {}
        for bk in ev.get('bookmakers') or []:
            q = {}
            for mk in bk.get('markets') or []:
                if mk.get('key') == 'h2h':
                    for o in mk.get('outcomes') or []:
                        k = '1' if o.get('name') == home else ('2' if o.get('name') == away else ('X' if o.get('name') == 'Draw' else None))
                        if k and o.get('price'):
                            q[k] = float(o['price'])
                elif mk.get('key') == 'totals':
                    for o in mk.get('outcomes') or []:
                        p = o.get('point')
                        if p is None or not o.get('price'):
                            continue
                        k = ('Ü' if o.get('name') == 'Over' else 'A') + f'{float(p):g}'
                        q[k] = float(o['price'])
            if q:
                books[bk.get('key')] = q
        ko = _iso(ev.get('commence_time'))
        out.append({'home': home, 'away': away, 'kickoff': ko.isoformat() if ko else None, 'books': books})
    return out


def summarize_books(books):
    """Best and average price per outcome across bookmakers, plus Pinnacle when present."""
    keys = sorted({k for q in books.values() for k in q})
    mx, avg = {}, {}
    for k in keys:
        v = [q[k] for q in books.values() if k in q]
        if v:
            mx[k] = max(v); avg[k] = round(sum(v) / len(v), 3)
    out = {'max': mx, 'avg': avg, 'n_books': len(books)}
    if 'pinnacle' in books:
        out['pin'] = books['pinnacle']
    return out
