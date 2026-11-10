# Futbol Tahmin Bülteni

22 lig için **istediğinde tek dokunuşla güncellenen** tahmin sitesi:
**https://batshuayibatsman.github.io/futbol-tahmin/**

Türkiye Süper Lig · İngiltere Premier Lig, Championship, League One, League Two, National League · İskoçya Premiership,
Championship, League One, League Two · Almanya Bundesliga, 2. Bundesliga · İtalya Serie A, Serie B · İspanya La Liga,
La Liga 2 · Fransa Ligue 1, Ligue 2 · Hollanda Eredivisie · Belçika Pro League · Portekiz Liga Portugal · Yunanistan Süper Lig.

Zamanlanmış çalıştırma yoktur. Güncelleme yalnızca sen istediğinde çalışır: GitHub veriyi kendisi çeker, modeli yeniden kurar,
tahminleri hesaplar ve siteyi yayınlar. Hiçbir şey yapıştırman gerekmez.

## Sitede ne var

- Her maç için ilk yarı ve maç sonu beklenen gol ve korner, skor olasılıkları, 9 hücreli İY/MS tablosu (1/2 ve 2/1 dönüşleri),
  gol ve korner alt/üst çizgileri, karşılıklı gol
- **Maç arama** (takım ya da lig adı; Türkçe karakter fark etmez) ve ülkelere göre gruplanmış lig seçimi
- Sabit kurallarla seçilen **banko** ve **sürpriz** tahminler; maç başlayana kadar her güncellemede yeniden hesaplanır,
  karneye **maç başlamadan önceki son güncellemede görünen seçim** yazılır
- **Oranlara göre tahmin:** maçın bahis oranları varsa iki takımın gol beklentisi bu oranlardan türetilir; oranlar değişince
  tahmin de bir sonraki güncellemede değişir. Oran yoksa tahmin istatistikten gelir. Her maçta "sadece istatistik" ile
  oranların nerede ayrıştığı da gösterilir.
- Bahis sitelerinin oranları (DraftKings ve Bet365 ESPN'den; Bet365, en iyi ve ortalama football-data'dan) ve her oran için
  beklenen kazanç/kayıp
- **Canlı** sekmesi, **canlı karne** (silinmeyen kayıt; isabet, beklenen isabet, birim, getiri), geçmiş test ve veri durumu; Excel/CSV indirme

## Veri kaynakları

| Kaynak | Ne için | Ne zaman yenilenir |
|---|---|---|
| football-data.co.uk | Sonuç, devre skoru, korner (modelin verisi) | Kaynak Pazar ve Çarşamba geceleri günceller |
| football-data.co.uk | Oranlar (Bet365, en iyi, ortalama) ve İskoçya League One / Two fikstürü | Kaynak Salı ve Cuma öğleden sonra ekler |
| ESPN (resmî olmayan açık veri) | İki haftalık fikstür, maç durumu, canlı skor, **güncel oranlar** (DraftKings, Bet365) | Her güncellemede; canlı skorlar sayfa açıkken her dakika |
| The Odds API (isteğe bağlı) | Daha çok sitenin oranları | Güncellemede, maçtan önceki 36 saatte, lig başına en sık 8 saatte bir |

ESPN İskoçya League One ve League Two'yu güncel tutmuyor; bu iki ligin fikstürü football-data oran dosyasından gelir (yaklaşık bir hafta önceden).
National League'in resmî verisinde korner yok; o ligde korner tahmini gösterilmez. Bir güncellemede her siteye sınırlı sayıda istek gider.
Ziyaretçilerin tarayıcısı kaynaklara istek atmaz (ESPN izin veriyorsa canlı maç sırasında skorlar hariç).

### Daha çok sitenin oranı (isteğe bağlı, ücretsiz)
1. the-odds-api.com'dan ücretsiz plana kaydol; e-postana bir anahtar gelir.
2. Bu depoda **Settings → Secrets and variables → Actions → New repository secret**: ad `ODDS_API_KEY`, değer anahtarın.

## Güncelleme nasıl başlatılır
- **GitHub'da:** Actions → "Verileri güncelle ve yayınla" → Run workflow. Birkaç dakikada site yenilenir.
- **Claude'a "güncelle" de:** Claude depodaki `guncelle.txt` dosyasını değiştirir, bu da aynı güncellemeyi başlatır.

Karneye, maç başlamadan önceki son güncellemede sitede görünen seçim yazılır (maç başladıktan sonraki ilk güncellemede).
Sonuçlar, football-data resmî istatistikleri geldikten sonraki ilk güncellemede işlenir.

## Dosyalar

| Klasör | İçerik |
|---|---|
| `tahmin/` | Model (`model.py`, `probs.py`, `config.py`), oranlardan gol beklentisi (`market.py`), seçim kuralları (`markets.py`), kaynaklar (`sources.py`), takım adı eşleme (`names.py`), veri denetimi (`dataset.py`), seçim kaydı (`picks.py`), akış (`pipeline.py`), formül kilidi (`lock.py`) |
| `site/` | Sayfa (`template.html`), tarayıcı hesap motoru (`engine.js`), Python ile eşlik testi (`parity_test.js`) |
| `data/history.csv` | 2017-18'den 2025-26'ya 22 ligin 67.785 maçı (sonuç, devre, korner, Bet365 oranları) |
| `data/seasons/` | Bu sezonun football-data dosyaları (her güncellemede yenilenir) ve arşivde eksik olan birkaç eski sezon |
| `data/frozen/` | Doğrulama sezonlarında dondurulmuş kalibrasyon, lig sıklıkları ve geçmiş test sonuçları |
| `state/` | **Silinmeyen kayıt**: `picks.csv` (karnedeki seçimler), `odds.csv` (o seçimlerin oranları), `results.csv` (sonuçlar), `pre_kickoff.json` (her maçın maç öncesi son tahmini) |
| `research/` | Modelin nasıl kurulduğu ve test edildiği; `research/v2/` 22 lig ve oranlarla tahmin |
| `tests/` | İnternetsiz deneme (gerçek ESPN fikstür ve oran örneğiyle) |

## Kurallar
- **Formül kilidi:** `model.lock`, tahmin formülü dosyalarının parmak izini tutar. Biri onaysız değişirse güncelleme
  çalışmaz. Değişikliği `research/` ile test ettikten sonra `python tahmin/lock.py approve "neden"` çalıştırıp commit et.
- **Kayıt:** `state/` dosyalarına yalnızca satır eklenir; kaybeden seçimler silinmez, seçim kuralları sonradan değiştirilmez.
- Seçim, maç başladıktan sonra hiçbir zaman değişmez.

## Geçmiş test özeti (2024-25 ve 2025-26, 22 lig, 14.763 maç)
Her maç yalnızca kendinden önce oynanmış maçlarla ve o maçın maç öncesi Bet365 oranlarıyla tahmin edildi; ayarlar 2021-24 sezonlarında seçildi.
- Bankolar: model ortalama %80,0 dedi, %81,2 tuttu. Sürprizler: model %17,4 dedi, %17,5 tuttu (olağan sıklık %11,7).
- Oranları hiç kullanmayan eski yöntemle bankolar %79,8 tutuyordu; maç sonucu log-kaybı 1,020 → 1,000 (Bet365'in kendisi 1,001).
- Oranlardan türetilen gol beklentisi 22 ligin hepsinde sadece istatistikten daha isabetliydi (`research/v2/blend.py`).
- Hiçbir seçim kuralı bahis oranlarına karşı güvenilir bir kâr göstermedi.

## Bilinen sınırlar
Oran gelmeden önceki tahminler sakatlık, ceza, rotasyon, teknik direktör değişikliği ve motivasyonu bilmez.
Devre, İY/MS ve korner hesapları her zaman istatistik modelinden gelir (ücretsiz veride bunların oranı yok).
İlk yarı kornerleri için ücretsiz resmî veri yok; toplamın %47'si varsayılır (StatsBomb açık verisinde 1.551 maçta doğrulandı).
ESPN resmî bir API sunmuyor; çalışmazsa fikstür ve oranlar football-data'dan gelir. Ücretsiz GitHub sitesi herkese açıktır.

Veri: football-data.co.uk (yalnızca tahmin amaçlı ücretsiz kullanım) · ESPN · The Odds API · StatsBomb Open Data ·
arşiv: github.com/xgabora/Club-Football-Match-Data.
