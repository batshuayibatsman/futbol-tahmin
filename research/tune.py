"""Hyper-parameter search on VALIDATION seasons only (2021-22, 2022-23, 2023-24).
The test seasons (2024-25, 2025-26) are never touched here."""
import pandas as pd, numpy as np, itertools, json, sys, time
from multiprocessing import Pool
from scipy.special import gammaln
from model import walk_forward
TOP=['T1','E0','SP1','I1','D1','F1','N1','P1']
VAL=[2021,2022,2023]
D=pd.read_csv('out/matches_clean.csv',parse_dates=['date'])
D=D[D['div'].isin(TOP)&(D.season>=2015)]
BASE=dict(window_days=1460,new_att_goals=-0.22,new_def_goals=-0.13,new_att_corners=-0.09,new_def_corners=-0.08)
def pll(y,l): return y*np.log(l)-l-gammaln(y+1)
def run(task):
    hl,kap,dv=task
    cfg=dict(BASE,hl_goals=hl,hl_corners=hl,kappa_goals=kap,kappa_corners=kap)
    P=walk_forward(D[D['div']==dv],cfg,VAL)
    P=P[P.fit_ok]
    return dict(hl=hl,kappa=kap,div=dv,n=len(P),g=float((pll(P.hg,P.lh)+pll(P.ag,P.la)).sum()),c=float((pll(P.hc,P.ch)+pll(P.ac,P.ca)).sum()))
if __name__=='__main__':
    grid=[(hl,k,dv) for hl in [150,240,365,540,800] for k in [2,5,10,20] for dv in TOP]
    t0=time.time(); res=[]
    with Pool(2) as p:
        for i,r in enumerate(p.imap_unordered(run,grid)):
            res.append(r)
            if i%16==15: print(i+1,len(grid),round(time.time()-t0),'s',flush=True)
    R=pd.DataFrame(res); R.to_csv('out/tune_results.csv',index=False)
    A=R.groupby(['hl','kappa']).agg(n=('n','sum'),g=('g','sum'),c=('c','sum')).reset_index()
    A['g_per_match']=A.g/A.n; A['c_per_match']=A.c/A.n
    print(A.pivot(index='hl',columns='kappa',values='g_per_match').round(4).to_string())
    print(A.pivot(index='hl',columns='kappa',values='c_per_match').round(4).to_string())
    print('DONE',round(time.time()-t0),'s')
