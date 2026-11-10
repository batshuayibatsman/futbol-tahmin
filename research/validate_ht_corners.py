"""First-half corners have no free official source. Check the thinning assumption (1H ~ NB(0.47*mean, k))
on 1,517 StatsBomb open-data matches of 2015-16 with walk-forward predictions (fit only on earlier matches)."""
import pandas as pd, numpy as np, json, difflib
from model import walk_forward, corner_mean, nb_pmf_vec
from config import *
cal=json.load(open('out/cal_val.json'))
D=pd.read_csv('out/matches_clean.csv',parse_dates=['date'])
S=pd.read_csv('data/sb/corners_by_half.csv',parse_dates=['date'])
out=[]
for dv in ['E0','SP1','I1','F1','D1']:
    P=walk_forward(D[(D['div']==dv)&(D.season>=2011)],CFG,[2015])
    s=S[S['div']==dv]
    for r in s.itertuples():
        c=P[(P.date==r.date)&(P.hg==r.hg)&(P.ag==r.ag)]
        if len(c)>1:
            sc=[difflib.SequenceMatcher(None,r.home.lower(),h.lower()).ratio()+difflib.SequenceMatcher(None,r.away.lower(),a.lower()).ratio() for h,a in zip(c.home,c.away)]
            c=c.iloc[[int(np.argmax(sc))]]
        if len(c)==1:
            q=c.iloc[0]
            mc=corner_mean(q.ch,q.ca,q.c_avg,cal['c_beta'])
            out.append(dict(div=dv,date=r.date,home=q.home,away=q.away,c1=r.hc1+r.ac1,ct=r.hc1+r.hc2+r.ac1+r.ac2,off=q.hc+q.ac,mc=mc,lg=q.c_avg))
O=pd.DataFrame(out); print('matched',len(O),'of',len(S))
print('SB total vs official total corners: mean abs diff %.3f, identical %.1f%%'%((O.ct-O.off).abs().mean(),100*(O.ct==O.off).mean()))
k=cal['nb_k']; s1=cal['c1_share']
ll_m=[];ll_b=[];rows=[]
for r in O.itertuples():
    pm=nb_pmf_vec(s1*r.mc,k); pb=nb_pmf_vec(s1*r.lg,k)
    ll_m.append(-np.log(pm[int(r.c1)])); ll_b.append(-np.log(pb[int(r.c1)]))
    rows.append({f'o{L}':pm[int(L+.5):].sum() for L in (3.5,4.5,5.5)}|{f'y{L}':r.c1>L for L in (3.5,4.5,5.5)})
R=pd.DataFrame(rows)
res={'n':int(len(O)),'actual_mean':float(O.c1.mean()),'pred_mean':float((s1*O.mc).mean()),
     'logloss_model':float(np.mean(ll_m)),'logloss_league_avg':float(np.mean(ll_b)),
     'mae_model':float((O.c1-s1*O.mc).abs().mean()),'mae_league_avg':float((O.c1-s1*O.lg).abs().mean()),
     'lines':{f'{L} Üst':{'actual':float(R[f'y{L}'].mean()),'pred':float(R[f'o{L}'].mean())} for L in (3.5,4.5,5.5)},
     'var_actual':float(O.c1.var()),'note':'share 0.47 was measured on these same matches; dispersion and team effects are out-of-sample'}
print(json.dumps(res,indent=1,ensure_ascii=False))
json.dump(res,open('out/ht_corner_check.json','w'),indent=1,ensure_ascii=False)
