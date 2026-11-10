"""Per-match probabilities for every market from the four team means (identical to research/calibrate.py)."""
import numpy as np, pandas as pd
from model import pois_vec, match_distribution, summarize, nb_pmf_vec, corner_mean, apply_htft_cal, MAXG


def has_corners(r):
    """Corner markets exist only for leagues whose results include corner counts (not e.g. the National League)."""
    v=(r.ch,r.ca,r.c_avg)
    return all(x is not None and x==x for x in v)


def predict_all(T,cal):
    """Per-match probabilities for every market (walk-forward means + frozen calibration)."""
    n=MAXG+1; out=[]
    idx=np.arange(2*n-1); I,J=np.meshgrid(idx,idx,indexing='ij'); TOT=I+J
    i1=np.arange(n); I1,J1=np.meshgrid(i1,i1,indexing='ij')
    for r in T.itertuples():
        M1,M2,S=match_distribution(r.lh,r.la,r.s1h,r.s1a,cal)
        FT,htft=summarize(M1,M2,S)
        if cal.get('F') is not None: FT,htft=apply_htft_cal(FT,htft,cal['F'])
        d={'i':r.Index}
        ht=getattr(r,'ht',True); d['ht']=not (ht is False or ht==0)      # False: league without half-time scores
        d['p1']=FT[I>J].sum(); d['px']=FT[I==J].sum(); d['p2']=FT[I<J].sum()
        tot=np.bincount(TOT.ravel(),FT.ravel())
        for L in (0.5,1.5,2.5,3.5,4.5): d[f'o{L}']=tot[int(L+.5):].sum()
        d['btts']=1-FT[0,:].sum()-FT[:,0].sum()+FT[0,0]
        d['h1']=M1[I1>J1].sum(); d['hx']=M1[I1==J1].sum(); d['h2']=M1[I1<J1].sum()
        t1=np.bincount((I1+J1).ravel(),M1.ravel())
        d['ho0.5']=t1[1:].sum(); d['ho1.5']=t1[2:].sum(); d['ho2.5']=t1[3:].sum()
        for a,A in enumerate('1X2'):
            for b,B in enumerate('1X2'): d[f'hf{A}{B}']=htft[a,b]
        hg,ag=int(r.hg),int(r.ag)
        d['p_score']=FT[hg,ag] if hg<2*n-1 and ag<2*n-1 else 1e-12
        if r.hthg==r.hthg and r.htag==r.htag:
            hh,ha=int(r.hthg),int(r.htag)
            d['p_htscore']=M1[hh,ha] if hh<n and ha<n else 1e-12
        fl=np.argsort(-FT.ravel())[:3]; d['top3']=[(int(k//(2*n-1)),int(k%(2*n-1))) for k in fl]
        hl=np.argsort(-M1.ravel())[:3]; d['httop3']=[(int(k//n),int(k%n)) for k in hl]
        d['exp_g']=float((TOT*FT).sum()); d['exp_g1']=float(((I1+J1)*M1).sum())
        if has_corners(r):
            mc=corner_mean(r.ch,r.ca,r.c_avg,cal['c_beta']); pc=nb_pmf_vec(mc,cal['nb_k'])
            d['exp_c']=mc; d['exp_c1']=mc*cal['c1_share']
            pc1=nb_pmf_vec(mc*cal['c1_share'],cal['nb_k'])
            for L in (3.5,4.5,5.5): d[f'hco{L}']=pc1[int(L+.5):].sum()
            for L in (7.5,8.5,9.5,10.5,11.5,12.5): d[f'co{L}']=pc[int(L+.5):].sum()
            if r.hc==r.hc and r.ac==r.ac: d['p_ctot']=pc[int(r.hc+r.ac)] if (r.hc+r.ac)<=40 else 1e-12
        out.append(d)
    return pd.DataFrame(out).set_index('i')
