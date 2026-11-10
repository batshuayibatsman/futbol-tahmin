"""'İlginç istatistikler': descriptive facts from the current season and head-to-head history.
Every candidate fact gets a deterministic 'remarkability' score (how far it is from the league norm,
in standard-error units); the three strongest are shown. They are context only, the model does not use them."""
import numpy as np, pandas as pd


def fmt(x, d=1):
    return f'{x:.{d}f}'.replace('.', ',')


def team_rows(C, t):
    h = C[C.home == t].assign(gf=lambda d: d.hg, ga=lambda d: d.ag, gf1=lambda d: d.hthg, ga1=lambda d: d.htag, cf=lambda d: d.hc, ca=lambda d: d.ac, ven='H')
    a = C[C.away == t].assign(gf=lambda d: d.ag, ga=lambda d: d.hg, gf1=lambda d: d.htag, ga1=lambda d: d.hthg, cf=lambda d: d.ac, ca=lambda d: d.hc, ven='A')
    return pd.concat([h, a]).sort_values('date')


def league_norms(C):
    tm = pd.concat([C.assign(gf=C.hg, ga=C.ag, cf=C.hc, ca=C.ac), C.assign(gf=C.ag, ga=C.hg, cf=C.ac, ca=C.hc)])
    tot = C.hg + C.ag
    return {'gpm': tm.gf.mean(), 'gsd': tm.gf.std(), 'cpm': tm.cf.mean(), 'csd': tm.cf.std(),
            'o25': (tot > 2.5).mean(), 'btts': ((C.hg > 0) & (C.ag > 0)).mean(),
            's1': (C.hthg + C.htag).sum() / max(tot.sum(), 1), 'cs': (tm.ga == 0).mean(), 'fts': (tm.gf == 0).mean(),
            'home_gpm': C.hg.mean(), 'away_gpm': C.ag.mean(), 'hsd': C.hg.std(), 'asd': C.ag.std()}


def facts_for_team(C, t, name, L, venue):
    R = team_rows(C, t); n = len(R); out = []
    if n < 5:
        return out
    z = lambda x, mu, sd, k: (x - mu) / (sd / np.sqrt(k))
    zb = lambda k, m, p: (k / m - p) / np.sqrt(p * (1 - p) / m)
    gf, ga = R.gf.mean(), R.ga.mean()
    s = z(gf, L['gpm'], L['gsd'], n)
    out.append((abs(s), f'{name}: maç başına {fmt(gf)} gol atıyor (lig ort. {fmt(L["gpm"])})' if gf >= L['gpm'] else f'{name}: {n} maçta yalnızca {int(R.gf.sum())} gol attı (maç başına {fmt(gf)})', t))
    s = z(ga, L['gpm'], L['gsd'], n)
    out.append((abs(s), f'{name}: maç başına {fmt(ga)} gol yiyor (lig ort. {fmt(L["gpm"])})' if ga >= L['gpm'] else f'{name}: {n} maçta yalnızca {int(R.ga.sum())} gol yedi', t))
    k = int(((R.gf + R.ga) > 2.5).sum())
    out.append((abs(zb(k, n, L['o25'])), f'{name}: {n} maçta {k} kez 2,5 üst' + ('' if k / n >= L['o25'] else f' (lig ort. %{round(100 * L["o25"])})'), t))
    k = int(((R.gf > 0) & (R.ga > 0)).sum())
    out.append((abs(zb(k, n, L['btts'])) * 0.9, f'{name}: {n} maçta {k} kez karşılıklı gol', t))
    k = int((R.ga == 0).sum())
    if k / n > L['cs']:
        out.append((zb(k, n, L['cs']), f'{name}: {n} maçta {k} kez kalesini gole kapattı', t))
    k = int((R.gf == 0).sum())
    if k / n > L['fts']:
        out.append((zb(k, n, L['fts']), f'{name}: {n} maçta {k} kez gol atamadı', t))
    cf, ca = R.cf.mean(), R.ca.mean()
    out.append((abs(z(cf, L['cpm'], L['csd'], n)), f'{name}: maç başına {fmt(cf)} korner kullanıyor (lig ort. {fmt(L["cpm"])})', t))
    out.append((abs(z(ca, L['cpm'], L['csd'], n)) * 0.9, f'{name}: rakiplerine maç başına {fmt(ca)} korner veriyor (lig ort. {fmt(L["cpm"])})', t))
    G = int((R.gf + R.ga).sum()); G1 = int((R.gf1 + R.ga1).sum())
    if G >= 12:
        out.append((abs(zb(G1, G, L['s1'])), f'{name} maçlarındaki goller: ilk yarı {G1}, ikinci yarı {G - G1}', t))
    beh = R[R.gf1 < R.ga1]
    if len(beh) >= 3:
        k = int((beh.gf >= beh.ga).sum())
        out.append((k / len(beh) * 2.2 if k >= 2 else 0, f'{name}: devreyi geride kapattığı {len(beh)} maçta {k} kez puan aldı', t))
    lead = R[R.gf1 > R.ga1]
    if len(lead) >= 3:
        k = int((lead.gf <= lead.ga).sum())
        out.append((k / len(lead) * 2.2 if k >= 2 else 0, f'{name}: devreyi önde kapattığı {len(lead)} maçta {k} kez kazanamadı', t))
    V = R[R.ven == venue]
    if len(V) >= 4:
        mu, sd = (L['home_gpm'], L['hsd']) if venue == 'H' else (L['away_gpm'], L['asd'])
        lab = 'iç sahada' if venue == 'H' else 'deplasmanda'
        w = int((V.gf > V.ga).sum()); d = int((V.gf == V.ga).sum()); l = len(V) - w - d
        out.append((abs(z(V.gf.mean(), mu, sd, len(V))), f'{name}: {lab} {len(V)} maçta {int(V.gf.sum())} gol attı, {int(V.ga.sum())} gol yedi ({w}G {d}B {l}M)', t))
    res = np.sign(R.gf.values - R.ga.values)[::-1]
    def run(cond):
        c = 0
        for v in res:
            if cond(v): c += 1
            else: break
        return c
    w, ub, wl, ls = run(lambda v: v > 0), run(lambda v: v >= 0), run(lambda v: v <= 0), run(lambda v: v < 0)
    if w >= 3: out.append((0.9 + 0.35 * w, f'{name}: üst üste {w} maçtır kazanıyor', t))
    elif ub >= 5: out.append((0.6 + 0.3 * ub, f'{name}: {ub} maçtır yenilmiyor', t))
    if ls >= 3: out.append((0.9 + 0.35 * ls, f'{name}: üst üste {ls} maçtır kaybediyor', t))
    elif wl >= 5: out.append((0.6 + 0.3 * wl, f'{name}: {wl} maçtır kazanamıyor', t))
    return out


def h2h_fact(H, home, away, hn, an, date):
    m = H[(((H.home == home) & (H.away == away)) | ((H.home == away) & (H.away == home))) & (H.date < date)].sort_values('date').tail(6)
    if len(m) < 4:
        return None
    gh = np.where(m.home == home, m.hg, m.ag); ga = np.where(m.home == home, m.ag, m.hg)
    w = int((gh > ga).sum()); d = int((gh == ga).sum()); l = len(m) - w - d; g = (m.hg + m.ag).mean()
    txt = f'Aralarındaki son {len(m)} lig maçı: {hn} {w}G {d}B {l}M, maç başına {fmt(g)} gol'
    sc = 0.0
    if max(w, l) >= len(m) - 1: sc = max(sc, 2.4)
    elif max(w, l) >= len(m) - 2 and min(w, l) == 0: sc = max(sc, 1.8)
    if g >= 3.5 or g <= 1.5: sc = max(sc, 1.9)
    return (sc, txt, 'h2h') if sc > 0 else None


def match_facts(C, H, home, away, hn, an, date, k=3, min_score=1.5):
    L = league_norms(C)
    cand = facts_for_team(C, home, hn, L, 'H') + facts_for_team(C, away, an, L, 'A')
    f = h2h_fact(H, home, away, hn, an, date)
    if f: cand.append(f)
    cand = [c for c in cand if c[0] >= min_score]
    cand.sort(key=lambda c: -c[0])            # stable sort keeps candidate order on ties
    out, per = [], {}
    for sc, txt, who in cand:
        if per.get(who, 0) >= (1 if who == 'h2h' else 2):
            continue
        out.append({'text': txt, 'score': round(float(sc), 2)}); per[who] = per.get(who, 0) + 1
        if len(out) == k:
            break
    return out
