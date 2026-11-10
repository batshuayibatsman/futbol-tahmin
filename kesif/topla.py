"""Tek seferlik keşif: yeni ligler için gerçek takım adlarını, fikstürleri ve oran alanlarını toplar.
Hiçbir dosya yazmaz; özet satırları iş günlüğüne 'KESIF\t{json}' olarak basılır."""
import csv, gzip, io, json, time, urllib.request, urllib.error

UA = 'futbol-tahmin/1.0 (kisisel tahmin sitesi; GitHub Actions)'
MAIN = {'E0': 'eng.1', 'E1': 'eng.2', 'E2': 'eng.3', 'E3': 'eng.4', 'EC': 'eng.5', 'SC0': 'sco.1', 'SC1': 'sco.2',
        'SC2': 'sco.3', 'SC3': 'sco.4', 'D1': 'ger.1', 'D2': 'ger.2', 'I1': 'ita.1', 'I2': 'ita.2', 'SP1': 'esp.1',
        'SP2': 'esp.2', 'F1': 'fra.1', 'F2': 'fra.2', 'N1': 'ned.1', 'B1': 'bel.1', 'P1': 'por.1', 'T1': 'tur.1', 'G1': 'gre.1'}
EXTRA = {'ARG': 'arg.1', 'AUT': 'aut.1', 'BRA': 'bra.1', 'CHN': 'chn.1', 'DNK': 'den.1', 'FIN': 'fin.1', 'IRL': 'irl.1',
         'JPN': 'jpn.1', 'MEX': 'mex.1', 'NOR': 'nor.1', 'POL': 'pol.1', 'ROU': 'rou.1', 'RUS': 'rus.1', 'SWE': 'swe.1',
         'SWZ': 'sui.1', 'USA': 'usa.1'}
CUPS = {'UCL': 'uefa.champions', 'UEL': 'uefa.europa', 'UECL': 'uefa.europa.conf'}
E = 'https://site.api.espn.com/apis/site/v2/sports/soccer/'


def out(kind, **kw):
    kw['kind'] = kind
    print('KESIF\t' + json.dumps(kw, ensure_ascii=False), flush=True)


def get(url):
    err = ''
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
        except Exception as e:  # network hiccup
            err = str(e); time.sleep(3)
    return -1, err.encode()


def espn(code, slug):
    st, b = get(E + slug + '/teams')
    teams = []
    if st == 200:
        j = json.loads(b)
        for L in j.get('sports', [{}])[0].get('leagues', []):
            for t in L.get('teams', []):
                t = t.get('team', {})
                teams.append({k: t.get(k) for k in ('id', 'displayName', 'shortDisplayName', 'abbreviation', 'location', 'name')})
    out('espn_teams', code=code, slug=slug, status=st, teams=teams)
    time.sleep(0.3)
    st, b = get(E + slug + '/scoreboard')
    cal = []
    if st == 200:
        j = json.loads(b)
        L = (j.get('leagues') or [{}])[0]
        cal = [c if isinstance(c, str) else c.get('startDate', '') for c in L.get('calendar', [])]
        evs = j.get('events', [])
        out('espn_plain', code=code, slug=slug, status=st, season=L.get('season'), n_cal=len(cal),
            events=[ev_summary(e) for e in evs][:12])
    else:
        out('espn_plain', code=code, slug=slug, status=st)
    time.sleep(0.3)
    days = sorted({c[:10].replace('-', '') for c in cal if '2026-11-11' <= c[:10] <= '2026-11-30'})[:4]
    for d in days:
        st, b = get(E + slug + '/scoreboard?dates=' + d)
        evs = json.loads(b).get('events', []) if st == 200 else []
        out('espn_day', code=code, slug=slug, day=d, status=st, events=[ev_summary(e, odds=True) for e in evs])
        time.sleep(0.3)


def ev_summary(e, odds=False):
    c = (e.get('competitions') or [{}])[0]
    side = {x.get('homeAway'): x for x in c.get('competitors', [])}
    s = {'id': e.get('id'), 'date': e.get('date'), 'status': ((e.get('status') or {}).get('type') or {}).get('name'),
         'home': ((side.get('home') or {}).get('team') or {}).get('displayName'),
         'away': ((side.get('away') or {}).get('team') or {}).get('displayName'),
         'home_id': ((side.get('home') or {}).get('team') or {}).get('id'),
         'away_id': ((side.get('away') or {}).get('team') or {}).get('id')}
    if odds:
        s['odds'] = c.get('odds')
    return s


def fd_csv(url):
    st, b = get(url)
    if st != 200:
        return st, None, []
    txt = b.decode('utf-8-sig', errors='replace')
    rows = list(csv.reader(io.StringIO(txt)))
    return st, rows[0] if rows else None, rows[1:]


def main():
    for code, slug in {**MAIN, **EXTRA, **CUPS}.items():
        espn(code, slug)
    for div in MAIN:
        st, hdr, rows = fd_csv(f'https://www.football-data.co.uk/mmz4281/2627/{div}.csv')
        rows = [r for r in rows if len(r) > 5 and r[1]]
        teams = sorted({r[hdr.index('HomeTeam')] for r in rows} | {r[hdr.index('AwayTeam')] for r in rows}) if hdr and 'HomeTeam' in hdr else []
        out('fd_season', div=div, status=st, header=hdr, n=len(rows), teams=teams,
            last=rows[-1][1] if rows else None)
        time.sleep(0.5)
    st, hdr, rows = fd_csv('https://www.football-data.co.uk/fixtures.csv')
    out('fd_fixtures_header', status=st, header=hdr, n=len(rows))
    for r in rows:
        if any(r):
            out('fd_fixture', row=r)
    for name in ('new_league_fixtures.csv', 'new_fixtures.csv'):
        st, hdr, rows = fd_csv('https://www.football-data.co.uk/' + name)
        out('fd_extra_fixtures_header', file=name, status=st, header=hdr, n=len(rows))
        for r in rows[:400]:
            if any(r):
                out('fd_extra_fixture', file=name, row=r)
        time.sleep(0.5)
    for code in EXTRA:
        st, hdr, rows = fd_csv(f'https://www.football-data.co.uk/new/{code}.csv')
        info = {'status': st, 'header': hdr, 'n': len(rows)}
        if hdr and 'Season' in hdr:
            si = hdr.index('Season'); hi = hdr.index('Home'); ai = hdr.index('Away')
            seasons = sorted({r[si] for r in rows if len(r) > si})
            info['seasons'] = seasons[-4:]
            last = seasons[-1] if seasons else None
            lr = [r for r in rows if len(r) > ai and r[si] == last]
            info['last_season_rows'] = len(lr)
            info['teams_last'] = sorted({r[hi] for r in lr} | {r[ai] for r in lr})
            info['last_rows'] = rows[-3:]
        out('fd_new', code=code, **info)
        time.sleep(0.5)
    out('done')


main()
