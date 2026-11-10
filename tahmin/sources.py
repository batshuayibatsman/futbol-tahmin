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
    # name: unique label (alerts, pick log); short + country: what the page shows. espn None = ESPN feed not current.
    'T1': {'name': 'Süper Lig', 'short': 'Süper Lig', 'country': 'Türkiye', 'espn': 'tur.1', 'odds': 'soccer_turkey_super_league'},
    'E0': {'name': 'Premier Lig', 'short': 'Premier Lig', 'country': 'İngiltere', 'espn': 'eng.1', 'odds': 'soccer_epl'},
    'E1': {'name': 'Championship', 'short': 'Championship', 'country': 'İngiltere', 'espn': 'eng.2', 'odds': 'soccer_efl_champ'},
    'E2': {'name': 'League One', 'short': 'League One', 'country': 'İngiltere', 'espn': 'eng.3', 'odds': 'soccer_england_league1'},
    'E3': {'name': 'League Two', 'short': 'League Two', 'country': 'İngiltere', 'espn': 'eng.4', 'odds': 'soccer_england_league2'},
    'EC': {'name': 'National League', 'short': 'National League', 'country': 'İngiltere', 'espn': 'eng.5', 'odds': None},
    'SC0': {'name': 'İskoçya Premiership', 'short': 'Premiership', 'country': 'İskoçya', 'espn': 'sco.1', 'odds': 'soccer_spl'},
    'SC1': {'name': 'İskoçya Championship', 'short': 'Championship', 'country': 'İskoçya', 'espn': 'sco.2', 'odds': None},
    'SC2': {'name': 'İskoçya League One', 'short': 'League One', 'country': 'İskoçya', 'espn': None, 'odds': None},
    'SC3': {'name': 'İskoçya League Two', 'short': 'League Two', 'country': 'İskoçya', 'espn': None, 'odds': None},
    'SP1': {'name': 'La Liga', 'short': 'La Liga', 'country': 'İspanya', 'espn': 'esp.1', 'odds': 'soccer_spain_la_liga'},
    'SP2': {'name': 'La Liga 2', 'short': 'La Liga 2', 'country': 'İspanya', 'espn': 'esp.2', 'odds': 'soccer_spain_segunda_division'},
    'I1': {'name': 'Serie A', 'short': 'Serie A', 'country': 'İtalya', 'espn': 'ita.1', 'odds': 'soccer_italy_serie_a'},
    'I2': {'name': 'Serie B', 'short': 'Serie B', 'country': 'İtalya', 'espn': 'ita.2', 'odds': 'soccer_italy_serie_b'},
    'D1': {'name': 'Bundesliga', 'short': 'Bundesliga', 'country': 'Almanya', 'espn': 'ger.1', 'odds': 'soccer_germany_bundesliga'},
    'D2': {'name': '2. Bundesliga', 'short': '2. Bundesliga', 'country': 'Almanya', 'espn': 'ger.2', 'odds': 'soccer_germany_bundesliga2'},
    'F1': {'name': 'Ligue 1', 'short': 'Ligue 1', 'country': 'Fransa', 'espn': 'fra.1', 'odds': 'soccer_france_ligue_one'},
    'F2': {'name': 'Ligue 2', 'short': 'Ligue 2', 'country': 'Fransa', 'espn': 'fra.2', 'odds': 'soccer_france_ligue_two'},
    'N1': {'name': 'Eredivisie', 'short': 'Eredivisie', 'country': 'Hollanda', 'espn': 'ned.1', 'odds': 'soccer_netherlands_eredivisie'},
    'B1': {'name': 'Belçika Pro League', 'short': 'Pro League', 'country': 'Belçika', 'espn': 'bel.1', 'odds': 'soccer_belgium_first_div'},
    'P1': {'name': 'Liga Portugal', 'short': 'Liga Portugal', 'country': 'Portekiz', 'espn': 'por.1', 'odds': 'soccer_portugal_primeira_liga'},
    'G1': {'name': 'Yunanistan Süper Ligi', 'short': 'Süper Lig', 'country': 'Yunanistan', 'espn': 'gre.1', 'odds': 'soccer_greece_super_league'},
    # full-time-only leagues (football-data.co.uk/new/<code>.csv); fd: country name in new_league_fixtures.csv
    'USA': {'name': 'ABD MLS', 'short': 'MLS', 'country': 'ABD', 'espn': 'usa.1', 'odds': 'soccer_usa_mls', 'new': True, 'fd': 'USA'},
    'ARG': {'name': 'Arjantin Liga Profesional', 'short': 'Liga Profesional', 'country': 'Arjantin', 'espn': 'arg.1', 'odds': 'soccer_argentina_primera_division', 'new': True, 'fd': 'Argentina'},
    'AUT': {'name': 'Avusturya Bundesliga', 'short': 'Bundesliga', 'country': 'Avusturya', 'espn': 'aut.1', 'odds': 'soccer_austria_bundesliga', 'new': True, 'fd': 'Austria'},
    'BRA': {'name': 'Brezilya Série A', 'short': 'Série A', 'country': 'Brezilya', 'espn': 'bra.1', 'odds': 'soccer_brazil_campeonato', 'new': True, 'fd': 'Brazil'},
    'CHN': {'name': 'Çin Süper Ligi', 'short': 'Süper Lig', 'country': 'Çin', 'espn': 'chn.1', 'odds': 'soccer_china_superleague', 'new': True, 'fd': 'China'},
    'DNK': {'name': 'Danimarka Superliga', 'short': 'Superliga', 'country': 'Danimarka', 'espn': 'den.1', 'odds': 'soccer_denmark_superliga', 'new': True, 'fd': 'Denmark'},
    'FIN': {'name': 'Finlandiya Veikkausliiga', 'short': 'Veikkausliiga', 'country': 'Finlandiya', 'espn': None, 'odds': 'soccer_finland_veikkausliiga', 'new': True, 'fd': 'Finland'},
    'IRL': {'name': 'İrlanda Premier Division', 'short': 'Premier Division', 'country': 'İrlanda', 'espn': None, 'odds': 'soccer_league_of_ireland', 'new': True, 'fd': 'Ireland'},
    'SWE': {'name': 'İsveç Allsvenskan', 'short': 'Allsvenskan', 'country': 'İsveç', 'espn': 'swe.1', 'odds': 'soccer_sweden_allsvenskan', 'new': True, 'fd': 'Sweden'},
    'SWZ': {'name': 'İsviçre Super League', 'short': 'Super League', 'country': 'İsviçre', 'espn': None, 'odds': 'soccer_switzerland_superleague', 'new': True, 'fd': 'Switzerland'},
    'JPN': {'name': 'Japonya J1 League', 'short': 'J1 League', 'country': 'Japonya', 'espn': 'jpn.1', 'odds': 'soccer_japan_j_league', 'new': True, 'fd': 'Japan'},
    'MEX': {'name': 'Meksika Liga MX', 'short': 'Liga MX', 'country': 'Meksika', 'espn': 'mex.1', 'odds': 'soccer_mexico_ligamx', 'new': True, 'fd': 'Mexico'},
    'NOR': {'name': 'Norveç Eliteserien', 'short': 'Eliteserien', 'country': 'Norveç', 'espn': 'nor.1', 'odds': 'soccer_norway_eliteserien', 'new': True, 'fd': 'Norway'},
    'POL': {'name': 'Polonya Ekstraklasa', 'short': 'Ekstraklasa', 'country': 'Polonya', 'espn': None, 'odds': 'soccer_poland_ekstraklasa', 'new': True, 'fd': 'Poland'},
    'ROU': {'name': 'Romanya Superliga', 'short': 'Superliga', 'country': 'Romanya', 'espn': None, 'odds': None, 'new': True, 'fd': 'Romania'},
    'RUS': {'name': 'Rusya Premier Ligi', 'short': 'Premier Lig', 'country': 'Rusya', 'espn': 'rus.1', 'odds': None, 'new': True, 'fd': 'Russia'},
    # competitions without a statistics model (clubs from many leagues, or no free results archive): odds only, ESPN only.
    # base: whose league frequencies the SÜRPRİZ rule compares with ('MAIN' = 22-league average; none = no SÜRPRİZ)
    'UCL': {'name': 'Şampiyonlar Ligi', 'short': 'Şampiyonlar Ligi', 'country': 'UEFA', 'espn': 'uefa.champions', 'odds': 'soccer_uefa_champs_league', 'odds_only': True, 'base': 'MAIN'},
    'UEL': {'name': 'Avrupa Ligi', 'short': 'Avrupa Ligi', 'country': 'UEFA', 'espn': 'uefa.europa', 'odds': 'soccer_uefa_europa_league', 'odds_only': True, 'base': 'MAIN'},
    'UECL': {'name': 'Konferans Ligi', 'short': 'Konferans Ligi', 'country': 'UEFA', 'espn': 'uefa.europa.conf', 'odds': 'soccer_uefa_europa_conference_league', 'odds_only': True, 'base': 'MAIN'},
    'UWCL': {'name': 'Kadınlar Şampiyonlar Ligi', 'short': 'UEFA Şampiyonlar Ligi', 'country': 'Kadınlar', 'espn': 'uefa.wchampions', 'odds': None, 'odds_only': True},
    'WSL': {'name': 'İngiltere Kadınlar Süper Ligi', 'short': 'İngiltere WSL', 'country': 'Kadınlar', 'espn': 'eng.w.1', 'odds': None, 'odds_only': True},
    'LIGAF': {'name': 'İspanya Kadınlar Liga F', 'short': 'İspanya Liga F', 'country': 'Kadınlar', 'espn': 'esp.w.1', 'odds': None, 'odds_only': True},
    'FRW': {'name': 'Fransa Kadınlar Première Ligue', 'short': 'Fransa Première Ligue', 'country': 'Kadınlar', 'espn': 'fra.w.1', 'odds': None, 'odds_only': True},
    'NWSL': {'name': 'ABD Kadınlar NWSL', 'short': 'ABD NWSL', 'country': 'Kadınlar', 'espn': 'usa.nwsl', 'odds': None, 'odds_only': True},
}
FD_SEASON = 'https://www.football-data.co.uk/mmz4281/{code}/{div}.csv'
FD_FIXTURES = 'https://www.football-data.co.uk/fixtures.csv'
FD_NEW = 'https://www.football-data.co.uk/new/{code}.csv'
FD_NEW_FIXTURES = 'https://www.football-data.co.uk/new_league_fixtures.csv'
ESPN_DAY = 'https://site.api.espn.com/apis/site/v2/sports/soccer/{slug}/scoreboard?dates={d0}'
ESPN_PLAIN = 'https://site.api.espn.com/apis/site/v2/sports/soccer/{slug}/scoreboard'
ODDS_API = 'https://api.the-odds-api.com/v4/sports/{sport}/odds/?apiKey={key}&regions=eu&markets=h2h,totals&oddsFormat=decimal&dateFormat=iso'
# Updates run only on request and with --force every source is re-checked, so one run must fit a full refresh:
# football-data up to 71 files (22 leagues, two seasons in Jul-Sep, 16 full-time-only files, 2 fixture files, backfill),
# ESPN 39 scoreboards + every match date in 16 days (22 days back and forth for the odds-only competitions).
PER_RUN_CAP = {'football-data.co.uk': 90, 'site.api.espn.com': 800, 'api.the-odds-api.com': 6}
# season files missing from the archive mirror (whole or partial seasons inside the 4-year window): fetched once,
# kept in data/seasons/<code>/ and committed, never downloaded again
BACKFILL = {'2223': ['G1'], '2324': ['G1'], '2425': ['G1', 'EC', 'SC0', 'SC1', 'SC2', 'SC3', 'T1']}


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
        h = url.split('/')[2].lower()
        return h[4:] if h.startswith('www.') else h

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
                if data[:2] == b'\x1f\x8b':
                    import gzip
                    data = gzip.decompress(data)
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
                try:
                    raw = e.read()
                    if raw[:2] == b'\x1f\x8b':
                        import gzip
                        raw = gzip.decompress(raw)
                    body = raw[:160].decode('utf-8', 'replace').replace('\n', ' ')
                except Exception:
                    body = ''
                err = f'HTTP {e.code}' + (f' {body}' if body else '')
                if e.code in (400, 401, 403, 404, 429):
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


def _season_label(x):
    """'2026' -> 2026, '2025/2026' -> 2025 (start year)."""
    t = (x or '').strip()
    try:
        return int(t.split('/')[0])
    except ValueError:
        return None


def parse_fd_new(div, b, today, keep_from):
    """football-data.co.uk 'new' league file (all seasons; full-time score and closing odds only).
    Returns (rows with STD columns + 'season', rejected) or (None, []) when unreadable."""
    rows = _rows(b)
    if not rows or 'Home' not in rows[0] or 'HG' not in rows[0]:
        return None, []
    out, rejected = [], []
    for r in rows:
        if not (r.get('Home') or '').strip():
            continue
        se = _season_label(r.get('Season'))
        d = _date(r.get('Date'))
        if d is None or d > today or se is None:
            rejected.append({'neden': 'tarih/sezon geçersiz', **r}); continue
        if se < keep_from:
            continue
        def iv(k):
            v = (r.get(k) or '').strip()
            try:
                return int(float(v)) if v else None
            except ValueError:
                return None
        out.append({'div': div, 'date': d.isoformat(), 'time': (r.get('Time') or '').strip(), 'home': r['Home'].strip(), 'away': r['Away'].strip(),
                    'hg': iv('HG'), 'ag': iv('AG'), 'hthg': None, 'htag': None, 'hc': None, 'ac': None,
                    'oh': _num(r, 'B365CH', 'AvgCH'), 'od': _num(r, 'B365CD', 'AvgCD'), 'oa': _num(r, 'B365CA', 'AvgCA'),
                    'mh': _num(r, 'MaxCH'), 'md': _num(r, 'MaxCD'), 'ma': _num(r, 'MaxCA'), 'o25': None, 'u25': None, 'season': se})
    return out, rejected


def parse_fd_new_fixtures(b, country_to_div):
    """Upcoming fixtures of the full-time-only leagues with 1X2 odds (Pinnacle, best, average, Bet365). Times are UK local."""
    from zoneinfo import ZoneInfo
    uk = ZoneInfo('Europe/London')
    out = []
    for r in _rows(b):
        div = country_to_div.get((r.get('Country') or '').strip())
        d = _date(r.get('Date'))
        if not div or d is None:
            continue
        t = (r.get('Time') or '15:00').strip() or '15:00'
        try:
            hh, mm = map(int, t.split(':')[:2])
        except ValueError:
            hh, mm = 15, 0
        ko = dt.datetime(d.year, d.month, d.day, hh, mm, tzinfo=uk).astimezone(UTC)
        odds = {}
        for book, (h, x, a) in {'pin': ('PSH', 'PSD', 'PSA'), 'max': ('MaxH', 'MaxD', 'MaxA'), 'avg': ('AvgH', 'AvgD', 'AvgA'), 'b365': ('B365H', 'B365D', 'B365A')}.items():
            v = {'1': _num(r, h), 'X': _num(r, x), '2': _num(r, a)}
            v = {k: q for k, q in v.items() if q and q > 1}
            if v:
                odds[book] = v
        out.append({'div': div, 'kickoff': ko.isoformat(), 'home': r['Home'].strip(), 'away': r['Away'].strip(), 'odds': odds})
    return out


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
        odds = espn_odds(comp)
        ko = _iso(ev.get('date') or comp.get('date'))
        ev_out.append({'id': str(ev.get('id')), 'kickoff': ko.isoformat() if ko else None, 'state': ty.get('state'), 'completed': bool(ty.get('completed')),
                       'status_name': ty.get('name'), 'detail': ty.get('shortDetail') or ty.get('detail'), 'clock': st.get('displayClock'),
                       'period': st.get('period'), 'home': team(h), 'away': team(a),
                       'hs': score(h), 'as': score(a), 'hht': half(h), 'aht': half(a),
                       'hc': stat(h, 'wonCorners'), 'ac': stat(a, 'wonCorners'), 'odds': odds})
    return ev_out


def _american(v):
    """American odds ('-250', '+390', 390, 'EVEN') -> decimal."""
    if v is None:
        return None
    t = str(v).strip().upper()
    if t in ('EVEN', 'EV'):
        return 2.0
    try:
        x = float(t.replace('+', ''))
    except ValueError:
        return None
    if abs(x) < 100:
        return None
    return round(1 + x / 100, 4) if x > 0 else round(1 + 100 / abs(x), 4)


def espn_odds(comp):
    """Bookmaker prices ESPN shows with a match, as decimal odds:
    'dk' (DraftKings: 1X2 and the total-goals line with over/under), 'b365e' (Bet365: 1X2)."""
    out = {}
    for o in comp.get('odds') or []:
        if not isinstance(o, dict):
            continue
        prov = ((o.get('provider') or {}).get('name') or '').lower()
        key = 'dk' if 'draftkings' in prov else ('b365e' if '365' in prov else None)
        if not key or key in out:
            continue
        def last(x):
            x = x or {}
            return ((x.get('close') or {}).get('odds')) or ((x.get('open') or {}).get('odds'))
        v = {}
        ml = o.get('moneyline') or {}
        for s_, k in (('home', '1'), ('draw', 'X'), ('away', '2')):
            d = _american(last(ml.get(s_)))
            if d:
                v[k] = d
        for s_, k in (('homeTeamOdds', '1'), ('drawOdds', 'X'), ('awayTeamOdds', '2')):
            x = o.get(s_) or {}
            if k not in v:
                try:
                    d = float(x.get('value')) if x.get('value') is not None else _american(x.get('moneyLine'))
                except (TypeError, ValueError):
                    d = None
                if d and d > 1:
                    v[k] = round(d, 4)
        tot = o.get('total') or {}
        ov, un = _american(last(tot.get('over'))), _american(last(tot.get('under')))
        line = o.get('overUnder')
        try:
            cl = ((tot.get('over') or {}).get('close') or {}).get('line') or ''
            if cl[:1] in 'oO':
                line = float(cl[1:])
        except (TypeError, ValueError):
            pass
        if ov and un and line is not None:
            v.update(line=float(line), **{'Ü': ov, 'A': un, f'Ü{float(line):g}': ov, f'A{float(line):g}': un})
        if v:
            out[key] = v
    return out or None


def espn_calendar(b):
    """Match dates (US Eastern calendar days, YYYYMMDD) listed in a scoreboard response's league calendar."""
    from zoneinfo import ZoneInfo
    et = ZoneInfo('America/New_York')
    try:
        J = json.loads(b)
    except Exception:
        return None
    cal = []
    for lg in J.get('leagues') or []:
        for c in lg.get('calendar') or []:
            items = []
            if isinstance(c, str):
                items = [c]
            elif isinstance(c, dict):
                a, z = _iso(c.get('startDate')), _iso(c.get('endDate'))
                if a and z:
                    d = a.astimezone(et).date()
                    while d <= z.astimezone(et).date():
                        cal.append(d.strftime('%Y%m%d')); d += dt.timedelta(days=1)
                for e in c.get('entries') or []:
                    if isinstance(e, dict):
                        items += [e.get('startDate')]
            for x in items:
                t = _iso(x)
                if t:
                    cal.append(t.astimezone(et).date().strftime('%Y%m%d'))
    return sorted(set(cal)) if cal else None


def espn_summary(b):
    try:
        J = json.loads(b)
    except Exception:
        return 'okunamadı'
    ev = J.get('events') or []
    ds = sorted(e.get('date', '') for e in ev)
    lg = (J.get('leagues') or [{}])[0]
    return f"{len(ev)} maç {ds[0][:10] if ds else ''}..{ds[-1][:10] if ds else ''}, takvim {len(lg.get('calendar') or [])} gün ({lg.get('calendarType')})"


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
