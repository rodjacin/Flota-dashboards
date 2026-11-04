# -*- coding: utf-8 -*-
"""Convierte el texto de window.__calExport() (calendario_fleet_lector.js) en
automatizacion/entradas/calendario_fleet.json, que lee la pestaña Capacidad.

    python3 calendario_fleet_json.py lectura.txt [--generado 2026-11-04T10:05:00+01:00]

· Comprueba que cada línea cuadra (suma de b+nc+ev == tot). Si alguna no cuadra, no escribe nada.
· Fusiona con el JSON existente: los días leídos ahora sustituyen a los anteriores; el resto se conserva.
· Los días con 0 reservas (semana aún sin cargar) no se guardan.
· Conserva solo las últimas 6 semanas para que el fichero no crezca sin fin.
"""
import os, re, sys, json, datetime as dt

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


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    gen = None
    if "--generado" in sys.argv:
        gen = sys.argv[sys.argv.index("--generado") + 1]
    from zoneinfo import ZoneInfo
    gen = gen or dt.datetime.now(ZoneInfo("Europe/Madrid")).isoformat(timespec="minutes")
    dias, malas = parse(open(sys.argv[1], encoding="utf-8").read())
    if malas:
        print("NO SE ESCRIBE: hay líneas que no cuadran:\n  " + "\n  ".join(malas)); sys.exit(1)
    if not dias:
        print("NO SE ESCRIBE: lectura vacía"); sys.exit(1)
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
