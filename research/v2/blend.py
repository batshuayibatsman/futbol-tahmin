"""v2: should bookmaker odds move the prediction, and by how much?
Market-implied goal means from 1X2 + over/under odds (margin removed proportionally):
  total T from P(goals > line) and the home share r from P(home) - P(away), both under independent Poisson.
Blend with the model:  log T = (1-wt) log T_model + wt log T_market,  log(lh/la) = (1-wr) log-ratio_model + wr log-ratio_market.
wr, wt are chosen on the validation seasons 2021-23 only (exact-score log-likelihood) and then scored on 2024-26."""
import json, sys
sys.path.insert(0, 'tahmin')
import numpy as np, pandas as pd
from scipy.special import gammaln

K = np.arange(11)


def pois(lam):                                   # (N,) -> (N, 11), truncated and renormalised like the model
    lp = -lam[:, None] + K[None, :] * np.log(lam[:, None]) - gammaln(K + 1)[None, :]
    p = np.exp(lp); return p / p.sum(1, keepdims=True)


def p_over(T, line):
    c = pois(T); kk = int(np.floor(line))
    return 1 - c[:, :kk + 1].sum(1)


def hda(lh, la):
    A = pois(lh); B = pois(la)
    M = A[:, :, None] * B[:, None, :]
    I, J = np.meshgrid(K, K, indexing='ij')
    return (M * (I > J)).sum((1, 2)), (M * (I == J)).sum((1, 2)), (M * (I < J)).sum((1, 2))


def bisect(f, lo, hi, n=60):
    lo = np.full_like(f.__defaults__[0], lo) if False else lo
    for _ in range(n):
        mid = (lo + hi) / 2
        s = f(mid)
        lo = np.where(s < 0, mid, lo); hi = np.where(s < 0, hi, mid)
    return (lo + hi) / 2


def market_means(o1, ox, o2, oo, ou, line, T_fallback):
    """Vectorised market-implied (lh, la). o*: decimal odds; oo/ou may be NaN (then T = T_fallback)."""
    q = np.vstack([1 / o1, 1 / ox, 1 / o2]); p = q / q.sum(0)
    target = p[0] - p[2]
    qo = np.vstack([1 / oo, 1 / ou]); po = (qo / qo.sum(0))[0]
    has_t = np.isfinite(po)
    N = len(o1)
    lo = np.full(N, 0.2); hi = np.full(N, 8.0)
    po_ = np.where(has_t, po, 0.5)
    T = bisect(lambda t: p_over(t, line) - po_, lo, hi)          # p_over increases with t
    T = np.where(has_t, T, T_fallback)
    def g(r):
        a, _, c = hda(T * r, T * (1 - r)); return (a - c) - target
    r = bisect(g, np.full(N, 0.01), np.full(N, 0.99))
    return T * r, T * (1 - r), has_t


def blend(lh, la, mh, ma, wr, wt):
    Tm = lh + la; Tk = mh + ma
    T = np.exp((1 - wt) * np.log(Tm) + wt * np.log(Tk))
    R = (1 - wr) * np.log(lh / la) + wr * np.log(mh / ma)
    return T * np.exp(R) / (1 + np.exp(R)), T / (1 + np.exp(R))


def score_nll(lh, la, hg, ag):
    hg = np.minimum(hg, 10).astype(int); ag = np.minimum(ag, 10).astype(int)
    A = pois(lh); B = pois(la)
    return -(np.log(A[np.arange(len(lh)), hg]) + np.log(B[np.arange(len(la)), ag]))


if __name__ == '__main__':
    P = pd.read_csv('out/wf22.csv', parse_dates=['date'])
    ok = (P.oh > 1) & (P.od > 1) & (P.oa > 1) & P.fit_ok
    P = P[ok].copy()
    mh, ma, has_t = market_means(P.oh.values, P.od.values, P.oa.values, P.o25.values, P.u25.values, 2.5, (P.lh + P.la).values)
    P['mh_'] = mh; P['ma_'] = ma; P['has_t'] = has_t
    P.to_csv('out/wf22_market.csv', index=False)
    V = P[P.season.isin([2021, 2022, 2023])]; T = P[P.season.isin([2024, 2025])]
    grid = np.round(np.arange(0, 1.0001, 0.05), 2)
    res = {}
    for wr in grid:
        for wt in grid:
            bh, ba = blend(V.lh.values, V.la.values, V.mh_.values, V.ma_.values, wr, wt)
            res[(wr, wt)] = float(score_nll(bh, ba, V.hg.values, V.ag.values).mean())
    best = min(res, key=res.get)
    print('validation matches', len(V), 'test matches', len(T))
    print('VAL exact-score NLL  model only %.5f  market only %.5f  best %s %.5f' % (res[(0.0, 0.0)], res[(1.0, 1.0)], best, res[best]))
    # neighbourhood of the optimum (flatness)
    for wr in grid[::2]:
        print('  wr=%.2f ' % wr + ' '.join('%.4f' % res[(wr, wt)] for wt in grid[::2]))
    out = {'validation_n': int(len(V)), 'test_n': int(len(T)), 'best': {'wr': best[0], 'wt': best[1]}, 'val': {}}
    for name, (wr, wt) in {'model': (0, 0), 'market': (1, 1), 'blend': best}.items():
        bh, ba = blend(T.lh.values, T.la.values, T.mh_.values, T.ma_.values, wr, wt)
        h, d, a = hda(bh, ba)
        res_t = np.where(T.hg > T.ag, h, np.where(T.hg == T.ag, d, a))
        po = p_over(bh + ba, 2.5); ov = (T.hg + T.ag) > 2.5
        out[name] = {'score_nll': float(score_nll(bh, ba, T.hg.values, T.ag.values).mean()),
                     '1x2_logloss': float(-np.log(res_t).mean()),
                     'ou25_logloss': float(-np.log(np.where(ov, po, 1 - po)).mean())}
        print('TEST', name, {k: round(v, 5) for k, v in out[name].items()})
    for grp, divs in {'6 eski lig': ['T1', 'E0', 'SP1', 'I1', 'D1', 'F1'], '16 yeni lig': None}.items():
        S = T[T['div'].isin(divs)] if divs else T[~T['div'].isin(['T1', 'E0', 'SP1', 'I1', 'D1', 'F1'])]
        for name, (wr, wt) in {'model': (0, 0), 'blend': best}.items():
            bh, ba = blend(S.lh.values, S.la.values, S.mh_.values, S.ma_.values, wr, wt)
            print('TEST', grp, name, round(float(score_nll(bh, ba, S.hg.values, S.ag.values).mean()), 5), len(S))
    json.dump(out, open('out/blend_weights.json', 'w'), indent=1)
