"""Bookmaker odds -> goal means (v2, Kasım 2026). Deterministic: fixed-iteration bisection, no random numbers.

The margin is removed proportionally. The total-goals line gives the expected total T (P(goals > line) under a Poisson
total) and P(home) - P(away) gives the home share r (independent Poisson goals with means T*r and T*(1-r)).
Without a total-goals price T comes from the 1X2 odds as well: P(draw) and P(home) - P(away) fix T and r together;
independent Poisson gives too few draws, so T is scaled by DRAW_TOTAL_SCALE (chosen on 2021-23 against the 2.5-goal
prices; it was closer to the market total than the statistics model and better on the 16 full-time-only leagues,
research/v2/draw_total.py).
The result is blended with the statistics model with config.ODDS_BLEND (research/v2/blend.py: weight 1 = odds only
was the most accurate on 2021-23 and on the untouched 2024-26 seasons).
Identical to research/v2/blend.py (vectorised there)."""
import math
import numpy as np
from model import pois_vec

# preference order: the freshest prices first (ESPN is read at every update; football-data adds odds twice a week)
ORDER_1X2 = [('dk', 'DraftKings (ESPN)'), ('b365e', 'Bet365 (ESPN)'), ('b365', 'Bet365'), ('avg', 'piyasa ortalaması'),
             ('pin', 'Pinnacle'), ('max', 'en iyi oranlar')]
ORDER_TOTAL = [('dk', 'DraftKings (ESPN)'), ('b365', 'Bet365'), ('avg', 'piyasa ortalaması'), ('pin', 'Pinnacle'), ('max', 'en iyi oranlar')]
ITER = 60
DRAW_TOTAL_SCALE = 1.1111


def _ok(x):
    return x is not None and x == x and x > 1.0


def choose(odds):
    """odds: {book: {'1','X','2', 'Ü2.5','A2.5'} or for ESPN/DraftKings {'1','X','2','line','Ü','A'}}.
    Returns {'1','X','2','src'} plus optionally {'line','over','under','src_total'}, or None without a full 1X2 price."""
    if not odds:
        return None
    out = None
    for key, label in ORDER_1X2:
        v = odds.get(key) or {}
        if all(_ok(v.get(s)) for s in ('1', 'X', '2')):
            out = {'1': float(v['1']), 'X': float(v['X']), '2': float(v['2']), 'src': label}
            break
    if out is None:
        return None
    for key, label in ORDER_TOTAL:
        v = odds.get(key) or {}
        if key == 'dk':
            line = v.get('line')
            if line is not None and abs(line * 2 - round(line * 2)) < 1e-9 and round(line * 2) % 2 == 1 and _ok(v.get('Ü')) and _ok(v.get('A')):
                out.update(line=float(line), over=float(v['Ü']), under=float(v['A']), src_total=label)
                break
        elif _ok(v.get('Ü2.5')) and _ok(v.get('A2.5')):
            out.update(line=2.5, over=float(v['Ü2.5']), under=float(v['A2.5']), src_total=label)
            break
    return out


def _p_over(T, line):
    c = pois_vec(T)
    return 1.0 - float(c[:int(math.floor(line)) + 1].sum())


def _hda(lh, la):
    M = np.outer(pois_vec(lh), pois_vec(la))
    return float(np.tril(M, -1).sum()), float(np.trace(M)), float(np.triu(M, 1).sum())


def _split(T, target, it=ITER):
    lo, hi = 0.01, 0.99
    for _ in range(it):
        mid = (lo + hi) / 2
        a, _, c = _hda(T * mid, T * (1 - mid))
        if (a - c) - target < 0:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def total_from_1x2(p1, px, p2, it=40):
    """Expected total goals from margin-free 1X2 probabilities (draw probability falls as the total rises)."""
    target = p1 - p2
    lo, hi = 0.6, 7.0
    for _ in range(it):
        T = (lo + hi) / 2
        r = _split(T, target, it)
        _, d, _ = _hda(T * r, T * (1 - r))
        if d > px:
            lo = T
        else:
            hi = T
    return DRAW_TOTAL_SCALE * (lo + hi) / 2


def implied_means(o1, ox, o2, over=None, under=None, line=2.5):
    """Goal means (home, away) implied by the odds."""
    q = np.array([1 / o1, 1 / ox, 1 / o2]); p = q / q.sum()
    target = float(p[0] - p[2])
    if over and under:
        po = (1 / over) / (1 / over + 1 / under)
        lo, hi = 0.2, 8.0
        for _ in range(ITER):
            mid = (lo + hi) / 2
            if _p_over(mid, line) - po < 0:
                lo = mid
            else:
                hi = mid
        T = (lo + hi) / 2
    else:
        T = total_from_1x2(float(p[0]), float(p[1]), float(p[2]))
    r = _split(T, target)
    return T * r, T * (1 - r)


def blend(lh, la, mh, ma, wr, wt):
    T = math.exp((1 - wt) * math.log(lh + la) + wt * math.log(mh + ma))
    R = (1 - wr) * math.log(lh / la) + wr * math.log(mh / ma)
    return T * math.exp(R) / (1 + math.exp(R)), T / (1 + math.exp(R))


def odds_means(lh, la, odds, w):
    """(final home mean, final away mean, info). info is None when the match has no usable odds.
    lh/la None: competition without a statistics model (odds only)."""
    c = choose(odds)
    if c is None:
        return lh, la, None
    mh, ma = implied_means(c['1'], c['X'], c['2'], c.get('over'), c.get('under'), c.get('line', 2.5))
    fh, fa = (mh, ma) if lh is None else blend(lh, la, mh, ma, w['wr'], w['wt'])
    info = {'kaynak_1x2': c['src'], 'kaynak_gol': (f"{c['src_total']} {c['line']:g} gol" if c.get('src_total') else None),
            'oran': {k: c[k] for k in ('1', 'X', '2')}, 'mh': mh, 'ma': ma}
    if c.get('src_total'):
        info['oran'].update(line=c['line'], over=c['over'], under=c['under'])
    return fh, fa, info
