# -*- coding: utf-8 -*-
"""Convierte el texto de window.__calExport() y window.__demExport() (calendario_fleet_lector.js) en
automatizacion/entradas/calendario_fleet.json (reservas y no show) y
automatizacion/entradas/Demand-forecast-fleet-DD_MM_AAAA.csv (riders y pedidos forecast), que lee la pestaña Capacidad.

    python3 calendario_fleet_json.py lectura.txt [--generado 2026-11-04T10:05:00+01:00]

· Comprueba que cada línea cuadra (suma de b+nc+ev == tot). Si alguna no cuadra, no escribe nada.
· Fusiona con el JSON existente: los días leídos ahora sustituyen a los anteriores; el resto se conserva.
· Los días con 0 reservas (semana aún sin cargar) no se guardan.
· Conserva solo las últimas 6 semanas para que el fichero no crezca sin fin.
"""
import os, re, sys, csv, glob, json, datetime as dt

DEST = os.path.join(os.path.dirname(os.path.abspath(__file__)), "entradas", "calendario_fleet.json")


def parse(txt):
    dias, malas = {}, []
    for ln in txt.splitlines():
        ln = ln.strip()
        if not ln:
            continue
        m = re.fullmatch(r"([A-Z]{3}) (\d{4}-\d{2}-\d{2}) tot=(\d+) b=([\d,]+) nc=([\d:,]*) ev=([\d:,]*)", ln)
        if not m:
            malas.append("formato: " + ln[:60]); continue
        c, d, tot, b, nc, ev = m.groups()
        b = [int(x) for x in b.split(",")]
        if len(b) != 48:
            malas.append(f"{c} {d}: b tiene {len(b)} valores"); continue
        def sp(s):
            a = [0] * 48
            for p in filter(None, s.split(",")):
                i, n = p.split(":"); a[int(i)] += int(n)
            return a
        nc, ev = sp(nc), sp(ev)
        if sum(b) + sum(nc) + sum(ev) != int(tot):
            malas.append(f"{c} {d}: suma {sum(b) + sum(nc) + sum(ev)} != tot {tot}"); continue
        if int(tot) == 0:
            continue            # día todavía sin horario cargado: no se guarda (no es capacidad 0)
        dias[c + "|" + d] = {"b": b, "nc": nc, "ev": ev}
    return dias, malas


DEM_COLS = ["city_code", "c3pl_id", "slot_id", "slot_started_local_at", "day_of_week", "time",
            "max_couriers_pilot", "available_capacity", "zone_name", "final_order_forecast"]


def parse_dem(txt):
    """Líneas «DEM CIU AAAA-MM-DD r=48 o=48 tot=N» de window.__demExport()."""
    dem, malas = {}, []
    for ln in txt.splitlines():
        ln = ln.strip()
        if not ln.startswith("DEM "):
            continue
        m = re.fullmatch(r"DEM ([A-Z]{3}) (\d{4}-\d{2}-\d{2}) r=([\d,]+) o=([\d.,]+) tot=(\d+) otot=([\d.]+)", ln)
        if not m:
            malas.append("formato DEM: " + ln[:60]); continue
        c, d, r, o, tot, otot = m.groups()
        r = [int(x) for x in r.split(",")]; o = [float(x) for x in o.split(",")]
        if len(r) != 48 or len(o) != 48:
            malas.append(f"DEM {c} {d}: no hay 48 valores"); continue
        if sum(r) != int(tot):
            malas.append(f"DEM {c} {d}: suma {sum(r)} != tot {tot}"); continue
        if abs(sum(o) - float(otot)) > 0.06:
            malas.append(f"DEM {c} {d}: pedidos {sum(o):g} != otot {otot}"); continue
        dem[(c, d)] = (r, o)
    return dem, malas


def escribir_demanda(dem):
    """Guarda la demanda de la fleet tool como entradas/Demand-forecast-fleet-DD_MM_AAAA.csv (formato que lee
    capacidad_forecast.py). Conserva los días de ficheros fleet anteriores que no se han vuelto a leer y borra esos ficheros."""
    ent = os.path.dirname(DEST)
    filas = {}
    viejos = sorted(glob.glob(os.path.join(ent, "Demand-forecast-fleet-*.csv")), key=os.path.getmtime)
    for f in viejos:
        with open(f, encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                filas[(row["city_code"], row["slot_started_local_at"][:10], row["slot_started_local_at"][11:16])] = row
    filas = {k: v for k, v in filas.items() if (k[0], k[1]) not in dem}
    for (c, d), (r, o) in dem.items():
        wd = dt.date.fromisoformat(d).strftime("%a")
        for i in range(48):
            hhmm = "%02d:%02d" % (i // 2, 30 * (i % 2))
            filas[(c, d, hhmm)] = {"city_code": c, "c3pl_id": "3393", "slot_id": "", "slot_started_local_at": f"{d} {hhmm}:00",
                                   "day_of_week": wd, "time": hhmm + ":00", "max_couriers_pilot": r[i], "available_capacity": "",
                                   "zone_name": c, "final_order_forecast": ("%g" % o[i])}
    corte = (dt.date.today() - dt.timedelta(weeks=6)).isoformat()
    nuevo = os.path.join(ent, "Demand-forecast-fleet-%s.csv" % dt.date.today().strftime("%d_%m_%Y"))
    with open(nuevo, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=DEM_COLS); w.writeheader()
        for k in sorted(filas):
            if k[1] >= corte:
                w.writerow(filas[k])
    for f in viejos:
        if os.path.abspath(f) != os.path.abspath(nuevo):
            os.remove(f)
    return nuevo


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    gen = None
    if "--generado" in sys.argv:
        gen = sys.argv[sys.argv.index("--generado") + 1]
    from zoneinfo import ZoneInfo
    gen = gen or dt.datetime.now(ZoneInfo("Europe/Madrid")).isoformat(timespec="minutes")
    txt = open(sys.argv[1], encoding="utf-8").read()
    dem, malas_d = parse_dem(txt)
    dias, malas = parse("\n".join(l for l in txt.splitlines() if not l.strip().startswith("DEM ")))
    malas += malas_d
    if malas:
        print("NO SE ESCRIBE: hay líneas que no cuadran:\n  " + "\n  ".join(malas)); sys.exit(1)
    if not dias and not dem:
        print("NO SE ESCRIBE: lectura vacía"); sys.exit(1)
    if dem:
        f = escribir_demanda(dem)
        print(f"Demanda: {len(dem)} días-ciudad → {os.path.basename(f)}")
    if not dias:
        return
    old = {}
    if os.path.exists(DEST):
        try:
            old = json.load(open(DEST, encoding="utf-8")).get("dias", {})
        except Exception:
            old = {}
    old.update(dias)
    corte = (dt.date.today() - dt.timedelta(weeks=6)).isoformat()
    old = {k: v for k, v in old.items() if k.split("|")[1] >= corte}
    out = {"generado": gen, "fuente": "fleet.glovoapp.com · Calendario (slots por rider)",
           "nota": "b = media hora reservada y presentada; nc = reservada sin registro (no show); ev = en evaluación (turno en curso). Reservado actual = b+nc+ev; capacidad actual = b+ev.",
           "dias": dict(sorted(old.items()))}
    json.dump(out, open(DEST, "w", encoding="utf-8"), separators=(",", ":"))
    tot = {}
    for k, v in dias.items():
        c = k.split("|")[0]; tot[c] = tot.get(c, 0) + sum(v["b"]) + sum(v["nc"]) + sum(v["ev"])
    print(f"OK · {len(dias)} días-ciudad leídos · " + ", ".join(f"{c}: {n / 2:g} h" for c, n in sorted(tot.items())))


if __name__ == "__main__":
    main()
