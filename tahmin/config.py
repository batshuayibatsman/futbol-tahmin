# Frozen model configuration. v1 (team strengths) was chosen on validation seasons 2021-22..2023-24 only (see tune.py);
# v2 (Kasım 2026) extends it to 22 leagues and lets bookmaker odds set the goal means (research/v2/blend.py).
CFG=dict(window_days=1460,
         hl_goals=365, kappa_goals=10,
         hl_corners=240, kappa_corners=40,
         new_att_goals=-0.22, new_def_goals=-0.13,     # promoted-club prior (175 promoted team-seasons 2010-2020)
         new_att_corners=-0.09, new_def_corners=-0.08,
         s1_default=(0.446, 0.446))                    # first-half goal share, 22 leagues 2021-24 (for leagues without HT scores)
# leagues served in the page, in display order (all have full-time + half-time scores; all but EC have corners)
MAIN=['T1','E0','SP1','I1','D1','F1','N1','P1','B1','G1','SC0',
      'E1','SP2','I2','D2','F2','E2','E3','EC','SC1','SC2','SC3']
# leagues with full-time scores and 1X2 odds only (football-data.co.uk "new" files): no half-time or corner markets
EXTRA=['USA','ARG','AUT','BRA','CHN','DNK','FIN','IRL','SWE','SWZ','JPN','MEX','NOR','POL','ROU','RUS']
# competitions without a statistics model: predictions only from bookmaker odds, full-time markets only
ODDS_ONLY_MEN=['UCL','UEL','UECL']
ODDS_ONLY_WOMEN=['UWCL','WSL','LIGAF','FRW','NWSL']
ODDS_ONLY=ODDS_ONLY_MEN+ODDS_ONLY_WOMEN
TARGET=MAIN[:1]+ODDS_ONLY_MEN+MAIN[1:]+EXTRA+ODDS_ONLY_WOMEN
TOP=MAIN                                              # v2: calibration on the 22 leagues with half-time scores
VAL=[2021,2022,2023]; TEST=[2024,2025]
CORNER_1H_SHARE=0.470   # StatsBomb open data, 1,551 matches (2015/16 big-5): 46.98% of corners come before half-time
# Weight of the odds-implied goal means (1 = odds only). Chosen on 2021-23: the exact-score log-likelihood was best
# at 1.0 for both the strength ratio (wr) and the goal total (wt); on 2024-26 it beat the statistics model in all 22 leagues.
ODDS_BLEND=dict(wr=1.0, wt=1.0)
