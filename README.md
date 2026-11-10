# Futbol Tahmin Bülteni

Süper Lig, Premier Lig, La Liga, Serie A, Bundesliga ve Ligue 1 için **kendi kendine güncellenen** tahmin sitesi:
**https://batshuayibatsman.github.io/futbol-tahmin/**

GitHub her 20 dakikada bir veriyi kendisi çeker, modeli yeniden kurar, tahminleri hesaplar ve siteyi yayınlar.
Senin hiçbir şey yapıştırman ya da çalıştırman gerekmez. Sayfa açıkken de kendini yeniler.

## Sitede ne var

- Her maç için ilk yarı ve maç sonu beklenen gol ve korner, skor olasılıkları, 9 hücreli İY/MS tablosu (1/2 ve 2/1 dönüşleri),
  gol ve korner alt/üst çizgileri, karşılıklı gol
- Sabit kurallarla seçilen **banko** ve **sürpriz** tahminler; maçtan **48 saat önce kilitlenir**, sonra değişmez
- Bahis sitelerinin oranları (Bet365, Pinnacle, en iyi, ortalama: 1X2, 2,5 gol, Asya handikap) ve her oran için modelin
  beklediği kazanç/kayıp
- **Canlı** sekmesi: oynanan maçların skoru, sıradaki maçlar, son biten maçlar
- **Canlı karne**: kilitlenen her seçim, oranıyla birlikte silinmeyen bir kayda yazılır; sonuçlar resmî istatistik gelince
  kendiliğinden işlenir (isabet, beklenen isabet, birim, getiri, en büyük düşüş)
- Geçmiş test (2024–26, 4.123 maç) ve veri durumu sayfası; Excel/CSV indirme

## Veri kaynakları ve güncelleme sıklığı

| Kaynak | Ne için | Ne zaman yenilenir |
|---|---|---|
| football-data.co.uk | Sonuç, devre skoru, korner (modelin verisi) | Site 3 saatte bir bakar; kaynak Pazar ve Çarşamba geceleri günceller |
| football-data.co.uk | Oranlar (Bet365, Pinnacle, en iyi, ortalama) | Kaynak hafta sonu maçları için Cuma, hafta içi için Salı öğleden sonra ekler |
| ESPN (resmî olmayan açık veri) | İki haftalık fikstür, maç durumu, canlı skor | Her 20 dakika; maç saatlerinde 10 dakika |
| The Odds API (isteğe bağlı) | Daha sık ve daha çok sitenin oranları | Maçtan önceki 36 saatte, lig başına en sık 8 saatte bir |

İstekler sınırlıdır: her kaynak için önbellek ve en kısa yenileme süresi vardır, değişmeyen dosya yeniden indirilmez,
bir çalıştırmada her siteye en fazla birkaç istek gider. Ziyaretçilerin tarayıcısı kaynaklara istek atmaz
(ESPN izin veriyorsa canlı maç sırasında skorlar hariç).

### Daha sık oran istersen (ücretsiz)
1. the-odds-api.com'dan ücretsiz plana kaydol; e-postana bir anahtar gelir.
2. Bu depoda **Settings → Secrets and variables → Actions → New repository secret**: ad `ODDS_API_KEY`, değer anahtarın.
Site ayda en fazla ~440 kredi harcar (60 kredi yedekte kalır); ücretsiz plan 500 kredidir.

## Elle yenileme
**Actions → "Verileri güncelle ve yayınla" → Run workflow.** "Önbelleği yok say" kutusunu işaretlersen her şey yeniden indirilir.

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
- **Formül kilidi:** `model.lock`, tahmin formülü dosyalarının parmak izini tutar. Biri onaysız değişirse otomatik güncelleme
  durur. Değişikliği `research/` ile test ettikten sonra `python tahmin/lock.py approve "neden"` çalıştırıp commit et.
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
