import pandas as pd, numpy as np, time
from multiprocessing import Pool
from tune import run, TOP
if __name__=='__main__':
    grid=[(hl,k,dv) for hl in [240,365] for k in [40,80,160] for dv in TOP]
    res=[]
    with Pool(2) as p:
        for r in p.imap_unordered(run,grid): res.append(r)
    R=pd.DataFrame(res); R.to_csv('out/tune_results2.csv',index=False)
    A=R.groupby(['hl','kappa']).agg(n=('n','sum'),g=('g','sum'),c=('c','sum')).reset_index()
    A['g_per_match']=A.g/A.n; A['c_per_match']=A.c/A.n
    print(A.round(4).to_string()); print('DONE')
