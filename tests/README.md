# Çevrimdışı test

İnternet olmadan bütün akışı denemek için (gerçek veriye dokunmaz, geçici bir kopyada çalışır):

```bash
cp -r . /tmp/ft && cd /tmp/ft
python tests/sahte_kaynaklar.py /tmp/ft 2026-11-19T10:00:00+00:00   # SAHTE ESPN ve oran dosyaları üretir
python tahmin/pipeline.py --offline --now 2026-11-19T10:00:00+00:00
node site/parity_test.js .cache/parity.json
```
`sahte_kaynaklar.py` yalnızca test içindir; zamanlanmış görev onu hiç çalıştırmaz.
