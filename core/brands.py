# -*- coding: utf-8 -*-
"""PRO-режим: дефолтные списки брендов сельхоз/спецтехники по странам."""

from typing import Dict, List

DEFAULT_COUNTRY_BRANDS: Dict[str, List[str]] = {
    "Россия": [
        "gaz", "kamaz", "maz", "zil", "ural", "kraz", "uaz", "paz", "liaz", "kavz",
        "mtz", "belarus", "kirovets", "ptz", "k700", "k701", "k744", "k525", "k7",
        "htz", "t150", "dt75", "vtz", "umz", "t40", "t25", "t16", "chtz",
        "agromash", "terrion", "amkodor", "rostselmash", "rsm", "acros", "torum",
        "vector", "nova", "don", "sk5", "yenisei", "gomselmash", "palesse",
        "nefaz", "szap", "tonar", "pts", "2pts", "pim", "prt", "pku", "bdm",
        "veles", "bobruisk", "lidselmash", "voronezh", "belama", "arzamas", "oztp",
        "salskselmash", "chervona", "kuban", "moroz", "rubarz", "fmz", "orkanz",
        "rs", "fortia", "cheboксары", "promtraktor", "altrem", "grunwald",
    ],
    "СССР": [
        "zil-130", "zil130", "zil-131", "zil131", "zil-157", "gaz-52", "gaz-53",
        "gaz53", "gaz-66", "gaz66", "gaz-51", "gaz-69", "uaz-469", "uaz469",
        "uaz-452", "mtz-50", "mtz50", "mtz-80", "mtz80", "mtz-82", "umz-6", "umz6",
        "dt-75", "dt75", "t-40", "t40", "t-25", "t25", "t-16", "t16", "t-150k",
        "k-700", "k700", "k-701", "k701", "sk-5", "sk5", "don-1500", "don1500",
        "kraz-255", "kraz255", "kraz-256", "maz-500", "maz-501", "kamaz-5320",
        "kamaz-5410", "2pts-4", "pts-4", "dzn-1", "ekipazhirovka", "sssr", "soviet",
    ],
    "Беларусь": [
        "mtz", "belarus", "gomselmash", "palesse", "amkodor", "belaz", "mzkt",
        "volat", "bobruisk", "lidselmash", "uniso", "belaruskali",
    ],
    "Украина": ["htz", "kraz", "laz", "bogdan", "massey ferguson", "khzt", "druzhba"],
    "Казахстан": ["kaztraktor", "eastkart", "eurasia"],
    "Германия": [
        "claas", "fendt", "deutz", "deutz-fahr", "deutzfahr", "man", "mercedes",
        "mercedes-benz", "mb-trac", "krone", "grimme", "ropa", "holmer", "lemken",
        "amazone", "huard", "bauer", "gsw", "rabe", "schuitemaker", "vredo",
        "unia", "rabe", "ostermann", "horst", "prexa", "hurlimann", "weidemann",
        "wacker", "bomag", "liebherr", "zeppelin", "sennebogen", "atlas",
        "lindner", "jcb", "kramer", "case", "case ih", "new holland",
    ],
    "США": [
        "johndeere", "john deere", "deere", "case", "case ih", "international",
        "intl", "ih", "new holland", "nh", "kubota us", "cat", "caterpillar",
        "mack", "peterbilt", "kenworth", "freightliner", "western star",
        "allischalmers", "lida", "jD", "versatile", "artemisse", "row-crop",
        "kinze", "planting", "sunflower", "cotton picker", "john deere",
        "chevrolet", "ford", "gm", "gmc", "jeep", "canam", "polaris", "bobcat",
        "jlg", "genie", "skyjack", "terex", "moffett", "alkin", "elgin",
    ],
    "Франция": [
        "manitou", "mrt", "mlt", "renault", "renault agriculture", "peugeot",
        "citroen", "amazone fr", "kuhn", "sauton", "stiga", "rupes", "derome",
        "pellen", "carraro", "levy", "berthoud", "mathieu", "fradin", "charlock",
        "pottinger fr", "grimme fr", "maschio", "same fr",
    ],
    "Италия": [
        "laverda", "goldoni", "pasquali", "valpadana", "antonio carraro", "carraro",
        "landini", "new holland it", "case it", "same", "deutz it", "ferrari",
        "bcs", "cascia", "motomec", "terrenova", "secom", "gaspergo", "oroblue",
        "bema", "cavri", "zanibani", "berti", "fm", "riform", "sds", "italmet",
    ],
    "Великобритания": [
        "jcb", "massey ferguson", "mf", "marshall", "jcb fastrack", "gregory",
        "amazone uk", "brochard", "cimbria", "david brown", "alvis", "fendt uk",
    ],
    "Швеция": ["volvo", "volvo bm", "scania", "valtra", "ponsse", "rottne",
              "linder", "massey", "husqvarna", "atlascopco", "sandvik"],
    "Финляндия": ["valtra", "ponsse", "jukka", "sautocupo", "ferri", "rok"],
    "Нидерланды": ["kuhn", "vicon", "rauch", "bosman", "stiemer", "forigo",
                   "jongeneel", "lizard", "vermeer", "tromp", "nola", "payen"],
    "Дания": ["massey", "sonne", "kvindeby", "pfeifer", "case danmark"],
    "Австрия": ["steyr", "poettinger", "pottinger", "reidlinger", "linde",
                "kranabritscher", "dammann", "winkler", "grada"],
    "Швейцария": ["bucher", "stadtler", "maillard", "prona", "riri", "felco"],
    "Польша": [
        "unia", "bomet", "sipma", "metalfach", "polsrem", "rolmako", "krukowiak",
        "agrotom", "agrozet", "biardzki", "fas", "zelmer", "polam", "mesinger pl",
        "stalmet", "promet", "polmozbytom", "fabula", "marrot",
    ],
    "Чехия": ["zetor", "proterra", "brantner", "ekolift", "agrostem", "huerter",
              "porsche", "tatra", "skoda", "crown cz"],
    "Япония": [
        "kubota", "iseki", "yanmar", "toyota", "mitsubishi", "komatsu",
        "hitachi", "sumitomo", "kobelco", "doosan jp", "misubishi", "nisshinbo",
        "muramatsu", "fuda", "nishihari", "eijiri", "clark",
    ],
    "Южная Корея": ["ls", "kioti", "tym", "branson", "daedong", "hyundai",
                    "doosan", "jinseong", "aegean", "great wall kr"],
    "Китай": [
        "shacman", "shaanxi", "faw", "howo", "sinotruk", "dongfeng", "foton",
        "jac", "sitrak", "lovol", "foton lovol", "yto", "zoomlion", "xcmg",
        "liugong", "sdlg", "shantui", "chengli", "chenyu", "dongfanghong",
        "first tractor", "harbin", "wanhua", "luoluo", "xingtuo",
        "changfa", "changzhou", "shifeng", "case ih cn", "new holland cn",
    ],
    "Индия": ["mahindra", "swaraj", "sonalika", "tAFE", "escort", "farming",
              "new holland india", "john deere india", "kubota india"],
    "Турция": ["tumosan", "hars", "erkunt", "gursat", "ciftci", "asan", "bekas"],
    "Бразилия": ["massey brasil", "valtra brasil", "stara", "jactto", "brasileira"],
    "Аргентина": ["paquete", "guascarello", "ecsa", "fal", "cafi", "metalpar"],
    "Канада": ["ostero", "versatile", "big grower", "buhler", "cwms"],
    "Австралия": ["mallee", "boxer", "bate man", "howard", "sloane", "dingo"],
}


def brands_payload(country_brands: Dict[str, List[str]]) -> Dict[str, List[str]]:
    return {k: list(v) for k, v in country_brands.items()}


def merge_defaults(saved: Dict[str, List[str]]) -> Dict[str, List[str]]:
    """Дефолты для стран, которых нет в сохранённых настройках."""
    out: Dict[str, List[str]] = dict(saved or {})
    for country, brands in DEFAULT_COUNTRY_BRANDS.items():
        out.setdefault(country, list(brands))
    return out
