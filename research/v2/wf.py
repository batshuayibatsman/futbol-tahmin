"""v2: walk-forward team means for the 22 leagues, seasons 2021-22..2025-26 (each match predicted only from
matches played before it). Output: out/wf22.csv"""
import sys, time
sys.path.insert(0, 'tahmin')
import pandas as pd
from multiprocessing import Pool
from model import walk_forward
from config import CFG

L22 = ['E0', 'E1', 'E2', 'E3', 'EC', 'SC0', 'SC1', 'SC2', 'SC3', 'D1', 'D2', 'I1', 'I2', 'SP1', 'SP2',
       'F1', 'F2', 'N1', 'B1', 'P1', 'T1', 'G1']
SEASONS = [2021, 2022, 2023, 2024, 2025]
D = pd.read_csv('out/matches22.csv', parse_dates=['date'])


def run(dv):
    return walk_forward(D[D['div'] == dv], CFG, SEASONS)


if __name__ == '__main__':
    t0 = time.time()
    with Pool(2) as p:
        parts = p.map(run, L22)
    P = pd.concat(parts).sort_values(['date', 'div', 'home']).reset_index(drop=True)
    P.to_csv('out/wf22.csv', index=False)
    print(len(P), 'predictions', round(time.time() - t0), 's')
    print(P.groupby(['div', 'season']).size().unstack().to_string())
