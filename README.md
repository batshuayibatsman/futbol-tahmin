# Futbol Tahmin Bülteni

Süper Lig, Premier Lig, La Liga, Serie A, Bundesliga ve Ligue 1 için **istediğinde tek dokunuşla güncellenen** tahmin sitesi:
**https://batshuayibatsman.github.io/futbol-tahmin/**

Zamanlanmış çalıştırma yoktur. Güncelleme yalnızca sen istediğinde çalışır: GitHub veriyi kendisi çeker, modeli yeniden kurar,
tahminleri hesaplar ve siteyi yayınlar. Hiçbir şey yapıştırman gerekmez.

## Sitede ne var

- Her maç için ilk yarı ve maç sonu beklenen gol ve korner, skor olasılıkları, 9 hücreli İY/MS tablosu (1/2 ve 2/1 dönüşleri),
  gol ve korner alt/üst çizgileri, karşılıklı gol
- Sabit kurallarla seçilen **banko** ve **sürpriz** tahminler; maça **48 saatten az kala yapılan ilk güncellemede kilitlenir**, sonra değişmez
- Bahis sitelerinin oranları (Bet365, Pinnacle, en iyi, ortalama: 1X2, 2,5 gol, Asya handikap) ve her oran için modelin
  beklediği kazanç/kayıp
- **Canlı** sekmesi: oynanan maçların skoru, sıradaki maçlar, son biten maçlar
- **Canlı karne**: kilitlenen her seçim, oranıyla birlikte silinmeyen bir kayda yazılır; sonuçlar resmî istatistik gelince
  kendiliğinden işlenir (isabet, beklenen isabet, birim, getiri, en büyük düşüş)
- Geçmiş test (2024–26, 4.123 maç) ve veri durumu sayfası; Excel/CSV indirme

## Veri kaynakları ve güncelleme sıklığı

| Kaynak | Ne için | Ne zaman yenilenir |
|---|---|---|
| football-data.co.uk | Sonuç, devre skoru, korner (modelin verisi) | Kaynak Pazar ve Çarşamba geceleri günceller |
| football-data.co.uk | Oranlar (Bet365, Pinnacle, en iyi, ortalama) | Kaynak hafta sonu maçları için Cuma, hafta içi için Salı öğleden sonra ekler |
| ESPN (resmî olmayan açık veri) | İki haftalık fikstür, maç durumu, canlı skor | Her güncellemede; canlı skorlar sayfa açıkken her dakika |
| The Odds API (isteğe bağlı) | Daha sık ve daha çok sitenin oranları | Güncellemede, maçtan önceki 36 saatte, lig başına en sık 8 saatte bir |

İstekler sınırlıdır: bir güncellemede her siteye sınırlı sayıda istek gider. Ziyaretçilerin tarayıcısı kaynaklara istek atmaz
(ESPN izin veriyorsa canlı maç sırasında skorlar hariç).

### Daha sık oran istersen (ücretsiz)
1. the-odds-api.com'dan ücretsiz plana kaydol; e-postana bir anahtar gelir.
2. Bu depoda **Settings → Secrets and variables → Actions → New repository secret**: ad `ODDS_API_KEY`, değer anahtarın.
Site ayda en fazla ~440 kredi harcar (60 kredi yedekte kalır); ücretsiz plan 500 kredidir.

## Güncelleme nasıl başlatılır
- **GitHub'da:** Actions → "Verileri güncelle ve yayınla" → Run workflow. Bir iki dakikada site yenilenir.
- **Claude'a "güncelle" de:** Claude depodaki `guncelle.txt` dosyasını değiştirir, bu da aynı güncellemeyi başlatır.

Seçimler maça 48 saatten az kala yaptığın ilk güncellemede kilitlenir. O aralıkta güncelleme yapmazsan o maçın seçimi kayda
geçmez; maç başladıktan sonra hiçbir seçim kaydedilmez. Sonuçlar, football-data resmî istatistikleri geldikten sonraki ilk güncellemede işlenir.

## Dosyalar

| Klasör | İçerik |
|---|---|
| `tahmin/` | Model (`model.py`, `probs.py`, `config.py`), seçim kuralları (`markets.py`), kaynaklar (`sources.py`), takım adı eşleme (`names.py`), veri denetimi (`dataset.py`), seçim kaydı (`picks.py`), akış (`pipeline.py`), formül kilidi (`lock.py`) |
| `site/` | Sayfa (`template.html`), tarayıcı hesap motoru (`engine.js`), Python ile eşlik testi (`parity_test.js`) |
| `data/history.csv` | 2017-18'den 2025-26'ya 6 ligin 19.170 maçı (sonuç, devre, korner) |
| `data/seasons/` | Bu sezonun football-data dosyaları; her güncellemede yenilenir |
| `data/frozen/` | Doğrulama sezonlarında dondurulmuş kalibrasyon, lig sıklıkları ve geçmiş test sonuçları |
| `state/` | **Silinmeyen kayıt**: `picks.csv` (kilitlenen seçimler), `odds.csv` (seçimden sonra görülen oranlar), `results.csv` (sonuçlar) |
| `research/` | Modelin nasıl kurulduğu ve test edildiği (walk-forward test, ayar arama, kalibrasyon) |
| `tests/` | İnternetsiz deneme için sahte kaynak üretici |

## Kurallar
- **Formül kilidi:** `model.lock`, tahmin formülü dosyalarının parmak izini tutar. Biri onaysız değişirse güncelleme
  çalışmaz. Değişikliği `research/` ile test ettikten sonra `python tahmin/lock.py approve "neden"` çalıştırıp commit et.
- **Kayıt:** `state/` dosyalarına yalnızca satır eklenir; kaybeden seçimler silinmez, seçim kuralları sonradan değiştirilmez.
- Seçim, maç başladıktan sonra hiçbir zaman kaydedilmez.

## Geçmiş test özeti (2024-25 ve 2025-26, 4.123 maç)
- Bankolar: model ortalama %81,4 dedi, %81,4 tuttu. Sürprizler: model %18,4 dedi, %18,3 tuttu (olağan sıklık %12,2).
- Maç sonucu log-kaybı: model 0,988, Bet365 0,967, lig ortalaması 1,074. **Bahis piyasası modelden daha isabetli.**
- Modelin "değerli" bulduğu oranlarla düz oynamak %12–19 kaybettirdi; hiçbir kural oranlara karşı kâr etmedi.

## Bilinen sınırlar
Model sakatlık, ceza, rotasyon, teknik direktör değişikliği ve motivasyonu bilmez. Korner tahmini goller kadar güçlü değil.
İlk yarı kornerleri için ücretsiz resmî veri yok; toplamın %47'si varsayılır (StatsBomb açık verisinde 1.551 maçta doğrulandı).
ESPN resmî bir API sunmuyor; çalışmazsa fikstür football-data'nın oran dosyasından gelir.
Ücretsiz GitHub sitesi herkese açıktır.

Veri: football-data.co.uk (yalnızca tahmin amaçlı ücretsiz kullanım) · ESPN · The Odds API · StatsBomb Open Data ·
arşiv: github.com/xgabora/Club-Football-Match-Data-2000-2025.
