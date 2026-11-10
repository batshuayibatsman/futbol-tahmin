"""v2 calibration: the same layer as v1 (3 half-time states, corner shrink, HT/FT recalibration), refitted on the
validation seasons 2021-23 of all 22 leagues, with the goal means the live site uses: odds-implied wherever
odds exist (blend.py: the odds alone were the most accurate choice), the statistics model otherwise.
Writes out/v2_<variant>_{cal.json,val.pkl,test.pkl} for variant 'model' (v1 rule) and 'oran' (v2 rule)."""
import json, sys
sys.path.insert(0, 'tahmin')
import numpy as np, pandas as pd
from multiprocessing import Pool
from scipy.optimize import minimize
from scipy.special import gammaln
from probs import predict_all
from config import CORNER_1H_SHARE

VAL, TEST = [2021, 2022, 2023], [2024, 2025]


def load(variant):
    W = pd.read_csv('out/wf22.csv', parse_dates=['date'])
    M = pd.read_csv('out/wf22_market.csv', parse_dates=['date'])[['div', 'date', 'home', 'away', 'mh_', 'ma_']]
    P = W.merge(M, on=['div', 'date', 'home', 'away'], how='left')
    P = P[P.fit_ok].copy()
    P['lh_model'] = P.lh; P['la_model'] = P.la
    P['basis'] = 'model'
    if variant == 'oran':
        m = P.mh_.notna()
        P.loc[m, 'lh'] = P.loc[m, 'mh_']; P.loc[m, 'la'] = P.loc[m, 'ma_']; P.loc[m, 'basis'] = 'oran'
    P['g2h'] = P.hg - P.hthg; P['g2a'] = P.ag - P.htag
    P['l1h'] = P.lh * P.s1h; P['l1a'] = P.la * P.s1a; P['l2h'] = P.lh - P.l1h; P['l2a'] = P.la - P.l1a
    return P.reset_index(drop=True)


def fit_cal(V, K=3):
    c = (K - 1) // 2
    k = (np.clip(V.hthg - V.htag, -c, c) + c).astype(int)
    st = [[float(V[k == s].g2h.sum() / V[k == s].l2h.sum()), float(V[k == s].g2a.sum() / V[k == s].l2a.sum())] for s in range(K)]
    C = V[V.ch.notna() & V.hc.notna() & V.ac.notna()]
    t = (C.hc + C.ac).values; m0 = (C.ch + C.ca).values; L = C.c_avg.values

    def nll(par):
        b = par[0]; kk = np.exp(par[1]); m = L ** (1 - b) * m0 ** b
        return -(gammaln(t + kk) - gammaln(kk) - gammaln(t + 1) + kk * np.log(kk / (kk + m)) + t * np.log(m / (kk + m))).sum()
    r = minimize(nll, [0.7, 4.0], method='Nelder-Mead', options={'xatol': 1e-5, 'fatol': 1e-7})
    return {'st': st, 'c_beta': float(r.x[0]), 'nb_k': float(np.exp(r.x[1])), 'c1_share': CORNER_1H_SHARE}


def fit_F(Q, D):
    cells = [a + b for a in '1X2' for b in '1X2']
    R = Q[['hf' + x for x in cells]].values.reshape(-1, 3, 3)
    ht = np.where(D.hthg > D.htag, 0, np.where(D.hthg == D.htag, 1, 2)); ft = np.where(D.hg > D.ag, 0, np.where(D.hg == D.ag, 1, 2))

    def nll(th):
        F = np.ones((3, 3)); F[:, 1:] = np.exp(th.reshape(3, 2))
        A = R * F[None]; A = A / A.sum(2, keepdims=True) * R.sum(2, keepdims=True)
        return -np.log(A[np.arange(len(R)), ht, ft]).sum()
    r = minimize(nll, np.zeros(6), method='BFGS')
    F = np.ones((3, 3)); F[:, 1:] = np.exp(r.x.reshape(3, 2))
    return F.tolist()


def _pa(args):
    D, cal = args
    return predict_all(D, cal)


def par_predict(D, cal, n=2):
    k = n * 4; step = -(-len(D) // k)
    parts = [D.iloc[i:i + step] for i in range(0, len(D), step)]
    with Pool(n) as p:
        out = p.map(_pa, [(x, cal) for x in parts])
    return pd.concat(out).loc[D.index]


if __name__ == '__main__':
    for variant in sys.argv[1:] or ['model', 'oran']:
        P = load(variant)
        V = P[P.season.isin(VAL)]; T = P[P.season.isin(TEST)]
        cal = fit_cal(V)
        cal['F'] = fit_F(par_predict(V, cal), V)
        print(variant, 'CAL', json.dumps({k: (np.round(v, 4).tolist() if isinstance(v, list) else round(v, 4)) for k, v in cal.items()}), flush=True)
        json.dump(cal, open(f'out/v2_{variant}_cal.json', 'w'), indent=1)
        Qv = par_predict(V, cal); Qt = par_predict(T, cal)
        V.join(Qv, rsuffix='_q').to_pickle(f'out/v2_{variant}_val.pkl'); T.join(Qt, rsuffix='_q').to_pickle(f'out/v2_{variant}_test.pkl')
        print(variant, 'saved', len(V), len(T), 'odds share in test', round(float((T.basis == 'oran').mean()), 4), flush=True)
