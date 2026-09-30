# -*- coding: utf-8 -*-
"""
================================================================================
 Historial de posiciones de los riders y cálculo de paradas con pedido activo
================================================================================
 · muestrear(): descarga Live Operations (en_vivo.py) y añade una observación por
   rider al historial. Lo lanza cada 10 min el workflow "Muestreo de posiciones"
   y también cada actualización del dashboard.
 · quietos(): minutos que lleva cada rider sin moverse (menos de MOVE_M metros)
   mientras tiene un pedido activo y no está junto a un restaurante conocido
   (vendor_location del bucket, delivery_lv).

 PRIVACIDAD: las coordenadas solo se guardan en HIST_FILE (caché privada de
 GitHub Actions / tu Mac), se borran pasadas KEEP_HOURS horas y NUNCA se
 publican: el dashboard solo muestra minutos.

 Uso manual:  python3 posiciones.py          (toma una muestra de todas las ciudades)
================================================================================
"""
import os, json, math, datetime as dt

HIST_FILE = os.path.expanduser("~/Downloads/dashboards/posiciones/historial.json")
DELIV_CSV = os.path.expanduser("~/Downloads/fleet_data_combinado/delivery_lv_combinado.csv")
CIUDADES = ["ALC", "GRA", "MAD", "NOM", "SAB"]
NODE_ALIASES = {"NEM": "MAD"}

KEEP_HOURS = 3        # horas de historial que se guardan
MOVE_M = 80           # se considera "sin moverse" si está a menos de estos metros
REST_M = 100          # a menos de estos metros de un restaurante conocido = esperando en el local
MAX_GAP_MIN = 25      # si faltan muestras más tiempo que esto, se corta la cuenta
FRESH_MIN = 20        # la última muestra debe tener como mucho estos minutos para mostrarse


def _now():
    return dt.datetime.now(dt.timezone.utc)


def _ts(s):
    try:
        return dt.datetime.fromisoformat(str(s).replace("Z", "+00:00")[:32])
    except Exception:
        return None


def _dist(a, b):
    """Metros entre (lat, lng) a y b (haversine)."""
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 2 * 6371000 * math.asin(math.sqrt(h))


# ------------------------------------------------------------------ historial
def cargar():
    try:
        return json.load(open(HIST_FILE, encoding="utf-8"))
    except Exception:
        return {"riders": {}}


def guardar(h):
    os.makedirs(os.path.dirname(HIST_FILE), exist_ok=True)
    tmp = HIST_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(h, f, separators=(",", ":"))
    os.replace(tmp, HIST_FILE)


def registrar(snap, pos, cuando=None):
    """Añade al historial una observación por rider de la foto (snap) + posiciones (pos)."""
    t = cuando or _ts(snap.get("fetched_at")) or _now()
    h = cargar()
    R = h.setdefault("riders", {})
    n = 0
    for code, C in (snap.get("cities") or {}).items():
        for r in C.get("riders") or []:
            rid = str(r.get("employee_id"))
            p = pos.get(rid)
            if not p:
                continue
            d = r.get("deliveries_info") or {}
            act = [str(x) for x in (d.get("active_delivery_ids") or [])]
            activo = bool(act or d.get("has_active_deliveries") or d.get("has_active_delivery"))
            obs = [t.isoformat(), round(p["lat"], 6), round(p["lng"], 6), p.get("loc_at"), 1 if activo else 0,
                   act, code, r.get("status")]
            lst = R.setdefault(rid, [])
            if lst and lst[-1][0] == obs[0]:
                lst[-1] = obs
            else:
                lst.append(obs)
            n += 1
    lim = (_now() - dt.timedelta(hours=KEEP_HOURS)).isoformat()
    for rid in list(R):
        R[rid] = sorted([o for o in R[rid] if o[0] >= lim], key=lambda o: o[0])
        if not R[rid]:
            del R[rid]
    h["updated_at"] = _now().isoformat()
    guardar(h)
    return n


def muestrear(codigos=None):
    import en_vivo
    snap = en_vivo._descargar(codigos or CIUDADES)
    n = registrar(snap, en_vivo._POS)
    print("muestra %s: %d riders con posición · errores: %s" % (
        snap.get("fetched_at", "")[:16], n, "; ".join(snap.get("errors") or []) or "ninguno"))
    return n


# ------------------------------------------------------------- restaurantes
def restaurantes(cities):
    """Rejilla de posiciones de locales (vendor_location) de esas ciudades."""
    import csv, re
    pat = re.compile(r"POINT\(([-\d.]+) ([-\d.]+)\)")
    cs = set(cities or [])
    pts = set()
    try:
        with open(DELIV_CSV, encoding="utf-8-sig") as fh:
            for r in csv.DictReader(fh):
                c = (r.get("city_code") or "").strip()
                if cs and NODE_ALIASES.get(c, c) not in cs:
                    continue
                m = pat.search(r.get("vendor_location") or "")
                if m:
                    pts.add((round(float(m.group(2)), 5), round(float(m.group(1)), 5)))
    except FileNotFoundError:
        pass
    grid = {}
    for p in pts:
        grid.setdefault((int(p[0] * 1000), int(p[1] * 1000)), []).append(p)
    return grid


def _junto_a_local(p, grid):
    gy, gx = int(p[0] * 1000), int(p[1] * 1000)
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            for q in grid.get((gy + dy, gx + dx), ()):
                if _dist(p, q) <= REST_M:
                    return True
    return False


# ------------------------------------------------------------------ paradas
def quietos(cities, grid=None, hist=None):
    """rider_id -> dict con el estado de parada en la última muestra.
       estado: 'parado' (min = minutos sin moverse con pedido activo), 'local' (junto a un
       restaurante), 'sin_pedido', 'sin_datos'. 'desde_inicio' = la cuenta llega a la
       primera muestra disponible (el valor real puede ser mayor)."""
    h = hist if hist is not None else cargar()
    grid = grid if grid is not None else restaurantes(cities)
    cs = set(cities or [])
    ahora = _now()
    out, ultima = {}, None
    for rid, obs in (h.get("riders") or {}).items():
        if not obs or (cs and obs[-1][6] not in cs):
            continue
        cur = obs[-1]
        tc = _ts(cur[0])
        if not tc or (ahora - tc).total_seconds() > FRESH_MIN * 60:
            continue
        ultima = max(ultima or tc, tc)
        pc = (cur[1], cur[2])
        res = {"t": cur[0], "loc_at": cur[3]}
        if not cur[4]:
            res["estado"] = "sin_pedido"
        elif _junto_a_local(pc, grid):
            res["estado"] = "local"
        else:
            desde, prev_t, inicio = tc, tc, True
            for o in reversed(obs[:-1]):
                to = _ts(o[0])
                if (not o[4] or _dist((o[1], o[2]), pc) > MOVE_M
                        or (prev_t - to).total_seconds() > MAX_GAP_MIN * 60):
                    inicio = False
                    break
                desde = prev_t = to
            res.update(estado="parado", min=round((tc - desde).total_seconds() / 60),
                       desde=desde.isoformat(), desde_inicio=inicio and len(obs) > 1,
                       n_muestras=len(obs))
        # GPS congelado: la posición no se ha actualizado en más de 15 min
        la = _ts(cur[3])
        if la and (tc - la).total_seconds() > 15 * 60:
            res["gps_viejo"] = round((tc - la).total_seconds() / 60)
        out[rid] = res
    return out, (ultima.isoformat() if ultima else None)


if __name__ == "__main__":
    import sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    muestrear()
