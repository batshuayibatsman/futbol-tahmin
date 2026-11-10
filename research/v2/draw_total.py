"""v2: toplam gol oranı olmayan maçlarda toplam golü 1X2 oranlarından çıkarmak.
Beraberlik olasılığı toplam golle güçlü biçimde ilişkili: P(1)-P(2) ve P(X) birlikte (bağımsız Poisson ile) T ve payı verir.
Poisson beraberliği olduğundan az verdiği için T sistematik düşük çıkar; ölçek katsayısı yalnızca 2021-23'te,
2,5 gol oranından çıkan toplama göre seçilir. Sonra ek 16 ligde (yalnızca 1X2 oranı) model toplamıyla karşılaştırılır."""
import sys
sys.path.insert(0, 'tahmin'); sys.path.insert(0, 'research/v2')
import numpy as np, pandas as pd
from blend import hda, score_nll


def draw_fit_total(o1, ox, o2, it=40):
    q = np.vstack([1 / o1, 1 / ox, 1 / o2]); p = q / q.sum(0)
    tgt, pdr = p[0] - p[2], p[1]
    lo = np.full(len(o1), 0.6); hi = np.full(len(o1), 7.0)
    for _ in range(it):
        T = (lo + hi) / 2
        a = np.full(len(o1), 0.01); b = np.full(len(o1), 0.99)
        for _ in range(it):
            r = (a + b) / 2; h, d, aw = hda(T * r, T * (1 - r))
            m = (h - aw) - tgt < 0; a = np.where(m, r, a); b = np.where(m, b, r)
        r = (a + b) / 2; h, d, aw = hda(T * r, T * (1 - r))
        m = d > pdr; lo = np.where(m, T, lo); hi = np.where(m, hi, T)
    return (lo + hi) / 2


if __name__ == '__main__':
    P = pd.read_csv('out/wf22_market.csv')
    V = P[P.season.isin([2021, 2022, 2023]) & P.has_t]
    Td = draw_fit_total(V.oh.values, V.od.values, V.oa.values)
    Tou = (V.mh_ + V.ma_).values
    k = float(Tou.mean() / Td.mean())
    print('scale (2021-23, %d matches): %.4f | MAE vs O/U total: scaled draw-fit %.3f, model total %.3f' % (
        len(V), k, np.abs(Tou - k * Td).mean(), np.abs(Tou - (V.lh + V.la).values).mean()))
    X = pd.read_csv('out/wf_extra.csv')
    Tx = k * draw_fit_total(X.oh.values, X.od.values, X.oa.values)
    # home share from the 1X2 odds with that total (same rule as market.implied_means)
    from market import implied_means
    mm = np.array([implied_means(r.oh, r.od, r.oa, None, None, 2.5, t) for r, t in zip(X.itertuples(), Tx)])
    for nm, S in (('VAL 2021-23', X.season.isin([2021, 2022, 2023])), ('TEST 2024', X.season == 2024)):
        a = score_nll(X.mh_.values[S], X.ma_.values[S], X.hg.values[S], X.ag.values[S]).mean()
        b = score_nll(mm[S, 0], mm[S, 1], X.hg.values[S], X.ag.values[S]).mean()
        print('%s ek ligler: model toplamı %.5f | 1X2 toplamı %.5f (n=%d)' % (nm, a, b, int(S.sum())))
