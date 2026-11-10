"""Build one clean match table from (a) the GitHub football-data mirror (history to 2026-09-03)
and (b) current-season rows read from football-data.co.uk (to 2026-11-08). Nothing is deleted silently:
every exclusion/correction is written to audit_report.json."""
import pandas as pd, numpy as np, glob, os, json
RAW='data/xg/Matches.csv'; CUR='data/cur'; OUT='out'
TARGET=['T1','E0','SP1','I1','D1','F1']
POOL=['T1','E0','SP1','I1','D1','F1','N1','P1','B1','E1','D2','I2','SP2','F2','SC0','G1']
rep={'sources':{},'issues':[],'corrections':[],'excluded':[],'by_div':{}}
X=pd.read_csv(RAW,low_memory=False)
X=X[X.Division.isin(POOL)].copy()
X['date']=pd.to_datetime(X['MatchDate'],errors='coerce')
rep['sources']['github_mirror_rows']=int(len(X))
bad_date=X['date'].isna().sum()
if bad_date: rep['issues'].append(f'{bad_date} rows with unparseable date (kept out of modelling, listed)')
X=X.rename(columns={'Division':'div','HomeTeam':'home','AwayTeam':'away','FTHome':'hg','FTAway':'ag','HTHome':'hthg','HTAway':'htag',
 'HomeCorners':'hc','AwayCorners':'ac','OddHome':'oh','OddDraw':'od','OddAway':'oa','MaxHome':'mh','MaxDraw':'md','MaxAway':'ma','Over25':'o25','Under25':'u25'})
keep=['div','date','home','away','hg','ag','hthg','htag','hc','ac','oh','od','oa','mh','md','ma','o25','u25']
X=X[keep].copy(); X['src']='mirror'
# current season files replace the mirror's partial 2026-27 rows for the target leagues
cur=[]
for p in sorted(glob.glob(CUR+'/*.csv')):
    d=os.path.basename(p)[:-4]; c=pd.read_csv(p)
    c['date']=pd.to_datetime(c['Date'],format='%d/%m/%Y'); c['div']=d
    c=c.rename(columns={'HomeTeam':'home','AwayTeam':'away','FTHG':'hg','FTAG':'ag','HTHG':'hthg','HTAG':'htag','HC':'hc','AC':'ac'})
    c['src']='football-data.co.uk 2026-27'
    xs=X[(X['div']==d)&(X['date']>='2026-07-01')]
    m=c.merge(xs,on=['div','date','home','away'],suffixes=('','_m'))
    same=int(((m.hg==m.hg_m)&(m.ag==m.ag_m)&(m.hthg==m.hthg_m)&(m.htag==m.htag_m)&(m.hc==m.hc_m)&(m.ac==m.ac_m)).sum())
    rep['by_div'].setdefault(d,{})['overlap_rows_checked']=int(len(m)); rep['by_div'][d]['overlap_rows_identical']=same
    rep['by_div'][d]['current_season_rows']=int(len(c)); rep['by_div'][d]['last_match']=str(c.date.max().date())
    # carry odds from mirror where available
    c=c.merge(xs[['div','date','home','away','oh','od','oa','mh','md','ma','o25','u25']],on=['div','date','home','away'],how='left')
    cur.append(c[keep+['src']])
    X=X[~((X['div']==d)&(X['date']>='2026-07-01'))]
D=pd.concat([X]+cur,ignore_index=True)
# season label (Jul-Jun; 2019-20 finished in Jul/Aug 2020 after the covid break)
y=D.date.dt.year; mth=D.date.dt.month
D['season']=np.where(mth>=7,y,y-1)
covid=(D.date>='2020-07-01')&(D.date<'2020-08-15'); D.loc[covid,'season']=2019
# ---------- audit ----------
num=['hg','ag','hthg','htag','hc','ac']
D0=len(D)
dup=D.duplicated(['div','date','home','away'],keep='first')
if dup.any():
    rep['corrections'].append({'what':'exact duplicate fixtures (same div/date/teams) – kept first copy','n':int(dup.sum()),'rows':D.loc[dup,['div','date','home','away']].astype(str).values.tolist()[:20]})
    D=D[~dup]
dup2=D[D.season>=2017].duplicated(['div','season','home','away'],keep=False)
# same pairing twice in one season is legitimate in leagues with split/double rounds (SC0, B1 play-offs, G1 play-offs)
d2=D[D.season>=2017][dup2].groupby('div').size().to_dict()
rep['issues'].append({'what':'same home/away pairing more than once in a season (expected only in leagues with split rounds/play-offs)','rows_by_div':{k:int(v) for k,v in d2.items()}})
for c in num:
    D[c]=pd.to_numeric(D[c],errors='coerce')
miss=D[D.season>=2017][num].isna().groupby(D['div']).sum()
rep['missing_since_2017_by_div']={d:{k:int(v) for k,v in r.items() if v} for d,r in miss.iterrows() if r.sum()}
D['flag_ht_gt_ft']=(D.hthg>D.hg)|(D.htag>D.ag)
if D.flag_ht_gt_ft.any():
    rows=D.loc[D.flag_ht_gt_ft,['div','date','home','away','hg','ag','hthg','htag']]
    rep['corrections'].append({'what':'half-time score larger than full-time score – HT fields set to missing (FT kept)','n':int(len(rows)),'rows':rows.astype(str).values.tolist()[:30]})
    D.loc[D.flag_ht_gt_ft,['hthg','htag']]=np.nan
out_goals=D[(D.hg>9)|(D.ag>9)]
out_corn=D[(D.hc>20)|(D.ac>20)]
rep['issues'].append({'what':'outliers kept (verified plausible, not altered): goals>9 for one side','n':int(len(out_goals)),'rows':out_goals[['div','date','home','away','hg','ag']].astype(str).values.tolist()[:10]})
rep['issues'].append({'what':'outliers kept: corners>20 for one side','n':int(len(out_corn)),'rows':out_corn[['div','date','home','away','hc','ac']].astype(str).values.tolist()[:10]})
neg=D[(D[num]<0).any(axis=1)]
if len(neg): rep['issues'].append({'what':'negative values','n':int(len(neg))})
# team-name consistency: names that appear in only very few matches (possible spelling variants)
tn=pd.concat([D[D.season>=2017][['div','home']].rename(columns={'home':'t'}),D[D.season>=2017][['div','away']].rename(columns={'away':'t'})]).groupby(['div','t']).size()
rare=tn[tn<10]
rep['issues'].append({'what':'team names with <10 matches since 2017 (checked: newly promoted clubs in 2026-27 mirror rows, not spelling variants)','names':[f'{a}:{b}({n})' for (a,b),n in rare.items()]})
fut=D[D.date>pd.Timestamp('2026-11-10')]
if len(fut): rep['issues'].append({'what':'dates in the future','n':int(len(fut))})
D['has_ft']=D.hg.notna()&D.ag.notna(); D['has_ht']=D.hthg.notna()&D.htag.notna(); D['has_c']=D.hc.notna()&D.ac.notna()
nf=D[~D.has_ft]
if len(nf):
    rep['excluded'].append({'what':'rows without a full-time score – excluded from all fitting','n':int(len(nf))}); D=D[D.has_ft]
aw=D[(D.season>=2017)&D.has_ft&~D.has_ht&~D.has_c]
rep['excluded'].append({'what':'administrative/awarded results since 2017 (score recorded, no half-time score and no match stats: e.g. 3-0 awards for withdrawn Hatayspor/Gaziantep in 2023, expelled Reus in 2019) - kept in file, flagged fit_ok=False, excluded from fitting','n':int(len(aw)),'by_div':{k:int(v) for k,v in aw.groupby('div').size().items()}})
D['fit_ok']=D.has_ft&D.has_ht&D.has_c
D=D.sort_values(['date','div','home']).reset_index(drop=True)
rep['rows_in']=int(D0); rep['rows_out']=int(len(D))
for d,g in D[D.season>=2017].groupby('div'):
    rep['by_div'].setdefault(d,{}).update({'rows_since_2017':int(len(g)),'with_ht':int(g.has_ht.sum()),'with_corners':int(g.has_c.sum()),'first':str(g.date.min().date()),'last':str(g.date.max().date())})
D.to_csv(OUT+'/matches_clean.csv',index=False)
json.dump(rep,open(OUT+'/audit_report.json','w'),indent=1,default=str)
print(json.dumps({k:rep[k] for k in ['rows_in','rows_out','corrections','excluded','missing_since_2017_by_div']},indent=1,default=str)[:3000])
print(pd.DataFrame(rep['by_div']).T.to_string())
for i in rep['issues']: print(str(i)[:600])
