import json, sys, os
# Regenera entradas/festivos_flota.json:  python3 automatizacion/festivos_flota_datos.py automatizacion/entradas/festivos_flota.json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); import festivos_config as fc
CCAA = {"Alicante": "Comunitat Valenciana", "Valencia": "Comunitat Valenciana", "Granada": "Andalucía", "Madrid": "Comunidad de Madrid"}
Z = {  # % de entregas por municipio (puntos de entrega 22–29/10/2026, pp_heat.json) · provincia
 "ALC": ("Alicante", "Alicante", [("Alacant", 89.7), ("Sant Vicent del Raspeig", 4.9), ("Sant Joan d'Alacant", 1.7), ("Mutxamel", 1.5), ("El Campello", 1.5)]),
 "GRA": ("Granada", "Granada", [("Granada", 71.6), ("Churriana de la Vega", 8.1), ("Armilla", 5.2), ("Las Gabias", 2.8), ("La Zubia", 2.4), ("Maracena", 2.4),
         ("Ogíjares", 2.4), ("Gójar", 1.4), ("Monachil", 1.4), ("Huétor Vega", 1.4), ("Pulianas", 0.5), ("Alhendín", 0.5)]),
 "MAD": ("Madrid norte · Alcobendas · S.S. Reyes", "Madrid", [("Madrid", 43.0), ("San Sebastián de los Reyes", 35.0), ("Alcobendas", 21.9)]),
 "NOM": ("Madrid noroeste", "Madrid", [("Las Rozas de Madrid", 25.5), ("Pozuelo de Alarcón", 22.5), ("Madrid", 17.3), ("Boadilla del Monte", 14.4), ("Majadahonda", 13.1),
         ("Torrelodones", 4.2), ("Villaviciosa de Odón", 1.3), ("Alcorcón", 0.7), ("Galapagar", 0.3), ("Leganés", 0.3), ("Collado Villalba", 0.3)]),
 "SAB": ("Camp de Túria · San Antonio de Benagéber", "Valencia", [("La Pobla de Vallbona", 36.2), ("L'Eliana", 17.8), ("Bétera", 15.5), ("Llíria", 10.9),
         ("San Antonio de Benagéber", 8.0), ("Paterna", 4.6), ("Benaguasil", 3.4), ("València", 1.7), ("Riba-roja de Túria", 1.1), ("Benissanó", 0.6)]),
}
L26 = dict(fc.L26)
L26.update({
 "Sant Vicent del Raspeig": [("04-13", "Fiestas patronales"), ("04-14", "Moros y Cristianos")],
 "Sant Joan d'Alacant": [("06-23", "Fiesta local"), ("09-14", "Fiesta local")],
 "Mutxamel": [("08-06", "El Salvador"), ("09-09", "Mare de Déu del Loreto")],
 "El Campello": [("07-16", "Virgen del Carmen"), ("10-15", "Santa Teresa de Jesús")],
 "Bétera": [("03-20", "Santa Alejandra"), ("04-13", "San Vicente Ferrer")],
 "San Antonio de Benagéber": [("04-08", "Fiesta de la Segregación"), ("05-15", "San Isidro")],
 "Paterna": [("04-13", "San Vicente Ferrer"), ("08-31", "Santísimo Cristo de la Fe")],
 "Benaguasil": [("03-18", "Fallas"), ("09-08", "Virgen de Montiel")],
 "Riba-roja de Túria": [("04-13", "San Vicente Ferrer"), ("09-14", "Festividad del Cristo")],
 "Benissanó": [("09-08", "Virgen del Fundamento"), ("09-09", "Nuestra Señora de los Dolores")],
 "Churriana de la Vega": [("02-12", "Fiesta local"), ("09-08", "Fiesta local")],
 "Las Gabias": [("05-04", "Fiesta local"), ("08-05", "Fiesta local")],
 "La Zubia": [("05-16", "Fiesta local"), ("06-04", "Corpus Christi")],
 "Maracena": [("03-27", "Fiesta local"), ("08-14", "Fiesta local")],
 "Ogíjares": [("06-04", "Corpus Christi"), ("09-14", "Fiesta local")],
 "Gójar": [("06-04", "Corpus Christi"), ("08-31", "Fiesta local")],
 "Monachil": [("01-19", "Fiesta local"), ("03-23", "Fiesta local")],
 "Pulianas": [("02-12", "Fiesta local"), ("06-04", "Corpus Christi")],
 "Alcobendas": [("01-24", "Fiesta local"), ("05-15", "San Isidro")],
 "San Sebastián de los Reyes": [("01-20", "San Sebastián"), ("08-28", "Fiestas patronales")],
 "Las Rozas de Madrid": [("05-04", "Fiesta local"), ("09-29", "San Miguel")],
 "Pozuelo de Alarcón": [("07-16", "Virgen del Carmen"), ("09-07", "Fiestas patronales")],
 "Boadilla del Monte": [("06-01", "Fiesta local"), ("10-05", "Fiestas patronales")],
 "Majadahonda": [("09-14", "Fiestas patronales"), ("11-25", "Fiesta local")],
 "Torrelodones": [("07-16", "Virgen del Carmen"), ("08-14", "Fiestas patronales")],
 "Villaviciosa de Odón": [("01-20", "San Sebastián"), ("09-21", "Fiestas patronales")],
 "Alcorcón": [("04-06", "Fiesta local"), ("09-08", "Fiestas patronales")],
 "Galapagar": [("05-15", "San Isidro"), ("09-14", "Fiestas patronales")],
 "Leganés": [("08-14", "Fiestas patronales"), ("10-09", "Fiesta local")],
 "Collado Villalba": [("06-12", "Fiesta local"), ("07-24", "Fiestas patronales")],
})
munis = {m for _, _, ms in Z.values() for m, _ in ms}
falta = [m for m in munis if m not in L26]; assert not falta, falta
hol = []
nat = {d for y in fc.NACIONAL.values() for d in y}
used = {CCAA[p] for _, p, _ in Z.values()}
for ccaa in used:
    for d, n in fc.REG[ccaa].items():
        hol.append([d, "Nacional" if d in nat else "Autonómico", n, ccaa])
for m in sorted(munis):
    for md, n in L26[m]: hol.append([f"2026-{md}", "Local", n, m])
    for md, n in fc.L27.get(m, []): hol.append([f"2027-{md}", "Local", n, m])
hol.sort()
mg = {}
for d, t, n, terr in hol:
    k = (d, n.split(' (')[0] if t != 'Local' else n, t if t == 'Local' else 'X')
    e = mg.setdefault(k, [d, t, n, []]); e[3].append(terr)
    if t == 'Nacional': e[1] = 'Nacional'
hol = sorted(mg.values())
cfg = dict(
  fuentes=fc.FUENTES[:3] + ["Locales 2026 Comunidad de Madrid: Resolución 2/12/2025 DG Trabajo (BOCM 12/12/2025)",
           "Municipios por zona: puntos de entrega pp_heat.json (22–29/10/2026) × límites municipales INE (es-atlas)"],
  nota="No hay festivos laborales provinciales ni comarcales en estas comunidades. Añadir los locales de 2027 cuando se publiquen.",
  dashboards={"sab": ["SAB"], "gra-mad-nom-alc": ["ALC", "GRA", "MAD", "NOM"]},
  zonas={z: dict(nombre=n, provincia=p, muni=[[m, s, CCAA[p]] for m, s in ms]) for z, (n, p, ms) in Z.items()},
  hol=hol)
json.dump(cfg, open(sys.argv[1], "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(len(hol), "festivos ·", len(munis), "municipios")
