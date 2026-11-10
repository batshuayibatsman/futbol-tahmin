"""Offline test (v2, 22 leagues). Inside a throw-away copy of the repo it writes:
  - ESPN-style JSON for the 20 leagues ESPN keeps current, rebuilt from a real snapshot taken on 10 Nov 2026
    (tests/ornek_espn.json: real fixtures, club names and DraftKings / Bet365 prices; matches before --now get a fake score),
  - a football-data-style fixtures.csv (fake prices) for the Scottish League One / Two, which ESPN does not keep current,
  - optionally, stand-in 2026-27 season files from the archive mirror for leagues that have none yet.
Never used by the update job.
Usage: python tests/sahte_kaynaklar.py <copy> <now ISO> [Matches.csv]"""
import csv, json, sys, datetime as dt
from pathlib import Path
from zoneinfo import ZoneInfo

root = Path(sys.argv[1]); cache = root / '.cache' / 'http'; cache.mkdir(parents=True, exist_ok=True)
UK, UTC = ZoneInfo('Europe/London'), dt.timezone.utc
now = dt.datetime.fromisoformat(sys.argv[2]).astimezone(UTC)
here = Path(__file__).resolve().parent
sys.path.insert(0, str(root / 'tahmin'))
import sources as S
from config import TARGET

snap = json.load(open(here / 'ornek_espn.json', encoding='utf-8'))
counts = {}
for div in TARGET:
    if div not in snap or not S.LEAGUES[div]['espn']:
        continue
    L = snap[div]
    by_day = {}
    for k, e in enumerate(L['events']):
        ko = dt.datetime.fromisoformat(e['date'].replace('Z', '+00:00'))
        st = 'pre' if ko > now else 'post'
        team = lambda n, i: {'id': i, 'displayName': n, 'shortDisplayName': n, 'name': n, 'location': n, 'abbreviation': n[:3].upper()}
        hs, as_ = (0, 0) if st == 'pre' else (1 + k % 3, k % 2)
        ev = {'id': e['id'], 'date': e['date'], 'competitions': [{
            'competitors': [{'homeAway': 'home', 'team': team(e['home'], e['home_id']), 'score': str(hs), 'linescores': [{'value': min(hs, 1)}]},
                            {'homeAway': 'away', 'team': team(e['away'], e['away_id']), 'score': str(as_), 'linescores': [{'value': 0}]}],
            'status': {'displayClock': "0'", 'period': 0 if st == 'pre' else 2,
                       'type': {'state': st, 'completed': st == 'post', 'name': 'STATUS_SCHEDULED' if st == 'pre' else 'STATUS_FULL_TIME',
                                'shortDetail': 'FT' if st == 'post' else ''}},
            'odds': e['odds'] if st == 'pre' else []}]}
        by_day.setdefault(ko.astimezone(ZoneInfo('America/New_York')).strftime('%Y%m%d'), []).append(ev)
    days = sorted(by_day)
    cal = [f'{d[:4]}-{d[4:6]}-{d[6:]}T08:00Z' for d in days]
    (cache / f'espn_{div}_plain.bin').write_text(json.dumps({'leagues': [{'calendar': cal}], 'events': by_day[days[0]]}))
    for d in days:
        (cache / f'espn_{div}_{d}.bin').write_text(json.dumps({'events': by_day[d]}))
    counts[div] = sum(len(v) for v in by_day.values())

# stand-in current-season files (only in the test copy) so that this season's clubs are known
mirror = sys.argv[3] if len(sys.argv) > 3 else None
teams = {}
if mirror:
    import pandas as pd
    X = pd.read_csv(mirror, low_memory=False)
    X['d'] = pd.to_datetime(X.MatchDate, errors='coerce')
    for div in TARGET:
        p = root / 'data' / 'seasons' / '2627' / f'{div}.csv'
        g = X[(X.Division == div) & (X.d >= '2026-07-01')]
        teams[div] = sorted(set(g.HomeTeam) | set(g.AwayTeam))
        if p.exists() or g.empty:
            continue
        out = pd.DataFrame({'div': div, 'date': g.d.dt.strftime('%Y-%m-%d'), 'time': '', 'home': g.HomeTeam, 'away': g.AwayTeam,
                            'hg': g.FTHome, 'ag': g.FTAway, 'hthg': g.HTHome, 'htag': g.HTAway, 'hc': g.HomeCorners, 'ac': g.AwayCorners,
                            'oh': g.OddHome, 'od': g.OddDraw, 'oa': g.OddAway, 'mh': g.MaxHome, 'md': g.MaxDraw, 'ma': g.MaxAway, 'o25': g.Over25, 'u25': g.Under25})
        p.parent.mkdir(parents=True, exist_ok=True); out[S.STD].to_csv(p, index=False)

# full-time-only leagues: the mirror ends in Dec 2024, so its last three seasons are shifted by two years (test copy only)
EXTRA_MIRROR = {'ARG': 'ARG', 'AUT': 'AUT', 'BRA': 'BRA', 'CHN': 'CHN', 'DNK': 'DEN', 'FIN': 'FIN', 'IRL': 'IRL', 'JPN': 'JAP', 'MEX': 'MEX',
                'NOR': 'NOR', 'POL': 'POL', 'ROU': 'ROM', 'RUS': 'RUS', 'SWE': 'SWE', 'SWZ': 'SUI', 'USA': 'USA'}
if mirror:
    for div, md in EXTRA_MIRROR.items():
        if div not in TARGET:
            continue
        p = root / 'data' / 'seasons' / 'new' / f'{div}.csv'
        g = X[(X.Division == md) & (X.d >= '2022-01-01')].copy()
        if p.exists() or g.empty:
            continue
        g['d2'] = g.d + pd.DateOffset(years=2)
        cal = div in ('ARG', 'BRA', 'CHN', 'FIN', 'IRL', 'JPN', 'NOR', 'SWE', 'USA')
        se = g.d2.dt.year if cal else g.d2.dt.year.where(g.d2.dt.month >= 7, g.d2.dt.year - 1)
        out = pd.DataFrame({'div': div, 'date': g.d2.dt.strftime('%Y-%m-%d'), 'time': '', 'home': g.HomeTeam, 'away': g.AwayTeam,
                            'hg': g.FTHome, 'ag': g.FTAway, 'hthg': None, 'htag': None, 'hc': None, 'ac': None,
                            'oh': g.OddHome, 'od': g.OddDraw, 'oa': g.OddAway, 'mh': g.MaxHome, 'md': g.MaxDraw, 'ma': g.MaxAway, 'o25': None, 'u25': None, 'season': se})
        p.parent.mkdir(parents=True, exist_ok=True); out.to_csv(p, index=False)
        teams[div] = sorted(set(g[g.d2 >= '2026-01-01'].HomeTeam) | set(g[g.d2 >= '2026-01-01'].AwayTeam))

# football-data-style fixtures with fake prices for the leagues without a current ESPN feed
rows = []
for div in [d for d in TARGET if not S.LEAGUES[d]['espn']]:
    t = teams.get(div) or []
    ko = (now + dt.timedelta(days=2)).replace(hour=15, minute=0, second=0, microsecond=0).astimezone(UK)
    for i in range(0, len(t) - 1, 2):
        rows.append({'Div': div, 'Date': ko.strftime('%d/%m/%Y'), 'Time': ko.strftime('%H:%M'), 'HomeTeam': t[i], 'AwayTeam': t[i + 1],
                     'B365H': 2.3, 'B365D': 3.3, 'B365A': 3.1, 'MaxH': 2.45, 'MaxD': 3.5, 'MaxA': 3.3, 'AvgH': 2.3, 'AvgD': 3.3, 'AvgA': 3.1,
                     'B365>2.5': 1.85, 'B365<2.5': 1.95, 'Max>2.5': 1.93, 'Max<2.5': 2.02, 'Avg>2.5': 1.86, 'Avg<2.5': 1.94})
main_rows = [r for r in rows if r['Div'] in S.LEAGUES and not S.LEAGUES[r['Div']].get('new')]
new_rows = [{'Country': S.LEAGUES[r['Div']]['fd'], 'League': '', 'Date': r['Date'], 'Time': r['Time'], 'Home': r['HomeTeam'], 'Away': r['AwayTeam'],
             'PSH': r['B365H'], 'PSD': r['B365D'], 'PSA': r['B365A'], 'AvgH': r['AvgH'], 'AvgD': r['AvgD'], 'AvgA': r['AvgA'],
             'B365H': r['B365H'], 'B365D': r['B365D'], 'B365A': r['B365A']} for r in rows if S.LEAGUES[r['Div']].get('new')]
for name, rr in (('fd_fixtures.bin', main_rows), ('fd_new_fixtures.bin', new_rows)):
    if rr:
        with open(cache / name, 'w', newline='', encoding='utf-8') as f:
            w = csv.DictWriter(f, fieldnames=list(rr[0].keys())); w.writeheader(); w.writerows(rr)
print('sahte akış:', counts, '| football-data fikstür satırı:', len(main_rows), '+ ek lig', len(new_rows))
