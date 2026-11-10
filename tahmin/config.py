# Frozen model configuration (chosen on validation seasons 2021-22..2023-24 only; see tune.py)
CFG=dict(window_days=1460,
         hl_goals=365, kappa_goals=10,
         hl_corners=240, kappa_corners=40,
         new_att_goals=-0.22, new_def_goals=-0.13,     # promoted-club prior (175 promoted team-seasons 2010-2020)
         new_att_corners=-0.09, new_def_corners=-0.08)
TOP=['T1','E0','SP1','I1','D1','F1','N1','P1']        # leagues used for validation/calibration
TARGET=['T1','E0','SP1','I1','D1','F1']               # leagues served in the page
VAL=[2021,2022,2023]; TEST=[2024,2025]
CORNER_1H_SHARE=0.470   # StatsBomb open data, 1,551 matches (2015/16 big-5): 46.98% of corners come before half-time
