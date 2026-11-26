# -*- coding: utf-8 -*-
"""
MushDrink · pedidos reales del año anterior por restaurante, día y hora (para «Proyección vs mes anterior»).

Lee los Excel de pedidos de restaurante (export «Resumen pedidos»: Confirmado, Código, Fallo de Entrega…)
y acumula en mushdrink/pedidos_anio_anterior.json: {"D": {fecha: {código: {hora: pedidos}}}}.
Cuenta todos los pedidos del restaurante (todas las flotas y canales), salvo los cancelados.
Un fichero nuevo sustituye los restaurantes y fechas que trae (los demás se conservan).

Uso: python3 automatizacion/mushdrink_pedidos_2025.py fichero1.xlsx [fichero2.xlsx …]
     (después: python3 automatizacion/mushdrink_proyeccion.py)
"""
import sys, os, json, collections
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
STORE = os.path.join(HERE, "..", "mushdrink", "pedidos_anio_anterior.json")


def main():
    if len(sys.argv) < 2: sys.exit(__doc__)
    fr = []
    for f in sys.argv[1:]:
        for sh, x in pd.read_excel(f, sheet_name=None).items():
            if "Confirmado" in x.columns and "Código" in x.columns: fr.append(x)
    x = pd.concat(fr, ignore_index=True).drop_duplicates("Id")
    x = x[x["Código"].notna() & x.Confirmado.notna()]
    x = x[~x["Fallo de Entrega"].fillna("").astype(str).str.startswith("Cancelado")]
    t = pd.to_datetime(x.Confirmado)
    D = collections.defaultdict(lambda: collections.defaultdict(dict))
    for (f, c, h), n in x.groupby([t.dt.strftime("%Y-%m-%d"), x["Código"].astype(int).astype(str), t.dt.hour]).size().items():
        D[f][c][str(h)] = int(n)
    old = json.load(open(STORE, encoding="utf-8")) if os.path.exists(STORE) else {"D": {}}
    for f, v in D.items():                      # por fecha y restaurante: un fichero de BK no borra los PLK del mismo día
        old["D"].setdefault(f, {}).update(dict(v))
    old["D"] = dict(sorted(old["D"].items()))
    json.dump(old, open(STORE, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    print(f"pedidos año anterior: {len(x)} pedidos · {len(D)} fechas ({min(D)}..{max(D)}) · "
          f"{len({c for v in D.values() for c in v})} restaurantes → {os.path.relpath(STORE)}")


if __name__ == "__main__":
    main()
