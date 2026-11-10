"""Offline test: builds FAKE feed files (ESPN-style JSON and a football-data-style fixtures.csv) for the
20-23 Nov 2026 round inside a throw-away copy of the repo, so the whole pipeline can run without internet.
Never used by the scheduled job."""
import json, sys, csv, datetime as dt
from pathlib import Path
from zoneinfo import ZoneInfo
root = Path(sys.argv[1]); cache = root / '.cache' / 'http'; cache.mkdir(parents=True, exist_ok=True)
TR, UK, UTC = ZoneInfo('Europe/Istanbul'), ZoneInfo('Europe/London'), dt.timezone.utc
ESPN_NAMES = {'Bournemouth': 'AFC Bournemouth', 'Brighton': 'Brighton & Hove Albion', 'Coventry': 'Coventry City', 'Hull': 'Hull City', 'Ipswich': 'Ipswich Town',
  'Leeds': 'Leeds United', 'Man City': 'Manchester City', 'Man United': 'Manchester United', 'Newcastle': 'Newcastle United', "Nott'm Forest": 'Nottingham Forest',
  'Tottenham': 'Tottenham Hotspur', 'Alaves': 'Alavés', 'Ath Bilbao': 'Athletic Club', 'Ath Madrid': 'Atlético Madrid', 'Betis': 'Real Betis', 'Celta': 'Celta Vigo',
  'Espanol': 'Espanyol', 'La Coruna': 'Deportivo La Coruña', 'Malaga': 'Málaga', 'Santander': 'Racing Santander', 'Sociedad': 'Real Sociedad', 'Vallecano': 'Rayo Vallecano',
  'Inter': 'Internazionale', 'Milan': 'AC Milan', 'Roma': 'AS Roma', 'Augsburg': 'FC Augsburg', 'Dortmund': 'Borussia Dortmund', 'Ein Frankfurt': 'Eintracht Frankfurt',
  'Elversberg': 'SV Elversberg', 'FC Koln': 'FC Cologne', 'Freiburg': 'SC Freiburg', 'Hamburg': 'Hamburg SV', 'Hoffenheim': 'TSG Hoffenheim', 'Leverkusen': 'Bayer Leverkusen',
  "M'gladbach": 'Borussia Mönchengladbach', 'Paderborn': 'SC Paderborn 07', 'Stuttgart': 'VfB Stuttgart', 'Auxerre': 'AJ Auxerre', 'Le Havre': 'Le Havre AC',
  'Monaco': 'AS Monaco', 'Paris SG': 'Paris Saint-Germain', 'Rennes': 'Stade Rennais', 'Buyuksehyr': 'Istanbul Basaksehir', 'Corum': 'Corum FK', 'Gaziantep': 'Gaziantep FK',
  'Goztep': 'Goztepe', 'Rizespor': 'Caykur Rizespor'}
SLUG = {'T1': 'tur.1', 'E0': 'eng.1', 'SP1': 'esp.1', 'I1': 'ita.1', 'D1': 'ger.1', 'F1': 'fra.1'}
now = dt.datetime.fromisoformat(sys.argv[2]).astimezone(UTC)
fx = list(csv.DictReader(open(Path(__file__).resolve().parent / 'fixtures_ornek.csv', encoding='utf-8')))
tid = {}
ev = {d: [] for d in SLUG}
fd_rows = []
for k, r in enumerate(fx):
    ko = dt.datetime.fromisoformat(f"{r['date']}T{r['time']}").replace(tzinfo=TR).astimezone(UTC)
    def team(t):
        tid.setdefault(t, str(100 + len(tid)))
        n = ESPN_NAMES.get(t, t)
        return {'id': tid[t], 'displayName': n, 'shortDisplayName': n, 'name': n, 'location': n, 'abbreviation': n[:3].upper()}
    mins = (now - ko).total_seconds() / 60
    state = 'pre' if mins < 0 else ('in' if mins < 110 else 'post')
    hs, as_ = (1, 0) if state == 'in' else ((2, 1) if state == 'post' else (0, 0))
    ev[r['div']].append({'id': str(700000 + k), 'date': ko.strftime('%Y-%m-%dT%H:%MZ'), 'competitions': [{'competitors': [
        {'homeAway': 'home', 'team': team(r['home']), 'score': str(hs), 'linescores': [{'value': 1}]},
        {'homeAway': 'away', 'team': team(r['away']), 'score': str(as_), 'linescores': [{'value': 0}]}],
        'status': {'displayClock': f"{int(min(mins, 90))}'" if state == 'in' else '0\'', 'period': 1 if state == 'in' else 0,
                   'type': {'state': state, 'completed': state == 'post', 'name': 'STATUS_FIRST_HALF' if state == 'in' else ('STATUS_FULL_TIME' if state == 'post' else 'STATUS_SCHEDULED'),
                            'shortDetail': 'FT' if state == 'post' else ''}}}]})
    # football-data-style odds row (fake prices derived from the Sportradar percentages, 5% margin)
    if r['mkt_h']:
        ph, pd_, pa = (float(r[c]) / 100 for c in ('mkt_h', 'mkt_d', 'mkt_a'))
        o = [round(1 / (p * 1.05), 2) for p in (ph, pd_, pa)]
        uk = ko.astimezone(UK)
        fd_rows.append({'Div': r['div'], 'Date': uk.strftime('%d/%m/%Y'), 'Time': uk.strftime('%H:%M'), 'HomeTeam': r['home'], 'AwayTeam': r['away'],
                        'B365H': o[0], 'B365D': o[1], 'B365A': o[2], 'PSH': round(o[0] * 1.02, 2), 'PSD': round(o[1] * 1.02, 2), 'PSA': round(o[2] * 1.02, 2),
                        'MaxH': round(o[0] * 1.05, 2), 'MaxD': round(o[1] * 1.05, 2), 'MaxA': round(o[2] * 1.05, 2), 'AvgH': o[0], 'AvgD': o[1], 'AvgA': o[2],
                        'B365>2.5': 1.85, 'B365<2.5': 1.95, 'Max>2.5': 1.93, 'Max<2.5': 2.02, 'Avg>2.5': 1.86, 'Avg<2.5': 1.94,
                        'AHh': -0.5 if ph > pa else 0.5, 'B365AHH': 1.95, 'B365AHA': 1.9, 'MaxAHH': 2.0, 'MaxAHA': 1.97, 'AvgAHH': 1.93, 'AvgAHA': 1.9})
for d, e in ev.items():
    (cache / f'espn_{d}_w0.bin').write_text(json.dumps({'events': e}))
with open(cache / 'fd_fixtures.bin', 'w', newline='', encoding='utf-8') as f:
    w = csv.DictWriter(f, fieldnames=list(fd_rows[0].keys())); w.writeheader(); w.writerows(fd_rows)
print('sahte akış:', {d: len(e) for d, e in ev.items()}, 'oranlı', len(fd_rows))
