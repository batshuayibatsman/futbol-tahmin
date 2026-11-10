"""Excel copy of the pick log, rebuilt on every run from state/*.csv (the CSV files are the source of truth).
Net units, cumulative units and drawdown are Excel formulas so the numbers can be checked by hand."""
import datetime as dt
from zoneinfo import ZoneInfo
import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

F = 'Arial'; TR = ZoneInfo('Europe/Istanbul')
HDR = PatternFill('solid', fgColor='1F2A24'); thin = Side(style='thin', color='C9D1C8')
COLS = [('No', 5), ('Son tahmin (TSİ)', 16), ('Lig', 11), ('Maç tarihi', 11), ('Saat', 7), ('Ev sahibi', 17), ('Deplasman', 17), ('Tür', 9),
        ('Pazar', 15), ('Model olasılığı', 10), ('Adil oran', 8), ('Olağan sıklık', 9), ('Bet365', 8), ('En iyi oran', 9), ('Sonuç', 13),
        ('Skor (İY)', 10), ('Korner', 7), ('Net Bet365', 9), ('Net en iyi', 9), ('Kümülatif (en iyi)', 10), ('Zirve', 8), ('Düşüş', 8)]


def _tr(s):
    try:
        return dt.datetime.fromisoformat(s).astimezone(TR).strftime('%d.%m.%Y %H:%M')
    except Exception:
        return s


def build(T, path, perf):
    wb = Workbook(); ws = wb.active; ws.title = 'Kayıt'
    for c, (h, w) in enumerate(COLS, 1):
        x = ws.cell(1, c, h); x.font = Font(name=F, size=10, bold=True, color='FFFFFF'); x.fill = HDR
        x.alignment = Alignment(wrap_text=True, vertical='center'); ws.column_dimensions[get_column_letter(c)].width = w
    ws.row_dimensions[1].height = 30
    n = len(T)
    for i, r in enumerate(T.to_dict('records'), start=2):
        def v(k):
            x = r.get(k)
            return None if x is None or (isinstance(x, float) and pd.isna(x)) or x == '' else x
        score = f"{int(r['hg'])}-{int(r['ag'])}" + (f" ({int(r['hthg'])}-{int(r['htag'])})" if v('hthg') is not None else '') if v('hg') is not None else None
        corners = int(r['hc']) + int(r['ac']) if v('hc') is not None and v('ac') is not None else None
        vals = [i - 1, _tr(r['kilit_utc']), r['lig'], dt.date.fromisoformat(r['tarih_tsi']), r['saat_tsi'], r['ev_ad'], r['dep_ad'], r['tur'],
                str(r['pazar']).replace('Sürpriz ', ''), float(r['olasilik']), f'=1/J{i}', v('olagan'), v('b365'), v('en_iyi'),
                v('durum') or 'Bekliyor', score, corners]
        for c, x in enumerate(vals, 1):
            ws.cell(i, c, x)
        ws.cell(i, 18, f'=IF(OR(M{i}="",AND(O{i}<>"Tuttu",O{i}<>"Tutmadı")),"",IF(O{i}="Tuttu",M{i}-1,-1))')
        ws.cell(i, 19, f'=IF(OR(N{i}="",AND(O{i}<>"Tuttu",O{i}<>"Tutmadı")),"",IF(O{i}="Tuttu",N{i}-1,-1))')
        ws.cell(i, 20, f'=IF(ISNUMBER(S{i}),S{i},0)' if i == 2 else f'=T{i-1}+IF(ISNUMBER(S{i}),S{i},0)')
        ws.cell(i, 21, f'=MAX(0,T{i})' if i == 2 else f'=MAX(U{i-1},T{i})')
        ws.cell(i, 22, f'=U{i}-T{i}')
        for c in range(1, len(COLS) + 1):
            ws.cell(i, c).font = Font(name=F, size=10, color='808080' if c in (21, 22) else '000000'); ws.cell(i, c).border = Border(bottom=thin)
        ws.cell(i, 4).number_format = 'DD.MM.YYYY'; ws.cell(i, 10).number_format = '0.0%'; ws.cell(i, 12).number_format = '0.0%'
        for c in (11, 13, 14):
            ws.cell(i, c).number_format = '0.00'
        for c in (18, 19, 20, 21, 22):
            ws.cell(i, c).number_format = '+0.00;-0.00;0.00'
    ws.freeze_panes = 'J2'
    if n:
        ws.auto_filter.ref = f'A1:V{n + 1}'
    S = wb.create_sheet('Özet', 0)
    S.column_dimensions['A'].width = 40
    for c in 'BCD':
        S.column_dimensions[c].width = 13
    S['A1'] = 'Canlı takip özeti'; S['A1'].font = Font(name=F, size=14, bold=True)
    S['A2'] = (f'Kayıttan formülle hesaplanır. Her satır, maçtan önceki son güncellemede sitede görünen seçimdir; hiçbir satır silinmez. '
               f'Oluşturulma: {dt.datetime.now(TR):%d.%m.%Y %H:%M} TSİ')
    S['A2'].font = Font(name=F, size=9, italic=True, color='555555')
    last = max(n + 1, 2)
    Ty, Rs, P = f'Kayıt!$H$2:$H${last}', f'Kayıt!$O$2:$O${last}', f'Kayıt!$J$2:$J${last}'
    S['A4'], S['B4'], S['C4'], S['D4'] = 'Ölçü', 'Tümü', 'BANKO', 'SÜRPRİZ'
    def f3(a, t):
        return [a, t.replace('#T', '"BANKO"'), t.replace('#T', '"SÜRPRİZ"')]
    rows = [('Karnedeki seçim', f'=COUNTA(Kayıt!$I$2:$I${last})', f'=COUNTIF({Ty},#T)'),
            ('Tuttu', f'=COUNTIF({Rs},"Tuttu")', f'=COUNTIFS({Ty},#T,{Rs},"Tuttu")'),
            ('Tutmadı', f'=COUNTIF({Rs},"Tutmadı")', f'=COUNTIFS({Ty},#T,{Rs},"Tutmadı")'),
            ('Bekliyor / doğrulanamadı', f'=B5-B6-B7', None)]
    for k, (lab, fa, ft) in enumerate(rows):
        i = 5 + k; S.cell(i, 1, lab)
        vals = f3(fa, ft) if ft else [fa, f'=C5-C6-C7', f'=D5-D6-D7']
        for c, x in enumerate(vals, 2):
            S.cell(i, c, x)
    for c in 'BCD':
        t = '' if c == 'B' else ('"BANKO"' if c == 'C' else '"SÜRPRİZ"')
        S[f'{c}9'] = f'=IF({c}6+{c}7=0,"",{c}6/({c}6+{c}7))'
        cond = f'(({Rs}="Tuttu")+({Rs}="Tutmadı"))' + (f'*({Ty}={t})' if t else '')
        S[f'{c}10'] = f'=IF({c}6+{c}7=0,"",SUMPRODUCT({cond}*{P})/({c}6+{c}7))'
        for row, col in ((11, 'R'), (12, 'S')):
            rng = f'Kayıt!${col}$2:${col}${last}'
            S[f'{c}{row}'] = f'=SUMPRODUCT(ISNUMBER({rng})*1{("*(" + Ty + "=" + t + ")") if t else ""})'
            S[f'{c}{row + 2}'] = f'=SUMIFS({rng},{Ty},{t})' if t else f'=SUM({rng})'
        S[f'{c}15'] = f'=IF({c}12=0,"",{c}14/{c}12)'
    labels = {9: 'İsabet (sonuçlananlar)', 10: 'Modelin beklediği isabet', 11: 'Bet365 oranı olan', 12: 'En iyi oranı olan',
              13: 'Net birim (Bet365)', 14: 'Net birim (en iyi oran)', 15: 'Getiri (en iyi oran)'}
    for i, lab in labels.items():
        S.cell(i, 1, lab)
    S['A16'] = 'En büyük düşüş (en iyi oran, birim)'; S['B16'] = f'=MAX(Kayıt!$V$2:$V${last})'
    for i in range(4, 17):
        for c in range(1, 5):
            x = S.cell(i, c); x.font = Font(name=F, size=10, bold=(i == 4), color='FFFFFF' if i == 4 else '000000')
            if i == 4:
                x.fill = HDR
            x.border = Border(bottom=thin)
    for c in 'BCD':
        S[f'{c}9'].number_format = '0.0%'; S[f'{c}10'].number_format = '0.0%'; S[f'{c}15'].number_format = '0.0%'
        S[f'{c}13'].number_format = '+0.00;-0.00;0.00'; S[f'{c}14'].number_format = '+0.00;-0.00;0.00'
    S['B16'].number_format = '0.00'
    notes = ['Oranlar: maçtan önceki son güncellemede görülen fiyatlar (ESPN: DraftKings, Bet365; football-data.co.uk; varsa The Odds API). Korner, İY ve çifte şans için ücretsiz oran yok: bu seçimler isabete sayılır, birime sayılmaz.',
             'Sonuçlar football-data.co.uk resmî maç istatistiklerinden (devre skoru, maç sonu, korner) otomatik işlenir.',
             'Bu dosya her güncellemede yeniden üretilir; elle yapılan değişiklikler saklanmaz. Kaynak: depodaki state/picks.csv, odds.csv, results.csv.']
    for k, t in enumerate(notes):
        S.cell(18 + k, 1, '• ' + t).font = Font(name=F, size=9, color='333333')
    wb.calculation.fullCalcOnLoad = True
    wb.save(path)
