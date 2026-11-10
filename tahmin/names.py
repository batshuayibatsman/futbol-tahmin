"""Team names. The model's canonical names are football-data.co.uk's (they are consistent across seasons).
External feeds (ESPN, The Odds API) are mapped onto them: alias table first, then normalised/fuzzy matching
with a one-to-one constraint inside each league. Anything below the threshold is reported, never guessed."""
import re, unicodedata
from difflib import SequenceMatcher

# Turkish-friendly display names (canonical -> shown)
DISPLAY = {
    'Besiktas': 'Beşiktaş', 'Buyuksehyr': 'Başakşehir', 'Corum': 'Çorum FK', 'Eyupspor': 'Eyüpspor', 'Fenerbahce': 'Fenerbahçe',
    'Gaziantep': 'Gaziantep FK', 'Genclerbirligi': 'Gençlerbirliği', 'Goztep': 'Göztepe', 'Kasimpasa': 'Kasımpaşa', 'Karagumruk': 'Karagümrük',
    'Ad. Demirspor': 'Adana Demirspor', 'Ankaragucu': 'Ankaragücü', 'Istanbulspor': 'İstanbulspor', 'Umraniyespor': 'Ümraniyespor',
    'Man City': 'Manchester City', 'Man United': 'Manchester United', "Nott'm Forest": 'Nottingham Forest', 'Hull': 'Hull City',
    'Ipswich': 'Ipswich Town', 'Leeds': 'Leeds United', 'Coventry': 'Coventry City', 'Newcastle': 'Newcastle United', 'Wolves': 'Wolverhampton',
    'Alaves': 'Alavés', 'Ath Bilbao': 'Athletic Bilbao', 'Ath Madrid': 'Atlético Madrid', 'Betis': 'Real Betis', 'Celta': 'Celta Vigo',
    'Espanol': 'Espanyol', 'La Coruna': 'Deportivo La Coruña', 'Malaga': 'Málaga', 'Santander': 'Racing Santander', 'Sociedad': 'Real Sociedad',
    'Vallecano': 'Rayo Vallecano', 'Cadiz': 'Cádiz', 'Almeria': 'Almería', 'Leganes': 'Leganés', 'Sp Gijon': 'Sporting Gijón',
    'Bayern Munich': 'Bayern Münih', 'Ein Frankfurt': 'Eintracht Frankfurt', 'FC Koln': 'Köln', "M'gladbach": 'Mönchengladbach',
    'Paris SG': 'PSG', 'St Etienne': 'Saint-Étienne',
}


def display(t):
    return DISPLAY.get(t, t)


# external name -> canonical, per league (ESPN displayName / shortDisplayName, The Odds API names, common variants)
ALIASES = {
    'ENG': {'afc bournemouth': 'Bournemouth', 'brighton & hove albion': 'Brighton', 'brighton and hove albion': 'Brighton',
           'coventry city': 'Coventry', 'hull city': 'Hull', 'ipswich town': 'Ipswich', 'leeds united': 'Leeds',
           'manchester city': 'Man City', 'man city': 'Man City', 'manchester united': 'Man United', 'man utd': 'Man United', 'man united': 'Man United',
           'newcastle united': 'Newcastle', 'nottingham forest': "Nott'm Forest", "nott'm forest": "Nott'm Forest", 'tottenham hotspur': 'Tottenham',
           'wolverhampton wanderers': 'Wolves', 'wolverhampton': 'Wolves', 'west ham united': 'West Ham', 'leicester city': 'Leicester',
           'luton town': 'Luton', 'norwich city': 'Norwich', 'stoke city': 'Stoke', 'swansea city': 'Swansea', 'cardiff city': 'Cardiff',
           'west bromwich albion': 'West Brom', 'queens park rangers': 'QPR', 'derby county': 'Derby', 'birmingham city': 'Birmingham',
           'blackburn rovers': 'Blackburn', 'preston north end': 'Preston', 'charlton athletic': 'Charlton', 'oxford united': 'Oxford',
           'plymouth argyle': 'Plymouth', 'lincoln city': 'Lincoln', 'sheffield wednesday': 'Sheffield Weds'},
    'ESP': {'athletic club': 'Ath Bilbao', 'athletic bilbao': 'Ath Bilbao', 'atletico madrid': 'Ath Madrid', 'atlético madrid': 'Ath Madrid',
            'atletico de madrid': 'Ath Madrid', 'real betis': 'Betis', 'celta vigo': 'Celta', 'rc celta': 'Celta', 'celta de vigo': 'Celta',
            'espanyol': 'Espanol', 'rcd espanyol': 'Espanol', 'deportivo la coruña': 'La Coruna', 'deportivo la coruna': 'La Coruna',
            'deportivo': 'La Coruna', 'rc deportivo': 'La Coruna', 'málaga': 'Malaga', 'racing santander': 'Santander', 'racing': 'Santander',
            'real sociedad': 'Sociedad', 'rayo vallecano': 'Vallecano', 'alavés': 'Alaves', 'deportivo alavés': 'Alaves', 'deportivo alaves': 'Alaves',
            'real oviedo': 'Oviedo', 'real valladolid': 'Valladolid', 'leganés': 'Leganes', 'cádiz': 'Cadiz', 'almería': 'Almeria',
            'sporting gijón': 'Sp Gijon', 'sporting gijon': 'Sp Gijon', 'real zaragoza': 'Zaragoza', 'ud las palmas': 'Las Palmas'},
    'ITA': {'internazionale': 'Inter', 'inter milan': 'Inter', 'inter': 'Inter', 'ac milan': 'Milan', 'as roma': 'Roma', 'hellas verona': 'Verona',
           'ss lazio': 'Lazio', 'ssc napoli': 'Napoli', 'juventus fc': 'Juventus'},
    'GER': {'bayern munich': 'Bayern Munich', 'bayern münchen': 'Bayern Munich', 'fc bayern münchen': 'Bayern Munich', 'borussia dortmund': 'Dortmund',
           'eintracht frankfurt': 'Ein Frankfurt', 'sv elversberg': 'Elversberg', 'sv 07 elversberg': 'Elversberg', 'fc cologne': 'FC Koln',
           '1. fc köln': 'FC Koln', 'fc köln': 'FC Koln', 'fc koln': 'FC Koln', 'cologne': 'FC Koln', 'köln': 'FC Koln', 'sc freiburg': 'Freiburg',
           'hamburg sv': 'Hamburg', 'hamburger sv': 'Hamburg', 'tsg hoffenheim': 'Hoffenheim', 'tsg 1899 hoffenheim': 'Hoffenheim',
           'bayer leverkusen': 'Leverkusen', 'borussia mönchengladbach': "M'gladbach", 'borussia monchengladbach': "M'gladbach",
           'gladbach': "M'gladbach", "m'gladbach": "M'gladbach", 'mainz': 'Mainz', 'fsv mainz': 'Mainz', '1. fsv mainz 05': 'Mainz', 'mainz 05': 'Mainz',
           'sc paderborn 07': 'Paderborn', 'sc paderborn': 'Paderborn', 'fc schalke 04': 'Schalke 04', 'vfb stuttgart': 'Stuttgart',
           '1. fc union berlin': 'Union Berlin', 'sv werder bremen': 'Werder Bremen', 'fc augsburg': 'Augsburg', 'vfl wolfsburg': 'Wolfsburg',
           '1. fc heidenheim 1846': 'Heidenheim', 'fc heidenheim': 'Heidenheim', 'fc st. pauli': 'St Pauli', 'st. pauli': 'St Pauli',
           'vfl bochum': 'Bochum', 'sv darmstadt 98': 'Darmstadt', 'hertha berlin': 'Hertha', 'hertha bsc': 'Hertha', '1. fc nürnberg': 'Nurnberg'},
    'FRA': {'aj auxerre': 'Auxerre', 'stade brestois 29': 'Brest', 'stade brest 29': 'Brest', 'le havre ac': 'Le Havre', 'rc lens': 'Lens',
           'racing club de lens': 'Lens', 'losc lille': 'Lille', 'lille osc': 'Lille', 'olympique lyonnais': 'Lyon', 'olympique lyon': 'Lyon',
           'olympique de marseille': 'Marseille', 'olympique marseille': 'Marseille', 'as monaco': 'Monaco', 'ogc nice': 'Nice',
           'paris saint-germain': 'Paris SG', 'paris saint germain': 'Paris SG', 'psg': 'Paris SG', 'stade rennais': 'Rennes',
           'stade rennais fc': 'Rennes', 'rc strasbourg': 'Strasbourg', 'strasbourg alsace': 'Strasbourg', 'rc strasbourg alsace': 'Strasbourg',
           'toulouse fc': 'Toulouse', 'estac troyes': 'Troyes', 'es troyes ac': 'Troyes', 'angers sco': 'Angers', 'le mans fc': 'Le Mans',
           'fc lorient': 'Lorient', 'fc nantes': 'Nantes', 'saint-etienne': 'St Etienne', 'saint-étienne': 'St Etienne', 'as saint-étienne': 'St Etienne',
           'stade de reims': 'Reims', 'clermont foot': 'Clermont', 'montpellier hsc': 'Montpellier', 'fc metz': 'Metz'},
    'TUR': {'istanbul basaksehir': 'Buyuksehyr', 'başakşehir': 'Buyuksehyr', 'basaksehir': 'Buyuksehyr', 'istanbul basaksehir fk': 'Buyuksehyr',
           'rams başakşehir': 'Buyuksehyr', 'goztepe': 'Goztep', 'göztepe': 'Goztep', 'caykur rizespor': 'Rizespor', 'çaykur rizespor': 'Rizespor',
           'corum fk': 'Corum', 'çorum': 'Corum', 'çorum fk': 'Corum', 'arca çorum fk': 'Corum', 'besiktas jk': 'Besiktas', 'beşiktaş': 'Besiktas',
           'fenerbahçe': 'Fenerbahce', 'gaziantep fk': 'Gaziantep', 'gençlerbirliği': 'Genclerbirligi', 'kasımpaşa': 'Kasimpasa',
           'eyüpspor': 'Eyupspor', 'amed sk': 'Amedspor', 'amed sfk': 'Amedspor', 'amed': 'Amedspor', 'amed sportif faaliyetler': 'Amedspor', 'erzurumspor fk': 'Erzurumspor',
           'erzurum bb': 'Erzurumspor', 'fatih karagumruk': 'Karagumruk', 'fatih karagümrük': 'Karagumruk', 'adana demirspor': 'Ad. Demirspor',
           'mke ankaragucu': 'Ankaragucu', 'ankaragücü': 'Ankaragucu', 'umraniyespor': 'Umraniyespor', 'sivasspor': 'Sivasspor',
           'corendon alanyaspor': 'Alanyaspor', 'tümosan konyaspor': 'Konyaspor', 'tumosan konyaspor': 'Konyaspor'},
}

# clubs move between divisions of one country, so aliases are kept per country
GROUP = {'E0': 'ENG', 'E1': 'ENG', 'E2': 'ENG', 'E3': 'ENG', 'EC': 'ENG', 'SC0': 'SCO', 'SC1': 'SCO', 'SC2': 'SCO', 'SC3': 'SCO',
         'D1': 'GER', 'D2': 'GER', 'I1': 'ITA', 'I2': 'ITA', 'SP1': 'ESP', 'SP2': 'ESP', 'F1': 'FRA', 'F2': 'FRA',
         'N1': 'NED', 'B1': 'BEL', 'P1': 'POR', 'T1': 'TUR', 'G1': 'GRE'}
MORE = {
    'ENG': {'peterborough united': 'Peterboro', 'bristol rovers': 'Bristol Rvs', 'boston united': 'Boston Utd', 'mk dons': 'Milton Keynes Dons',
            'milton keynes dons': 'Milton Keynes Dons', 'afc fylde': 'Fylde', 'fc halifax town': 'Halifax', 'forest green rovers': 'Forest Green',
            'wigan athletic': 'Wigan', 'wycombe wanderers': 'Wycombe', 'bolton wanderers': 'Bolton', 'accrington stanley': 'Accrington',
            'crewe alexandra': 'Crewe', 'oldham athletic': 'Oldham', 'tranmere rovers': 'Tranmere', 'doncaster rovers': 'Doncaster'},
    'SCO': {'heart of midlothian': 'Hearts', 'hearts': 'Hearts', 'inverness caledonian thistle': 'Inverness C', 'inverness ct': 'Inverness C',
            'raith rovers': 'Raith Rvs', 'airdrieonians': 'Airdrie Utd', 'airdrie': 'Airdrie Utd', 'queen of the south': 'Queen of Sth',
            "queen's park": 'Queens Park', 'greenock morton': 'Morton', 'partick thistle': 'Partick', 'dunfermline athletic': 'Dunfermline',
            'ayr united': 'Ayr', 'hamilton academical': 'Hamilton', 'alloa athletic': 'Alloa', 'forfar athletic': 'Forfar', 'elgin city': 'Elgin',
            'stirling albion': 'Stirling', 'spartans fc': 'Spartans', 'the spartans': 'Spartans', 'st. johnstone': 'St Johnstone',
            'st. mirren': 'St Mirren', 'dundee utd': 'Dundee United'},
    'ESP': {'rc celta fortuna': 'Celta B', 'celta fortuna': 'Celta B', 'celta b': 'Celta B', 'real sociedad ii': 'Sociedad B',
            'real sociedad b': 'Sociedad B', 'sanse': 'Sociedad B'},
    'GER': {'karlsruher sc': 'Karlsruhe', 'eintracht braunschweig': 'Braunschweig', 'tsv eintracht braunschweig': 'Braunschweig',
            'dynamo dresden': 'Dresden', 'sg dynamo dresden': 'Dresden', 'arminia bielefeld': 'Bielefeld', 'energie cottbus': 'Cottbus',
            'spvgg greuther fürth': 'Greuther Furth', 'greuther fürth': 'Greuther Furth', 'greuther furth': 'Greuther Furth',
            'hannover 96': 'Hannover', 'vfl osnabrück': 'Osnabruck', 'vfl osnabruck': 'Osnabruck', 'fc nürnberg': 'Nurnberg', 'nürnberg': 'Nurnberg'},
    'ITA': {'südtirol': 'Sudtirol', 'fc südtirol': 'Sudtirol', 'sudtirol': 'Sudtirol'},
    'FRA': {'dijon fco': 'Dijon', 'stade laval': 'Laval', 'rodez aveyron': 'Rodez', 'red star fc': 'Red Star', 'en avant guingamp': 'Guingamp',
            'usl dunkerque': 'Dunkerque', 'grenoble foot 38': 'Grenoble', 'as nancy lorraine': 'Nancy', 'fc sochaux-montbéliard': 'Sochaux',
            'sochaux-montbéliard': 'Sochaux', 'us boulogne': 'Boulogne'},
    'NED': {'fortuna sittard': 'For Sittard', 'nec nijmegen': 'Nijmegen', 'nec': 'Nijmegen', 'pec zwolle': 'Zwolle', 'ado den haag': 'Den Haag',
            'az alkmaar': 'AZ Alkmaar', 'az': 'AZ Alkmaar', 'psv': 'PSV Eindhoven', 'psv eindhoven': 'PSV Eindhoven', 'sc cambuur': 'Cambuur'},
    'BEL': {'oh leuven': 'Oud-Heverlee Leuven', 'oud-heverlee leuven': 'Oud-Heverlee Leuven', 'sint-truidense': 'St Truiden',
            'sint-truidense vv': 'St Truiden', 'union st.-gilloise': 'St. Gilloise', 'union saint-gilloise': 'St. Gilloise',
            'royale union saint-gilloise': 'St. Gilloise', 'zulte-waregem': 'Waregem', 'sv zulte waregem': 'Waregem', 'standard liege': 'Standard',
            'standard liège': 'Standard', 'royal antwerp': 'Antwerp', 'waasland-beveren': 'Beveren', 'sk beveren': 'Beveren',
            'raal la louvière': 'RAAL La Louviere', 'raal la louviere': 'RAAL La Louviere', 'la louvière': 'RAAL La Louviere', 'lommel': 'Lommel SK'},
    'POR': {'sporting cp': 'Sp Lisbon', 'sporting lisbon': 'Sp Lisbon', 'sporting': 'Sp Lisbon', 'braga': 'Sp Braga', 'sc braga': 'Sp Braga',
            'sporting braga': 'Sp Braga', 'vitória de guimaraes': 'Guimaraes', 'vitória de guimarães': 'Guimaraes', 'vitoria guimaraes': 'Guimaraes',
            'c.d. nacional': 'Nacional', 'cd nacional': 'Nacional', 'académico de viseu': 'Academico Viseu', 'academico de viseu': 'Academico Viseu',
            'estrela da amadora': 'Estrela', 'estoril praia': 'Estoril'},
    'ARG': {'independiente rivadavia': 'Ind. Rivadavia', 'argentinos juniors': 'Argentinos Jrs', 'estudiantes de la plata': 'Estudiantes L.P.',
            'gimnasia la plata': 'Gimnasia L.P.', 'atlético tucumán': 'Atl. Tucuman', 'deportivo riestra': 'Dep. Riestra'},
    'DNK': {'agf': 'Aarhus', 'agf aarhus': 'Aarhus', 'brøndby if': 'Brondby', 'brøndby': 'Brondby', 'f.c. københavn': 'FC Copenhagen',
            'fc københavn': 'FC Copenhagen', 'fc copenhagen': 'FC Copenhagen', 'sønderjyske fodbold': 'Sonderjyske', 'sønderjyske': 'Sonderjyske',
            'fc nordsjælland': 'Nordsjaelland'},
    'JPN': {'urawa red diamonds': 'Urawa Reds'},
    'NOR': {'hamarkameratene': 'HamKam'},
    'ROU': {'universitatea cluj': 'U. Cluj', 'csu craiova': 'Univ. Craiova', 'universitatea craiova': 'Univ. Craiova', 'sepsi osk': 'Sepsi Sf. Gheorghe'},
    'MEX': {'atlético de san luis': 'Atl. San Luis', 'atletico de san luis': 'Atl. San Luis'},
    'SWE': {'halmstads bk': 'Halmstad'},
    'RUS': {'akron tolyatti': 'Akron Togliatti'},
    'USA': {'la galaxy': 'Los Angeles Galaxy', 'los angeles galaxy': 'Los Angeles Galaxy', 'lafc': 'Los Angeles FC', 'los angeles fc': 'Los Angeles FC',
            'red bull new york': 'New York Red Bulls', 'new york red bulls': 'New York Red Bulls', 'atlanta united fc': 'Atlanta Utd',
            'atlanta united': 'Atlanta Utd'},
    'GRE': {'olympiacos': 'Olympiakos', 'olympiacos fc': 'Olympiakos', 'aek athens': 'AEK', 'ofi': 'OFI Crete', 'levadiakos': 'Levadeiakos',
            'volos': 'Volos NFC', 'asteras tripoli': 'Asteras Tripolis', 'aris thessaloniki': 'Aris', 'paok salonika': 'PAOK'},
}
for _g, _m in MORE.items():
    ALIASES.setdefault(_g, {}).update(_m)


def aliases_for(div):
    return ALIASES.get(GROUP.get(div, div), {})


DROP = {'fc', 'cf', 'sc', 'ac', 'as', 'afc', 'sk', 'jk', 'fk', 'ssc', 'us', 'rc', 'rcd', 'ca', 'cd', 'ud', 'sd', 'sv', 'tsg', 'vfb', 'vfl',
        'fsv', 'bv', 'bsc', 'club', 'de', 'calcio', 'ogc', 'losc', 'estac', 'aj', 'sco', 'hsc', 'osc', 'the', 'and', 'a', 's', 'k', 'spor'}


def _fold(s):
    s = s.replace('ı', 'i').replace('İ', 'i').replace('&', ' and ')
    s = unicodedata.normalize('NFKD', s)
    return ''.join(ch for ch in s if not unicodedata.combining(ch)).lower()


def norm(s):
    toks = [t for t in re.split(r"[^a-z0-9]+", _fold(s)) if t]
    toks = [t for t in toks if t not in DROP and not re.fullmatch(r'\d{1,4}', t)]
    return ' '.join(toks)


def _score(ext, can):
    a, b = norm(ext), norm(can)
    if not a or not b:
        return 0.0
    if a == b:
        return 0.98
    ta, tb = set(a.split()), set(b.split())
    if ta <= tb or tb <= ta:
        return 0.9
    r = SequenceMatcher(None, a, b).ratio()
    j = len(ta & tb) / len(ta | tb)
    return max(r, 0.5 + 0.4 * j if j > 0 else 0)


def build_map(div, external, canonical, threshold=0.74):
    """external: {ext_id: [name variants]} ; canonical: list of football-data names.
    Returns ({ext_id: canonical}, [unresolved ext_id], {ext_id: score})."""
    al = aliases_for(div)
    can = list(canonical)
    cands = []
    for eid, variants in external.items():
        best = {}
        for v in variants:
            if not v:
                continue
            k = _fold(v).strip()
            hit = al.get(k) or al.get(v.lower().strip())
            if hit in can:
                best[hit] = 1.0
                continue
            for c in can:
                s = _score(v, c)
                if s > best.get(c, 0):
                    best[c] = s
        for c, s in best.items():
            cands.append((s, eid, c))
    cands.sort(key=lambda x: (-x[0], str(x[1]), x[2]))
    out, used, score = {}, set(), {}
    for s, eid, c in cands:
        if s < threshold or eid in out or c in used:
            continue
        out[eid] = c; used.add(c); score[eid] = round(s, 3)
    return out, [e for e in external if e not in out], score
