# Çevrimdışı test

İnternet olmadan bütün akışı denemek için (gerçek veriye dokunmaz, geçici bir kopyada çalışır):

```bash
cp -r . /tmp/ft && cd /tmp/ft
python tests/sahte_kaynaklar.py /tmp/ft 2026-11-19T10:00:00+00:00 [Matches.csv]   # test akışlarını üretir
python tahmin/pipeline.py --offline --now 2026-11-19T10:00:00+00:00
node site/parity_test.js .cache/parity.json
```

`ornek_espn.json`, 10 Kasım 2026'da ESPN'den alınmış gerçek bir örnektir: 20 ligin 20–30 Kasım fikstürü, takım adları ve
DraftKings / Bet365 oranları (canlı skor yok). İskoçya League One / Two için sahte oranlı bir football-data fikstür dosyası yazılır.
İsteğe bağlı üçüncü argüman arşiv aynasının `Matches.csv` dosyasıdır; verilirse henüz sezon dosyası olmayan ligler için
2026-27'nin ilk haftaları yer tutucu olarak kopyaya yazılır (yalnızca test kopyasında).

`sahte_kaynaklar.py` yalnızca test içindir; güncelleme görevi onu hiç çalıştırmaz.
