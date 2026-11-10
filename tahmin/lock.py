"""Formula lock: the scheduled job refuses to publish if a prediction-formula file changed without approval.
    python tahmin/lock.py check      (run by the workflow)
    python tahmin/lock.py approve "neden"   (after re-running the backtest in research/; records the change)"""
import hashlib, json, sys, datetime as dt
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FILES = ['tahmin/config.py', 'tahmin/model.py', 'tahmin/probs.py', 'tahmin/markets.py', 'site/engine.js', 'data/frozen/cal_val.json', 'data/frozen/base_rates.json']


def digest():
    return {f: hashlib.sha256((ROOT / f).read_bytes()).hexdigest() for f in FILES}


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'check'
    lock = ROOT / 'model.lock'
    cur = digest()
    if cmd == 'approve':
        why = ' '.join(sys.argv[2:]) or 'gerekçe yazılmadı'
        old = json.loads(lock.read_text()) if lock.exists() else {}
        changed = [f for f in FILES if old.get(f) != cur[f]]
        lock.write_text(json.dumps(cur, indent=1) + '\n')
        with open(ROOT / 'model_degisiklikleri.log', 'a', encoding='utf-8') as g:
            g.write(f'{dt.datetime.now(dt.timezone.utc):%Y-%m-%d %H:%M} UTC | {why} | {changed}\n')
        print('onaylandı:', changed)
        return
    if not lock.exists():
        sys.exit('model.lock yok: önce "python tahmin/lock.py approve ilk kurulum" çalıştır.')
    old = json.loads(lock.read_text())
    changed = [f for f in FILES if old.get(f) != cur[f]]
    if changed:
        sys.exit('DURDU: tahmin formülü dosyaları onaysız değişmiş: ' + ', '.join(changed) +
                 '. Yeni ayarı research/ ile test ettikten sonra "python tahmin/lock.py approve <neden>" çalıştırıp commit et.')
    print('formül kilidi tamam')


if __name__ == '__main__':
    main()
