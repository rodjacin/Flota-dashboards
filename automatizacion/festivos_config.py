# -*- coding: utf-8 -*-
"""Genera festivos.json (configuración editable de la pestaña Festivos y del aviso emergente).

Ámbitos (no existen festivos laborales «comarcales» en Andalucía, Cataluña, C. Valenciana ni Madrid:
las fiestas locales las fija cada municipio, aunque en Cataluña se publican agrupadas por comarca).
"""
import json, sys

FUENTES = [
    "Nacional/autonómico 2026: BOE Resolución 17/10/2025 · Decreto 101/2025 Junta de Andalucía · Decreto 100/2025 Consell (DOGV 07/07/2025) · Ordre EMT/66/2025 (DOGC) · Comunidad de Madrid (BOCM 25/09/2025)",
    "Nacional/autonómico 2027: BOE Resolución 08/10/2026 (BOE 13/10/2026) · Decreto 84/2026 Junta de Andalucía · Decreto Consell 2027 · Ordre EMT/52/2026 (DOGC) · Decreto 82/2026 Comunidad de Madrid",
    "Locales 2026: BOJA 197 de 14/10/2025 (+ modificaciones) · DOGV Resolución 12/11/2025 · Ordre EMT/208/2025 (DOGC 17/12/2025) y EMT/3/2026 · Ayuntamiento de Madrid (Pleno 30/09/2025)",
    "Locales 2027: Madrid (Pleno 29/09/2026) · València (propuesta de la Comisión, pendiente de Pleno) · Málaga (Pleno 28/05/2026). El resto se publica entre octubre y diciembre de 2026: añadirlos aquí.",
]

# ---------------- Autonómico + nacional (lista completa de cada CCAA) ----------------
N = {  # nombres
    "01-01": "Año Nuevo", "01-06": "Epifanía del Señor", "05-01": "Fiesta del Trabajo", "08-15": "Asunción de la Virgen",
    "10-12": "Fiesta Nacional de España", "11-01": "Todos los Santos", "12-06": "Día de la Constitución",
    "12-08": "Inmaculada Concepción", "12-25": "Navidad",
}
NACIONAL = {
    2026: ["2026-01-01", "2026-01-06", "2026-04-03", "2026-05-01", "2026-08-15", "2026-10-12", "2026-12-08", "2026-12-25"],
    2027: ["2027-01-01", "2027-01-06", "2027-03-26", "2027-05-01", "2027-10-12", "2027-11-01", "2027-12-06", "2027-12-08", "2027-12-25"],
}
REG = {
    "Andalucía": {
        "2026-01-01": "Año Nuevo", "2026-01-06": "Epifanía del Señor", "2026-02-28": "Día de Andalucía",
        "2026-04-02": "Jueves Santo", "2026-04-03": "Viernes Santo", "2026-05-01": "Fiesta del Trabajo",
        "2026-08-15": "Asunción de la Virgen", "2026-10-12": "Fiesta Nacional de España",
        "2026-11-02": "Todos los Santos (traslado del domingo 1/11)", "2026-12-07": "Día de la Constitución (traslado del domingo 6/12)",
        "2026-12-08": "Inmaculada Concepción", "2026-12-25": "Navidad",
        "2027-01-01": "Año Nuevo", "2027-01-06": "Epifanía del Señor", "2027-03-01": "Día de Andalucía (traslado del domingo 28/2)",
        "2027-03-25": "Jueves Santo", "2027-03-26": "Viernes Santo", "2027-05-01": "Fiesta del Trabajo",
        "2027-08-16": "Asunción de la Virgen (traslado del domingo 15/8)", "2027-10-12": "Fiesta Nacional de España",
        "2027-11-01": "Todos los Santos", "2027-12-06": "Día de la Constitución", "2027-12-08": "Inmaculada Concepción",
        "2027-12-25": "Navidad"},
    "Comunidad de Madrid": {
        "2026-01-01": "Año Nuevo", "2026-01-06": "Epifanía del Señor", "2026-04-02": "Jueves Santo",
        "2026-04-03": "Viernes Santo", "2026-05-01": "Fiesta del Trabajo", "2026-05-02": "Fiesta de la Comunidad de Madrid",
        "2026-08-15": "Asunción de la Virgen", "2026-10-12": "Fiesta Nacional de España",
        "2026-11-02": "Todos los Santos (traslado del domingo 1/11)", "2026-12-07": "Día de la Constitución (traslado del domingo 6/12)",
        "2026-12-08": "Inmaculada Concepción", "2026-12-25": "Navidad",
        "2027-01-01": "Año Nuevo", "2027-01-06": "Epifanía del Señor", "2027-03-19": "San José",
        "2027-03-25": "Jueves Santo", "2027-03-26": "Viernes Santo", "2027-05-01": "Fiesta del Trabajo",
        "2027-08-16": "Asunción de la Virgen (traslado del domingo 15/8)", "2027-10-12": "Fiesta Nacional de España",
        "2027-11-01": "Todos los Santos", "2027-12-06": "Día de la Constitución", "2027-12-08": "Inmaculada Concepción",
        "2027-12-25": "Navidad"},
    "Comunitat Valenciana": {
        "2026-01-01": "Año Nuevo", "2026-01-06": "Epifanía del Señor", "2026-03-19": "San José",
        "2026-04-03": "Viernes Santo", "2026-04-06": "Lunes de Pascua", "2026-05-01": "Fiesta del Trabajo",
        "2026-06-24": "San Juan", "2026-08-15": "Asunción de la Virgen", "2026-10-09": "Día de la Comunitat Valenciana",
        "2026-10-12": "Fiesta Nacional de España", "2026-12-08": "Inmaculada Concepción", "2026-12-25": "Navidad",
        "2027-01-01": "Año Nuevo", "2027-01-06": "Epifanía del Señor", "2027-03-19": "San José",
        "2027-03-26": "Viernes Santo", "2027-03-29": "Lunes de Pascua", "2027-05-01": "Fiesta del Trabajo",
        "2027-10-09": "Día de la Comunitat Valenciana", "2027-10-12": "Fiesta Nacional de España",
        "2027-11-01": "Todos los Santos", "2027-12-06": "Día de la Constitución", "2027-12-08": "Inmaculada Concepción",
        "2027-12-25": "Navidad"},
    "Cataluña": {
        "2026-01-01": "Cap d'Any", "2026-01-06": "Reis", "2026-04-03": "Divendres Sant", "2026-04-06": "Dilluns de Pasqua Florida",
        "2026-05-01": "Festa del Treball", "2026-06-24": "Sant Joan", "2026-08-15": "L'Assumpció",
        "2026-09-11": "Diada Nacional de Catalunya", "2026-10-12": "Festa Nacional d'Espanya",
        "2026-12-08": "La Immaculada", "2026-12-25": "Nadal", "2026-12-26": "Sant Esteve",
        "2027-01-01": "Cap d'Any", "2027-01-06": "Reis", "2027-03-26": "Divendres Sant", "2027-03-29": "Dilluns de Pasqua Florida",
        "2027-05-01": "Festa del Treball", "2027-06-24": "Sant Joan", "2027-09-11": "Diada Nacional de Catalunya",
        "2027-10-12": "Festa Nacional d'Espanya", "2027-11-01": "Tots Sants", "2027-12-06": "Dia de la Constitució",
        "2027-12-08": "La Immaculada", "2027-12-25": "Nadal"},
}

# ---------------- Locales (2 por municipio) ----------------
L26 = {
    # Comunitat Valenciana · provincia de Valencia
    "València": [("01-22", "San Vicente Mártir"), ("04-13", "San Vicente Ferrer")],
    "Alfafar": [("04-13", "San Vicente Ferrer"), ("09-08", "Nuestra Señora del Don")],
    "Massalfassar": [("04-13", "San Vicente Ferrer"), ("08-10", "San Lorenzo")],
    "Sagunt": [("04-13", "San Vicente Ferrer"), ("07-30", "Santos Abdón y Senén")],
    "L'Eliana": [("07-16", "Fiestas patronales"), ("07-17", "Fiestas patronales")],
    "La Pobla de Vallbona": [("01-20", "San Sebastián"), ("10-07", "Virgen del Rosario")],
    "Alboraia": [("04-13", "San Vicente Ferrer"), ("07-10", "San Cristóbal")],
    "Alaquàs": [("09-08", "Virgen del Olivar"), ("09-09", "Cristo de la Buena Muerte")],
    "Alfara del Patriarca": [("04-13", "San Vicente Ferrer"), ("08-24", "San Bartolomé")],
    "Llíria": [("04-13", "San Vicente Ferrer"), ("09-29", "San Miguel Arcángel")],
    "Puçol": [("04-13", "San Vicente Ferrer"), ("09-08", "Patrona de Puçol")],
    "Picassent": [("07-10", "San Cristóbal"), ("09-08", "Virgen de Vallivana")],
    "Ontinyent": [("08-24", "Moros y Cristianos"), ("11-16", "Lunes de Feria")],
    # Comunitat Valenciana · provincia de Alicante
    "Calp": [("08-05", "Madre de Dios de las Nieves"), ("10-22", "Santísimo Cristo del Sudor")],
    "Alacant": [("04-16", "Santa Faz"), ("06-23", "Fogueres de Sant Joan")],
    "Petrer": [("05-18", "Moros y Cristianos"), ("10-07", "Virgen del Remedio")],
    "Dénia": [("04-13", "San Vicente"), ("07-08", "Santísima Sangre")],
    "La Vila Joiosa": [("07-29", "Santa Marta"), ("09-29", "San Miguel")],
    "Novelda": [("04-13", "Segundo Lunes de Pascua"), ("07-22", "Santa María Magdalena")],
    "L'Alfàs del Pi": [("11-09", "Fiestas patronales"), ("11-10", "Fiestas patronales")],
    "Benidorm": [("11-09", "Fiestas patronales"), ("11-10", "Fiestas patronales")],
    "Finestrat": [("08-21", "Fiestas patronales"), ("08-24", "Fiestas patronales")],
    "Santa Pola": [("07-16", "Virgen del Carmen"), ("09-08", "Virgen de Loreto")],
    "Ondara": [("04-13", "San Vicente"), ("07-13", "Virgen de la Soledad")],
    "Alcoi": [("04-25", "Moros y Cristianos"), ("04-27", "Moros y Cristianos")],
    "Elda": [("09-08", "Fiestas patronales"), ("09-09", "Fiestas patronales")],
    "La Nucia": [("04-13", "San Vicente"), ("08-17", "Fiestas de agosto")],
    "Rojales": [("06-29", "San Pedro Apóstol"), ("10-07", "Virgen del Rosario")],
    "Crevillent": [("04-02", "Jueves Santo"), ("10-05", "Fiestas patronales")],
    "Ibi": [("09-11", "Fiestas patronales"), ("09-14", "Fiestas patronales")],
    "San Fulgencio": [("01-16", "San Fulgencio"), ("10-08", "Virgen del Remedio")],
    "Villena": [("04-13", "San Vicente"), ("09-10", "Fiestas patronales")],
    # Comunidad de Madrid
    "Madrid": [("05-15", "San Isidro Labrador"), ("11-09", "Nuestra Señora de la Almudena")],
    # Cataluña
    "Barcelona": [("05-25", "Segona Pasqua"), ("09-24", "La Mercè")],
    "Badalona": [("05-11", "Sant Anastasi"), ("05-25", "Segona Pasqua")],
    "Santa Coloma de Gramenet": [("05-25", "Segona Pasqua"), ("09-24", "La Mercè")],
    "Premià de Mar": [("02-16", "Festa local"), ("07-10", "Sant Cristòfol")],
    "Cabrera de Mar": [("05-25", "Segona Pasqua"), ("08-01", "Festa Major")],
    "Girona": [("07-25", "Sant Jaume"), ("10-29", "Sant Narcís")],
    "Figueres": [("05-25", "Segona Pasqua"), ("06-29", "Sant Pere")],
    "Blanes": [("04-07", "Festa local"), ("08-21", "Festa local")],
    "Lloret de Mar": [("07-24", "Santa Cristina"), ("11-18", "Festa local")],
    # Andalucía
    "Sevilla": [("04-22", "Feria de Abril"), ("06-04", "Corpus Christi")],
    "Dos Hermanas": [("05-07", "Romería de Valme"), ("10-19", "Romería de Valme")],
    "Alcalá de Guadaíra": [("06-05", "Fiesta local"), ("09-21", "Fiesta local")],
    "Mairena del Aljarafe": [("01-23", "Fiesta local"), ("06-26", "Fiesta local")],
    "Écija": [("09-08", "Virgen del Valle"), ("09-18", "Feria")],
    "Bormujos": [("05-20", "Fiesta local"), ("08-28", "Fiesta local")],
    "Carmona": [("05-15", "Fiesta local"), ("09-08", "Fiesta local")],
    "Castilleja de la Cuesta": [("04-06", "Fiesta local"), ("09-18", "Fiesta local")],
    "La Rinconada": [("03-19", "San José"), ("09-15", "Fiesta local")],
    "San Juan de Aznalfarache": [("06-04", "Corpus Christi"), ("06-24", "San Juan")],
    "Mairena del Alcor": [("04-20", "Fiesta local"), ("09-08", "Fiesta local")],
    "Gines": [("05-20", "Fiesta local"), ("06-04", "Corpus Christi")],
    "Sanlúcar la Mayor": [("05-08", "Fiesta local"), ("06-04", "Corpus Christi")],
    "Pilas": [("04-06", "Fiesta local"), ("06-29", "Fiesta local")],
    "Marbella": [("06-11", "San Bernabé"), ("10-19", "Virgen del Rosario")],
    "Málaga": [("08-19", "Incorporación a la Corona de Castilla"), ("09-08", "Virgen de la Victoria")],
    "Estepona": [("05-15", "San Isidro"), ("07-16", "Virgen del Carmen")],
    "Alhaurín de la Torre": [("01-20", "San Sebastián"), ("06-24", "San Juan")],
    "Granada": [("01-02", "Día de la Toma"), ("06-04", "Corpus Christi")],
    "Motril": [("05-04", "Fiesta local"), ("06-24", "San Juan")],
    "Armilla": [("05-15", "San Isidro"), ("09-29", "San Miguel")],
    "Vegas del Genil": [("04-24", "Fiesta local"), ("10-02", "Fiesta local")],
    "Alhendín": [("06-04", "Corpus Christi"), ("08-24", "Fiesta local")],
    "Huétor Vega": [("06-04", "Corpus Christi"), ("06-05", "Fiesta local")],
    "Almería": [("06-24", "San Juan"), ("08-29", "Feria")],
    "El Ejido": [("04-27", "Fiesta local"), ("06-29", "Fiesta local")],
    "Vícar": [("06-22", "Fiesta local"), ("09-21", "Fiesta local")],
    "La Mojonera": [("06-29", "Fiesta local"), ("09-14", "Fiesta local")],
    "El Puerto de Santa María": [("05-04", "Fiesta local"), ("09-08", "Virgen de los Milagros")],
    "La Línea de la Concepción": [("07-20", "Feria"), ("07-27", "Fiesta local")],
    "Los Barrios": [("05-15", "San Isidro"), ("07-16", "Virgen del Carmen")],
}
L27 = {
    "Madrid": [("05-15", "San Isidro Labrador"), ("11-09", "Nuestra Señora de la Almudena")],
    "València": [("01-22", "San Vicente Mártir"), ("04-05", "San Vicente Ferrer (pendiente de Pleno)")],
    "Málaga": [("08-19", "Incorporación a la Corona de Castilla"), ("09-08", "Virgen de la Victoria")],
}

# ---------------- Municipio → provincia, CCAA ----------------
def _m(prov, ccaa, *ms): return {m: [prov, ccaa] for m in ms}
MUNI = {}
MUNI.update(_m("Valencia", "Comunitat Valenciana", "València", "Alfafar", "Massalfassar", "Sagunt", "L'Eliana", "La Pobla de Vallbona",
               "Alboraia", "Alaquàs", "Alfara del Patriarca", "Llíria", "Puçol", "Picassent", "Ontinyent"))
MUNI.update(_m("Alicante", "Comunitat Valenciana", "Calp", "Alacant", "Petrer", "Dénia", "La Vila Joiosa", "Novelda", "L'Alfàs del Pi",
               "Benidorm", "Finestrat", "Santa Pola", "Ondara", "Alcoi", "Elda", "La Nucia", "Rojales", "Crevillent", "Ibi",
               "San Fulgencio", "Villena"))
MUNI.update(_m("Madrid", "Comunidad de Madrid", "Madrid"))
MUNI.update(_m("Barcelona", "Cataluña", "Barcelona", "Badalona", "Santa Coloma de Gramenet", "Premià de Mar", "Cabrera de Mar"))
MUNI.update(_m("Girona", "Cataluña", "Girona", "Figueres", "Blanes", "Lloret de Mar"))
MUNI.update(_m("Sevilla", "Andalucía", "Sevilla", "Dos Hermanas", "Alcalá de Guadaíra", "Mairena del Aljarafe", "Écija", "Bormujos",
               "Carmona", "Castilleja de la Cuesta", "La Rinconada", "San Juan de Aznalfarache", "Mairena del Alcor", "Gines",
               "Sanlúcar la Mayor", "Pilas"))
MUNI.update(_m("Málaga", "Andalucía", "Marbella", "Málaga", "Estepona", "Alhaurín de la Torre"))
MUNI.update(_m("Granada", "Andalucía", "Granada", "Motril", "Armilla", "Vegas del Genil", "Alhendín", "Huétor Vega"))
MUNI.update(_m("Almería", "Andalucía", "Almería", "El Ejido", "Vícar", "La Mojonera"))
MUNI.update(_m("Cádiz", "Andalucía", "El Puerto de Santa María", "La Línea de la Concepción", "Los Barrios"))

# ciudad del fichero de puntos → municipio canónico
ALIAS = {"Valencia": "València", "Sagunto/Sagunt": "Sagunt", "Alboraia/Alboraya": "Alboraia", "Alicante/Alacant": "Alacant",
         "Alicante": "Alacant", "Villajoyosa/Vila Joiosa, la": "La Vila Joiosa", "Alfàs del Pi, l'": "L'Alfàs del Pi",
         "Ejido, El": "El Ejido", "Puerto de Santa María, El": "El Puerto de Santa María", "Rinconada, La": "La Rinconada",
         "Barrios, Los": "Los Barrios", "Pobla de Vallbona, la": "La Pobla de Vallbona", "La Eliana": "L'Eliana",
         "Alcoy/Alcoi": "Alcoi", "Nucia, la": "La Nucia", "la Nucia": "La Nucia", "Calp": "Calp", "Dénia": "Dénia",
         "Santa Margarita": "La Línea de la Concepción", "Puçol": "Puçol", "Llíria": "Llíria", "Ontinyent": "Ontinyent"}
# restaurantes con la ciudad mal o vacía en el fichero de puntos
REST = {"99910": "València", "15695": "Madrid", "15697": "La Nucia", "16083": "Marbella", "16315": "Calp", "16386": "Sevilla",
        "16387": "Almería", "16404": "València", "16452": "Granada", "16513": "Lloret de Mar", "15876": "Écija", "15878": "Granada",
        "33322": "La Mojonera", "33381": "Marbella", "99912": "Barcelona", "99953": "Madrid", "99964": "Madrid",
        "99965": "València", "99976": "Benidorm", "99980": "Sevilla", "20264": "Estepona", "29108": "La Línea de la Concepción"}


def build():
    hol = []
    nat = {d for y in NACIONAL.values() for d in y}
    by_date = {}
    for ccaa, dd in REG.items():
        for d, n in dd.items():
            by_date.setdefault(d, {})[ccaa] = n
    for d, cc in sorted(by_date.items()):
        tipo = "Nacional" if d in nat else "Autonómico"
        if len(cc) == len(REG):
            hol.append([d, tipo, cc.get("Andalucía") or cc.get("Comunidad de Madrid") or next(iter(cc.values())), "ES"])
        else:
            for c, n in cc.items():
                hol.append([d, tipo, n, c])
    for year, L in ((2026, L26), (2027, L27)):
        for muni, ds in L.items():
            assert muni in MUNI, muni
            for md, n in ds:
                hol.append([f"{year}-{md}", "Local", n, muni])
    hol.sort()
    return dict(fuentes=FUENTES, hol=hol, muni=MUNI, alias=ALIAS, rest=REST,
                locales_disponibles={"2026": sorted(L26), "2027": sorted(L27)},
                nota="No hay festivos laborales comarcales en estas comunidades: las fiestas locales son por municipio.")


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "festivos.json"
    json.dump(build(), open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("ok", out)
