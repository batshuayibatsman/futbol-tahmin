import pandas as pd, numpy as np, time
from multiprocessing import Pool
from model import walk_forward
from config import *
D=pd.read_csv('out/matches_clean.csv',parse_dates=['date'])
D=D[D['div'].isin(TOP)&(D.season>=2015)]
def run(dv): return walk_forward(D[D['div']==dv],CFG,VAL+TEST)
if __name__=='__main__':
    t0=time.time()
    with Pool(2) as p: parts=p.map(run,TOP)
    P=pd.concat(parts).sort_values(['date','div','home']).reset_index(drop=True)
    P.to_csv('out/wf_predictions.csv',index=False)
    print(len(P),'predictions',round(time.time()-t0),'s'); print(P.groupby(['season']).size().to_string())
