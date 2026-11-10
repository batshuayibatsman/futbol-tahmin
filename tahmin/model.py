"""Core of the prediction engine (deterministic: no random numbers anywhere).

Team strengths: time-weighted, ridge-penalised Poisson model (Dixon-Coles style)
    log(lambda_home) = mu + home_adv + att[home] - def[away]
    log(lambda_away) = mu            + att[away] - def[home]
The same structure is used for goals and for corners.
"""
import numpy as np
import pandas as pd
from scipy.optimize import minimize

LN2 = np.log(2.0)


def fit_strengths(hi, ai, yh, ya, w, n, pm_att, pm_def, kappa, x0=None):
    """Weighted penalised Poisson MLE. Returns (mu, gamma, att[n], def[n])."""
    hi = np.asarray(hi); ai = np.asarray(ai)
    yh = np.asarray(yh, float); ya = np.asarray(ya, float); w = np.asarray(w, float)

    def f(p):
        mu, g = p[0], p[1]
        att = p[2:2 + n]; de = p[2 + n:]
        eh = mu + g + att[hi] - de[ai]
        ea = mu + att[ai] - de[hi]
        lh = np.exp(eh); la = np.exp(ea)
        ll = np.sum(w * (yh * eh - lh + ya * ea - la))
        pen = 0.5 * kappa * (np.sum((att - pm_att) ** 2) + np.sum((de - pm_def) ** 2))
        rh = w * (yh - lh); ra = w * (ya - la)
        g_att = np.bincount(hi, rh, n) + np.bincount(ai, ra, n) - kappa * (att - pm_att)
        g_def = -np.bincount(ai, rh, n) - np.bincount(hi, ra, n) - kappa * (de - pm_def)
        grad = np.concatenate([[rh.sum() + ra.sum(), rh.sum()], g_att, g_def])
        return -(ll - pen), -grad

    if x0 is None:
        tot = max(w.sum(), 1e-9)
        m = max((w * (yh + ya)).sum() / (2 * tot), 1e-3)
        x0 = np.concatenate([[np.log(m), 0.1], pm_att, pm_def])
    r = minimize(f, x0, jac=True, method='L-BFGS-B', options={'maxiter': 500, 'ftol': 1e-12, 'gtol': 1e-8})
    p = r.x
    return p[0], p[1], p[2:2 + n], p[2 + n:], p


class LeagueFitter:
    """Fits goals + corners strengths for one division using only matches strictly before `cutoff`."""

    def __init__(self, df, cfg):
        # df: all rows of one division (any dates), must contain fit_ok flag
        self.df = df.sort_values('date').reset_index(drop=True)
        self.cfg = cfg
        self.teams_by_season = {s: set(g.home) | set(g.away) for s, g in self.df.groupby('season')}
        self._x0g = None; self._x0c = None; self._teams_prev = None

    def fit(self, cutoff, season, extra_teams=()):
        cfg = self.cfg
        d = self.df
        win = d[(d.date < cutoff) & (d.date >= cutoff - pd.Timedelta(days=cfg['window_days']))]
        m = win[win.fit_ok]                                        # goals: full-time + half-time score
        mc = win[win.fit_c] if 'fit_c' in win.columns else m       # corners: rows that also have corner counts
        # teams: everything in the window plus the clubs of the current season (and fixture-only clubs, e.g. at season start)
        cur = self.df[(self.df.season == season)]
        teams = sorted(set(m.home) | set(m.away) | set(mc.home) | set(mc.away) | set(cur.home) | set(cur.away) | set(extra_teams))
        idx = {t: i for i, t in enumerate(teams)}
        n = len(teams)
        prev = self.teams_by_season.get(season - 1, set())
        new = np.array([(t not in prev) for t in teams])
        hi = m.home.map(idx).values; ai = m.away.map(idx).values
        age = (cutoff - m.date).dt.days.values.astype(float)
        out = {'teams': teams, 'idx': idx, 'new': new, 'n_matches': int(len(m))}
        warm = (self._teams_prev == teams)
        # ---- goals
        w = np.exp(-LN2 * age / cfg['hl_goals'])
        pm_a = np.where(new, cfg['new_att_goals'], 0.0); pm_d = np.where(new, cfg['new_def_goals'], 0.0)
        mu, g, att, de, p = fit_strengths(hi, ai, m.hg.values, m.ag.values, w, n, pm_a, pm_d, cfg['kappa_goals'],
                                          self._x0g if warm else None)
        self._x0g = p
        out.update(mu=mu, gamma=g, att=att, de=de)
        sw = w.sum()
        out['eff_n'] = float(sw)
        # league first-half share of goals (home / away), same weights; leagues without half-time scores use the
        # 22-league average (only their full-time markets are shown)
        hm = m.hthg.notna().values & m.htag.notna().values
        if hm.sum() >= 100:
            out['s1_h'] = float((w[hm] * m.hthg.values[hm]).sum() / max((w[hm] * m.hg.values[hm]).sum(), 1e-9))
            out['s1_a'] = float((w[hm] * m.htag.values[hm]).sum() / max((w[hm] * m.ag.values[hm]).sum(), 1e-9))
            out['has_ht'] = True
        else:
            out['s1_h'], out['s1_a'] = cfg.get('s1_default', (0.446, 0.446))
            out['has_ht'] = False
        # ---- corners (only where the league records them: at least half of the window's matches and 200 rows)
        if len(mc) >= max(200, 0.5 * len(m)):
            hic = mc.home.map(idx).values; aic = mc.away.map(idx).values
            agec = (cutoff - mc.date).dt.days.values.astype(float)
            wc = np.exp(-LN2 * agec / cfg['hl_corners'])
            pm_a = np.where(new, cfg['new_att_corners'], 0.0); pm_d = np.where(new, cfg['new_def_corners'], 0.0)
            cmu, cg, catt, cde, pc = fit_strengths(hic, aic, mc.hc.values, mc.ac.values, wc, n, pm_a, pm_d, cfg['kappa_corners'],
                                                   self._x0c if (warm and self._x0c is not None) else None)
            self._x0c = pc
            out.update(cmu=cmu, cgamma=cg, catt=catt, cde=cde)
            out['c_avg'] = float((wc * (mc.hc.values + mc.ac.values)).sum() / wc.sum())
        else:
            self._x0c = None
            out.update(cmu=None, cgamma=None, catt=None, cde=None, c_avg=None)
        self._teams_prev = teams
        return out


def predict_means(fit, home, away):
    i = fit['idx'][home]; j = fit['idx'][away]
    lh = np.exp(fit['mu'] + fit['gamma'] + fit['att'][i] - fit['de'][j])
    la = np.exp(fit['mu'] + fit['att'][j] - fit['de'][i])
    if fit['cmu'] is None:                       # league without corner statistics
        return lh, la, float('nan'), float('nan')
    ch = np.exp(fit['cmu'] + fit['cgamma'] + fit['catt'][i] - fit['cde'][j])
    ca = np.exp(fit['cmu'] + fit['catt'][j] - fit['cde'][i])
    return lh, la, ch, ca


def walk_forward(df_div, cfg, seasons, refit_gap_days=3):
    """Walk-forward predictions for one division. Each match is predicted from a fit that only
    saw matches played strictly before the (re)fit date, which is <= the match date."""
    fitter = LeagueFitter(df_div, cfg)
    d = fitter.df
    rows = []
    for s in seasons:
        ds = d[(d.season == s)]
        last_fit = None; fit = None
        for date, blk in ds.groupby('date'):
            if fit is None or (date - last_fit).days >= refit_gap_days:
                fit = fitter.fit(date, s); last_fit = date
            for r in blk.itertuples():
                lh, la, ch, ca = predict_means(fit, r.home, r.away)
                rows.append((r.Index, lh, la, ch, ca, fit['c_avg'] if fit['c_avg'] is not None else float('nan'), fit['s1_h'], fit['s1_a'],
                             bool(fit['new'][fit['idx'][r.home]]), bool(fit['new'][fit['idx'][r.away]]), fit['eff_n']))
    P = pd.DataFrame(rows, columns=['i', 'lh', 'la', 'ch', 'ca', 'c_avg', 's1h', 's1a', 'new_h', 'new_a', 'eff_n']).set_index('i')
    return d.join(P, how='inner')


# ----------------------------------------------------------------------------------------------
# Probability layer (must stay identical to the JavaScript in the page; parity is tested)
# ----------------------------------------------------------------------------------------------
MAXG = 10  # goals per team per half are truncated at 10 (probability mass beyond is < 1e-9)


def pois_vec(lam, n=MAXG):
    k = np.arange(n + 1)
    logp = -lam + k * np.log(lam) - np.cumsum(np.concatenate([[0.0], np.log(np.arange(1, n + 1))]))
    p = np.exp(logp)
    return p / p.sum()


def n_states(cal):
    return len(cal['st'])


def state_of(i, j, K):
    """Half-time state index from the HT score. K=3: away lead / level / home lead.
    K=5: away lead by 2+, away by 1, level, home by 1, home by 2+."""
    c = (K - 1) // 2
    return int(min(max(i - j, -c), c)) + c


def match_distribution(lh, la, s1h, s1a, cal):
    """Joint distribution of (HT score, 2nd-half score).
    First half: independent Poisson with means lambda*share.
    Second half: independent Poisson whose means depend on the half-time state through the
    multipliers cal['st'][k] = (mult_home, mult_away); they are renormalised per match so the expected
    2nd-half goals of each team stay lambda*(1-share)."""
    l1h = lh * s1h; l1a = la * s1a
    l2h = lh - l1h; l2a = la - l1a
    M1 = np.outer(pois_vec(l1h), pois_vec(l1a))
    K = n_states(cal); n = MAXG + 1
    S = np.array([[state_of(i, j, K) for j in range(n)] for i in range(n)])
    ps = np.array([M1[S == k].sum() for k in range(K)])
    st = np.asarray(cal['st'], float)
    nh = float((ps * st[:, 0]).sum()); na = float((ps * st[:, 1]).sum())
    M2 = [np.outer(pois_vec(l2h * st[k, 0] / nh), pois_vec(l2a * st[k, 1] / na)) for k in range(K)]
    return M1, M2, S


def summarize(M1, M2, S):
    """Full-time score matrix and the 3x3 HT/FT table.
    htft rows: HT result (home lead, level, away lead); cols: FT result (1, X, 2)."""
    n = MAXG + 1; K = len(M2); c = (K - 1) // 2
    idx = np.arange(n)
    I, J = np.meshgrid(idx, idx, indexing='ij')
    dif = (I - J + n - 1).ravel()
    FT = np.zeros((2 * n - 1, 2 * n - 1))
    htft = np.zeros((3, 3))
    z = 2 * (n - 1)
    sign = np.sign(I - J)
    for k in range(K):
        B = M2[k]
        d2 = np.bincount(dif, B.ravel(), 2 * n - 1)
        for r, sg in enumerate((1, 0, -1)):          # HT result rows: home lead, level, away lead
            A = np.where((S == k) & (sign == sg), M1, 0.0)
            if A.sum() <= 0:
                continue
            for i in range(n):
                for j in range(n):
                    if A[i, j] > 0:
                        FT[i:i + n, j:j + n] += A[i, j] * B
            d = np.convolve(np.bincount(dif, A.ravel(), 2 * n - 1), d2)
            htft[r, 0] += d[z + 1:].sum(); htft[r, 1] += d[z]; htft[r, 2] += d[:z].sum()
    return FT, htft


def apply_htft_cal(FT, htft, F):
    """Row-wise recalibration of P(FT result | HT result) with fixed factors F (3x3, fitted in validation).
    Half-time marginals are untouched; the full-time score matrix is rescaled by result region so that
    every market derived from it stays consistent with the adjusted HT/FT table."""
    F = np.asarray(F, float)
    adj = htft * F
    adj = adj / adj.sum(1, keepdims=True) * htft.sum(1, keepdims=True)
    raw_col = htft.sum(0); new_col = adj.sum(0)
    n = FT.shape[0]
    idx = np.arange(n)
    I, J = np.meshgrid(idx, idx, indexing='ij')
    G = np.where(I > J, new_col[0] / raw_col[0], np.where(I == J, new_col[1] / raw_col[1], new_col[2] / raw_col[2]))
    return FT * G, adj


def corner_mean(ch, ca, c_avg, beta):
    """Total-corner mean shrunk towards the league average (beta fitted in validation)."""
    return c_avg ** (1 - beta) * (ch + ca) ** beta


def nb_pmf_vec(mean, k, n=40):
    """Negative binomial pmf (mean, size k) for 0..n ; k -> inf gives Poisson."""
    from scipy.special import gammaln
    x = np.arange(n + 1)
    if k > 1e6:
        logp = -mean + x * np.log(mean) - gammaln(x + 1)
    else:
        logp = gammaln(x + k) - gammaln(k) - gammaln(x + 1) + k * np.log(k / (k + mean)) + x * np.log(mean / (k + mean))
    p = np.exp(logp)
    return p / p.sum()
