"""Update job (GitHub Actions, started only on request): fetch -> validate -> fit -> predict -> record / settle picks -> build the site.
The public page never triggers any of this; it only reads the files this job publishes.
    python tahmin/pipeline.py              normal run (respects cache intervals)
    python tahmin/pipeline.py --force      ignore cache intervals (manual "refresh everything")
    python tahmin/pipeline.py --offline    use cached files only (tests)"""
import argparse, hashlib, json, os, sys, time, datetime as dt
from pathlib import Path
from zoneinfo import ZoneInfo

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
import numpy as np, pandas as pd
from config import CFG, TARGET, ODDS_BLEND, EXTRA
from model import LeagueFitter, predict_means, match_distribution, summarize, apply_htft_cal
from probs import predict_all
from markets import (market_probs, pick_banko, pick_surprise, BANKO_MENU, BANKO_MIN, BANKO_MAX,
                     SURPRISE_MENU, SURPRISE_MIN_P, SURPRISE_MIN_LIFT)
from stats import match_facts
import sources as S
from names import build_map, display, DISPLAY
from market import odds_means
from dataset import load as load_dataset
from picks import PickLog

TR = ZoneInfo('Europe/Istanbul'); UK = ZoneInfo('Europe/London'); UTC = dt.timezone.utc
CACHE = ROOT / '.cache'; SITE = ROOT / '_site'; STATE = ROOT / 'state'; FROZEN = ROOT / 'data' / 'frozen'
ESPN_HOT_MIN, ESPN_COLD_MIN = 10, 120
FD_MIN = 180
ODDS_RESERVE, ODDS_MIN_GAP_H, ODDS_AHEAD_H = 60, 8, 36
AHEAD_DAYS = 14


def jload(p, default):
    try:
        return json.load(open(p, encoding='utf-8'))
    except Exception:
        return default


def jdump(o, p):
    p = Path(p); p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + '.tmp')
    json.dump(o, open(tmp, 'w', encoding='utf-8'), ensure_ascii=False, default=_jdef, separators=(',', ':'))
    tmp.replace(p)


def _jdef(o):
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return None if np.isnan(o) else float(o)
    if isinstance(o, (np.bool_,)):
        return bool(o)
    if isinstance(o, (pd.Timestamp, dt.datetime, dt.date)):
        return o.isoformat()
    return str(o)


def season_now(d):
    return d.year if d.month >= 7 else d.year - 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--offline', action='store_true'); ap.add_argument('--force', action='store_true')
    ap.add_argument('--now', help='ISO time override (tests)'); ap.add_argument('--site-origin', default=os.environ.get('SITE_ORIGIN', ''))
    a = ap.parse_args()
    now = dt.datetime.fromisoformat(a.now).astimezone(UTC) if a.now else dt.datetime.now(UTC)
    now_tr = now.astimezone(TR); today = now_tr.date(); SEASON = season_now(today)
    state = jload(CACHE / 'state.json', {})
    http = S.Http(CACHE / 'http', state, offline=a.offline, force=a.force)
    alerts = []
    def alert(level, scope, msg):
        alerts.append({'seviye': level, 'kapsam': scope, 'mesaj': msg})
    cal = jload(FROZEN / 'cal_val.json', None); base_all = jload(FROZEN / 'base_rates.json', {})
    names = {d: S.LEAGUES[d]['name'] for d in TARGET}

    # ------------------------------------------------------------ 1. football-data season files
    code = S.season_code(today)
    codes = [code]
    if today.month in (7, 8, 9):
        py = SEASON - 1; codes.append(f'{py % 100:02d}{(py + 1) % 100:02d}')
    fd_status = {}
    for div in [d for d in TARGET if d not in EXTRA]:
        for c in codes:
            b, info = http.get(f'fd_{c}_{div}', S.FD_SEASON.format(code=c, div=div), FD_MIN)
            snap = ROOT / 'data' / 'seasons' / c / f'{div}.csv'
            if info.get('action') == 'hata':
                if '404' in str(info.get('error')) and c == code and today.month in (6, 7, 8):
                    alert('BİLGİ', names[div], f'{c} sezon dosyası henüz yayınlanmadı')
                else:
                    alert('UYARI', names[div], f'football-data indirilemedi ({info.get("error")}); son kayıtlı dosya kullanıldı')
            if b is None or info.get('action') in ('önbellek', 'sınır', 'yok'):
                continue
            rows, rejected = S.parse_fd_season(div, b, today, [])
            if rows is None:
                alert('HATA', names[div], 'football-data dosyası okunamadı; eski dosya korundu'); continue
            new = pd.DataFrame(rows, columns=S.STD)
            old = pd.read_csv(snap) if snap.exists() else pd.DataFrame(columns=S.STD)
            if len(new) < len(old):
                alert('HATA', names[div], f'football-data satır sayısı azaldı ({len(old)} → {len(new)}); eski dosya korundu'); continue
            snap.parent.mkdir(parents=True, exist_ok=True)
            if not snap.exists() or new.to_csv(index=False) != old.to_csv(index=False):
                new.to_csv(snap, index=False)
            if rejected:
                pd.DataFrame(rejected).to_csv(snap.with_name(f'{div}_reddedilen.csv'), index=False)
                alert('UYARI', names[div], f'{len(rejected)} satır okunamadı (tarih geçersiz/gelecekte); {snap.parent.name}/{div}_reddedilen.csv dosyasına yazıldı')
        fd_status[div] = state['http'].get(f'fd_{code}_{div}', {})
    # full-time-only leagues: one file per country with every season (kept: the last six seasons)
    for div in [d for d in TARGET if d in EXTRA]:
        b, info = http.get(f'fdnew_{div}', S.FD_NEW.format(code=div), FD_MIN)
        snap = ROOT / 'data' / 'seasons' / 'new' / f'{div}.csv'
        if info.get('action') == 'hata':
            alert('UYARI', names[div], f'football-data indirilemedi ({info.get("error")}); son kayıtlı dosya kullanıldı')
        if b is None or info.get('action') in ('önbellek', 'sınır', 'yok'):
            continue
        rows, rejected = S.parse_fd_new(div, b, today, SEASON - 6)
        if rows is None:
            alert('HATA', names[div], 'football-data dosyası okunamadı; eski dosya korundu'); continue
        new = pd.DataFrame(rows, columns=S.STD + ['season'])
        old = pd.read_csv(snap) if snap.exists() else pd.DataFrame(columns=S.STD + ['season'])
        if len(new) < 0.9 * len(old):
            alert('HATA', names[div], f'football-data satır sayısı azaldı ({len(old)} → {len(new)}); eski dosya korundu'); continue
        snap.parent.mkdir(parents=True, exist_ok=True)
        if not snap.exists() or new.to_csv(index=False) != old.to_csv(index=False):
            new.to_csv(snap, index=False)
    # seasons missing from the archive mirror: downloaded once, then kept in data/seasons/<code>/
    for bc, divs in S.BACKFILL.items():
        for div in divs:
            snap = ROOT / 'data' / 'seasons' / bc / f'{div}.csv'
            if div not in TARGET or snap.exists():
                continue
            b, info = http.get(f'fd_{bc}_{div}', S.FD_SEASON.format(code=bc, div=div), 10 ** 7)
            rows, rejected = S.parse_fd_season(div, b, today, []) if b else (None, [])
            if rows:
                snap.parent.mkdir(parents=True, exist_ok=True)
                pd.DataFrame(rows, columns=S.STD).to_csv(snap, index=False)
            elif not a.offline:
                alert('BİLGİ', names[div], f'{bc} arşiv sezonu indirilemedi; model mevcut arşivle çalıştı')

    # ------------------------------------------------------------ 2. football-data fixtures (odds)
    uk = now.astimezone(UK)
    fx_min = 60 if (uk.weekday() in (1, 4) and uk.hour >= 12) else FD_MIN
    b, info = http.get('fd_fixtures', S.FD_FIXTURES, fx_min)
    fd_fix = S.parse_fd_fixtures(b, set(TARGET), alerts) if b else []
    if info.get('action') == 'hata':
        alert('UYARI', 'Oranlar', f'football-data fikstür/oran dosyası indirilemedi ({info.get("error")})')
    fd_fix_seen = state['http'].get('fd_fixtures', {}).get('ok')
    if EXTRA:
        b, info = http.get('fd_new_fixtures', S.FD_NEW_FIXTURES, fx_min)
        if b:
            fd_fix += S.parse_fd_new_fixtures(b, {S.LEAGUES[d]['fd']: d for d in TARGET if d in EXTRA})
        if info.get('action') == 'hata':
            alert('UYARI', 'Oranlar', f'football-data ek lig fikstür dosyası indirilemedi ({info.get("error")})')

    # ------------------------------------------------------------ 3. ESPN fixtures + live
    # ESPN refuses date ranges (HTTP 400). Per league: the default scoreboard (latest/current matchday, with the
    # season's match-date calendar), then every match date from yesterday to +14 days by date. Today's and
    # yesterday's dates refresh every 10 minutes around matches (2 hours otherwise), the next 3 days every 2 hours,
    # later dates every 6 hours.
    from zoneinfo import ZoneInfo as _Z
    hot = state.get('espn_hot', True)
    iv = ESPN_HOT_MIN if hot else ESPN_COLD_MIN
    et_today = now.astimezone(_Z('America/New_York')).date()
    lo, hi = (et_today - dt.timedelta(days=1)).strftime('%Y%m%d'), (et_today + dt.timedelta(days=AHEAD_DAYS)).strftime('%Y%m%d')
    near = {(et_today + dt.timedelta(days=k)).strftime('%Y%m%d') for k in (-1, 0)}
    soon = {(et_today + dt.timedelta(days=k)).strftime('%Y%m%d') for k in (1, 2, 3)}
    espn, espn_ok, cors = {}, {}, state.get('espn_cors')
    origin = a.site_origin or 'https://example.github.io'
    diag = []
    days = set()
    for div in TARGET:
        slug = S.LEAGUES[div]['espn']; evs_all = {}; got = False; oks = []
        if not slug:                      # ESPN does not keep this league current: fixtures come from football-data only
            espn[div] = []; espn_ok[div] = None
            continue
        b, info = http.get(f'espn_{div}_plain', S.ESPN_PLAIN.format(slug=slug), iv, conditional=False)
        espn_cal = S.espn_calendar(b) if b else None
        if b:
            diag.append(f'{div} varsayılan: {S.espn_summary(b)}')
        want = [d for d in (espn_cal or []) if lo <= d <= hi]
        if espn_cal is None:
            want = [(et_today + dt.timedelta(days=k)).strftime('%Y%m%d') for k in range(-1, 8)]
            diag.append(f'{div}: takvim yok, 9 gün tek tek')
        days.update(want)
        reqs = [(None, b, info)]
        for d in want:
            div_iv = iv if d in near else (120 if d in soon else 360)
            b2, i2 = http.get(f'espn_{div}_{d}', S.ESPN_DAY.format(slug=slug, d0=d), div_iv, conditional=False)
            reqs.append((d, b2, i2))
        for d, bb, ii in reqs:
            if ii.get('action') == 'hata':
                diag.append(f'{div} {d or "varsayılan"}: {ii.get("error")}')
            evs = S.parse_espn(bb) if bb else None
            if bb and evs is None:
                alert('UYARI', names[div], 'ESPN yanıtı okunamadı')
            for e in evs or []:
                evs_all[e['id']] = e
            got = got or bool(bb)
            oks.append(state['http'].get(f'espn_{div}_{d or "plain"}', {}).get('ok') or 0)
        if not got:
            alert('UYARI', names[div], 'ESPN fikstür/canlı skor alınamadı; fikstür yalnızca football-data oran dosyasından')
        espn[div] = list(evs_all.values())
        espn_ok[div] = max(oks) or None
    # forget per-day cache entries that left the window
    keep = set(days)
    for k in [k for k in state.get('http', {}) if k.startswith('espn_') and k[-8:].isdigit() and k[-8:] not in keep]:
        state['http'].pop(k, None)
        try:
            (CACHE / 'http' / (k + '.bin')).unlink()
        except OSError:
            pass
    # browser-side live scores are possible only if ESPN allows cross-origin reads: check once a day
    b, info = http.get('espn_cors', S.ESPN_PLAIN.format(slug='eng.1'), 1440, conditional=False, headers={'Origin': origin})
    if info.get('action') == 'indirildi':
        acao = (info.get('headers') or {}).get('access-control-allow-origin')
        cors = bool(acao and (acao == '*' or acao == origin)); state['espn_cors'] = cors
    state['espn_diag'] = diag[-12:]

    # ------------------------------------------------------------ 4. dataset + audit
    D, audit = load_dataset(str(ROOT), today)
    cutoff = pd.Timestamp(today)

    # ------------------------------------------------------------ 5. The Odds API (optional)
    key = os.environ.get('ODDS_API_KEY', '').strip()
    oa = state.setdefault('oddsapi', {})
    month = now.strftime('%Y-%m')
    if oa.get('month') != month:
        oa.update(month=month, used_this_month=0)
    oddsapi = {}
    if key and not a.offline:
        remaining = oa.get('remaining')
        for div in [d for d in TARGET if S.LEAGUES[d].get('odds')]:
            soon = [e for e in espn[div] if e['state'] == 'pre' and e['kickoff'] and 0 < (dt.datetime.fromisoformat(e['kickoff']) - now).total_seconds() / 3600 <= ODDS_AHEAD_H]
            soon += [f for f in fd_fix if f['div'] == div and 0 < (dt.datetime.fromisoformat(f['kickoff']) - now).total_seconds() / 3600 <= ODDS_AHEAD_H]
            last = oa.setdefault('last', {}).get(div, 0)
            if not soon or (time.time() - last) / 3600 < ODDS_MIN_GAP_H or (remaining is not None and int(remaining) <= ODDS_RESERVE):
                continue
            b, info = http.get(f'odds_{div}', S.ODDS_API.format(sport=S.LEAGUES[div]['odds'], key=key), 0, conditional=False, redact=key)
            if info.get('action') == 'indirildi':
                hdr = info.get('headers') or {}
                oa['remaining'] = remaining = hdr.get('x-requests-remaining', remaining)
                oa['used_this_month'] = oa.get('used_this_month', 0) + int(float(hdr.get('x-requests-last', 2) or 2))
                oa['last'][div] = time.time()
            elif info.get('action') == 'hata':
                alert('UYARI', 'Odds API', f'{names[div]}: {info.get("error")}')
        for div in TARGET:
            p = CACHE / 'http' / f'odds_{div}.bin'
            if p.exists() and time.time() - p.stat().st_mtime < 36 * 3600:
                oddsapi[div] = S.parse_oddsapi(p.read_bytes()) or []

    # ------------------------------------------------------------ 6. per league: fit, fixtures, predictions
    pre = {k: v for k, v in jload(STATE / 'pre_kickoff.json', {}).items() if k.count('|') == 4}   # v1 ids (no date) are dropped
    shown = jload(STATE / 'takim_adlari.json', {})            # ESPN's full club names (football-data uses short forms)
    log = PickLog(str(STATE))
    leagues, fixtures, unmapped, espn_map, parity = {}, [], {}, {}, []
    hot_next = False
    fnum = lambda x: None if x is None or x != x else float(x)
    for div in TARGET:
        df = D[D['div'] == div]
        # season label: July-June, except the full-time-only leagues whose files carry their own (e.g. calendar years)
        SEASON_L = int(df.season.max()) if (div in EXTRA and len(df)) else SEASON
        cur = df[(df.season == SEASON_L)]
        canon = sorted(set(cur.home) | set(cur.away)) or sorted(set(df[df.season == SEASON_L - 1].home))
        ext = {}
        for e in espn[div]:
            for side in ('home', 'away'):
                nm = [n for n in e[side]['names'] if n]
                if nm and not str(nm[0]).upper().startswith('TBD'):         # play-off placeholders
                    ext.setdefault(e[side]['id'], nm)
        mp, un, _ = build_map(div, ext, canon)
        espn_map[div] = mp
        if un:
            unmapped[div] = [ext[u][0] for u in un]
            alert('UYARI', names[div], 'ESPN takım adı eşleşmedi: ' + ', '.join(unmapped[div]) + ' (bu maçlar atlandı)')
        sh = shown.setdefault(div, {})
        for eid, c in mp.items():
            if ext[eid] and ext[eid][0]:
                sh[c] = ext[eid][0]
        disp = lambda t: DISPLAY.get(t) or sh.get(t) or display(t)
        # odds api names
        oa_ev = oddsapi.get(div, [])
        if oa_ev:
            omp, oun, _ = build_map(div, {n: [n] for e in oa_ev for n in (e['home'], e['away'])}, canon)
            if oun:
                alert('UYARI', 'Odds API', f'{names[div]}: eşleşmeyen ad: ' + ', '.join(oun))
        else:
            omp = {}
        # merge sources
        fx = {}
        for e in espn[div]:
            h, aw = mp.get(e['home']['id']), mp.get(e['away']['id'])
            if not h or not aw or not e['kickoff']:
                continue
            fx[(h, aw)] = {'kickoff': e['kickoff'], 'espn': e}
        for f in fd_fix:
            if f['div'] != div:
                continue
            k = (f['home'], f['away'])
            if f['home'] not in canon or f['away'] not in canon:
                alert('UYARI', names[div], f'oran dosyasında bilinmeyen takım: {f["home"]} - {f["away"]}'); continue
            if k in fx and abs((dt.datetime.fromisoformat(fx[k]['kickoff']) - dt.datetime.fromisoformat(f['kickoff'])).total_seconds()) > 2 * 86400:
                k = k + (f['kickoff'][:10],)          # same pairing on another date (leagues where clubs meet 3-4 times)
            fx.setdefault(k, {'kickoff': f['kickoff']})['fd'] = f
        for e in oa_ev:
            k = (omp.get(e['home']), omp.get(e['away']))
            if k in fx:
                fx[k]['oa'] = e
        ex_teams = {t for k in fx for t in k[:2]}
        fitter = LeagueFitter(df, CFG)
        fit = fitter.fit(cutoff, SEASON_L, extra_teams=sorted(ex_teams))
        has_c = fit['cmu'] is not None
        C = df[(df.season == SEASON_L) & df.fit_ok]
        teams = sorted(set(C.home) | set(C.away) | ex_teams)
        tab = []
        for t in teams:
            hh = C[C.home == t]; aa = C[C.away == t]
            w = int((hh.hg > hh.ag).sum() + (aa.ag > aa.hg).sum()); dr = int((hh.hg == hh.ag).sum() + (aa.ag == aa.hg).sum()); n = len(hh) + len(aa)
            tab.append(dict(team=t, name=disp(t), o=n, g=w, b=dr, m=n - w - dr, a=int(hh.hg.sum() + aa.ag.sum()), y=int(hh.ag.sum() + aa.hg.sum()), p=3 * w + dr))
        tab.sort(key=lambda r: (-r['p'], -(r['a'] - r['y']), -r['a'], r['team']))
        rank = {r['team']: i + 1 for i, r in enumerate(tab)}
        last_match = str(C.date.max().date()) if len(C) else None
        LG = S.LEAGUES[div]
        leagues[div] = dict(name=names[div], short=LG['short'], country=LG['country'], corners=has_c, ht=bool(fit['has_ht']),
                            mu=float(fit['mu']), gamma=float(fit['gamma']), cmu=fnum(fit['cmu']), cgamma=fnum(fit['cgamma']),
                            c_avg=fnum(fit['c_avg']), s1h=float(fit['s1_h']), s1a=float(fit['s1_a']), played=int(len(C)), last_match=last_match,
                            round=f'{int(round(2 * len(C) / max(len(teams), 1))) + 1}. hafta' if len(C) else '1. hafta',
                            base=base_all.get(div, {}), table=tab,
                            teams=[dict(id=t, name=disp(t), rank=rank[t], new=bool(fit['new'][fit['idx'][t]]),
                                        att=float(fit['att'][fit['idx'][t]]), de=float(fit['de'][fit['idx'][t]]),
                                        catt=fnum(fit['catt'][fit['idx'][t]]) if has_c else None,
                                        cde=fnum(fit['cde'][fit['idx'][t]]) if has_c else None) for t in teams])
        in_season = bool(fx) if div in EXTRA else (today.month >= 8 or today.month <= 5)
        if in_season and last_match and (today - dt.date.fromisoformat(last_match)).days > 16:
            alert('UYARI', names[div], f'football-data sonuçları bayat olabilir: son maç {last_match}')
        H = df[df.fit_ok]
        for key, src in sorted(fx.items(), key=lambda kv: (kv[1]['kickoff'], kv[0])):
            h, aw = key[0], key[1]
            ko = dt.datetime.fromisoformat(src['kickoff']).astimezone(UTC)
            if not (now - dt.timedelta(hours=36) <= ko <= now + dt.timedelta(days=AHEAD_DAYS)):
                continue
            e = src.get('espn')
            st = e['state'] if e else ('pre' if ko > now else 'unknown')
            if e and st == 'pre' and ko <= now - dt.timedelta(hours=3):
                st = 'unknown'
            postponed = bool(e and (e.get('status_name') or '').upper() in ('STATUS_POSTPONED', 'STATUS_CANCELED', 'STATUS_SUSPENDED', 'STATUS_ABANDONED'))
            if st in ('in',) or (st == 'pre' and ko - now <= dt.timedelta(hours=1)) or (now - dt.timedelta(hours=3) <= ko <= now):
                hot_next = True
            fid = f'{SEASON_L}|{div}|{h}|{aw}|{ko:%Y-%m-%d}'     # date included: in some leagues the same pairing is played twice
            ko_tr = ko.astimezone(TR)
            f = {'fid': fid, 'div': div, 'season': SEASON_L, 'home': h, 'away': aw, 'home_name': disp(h), 'away_name': disp(aw),
                 'kickoff': ko.isoformat(), 'date_tr': ko_tr.strftime('%Y-%m-%d'), 'time_tr': ko_tr.strftime('%H:%M'),
                 'state': 'postponed' if postponed else st}
            if e:
                f['live'] = {k: e.get(k) for k in ('hs', 'as', 'hht', 'aht', 'hc', 'ac', 'clock', 'detail', 'completed', 'period')}
                f['espn_id'] = e['id']
            # odds: ESPN (DraftKings, Bet365; read at every update), football-data (Bet365, Pinnacle, best, average),
            # The Odds API (best, average across more books)
            odds, srcs = {}, []
            if src.get('fd') and src['fd'].get('odds'):
                odds.update(src['fd']['odds']); srcs.append('football-data.co.uk')
            if e and e.get('odds'):
                odds.update(e['odds']); srcs.append('ESPN')
            if src.get('oa') and src['oa'].get('books'):
                sm = S.summarize_books(src['oa']['books'])
                for k in ('max', 'avg', 'pin'):
                    if sm.get(k):
                        odds.setdefault(k, {}).update(sm[k])
                odds['n_books'] = sm['n_books']; srcs.append('The Odds API')
            if odds:
                odds['_source'] = ' + '.join(srcs); odds['_seen'] = now.isoformat(timespec='seconds')
            f['odds'] = odds or None
            in_pre = fid in pre
            if f['state'] == 'pre' and ko > now:
                lh, la, ch, ca = predict_means(fit, h, aw)
                fh, fa, oinfo = odds_means(float(lh), float(la), f['odds'], ODDS_BLEND)
                inputs = dict(lh=float(fh), la=float(fa), ch=fnum(ch), ca=fnum(ca), c_avg=fnum(fit['c_avg']), s1h=float(fit['s1_h']), s1a=float(fit['s1_a']),
                              lh_model=float(lh), la_model=float(la), ht=bool(fit['has_ht']))
                facts = match_facts(C, H, h, aw, disp(h), disp(aw), cutoff)
                basis = 'güncel'
            elif in_pre:
                inputs, facts = pre[fid]['inputs'], pre[fid].get('facts', [])
                oinfo = pre[fid].get('odds_basis')
                f['odds_last'] = pre[fid].get('odds_last')
                basis = 'maç öncesi'
            else:
                lh, la, ch, ca = predict_means(fit, h, aw)
                fh, fa, oinfo = odds_means(float(lh), float(la), f['odds'], ODDS_BLEND)
                inputs = dict(lh=float(fh), la=float(fa), ch=fnum(ch), ca=fnum(ca), c_avg=fnum(fit['c_avg']), s1h=float(fit['s1_h']), s1a=float(fit['s1_a']),
                              lh_model=float(lh), la_model=float(la), ht=bool(fit['has_ht']))
                facts = []
                basis = 'maç başladıktan sonra hesaplandı'
            f['pred_basis'] = basis
            X = pd.DataFrame([dict({k: inputs.get(k) for k in ('lh', 'la', 'ch', 'ca', 'c_avg', 's1h', 's1a')}, ht=inputs.get('ht', True), hg=0, ag=0, hthg=0, htag=0, hc=0, ac=0)])
            q = predict_all(X, cal).iloc[0].to_dict()
            m = market_probs(q)
            base = leagues[div]['base']
            bk = pick_banko(m); sp = pick_surprise(m, base)
            f['pred'] = {'inputs': inputs, 'banko': list(bk) if bk else None, 'surpriz': list(sp) if sp else None,
                         'exp_g': float(q['exp_g']), 'exp_g1': float(q['exp_g1']), 'exp_c': fnum(q.get('exp_c')), 'exp_c1': fnum(q.get('exp_c1')),
                         'odds_basis': oinfo}
            parity.append({'div': div, 'inputs': inputs, 'markets': {k: float(v) for k, v in m.items()}, 'banko': f['pred']['banko'], 'surpriz': f['pred']['surpriz']})
            if basis == 'güncel':
                newp = {'inputs': inputs, 'facts': facts, 'kickoff': f['kickoff'], 'odds_last': f['odds'] or (pre.get(fid, {}).get('odds_last')),
                        'odds_basis': oinfo, 'home_name': f['home_name'], 'away_name': f['away_name'],
                        'picks': {'BANKO': list(bk) if bk else None, 'SÜRPRİZ': (list(sp) + [base.get(sp[0])]) if sp else None}}
                old = pre.get(fid, {})
                strip = lambda d: {k: ({x: y for x, y in v.items() if x != '_seen'} if k == 'odds_last' and isinstance(v, dict) else v) for k, v in d.items()}
                if strip({k: old.get(k) for k in newp}) != strip(newp):      # rewrite only when something changed (quiet git history)
                    pre[fid] = dict(newp, saved=now.isoformat(timespec='seconds'))
            f['facts'] = facts
            f['rank_h'] = rank.get(h); f['rank_a'] = rank.get(aw)
            fixtures.append(f)
    jdump(shown, STATE / 'takim_adlari.json')

    # ------------------------------------------------------------ 7. picks: record the last pre-match pick, settle, performance
    recorded = log.finalize(pre, fixtures, now, names)
    settled = log.settle(D, now)
    perf, T = log.performance(now)
    done = log.recorded_fids()
    for f in fixtures:
        lk = log.locked_for(f['fid'])
        f['locked'] = [{'tur': p['tur'], 'pazar': p['pazar'], 'olasilik': float(p['olasilik']), 'kilit_utc': p['kilit_utc']} for p in lk]
        if f.get('locked'):
            ids = [p['id'] for p in lk]
            rr = T[T.id.isin(ids)][['tur', 'durum']].dropna()
            f['settled'] = dict(zip(rr.tur, rr.durum))
    # keep pre-match snapshots for 10 days (30 while a match is still unrecorded, e.g. postponed)
    pre = {k: v for k, v in pre.items() if dt.datetime.fromisoformat(v['kickoff']) > now - dt.timedelta(days=10 if k in done else 30)}
    jdump(pre, STATE / 'pre_kickoff.json')
    state['espn_hot'] = hot_next

    # ------------------------------------------------------------ 8. site payload
    def ts(x):
        return dt.datetime.fromtimestamp(x, UTC).isoformat(timespec='seconds') if x else None
    hs = state.get('http', {})
    sources = {
        'football-data': {'ok': ts(max([hs.get(f'fd_{code}_{d}', {}).get('ok') or 0 for d in TARGET]) or None), 'son_mac': {d: leagues[d]['last_match'] for d in TARGET}},
        'oranlar': {'ok': ts(hs.get('fd_fixtures', {}).get('ok')), 'mac_sayisi': len([f for f in fixtures if f.get('odds')]),
                    'orana_dayali': len([f for f in fixtures if (f.get('pred') or {}).get('odds_basis')])},
        'espn': {'ok': ts(max([espn_ok.get(d) or 0 for d in TARGET]) or None), 'cors': bool(cors),
                 'ligsiz': [d for d in TARGET if not S.LEAGUES[d]['espn']]},
        'odds_api': {'aktif': bool(key), 'kalan': oa.get('remaining'), 'bu_ay': oa.get('used_this_month', 0)},
    }
    data = {
        'meta': {'generated': now.isoformat(timespec='seconds'), 'cutoff': str(today), 'model': CFG, 'cal': cal, 'odds_blend': ODDS_BLEND,
                 'rules': {'banko_menu': BANKO_MENU, 'banko_min': BANKO_MIN, 'banko_max': BANKO_MAX, 'surprise_menu': SURPRISE_MENU,
                           'surprise_min_p': SURPRISE_MIN_P, 'surprise_min_lift': SURPRISE_MIN_LIFT},
                 'sources': sources, 'alerts': alerts, 'espn_slugs': {d: S.LEAGUES[d]['espn'] for d in TARGET if S.LEAGUES[d]['espn']},
                 'espn_map': espn_map, 'order': TARGET, 'ahead_days': AHEAD_DAYS,
                 'new_rows': log.new_rows, 'recorded_now': len(recorded), 'settled_now': len(settled)},
        'leagues': leagues, 'fixtures': fixtures, 'track': perf,
        'backtest': jload(FROZEN / 'backtest.json', {}), 'ht_corner': jload(FROZEN / 'ht_corner_check.json', {}),
        'audit': {'rows_in': audit['rows_in'], 'rows_out': audit['rows_out'], 'fit_rows': audit['fit_rows'], 'issues': audit['issues']},
    }
    SITE.mkdir(exist_ok=True)
    jdump(data, SITE / 'data.json')
    tpl = (ROOT / 'site' / 'template.html').read_text(encoding='utf-8')
    eng = (ROOT / 'site' / 'engine.js').read_text(encoding='utf-8')
    blob = json.dumps(data, ensure_ascii=False, separators=(',', ':'), default=_jdef).replace('</', '<\\/')
    (SITE / 'index.html').write_text(tpl.replace('/*__ENGINE__*/', eng).replace('/*__DATA__*/', 'window.DATA=' + blob + ';'), encoding='utf-8')
    (SITE / '.nojekyll').write_text('')
    if not T.empty:
        T.drop(columns=['lh', 'la', 'ch', 'ca', 'c_avg', 's1h', 's1a'], errors='ignore').to_csv(SITE / 'tahmin_kaydi.csv', index=False)
        try:
            from tracker_xlsx import build as build_xlsx
            build_xlsx(T, SITE / 'Tahmin_Takip.xlsx', perf)
        except Exception as ex:
            alert('BİLGİ', 'Excel', f'takip dosyası üretilemedi: {ex}')
    # parity reference for site/parity_test.js (not published)
    jdump({'meta': data['meta'], 'leagues': {d: {'base': leagues[d]['base']} for d in leagues}, 'fixtures': parity}, CACHE / 'parity.json')

    # ------------------------------------------------------------ 9. change detection for deploy
    core = json.dumps({k: v for k, v in data.items() if k != 'meta'}, sort_keys=True, default=_jdef, ensure_ascii=False)
    h = hashlib.sha256(core.encode()).hexdigest()
    deploy = a.force or h != state.get('last_hash') or (time.time() - state.get('last_deploy', 0)) > 3 * 3600
    state['last_hash'] = h
    if deploy:
        state['last_deploy'] = time.time()
    jdump(state, CACHE / 'state.json')
    if os.environ.get('GITHUB_OUTPUT'):
        with open(os.environ['GITHUB_OUTPUT'], 'a') as g:
            g.write(f'deploy={"true" if deploy else "false"}\n')
    # ------------------------------------------------------------ 10. report
    acts = {}
    for x in http.log:
        acts[x['action']] = acts.get(x['action'], 0) + 1
    print(f'[{now_tr:%Y-%m-%d %H:%M} TSİ] istekler: {acts} | maç: {len(fixtures)} (oranlı {sources["oranlar"]["mac_sayisi"]}, '
          f'tahmini orana dayalı {sources["oranlar"]["orana_dayali"]}) | kayda geçen seçim: {len(recorded)} | sonuçlanan: {len(settled)} | '
          f'ESPN CORS: {cors} | yayın: {deploy}')
    for x in http.log:
        if x['action'] in ('indirildi', 'hata', 'değişmedi', 'sınır'):
            print('  ', x['action'], x['key'], x.get('bytes', ''), x.get('error', ''), x.get('headers', ''))
    for al in alerts:
        print(f"  [{al['seviye']}] {al['kapsam']}: {al['mesaj']}")
    for d in state.get('espn_diag', []):
        print('   ESPN tanı:', d)
    if any(al['seviye'] == 'HATA' for al in alerts):
        print('::warning::Veri hataları var; ayrıntı data.json → meta.alerts')


if __name__ == '__main__':
    main()
