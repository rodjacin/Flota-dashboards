# -*- coding: utf-8 -*-
"""
================================================================================
 Pestaña "Capacidad" para los dashboards de flota
================================================================================
 Riders y pedidos por media hora: forecast frente a real.
   - Forecast: ficheros Demand-forecast-DD_MM_AAAA.csv en ~/Downloads
     (max_couriers_pilot = riders, final_order_forecast = pedidos). Si varios
     ficheros cubren la misma franja, gana el emitido más tarde.
   - Real: ~/Downloads/fleet_data (copia local del bucket de GCP):
     riders conectados de shift_lv.csv y pedidos de delivery_lv.csv.
   - Horario: ficheros subidos a la fleet tool (HORARIO*.xlsx/.csv y
     FORMATO GLOVO*.xlsx/.csv de ~/Downloads, con BOOK/UNBOOK). Los días sin datos reales (semana en curso o futura) se
     comparan con el horario.
 Lo usa generar_resumen_flota.py (igual que las pestañas UTR y No show).
================================================================================
"""
import os, re, csv, glob, json, datetime as dt, collections

FORECAST_GLOB = os.path.expanduser("~/Downloads/Demand-forecast-*.csv")
FLEET_DIR = os.path.expanduser("~/Downloads/fleet_data")
NODE_ALIASES = {"NEM": "MAD"}
MAX_WEEKS = 12


def _fecha_fichero(f):
    m = re.search(r"(\d\d)_(\d\d)_(\d{4})", os.path.basename(f))
    if m:
        try:
            return dt.datetime(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        except ValueError:
            pass
    return dt.datetime.fromtimestamp(os.path.getmtime(f))


def _slot(t):
    return t.replace(minute=0 if t.minute < 30 else 30, second=0, microsecond=0)


def _p(s):
    s = (s or "").strip()
    if not s:
        return None
    try:
        return dt.datetime.fromisoformat(s[:26])
    except ValueError:
        return None


def _num(v):
    try:
        return float(v or 0)
    except ValueError:
        return 0.0


def _city(v):
    v = (v or "").strip()
    return NODE_ALIASES.get(v, v)


# ------------------------------------------------------------------------------
#  Horarios subidos a la fleet tool (BOOK/UNBOOK): codigo_ciudad, dia,
#  hora_inicio, hora_final, accion, rider_id. Por ciudad y semana se usa el
#  fichero más reciente con reservas (BOOK) de esa semana.
# ------------------------------------------------------------------------------
HORARIO_DIR = os.path.expanduser("~/Downloads")
HORARIO_PATRON = re.compile(r"horario|formato\s*glo|ajuste", re.I)   # también los AJUSTE… (BOOK/UNBOOK) subidos a la fleet tool
_COLS = ("codigo_ciudad", "dia", "hora_inicio", "hora_final", "accion", "rider_id")


def _xlsx_filas(path):
    """Lee la primera hoja de un .xlsx (openpyxl si está; si no, lector mínimo)."""
    try:
        import openpyxl
        ws = openpyxl.load_workbook(path, data_only=True, read_only=True).worksheets[0]
        return [list(r) for r in ws.iter_rows(values_only=True)]
    except ImportError:
        pass
    import zipfile, xml.etree.ElementTree as ET
    ns = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    z = zipfile.ZipFile(path)
    ss = []
    if "xl/sharedStrings.xml" in z.namelist():
        for si in ET.fromstring(z.read("xl/sharedStrings.xml")).findall("m:si", ns):
            ss.append("".join(t.text or "" for t in si.iter("{%s}t" % ns["m"])))
    hoja = sorted(n for n in z.namelist() if n.startswith("xl/worksheets/sheet"))[0]
    filas = []
    for row in ET.fromstring(z.read(hoja)).iter("{%s}row" % ns["m"]):
        vals = {}
        for c in row.findall("m:c", ns):
            ref = re.match(r"([A-Z]+)", c.get("r", "A")).group(1)
            col = 0
            for ch in ref:
                col = col * 26 + ord(ch) - 64
            t, v = c.get("t"), c.find("m:v", ns)
            if t == "s" and v is not None:
                val = ss[int(v.text)]
            elif t == "inlineStr":
                val = "".join(x.text or "" for x in c.iter("{%s}t" % ns["m"]))
            elif v is not None:
                try:
                    val = float(v.text)
                except ValueError:
                    val = v.text
            else:
                val = None
            vals[col - 1] = val
        if vals:
            filas.append([vals.get(i) for i in range(max(vals) + 1)])
    return filas


def _csv_filas(path):
    with open(path, encoding="utf-8-sig", errors="replace") as fh:
        txt = fh.read()
    sep = ";" if txt.split("\n", 1)[0].count(";") > txt.split("\n", 1)[0].count(",") else ","
    return [r for r in csv.reader(txt.splitlines(), delimiter=sep)]


def _fecha(v):
    if v is None or v == "":
        return None
    if isinstance(v, dt.datetime):
        return v.date()
    if isinstance(v, dt.date):
        return v
    if isinstance(v, (int, float)):
        return dt.date(1899, 12, 30) + dt.timedelta(days=int(v))
    s = str(v).strip()
    for f in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%d/%m/%y"):
        try:
            return dt.datetime.strptime(s[:10] if f == "%Y-%m-%d" else s, f).date()
        except ValueError:
            pass
    try:
        return dt.date(1899, 12, 30) + dt.timedelta(days=int(float(s)))
    except ValueError:
        return None


def _hora(v):
    if v is None or v == "":
        return None
    if isinstance(v, dt.datetime):
        return v.hour * 60 + v.minute
    if isinstance(v, dt.time):
        return v.hour * 60 + v.minute
    if isinstance(v, (int, float)):
        return int(round((float(v) % 1) * 1440)) % 1440
    m = re.match(r"\s*(\d{1,2}):(\d{2})", str(v))
    if m:
        return (int(m.group(1)) % 24) * 60 + int(m.group(2))
    try:
        return int(round((float(v) % 1) * 1440)) % 1440
    except ValueError:
        return None


def _cabecera(fila0):
    """Devuelve {columna: índice} o None. Admite City/codigo_ciudad, rider_ID/rider_id y ficheros sin cabecera."""
    hdr = [str(h or "").strip().lower() for h in fila0]
    hdr = ["codigo_ciudad" if h in ("city", "ciudad") else h for h in hdr]
    if all(c in hdr for c in _COLS):
        return {c: hdr.index(c) for c in _COLS}, True
    # sin cabecera: formato Glovo "ciudad, rider, dia, inicio, fin, accion"
    v = list(fila0) + [None] * 6
    if re.fullmatch(r"[A-Z]{3}", str(v[0] or "").strip()) and str(v[5] or "").strip().upper() in ("BOOK", "UNBOOK"):
        return {"codigo_ciudad": 0, "rider_id": 1, "dia": 2, "hora_inicio": 3, "hora_final": 4, "accion": 5}, False
    return None, False


def _leer_horarios(cities):
    """Horario con turno por media hora a partir de los ficheros subidos a la fleet tool.
    Por ciudad y semana: el último fichero completo (solo BOOK) es la base; los ficheros
    posteriores con cambios (BOOK/UNBOOK o pocas filas) se aplican encima como ajustes.
    Devuelve {(ciudad, 'AAAA-MM-DD HH:MM'): riders}, {ciudad: set(fechas)}, {ciudad: {semana: [ficheros]}}."""
    piezas = []   # (mtime, fichero, (ciudad, semana), [(accion, rider, ini, fin)])
    for f in glob.glob(os.path.join(HORARIO_DIR, "*")):
        base = os.path.basename(f)
        if not HORARIO_PATRON.search(base) or not base.lower().endswith((".xlsx", ".csv")) or base.startswith("~$"):
            continue
        try:
            filas = _xlsx_filas(f) if base.lower().endswith(".xlsx") else _csv_filas(f)
        except Exception:
            continue
        if not filas:
            continue
        ix, con_cab = _cabecera(filas[0])
        if not ix:
            continue
        grupos = collections.defaultdict(list)
        for r in (filas[1:] if con_cab else filas):
            g = lambda c: r[ix[c]] if ix[c] < len(r) else None
            c = _city(str(g("codigo_ciudad") or ""))
            if not c or (cities and c not in cities):
                continue
            d, a, b = _fecha(g("dia")), _hora(g("hora_inicio")), _hora(g("hora_final"))
            acc = str(g("accion") or "").strip().upper()
            if d is None or a is None or b is None or acc not in ("BOOK", "UNBOOK"):
                continue
            rid = str(g("rider_id") or "").strip()
            if rid.endswith(".0"):
                rid = rid[:-2]
            ini = dt.datetime.combine(d, dt.time()) + dt.timedelta(minutes=a)
            fin = dt.datetime.combine(d, dt.time()) + dt.timedelta(minutes=b)
            if fin <= ini:
                fin += dt.timedelta(days=1)
            grupos[(c, d.isocalendar()[:2])].append((acc, rid, ini, fin))
        for key, ts in grupos.items():
            piezas.append((os.path.getmtime(f), base, key, ts))
    por_clave = collections.defaultdict(list)
    for p in piezas:
        por_clave[p[2]].append(p)
    cnt = collections.defaultdict(set)
    fechas = collections.defaultdict(set)
    fuentes = collections.defaultdict(dict)
    for key, ps in por_clave.items():
        ps.sort()
        mayor = max(len(p[3]) for p in ps)
        completos = [p for p in ps if all(t[0] == "BOOK" for t in p[3]) and len(p[3]) >= max(20, 0.5 * mayor)]
        if not completos:
            continue                                   # solo ajustes sueltos: no hay horario completo
        base_p = completos[-1]
        activos = set()                                 # (rider, slot)
        def aplicar(ts):
            for acc, rid, ini, fin in ts:
                t = _slot(ini)
                while t < fin:
                    if acc == "BOOK":
                        activos.add((rid, t))
                    else:
                        activos.discard((rid, t))
                    t += dt.timedelta(minutes=30)
        aplicar(base_p[3])
        usados = [base_p[1]]
        for p in ps:
            if p[0] > base_p[0] and p is not base_p:
                aplicar(p[3])
                usados.append(p[1])
        c, wk = key
        fuentes[c]["W%d" % wk[1]] = usados
        for rid, t in activos:
            cnt[(c, t.strftime("%Y-%m-%d %H:%M"))].add(rid)
            fechas[c].add(t.date().isoformat())
    return {k: len(v) for k, v in cnt.items()}, fechas, fuentes

def _cargar(cities):
    cities = set(cities or [])
    files = sorted(glob.glob(FORECAST_GLOB), key=_fecha_fichero)
    if not files:
        raise ValueError("no hay ficheros Demand-forecast-*.csv en Descargas")
    fc = {}
    for f in files:
        with open(f, encoding="utf-8-sig") as fh:
            for r in csv.DictReader(fh):
                c = _city(r.get("city_code"))
                if cities and c not in cities:
                    continue
                ts = (r.get("slot_started_local_at") or "")[:16]
                if len(ts) < 16:
                    continue
                fc[(c, ts)] = (int(_num(r.get("max_couriers_pilot"))), _num(r.get("final_order_forecast")))
    if not fc:
        raise ValueError("el forecast no tiene datos de " + ", ".join(sorted(cities)))
    fdates = sorted({k[1][:10] for k in fc})
    wk = sorted({dt.date.fromisoformat(d).isocalendar()[:2] for d in fdates})[-MAX_WEEKS:]
    fdates = [d for d in fdates if dt.date.fromisoformat(d).isocalendar()[:2] in wk]
    # ciudad de cada rider (los shift_lv antiguos no traen city_code)
    rc = collections.defaultdict(collections.Counter)
    for f in glob.glob(os.path.join(FLEET_DIR, "*", "*", "rider_lv.csv")):
        with open(f, encoding="utf-8-sig") as fh:
            for r in csv.DictReader(fh):
                if r.get("city_code"):
                    rc[r["rider_id"]][_city(r["city_code"])] += 1
    rcity = {k: v.most_common(1)[0][0] for k, v in rc.items()}
    days = set()
    for d in fdates:
        x = dt.date.fromisoformat(d)
        for k in (-1, 0, 1):
            days.add((x + dt.timedelta(days=k)).isoformat())
    cap = collections.defaultdict(float)
    orders = collections.defaultdict(set)
    seen, real_days = set(), set()
    for d in sorted(days):
        base = os.path.join(FLEET_DIR, d)
        if not os.path.isdir(base):
            continue
        real_days.add(d)
        for f in glob.glob(os.path.join(base, "*", "shift_lv.csv")):
            with open(f, encoding="utf-8-sig") as fh:
                for r in csv.DictReader(fh):
                    a, b = _p(r.get("interval_start")), _p(r.get("interval_finish"))
                    if not a or not b or b <= a:
                        continue
                    key = (r.get("rider_id"), r.get("interval_start"), r.get("interval_finish"))
                    if key in seen:
                        continue
                    seen.add(key)
                    c = _city(r.get("city_code")) or rcity.get(r.get("rider_id"))
                    if not c or (cities and c not in cities):
                        continue
                    t = _slot(a)
                    while t < b:
                        e = t + dt.timedelta(minutes=30)
                        ov = (min(b, e) - max(a, t)).total_seconds()
                        if ov > 0:
                            cap[(c, t.strftime("%Y-%m-%d %H:%M"))] += ov / 1800.0
                        t = e
        for f in glob.glob(os.path.join(base, "*", "delivery_lv.csv")):
            with open(f, encoding="utf-8-sig") as fh:
                for r in csv.DictReader(fh):
                    c = _city(r.get("city_code"))
                    if cities and c not in cities:
                        continue
                    t = _p(r.get("order_created_local_at"))
                    if t:
                        orders[(c, _slot(t).strftime("%Y-%m-%d %H:%M"))].add(r.get("order_id"))
    hor, hor_fechas, hor_fuentes = _leer_horarios(cities)
    out_cities = sorted({k[0] for k in fc})
    out = {"cities": out_cities, "days": {}, "hor": {}, "horSrc": {c: hor_fuentes.get(c, {}) for c in out_cities}}
    last_real = None
    for c in out_cities:
        for d in fdates:
            has = d in real_days and any((c, "%s %02d:%02d" % (d, h, m)) in cap
                                         for h in range(24) for m in (0, 30))
            rows, anyv = [], False
            for h in range(24):
                for m in (0, 30):
                    k = (c, "%s %02d:%02d" % (d, h, m))
                    fR, fO = fc.get(k, (0, 0.0))
                    rows.append([fR, hor.get(k, 0), round(fO, 1),
                                 round(cap.get(k, 0.0), 2) if has else None,
                                 len(orders.get(k, ())) if has else None])
                    anyv = anyv or bool(fR or fO)
            if d in hor_fechas.get(c, ()):
                out["hor"].setdefault(c, []).append(d)
            if anyv or has:
                out["days"].setdefault(c, {})[d] = rows
            if has and (last_real is None or d > last_real):
                last_real = d
    return out, last_real


def construir_html(cities=None, semanas=None, sello=True):
    data, last_real = _cargar(cities)
    data["generated"] = True
    data["lastReal"] = (last_real[8:10] + "/" + last_real[5:7]) if last_real else "—"
    html = HTML.replace("__DATA__", json.dumps(data, ensure_ascii=False, separators=(",", ":")))
    nd = sum(len(v) for v in data["days"].values())
    res = ("forecast vs real · " + str(nd) + " días-ciudad · real hasta " + data["lastReal"]
           + " · " + ", ".join(data["cities"]))
    return html, res


_BTN = '<button data-v="capacidad" aria-pressed="false">Capacidad</button>'
_VIEWS = ["viewSemanal", "viewDiario", "viewLiga", "viewHeat", "viewUtr", "viewNoShow"]


def integrar_en_dashboard(dash_html, cap_html):
    """Añade la pestaña 'Capacidad' al selector Vista del dashboard (en un iframe aislado)."""
    if 'id="viewCap"' in dash_html:
        return dash_html
    ancla = None
    for a in ['<button data-v="noshow" aria-pressed="false">No show</button>',
              '<button data-v="utr" aria-pressed="false">UTR</button>',
              '<button data-v="heat" aria-pressed="false">Mapas de calor</button>',
              '<button data-v="liga" aria-pressed="false">Delivery Race</button>']:
        if a in dash_html:
            ancla = a
            break
    sec_ancla = '<div id="viewSemanal">'
    if not ancla or sec_ancla not in dash_html or "</body>" not in dash_html:
        raise ValueError("la plantilla no tiene el selector de Vista esperado")
    dash_html = dash_html.replace(ancla, ancla + "\n        " + _BTN, 1)
    dash_html = dash_html.replace(sec_ancla,
        '<section id="viewCap" style="display:none"><iframe id="capFrame" title="Capacidad forecast vs real" '
        'style="width:100%;height:1400px;border:0;display:block;background:transparent"></iframe></section>\n  '
        + sec_ancla, 1)
    # "<" -> <: sin etiquetas literales dentro (el perl de publicar_dashboards.sh no puede romperlo)
    src = json.dumps(cap_html, ensure_ascii=False).replace("<", "\\u003c")
    js = ("<script>\n/* ==== Pestaña Capacidad (forecast vs real) ==== */\n(function(){\n"
          "  const CAP_HTML=" + src + ";\n"
          "  const seg=document.getElementById('viewSeg'),sec=document.getElementById('viewCap'),fr=document.getElementById('capFrame');\n"
          "  if(!seg||!sec||!fr) return; let loaded=false;\n"
          "  seg.querySelectorAll('button').forEach(b=>b.addEventListener('click',()=>{\n"
          "    const on=b.dataset.v==='capacidad'; sec.style.display=on?'':'none';\n"
          "    if(on){ seg.querySelectorAll('button').forEach(x=>x.setAttribute('aria-pressed',String(x===b)));\n"
          "      " + json.dumps(_VIEWS) + ".forEach(id=>{const e=document.getElementById(id); if(e) e.style.display='none';});\n"
          "      if(!loaded){ fr.srcdoc=CAP_HTML; loaded=true; } window.scrollTo(0,0); }\n"
          "  }));\n"
          "  window.addEventListener('message',e=>{ if(e.source===fr.contentWindow && e.data && e.data.capH){\n"
          "    fr.style.height=Math.max(700,Math.ceil(e.data.capH)+20)+'px'; } });\n"
          "})();\n</script>\n")
    i = dash_html.rindex("</body>")
    return dash_html[:i] + js + dash_html[i:]


HTML = '<!DOCTYPE html><html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Capacidad · forecast vs real</title>\n<style>\n:root{--bg:#F6F7F9;--surface:#FFFFFF;--line:#E4E7EC;--grid:#EEF0F3;--ink:#14171F;--ink2:#4B5563;--muted:#6B7280;\n--real:#2a78d6;--realfill:rgba(42,120,214,.10);--fc:#eb6834;--short:#d03b3b;--shortfill:rgba(208,59,59,.18);--over:#6B7280;--overfill:rgba(107,114,128,.16);--good:#0a7f0a;--acc:#0E5A6B;--chip:#EEF1F4}\n*{box-sizing:border-box}\nbody{margin:0;background:var(--bg);color:var(--ink);font-family:"Inter",-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;font-size:14px;padding:0 0 24px}\n.wrap{display:flex;flex-direction:column;gap:16px}\nh1{font-size:18px;font-weight:650;margin:0}\nh2{font-size:12px;letter-spacing:.06em;text-transform:uppercase;font-weight:650;margin:0}\n.sub{color:var(--ink2);margin:5px 0 0;max-width:95ch;line-height:1.5;font-size:13px}\n.n,.mono{font-family:ui-monospace,"SF Mono",Menlo,Consolas,monospace;font-variant-numeric:tabular-nums}\n.filters{background:var(--surface);border:1px solid var(--line);border-radius:12px;padding:14px 16px;display:flex;flex-wrap:wrap;gap:16px;align-items:flex-end}\n.fg{display:flex;flex-direction:column;gap:6px}\n.fg[hidden]{display:none}\n.fg>span{font-family:ui-monospace,"SF Mono",Menlo,monospace;font-size:11px;letter-spacing:.07em;text-transform:uppercase;color:var(--muted)}\n.seg{display:inline-flex;flex-wrap:wrap;background:var(--bg);border:1px solid var(--line);border-radius:9px;padding:3px;gap:2px}\n.seg button{font:inherit;font-size:13px;border:0;background:transparent;color:var(--ink2);border-radius:7px;padding:6px 11px;cursor:pointer}\n.seg button:hover{color:var(--ink)}\n.seg button.on{background:var(--acc);color:#fff}\n.seg button:focus-visible{outline:2px solid var(--acc);outline-offset:2px}\n.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px}\n.kpi{background:var(--surface);border:1px solid var(--line);border-radius:12px;padding:12px 14px;display:flex;flex-direction:column;gap:4px}\n.kpi b{font-size:22px;font-weight:650;font-family:ui-monospace,"SF Mono",Menlo,monospace;font-variant-numeric:tabular-nums}\n.kpi span{font-size:12px;color:var(--ink2)}\n.kpi b span{font-size:inherit;color:inherit}\n.kpi b span.bad,.kpi span.bad{color:var(--short)}\n.kpi span.good{color:var(--good)}\n.kpi em{font-style:normal;font-family:ui-monospace,"SF Mono",Menlo,monospace;font-size:11px;letter-spacing:.06em;text-transform:uppercase;color:var(--muted)}\n.bad{color:var(--short)}.good{color:var(--good)}\n.panel{background:var(--surface);border:1px solid var(--line);border-radius:12px;padding:14px;display:flex;flex-direction:column;gap:10px;min-width:0}\n.stack{display:flex;flex-direction:column;gap:14px}\n.two{display:grid;grid-template-columns:repeat(auto-fit,minmax(380px,1fr));gap:14px}\n.ph{display:flex;justify-content:space-between;gap:10px;flex-wrap:wrap;align-items:baseline}\n.ph p{margin:0;color:var(--ink2);font-size:12.5px}\n.legend{display:flex;flex-wrap:wrap;gap:14px;color:var(--ink2);font-size:12px}\n.legend i{display:inline-block;vertical-align:middle;margin-right:6px}\n.l-real{width:16px;border-top:2px solid var(--real)}.l-fc{width:16px;border-top:2px dashed var(--fc)}\n.l-ho{width:16px;border-top:2px dotted var(--over)}\n.l-sh{width:12px;height:9px;background:var(--shortfill)}.l-ov{width:12px;height:9px;background:var(--overfill)}\n.chart{position:relative}\nsvg{display:block;width:100%;height:auto}\nsvg text{fill:var(--muted);font-family:ui-monospace,"SF Mono",Menlo,monospace;font-size:11px}\n.tip{position:absolute;pointer-events:none;background:var(--ink);color:#fff;padding:7px 9px;border-radius:6px;font-size:12px;line-height:1.5;white-space:nowrap;font-family:ui-monospace,"SF Mono",Menlo,monospace;z-index:3}\n.tip[hidden]{display:none}\n.tw{overflow-x:auto}\ntable{border-collapse:collapse;width:100%}\nth,td{padding:8px 10px;text-align:left;border-bottom:1px solid var(--line);white-space:nowrap}\nth{font-family:ui-monospace,"SF Mono",Menlo,monospace;font-size:11px;letter-spacing:.05em;text-transform:uppercase;color:var(--muted);font-weight:500}\ntd.n,th.n{text-align:right}\ntbody tr:last-child td{border-bottom:0}\ntr.click{cursor:pointer}tr.click:hover td,tr.sel td{background:var(--chip)}\n.bar{display:inline-block;height:8px;border-radius:0 4px 4px 0;vertical-align:middle}\n.bar.s{background:var(--short)}.bar.o{background:var(--over)}\n.pill{display:inline-block;padding:1px 8px;border-radius:99px;font-size:12px;font-family:ui-monospace,"SF Mono",Menlo,monospace}\n.pill.s{color:var(--short);background:var(--shortfill)}.pill.o{color:var(--ink2);background:var(--overfill)}\n.empty{color:var(--muted);padding:16px 0}\n.note{color:var(--muted);font-size:12px;line-height:1.55;max-width:120ch;margin:0}\n.banner{background:#FFF7E6;border:1px solid #F5D9A8;border-radius:8px;padding:9px 12px;color:#7A5200;font-size:13px}\n.banner[hidden]{display:none}\n.stamp{font-family:ui-monospace,"SF Mono",Menlo,monospace;font-size:11px;color:var(--muted)}\n\n[data-def]{cursor:help}\n.kpi em[data-def],h2[data-def],.fg>span[data-def],th[data-def]{text-decoration:underline dotted;text-underline-offset:3px}\n#defTip{position:fixed;z-index:50;max-width:300px;background:#14171F;color:#fff;font-size:12px;line-height:1.45;padding:8px 10px;border-radius:7px;pointer-events:none;box-shadow:0 4px 14px rgba(0,0,0,.18);text-transform:none;letter-spacing:0;font-weight:400}\n#defTip[hidden]{display:none}\n.dgrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(360px,1fr));gap:12px}\n.dcard{border:1px solid var(--line);border-radius:10px;padding:10px 10px 4px;display:flex;flex-direction:column;gap:4px;min-width:0}\n.dcard h3{font-size:14px;font-weight:650;margin:0;display:flex;flex-wrap:wrap;gap:6px;align-items:baseline}\n.dcard h3 small{font-weight:400;color:var(--ink2);font-size:12px}\ntfoot td{border-top:1px solid var(--line);border-bottom:0}\n</style></head><body>\n<div class="wrap">\n  <header>\n    <h1>Capacidad · forecast vs real</h1>\n    <p class="sub"><span class="stamp" id="stamp"></span> Riders y pedidos por media hora. <b>Forecast</b>: ficheros Demand-forecast del planificador (<span class="mono">max_couriers_pilot</span> y <span class="mono">final_order_forecast</span>). <b>Real</b>: bucket GCP de la flota (riders conectados según <span class="mono">shift_lv</span>, pedidos según <span class="mono">delivery_lv</span>); <b>Horario</b>: turnos subidos a la fleet tool, para las semanas sin datos reales.</p>\n  </header>\n  <div class="filters">\n    <div class="fg" id="fgCity"><span>Ciudad</span><div class="seg" id="fCity"></div></div>\n    <div class="fg"><span>Semana</span><div class="seg" id="fWeek"></div></div>\n    <div class="fg"><span>Día</span><div class="seg" id="fDay"></div></div>\n  </div>\n  <div class="banner" id="banner" hidden></div>\n  <section class="kpis" id="kpis"></section>\n  <section class="two">\n    <div class="panel"><div class="ph"><h2>Curva de capacidad</h2><p id="capSub"></p></div>\n      <div class="legend" id="capLeg"></div>\n      <div class="chart" id="cCap"></div></div>\n    <div class="panel"><div class="ph"><h2>Curva de demanda</h2><p id="demSub"></p></div>\n      <div class="legend" id="demLeg"></div>\n      <div class="chart" id="cDem"></div></div>\n  </section>\n  <section class="stack">\n    <div class="panel"><div class="ph"><h2 class="bad">Tramos con baja capacidad</h2><p>Horas-rider que faltaron frente al forecast</p></div><div class="tw"><table id="tLow"></table></div></div>\n    <div class="panel"><div class="ph"><h2>Tramos con alta capacidad</h2><p>Horas-rider conectadas por encima del forecast</p></div><div class="tw"><table id="tHigh"></table></div></div>\n  </section>\n  <section class="panel"><div class="ph"><h2>Detalle por día</h2><p>Clic en un día para filtrarlo</p></div><div class="tw"><table id="tDays"></table></div></section>\n  <section class="panel" id="secDow"><div class="ph"><h2 id="dowTitle">Capacidad vs forecast</h2><p id="dowSub"></p></div>\n    <div class="legend" id="dowLeg"></div>\n    <div class="tw"><table id="tDow"></table></div>\n    <div class="dgrid" id="dowGrid"></div></section>\n  <p class="note">Cálculo por media hora y ciudad: baja capacidad = forecast − conectados cuando es positivo; alta capacidad = conectados − forecast cuando es positivo. Se suman en horas-rider (media hora = 0,5 h) sin compensar ciudades ni franjas entre sí. Riders conectados = tiempo conectado dentro de la media hora ÷ 30 min, así que un rider que entra a mitad cuenta 0,5. Cuando el filtro abarca varios días, las curvas muestran la media por día. Cada franja usa el último fichero de forecast emitido que la cubre. Los días sin datos reales todavía (semana en curso o futura) se comparan con el horario subido a la fleet tool (ficheros HORARIO de Descargas; por ciudad y semana, el último fichero completo de reservas). Sin horario subido, solo se muestra el forecast. Pedidos reales = pedidos de la flota MushDrink por hora de creación.</p>\n</div>\n<script>\nconst DATA=__DATA__;\nif(DATA.cities.length<2)document.getElementById(\'fgCity\').hidden=true;\nif(DATA.generated)document.getElementById(\'stamp\').textContent=\'Datos reales hasta \'+DATA.lastReal+\' · \';\nconst CITIES=DATA.cities;\nconst DOW=[\'Dom\',\'Lun\',\'Mar\',\'Mié\',\'Jue\',\'Vie\',\'Sáb\'];\nconst pd=d=>new Date(d+\'T12:00:00\');\nfunction isoWeek(d){const t=pd(d);const day=(t.getDay()+6)%7;t.setDate(t.getDate()-day+3);const f=new Date(t.getFullYear(),0,4);return 1+Math.round(((t-f)/864e5-3+((f.getDay()+6)%7))/7);}\nconst ddmm=d=>d.slice(8,10)+\'/\'+d.slice(5,7);\nconst dlbl=d=>DOW[pd(d).getDay()]+\' \'+ddmm(d);\nconst nf=(v,dec=0)=>v==null||isNaN(v)?\'—\':v.toLocaleString(\'es-ES\',{minimumFractionDigits:dec,maximumFractionDigits:dec});\nconst f1=v=>nf(v,Math.abs(v)<100&&v%1?1:0);\nconst hm=i=>String(Math.floor(i/2)).padStart(2,\'0\')+\':\'+(i%2?\'30\':\'00\');\n// índice de fechas\nconst allDates=[...new Set(CITIES.flatMap(c=>Object.keys(DATA.days[c]||{})))].sort();\nconst weeks={};allDates.forEach(d=>{const w=isoWeek(d);(weeks[w]=weeks[w]||[]).push(d);});\nconst WK=Object.keys(weeks).map(Number).sort((a,b)=>a-b);\nconst hasReal=(c,d)=>{const r=DATA.days[c]&&DATA.days[c][d];return !!r&&r.some(x=>x[3]!=null);};\nconst S={city:\'ALL\',week:null,day:\'ALL\'};\n// semana por defecto: la última con datos reales\nS.week=[...WK].reverse().find(w=>weeks[w].some(d=>CITIES.some(c=>hasReal(c,d))))||WK[WK.length-1];\nfunction seg(id,opts,val,on){const el=document.getElementById(id);el.innerHTML=opts.map(o=>`<button data-v="${o.v}" class="${String(o.v)===String(val)?\'on\':\'\'}" ${o.dis?\'disabled\':\'\'} title="${o.t||\'\'}">${o.l}</button>`).join(\'\');el.onclick=e=>{const b=e.target.closest(\'button\');if(!b||b.disabled)return;on(b.dataset.v);};}\nfunction drawFilters(){\n  seg(\'fCity\',[{v:\'ALL\',l:\'Todas\'}].concat(CITIES.map(c=>({v:c,l:c}))),S.city,v=>{S.city=v;render();});\n  seg(\'fWeek\',WK.map(w=>{const ds=weeks[w];return {v:w,l:\'W\'+w,t:ddmm(ds[0])+\'–\'+ddmm(ds[ds.length-1])};}),S.week,v=>{S.week=+v;S.day=\'ALL\';render();});\n  const ds=weeks[S.week]||[];\n  seg(\'fDay\',[{v:\'ALL\',l:\'Semana\'}].concat(ds.map(d=>({v:d,l:dlbl(d)}))),S.day,v=>{S.day=v;render();});\n}\n// agrega: devuelve por slot sumas sobre ciudades y días + métricas\nconst HOR={};Object.entries(DATA.hor||{}).forEach(([c,ds])=>HOR[c]=new Set(ds));\nfunction aggregate(){\n  const cs=S.city===\'ALL\'?CITIES:[S.city];\n  const ds=S.day===\'ALL\'?(weeks[S.week]||[]):[S.day];\n  const slot=[...Array(48)].map(()=>({fR:0,aR:0,hR:0,fO:0,aO:0,sh:0,ov:0,shDays:0}));\n  const byDay={};let anyReal=false,anyFc=false,anyRl=false,anyHorCmp=false,anyOrd=false,anyHorLine=false;\n  let nr=0,nOrd=0,nHd=0;\n  ds.forEach(d=>{const bd=byDay[d]={fR:0,fRc:0,aR:0,fO:0,fOr:0,aO:0,sh:0,ov:0,real:false,rl:false,hor:false,ord:false,worst:null};\n    const dayShort=Array(48).fill(0);let dayHor=false;\n    cs.forEach(c=>{const r=DATA.days[c]&&DATA.days[c][d];if(!r)return;\n      const real=r.some(x=>x[3]!=null), hor=!!(HOR[c]&&HOR[c].has(d));\n      const cmp=real?\'real\':(hor?\'hor\':null);\n      if(cmp){bd.real=true;anyReal=true;if(real){bd.rl=true;anyRl=true;}else{bd.hor=true;anyHorCmp=true;}}\n      if(real){bd.ord=true;anyOrd=true;}\n      if(hor)dayHor=true;\n      r.forEach((x,i)=>{const s=slot[i];const [fR,hR,fO,aR,aO]=x;\n        s.fR+=fR;s.fO+=fO;bd.fR+=fR/2;bd.fO+=fO;if(fR||fO)anyFc=true;\n        if(hor)s.hR+=hR;\n        if(cmp){const v=real?aR:hR;s.aR+=v;bd.aR+=v/2;bd.fRc+=fR/2;\n          const sh=Math.max(fR-v,0)/2,ov=Math.max(v-fR,0)/2;s.sh+=sh;s.ov+=ov;bd.sh+=sh;bd.ov+=ov;dayShort[i]+=sh;}\n        if(real){s.aO+=aO;bd.aO+=aO;bd.fOr+=fO;}\n      });});\n    if(bd.real)nr++; if(bd.ord)nOrd++; if(dayHor){nHd++;anyHorLine=true;}\n    dayShort.forEach((v,i)=>{if(v>0.25)slot[i].shDays++;});\n    let wi=-1,wv=0;dayShort.forEach((v,i)=>{if(v>wv){wv=v;wi=i;}});bd.worst=wi>=0?[wi,wv]:null;\n  });\n  const nd=ds.length;\n  const lab=anyRl&&anyHorCmp?\'real/horario\':anyHorCmp?\'horario\':\'real\';\n  return {cs,ds,slot,byDay,nd,nr,nOrd,nHd,anyReal,anyFc,anyRl,anyHorCmp,anyOrd,anyHorLine,lab};\n}\nconst W=560,H=250,L=34,R=10,T=12,B=26;\nconst NS=\'http://www.w3.org/2000/svg\';\nfunction el(t,a,p){const e=document.createElementNS(NS,t);for(const k in a)e.setAttribute(k,a[k]);p&&p.appendChild(e);return e;}\nfunction niceStep(v){const raw=v/4;const p=Math.pow(10,Math.floor(Math.log10(raw)));const m=[1,2,5,10].find(m=>m*p>=raw);return Math.max(1,m*p);}\nfunction chart(box,{fc,re,ho,i0,i1,fmt,unit,shade,reLab,ymax}){\n  box.innerHTML=\'\';const tip=document.createElement(\'div\');tip.className=\'tip\';tip.hidden=true;\n  const n=i1-i0+1;const dmax=Math.max(1,...fc.slice(i0,i1+1),...(re?re.slice(i0,i1+1):[0]),...(ho?ho.slice(i0,i1+1):[0]));const dm=Math.max(dmax,ymax||0);const st=niceStep(dm);const vmax=Math.ceil(dm/st)*st;\n  const svg=el(\'svg\',{viewBox:`0 0 ${W} ${H}`,role:\'img\',\'aria-label\':unit+\' por media hora\'});box.append(svg,tip);\n  const sw=(W-L-R)/n,X=i=>L+(i-i0)*sw,Y=v=>T+(H-T-B)*(1-v/vmax);\n  const ticks=[];for(let v=0;v<=vmax+1e-9;v+=st)ticks.push(v);\n  ticks.forEach(v=>{el(\'line\',{x1:L,x2:W-R,y1:Y(v),y2:Y(v),stroke:\'var(--grid)\'},svg);el(\'text\',{x:L-6,y:Y(v)+4,\'text-anchor\':\'end\'},svg).textContent=fmt(v);});\n  const every=n>28?4:2;for(let i=i0;i<=i1+1;i++){if(i%every===0){el(\'text\',{x:X(i),y:H-8,\'text-anchor\':\'middle\'},svg).textContent=i===48?\'24:00\':hm(i%48);}}\n  const step=a=>{let p=\'\';for(let i=i0;i<=i1;i++){const y=Y(a[i]);p+=(i===i0?`M${X(i)},${y}`:`L${X(i)},${y}`)+`L${X(i+1)},${y}`;}return p;};\n  if(re){\n    el(\'path\',{d:step(re)+`L${X(i1+1)},${Y(0)}L${X(i0)},${Y(0)}Z`,fill:\'var(--realfill)\'},svg);\n    if(shade)for(let i=i0;i<=i1;i++){const a=fc[i],b=re[i];if(Math.abs(a-b)<0.05)continue;el(\'rect\',{x:X(i),y:Y(Math.max(a,b)),width:sw,height:Math.abs(Y(a)-Y(b)),fill:a>b?\'var(--shortfill)\':\'var(--overfill)\'},svg);}\n    el(\'path\',{d:step(re),fill:\'none\',stroke:\'var(--real)\',\'stroke-width\':2,\'stroke-linejoin\':\'round\'},svg);\n  }\n  if(ho)el(\'path\',{d:step(ho),fill:\'none\',stroke:\'var(--over)\',\'stroke-width\':1.6,\'stroke-dasharray\':\'2 3\',\'stroke-linejoin\':\'round\'},svg);\n  el(\'path\',{d:step(fc),fill:\'none\',stroke:\'var(--fc)\',\'stroke-width\':2,\'stroke-dasharray\':\'5 3\',\'stroke-linejoin\':\'round\'},svg);\n  const hl=el(\'rect\',{x:0,y:T,width:sw,height:H-T-B,fill:\'var(--ink)\',opacity:0},svg);\n  const hit=el(\'rect\',{x:L,y:0,width:W-L-R,height:H-B,fill:\'transparent\'},svg);\n  hit.addEventListener(\'pointermove\',ev=>{const bb=svg.getBoundingClientRect();const sx=(ev.clientX-bb.left)/bb.width*W;const i=Math.max(i0,Math.min(i1,i0+Math.floor((sx-L)/sw)));\n    hl.setAttribute(\'x\',X(i));hl.setAttribute(\'opacity\',.06);\n    const a=fc[i],b=re?re[i]:null;let t=`${hm(i)}–${hm((i+1)%48)}<br>Forecast ${fmt(a,1)} ${unit}`;\n    if(ho)t+=`<br>Horario ${fmt(ho[i],1)} ${unit}`;\n    if(re){t+=`<br>${reLab||\'Real\'} ${fmt(b,1)} ${unit}`;const d=b-a;if(Math.abs(d)>=0.05)t+=`<br>${d<0?\'<b>\':\'\'}${d>0?\'+\':\'−\'}${fmt(Math.abs(d),1)} ${unit}${d<0?\'</b>\':\'\'}`;}\n    tip.innerHTML=t;tip.hidden=false;const px=(X(i)+sw/2)/W*bb.width;tip.style.left=Math.min(Math.max(px-70,0),bb.width-150)+\'px\';tip.style.top=\'4px\';});\n  hit.addEventListener(\'pointerleave\',()=>{tip.hidden=true;hl.setAttribute(\'opacity\',0);});\n}\n\nfunction renderDow(){\n  const save=S.day;S.day=\'ALL\';\n  const cs=S.city===\'ALL\'?CITIES:[S.city];const ds=weeks[S.week]||[];S.day=save;\n  const name=S.city===\'ALL\'?(CITIES.length===1?CITIES[0]:\'Todas\'):S.city;\n  const t=document.getElementById(\'dowTitle\');t.textContent=\'Capacidad vs forecast · \'+name;\n  t.dataset.def=\'Por cada día de la semana elegida: riders forecast frente a riders conectados (días con datos reales) o con turno en el horario subido (días sin real todavía), por media hora. Mismo formato que el informe «Capacidad vs forecast · SAB».\';t.tabIndex=0;\n  const days=ds.map(d=>{const fc=Array(48).fill(0),cap=Array(48).fill(0);let src=null,has=false;\n    cs.forEach(c=>{const r=DATA.days[c]&&DATA.days[c][d];if(!r)return;const real=r.some(x=>x[3]!=null),hor=!!(HOR[c]&&HOR[c].has(d));\n      const cmp=real?\'real\':hor?\'hor\':null;if(!cmp)return;has=true;src=src&&src!==cmp?\'mix\':cmp;\n      r.forEach((x,i)=>{fc[i]+=x[0];cap[i]+=real?x[3]:x[1];});});\n    if(!has)cs.forEach(c=>{const r=DATA.days[c]&&DATA.days[c][d];if(r)r.forEach((x,i)=>{fc[i]+=x[0];});});\n    let f=0,k=0,sh=0,ov=0,pf=0,pc=0;fc.forEach((v,i)=>{f+=v/2;pf=Math.max(pf,v);if(has){k+=cap[i]/2;sh+=Math.max(v-cap[i],0)/2;ov+=Math.max(cap[i]-v,0)/2;pc=Math.max(pc,cap[i]);}});\n    return {d,fc,cap,has,src,f,k,sh,ov,pf,pc};});\n  const any=days.some(x=>x.has),srcs=new Set(days.filter(x=>x.has).map(x=>x.src));\n  const capName=srcs.has(\'hor\')&&(srcs.has(\'real\')||srcs.has(\'mix\'))?\'Capacidad (real u horario)\':srcs.has(\'hor\')?\'Capacidad (horario)\':\'Capacidad (conectados)\';\n  document.getElementById(\'dowSub\').textContent=\'W\'+S.week+\' · \'+ddmm(ds[0]||\'\')+\'–\'+ddmm(ds[ds.length-1]||\'\')+(any?\' · \'+capName.toLowerCase():\' · sin real ni horario\');\n  document.getElementById(\'dowLeg\').innerHTML=(any?`<span><i class="l-real"></i>${capName}</span>`:\'\')+\'<span><i class="l-fc"></i>Forecast</span>\'+(any?\'<span><i class="l-sh"></i>Falta capacidad (forecast &gt; capacidad)</span><span><i class="l-ov"></i>Sobra capacidad</span>\':\'\');\n  const T=days.reduce((a,x)=>{a.f+=x.f;if(x.has){a.fk+=x.f;a.k+=x.k;a.sh+=x.sh;a.ov+=x.ov;}return a;},{f:0,fk:0,k:0,sh:0,ov:0});\n  const sg=v=>(v>=0?\'+\':\'−\')+f1(Math.abs(v));\n  const srcTag=x=>x.src===\'hor\'&&srcs.size>1?\' <span class="pill o">horario</span>\':\'\';\n  document.getElementById(\'tDow\').innerHTML=\'<thead><tr><th>Día</th><th class="n">Forecast h</th><th class="n">Capacidad h</th><th class="n">Diferencia</th><th class="n">Faltan h</th><th class="n">Sobran h</th><th class="n">Pico forecast</th><th class="n">Pico capacidad</th></tr></thead><tbody>\'+\n    days.map(x=>`<tr><td>${dlbl(x.d)}${srcTag(x)}</td><td class="n">${f1(x.f)}</td><td class="n">${x.has?f1(x.k):\'—\'}</td><td class="n">${x.has?sg(x.k-x.f):\'—\'}</td><td class="n">${x.has?(x.sh>=0.25?`<span class="pill s">−${f1(x.sh)} h</span>`:\'0\'):\'—\'}</td><td class="n">${x.has?f1(x.ov):\'—\'}</td><td class="n">${x.pf}</td><td class="n">${x.has?nf(x.pc,x.pc%1?1:0):\'—\'}</td></tr>`).join(\'\')+\n    `</tbody><tfoot><tr><td><b>Semana</b></td><td class="n"><b>${f1(T.f)}</b></td><td class="n"><b>${any?f1(T.k):\'—\'}</b></td><td class="n"><b>${any?sg(T.k-T.fk):\'—\'}</b></td><td class="n">${any?`<span class="pill s">−${f1(T.sh)} h</span>`:\'—\'}</td><td class="n"><b>${any?f1(T.ov):\'—\'}</b></td><td></td><td></td></tr></tfoot>`;\n  const g=document.getElementById(\'dowGrid\');g.innerHTML=\'\';\n  let i0=47,i1=0;days.forEach(x=>x.fc.forEach((v,i)=>{if(v||x.cap[i]>0.05){i0=Math.min(i0,i);i1=Math.max(i1,i);}}));if(i0>i1){i0=20;i1=47;}\n  const ym=Math.max(1,...days.flatMap(x=>x.fc.concat(x.has?x.cap:[])));\n  days.forEach(x=>{const c=document.createElement(\'div\');c.className=\'dcard\';\n    c.innerHTML=`<h3>${dlbl(x.d)} <small>forecast ${f1(x.f)} h${x.has?` · capacidad ${f1(x.k)} h${x.sh>=0.25?` · <span class="bad">faltan ${f1(x.sh)} h</span>`:\'\'}`:\'\'}</small></h3><div class="chart"></div>`;\n    g.appendChild(c);\n    chart(c.querySelector(\'.chart\'),{fc:x.fc,re:x.has?x.cap:null,i0,i1,fmt:(v,d)=>nf(v,d||0),unit:\'riders\',shade:true,reLab:x.src===\'hor\'?\'Horario\':\'Capacidad\',ymax:ym});});\n}\nfunction render(){\n  drawFilters();\n  const A=aggregate(),{slot,nd,nr,lab}=A;\n  const nDiv=Math.max(nd,1),nDivR=Math.max(nr,1),nDivO=Math.max(A.nOrd,1),nDivH=Math.max(A.nHd,1);\n  const fcR=slot.map(s=>s.fR/nDiv),reR=slot.map(s=>s.aR/nDivR),hoR=slot.map(s=>s.hR/nDivH),fcO=slot.map(s=>s.fO/nDiv),reO=slot.map(s=>s.aO/nDivO);\n  let i0=47,i1=0;slot.forEach((s,i)=>{if(s.fR||s.aR>0.05||s.hR||s.fO||s.aO){i0=Math.min(i0,i);i1=Math.max(i1,i);}});if(i0>i1){i0=20;i1=47;}\n  i0=Math.max(0,i0-1);i1=Math.min(47,i1+1);\n  const tot=Object.values(A.byDay).reduce((a,b)=>{[\'fR\',\'fRc\',\'aR\',\'fO\',\'fOr\',\'aO\',\'sh\',\'ov\'].forEach(k=>a[k]+=b[k]);return a;},{fR:0,fRc:0,aR:0,fO:0,fOr:0,aO:0,sh:0,ov:0});\n  const ban=document.getElementById(\'banner\');\n  const nHc=Object.values(A.byDay).filter(b=>b.hor&&!b.rl).length;\n  if(!A.anyReal){ban.hidden=false;ban.textContent=\'Sin datos reales ni horario subido para este periodo: se muestra solo el forecast.\';}\n  else if(A.anyHorCmp&&!A.anyRl){ban.hidden=false;ban.textContent=\'Todavía no hay datos reales: se compara el forecast con el horario subido a la fleet tool (riders con turno reservado)\'+(S.city===\'ALL\'&&A.cs.length>1?\'. Solo las ciudades con horario subido entran en la comparación.\':\'.\');}\n  else if(A.anyHorCmp){ban.hidden=false;ban.textContent=`Días con datos reales: ${nr-nHc}; días sin real todavía (comparados con el horario subido): ${nHc}.`;}\n  else if(nr<nd){ban.hidden=false;ban.textContent=`Datos reales de ${nr} de ${nd} días; la comparación usa solo esos días.`;}else ban.hidden=true;\n  const cov=tot.fRc?tot.aR/tot.fRc:null,dO=tot.fOr?tot.aO/tot.fOr-1:null;\n  const scope=(S.city===\'ALL\'?(CITIES.length===1?CITIES[0]:\'Todas las ciudades\'):S.city)+\' · \'+(S.day===\'ALL\'?\'W\'+S.week:dlbl(S.day));\n  const capT=lab===\'horario\'?\'Horas-rider en horario\':lab===\'real\'?\'Horas-rider conectadas\':\'Horas-rider conectadas / horario\';\n  document.getElementById(\'kpis\').innerHTML=[\n    [\'Horas-rider forecast\',f1(tot.fR)+\' h\',scope],\n    [\'Capacidad vs forecast\',A.anyReal?`<span class="${cov<0.97?\'bad\':\'good\'}">${nf(cov*100,1)} %</span>`:\'—\',A.anyReal?`cubierto por franja: ${nf((1-tot.sh/tot.fRc)*100,1)} %`:\'sin real ni horario\'],\n    [capT,A.anyReal?f1(tot.aR)+\' h\':\'—\',A.anyReal?`${tot.aR-tot.fRc>=0?\'+\':\'−\'}${f1(Math.abs(tot.aR-tot.fRc))} h vs forecast`:\'sin real ni horario\'],\n    [\'Baja capacidad\',A.anyReal?`<span class="bad">${f1(tot.sh)} h</span>`:\'—\',\'horas-rider que faltan\'],\n    [\'Alta capacidad\',A.anyReal?f1(tot.ov)+\' h\':\'—\',\'horas-rider por encima\'],\n    [\'Pedidos forecast\',nf(tot.fO),\'\'],\n    [\'Pedidos reales\',A.anyOrd?nf(tot.aO):\'—\',A.anyOrd?`${dO>=0?\'+\':\'−\'}${nf(Math.abs(dO*100),1)} % vs forecast`:\'sin real\'],\n  ].map(([e,b,s])=>`<div class="kpi"><em>${e}</em><b>${b}</b><span>${s}</span></div>`).join(\'\');\n  const per=S.day===\'ALL\'?`media por día · ${nd} días`:dlbl(S.day);\n  document.getElementById(\'capSub\').textContent=\'Riders por media hora · \'+per;\n  document.getElementById(\'demSub\').textContent=\'Pedidos por media hora · \'+per;\n  const reLab=lab===\'horario\'?\'Riders con turno (horario)\':lab===\'real\'?\'Riders conectados (real)\':\'Riders conectados o con turno\';\n  const showHo=A.anyHorLine&&A.anyRl;\n  document.getElementById(\'capLeg\').innerHTML=(A.anyReal?`<span><i class="l-real"></i>${reLab}</span>`:\'\')+`<span><i class="l-fc"></i>Riders forecast</span>`+(showHo?`<span><i class="l-ho"></i>Horario subido</span>`:\'\')+(A.anyReal?`<span><i class="l-sh"></i>Baja capacidad</span><span><i class="l-ov"></i>Alta capacidad</span>`:\'\');\n  document.getElementById(\'demLeg\').innerHTML=(A.anyOrd?`<span><i class="l-real"></i>Pedidos reales</span>`:\'\')+`<span><i class="l-fc"></i>Pedidos forecast</span>`;\n  chart(document.getElementById(\'cCap\'),{fc:fcR,re:A.anyReal?reR:null,ho:showHo?hoR:null,i0,i1,fmt:(v,d)=>nf(v,d||0),unit:\'riders\',shade:true,reLab:lab===\'horario\'?\'Horario\':lab===\'real\'?\'Real\':\'Real/horario\'});\n  chart(document.getElementById(\'cDem\'),{fc:fcO,re:A.anyOrd?reO:null,i0,i1,fmt:(v,d)=>nf(v,d||0),unit:\'pedidos\',shade:false});\n  const bands=[];for(let h=0;h<24;h++){const a=slot[2*h],b=slot[2*h+1];const x={h,sh:a.sh+b.sh,ov:a.ov+b.ov,fR:(a.fR+b.fR)/2/nDiv,aR:(a.aR+b.aR)/2/nDivR,fO:a.fO+b.fO,aO:a.aO+b.aO,days:Math.max(a.shDays,b.shDays)};if(x.fR||x.aR)bands.push(x);}\n  const band=h=>`${String(h).padStart(2,\'0\')}:00–${String((h+1)%24).padStart(2,\'0\')}:00`;\n  const mx=Math.max(0.01,...bands.map(b=>Math.max(b.sh,b.ov)));\n  const rTh=lab===\'horario\'?\'Riders horario\':lab===\'real\'?\'Riders real\':\'Riders real/horario\';\n  const tbl=(id,key,cls,empty)=>{const rs=bands.filter(b=>b[key]>=0.25).sort((a,b)=>b[key]-a[key]).slice(0,8);\n    document.getElementById(id).innerHTML=!A.anyReal?`<tbody><tr><td class="empty">Sin datos reales ni horario en este periodo.</td></tr></tbody>`:!rs.length?`<tbody><tr><td class="empty">${empty}</td></tr></tbody>`:\n    `<thead><tr><th>Tramo</th><th class="n">${key===\'sh\'?\'Faltan\':\'Sobran\'}</th><th class="n">Riders fc</th><th class="n">${rTh}</th>${S.day===\'ALL\'&&key===\'sh\'?\'<th class="n">Días</th>\':\'\'}<th class="n">Pedidos fc</th>${A.anyOrd?\'<th class="n">Pedidos real</th>\':\'\'}</tr></thead><tbody>`+\n    rs.map(b=>`<tr><td class="mono">${band(b.h)}</td><td class="n"><span class="bar ${cls}" style="width:${Math.max(3,Math.round(b[key]/mx*60))}px;margin:0 8px 0 0"></span><span class="pill ${cls}">${f1(b[key])} h</span></td><td class="n">${nf(b.fR,1)}</td><td class="n">${nf(b.aR,1)}</td>${S.day===\'ALL\'&&key===\'sh\'?`<td class="n">${b.days} de ${nr}</td>`:\'\'}<td class="n">${nf(b.fO)}</td>${A.anyOrd?`<td class="n">${nf(b.aO)}</td>`:\'\'}</tr>`).join(\'\')+\'</tbody>\';};\n  tbl(\'tLow\',\'sh\',\'s\',\'Ningún tramo con déficit relevante.\');tbl(\'tHigh\',\'ov\',\'o\',\'Ningún tramo con exceso relevante.\');\n  const save=S.day;S.day=\'ALL\';const W2=aggregate();S.day=save;\n  const cTh=W2.anyHorCmp&&W2.anyRl?\'Real / horario h\':W2.anyHorCmp?\'Horario h\':\'Conectadas h\';\n  document.getElementById(\'tDays\').innerHTML=`<thead><tr><th>Día</th><th class="n">Forecast h</th><th class="n">${cTh}</th><th class="n">Cobertura</th><th class="n">Faltan h</th><th class="n">Sobran h</th><th>Peor media hora</th><th class="n">Pedidos fc</th><th class="n">Pedidos real</th></tr></thead><tbody>`+\n   W2.ds.map(d=>{const b=W2.byDay[d];const c=b.real&&b.fRc?b.aR/b.fRc:null;const tag=b.hor&&!b.rl&&W2.anyRl?\' <span class="pill o">horario</span>\':\'\';\n    return `<tr class="click ${S.day===d?\'sel\':\'\'}" data-d="${d}"><td>${dlbl(d)}${S.day===d?\' ◂\':\'\'}</td><td class="n">${f1(b.fR)}</td><td class="n">${b.real?f1(b.aR)+tag:\'—\'}</td><td class="n ${c!=null&&c<0.97?\'bad\':\'\'}">${c!=null?nf(c*100,1)+\' %\':\'—\'}</td><td class="n">${b.real&&b.sh>=0.25?`<span class="pill s">${f1(b.sh)}</span>`:b.real?\'0\':\'—\'}</td><td class="n">${b.real?f1(b.ov):\'—\'}</td><td class="mono">${b.worst&&b.worst[1]>=0.25?hm(b.worst[0])+\' · −\'+f1(b.worst[1]*2)+\' riders\':\'—\'}</td><td class="n">${nf(b.fO)}</td><td class="n">${b.ord?nf(b.aO):\'—\'}</td></tr>`;}).join(\'\')+\'</tbody>\';\n  document.querySelectorAll(\'#tDays tr[data-d]\').forEach(tr=>tr.onclick=()=>{S.day=S.day===tr.dataset.d?\'ALL\':tr.dataset.d;render();});\n  renderDow();\n  applyDefs();\n}\n/* ==== definiciones al pasar el ratón ==== */\nconst DEF={"Ciudad": "Ciudad o nodo de la flota. «Todas» suma las ciudades sin compensar el déficit de una con el exceso de otra.", "Semana": "Semana ISO, de lunes a domingo. Solo aparecen las semanas que tienen fichero Demand-forecast.", "Día": "«Semana» muestra la media diaria de la semana elegida; un día concreto muestra solo ese día.", "Horas-rider forecast": "Riders que pide el planificador (max_couriers_pilot) en cada media hora × 0,5 h, sumado en el periodo.", "Horas-rider conectadas": "Tiempo real que los riders estuvieron conectados (shift_lv del bucket GCP). El % compara con el forecast de los mismos días con datos reales.", "Baja capacidad": "Horas-rider que faltan: en cada media hora y ciudad, forecast − conectados (o riders con turno en el horario, si aún no hay real) cuando el forecast es mayor. No se compensa con los excesos de otras franjas.", "Alta capacidad": "Horas-rider por encima de lo previsto: en cada media hora y ciudad, conectados (u horario) − forecast cuando hay más riders que los pedidos por el planificador.", "Pedidos forecast": "Pedidos previstos para la media hora (final_order_forecast).", "Pedidos reales": "Pedidos distintos creados en la media hora y atendidos por la flota.", "Curva de capacidad": "Riders por media hora: forecast del planificador frente a riders realmente conectados. En vista semana es la media por día. Rojo = faltan riders; gris = sobran.", "Curva de demanda": "Pedidos por media hora: forecast frente a pedidos reales creados. En vista semana es la media por día.", "Tramos con baja capacidad": "Franjas de 1 hora ordenadas por horas-rider que faltaron frente al forecast (suma de días y ciudades del filtro).", "Tramos con alta capacidad": "Franjas de 1 hora ordenadas por horas-rider conectadas por encima del forecast (suma de días y ciudades del filtro).", "Detalle por día": "Resumen de cada día de la semana elegida. Clic en una fila para filtrar ese día; otro clic vuelve a la semana.", "Riders conectados (real)": "Riders conectados en la media hora: minutos conectados ÷ 30, así que quien conecta a mitad de franja cuenta 0,5.", "Riders forecast": "Riders que el planificador pide para esa media hora (max_couriers_pilot).", "Tramo": "Franja de una hora del día.", "Faltan": "Horas-rider que faltaron en el tramo frente al forecast, sumando los días y ciudades del filtro.", "Sobran": "Horas-rider conectadas por encima del forecast en el tramo, sumando días y ciudades.", "Riders fc": "Media de riders pedidos por el forecast en cada media hora del tramo (por día).", "Riders real": "Media de riders conectados en cada media hora del tramo (por día).", "Días": "Días de la semana en los que ese tramo tuvo déficit (al menos 0,5 riders de menos en alguna de sus medias horas).", "Pedidos fc": "Pedidos previstos en el tramo (o en el día), sumando días y ciudades.", "Pedidos real": "Pedidos reales creados en el tramo (o en el día), sumando días y ciudades.", "Forecast h": "Horas-rider previstas por el planificador ese día.", "Conectadas h": "Horas-rider realmente conectadas ese día.", "Cobertura": "Horas conectadas (u horario) ÷ horas forecast de las mismas ciudades y días. En rojo si queda por debajo del 97 %.", "Faltan h": "Horas-rider que faltaron ese día, sumando cada media hora con déficit.", "Sobran h": "Horas-rider por encima del forecast ese día, sumando cada media hora con exceso.", "Peor media hora": "Media hora del día con más riders de menos frente al forecast (sumando ciudades).", "Horas-rider en horario": "Horas con turno reservado en el horario subido a la fleet tool (ficheros HORARIO de Descargas). Se usa en los días que aún no tienen datos reales.", "Horas-rider conectadas / horario": "Horas conectadas en los días con datos reales y horas con turno reservado (horario subido) en los días que aún no los tienen.", "Riders con turno (horario)": "Riders con turno reservado en esa media hora según el horario subido a la fleet tool.", "Riders conectados o con turno": "Conectados reales en los días con datos; riders con turno en el horario subido en los días sin datos todavía.", "Horario subido": "Riders con turno reservado en el horario subido a la fleet tool, como referencia frente a lo que se conectó de verdad.", "Riders horario": "Media de riders con turno reservado en cada media hora del tramo (por día), según el horario subido.", "Riders real/horario": "Media de riders conectados (días con real) o con turno en el horario (días sin real) en cada media hora del tramo.", "Horario h": "Horas-rider con turno reservado ese día en el horario subido a la fleet tool.", "Real / horario h": "Horas conectadas en días con datos reales; horas con turno del horario subido en los días marcados «horario».", "Capacidad h": "Horas-rider de capacidad del día: conectadas si ya hay datos reales; con turno en el horario subido si todavía no.", "Diferencia": "Capacidad h − forecast h del día (o de la semana). Negativo = faltan horas en total, aunque algunas franjas sobren.", "Pico forecast": "Máximo de riders que pide el forecast en una media hora del día.", "Pico capacidad": "Máximo de riders (conectados u horario) en una media hora del día.", "Forecast": "Riders que pide el planificador (max_couriers_pilot) en cada media hora.", "Falta capacidad (forecast > capacidad)": "Medias horas en las que el forecast pide más riders de los que hay (conectados u horario).", "Sobra capacidad": "Medias horas con más riders de los que pide el forecast.", "Capacidad (horario)": "Riders con turno reservado en el horario subido a la fleet tool.", "Capacidad (conectados)": "Riders realmente conectados en la media hora (shift_lv del bucket GCP).", "Capacidad (real u horario)": "Conectados en los días con datos reales; horario subido en los días sin real todavía."};\nconst KDEF={"Horas-rider forecast": "Riders que pide el planificador (max_couriers_pilot) en cada media hora × 0,5 h, sumado en el periodo.", "Horas-rider conectadas": "Tiempo real que los riders estuvieron conectados (shift_lv del bucket GCP). El % compara con el forecast de los mismos días con datos reales.", "Baja capacidad": "Horas-rider que faltan: en cada media hora y ciudad, forecast − conectados (o riders con turno en el horario, si aún no hay real) cuando el forecast es mayor. No se compensa con los excesos de otras franjas.", "Alta capacidad": "Horas-rider por encima de lo previsto: en cada media hora y ciudad, conectados (u horario) − forecast cuando hay más riders que los pedidos por el planificador.", "Pedidos forecast": "Pedidos previstos para la media hora (final_order_forecast).", "Pedidos reales": "Pedidos distintos creados en la media hora y atendidos por la flota.", "Horas-rider en horario": "Horas con turno reservado en el horario subido a la fleet tool (ficheros HORARIO de Descargas). Se usa en los días que aún no tienen datos reales.", "Horas-rider conectadas / horario": "Horas conectadas en los días con datos reales y horas con turno reservado (horario subido) en los días que aún no los tienen.", "Capacidad vs forecast": "Capacidad actual ÷ forecast: horas-rider conectadas (o con turno en el horario subido, si aún no hay real) entre las horas-rider que pide el forecast, en las mismas ciudades y días. Debajo, «cubierto por franja»: % del forecast que queda cubierto media hora a media hora (forecast − horas que faltan) ÷ forecast; no deja que el exceso de una franja tape el déficit de otra."};\nconst LDEF={"Pedidos reales":"Pedidos distintos creados en la media hora y atendidos por la flota.","Pedidos forecast":"Pedidos previstos para la media hora (final_order_forecast)."};\nfunction applyDefs(){\n  const put=(el,d)=>{if(d&&!el.dataset.def){el.dataset.def=d;el.tabIndex=0;}};\n  document.querySelectorAll(\'.kpi em\').forEach(e=>put(e,KDEF[e.textContent.trim()]));\n  document.querySelectorAll(\'.legend span\').forEach(e=>{const t=e.textContent.trim();put(e,LDEF[t]||DEF[t]);});\n  document.querySelectorAll(\'h2,.fg>span,th\').forEach(e=>put(e,DEF[e.textContent.trim()]));\n}\n(function(){const tip=document.createElement(\'div\');tip.id=\'defTip\';tip.hidden=true;tip.setAttribute(\'role\',\'tooltip\');document.body.appendChild(tip);\n  const place=(x,y)=>{const w=tip.offsetWidth,h=tip.offsetHeight;let l=x+12,t=y+14;if(l+w>innerWidth-8)l=Math.max(8,x-w-12);if(t+h>innerHeight-8)t=Math.max(8,y-h-12);tip.style.left=l+\'px\';tip.style.top=t+\'px\';};\n  const show=(el,x,y)=>{tip.textContent=el.dataset.def;tip.hidden=false;place(x,y);};\n  document.addEventListener(\'mouseover\',e=>{const el=e.target.closest(\'[data-def]\');if(el)show(el,e.clientX,e.clientY);});\n  document.addEventListener(\'mousemove\',e=>{if(!tip.hidden&&e.target.closest(\'[data-def]\'))place(e.clientX,e.clientY);});\n  document.addEventListener(\'mouseout\',e=>{const el=e.target.closest(\'[data-def]\');if(el&&!el.contains(e.relatedTarget))tip.hidden=true;});\n  document.addEventListener(\'focusin\',e=>{const el=e.target.closest(\'[data-def]\');if(el){const r=el.getBoundingClientRect();show(el,r.left,r.bottom);}});\n  document.addEventListener(\'focusout\',()=>{tip.hidden=true;});\n})();\n\nrender();\nif(window.parent!==window){const send=()=>window.parent.postMessage({capH:document.body.getBoundingClientRect().height},\'*\');\n  if(window.ResizeObserver) new ResizeObserver(send).observe(document.body); send();}\n</script></body></html>'
