# StatsBomb open data: count corners per half for full 2015/16 seasons of the big-5 leagues.
import json, sys, time, csv, os, gzip, io, urllib.request
from concurrent.futures import ThreadPoolExecutor
BASE='https://raw.githubusercontent.com/statsbomb/open-data/master/data/'
COMPS={'E0':(2,27),'SP1':(11,27),'I1':(12,27),'D1':(9,27),'F1':(7,27)}
OUT='data/sb/corners_by_half.csv'
def get(url,tries=4):
    for k in range(tries):
        try:
            req=urllib.request.Request(url,headers={'Accept-Encoding':'gzip'})
            with urllib.request.urlopen(req,timeout=90) as r:
                raw=r.read()
                if r.headers.get('Content-Encoding')=='gzip': raw=gzip.decompress(raw)
                return json.loads(raw)
        except Exception as e:
            err=e; time.sleep(2+3*k)
    raise err
def one(args):
    div,m=args
    mid=m['match_id']
    try:
        ev=get(BASE+f'events/{mid}.json')
    except Exception as e:
        return (div,mid,'ERR',str(e)[:80])
    home=m['home_team']['home_team_name']; away=m['away_team']['away_team_name']
    c={(1,'h'):0,(2,'h'):0,(1,'a'):0,(2,'a'):0}
    g={(1,'h'):0,(1,'a'):0}
    for e in ev:
        p=e.get('period')
        if p not in (1,2): continue
        side='h' if e.get('team',{}).get('name')==home else 'a'
        if e.get('type',{}).get('name')=='Pass' and e.get('pass',{}).get('type',{}).get('name')=='Corner':
            c[(p,side)]+=1
        if p==1:
            if e.get('type',{}).get('name')=='Shot' and e.get('shot',{}).get('outcome',{}).get('name')=='Goal': g[(1,side)]+=1
            if e.get('type',{}).get('name')=='Own Goal For': g[(1,side)]+=1
    return (div,mid,m['match_date'],home,away,m['home_score'],m['away_score'],c[(1,'h')],c[(2,'h')],c[(1,'a')],c[(2,'a')],g[(1,'h')],g[(1,'a')])
def main():
    jobs=[]
    for div,(c,s) in COMPS.items():
        ms=get(BASE+f'matches/{c}/{s}.json')
        print(div,len(ms),flush=True)
        jobs+=[(div,m) for m in ms]
    t0=time.time(); n=0
    with open(OUT,'w',newline='') as f, ThreadPoolExecutor(5) as ex:
        w=csv.writer(f); w.writerow(['div','match_id','date','home','away','hg','ag','hc1','hc2','ac1','ac2','hg1','ag1'])
        for r in ex.map(one,jobs):
            w.writerow(r); n+=1
            if n%100==0: f.flush(); print(n,round(time.time()-t0),'s',flush=True)
    print('DONE',n,round(time.time()-t0),'s',flush=True)
main()
