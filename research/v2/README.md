# v2 (Kasım 2026): 22 lig ve oranlarla tahmin

Sırayla çalıştırılır (arşiv aynası: github.com/xgabora/Club-Football-Match-Data, `data/Matches.csv`):

1. `build.py <Matches.csv>` – 22 ligin temiz maç tablosu (`out/matches22.csv`) ve `data/history.csv`. Aynadaki takım adlarının
   football-data 2026-27 dosyalarıyla birebir aynı olduğu kontrol edildi.
2. `wf.py` – 2021-22..2025-26 için walk-forward takım gücü tahminleri (her maç yalnızca kendinden önceki maçlarla).
3. `blend.py` – Bet365 1X2 ve 2,5 gol oranlarından gol beklentisi; istatistikle karışım ağırlığı yalnızca 2021-24'te seçildi.
   Sonuç: en iyi ağırlık 1 (yalnızca oranlar); 2024-26'da 22 ligin hepsinde istatistikten daha isabetli.
4. `calibrate.py model oran` – devre durumları, İY/MS düzeltmesi ve korner katmanı 2021-24'te, iki yöntem için yeniden kuruldu.
5. `evaluate.py oran` / `evaluate.py model` – dokunulmamış 2024-26 sezonlarında test (`data/frozen/backtest.json`).

| 2024-26, 14.763 maç | Oranlarla (site) | Sadece istatistik |
|---|---|---|
| Maç sonucu log-kaybı (Bet365: 1,001) | 1,000 | 1,020 |
| 2,5 gol log-kaybı (Bet365: 0,679) | 0,679 | 0,687 |
| Banko: model dedi / tuttu | %80,0 / %81,2 | %80,4 / %79,8 |
| Sürpriz: model dedi / tuttu (olağan) | %17,4 / %17,5 (%11,7) | %18,3 / %18,1 (%12,4) |
