# -*- coding: utf-8 -*-
"""
================================================================================
 Historial de posiciones de los riders y cálculo de paradas con pedido activo
================================================================================
 · muestrear(): descarga Live Operations (en_vivo.py) y añade una observación por
   rider al historial. Lo lanza cada 5 min el workflow "Muestreo de posiciones"
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
REST_FILE = os.path.expanduser("~/Downloads/dashboards/posiciones/restaurantes.json")
# Dashboards publicados y sus ciudades: el muestreo escribe <carpeta>/wtd_vivo.json
DASHBOARDS = {"gra-mad-nom-alc": ["ALC", "GRA", "MAD", "NOM"], "sab": ["SAB"]}
CIUDADES = ["ALC", "GRA", "MAD", "NOM", "SAB"]
NODE_ALIASES = {"NEM": "MAD"}

KEEP_HOURS = 24       # horas de historial que se guardan (día completo)
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
                   act, code, r.get("status"), d.get("completed_deliveries_count")]
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
    return n, snap


def exportar(repo, snap):
    """Escribe <repo>/<dashboard>/wtd_vivo.json con las paradas (solo minutos, sin coordenadas)."""
    nombres = {}
    for code, C in (snap.get("cities") or {}).items():
        for r in C.get("riders") or []:
            nombres[str(r.get("employee_id"))] = [r.get("name") or "", code]
    for carpeta, cs in DASHBOARDS.items():
        grid = restaurantes(cs)
        paradas, foto = quietos(cs, grid)
        try:
            ahora_te, episodios = tras_entrega(cs, grid)
        except Exception as e:
            print("tras_entrega (%s): %s" % (carpeta, e)); ahora_te, episodios = {}, []
        out = {"foto": foto or snap.get("fetched_at"), "paradas": paradas,
               "tras_entrega": ahora_te, "episodios": episodios,
               "riders": {k: v for k, v in nombres.items() if v[1] in cs}}
        d = os.path.join(repo, carpeta)
        if os.path.isdir(d):
            with open(os.path.join(d, "wtd_vivo.json"), "w", encoding="utf-8") as f:
                json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
            print("%s/wtd_vivo.json: %d riders con posición" % (carpeta, len(paradas)))
            try:
                n = acumular_liveops(os.path.join(d, LIVEOPS_HIST), snap, cs)
                print("%s/%s: %d riders hoy" % (carpeta, LIVEOPS_HIST, n))
            except Exception as e:
                print("histórico Live Ops (%s): %s" % (carpeta, e))
            try:
                n = guardar_historico(os.path.join(d, HIST_V1), episodios)
                print("%s/%s: %d paradas tras entrega acumuladas" % (carpeta, HIST_V1, n))
            except Exception as e:
                print("histórico WTD%% v1 (%s): %s" % (carpeta, e))


# ------------------------------------------------------------- restaurantes
def restaurantes(cities):
    """Rejilla de posiciones de locales (vendor_location) de esas ciudades.
       Lee el bucket (delivery_lv) si está; si no (muestreo cada 10 min), usa la copia
       guardada en REST_FILE en la última actualización horaria."""
    import csv, re
    pat = re.compile(r"POINT\(([-\d.]+) ([-\d.]+)\)")
    cs = set(cities or [])
    por_ciudad = {}
    if os.path.isfile(DELIV_CSV):
        with open(DELIV_CSV, encoding="utf-8-sig") as fh:
            for r in csv.DictReader(fh):
                c = (r.get("city_code") or "").strip()
                c = NODE_ALIASES.get(c, c)
                m = pat.search(r.get("vendor_location") or "")
                if m:
                    por_ciudad.setdefault(c, set()).add((round(float(m.group(2)), 5), round(float(m.group(1)), 5)))
        try:
            os.makedirs(os.path.dirname(REST_FILE), exist_ok=True)
            json.dump({c: sorted(v) for c, v in por_ciudad.items()}, open(REST_FILE, "w"), separators=(",", ":"))
        except Exception:
            pass
    else:
        try:
            por_ciudad = {c: set(map(tuple, v)) for c, v in json.load(open(REST_FILE)).items()}
        except Exception:
            por_ciudad = {}
    grid = {}
    for c, pts in por_ciudad.items():
        if cs and c not in cs:
            continue
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


# ------------------------------------------------- parado tras entregar (WTD% v1)
TRAS_UMBRAL_MIN = 5    # aviso: minutos parado tras entregar (rojo a partir del doble)


LIVEOPS_HIST = "liveops_hist.json"   # histórico diario de Live Operations por rider (sin coordenadas)
LIVEOPS_DIAS = 60
_ST_ES = {"working": "Trabajando", "ready": "Listo", "available": "Disponible", "late": "Con retraso", "break": "En pausa",
          "starting": "Empezando", "ending": "Terminando", "temp_not_working": "Parado temporalmente", "not_working": "No trabajando"}


def acumular_liveops(path, snap, cities):
    """Suma la foto actual al histórico diario: por rider y día (hora de Madrid)
    [área, nombre, fotos, fotos con retraso, fotos en pausa, nº pausas (máx), seg. en pausa (máx),
     notificados (máx), aceptados (máx), tasa de aceptación (última), fotos con monedero sobre el límite,
     saldo máximo, {estado · motivo: fotos}]"""
    import re
    try:
        h = json.load(open(path, encoding="utf-8"))
    except Exception:
        h = {}
    D = h.setdefault("dias", {})
    try:
        from zoneinfo import ZoneInfo
        hoy = dt.datetime.now(ZoneInfo("Europe/Madrid")).date().isoformat()
    except Exception:
        hoy = (_now() + dt.timedelta(hours=2)).date().isoformat()
    dia = D.setdefault(hoy, {})
    n = 0
    for code, C in (snap.get("cities") or {}).items():
        if code not in cities:
            continue
        for r in C.get("riders") or []:
            st = r.get("status") or ""
            if st in ("not_working", ""):
                continue
            rid = str(r.get("employee_id"))
            v = dia.get(rid) or [code, "", 0, 0, 0, 0, 0, 0, 0, None, 0, 0, {}]
            perf = r.get("performance") or {}
            ts = perf.get("time_spent") or {}
            di = r.get("deliveries_info") or {}
            wi = r.get("wallet_info") or {}
            v[0] = code; v[1] = r.get("name") or v[1]; v[2] += 1
            if st == "late": v[3] += 1
            if st == "break": v[4] += 1
            v[5] = max(v[5], int(ts.get("number_of_breaks") or 0))
            v[6] = max(v[6], int(ts.get("break_seconds") or 0))
            v[7] = max(v[7], int(di.get("notified_deliveries_count") or 0))
            v[8] = max(v[8], int(di.get("accepted_deliveries_count") or 0))
            if perf.get("acceptance_rate") is not None: v[9] = perf.get("acceptance_rate")
            if re.search(r"hard|over|above", str(wi.get("limit_status") or ""), re.I): v[10] += 1
            try: v[11] = max(v[11], round(float(wi.get("balance") or 0), 2))
            except Exception: pass
            mot = (r.get("status_metadata") or {}).get("reason")
            if mot and st != "working":
                k = _ST_ES.get(st, st) + " · " + str(mot)
                v[12][k] = v[12].get(k, 0) + 1
            dia[rid] = v
            n += 1
    lim = (dt.date.fromisoformat(hoy) - dt.timedelta(days=LIVEOPS_DIAS)).isoformat()
    h["dias"] = {k: v for k, v in D.items() if k >= lim}
    h["updated_at"] = _now().isoformat()
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(h, fh, ensure_ascii=False, separators=(",", ":"))
    os.replace(tmp, path)
    return len(dia)


HIST_V1 = "wtd_v1_hist.json"   # histórico publicado de paradas tras entrega (sin coordenadas)
HIST_V1_DIAS = 120             # días que se conservan


def _min_epoch(s):
    t = _ts(s)
    return int(t.timestamp() // 60) if t else None


def guardar_historico(path, episodios):
    """Acumula las paradas tras entrega en <dashboard>/wtd_v1_hist.json.
    Fila: [rider, área, estado, entrega_ini, entrega_fin(=desde), hasta, min, max, flags]
    (horas en minutos epoch UTC; flags: 1 en restaurante, 2 GPS congelado, 4 sin confirmar).
    Una parada se identifica por rider + entrega_fin; si vuelve a aparecer con más
    duración (seguía parado) se actualiza."""
    try:
        h = json.load(open(path, encoding="utf-8"))
    except Exception:
        h = {}
    filas = {"%s|%s" % (f[0], f[4]): f for f in h.get("eps", [])}
    for e in episodios:
        e1 = _min_epoch(e["ent_fin"])
        if e1 is None:
            continue
        fl = (1 if e.get("local") else 0) | (2 if e.get("gps_viejo") else 0) | (4 if e.get("confirmada") is None else 0)
        f = [str(e["rid"]), e["city"], e.get("status") or "", _min_epoch(e["ent_ini"]), e1,
             _min_epoch(e["hasta"]), e["min"], e["max"], fl]
        k = "%s|%s" % (f[0], e1)
        if k not in filas or (f[5] or 0) >= (filas[k][5] or 0):
            filas[k] = f
    lim = int(_now().timestamp() // 60) - HIST_V1_DIAS * 1440
    eps = sorted((f for f in filas.values() if f[4] >= lim), key=lambda f: (f[4], f[0]))
    out = {"v": 1, "updated_at": _now().isoformat(),
           "cols": ["rider", "area", "estado", "ent_ini", "ent_fin", "hasta", "min", "max", "flags"], "eps": eps}
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, separators=(",", ":"))
    os.replace(tmp, path)
    return len(eps)


def tras_entrega(cities, grid=None, hist=None):
    """Paradas justo después de entregar un pedido, en el historial disponible (KEEP_HOURS).

    Una entrega se detecta entre dos muestras seguidas cuando un pedido activo desaparece,
    el rider se queda sin pedido y (si Glovo lo informa) sube su contador de entregas
    completadas. Desde la primera muestra sin pedido se cuenta cuánto sigue a menos de
    MOVE_M metros del mismo punto sin coger otro pedido.

    Devuelve (ahora, episodios):
      ahora     rider_id -> episodio en curso en la última muestra (sigue parado ahora)
      episodios lista de episodios con al menos una muestra parado (>= ~10 min) o en curso
    Cada episodio: rid, city, status, ent_ini/ent_fin (entre qué muestras entregó), desde,
    hasta, min (mínimo parado: la parada real empezó en la entrega, antes de 'desde'),
    max (cota superior: desde la última muestra con el pedido), en_curso, local (junto a un
    restaurante), confirmada (subió el contador de completadas), gps_viejo. Sin coordenadas.
    """
    h = hist if hist is not None else cargar()
    grid = grid if grid is not None else restaurantes(cities)
    cs = set(cities or [])
    ahora = _now()
    actual, eps = {}, []
    for rid, obs in (h.get("riders") or {}).items():
        if len(obs) < 2:
            continue
        T = [_ts(o[0]) for o in obs]
        n = len(obs)
        fresco = T[-1] is not None and (ahora - T[-1]).total_seconds() <= FRESH_MIN * 60
        i = 1
        while i < n:
            p, c = obs[i - 1], obs[i]
            if (T[i] is None or T[i - 1] is None or (cs and c[6] not in cs)
                    or (T[i] - T[i - 1]).total_seconds() > MAX_GAP_MIN * 60
                    or not p[4] or c[4]):
                i += 1
                continue
            idos = set(p[5] or []) - set(c[5] or [])
            if p[5] and not idos:
                i += 1
                continue
            cp = p[8] if len(p) > 8 else None
            cc = c[8] if len(c) > 8 else None
            confirmada = None
            if cp is not None and cc is not None:
                if cc <= cp:          # desapareció sin sumar entrega: cancelado o reasignado
                    i += 1
                    continue
                confirmada = True
            ancla = (c[1], c[2])
            j = i
            while j + 1 < n:
                o = obs[j + 1]
                if (o[4] or T[j + 1] is None or (T[j + 1] - T[j]).total_seconds() > MAX_GAP_MIN * 60
                        or _dist((o[1], o[2]), ancla) > MOVE_M):
                    break
                j += 1
            en_curso = (j == n - 1) and fresco
            mins = round((T[j] - T[i]).total_seconds() / 60)
            if j > i or en_curso:
                ep = {"rid": rid, "city": c[6], "status": obs[j][7],
                      "ent_ini": obs[i - 1][0], "ent_fin": c[0], "desde": c[0], "hasta": obs[j][0],
                      "min": mins, "max": round((T[j] - T[i - 1]).total_seconds() / 60),
                      "en_curso": en_curso, "local": _junto_a_local(ancla, grid),
                      "confirmada": confirmada}
                la = _ts(obs[j][3])
                if la and (T[j] - la).total_seconds() > 15 * 60:
                    ep["gps_viejo"] = round((T[j] - la).total_seconds() / 60)
                eps.append(ep)
                if en_curso:
                    actual[rid] = ep
            i = j + 1
    eps.sort(key=lambda e: e["desde"], reverse=True)
    return actual, eps


if __name__ == "__main__":
    import sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    n, snap = muestrear()
    if len(sys.argv) > 1 and n:          # python3 posiciones.py <carpeta del repo>  -> publica wtd_vivo.json
        exportar(sys.argv[1], snap)
