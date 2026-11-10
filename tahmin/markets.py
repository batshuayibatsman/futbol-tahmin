"""Market definitions and the deterministic BANKO / SÜRPRİZ selection rules.
The same rules are used in the backtest (evaluate.py) and for live predictions (predict.py)."""
import numpy as np

CELLS = [a + b for a in '1X2' for b in '1X2']


def market_probs(d):
    """d: mapping with the raw probability columns produced by calibrate.predict_all."""
    m = {
        'MS 1': d['p1'], 'MS X': d['px'], 'MS 2': d['p2'],
        'ÇŞ 1X': d['p1'] + d['px'], 'ÇŞ X2': d['px'] + d['p2'], 'ÇŞ 12': d['p1'] + d['p2'],
        'KG Var': d['btts'], 'KG Yok': 1 - d['btts'],
        'İY 1': d['h1'], 'İY X': d['hx'], 'İY 2': d['h2'],
        'İY 0.5 Üst': d['ho0.5'], 'İY 0.5 Alt': 1 - d['ho0.5'],
        'İY 1.5 Üst': d['ho1.5'], 'İY 1.5 Alt': 1 - d['ho1.5'],
        'İY 2.5 Üst': d['ho2.5'], 'İY 2.5 Alt': 1 - d['ho2.5'],
    }
    for L in (1.5, 2.5, 3.5, 4.5):
        m[f'{L} Üst'] = d[f'o{L}']; m[f'{L} Alt'] = 1 - d[f'o{L}']
    for L in (7.5, 8.5, 9.5, 10.5, 11.5, 12.5):
        m[f'Korner {L} Üst'] = d[f'co{L}']; m[f'Korner {L} Alt'] = 1 - d[f'co{L}']
    for L in (3.5, 4.5, 5.5):
        if f'hco{L}' in d:
            m[f'İY Korner {L} Üst'] = d[f'hco{L}']; m[f'İY Korner {L} Alt'] = 1 - d[f'hco{L}']
    for c in CELLS:
        m[f'İY/MS {c[0]}/{c[1]}'] = d['hf' + c]
    # underdog wins (only defined for the side with the lower win probability)
    if d['p1'] < d['p2']:
        m['Sürpriz MS 1'] = d['p1']
    else:
        m['Sürpriz MS 2'] = d['p2']
    return m


def market_outcomes(hg, ag, hthg, htag, hc, ac, p1=None, p2=None):
    tg = hg + ag; t1 = hthg + htag; ct = hc + ac
    ht = '1' if hthg > htag else ('X' if hthg == htag else '2')
    ft = '1' if hg > ag else ('X' if hg == ag else '2')
    o = {'MS 1': ft == '1', 'MS X': ft == 'X', 'MS 2': ft == '2',
         'ÇŞ 1X': ft != '2', 'ÇŞ X2': ft != '1', 'ÇŞ 12': ft != 'X',
         'KG Var': hg > 0 and ag > 0, 'KG Yok': not (hg > 0 and ag > 0),
         'İY 1': ht == '1', 'İY X': ht == 'X', 'İY 2': ht == '2'}
    for L in (0.5, 1.5, 2.5):
        o[f'İY {L} Üst'] = t1 > L; o[f'İY {L} Alt'] = t1 < L
    for L in (1.5, 2.5, 3.5, 4.5):
        o[f'{L} Üst'] = tg > L; o[f'{L} Alt'] = tg < L
    for L in (7.5, 8.5, 9.5, 10.5, 11.5, 12.5):
        o[f'Korner {L} Üst'] = ct > L; o[f'Korner {L} Alt'] = ct < L
    for c in CELLS:
        o[f'İY/MS {c[0]}/{c[1]}'] = (ht + ft) == c
    if p1 is not None:
        if p1 < p2:
            o['Sürpriz MS 1'] = ft == '1'
        else:
            o['Sürpriz MS 2'] = ft == '2'
    return o


# ---------------------------------------------------------------------------------- rules
BANKO_MENU = ['MS 1', 'MS 2', 'ÇŞ 1X', 'ÇŞ X2', 'ÇŞ 12', '1.5 Üst', '2.5 Üst', '2.5 Alt', '3.5 Alt',
              'KG Var', 'KG Yok', 'İY 0.5 Üst', 'İY 1.5 Alt',
              'Korner 8.5 Üst', 'Korner 9.5 Üst', 'Korner 9.5 Alt', 'Korner 10.5 Alt', 'Korner 11.5 Alt']
BANKO_MIN, BANKO_MAX = 0.70, 0.90       # banko = most likely menu outcome that is not near-certain (<=90%)

SURPRISE_MENU = ['İY/MS 1/2', 'İY/MS 2/1', 'MS X', 'Sürpriz MS 1', 'Sürpriz MS 2', '3.5 Üst',
                 'İY 1.5 Üst', 'İY 2.5 Üst', 'Korner 11.5 Üst', 'Korner 7.5 Alt']
SURPRISE_MIN_P, SURPRISE_MIN_LIFT = 0.03, 1.25   # sürpriz = outcome far more likely than its usual frequency


def pick_banko(m):
    best = None
    for k in BANKO_MENU:
        p = m.get(k)
        if p is None or p > BANKO_MAX:
            continue
        if best is None or p > best[1] + 1e-12:
            best = (k, p)
    if best and best[1] >= BANKO_MIN:
        return best
    return None


def pick_surprise(m, base):
    """base: league base rates for the menu (frequency of the outcome in recent seasons)."""
    best = None
    for k in SURPRISE_MENU:
        p = m.get(k); b = base.get(k)
        if p is None or b is None or p < SURPRISE_MIN_P:
            continue
        lift = p / b
        if lift < SURPRISE_MIN_LIFT:
            continue
        if best is None or lift > best[2] + 1e-12:
            best = (k, p, lift)
    return best


def base_rates(outcome_dicts):
    """Mean outcome frequency for every market over a list of outcome dicts (one league)."""
    keys = set().union(*[o.keys() for o in outcome_dicts])
    out = {}
    for k in keys:
        v = [o[k] for o in outcome_dicts if k in o]
        if v:
            out[k] = float(np.mean(v))
    return out
