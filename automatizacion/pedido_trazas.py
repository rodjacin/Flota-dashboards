# -*- coding: utf-8 -*-
"""
pedido_trazas.py · Trazas y paradas por nº de pedido (cifradas)
================================================================
Cruza el archivo PRIVADO de posiciones con pedido (posiciones.py → archivo_pedidos.json,
3 días, solo en la caché de GitHub Actions) con el bucket de Glovo:

  · delivery_lv:     rider que entregó · aviso → recogida (tramo «hacia el restaurante»)
                     y recogida → entrega (tramo «hacia el cliente»)
  · reassignment_lv: rider al que se le reasignó · aviso → reasignación

Para cada tramo guarda el recorrido (muestras de posición) y las paradas de 3 min o más.
Todo se publica CIFRADO (AES-256-GCM, clave derivada con PBKDF2 de la contraseña del
secreto PEDIDOS_CLAVE) en <dashboard>/pedidos_trazas.json; la pestaña «Paradas con
pedido» lo descifra en el navegador al buscar un pedido con la contraseña.
No se publica la ubicación del cliente.

Uso (lo lanza ejecutar.sh tras generar los dashboards):
   PEDIDOS_CLAVE=... python3 pedido_trazas.py <carpeta del repo>
"""
import os
import sys
import json
import zlib
import base64
import datetime as dt

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import heatmaps_reasignaciones as H        # leer() / punto() del bucket ya descargado
import posiciones as P                      # ARCH_FILE, _dist, MOVE_M, REST_M

DIAG = {}   # contadores agregados (sin datos personales) para saber dónde se pierden los tramos

DASHBOARDS = {"gra-mad-nom-alc": ["ALC", "GRA", "MAD", "NOM"], "sab": ["SAB"]}
PARADA_MIN = 3          # minutos para contar una parada
MARGEN_MIN = 2          # margen alrededor del tramo para coger muestras
ITER = 200000           # PBKDF2


def _tz():
    from zoneinfo import ZoneInfo
    return ZoneInfo("Europe/Madrid")


def _local(s, tz):
    s = str(s or "").strip()
    if not s:
        return None
    try:
        d = dt.datetime.fromisoformat(s.replace("Z", "+00:00")[:32])
    except Exception:
        return None
    return d if d.tzinfo else d.replace(tzinfo=tz)


def _muestras(A, rid, t0, t1):
    """Muestras del rider entre t0 y t1 (con margen): [(datetime, lat, lng, loc_at)]."""
    a = t0 - dt.timedelta(minutes=MARGEN_MIN)
    b = t1 + dt.timedelta(minutes=MARGEN_MIN)
    out = []
    for o in A.get(str(rid)) or []:
        t = P._ts(o[0])
        if t and a <= t <= b:
            out.append((t, o[1], o[2], o[3]))
    return out


def _paradas(M, rest=None, tz=None):
    """Paradas >= PARADA_MIN min: grupos de muestras seguidas a menos de MOVE_M metros.
    La duración va de la primera a la última muestra del grupo (Glovo actualiza la ubicación cada
    ~5 min, así que una parada corta puede no verse)."""
    out, i = [], 0
    while i < len(M):
        j = i
        while j + 1 < len(M) and P._dist((M[i][1], M[i][2]), (M[j + 1][1], M[j + 1][2])) <= P.MOVE_M:
            j += 1
        mins = (M[j][0] - M[i][0]).total_seconds() / 60
        if mins >= PARADA_MIN:
            lat = sum(m[1] for m in M[i:j + 1]) / (j - i + 1)
            lon = sum(m[2] for m in M[i:j + 1]) / (j - i + 1)
            en_local = bool(rest and rest[0] is not None and P._dist((lat, lon), rest) <= P.REST_M)
            out.append([round(lat, 5), round(lon, 5), (M[i][0].astimezone(tz) if tz else M[i][0]).strftime("%H:%M"), round(mins, 1), 1 if en_local else 0])
        i = j + 1
    return out


def _tramo(A, rid, t0, t1, tipo, rest, tz):
    if not t0 or not t1 or t1 <= t0:
        return None
    M = _muestras(A, rid, t0, t1)
    if len(M) < 2:
        return None
    return {"tipo": tipo, "rider": str(rid),
            "t0": t0.astimezone(tz).strftime("%H:%M"), "t1": t1.astimezone(tz).strftime("%H:%M"),
            "min": round((t1 - t0).total_seconds() / 60, 1),
            "pts": [[round((m[0] - t0).total_seconds() / 60, 1), round(m[1], 5), round(m[2], 5)] for m in M],
            "par": _paradas(M, rest, tz)}


def construir(cities, A, tz):
    import pandas as pd
    lim = (P._now() - dt.timedelta(hours=P.ARCH_HOURS + 6)).astimezone(tz).replace(tzinfo=None)
    out = {}
    # entregas: tramo hacia el restaurante y hacia el cliente
    dl = H.leer(pd, "delivery_lv.csv", cols=[
        "order_id", "rider_id", "city_code", "store_name", "vendor_location", "delivery_status",
        "rider_notified_local_at", "rider_accepted_local_at", "rider_picked_up_at", "rider_dropped_off_local_at"])
    if not dl.empty:
        dl = dl[dl["city_code"].map(lambda c: H.NODE_ALIASES.get(c, c)).isin(set(cities))]
        t = pd.to_datetime(dl["rider_notified_local_at"].str.slice(0, 19), errors="coerce")
        dl = dl[t >= lim]
        for g in dl.to_dict("records"):
            oid, rid = str(g.get("order_id", "")).strip(), str(g.get("rider_id", "")).strip()
            if not oid or rid not in A:
                continue
            rest = H.punto(g.get("vendor_location"))
            t_av = _local(g.get("rider_notified_local_at") or g.get("rider_accepted_local_at"), tz)
            t_rec = _local(g.get("rider_picked_up_at"), tz)
            t_ent = _local(g.get("rider_dropped_off_local_at"), tz)
            tr = [x for x in (_tramo(A, rid, t_av, t_rec, "R", rest, tz), _tramo(A, rid, t_rec, t_ent, "C", rest, tz)) if x]
            if not tr:
                continue
            o = out.setdefault(oid, {"tienda": str(g.get("store_name", "")), "area": g.get("city_code", ""),
                                      "dia": t_av.astimezone(tz).strftime("%Y-%m-%d") if t_av else "",
                                      "rest": list(rest), "tramos": []})
            o["tramos"] += tr
    # reasignaciones: lo que hizo el rider que perdió el pedido, del aviso a la reasignación
    re_ = H.leer(pd, "reassignment_lv.csv", cols=[
        "order_id", "rider_id", "city_code", "store_name", "notified_at_local", "reassigned_at_local",
        "reassignment_reason", "delivery_id"])
    if not re_.empty:
        re_ = re_[re_["city_code"].map(lambda c: H.NODE_ALIASES.get(c, c)).isin(set(cities))]
        t = pd.to_datetime(re_["notified_at_local"].str.slice(0, 19), errors="coerce")
        re_ = re_[t >= lim]
        D = DIAG.setdefault(",".join(cities), {"reasig": 0, "rider_en_archivo": 0, "sin_horas": 0, "muestras_0": 0,
                                                "muestras_1": 0, "con_tramo": 0, "muestras_30min": 0})
        for g in re_.to_dict("records"):
            oid, rid = str(g.get("order_id", "")).strip(), str(g.get("rider_id", "")).strip()
            D["reasig"] += 1
            if not oid or rid not in A:
                continue
            D["rider_en_archivo"] += 1
            o = out.get(oid)
            rest = tuple(o["rest"]) if o else (None, None)
            ta, tb = _local(g.get("notified_at_local"), tz), _local(g.get("reassigned_at_local"), tz)
            if not ta or not tb or tb <= ta:
                D["sin_horas"] += 1; continue
            nm = len(_muestras(A, rid, ta, tb))
            if nm < 2:
                D["muestras_%d" % min(nm, 1)] += 1
                if _muestras(A, rid, ta - dt.timedelta(minutes=30), tb + dt.timedelta(minutes=30)):
                    D["muestras_30min"] += 1
            x = _tramo(A, rid, ta, tb, "X", rest, tz)
            if not x:
                continue
            D["con_tramo"] += 1
            x["motivo"] = H._info(str(g.get("reassignment_reason", "")))["es"]
            if o is None:
                t_av = _local(g.get("notified_at_local"), tz)
                o = out[oid] = {"tienda": str(g.get("store_name", "")), "area": g.get("city_code", ""),
                                "dia": t_av.strftime("%Y-%m-%d") if t_av else "", "rest": [None, None], "tramos": []}
            o["tramos"].insert(0, x)
    return out


def cifrar(obj, clave):
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    from cryptography.hazmat.primitives import hashes
    salt, iv = os.urandom(16), os.urandom(12)
    key = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=ITER).derive(clave.encode("utf-8"))
    raw = zlib.compress(json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8"), 9)
    ct = AESGCM(key).encrypt(iv, raw, None)
    b = lambda x: base64.b64encode(x).decode("ascii")
    return {"v": 1, "alg": "AES-256-GCM", "kdf": "PBKDF2-SHA256", "iter": ITER,
            "salt": b(salt), "iv": b(iv), "data": b(ct)}


def main(repo):
    clave = os.environ.get("PEDIDOS_CLAVE", "")
    if not clave:
        print("pedido_trazas: falta el secreto PEDIDOS_CLAVE; no se publica el buscador por pedido")
        return
    try:
        A = json.load(open(P.ARCH_FILE, encoding="utf-8"))
    except Exception:
        A = {}
    tz = _tz()
    for carpeta, cs in DASHBOARDS.items():
        d = os.path.join(repo, carpeta)
        if not os.path.isdir(d):
            continue
        datos = construir(cs, A, tz) if A else {}
        env = cifrar(datos, clave)
        dias = sorted({o["dia"] for o in datos.values() if o.get("dia")})
        env.update({"n": len(datos), "dias": dias, "updated_at": P._now().isoformat(),
                    "diag": DIAG.get(",".join(cs), {}),
                    "tramos": {k: sum(1 for o in datos.values() for t in o["tramos"] if t["tipo"] == k) for k in "XRC"},
                    "archivo_riders": len(A),
                    # nº de pedido con recorrido del rider reasignado (sin posiciones ni rider): la ventana de
                    # Delivery Race lo usa para avisar de qué pedidos tienen traza antes de pedir la contraseña
                    "con_x": sorted(k for k, o in datos.items() if any(t["tipo"] == "X" for t in o["tramos"]))})
        with open(os.path.join(d, "pedidos_trazas.json"), "w", encoding="utf-8") as f:
            json.dump(env, f, separators=(",", ":"))
        print("%s/pedidos_trazas.json: %d pedidos con traza (%s)" % (carpeta, len(datos), ", ".join(dias) or "sin días"))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else ".")
