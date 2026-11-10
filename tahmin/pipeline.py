"""Scheduled job (GitHub Actions): fetch -> validate -> fit -> predict -> lock / settle picks -> build the site.
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
from config import CFG, TARGET
from model import LeagueFitter, predict_means, match_distribution, summarize, apply_htft_cal
from probs import predict_all
from markets import (market_probs, pick_banko, pick_surprise, BANKO_MENU, BANKO_MIN, BANKO_MAX,
                     SURPRISE_MENU, SURPRISE_MIN_P, SURPRISE_MIN_LIFT)
from stats import match_facts
import sources as S
from names import build_map, display
from dataset import load as load_dataset
from picks import PickLog, LOCK_HOURS

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
    for div in TARGET:
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

    # ------------------------------------------------------------ 2. football-data fixtures (odds)
    uk = now.astimezone(UK)
    fx_min = 60 if (uk.weekday() in (1, 4) and uk.hour >= 12) else FD_MIN
    b, info = http.get('fd_fixtures', S.FD_FIXTURES, fx_min)
    fd_fix = S.parse_fd_fixtures(b, set(TARGET), alerts) if b else []
    if info.get('action') == 'hata':
        alert('UYARI', 'Oranlar', f'football-data fikstür/oran dosyası indirilemedi ({info.get("error")})')
    fd_fix_seen = state['http'].get('fd_fixtures', {}).get('ok')

    # ------------------------------------------------------------ 3. ESPN fixtures + live
    hot = state.get('espn_hot', True)
    d0 = (now - dt.timedelta(days=2)).strftime('%Y%m%d'); d1 = (now + dt.timedelta(days=AHEAD_DAYS)).strftime('%Y%m%d')
    espn, espn_ok, cors = {}, {}, state.get('espn_cors')
    origin = a.site_origin or 'https://example.github.io'
    for div in TARGET:
        b, info = http.get(f'espn_{div}', S.ESPN.format(slug=S.LEAGUES[div]['espn'], d0=d0, d1=d1), ESPN_HOT_MIN if hot else ESPN_COLD_MIN,
                           conditional=False, headers={'Origin': origin})
        if info.get('action') == 'indirildi':
            acao = (info.get('headers') or {}).get('access-control-allow-origin')
            cors = bool(acao and (acao == '*' or acao == origin))
        if info.get('action') == 'hata':
            alert('UYARI', names[div], f'ESPN fikstür/canlı skor alınamadı ({info.get("error")})')
        evs = S.parse_espn(b) if b else None
        if b and evs is None:
            alert('UYARI', names[div], 'ESPN yanıtı okunamadı')
        espn[div] = evs or []
        espn_ok[div] = state['http'].get(f'espn_{div}', {}).get('ok')
    state['espn_cors'] = cors

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
        for div in TARGET:
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
    pre = jload(STATE / 'pre_kickoff.json', {})
    log = PickLog(str(STATE))
    leagues, fixtures, unmapped, espn_map = {}, [], {}, {}
    hot_next = False
    for div in TARGET:
        df = D[D['div'] == div]
        cur = df[(df.season == SEASON)]
        canon = sorted(set(cur.home) | set(cur.away)) or sorted(set(df[df.season == SEASON - 1].home))
        ext = {}
        for e in espn[div]:
            for side in ('home', 'away'):
                ext.setdefault(e[side]['id'], [n for n in e[side]['names'] if n])
        mp, un, _ = build_map(div, ext, canon)
        espn_map[div] = mp
        if un:
            unmapped[div] = [ext[u][0] for u in un]
            alert('UYARI', names[div], 'ESPN takım adı eşleşmedi: ' + ', '.join(unmapped[div]) + ' (bu maçlar atlandı)')
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
            fx.setdefault(k, {'kickoff': f['kickoff']})['fd'] = f
        for e in oa_ev:
            k = (omp.get(e['home']), omp.get(e['away']))
            if k in fx:
                fx[k]['oa'] = e
        ex_teams = {t for k in fx for t in k}
        fitter = LeagueFitter(df, CFG)
        fit = fitter.fit(cutoff, SEASON, extra_teams=sorted(ex_teams))
        C = df[(df.season == SEASON) & df.fit_ok]
        teams = sorted(set(C.home) | set(C.away) | ex_teams)
        tab = []
        for t in teams:
            hh = C[C.home == t]; aa = C[C.away == t]
            w = int((hh.hg > hh.ag).sum() + (aa.ag > aa.hg).sum()); dr = int((hh.hg == hh.ag).sum() + (aa.ag == aa.hg).sum()); n = len(hh) + len(aa)
            tab.append(dict(team=t, name=display(t), o=n, g=w, b=dr, m=n - w - dr, a=int(hh.hg.sum() + aa.ag.sum()), y=int(hh.ag.sum() + aa.hg.sum()), p=3 * w + dr))
        tab.sort(key=lambda r: (-r['p'], -(r['a'] - r['y']), -r['a'], r['team']))
        rank = {r['team']: i + 1 for i, r in enumerate(tab)}
        last_match = str(C.date.max().date()) if len(C) else None
        leagues[div] = dict(name=names[div], mu=float(fit['mu']), gamma=float(fit['gamma']), cmu=float(fit['cmu']), cgamma=float(fit['cgamma']),
                            c_avg=float(fit['c_avg']), s1h=float(fit['s1_h']), s1a=float(fit['s1_a']), played=int(len(C)), last_match=last_match,
                            round=f'{int(round(2 * len(C) / max(len(teams), 1))) + 1}. hafta' if len(C) else '1. hafta',
                            base=base_all.get(div, {}), table=tab,
                            teams=[dict(id=t, name=display(t), rank=rank[t], new=bool(fit['new'][fit['idx'][t]]),
                                        att=float(fit['att'][fit['idx'][t]]), de=float(fit['de'][fit['idx'][t]]),
                                        catt=float(fit['catt'][fit['idx'][t]]), cde=float(fit['cde'][fit['idx'][t]])) for t in teams])
        in_season = today.month >= 8 or today.month <= 5
        if in_season and last_match and (today - dt.date.fromisoformat(last_match)).days > 16:
            alert('UYARI', names[div], f'football-data sonuçları bayat olabilir: son maç {last_match}')
        H = df[df.fit_ok]
        for (h, aw), src in sorted(fx.items(), key=lambda kv: (kv[1]['kickoff'], kv[0])):
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
            fid = f'{SEASON}|{div}|{h}|{aw}'
            ko_tr = ko.astimezone(TR)
            f = {'fid': fid, 'div': div, 'season': SEASON, 'home': h, 'away': aw, 'home_name': display(h), 'away_name': display(aw),
                 'kickoff': ko.isoformat(), 'date_tr': ko_tr.strftime('%Y-%m-%d'), 'time_tr': ko_tr.strftime('%H:%M'),
                 'state': 'postponed' if postponed else st, 'base': leagues[div]['base']}
            if e:
                f['live'] = {k: e.get(k) for k in ('hs', 'as', 'hht', 'aht', 'hc', 'ac', 'clock', 'detail', 'completed', 'period')}
                f['espn_id'] = e['id']
                if e.get('odds'):
                    f['espn_odds'] = e['odds']
            # odds: football-data (B365, Pinnacle, best, average) and The Odds API (best, average across more books)
            odds = {}
            if src.get('fd') and src['fd'].get('odds'):
                odds.update(src['fd']['odds']); odds['_source'] = 'football-data.co.uk'; odds['_seen'] = dt.datetime.fromtimestamp(fd_fix_seen or time.time(), UTC).isoformat(timespec='seconds')
            if src.get('oa') and src['oa'].get('books'):
                sm = S.summarize_books(src['oa']['books'])
                for k in ('max', 'avg', 'pin'):
                    if sm.get(k):
                        odds.setdefault(k, {}).update(sm[k])
                odds['_source'] = (odds.get('_source', '') + ' + The Odds API').strip(' +'); odds['n_books'] = sm['n_books']
                odds['_seen'] = dt.datetime.fromtimestamp(oa.get('last', {}).get(div, time.time()), UTC).isoformat(timespec='seconds')
            f['odds'] = odds or None
            in_pre = fid in pre
            if f['state'] == 'pre' and ko > now:
                lh, la, ch, ca = predict_means(fit, h, aw)
                inputs = dict(lh=float(lh), la=float(la), ch=float(ch), ca=float(ca), c_avg=float(fit['c_avg']), s1h=float(fit['s1_h']), s1a=float(fit['s1_a']))
                facts = match_facts(C, H, h, aw, display(h), display(aw), cutoff)
                pre[fid] = {'inputs': inputs, 'saved': now.isoformat(timespec='seconds'), 'facts': facts, 'kickoff': f['kickoff'],
                            'odds_last': f['odds'] or (pre.get(fid, {}).get('odds_last'))}
                f['pred_basis'] = 'güncel'
            elif in_pre:
                inputs, facts = pre[fid]['inputs'], pre[fid].get('facts', [])
                f['odds_last'] = pre[fid].get('odds_last')
                f['pred_basis'] = 'maç öncesi'
            else:
                lh, la, ch, ca = predict_means(fit, h, aw)
                inputs = dict(lh=float(lh), la=float(la), ch=float(ch), ca=float(ca), c_avg=float(fit['c_avg']), s1h=float(fit['s1_h']), s1a=float(fit['s1_a']))
                facts = []
                f['pred_basis'] = 'maç başladıktan sonra hesaplandı'
            X = pd.DataFrame([dict(inputs, hg=0, ag=0, hthg=0, htag=0, hc=0, ac=0)])
            q = predict_all(X, cal).iloc[0].to_dict()
            m = market_probs(q)
            bk = pick_banko(m); sp = pick_surprise(m, leagues[div]['base'])
            f['pred'] = {'inputs': inputs, 'markets': {k: float(v) for k, v in m.items()}, 'banko': list(bk) if bk else None,
                         'surpriz': list(sp) if sp else None, 'exp_g': float(q['exp_g']), 'exp_g1': float(q['exp_g1']),
                         'exp_c': float(q['exp_c']), 'exp_c1': float(q['exp_c1'])}
            f['facts'] = facts
            f['rank_h'] = rank.get(h); f['rank_a'] = rank.get(aw)
            fixtures.append(f)

    # prune pre-kickoff cache: keep only fixtures from the last 10 days
    pre = {k: v for k, v in pre.items() if dt.datetime.fromisoformat(v['kickoff']) > now - dt.timedelta(days=10)}
    jdump(pre, STATE / 'pre_kickoff.json')
    state['espn_hot'] = hot_next

    # ------------------------------------------------------------ 7. picks: lock, odds, settle, performance
    locked = log.lock(fixtures, now, names)
    log.observe_odds(fixtures, now)
    settled = log.settle(D, now)
    perf, T = log.performance(now)
    for f in fixtures:
        lk = log.locked_for(f['fid'])
        f['locked'] = [{'tur': p['tur'], 'pazar': p['pazar'], 'olasilik': float(p['olasilik']), 'kilit_utc': p['kilit_utc']} for p in lk]
        f['lock_due'] = (dt.datetime.fromisoformat(f['kickoff']) - dt.timedelta(hours=LOCK_HOURS)).isoformat()
        if f.get('locked'):
            ids = [p['id'] for p in lk]
            rr = T[T.id.isin(ids)][['tur', 'durum']].dropna()
            f['settled'] = dict(zip(rr.tur, rr.durum))

    # ------------------------------------------------------------ 8. site payload
    def ts(x):
        return dt.datetime.fromtimestamp(x, UTC).isoformat(timespec='seconds') if x else None
    hs = state.get('http', {})
    sources = {
        'football-data': {'ok': ts(max([hs.get(f'fd_{code}_{d}', {}).get('ok') or 0 for d in TARGET]) or None), 'son_mac': {d: leagues[d]['last_match'] for d in TARGET}},
        'oranlar': {'ok': ts(hs.get('fd_fixtures', {}).get('ok')), 'mac_sayisi': len([f for f in fixtures if f.get('odds')])},
        'espn': {'ok': ts(max([hs.get(f'espn_{d}', {}).get('ok') or 0 for d in TARGET]) or None), 'cors': bool(cors)},
        'odds_api': {'aktif': bool(key), 'kalan': oa.get('remaining'), 'bu_ay': oa.get('used_this_month', 0)},
    }
    data = {
        'meta': {'generated': now.isoformat(timespec='seconds'), 'cutoff': str(today), 'model': CFG, 'cal': cal, 'lock_hours': LOCK_HOURS,
                 'rules': {'banko_menu': BANKO_MENU, 'banko_min': BANKO_MIN, 'banko_max': BANKO_MAX, 'surprise_menu': SURPRISE_MENU,
                           'surprise_min_p': SURPRISE_MIN_P, 'surprise_min_lift': SURPRISE_MIN_LIFT},
                 'sources': sources, 'alerts': alerts, 'espn_slugs': {d: S.LEAGUES[d]['espn'] for d in TARGET},
                 'espn_map': espn_map, 'order': TARGET, 'ahead_days': AHEAD_DAYS,
                 'new_rows': log.new_rows, 'locked_now': len(locked), 'settled_now': len(settled)},
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
    par = [{'div': f['div'], 'inputs': f['pred']['inputs'], 'markets': f['pred']['markets'], 'banko': f['pred']['banko'], 'surpriz': f['pred']['surpriz']} for f in fixtures]
    jdump({'meta': data['meta'], 'leagues': {d: {'base': leagues[d]['base']} for d in leagues}, 'fixtures': par}, CACHE / 'parity.json')

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
    print(f'[{now_tr:%Y-%m-%d %H:%M} TSİ] istekler: {acts} | maç: {len(fixtures)} (oranlı {sources["oranlar"]["mac_sayisi"]}) | '
          f'kilitlenen: {len(locked)} | sonuçlanan: {len(settled)} | ESPN CORS: {cors} | yayın: {deploy}')
    for x in http.log:
        if x['action'] in ('indirildi', 'hata', 'değişmedi', 'sınır'):
            print('  ', x['action'], x['key'], x.get('bytes', ''), x.get('error', ''), x.get('headers', ''))
    for al in alerts:
        print(f"  [{al['seviye']}] {al['kapsam']}: {al['mesaj']}")
    if any(al['seviye'] == 'HATA' for al in alerts):
        print('::warning::Veri hataları var; ayrıntı data.json → meta.alerts')


if __name__ == '__main__':
    main()
