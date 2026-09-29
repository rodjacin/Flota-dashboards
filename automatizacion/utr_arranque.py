#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
================================================================================
 Pestaña "UTR" de la Consola de Flota (datos del bucket GCP de Glovo)
================================================================================

 Genera, a partir de ~/Downloads/fleet_data (shift_lv + delivery_lv):
   · UTR (entregas completadas / hora conectada) por hora del dia x dia de la
     semana y por rider x semana (o dia).
   · Arranque de turno: desde que el rider se conecta hasta su primer aviso,
     su primera recogida y los km hasta el primer restaurante.
   · Mapa de arranque AGRUPADO en cuadriculas de ~500 m (sin ID de rider y solo
     cuadriculas con al menos 3 conexiones), porque los dashboards son publicos.

 Lo usa generar_resumen_flota.py (pestaña "UTR"). Tambien se puede ejecutar
 solo para ver el resultado en un HTML suelto:
   python3 ~/Downloads/utr_arranque.py
================================================================================
"""

import os
import sys
import json
import math
import datetime
import bisect

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import heatmaps_reasignaciones as H          # leer(), punto(), RAW_DIR, NODE_ALIASES

OUTPUT_DIR   = os.environ.get("MUSHDRINK_OUT", os.path.expanduser("~/Downloads/dashboards"))
OUTPUT_FILE  = "utr_arranque.html"
WEEKS_TO_SHOW = 8
GRID_DEG      = 0.005      # tamaño de cuadricula del mapa (~500 m)
MIN_CELL      = 3          # conexiones minimas para mostrar una cuadricula
MIN_SHIFT_MIN = 10         # tramos de conexion mas cortos se ignoran

_C = {}


def _ts(pd, s):
    return pd.to_datetime(s.astype(str).str.slice(0, 19), errors="coerce")


def _cargar():
    if "s" in _C:
        return _C["s"], _C["d"]
    import pandas as pd
    s = H.leer(pd, "shift_lv.csv")
    if s.empty:
        raise ValueError("no encuentro shift_lv.csv en " + H.RAW_DIR)
    s = s.drop_duplicates(subset=[c for c in ["rider_id", "interval_start", "interval_finish"] if c in s.columns])
    s["a"], s["b"] = _ts(pd, s["interval_start"]), _ts(pd, s["interval_finish"])
    s = s[s["a"].notna() & s["b"].notna() & (s["b"] > s["a"])].copy()
    s["city"] = s["city_code"].astype(str).str.strip().map(lambda v: H.NODE_ALIASES.get(v, v) or "?")
    s["rider_id"] = s["rider_id"].astype(str).str.strip()

    cols = ["delivery_id", "rider_id", "city_code", "delivery_status", "rider_notified_local_at",
            "rider_picked_up_at", "rider_dropped_off_local_at", "sp_distance_google_km",
            "rider_notified_location", "vendor_location"]
    d = H.leer(pd, "delivery_lv.csv", cols=cols)
    if d.empty:
        raise ValueError("no encuentro delivery_lv.csv en " + H.RAW_DIR)
    for c in cols:
        if c not in d.columns:
            d[c] = ""
    d = d.drop_duplicates(subset=["delivery_id", "rider_id"])
    d["rider_id"] = d["rider_id"].astype(str).str.strip()
    d["city"] = d["city_code"].astype(str).str.strip().map(lambda v: H.NODE_ALIASES.get(v, v) or "?")
    d["n"] = _ts(pd, d["rider_notified_local_at"])
    d["p"] = _ts(pd, d["rider_picked_up_at"])
    d["o"] = _ts(pd, d["rider_dropped_off_local_at"])
    d["km"] = pd.to_numeric(d["sp_distance_google_km"], errors="coerce")
    d["done"] = d["delivery_status"].astype(str).str.lower().eq("completed")
    _C["s"], _C["d"] = s, d
    return s, d


def _wk(dt):
    y, w, _ = dt.isocalendar()
    return (y, w)


def _r(x, n=2):
    return None if x is None or (isinstance(x, float) and math.isnan(x)) else round(float(x), n)


def construir_html(cities=None, semanas=None, sello=True):
    """Devuelve (html, resumen) de la pestaña UTR para esas ciudades."""
    import pandas as pd
    s, d = _cargar()
    if cities:
        s = s[s["city"].isin(set(cities))]
        d = d[d["city"].isin(set(cities))]
    if s.empty:
        raise ValueError("no hay conexiones (shift_lv) para " + ", ".join(cities or []))

    keys = sorted(set(s["a"].map(_wk)))[-(semanas or WEEKS_TO_SHOW):]
    keep = set(keys)
    first_day = datetime.datetime.fromisocalendar(keys[0][0], keys[0][1], 1)
    s = s[s["a"] >= first_day]
    d = d[(d["n"] >= first_day) | (d["o"] >= first_day)]
    weeks = ["W" + str(k[1]) for k in keys]

    def wl(dt):
        k = _wk(dt)
        return ("W" + str(k[1])) if k in keep else None

    # ---- 1) horas conectadas por (dia, hora, ciudad) y por (rider, dia) -----------------
    hrs, rhrs = {}, {}
    for a, b, city, rider in s[["a", "b", "city", "rider_id"]].itertuples(index=False, name=None):
        t = a
        while t < b:
            nxt = min(b, t.replace(minute=0, second=0, microsecond=0) + pd.Timedelta(hours=1))
            h = (nxt - t).total_seconds() / 3600.0
            k = (t.strftime("%Y-%m-%d"), t.hour, city)
            hrs[k] = hrs.get(k, 0.0) + h
            k2 = (t.strftime("%Y-%m-%d"), city, rider)
            rhrs[k2] = rhrs.get(k2, 0.0) + h
            t = nxt
    # ---- entregas completadas por hora de entrega ----------------------------------------
    dl, rdl = {}, {}
    dd = d[d["done"] & d["o"].notna()]
    for o, city, rider in dd[["o", "city", "rider_id"]].itertuples(index=False, name=None):
        k = (o.strftime("%Y-%m-%d"), o.hour, city)
        dl[k] = dl.get(k, 0) + 1
        k2 = (o.strftime("%Y-%m-%d"), city, rider)
        rdl[k2] = rdl.get(k2, 0) + 1

    utr = []
    for k in sorted(set(hrs) | set(dl)):
        dt = datetime.datetime.strptime(k[0], "%Y-%m-%d")
        w = wl(dt)
        if not w:
            continue
        utr.append([k[0], w, dt.weekday(), k[1], k[2], dl.get(k, 0), round(hrs.get(k, 0.0), 3)])
    rutr = []
    for k in sorted(set(rhrs) | set(rdl)):
        dt = datetime.datetime.strptime(k[0], "%Y-%m-%d")
        w = wl(dt)
        if not w:
            continue
        rutr.append([k[0], w, k[1], k[2], rdl.get(k, 0), round(rhrs.get(k, 0.0), 3)])

    # ---- 2) arranque de turno: primer aviso dentro de cada tramo de conexion -------------
    ss = s[(s["b"] - s["a"]).dt.total_seconds() >= MIN_SHIFT_MIN * 60].sort_values("a")
    by_r = {r: sorted(g.tolist()) for r, g in dd.groupby("rider_id")["o"]}     # entregas por rider
    dn = d[d["n"].notna()].sort_values("n")
    m = pd.merge_asof(ss[["rider_id", "city", "a", "b"]], dn[["rider_id", "n", "p", "km", "rider_notified_location"]],
                      left_on="a", right_on="n", by="rider_id", direction="forward")
    arr, mp, cells, cell_idx = [], [], [], {}
    for rider, city, a, b, n, p, km, loc in m[["rider_id", "city", "a", "b", "n", "p", "km",
                                              "rider_notified_location"]].itertuples(index=False, name=None):
        w = wl(a)
        if not w:
            continue
        got = (not pd.isna(n)) and n <= b
        mn = _r((n - a).total_seconds() / 60.0, 1) if got else None
        mpk = _r((p - a).total_seconds() / 60.0, 1) if got and not pd.isna(p) and p >= a else None
        kmv = _r(km, 2) if got and not pd.isna(km) else None
        lst = by_r.get(rider, [])
        n_del = bisect.bisect_right(lst, b) - bisect.bisect_left(lst, a)       # entregas dentro de la conexion
        arr.append([a.strftime("%Y-%m-%d"), w, a.weekday(), a.hour, city, rider,
                    mn, mpk, kmv, 1 if got else 0, round((b - a).total_seconds() / 3600.0, 3), n_del])
        if got:
            lat, lon = H.punto(loc if isinstance(loc, str) else "")
            if lat is not None:
                ck = (round(math.floor(lat / GRID_DEG) * GRID_DEG + GRID_DEG / 2, 5),
                      round(math.floor(lon / GRID_DEG) * GRID_DEG + GRID_DEG / 2, 5))
                if ck not in cell_idx:
                    cell_idx[ck] = len(cells)
                    cells.append(list(ck))
                mp.append([a.strftime("%Y-%m-%d"), w, city, cell_idx[ck], mn])
    arr.sort(key=lambda r: (r[0], r[4], r[5], r[3]))
    mp.sort(key=lambda r: (r[0], r[2], r[3], -1 if r[4] is None else r[4]))

    # ---- restaurantes (capa de referencia del mapa) --------------------------------------
    rest = {}
    dv = d[d["done"] & (d["vendor_location"].astype(str) != "")]
    for loc, city in dv[["vendor_location", "city"]].itertuples(index=False, name=None):
        lat, lon = H.punto(loc)
        if lat is None:
            continue
        k = (round(lat, 4), round(lon, 4), city)
        rest[k] = rest.get(k, 0) + 1
    rests = sorted([[k[0], k[1], k[2], v] for k, v in rest.items()])

    data = {
        "utr": utr, "rutr": rutr, "arr": arr, "map": mp, "cells": cells, "rest": rests,
        "weeks": weeks, "cities": sorted(set(r[4] for r in utr) | set(r[4] for r in arr)),
        "minCell": MIN_CELL, "gridM": int(GRID_DEG * 111000 / 50) * 50,
        "generated": datetime.datetime.now().strftime("%d/%m/%Y %H:%M") if sello else "",
    }
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    tot_h = sum(r[6] for r in utr)
    tot_d = sum(r[5] for r in utr)
    resumen = (("UTR %.2f" % (tot_d / tot_h)) if tot_h else "UTR –") + " · " + \
              str(len(arr)) + " conexiones · " + weeks[0] + "–" + weeks[-1] + " · " + ", ".join(data["cities"])
    return HTML.replace("__DATA__", payload), resumen


_BTN = '<button data-v="utr" aria-pressed="false">UTR</button>'


def integrar_en_dashboard(dash_html, utr_html):
    """Añade la pestaña 'UTR' al selector Vista del dashboard (en un iframe aislado)."""
    if 'id="viewUtr"' in dash_html:
        return dash_html
    ancla = None
    for a in ['<button data-v="heat" aria-pressed="false">Mapas de calor</button>',
              '<button data-v="liga" aria-pressed="false">Delivery Race</button>']:
        if a in dash_html:
            ancla = a
            break
    sec_ancla = '<div id="viewSemanal">'
    if not ancla or sec_ancla not in dash_html or "</body>" not in dash_html:
        raise ValueError("la plantilla no tiene el selector de Vista esperado")
    dash_html = dash_html.replace(ancla, ancla + "\n        " + _BTN, 1)
    dash_html = dash_html.replace(sec_ancla,
        '<section id="viewUtr" style="display:none"><iframe id="utrFrame" title="UTR y arranque de turno" '
        'style="width:100%;height:1400px;border:0;display:block;background:transparent"></iframe></section>\n  '
        + sec_ancla, 1)
    # "<" -> <: sin etiquetas literales dentro (el perl de publicar_dashboards.sh no puede romperlo)
    src = json.dumps(utr_html, ensure_ascii=False).replace("<", "\\u003c")
    js = ("<script>\n/* ==== Pestaña UTR (bucket GCP) ==== */\n(function(){\n"
          "  const UTR_HTML=" + src + ";\n"
          "  const seg=document.getElementById('viewSeg'),sec=document.getElementById('viewUtr'),fr=document.getElementById('utrFrame');\n"
          "  if(!seg||!sec||!fr) return; let loaded=false;\n"
          "  seg.querySelectorAll('button').forEach(b=>b.addEventListener('click',()=>{\n"
          "    const on=b.dataset.v==='utr'; sec.style.display=on?'':'none';\n"
          "    if(on){ seg.querySelectorAll('button').forEach(x=>x.setAttribute('aria-pressed',String(x===b)));\n"
          "      ['viewSemanal','viewDiario','viewLiga','viewHeat'].forEach(id=>{const e=document.getElementById(id); if(e) e.style.display='none';});\n"
          "      if(!loaded){ fr.srcdoc=UTR_HTML; loaded=true; } window.scrollTo(0,0); }\n"
          "  }));\n"
          "  window.addEventListener('message',e=>{ if(e.source===fr.contentWindow && e.data && e.data.utrH){\n"
          "    fr.style.height=Math.max(600,Math.ceil(e.data.utrH)+20)+'px'; } });\n"
          "})();\n</script>\n")
    i = dash_html.rindex("</body>")
    return dash_html[:i] + js + dash_html[i:]


def main():
    try:
        html, res = construir_html(None)
    except ValueError as e:
        print("\nERROR: " + str(e) + "\n"); sys.exit(1)
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    out = os.path.join(OUTPUT_DIR, OUTPUT_FILE)
    open(out, "w", encoding="utf-8").write(html)
    print("OK · " + res + "\nÁbrelo con:\n   open \"" + out + "\"")


HTML = r"""<!DOCTYPE html>
<html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>UTR y arranque de turno</title>
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.css">
<script src="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.js"></script>
<style>
:root{--bg:#F6F7F9;--panel:#FFFFFF;--panel2:#F9FAFB;--line:#E4E7EC;--line2:#D3D8E0;--tx:#14171F;--tx2:#374151;--dim:#6B7280;--dimmer:#C2C8D0;--acc:#0E5A6B;--accsoft:#E3F0F2;--hover:#EEF2F5}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--tx);font:14px/1.45 "Inter",-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif}
.wrap{padding:0 0 24px}
h1{font-size:17px;margin:0 0 2px}.sub{color:var(--dim);font-size:12.5px}
.bar{display:flex;flex-wrap:wrap;gap:14px;align-items:flex-end;margin:14px 0 12px;padding:12px;background:var(--panel);border:1px solid var(--line);border-radius:12px}
.field{display:flex;flex-direction:column;gap:5px}
.lbl{font-size:11px;text-transform:uppercase;letter-spacing:.06em;color:var(--dim)}
select{background:#fff;color:var(--tx);border:1px solid var(--line2);border-radius:8px;padding:7px 10px;font:inherit;font-size:13px;min-width:150px}
.seg{display:flex;flex-wrap:wrap;gap:4px}
.seg button,.tabs button{background:#fff;color:var(--dim);border:1px solid var(--line2);border-radius:8px;padding:6px 11px;font:inherit;font-size:13px;cursor:pointer}
.seg button.on,.tabs button.on{background:var(--accsoft);color:var(--acc);border-color:var(--acc)}
.seg button small{color:var(--dim);margin-left:4px}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:10px;margin-bottom:12px}
.kpi{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:10px 14px}
.kpi b{display:block;font-size:20px;font-variant-numeric:tabular-nums}.kpi span{font-size:11.5px;color:var(--dim)}
.tabs{display:flex;flex-wrap:wrap;gap:6px;margin-bottom:10px}
.tabs .sep{width:1px;background:var(--line2);margin:0 4px}
.card{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:14px}
.hbox{border:1px solid var(--line2);border-radius:10px;padding:10px 12px;font-size:12.5px;color:var(--tx2);background:var(--panel2);margin-bottom:12px}
.hbox b.t{display:block;font-size:11px;text-transform:uppercase;letter-spacing:.06em;color:var(--dim);margin-bottom:3px}
.scroll{overflow-x:auto}
table.hm{border-collapse:separate;border-spacing:2px;font-size:12px;font-variant-numeric:tabular-nums}
table.hm th{color:var(--dim);font-weight:600;padding:4px 6px;white-space:nowrap;text-align:center;background:var(--panel)}
table.hm td{padding:5px 6px;text-align:center;border-radius:4px;min-width:38px;white-space:nowrap;color:#14171F}
table.hm .lft{text-align:left;position:sticky;left:0;background:var(--panel);z-index:1;max-width:240px;overflow:hidden;text-overflow:ellipsis}
table.hm td.tot,table.hm tr.totrow td{font-weight:650;color:#374151}
table.hm tr.totrow td{border-top:1px solid var(--line2)}
table.hm td.few{opacity:.45}
.cards3{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:10px;margin-bottom:14px}
.big{background:var(--panel2);border:1px solid var(--line2);border-radius:12px;padding:12px 14px}
.big .k{font-size:11px;text-transform:uppercase;letter-spacing:.06em;color:var(--dim)}
.big .v{font-size:24px;font-weight:650;margin-top:2px;font-variant-numeric:tabular-nums}
.big .v small{font-size:13px;font-weight:500;color:var(--dim)}
.big .d{font-size:12.5px;color:var(--tx2);margin-top:2px}
.bad{color:#B5342A}.good{color:#167C58}
.scat{background:var(--panel2);border:1px solid var(--line2);border-radius:12px;padding:10px;margin-bottom:14px}
.scat h3,.al h3{font-size:13px;margin:2px 4px 6px}
.scat svg{width:100%;height:auto;display:block}
.pbar{display:inline-block;width:60px;height:8px;border-radius:4px;background:#E4E7EC;vertical-align:middle;margin-right:6px;overflow:hidden}
.pbar i{display:block;height:100%;background:#E5624D}
table.hm td.dx{text-align:left;color:var(--tx2);white-space:normal;min-width:220px}
.tag{display:inline-block;font-size:11px;padding:1px 8px;border-radius:999px;font-weight:600}
.tag.r{background:#FBE9E7;color:#B5342A}.tag.a{background:#FBF1DD;color:#9A6B12}.tag.g{background:#E7F4EE;color:#167C58}
.dim{color:var(--dimmer)}
.foot{display:flex;justify-content:space-between;align-items:center;margin-top:10px;font-size:12px;color:var(--dim);gap:10px;flex-wrap:wrap}
.btn{background:#fff;color:var(--tx);border:1px solid var(--line2);border-radius:8px;padding:6px 12px;font:inherit;font-size:12.5px;cursor:pointer}
.leg{display:inline-block;width:70px;height:9px;border-radius:3px;vertical-align:middle;margin:0 6px}
.empty{padding:40px;text-align:center;color:var(--dim)}
#mapwrap{display:grid;grid-template-columns:minmax(0,1fr) 280px;gap:12px}
@media(max-width:900px){#mapwrap{grid-template-columns:1fr}}
#map{height:640px;border-radius:10px;background:#dfe3e8}
#maplist{max-height:640px;overflow:auto;border:1px solid var(--line2);border-radius:10px;padding:8px;background:var(--panel2)}
#maplist h4{margin:4px 6px 8px;font-size:11px;text-transform:uppercase;letter-spacing:.06em;color:var(--dim);font-weight:600}
.ml-item{display:flex;gap:8px;align-items:center;padding:6px 8px;border-radius:8px;cursor:pointer;font-size:12.5px}
.ml-item:hover{background:var(--hover)}
.ml-dot{width:12px;height:12px;border-radius:50%;border:1.5px solid #1b1b1b;flex:none}
.ml-n{margin-left:auto;font-weight:650;font-variant-numeric:tabular-nums;text-align:right}
.maplegend{background:rgba(255,255,255,.95);color:#1b1f24;padding:8px 10px;border-radius:8px;font:12px/1.3 -apple-system,Segoe UI,sans-serif;box-shadow:0 1px 5px rgba(0,0,0,.3)}
.maplegend .g{width:150px;height:10px;border-radius:3px;margin:5px 0 2px;border:1px solid rgba(0,0,0,.2)}
.maplegend .ends{display:flex;justify-content:space-between;color:#555}
.guide h2{font-size:15px;margin:20px 0 8px}.guide h2:first-child{margin-top:0}
.guide p{font-size:13px;color:var(--tx2);margin:0 0 8px;max-width:920px}
.gcards{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:10px}
.gcards div{background:var(--panel2);border:1px solid var(--line2);border-radius:10px;padding:10px 12px;font-size:12.5px;color:var(--tx2)}
.gcards b{display:block;color:var(--tx);margin-bottom:3px}
</style></head><body><div class="wrap">
<h1>UTR y arranque de turno</h1>
<div class="sub" id="sub"></div>

<div class="bar">
  <div class="field"><span class="lbl">Ciudad</span><div class="seg" id="citySeg"></div></div>
  <div class="field"><span class="lbl">Semana</span><select id="weekSel"></select></div>
  <div class="field"><span class="lbl">Día</span><select id="daySel"></select></div>
  <div class="field" id="farField"><span class="lbl">Lejos = primer restaurante a más de</span><select id="farSel">
    <option value="2">2 km</option><option value="3" selected>3 km</option><option value="4">4 km</option><option value="5">5 km</option></select></div>
  <div class="field" id="metField"><span class="lbl">Métrica de arranque</span><select id="metSel">
    <option value="6">Min hasta el primer aviso</option>
    <option value="7">Min hasta la primera recogida</option>
    <option value="8">Km hasta el primer restaurante</option>
    <option value="9">% conexiones sin pedido</option></select></div>
</div>

<div class="kpis" id="kpis"></div>

<div class="tabs" id="tabs">
  <button data-v="guia" class="on">📘 Guía</button><span class="sep"></span>
  <button data-v="uh">UTR · hora × día</button>
  <button data-v="ur">UTR · por rider</button><span class="sep"></span>
  <button data-v="al">⚠ Arranque lejano</button>
  <button data-v="ah">Arranque · hora × día</button>
  <button data-v="ar">Arranque · por rider</button>
  <button data-v="am">Arranque · mapa</button>
</div>

<div class="card">
  <div id="help"></div>
  <div class="scroll" id="out"></div>
  <div id="mapwrap" style="display:none"><div id="map"></div><div id="maplist"></div></div>
  <div class="foot" id="footbar"><span id="foot"></span><span id="legend"></span><button class="btn" id="csvBtn">Descargar CSV</button></div>
</div>
</div>
<script>
const D=__DATA__;
const U=D.utr,RU=D.rutr,A=D.arr,M=D.map;   // U:[fecha,sem,dow,hora,ciudad,entregas,horas] RU:[fecha,sem,ciudad,rider,entregas,horas]
                                           // A:[fecha,sem,dow,horaInicio,ciudad,rider,minAviso,minRecogida,km,conPedido,horasConexion,entregasConexion] M:[fecha,sem,ciudad,celda,minAviso]
const DOW=['Lun','Mar','Mié','Jue','Vie','Sáb','Dom'],DIAS=['Dom','Lun','Mar','Mié','Jue','Vie','Sáb'];
const st={city:'ALL',week:'ALL',day:'ALL',met:6,far:3,view:'guia'};
const MET={6:{n:'Min hasta el primer aviso',u:' min',agg:'med'},7:{n:'Min hasta la primera recogida',u:' min',agg:'med'},
           8:{n:'Km hasta el primer restaurante',u:' km',agg:'med'},9:{n:'% conexiones sin pedido',u:'%',agg:'pct'}};
let last=null,map=null,layer=null,restLayer=null,legendDiv=null;
const fmt=(n,d)=>n==null?'–':n.toLocaleString('es-ES',{minimumFractionDigits:d||0,maximumFractionDigits:d||0});
const esc=s=>String(s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const dayLbl=d=>{const x=new Date(d+'T12:00:00');return DIAS[x.getDay()]+' '+d.slice(8,10)+'/'+d.slice(5,7);};
function median(a){if(!a.length)return null;const s=a.slice().sort((x,y)=>x-y),m=s.length>>1;return s.length%2?s[m]:(s[m-1]+s[m])/2;}
// escala verde (bueno) -> ambar -> rojo (malo)
const ST=[[0,[46,158,123]],[.5,[224,169,74]],[1,[229,98,77]]];
function rgb(t){t=Math.max(0,Math.min(1,t));const [a,b]=t<=.5?[ST[0],ST[1]]:[ST[1],ST[2]];const f=(t-a[0])/(b[0]-a[0]);return a[1].map((x,k)=>Math.round(x+(b[1][k]-x)*f));}
const bg=t=>'rgba('+rgb(t)+','+(0.25+0.45*Math.abs(t-0.5)*2).toFixed(2)+')';
const LEG_GOOD='linear-gradient(90deg,rgba(46,158,123,.8),rgba(224,169,74,.8),rgba(229,98,77,.8))';

const inF=r=>(st.city==='ALL'||r.c===st.city);
function fU(){return U.filter(r=>(st.city==='ALL'||r[4]===st.city)&&(st.week==='ALL'||r[1]===st.week)&&(st.day==='ALL'||r[0]===st.day));}
function fRU(){return RU.filter(r=>(st.city==='ALL'||r[2]===st.city)&&(st.week==='ALL'||r[1]===st.week)&&(st.day==='ALL'||r[0]===st.day));}
function fA(){return A.filter(r=>(st.city==='ALL'||r[4]===st.city)&&(st.week==='ALL'||r[1]===st.week)&&(st.day==='ALL'||r[0]===st.day));}
function fM(){return M.filter(r=>(st.city==='ALL'||r[2]===st.city)&&(st.week==='ALL'||r[1]===st.week)&&(st.day==='ALL'||r[0]===st.day));}
function period(){
  if(st.day!=='ALL') return {keys:[st.day],lbl:[dayLbl(st.day)],w:false};
  if(st.week!=='ALL'){const ks=[...new Set(U.filter(r=>r[1]===st.week).map(r=>r[0]))].sort();return {keys:ks,lbl:ks.map(dayLbl),w:false};}
  return {keys:D.weeks,lbl:D.weeks,w:true};}
function aggMet(rows){const m=st.met;
  if(MET[m].agg==='pct'){if(!rows.length)return null;return 100*rows.filter(r=>!r[9]).length/rows.length;}
  return median(rows.map(r=>r[m]).filter(v=>v!=null));}
const metDec=()=>st.met==8?1:0;

// tabla generica: vals[i][j]=numero|null, tips[i][j], totals por fila, fila de totales
function table(head,rowL,colL,vals,opt){
  last={head,rowL,colL,vals,tot:opt.rowTot,totName:opt.totName||'Total'};
  if(!rowL.length) return '<div class="empty"><b>Sin datos</b><br>No hay datos con estos filtros.</div>';
  const all=[];vals.forEach(r=>r.forEach(v=>{if(v!=null)all.push(v);}));
  const lo=Math.min(...all),hi=Math.max(...all);
  const t=v=>{let x=(v-lo)/((hi-lo)||1);return opt.higherBetter?1-x:x;};
  let h='<table class="hm"><thead><tr><th class="lft">'+esc(head)+'</th>'+colL.map(c=>'<th>'+esc(c)+'</th>').join('')+
    (opt.rowTot?'<th>'+esc(opt.totName||'Total')+'</th>':'')+(opt.extra?opt.extra.h.map(x=>'<th>'+esc(x)+'</th>').join(''):'')+'</tr></thead><tbody>';
  rowL.forEach((rl,i)=>{h+='<tr><td class="lft" title="'+esc(rl)+'">'+esc(rl)+'</td>'+vals[i].map((v,j)=>{
      const tip=opt.tips&&opt.tips[i][j]||'',few=opt.few&&opt.few[i][j];
      return '<td'+(few?' class="few"':'')+(tip?' title="'+esc(tip)+'"':'')+(v!=null?' style="background:'+bg(t(v))+'"':'')+'>'+(v!=null?fmt(v,opt.dec):'<span class="dim">·</span>')+'</td>';}).join('')+
    (opt.rowTot?'<td class="tot">'+fmt(opt.rowTot[i],opt.dec)+'</td>':'')+(opt.extra?opt.extra.v[i].map(x=>'<td class="tot">'+x+'</td>').join(''):'')+'</tr>';});
  if(opt.colTot) h+='<tr class="totrow"><td class="lft">'+esc(opt.totName||'Total')+'</td>'+opt.colTot.map(v=>'<td>'+fmt(v,opt.dec)+'</td>').join('')+
    (opt.rowTot?'<td>'+fmt(opt.grand,opt.dec)+'</td>':'')+(opt.extra?opt.extra.h.map(()=>'<td></td>').join(''):'')+'</tr>';
  return h+'</tbody></table>';}

const HELP={
 uh:['¿EN QUÉ HORAS SOBRAN O FALTAN RIDERS?','Cada celda es el UTR (entregas completadas ÷ horas conectadas) de ese día de la semana y hora. Verde = UTR alto (riders bien aprovechados); rojo = UTR bajo (riders conectados sin pedidos: sobran horas en esa franja). Las celdas con menos de 1 h conectada salen atenuadas. Pasa el ratón para ver entregas y horas.'],
 ur:['¿QUÉ RIDERS APROVECHAN PEOR SUS HORAS?','Filas = riders (ordenados de peor a mejor UTR del periodo); columnas = semanas (o días si eliges una semana). Solo riders con al menos 2 h conectadas. Un rider en rojo todas las semanas se conecta en franjas o sitios sin demanda.'],
 al:['¿QUÉ RIDERS ARRANCAN LEJOS Y CUÁNTO LES BAJA EL UTR?','Para cada conexión miramos a cuántos km estaba el rider del restaurante de su primer pedido. Si está a más de los km elegidos arriba, esa conexión cuenta como «arranque lejano». Comparamos el UTR de sus conexiones que arrancan lejos con las que arrancan cerca: si baja, arrancar lejos le está costando entregas. Pasa el ratón por los puntos del gráfico para ver cada rider.'],
 ah:['¿CUÁNTO TARDAN EN ARRANCAR SEGÚN LA HORA A LA QUE SE CONECTAN?','Filas = día de la semana; columnas = hora a la que se conecta el rider. Cada celda es la mediana de la métrica elegida arriba (o el % de conexiones sin ningún pedido). Rojo = tardan más en recibir o recoger su primer pedido: suele indicar que se conectan antes del pico o que hay demasiados riders a esa hora.'],
 ar:['¿QUÉ RIDERS TARDAN MÁS EN ARRANCAR?','Filas = riders (peor arriba); columnas = semanas (o días). Cada celda es la mediana de la métrica elegida en sus conexiones. Solo riders con al menos 2 conexiones.'],
 am:['¿DESDE DÓNDE ARRANCAN Y CUÁNTO TARDAN?','Cada círculo es una cuadrícula de ~'+D.gridM+' m donde los riders estaban al recibir su primer pedido. Tamaño = nº de conexiones; color = mediana de minutos hasta ese primer aviso (rojo = tardan más). Los puntos grises pequeños son los restaurantes. Por privacidad no se muestran riders concretos ni cuadrículas con menos de '+D.minCell+' conexiones.'],
};

function kpis(){
  const u=fU(),a=fA(),dl=u.reduce((s,r)=>s+r[5],0),h=u.reduce((s,r)=>s+r[6],0);
  const k=[[h?fmt(dl/h,2):'–','UTR (entregas / hora conectada)'],[fmt(h,0),'Horas conectadas · '+fmt(dl)+' entregas'],
    [fmt(median(a.map(r=>r[6]).filter(v=>v!=null)),0)+' min','Mediana hasta el primer aviso'],
    [fmt(median(a.map(r=>r[7]).filter(v=>v!=null)),0)+' min','Mediana hasta la primera recogida'],
    [a.length?fmt(100*a.filter(r=>!r[9]).length/a.length,0)+'%':'–','Conexiones sin ningún pedido ('+fmt(a.length)+' conexiones)']];
  document.getElementById('kpis').innerHTML=k.map(x=>'<div class="kpi"><b>'+x[0]+'</b><span>'+esc(x[1])+'</span></div>').join('');}

function render(){
  kpis();
  const out=document.getElementById('out'),mw=document.getElementById('mapwrap'),hp=document.getElementById('help');
  document.getElementById('metField').style.display=(st.view==='ah'||st.view==='ar')?'':'none';
  document.getElementById('farField').style.display=st.view==='al'?'':'none';
  document.getElementById('footbar').style.display=st.view==='guia'?'none':'';
  out.style.display='';mw.style.display='none';let foot='',leg='';
  hp.innerHTML=HELP[st.view]?'<div class="hbox"><b class="t">Cómo leer esta vista · '+HELP[st.view][0]+'</b>'+esc(HELP[st.view][1])+'</div>':'';
  if(st.view==='guia'){last=null;out.innerHTML=guide();return;}
  if(st.view==='al'){const r=farView();out.innerHTML=r.html;foot=r.foot;leg='';}
  else if(st.view==='uh'){
    const u=fU(),dl=DOW.map(()=>Array(24).fill(0)),hr=DOW.map(()=>Array(24).fill(0));
    u.forEach(r=>{dl[r[2]][r[3]]+=r[5];hr[r[2]][r[3]]+=r[6];});
    const vals=dl.map((row,i)=>row.map((x,j)=>hr[i][j]>=0.25?x/hr[i][j]:null));
    const few=hr.map(row=>row.map(x=>x<1)),tips=dl.map((row,i)=>row.map((x,j)=>hr[i][j]?x+' entregas / '+fmt(hr[i][j],1)+' h':''));
    const rowTot=dl.map((row,i)=>{const h=hr[i].reduce((a,b)=>a+b,0);return h?row.reduce((a,b)=>a+b,0)/h:null;});
    const colTot=[...Array(24).keys()].map(j=>{const h=hr.reduce((s,r)=>s+r[j],0);return h?dl.reduce((s,r)=>s+r[j],0)/h:null;});
    const H_=hr.flat().reduce((a,b)=>a+b,0);
    out.innerHTML=table('Día',DOW,[...Array(24).keys()].map(h=>h+'h'),vals,{dec:2,higherBetter:true,tips,few,rowTot,colTot,grand:H_?dl.flat().reduce((a,b)=>a+b,0)/H_:null,totName:'UTR'});
    leg='UTR bajo <span class="leg" style="background:linear-gradient(90deg,rgba(229,98,77,.8),rgba(224,169,74,.8),rgba(46,158,123,.8))"></span> alto';
  } else if(st.view==='ur'){
    const P=period(),g=new Map();
    fRU().forEach(r=>{const k=r[3]+' · '+r[2];let o=g.get(k);if(!o){o={d:{},h:{},D:0,H:0};g.set(k,o);}const c=P.w?r[1]:r[0];
      o.d[c]=(o.d[c]||0)+r[4];o.h[c]=(o.h[c]||0)+r[5];o.D+=r[4];o.H+=r[5];});
    let e=[...g.entries()].filter(([k,o])=>o.H>=2).map(([k,o])=>[k,o,o.D/o.H]).sort((a,b)=>a[2]-b[2]);
    const more=Math.max(0,e.length-120);e=e.slice(0,120);
    const vals=e.map(([k,o])=>P.keys.map(c=>o.h[c]>=1?o.d[c]/o.h[c]:null));
    const tips=e.map(([k,o])=>P.keys.map(c=>o.h[c]?(o.d[c]||0)+' entregas / '+fmt(o.h[c],1)+' h':''));
    out.innerHTML=table('Rider',e.map(x=>x[0]),P.lbl,vals,{dec:2,higherBetter:true,tips,rowTot:e.map(x=>x[2]),totName:'UTR',
      extra:{h:['Horas','Entregas'],v:e.map(([k,o])=>[fmt(o.H,1),fmt(o.D)])}});
    leg='UTR bajo <span class="leg" style="background:linear-gradient(90deg,rgba(229,98,77,.8),rgba(224,169,74,.8),rgba(46,158,123,.8))"></span> alto';
    foot=(e.length+more)+' riders con ≥ 2 h'+(more?' (se muestran los 120 con peor UTR)':'');
  } else if(st.view==='ah'){
    const a=fA(),cells=DOW.map(()=>[...Array(24)].map(()=>[]));a.forEach(r=>cells[r[2]][r[3]].push(r));
    const vals=cells.map(row=>row.map(c=>c.length?aggMet(c):null)),few=cells.map(row=>row.map(c=>c.length<3));
    const tips=cells.map(row=>row.map(c=>c.length?c.length+' conexiones':''));
    const rowTot=cells.map(row=>aggMet(row.flat())),colTot=[...Array(24).keys()].map(j=>aggMet(cells.map(r=>r[j]).flat()));
    out.innerHTML=table('Día',DOW,[...Array(24).keys()].map(h=>h+'h'),vals,{dec:metDec(),tips,few,rowTot,colTot,grand:aggMet(a),totName:'Total'});
    leg=MET[st.met].n+': mejor <span class="leg" style="background:'+LEG_GOOD+'"></span> peor';
    foot='Hora = hora a la que el rider se conecta. Celdas atenuadas: menos de 3 conexiones.';
  } else if(st.view==='ar'){
    const P=period(),g=new Map();
    fA().forEach(r=>{const k=r[5]+' · '+r[4];let o=g.get(k);if(!o){o={c:{},all:[]};g.set(k,o);}const c=P.w?r[1]:r[0];(o.c[c]=o.c[c]||[]).push(r);o.all.push(r);});
    let e=[...g.entries()].filter(([k,o])=>o.all.length>=2).map(([k,o])=>[k,o,aggMet(o.all)]).filter(x=>x[2]!=null).sort((a,b)=>b[2]-a[2]);
    const more=Math.max(0,e.length-120);e=e.slice(0,120);
    const vals=e.map(([k,o])=>P.keys.map(c=>o.c[c]?aggMet(o.c[c]):null));
    const tips=e.map(([k,o])=>P.keys.map(c=>o.c[c]?o.c[c].length+' conexiones':''));
    out.innerHTML=table('Rider',e.map(x=>x[0]),P.lbl,vals,{dec:metDec(),tips,rowTot:e.map(x=>x[2]),totName:'Total',extra:{h:['Conexiones'],v:e.map(([k,o])=>[fmt(o.all.length)])}});
    leg=MET[st.met].n+': mejor <span class="leg" style="background:'+LEG_GOOD+'"></span> peor';
    foot=(e.length+more)+' riders con ≥ 2 conexiones'+(more?' (se muestran los 120 peores)':'');
  } else {out.style.display='none';mw.style.display='';last=null;foot=drawMap();}
  document.getElementById('foot').textContent=foot;document.getElementById('legend').innerHTML=leg;
  document.getElementById('csvBtn').style.display=st.view==='am'?'none':'';
}

// ---------- Arranque lejano ----------
function utrOf(rs){const h=rs.reduce((s,r)=>s+r[10],0);return h>0?rs.reduce((s,r)=>s+r[11],0)/h:null;}
function farView(){
  const F=st.far,a=fA().filter(r=>r[9]&&r[8]!=null),far=a.filter(r=>r[8]>F),near=a.filter(r=>r[8]<=F);
  if(!a.length){last=null;return {html:'<div class="empty"><b>Sin datos</b><br>No hay conexiones con pedido para estos filtros.</div>',foot:''};}
  const uF=utrOf(far),uN=utrOf(near),pF=100*far.length/a.length;
  const pkF=median(far.map(r=>r[7]).filter(v=>v!=null)),pkN=median(near.map(r=>r[7]).filter(v=>v!=null));
  const lost=(uF!=null&&uN!=null)?Math.max(0,(uN-uF)*far.reduce((s,r)=>s+r[10],0)):null;
  let h='<div class="cards3">'+
   '<div class="big"><div class="k">Conexiones que arrancan lejos (&gt; '+F+' km)</div><div class="v">'+fmt(pF,0)+'% <small>'+fmt(far.length)+' de '+fmt(a.length)+'</small></div><div class="d">Mediana: '+fmt(median(far.map(r=>r[8])),1)+' km hasta el primer restaurante (cerca: '+fmt(median(near.map(r=>r[8])),1)+' km)</div></div>'+
   '<div class="big"><div class="k">UTR de esas conexiones</div><div class="v"><span class="'+(uF<uN?'bad':'good')+'">'+fmt(uF,2)+'</span> <small>vs '+fmt(uN,2)+' arrancando cerca</small></div><div class="d">'+(uF!=null&&uN?((uF<uN?'▼ ':'▲ ')+fmt(Math.abs(100*(uF-uN)/uN),0)+'% '+(uF<uN?'menos':'más')+' entregas por hora'):'')+'</div></div>'+
   '<div class="big"><div class="k">Tiempo hasta la primera recogida</div><div class="v"><span class="'+(pkF>pkN?'bad':'good')+'">'+fmt(pkF,0)+' min</span> <small>vs '+fmt(pkN,0)+' min cerca</small></div><div class="d">'+(lost!=null?'≈ '+fmt(lost,0)+' entregas menos en el periodo por arrancar lejos':'')+'</div></div></div>';
  // por rider
  const g=new Map();a.forEach(r=>{const k=r[5]+' · '+r[4];let o=g.get(k);if(!o){o={k,all:[],far:[],near:[]};g.set(k,o);}o.all.push(r);(r[8]>F?o.far:o.near).push(r);});
  const R=[...g.values()].filter(o=>o.all.length>=3).map(o=>{const uf=utrOf(o.far),un=utrOf(o.near),u=utrOf(o.all),pf=100*o.far.length/o.all.length;
    let dx,tg;
    if(pf>=50&&uf!=null&&un!=null&&uf<un){tg='r';dx='Arranca lejos a menudo y ese día rinde menos';}
    else if(pf>=50){tg='r';dx='Arranca lejos a menudo';}
    else if(pf>=25&&uf!=null&&un!=null&&uf<un){tg='a';dx='A veces arranca lejos y le baja el UTR';}
    else if(pf>=25){tg='a';dx='A veces arranca lejos';}
    else {tg='g';dx='Suele arrancar cerca';}
    return {k:o.k,n:o.all.length,pf,km:median(o.all.map(r=>r[8])),pk:median(o.all.map(r=>r[7]).filter(v=>v!=null)),u,uf,un,d:(uf!=null&&un!=null)?uf-un:null,tg,dx};})
    .sort((x,y)=>(y.pf-x.pf)||((x.d==null?0:x.d)-(y.d==null?0:y.d)));
  // grafico de dispersion: km mediano (x) vs UTR (y)
  const P=R.filter(r=>r.u!=null);
  if(P.length){const W=900,H=360,ml=48,mr=16,mt=16,mb=40;
    const xs=P.map(r=>r.km).sort((a,b)=>a-b),xmax=Math.max(F*1.6,xs[Math.floor(xs.length*.97)]||1),ymax=Math.max(...P.map(r=>r.u))*1.08||1;
    const X=v=>ml+(W-ml-mr)*Math.min(v,xmax)/xmax,Y=v=>mt+(H-mt-mb)*(1-v/ymax),uAll=utrOf(a);
    let sv='<svg viewBox="0 0 '+W+' '+H+'" role="img" aria-label="Riders: km al primer restaurante frente a UTR">';
    sv+='<rect x="'+X(F)+'" y="'+Y(uAll)+'" width="'+(X(xmax)-X(F))+'" height="'+(Y(0)-Y(uAll))+'" fill="#FBE9E7"/>';
    sv+='<text x="'+(X(xmax)-6)+'" y="'+(Y(0)-8)+'" text-anchor="end" font-size="12" fill="#B5342A" font-weight="600">Arrancan lejos y rinden menos → hablar con ellos</text>';
    sv+='<text x="'+(ml+6)+'" y="'+(mt+12)+'" font-size="12" fill="#167C58" font-weight="600">Arrancan cerca y rinden más</text>';
    for(let i=0;i<=4;i++){const v=ymax*i/4;sv+='<line x1="'+ml+'" x2="'+(W-mr)+'" y1="'+Y(v)+'" y2="'+Y(v)+'" stroke="#E4E7EC"/><text x="'+(ml-6)+'" y="'+(Y(v)+4)+'" text-anchor="end" font-size="11" fill="#6B7280">'+fmt(v,1)+'</text>';}
    for(let v=0;v<=xmax;v+=Math.max(1,Math.round(xmax/8))){sv+='<text x="'+X(v)+'" y="'+(H-mb+16)+'" text-anchor="middle" font-size="11" fill="#6B7280">'+v+' km</text>';}
    sv+='<line x1="'+X(F)+'" x2="'+X(F)+'" y1="'+mt+'" y2="'+Y(0)+'" stroke="#B5342A" stroke-dasharray="4 4"/><text x="'+(X(F)+4)+'" y="'+(mt+12)+'" font-size="11" fill="#B5342A">'+F+' km</text>';
    sv+='<line x1="'+ml+'" x2="'+(W-mr)+'" y1="'+Y(uAll)+'" y2="'+Y(uAll)+'" stroke="#0E5A6B" stroke-dasharray="4 4"/><text x="'+(W-mr)+'" y="'+(Y(uAll)-5)+'" text-anchor="end" font-size="11" fill="#0E5A6B">UTR medio '+fmt(uAll,2)+'</text>';
    sv+='<text x="'+((ml+W-mr)/2)+'" y="'+(H-6)+'" text-anchor="middle" font-size="11.5" fill="#374151">Km medianos hasta el primer restaurante de cada conexión</text>';
    sv+='<text transform="translate(12,'+((mt+H-mb)/2)+') rotate(-90)" text-anchor="middle" font-size="11.5" fill="#374151">UTR del rider</text>';
    const mxn=Math.max(...P.map(r=>r.n));
    P.forEach(r=>{const c=r.tg==='r'?'#E5624D':r.tg==='a'?'#E0A94A':'#2E9E7B';
      sv+='<circle cx="'+X(r.km).toFixed(1)+'" cy="'+Y(r.u).toFixed(1)+'" r="'+(3.5+6*Math.sqrt(r.n/mxn)).toFixed(1)+'" fill="'+c+'" fill-opacity=".75" stroke="#1b1b1b" stroke-width=".6"><title>Rider '+esc(r.k)+'\n'+r.n+' conexiones · '+fmt(r.pf,0)+'% arrancan lejos\nKm mediano: '+fmt(r.km,1)+' · UTR: '+fmt(r.u,2)+'</title></circle>';});
    sv+='</svg>';
    h+='<div class="scat"><h3>Cada punto es un rider: cuanto más a la derecha, más lejos arranca; cuanto más abajo, menos entregas por hora. <span class="tag r">rojo = arranca lejos ≥ 50 % de las veces</span> <span class="tag a">ámbar = 25–50 %</span> <span class="tag g">verde = suele arrancar cerca</span></h3>'+sv+'</div>';}
  // tabla
  const rows=R.slice(0,150);
  last={head:'Rider',rowL:rows.map(r=>r.k),colL:['Conexiones','% lejos','Km mediano','Min 1ª recogida','UTR cerca','UTR lejos','Diferencia'],
        vals:rows.map(r=>[r.n,r.pf,r.km,r.pk,r.un,r.uf,r.d]),tot:null};
  h+='<div class="al"><h3>Riders ordenados por cuántas veces arrancan lejos (solo riders con ≥ 3 conexiones con pedido)</h3><div class="scroll"><table class="hm"><thead><tr><th class="lft">Rider</th><th>Conexiones</th><th>% arrancan lejos</th><th>Km mediano</th><th>Min hasta 1ª recogida</th><th>UTR arrancando cerca</th><th>UTR arrancando lejos</th><th>Diferencia</th><th style="text-align:left">Diagnóstico</th></tr></thead><tbody>'+
    rows.map(r=>'<tr><td class="lft">'+esc(r.k)+'</td><td>'+r.n+'</td><td style="text-align:left"><span class="pbar"><i style="width:'+r.pf.toFixed(0)+'%"></i></span>'+fmt(r.pf,0)+'%</td>'+
      '<td>'+fmt(r.km,1)+'</td><td>'+fmt(r.pk,0)+'</td><td>'+fmt(r.un,2)+'</td><td>'+fmt(r.uf,2)+'</td>'+
      '<td class="'+(r.d==null?'':r.d<0?'bad':'good')+'">'+(r.d==null?'–':(r.d>0?'+':'')+fmt(r.d,2))+'</td><td class="dx"><span class="tag '+r.tg+'">'+esc(r.dx)+'</span></td></tr>').join('')+'</tbody></table></div></div>';
  return {html:h,foot:R.length+' riders'+(R.length>150?' (se muestran 150)':'')+' · «UTR arrancando cerca/lejos» = entregas ÷ horas de sus conexiones de cada tipo'};
}

const MAPC=[[0,[254,224,139]],[.35,[252,141,89]],[.7,[215,48,31]],[1,[127,0,0]]];
function mapColor(t){t=Math.max(0,Math.min(1,t));let i=0;while(i<MAPC.length-2&&t>MAPC[i+1][0])i++;const a=MAPC[i],b=MAPC[i+1],f=(t-a[0])/(b[0]-a[0]);
  return 'rgb('+a[1].map((x,k)=>Math.round(x+(b[1][k]-x)*f))+')';}
function drawMap(){
  const el=document.getElementById('map'),list=document.getElementById('maplist');
  if(typeof L==='undefined'){el.innerHTML='<div class="empty">No se pudo cargar el mapa. Comprueba tu conexión a internet.</div>';return '';}
  if(!map){map=L.map(el,{preferCanvas:true,zoomSnap:.5});
    const esri='https://server.arcgisonline.com/ArcGIS/rest/services/',at='Tiles © Esri — Esri, HERE, Garmin, OpenStreetMap contributors';
    const gris=L.layerGroup([L.tileLayer(esri+'Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}',{attribution:at,maxZoom:19,maxNativeZoom:16}),
      L.tileLayer(esri+'Canvas/World_Light_Gray_Reference/MapServer/tile/{z}/{y}/{x}',{maxZoom:19,maxNativeZoom:16})]);
    const calles=L.tileLayer(esri+'World_Street_Map/MapServer/tile/{z}/{y}/{x}',{attribution:at,maxZoom:19});
    gris.addTo(map);restLayer=L.layerGroup().addTo(map);layer=L.layerGroup().addTo(map);
    L.control.layers({'Gris claro':gris,'Calles':calles},{'Restaurantes':restLayer,'Arranques':layer},{position:'topright'}).addTo(map);
    const lg=L.control({position:'bottomright'});lg.onAdd=()=>{legendDiv=L.DomUtil.create('div','maplegend');return legendDiv;};lg.addTo(map);
    map.setView([40.2,-3.7],6);}
  map.invalidateSize();layer.clearLayers();restLayer.clearLayers();
  D.rest.filter(r=>st.city==='ALL'||r[2]===st.city).forEach(r=>L.circleMarker([r[0],r[1]],{radius:2.5,color:'#4b5563',weight:0,fillColor:'#4b5563',fillOpacity:.55,interactive:false}).addTo(restLayer));
  const g=new Map();fM().forEach(r=>{let o=g.get(r[3]);if(!o){o={c:D.cells[r[3]],city:r[2],m:[]};g.set(r[3],o);}if(r[4]!=null)o.m.push(r[4]);});
  const pts=[...g.values()].filter(o=>o.m.length>=D.minCell).map(o=>({lat:o.c[0],lon:o.c[1],city:o.city,n:o.m.length,med:median(o.m)}));
  if(!pts.length){list.innerHTML='<div class="empty">Sin datos suficientes</div>';legendDiv.innerHTML='';return 'Sin cuadrículas con al menos '+D.minCell+' conexiones';}
  const nx=Math.max(...pts.map(p=>p.n)),mx=Math.max(20,...pts.map(p=>p.med));
  pts.sort((a,b)=>a.n-b.n).forEach(p=>{p.col=mapColor(p.med/mx);
    p.mk=L.circleMarker([p.lat,p.lon],{radius:5+15*Math.sqrt(p.n/nx),color:'#1b1b1b',weight:1.3,fillColor:p.col,fillOpacity:.85})
      .bindTooltip('<b>'+fmt(p.n)+' conexiones</b> ('+p.city+')<br>Mediana hasta el primer aviso: <b>'+fmt(p.med,0)+' min</b>',{direction:'top'}).addTo(layer);});
  legendDiv.innerHTML='<b>Min hasta el primer aviso (mediana)</b><div class="g" style="background:linear-gradient(90deg,#FEE08B,#FC8D59,#D7301F,#7F0000)"></div><div class="ends"><span>0</span><span>'+fmt(mx/2,0)+'</span><span>'+fmt(mx,0)+'+</span></div><div style="margin-top:4px;color:#555">Tamaño = nº de conexiones · gris = restaurantes</div>';
  const top=pts.slice().sort((a,b)=>b.med-a.med).slice(0,20);
  list.innerHTML='<h4>Zonas donde más tardan · clic para ir</h4>'+top.map((p,i)=>'<div class="ml-item" data-i="'+i+'"><span class="ml-dot" style="background:'+p.col+'"></span><span>'+esc(p.city)+' · '+fmt(p.n)+' conexiones</span><span class="ml-n">'+fmt(p.med,0)+' min</span></div>').join('');
  list.querySelectorAll('.ml-item').forEach(d=>d.onclick=()=>{const p=top[+d.dataset.i];map.setView([p.lat,p.lon],15);p.mk.openTooltip();});
  map.fitBounds(L.latLngBounds(pts.map(p=>[p.lat,p.lon])).pad(0.1),{maxZoom:14});
  return pts.length+' cuadrículas de ~'+D.gridM+' m'+(st.city==='ALL'?' · Elige una ciudad arriba para acercar el mapa':'');
}

function guide(){
  return '<div class="guide"><h2>1 · Qué es el UTR</h2><p><b>UTR = entregas completadas ÷ horas conectadas.</b> Mide cuánto trabajo real sale de cada hora que un rider está disponible en la app. '+
  'Es el mismo UTR que ves en la vista Semanal (las horas conectadas de estos datos cuadran con las horas trabajadas). Un UTR bajo en una franja significa que hay riders conectados esperando: sobran horas. Un UTR muy alto puede indicar que faltan riders.</p>'+
  '<h2>2 · Qué es el arranque de turno</h2><p>Para cada conexión del rider (cada vez que se pone disponible en la app) miramos su <b>primer pedido</b> dentro de esa conexión:</p>'+
  '<div class="gcards"><div><b>Min hasta el primer aviso</b>Desde que se conecta hasta que Glovo le asigna el primer pedido. Alto = se conecta cuando o donde no hay demanda.</div>'+
  '<div><b>Min hasta la primera recogida</b>Desde que se conecta hasta que recoge el primer pedido en el restaurante. Incluye la espera, el desplazamiento y la preparación.</div>'+
  '<div><b>Km hasta el primer restaurante</b>Distancia por carretera (Google) desde donde estaba al recibir el aviso hasta el restaurante. Alto = arranca lejos de los restaurantes.</div>'+
  '<div><b>% conexiones sin pedido</b>Conexiones en las que el rider no recibió ningún pedido. Alto = horas conectadas que no producen nada.</div></div>'+
  '<p style="margin-top:10px">Los datos no incluyen el recorrido GPS completo: solo dónde estaba el rider al recibir el aviso, el restaurante y las distancias.</p>'+
  '<h2>3 · Arranque lejano</h2><p>Una conexión «arranca lejos» cuando el restaurante de su primer pedido está a más de los km elegidos (por defecto 3 km, que en tus datos es 1 de cada 4 conexiones). La vista <b>⚠ Arranque lejano</b> compara el UTR de las conexiones que arrancan lejos con las que arrancan cerca y señala a los riders a los que más les pasa. Qué hacer: pedirles que se conecten cerca de las zonas con restaurantes (ver el mapa de arranque).</p>'+
  '<h2>4 · Qué responde cada vista</h2><div class="gcards">'+Object.entries(HELP).map(([k,v])=>'<div><b>'+esc(v[0])+'</b>'+esc(v[1])+'</div>').join('')+'</div>'+
  '<h2>5 · Colores</h2><p>El color compara las celdas de la misma tabla: <b>verde = mejor, rojo = peor</b>. En UTR, mejor es más alto; en arranque, mejor es más bajo (menos minutos, menos km, menos conexiones sin pedido). No son objetivos de Glovo.</p></div>';}

// ---- controles ----
function buildCity(){const el=document.getElementById('citySeg');
  const opts=[['ALL','Todas']].concat(D.cities.map(c=>[c,c]));
  el.innerHTML=opts.map(o=>'<button data-v="'+o[0]+'"'+(o[0]===st.city?' class="on"':'')+'>'+o[1]+'</button>').join('');
  el.querySelectorAll('button').forEach(b=>b.onclick=()=>{st.city=b.dataset.v;buildCity();render();});}
const ws=document.getElementById('weekSel'),dsel=document.getElementById('daySel');
ws.innerHTML='<option value="ALL">Todas ('+D.weeks[0]+'–'+D.weeks[D.weeks.length-1]+')</option>'+D.weeks.slice().reverse().map(w=>'<option>'+w+'</option>').join('');
function buildDays(){const ds=[...new Set(U.filter(r=>st.week==='ALL'||r[1]===st.week).map(r=>r[0]))].sort().reverse();
  if(st.day!=='ALL'&&!ds.includes(st.day))st.day='ALL';
  dsel.innerHTML='<option value="ALL">Todos los días</option>'+ds.map(d=>'<option value="'+d+'"'+(d===st.day?' selected':'')+'>'+dayLbl(d)+'</option>').join('');}
ws.onchange=e=>{st.week=e.target.value;buildDays();render();};
dsel.onchange=e=>{st.day=e.target.value;render();};
document.getElementById('farSel').onchange=e=>{st.far=+e.target.value;render();};
document.getElementById('metSel').onchange=e=>{st.met=+e.target.value;render();};
document.querySelectorAll('#tabs button').forEach(b=>b.onclick=()=>{st.view=b.dataset.v;
  document.querySelectorAll('#tabs button').forEach(x=>x.classList.toggle('on',x===b));render();});
document.getElementById('csvBtn').onclick=()=>{if(!last)return;const q=s=>'"'+String(s).replace(/"/g,'""')+'"';
  const n=v=>v==null?'':String(Math.round(v*100)/100).replace('.',',');
  const lines=[[last.head].concat(last.colL).concat(last.tot?[last.totName]:[]).map(q).join(';')];
  last.vals.forEach((r,i)=>lines.push([q(last.rowL[i])].concat(r.map(n)).concat(last.tot?[n(last.tot[i])]:[]).join(';')));
  const a=document.createElement('a');a.href=URL.createObjectURL(new Blob(['﻿'+lines.join('\n')],{type:'text/csv;charset=utf-8'}));
  a.download='utr_'+st.view+'_'+st.city+'.csv';a.click();};
document.getElementById('sub').textContent='Fuente: bucket GCP de Glovo (shift_lv + delivery_lv) · '+D.weeks[0]+'–'+D.weeks[D.weeks.length-1]+(D.generated?' · generado '+D.generated:'');
buildCity();buildDays();render();
if(window.parent!==window){const send=()=>window.parent.postMessage({utrH:document.body.getBoundingClientRect().height},'*');
  if(window.ResizeObserver) new ResizeObserver(send).observe(document.body); send();}
</script></body></html>
"""

if __name__ == "__main__":
    main()
