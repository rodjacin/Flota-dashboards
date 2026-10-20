#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tabla «Pedidos por restaurante» a partir del bucket de GCP (copia local en ~/Downloads/fleet_data).

Lee todos los delivery_lv.csv, cuenta pedidos distintos (order_id) por restaurante y semana ISO
(lunes-domingo, fecha de creación del pedido en hora local) y genera una página HTML autónoma.
Restaurante = ciudad + store_name + ubicación del local (vendor_location, ~10 m); el nombre
mostrado es «store_name · zona». Se guardan dos recuentos: entregados (delivery_status
completed) y todos (cualquier estado).

Uso: python3 pedidos_restaurantes.py [salida.html]
"""
import os, re, sys, csv, glob, json, datetime as dt, collections

RAW_DIR = os.path.expanduser("~/Downloads/fleet_data")
OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser("~/Downloads/dashboards/pedidos_restaurantes.html")
POLIGONOS = os.path.expanduser("~/Downloads/cp_poligonos.json")
TPL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "plantilla_pedidos_restaurantes.html")
POINT_RE = re.compile(r"POINT\s*\(\s*(-?\d+(?:\.\d+)?)\s+(-?\d+(?:\.\d+)?)\s*\)", re.I)
csv.field_size_limit(10 ** 8)


def _cps(locs):
    """{"lat,lon": código postal} con los polígonos de cp_poligonos.json (vacío si no hay shapely/fichero)."""
    try:
        from shapely import points, STRtree
        from shapely.geometry import shape
        G = json.load(open(POLIGONOS, encoding="utf-8"))
    except Exception:
        return {}
    geoms = [shape(f["geometry"]) for f in G["features"]]
    cps = [f["properties"]["cp"] for f in G["features"]]
    locs = [l for l in locs if l]
    if not locs:
        return {}
    pts = points([float(l.split(",")[1]) for l in locs], [float(l.split(",")[0]) for l in locs])
    ip, ig = STRtree(geoms).query(pts, predicate="within")
    return {locs[i]: cps[g] for i, g in zip(ip, ig)}


def main():
    files = sorted(glob.glob(os.path.join(RAW_DIR, "*", "*", "delivery_lv.csv")))
    if not files:
        sys.exit("no hay delivery_lv.csv en " + RAW_DIR)
    orders = {}          # order_id -> [fecha, ciudad, store, zona, loc, completed]
    for f in files:
        try:
            fh = open(f, encoding="utf-8-sig", newline="")
        except OSError:
            continue
        with fh:
            for r in csv.DictReader(fh):
                oid = (r.get("order_id") or "").strip()
                if not oid:
                    continue
                d = (r.get("order_created_local_at") or r.get("p_created_date") or "")[:10]
                if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", d):
                    continue
                m = POINT_RE.search(r.get("vendor_location") or "")
                loc = "%.4f,%.4f" % (float(m.group(2)), float(m.group(1))) if m else ""
                done = (r.get("delivery_status") or "").strip().lower() == "completed"
                prev = orders.get(oid)
                if prev is None:
                    orders[oid] = [d, (r.get("city_code") or "").strip(), (r.get("store_name") or "").strip(),
                                   (r.get("zone_name") or "").strip(), loc, done]
                else:                       # mismo pedido en varias filas (reasignado, multi-entrega)
                    prev[5] = prev[5] or done
                    if not prev[4] and loc:
                        prev[4] = loc
    # ubicación de los pedidos sin vendor_location: la más frecuente de ese store+zona
    freq = collections.defaultdict(collections.Counter)
    for d, c, s, z, loc, _ in orders.values():
        if loc:
            freq[(c, s, z)][loc] += 1
    agg = collections.defaultdict(lambda: [collections.Counter(), collections.Counter()])
    zones = collections.defaultdict(collections.Counter)
    days = set()
    for d, c, s, z, loc, done in orders.values():
        if not loc and freq.get((c, s, z)):
            loc = freq[(c, s, z)].most_common(1)[0][0]
        y, w, _ = dt.date.fromisoformat(d).isocalendar()
        wk = "%d-W%02d" % (y, w)
        k = (c, s, loc)
        agg[k][1][wk] += 1
        if done:
            agg[k][0][wk] += 1
        zones[k][z] += 1
        days.add(d)
    weeks = sorted({w for a in agg.values() for w in a[1]})
    wdays = collections.defaultdict(set)
    for d in days:
        y, w, _ = dt.date.fromisoformat(d).isocalendar()
        wdays["%d-W%02d" % (y, w)].add(d)
    # nombres: store · zona · CP (y #n si aun así hay varios locales iguales)
    cpm = _cps({k[2] for k in agg})
    def nombre(k):
        z = zones[k].most_common(1)[0][0] or k[0]
        n = (k[1] or "(sin nombre)") + " · " + z
        return n + (" · CP " + str(cpm[k[2]]) if k[2] in cpm else "")
    base = {k: nombre(k) for k in agg}
    cnt = collections.Counter(base.values())
    seen = collections.Counter()
    rows = []
    for k in sorted(agg, key=lambda k: -sum(agg[k][1].values())):
        n = base[k]
        if cnt[n] > 1:
            seen[n] += 1
            n += " #%d" % seen[n]
        rows.append(dict(c=k[0], n=n, s=k[1], loc=k[2], cp=str(cpm.get(k[2], "")),
                         e=[agg[k][0].get(w, 0) for w in weeks], t=[agg[k][1].get(w, 0) for w in weeks]))

    def lab(w):
        ds = sorted(wdays[w])
        f = lambda x: x[8:10] + "/" + x[5:7]
        y, n = w.split("-W")
        mon = dt.date.fromisocalendar(int(y), int(n), 1)
        return dict(w="W" + n, y=int(y), r=f(mon.isoformat()) + "–" + f((mon + dt.timedelta(days=6)).isoformat()),
                    n=len(ds))
    data = dict(weeks=[lab(w) for w in weeks], rows=rows, first=min(days), last=max(days), nd=len(days),
                gen=dt.datetime.now().strftime("%d/%m/%Y %H:%M"))
    html = open(TPL, encoding="utf-8").read().replace(
        "/*__DATA__*/null", json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/"))
    os.makedirs(os.path.dirname(OUT) or ".", exist_ok=True)
    open(OUT, "w", encoding="utf-8").write(html)
    print("pedidos por restaurante: %d restaurantes · %d semanas · %d pedidos (%s a %s) -> %s" % (
        len(rows), len(weeks), sum(sum(r["t"]) for r in rows), data["first"], data["last"], OUT))


if __name__ == "__main__":
    main()
