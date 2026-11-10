"""Tek seferlik keşif (2): UEFA kupaları, kadın ligleri ve İngiltere'nin 5. lig altı için ESPN akışları ve oranları.
Hiçbir dosya yazmaz; özet satırları iş günlüğüne 'KESIF\t{json}' olarak basılır."""
import gzip, json, time, urllib.request, urllib.error, datetime as dt

UA = 'futbol-tahmin/1.0 (kisisel tahmin sitesi; GitHub Actions)'
E = 'https://site.api.espn.com/apis/site/v2/sports/soccer/'
CUPS = ['uefa.champions', 'uefa.europa', 'uefa.europa.conf', 'uefa.wchampions']
WOMEN = ['eng.w.1', 'usa.nwsl', 'esp.w.1', 'ger.w.1', 'fra.w.1', 'ita.w.1', 'tur.w.1']
LOWER = ['eng.6', 'eng.7', 'eng.n', 'eng.s', 'eng.5.n', 'eng.5.s', 'eng.conf.n', 'eng.conf.s', 'eng.fa', 'eng.league_cup', 'eng.trophy']


def out(kind, **kw):
    kw['kind'] = kind
    print('KESIF\t' + json.dumps(kw, ensure_ascii=False), flush=True)


def get(url):
    for _ in range(3):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': UA, 'Accept-Encoding': 'gzip'})
            with urllib.request.urlopen(req, timeout=40) as r:
                b = r.read()
                if r.headers.get('Content-Encoding') == 'gzip':
                    b = gzip.decompress(b)
                return r.status, b
        except urllib.error.HTTPError as e:
            return e.code, b''
        except Exception:
            time.sleep(3)
    return -1, b''


def strip(o):
    if isinstance(o, dict):
        return {k: strip(v) for k, v in o.items() if k not in ('link', 'links', 'logos', 'tracking', 'logo')}
    if isinstance(o, list):
        return [strip(x) for x in o]
    return o


def ev(e):
    c = (e.get('competitions') or [{}])[0]
    side = {x.get('homeAway'): x for x in c.get('competitors', [])}
    t = lambda s: ((side.get(s) or {}).get('team') or {})
    return {'id': e.get('id'), 'date': e.get('date'), 'status': ((e.get('status') or {}).get('type') or {}).get('name'),
            'home': t('home').get('displayName'), 'away': t('away').get('displayName'), 'home_id': t('home').get('id'), 'away_id': t('away').get('id'),
            'score': [(side.get(s) or {}).get('score') for s in ('home', 'away')],
            'lines': [[l.get('value') for l in ((side.get(s) or {}).get('linescores') or [])] for s in ('home', 'away')],
            'odds': strip(c.get('odds'))}


for slug in CUPS + WOMEN + LOWER:
    st, b = get(E + slug + '/scoreboard')
    if st != 200:
        out('plain', slug=slug, status=st); time.sleep(0.3); continue
    j = json.loads(b); L = (j.get('leagues') or [{}])[0]
    out('plain', slug=slug, status=st, name=L.get('name'), season=L.get('season'), calendar=strip(L.get('calendar'))[:6],
        n_cal=len(L.get('calendar') or []), events=[ev(e) for e in j.get('events', [])][:6])
    time.sleep(0.3)
    if slug in LOWER:
        continue
    st, b = get(E + slug + '/teams')
    n = 0
    if st == 200:
        for Lg in json.loads(b).get('sports', [{}])[0].get('leagues', []):
            n += len(Lg.get('teams', []))
    out('teams', slug=slug, status=st, n=n)
    day = dt.date(2026, 11, 11)
    while day <= dt.date(2026, 11, 30):
        st, b = get(E + slug + '/scoreboard?dates=' + day.strftime('%Y%m%d'))
        evs = json.loads(b).get('events', []) if st == 200 else []
        if evs:
            out('day', slug=slug, day=day.isoformat(), events=[ev(e) for e in evs])
        day += dt.timedelta(days=1); time.sleep(0.25)
    for d0 in ('20261104', '20261105', '20261106'):
        st, b = get(E + slug + '/scoreboard?dates=' + d0)
        evs = json.loads(b).get('events', []) if st == 200 else []
        if evs:
            out('past', slug=slug, day=d0, events=[ev(e) for e in evs][:4])
        time.sleep(0.25)
out('done')
