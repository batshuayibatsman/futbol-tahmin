"""Calibration layer: fitted on validation seasons, then frozen and scored on the untouched test seasons."""
import numpy as np, pandas as pd, json, sys
from scipy.optimize import minimize
from scipy.special import gammaln
from model import pois_vec, match_distribution, summarize, nb_pmf_vec, corner_mean, apply_htft_cal, MAXG
from config import *

def load():
    P=pd.read_csv('out/wf_predictions.csv',parse_dates=['date'])
    P=P[P.fit_ok].copy()
    P['g2h']=P.hg-P.hthg; P['g2a']=P.ag-P.htag
    P['l1h']=P.lh*P.s1h; P['l1a']=P.la*P.s1a; P['l2h']=P.lh-P.l1h; P['l2a']=P.la-P.l1a
    return P

def fit_cal(V,K=5,shrink_corners=True):
    cal={}
    c=(K-1)//2
    k=(np.clip(V.hthg-V.htag,-c,c)+c).astype(int)
    st=[]
    for s in range(K):
        g=V[k==s]
        st.append([float(g.g2h.sum()/g.l2h.sum()),float(g.g2a.sum()/g.l2a.sum())] if K>1 else [1.0,1.0])
    cal['st']=st
    t=(V.hc+V.ac).values; m0=(V.ch+V.ca).values; L=V.c_avg.values
    def nll(par):
        b=par[0] if shrink_corners else 1.0; kk=np.exp(par[1]); m=L**(1-b)*m0**b
        return -(gammaln(t+kk)-gammaln(kk)-gammaln(t+1)+kk*np.log(kk/(kk+m))+t*np.log(m/(kk+m))).sum()
    r=minimize(nll,[0.7,4.0],method='Nelder-Mead',options={'xatol':1e-5,'fatol':1e-7})
    cal['c_beta']=float(r.x[0]) if shrink_corners else 1.0; cal['nb_k']=float(np.exp(r.x[1]))
    cal['c1_share']=CORNER_1H_SHARE
    return cal

def fit_F(Q,D):
    """MLE of the 3x3 factor table (first column fixed to 1) from raw HT/FT probabilities Q on matches D."""
    cells=[a+b for a in '1X2' for b in '1X2']
    R=Q[['hf'+x for x in cells]].values.reshape(-1,3,3)
    ht=np.where(D.hthg>D.htag,0,np.where(D.hthg==D.htag,1,2)); ft=np.where(D.hg>D.ag,0,np.where(D.hg==D.ag,1,2))
    def nll(th):
        F=np.ones((3,3)); F[:,1:]=np.exp(th.reshape(3,2))
        A=R*F[None]; A=A/A.sum(2,keepdims=True)*R.sum(2,keepdims=True)
        return -np.log(A[np.arange(len(R)),ht,ft]).sum()
    r=minimize(nll,np.zeros(6),method='BFGS')
    F=np.ones((3,3)); F[:,1:]=np.exp(r.x.reshape(3,2))
    return F.tolist()

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
        d['p1']=FT[I>J].sum(); d['px']=FT[I==J].sum(); d['p2']=FT[I<J].sum()
        tot=np.bincount(TOT.ravel(),FT.ravel())
        for L in (0.5,1.5,2.5,3.5,4.5): d[f'o{L}']=tot[int(L+.5):].sum()
        d['btts']=1-FT[0,:].sum()-FT[:,0].sum()+FT[0,0]
        d['h1']=M1[I1>J1].sum(); d['hx']=M1[I1==J1].sum(); d['h2']=M1[I1<J1].sum()
        t1=np.bincount((I1+J1).ravel(),M1.ravel())
        d['ho0.5']=t1[1:].sum(); d['ho1.5']=t1[2:].sum(); d['ho2.5']=t1[3:].sum()
        for a,A in enumerate('1X2'):
            for b,B in enumerate('1X2'): d[f'hf{A}{B}']=htft[a,b]
        hg,ag,hh,ha=int(r.hg),int(r.ag),int(r.hthg),int(r.htag)
        d['p_score']=FT[hg,ag] if hg<2*n-1 and ag<2*n-1 else 1e-12
        d['p_htscore']=M1[hh,ha] if hh<n and ha<n else 1e-12
        fl=np.argsort(-FT.ravel())[:3]; d['top3']=[(int(k//(2*n-1)),int(k%(2*n-1))) for k in fl]
        hl=np.argsort(-M1.ravel())[:3]; d['httop3']=[(int(k//n),int(k%n)) for k in hl]
        d['exp_g']=float((TOT*FT).sum()); d['exp_g1']=float(((I1+J1)*M1).sum())
        mc=corner_mean(r.ch,r.ca,r.c_avg,cal['c_beta']); pc=nb_pmf_vec(mc,cal['nb_k'])
        d['exp_c']=mc; d['exp_c1']=mc*cal['c1_share']
        pc1=nb_pmf_vec(mc*cal['c1_share'],cal['nb_k'])
        for L in (3.5,4.5,5.5): d[f'hco{L}']=pc1[int(L+.5):].sum()
        for L in (7.5,8.5,9.5,10.5,11.5,12.5): d[f'co{L}']=pc[int(L+.5):].sum()
        d['p_ctot']=pc[int(r.hc+r.ac)] if (r.hc+r.ac)<=40 else 1e-12
        out.append(d)
    return pd.DataFrame(out).set_index('i')

if __name__=='__main__':
    P=load()
    V=P[P.season.isin(VAL)]; T=P[P.season.isin(TEST)]
    # ---- component selection inside validation: fit on 2021-22, judge on 2023-24 season (test seasons untouched)
    A=P[P.season.isin([2021,2022])]; B=P[P.season==2023]
    def hf_ll(Q,D):
        st=np.where(D.hthg>D.htag,'1',np.where(D.hthg==D.htag,'X','2')); ft=np.where(D.hg>D.ag,'1',np.where(D.hg==D.ag,'X','2'))
        return float(np.mean([-np.log(Q.at[i,'hf'+a+b]) for i,a,b in zip(D.index,st,ft)]))
    def x12_ll(Q,D): return float(np.mean(-np.log(np.where(D.hg>D.ag,Q.p1,np.where(D.hg==D.ag,Q.px,Q.p2)))))
    def c_ll(Q,D): return float(np.mean(-np.log(Q.p_ctot)))
    sel={}
    for name,(K,sh,uf) in {'independent halves, raw corners':(1,False,False),'3 HT states':(3,False,False),'5 HT states':(5,False,False),'5 HT states + corner shrink':(5,True,False),'3 HT states + corner shrink + HT/FT recalibration':(3,True,True),'5 HT states + corner shrink + HT/FT recalibration':(5,True,True)}.items():
        c=fit_cal(A,K,sh)
        if uf: c['F']=fit_F(predict_all(A,c),A); print('   F=',np.round(c['F'],3).tolist())
        Q=predict_all(B,c)
        sel[name]=dict(htft_logloss=hf_ll(Q,B),ft1x2_logloss=x12_ll(Q,B),score_logloss=float(np.mean(-np.log(Q.p_score))),corner_total_logloss=c_ll(Q,B))
        print(name,{k:round(v,4) for k,v in sel[name].items()},[[round(x,3) for x in s] for s in c['st']],'beta=%.3f k=%.1f'%(c['c_beta'],c['nb_k']),flush=True)
    json.dump(sel,open('out/component_selection.json','w'),indent=1)
    K=int(sys.argv[1]) if len(sys.argv)>1 else 5
    cal=fit_cal(V,K,True); cal['F']=fit_F(predict_all(V,cal),V); print('CAL(val 2021-23):',json.dumps(cal))
    json.dump(cal,open('out/cal_val.json','w'),indent=1)
    Q=predict_all(T,cal); Q.to_pickle('out/test_probs.pkl')
    Qv=predict_all(V,cal); Qv.to_pickle('out/val_probs.pkl')
    pd.concat([Qv, Q])[['p1', 'p2']].to_csv('out/probs_p1p2.csv')
    print('saved',len(Q),len(Qv))
