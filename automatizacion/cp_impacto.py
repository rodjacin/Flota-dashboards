#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
================================================================================
 Pestaña "Códigos postales" para los dashboards de flota
================================================================================
 Qué códigos postales pesan más en WTD>10 %, RR % e incidencias de cada nodo,
 por semana, con la variación frente a la semana anterior.

 Fuente: bucket GCP de Glovo (delivery_lv + reassignment_lv, ya combinados por
 combinar_datos_fleet.py) y los polígonos oficiales de códigos postales del CNIG
 (cp_poligonos.json, reducido a las zonas de la flota).

 Asignación del código postal:
   · WTD e incidencias -> código postal del CLIENTE (customer_location).
   · Reasignaciones    -> código postal del RESTAURANTE (vendor_location): casi
     todas ocurren antes de la recogida y muchas las entrega otra flota, así que
     no hay dirección del cliente.

 Definiciones:
   · WTD>10 %  = entregas completadas con > 10 min entre llegar junto al cliente
                 y entregar ÷ entregas completadas (solo la entrega principal).
   · RR %      = reasignaciones ÷ (entregas + reasignaciones) del restaurante.
   · No entregado = pedidos con reembolso UNDELIVERED_RIDER_FRAUD.
   · Cliente ausente = pedidos con contacto por cliente ausente (dato por pedido
                 solo desde septiembre de 2026).
   · CAPU no viene pedido a pedido en el bucket: no se puede repartir por CP.

 Lo usa generar_resumen_flota.py (si está junto a él). También funciona solo:
   python3 cp_impacto.py   ->  ~/Downloads/dashboards/codigos_postales.html
================================================================================
"""
import os
import sys
import json
import datetime

COMB = os.path.expanduser("~/Downloads/fleet_data_combinado")
POLIGONOS = os.path.expanduser("~/Downloads/cp_poligonos.json")
OUTPUT_DIR = os.path.expanduser("~/Downloads/dashboards")
OUTPUT_FILE = "codigos_postales.html"
NODE_ALIASES = {"NEM": "MAD"}
WEEKS_TO_SHOW = 8
WTD_MIN = 10.0


def _cp_de(pd, np, serie, arbol, cps):
    """POINT(lon lat) -> código postal (None si cae fuera de los polígonos)."""
    from shapely import points
    xy = serie.astype(str).str.extract(r"POINT\(([-\d.]+) ([-\d.]+)\)").astype(float)
    ok = xy[0].notna() & xy[1].notna()
    out = np.full(len(serie), None, dtype=object)
    if ok.any():
        idx = np.flatnonzero(ok.values)
        pts = points(xy[0].values[idx], xy[1].values[idx])
        ip, ig = arbol.query(pts, predicate="within")
        out[idx[ip]] = cps[ig]
    return out


def _cargar(cities, semanas):
    import numpy as np
    import pandas as pd
    from shapely.geometry import shape
    from shapely import STRtree
    fd = os.path.join(COMB, "delivery_lv_combinado.csv")
    fr = os.path.join(COMB, "reassignment_lv_combinado.csv")
    for f in (fd, POLIGONOS):
        if not os.path.isfile(f):
            raise ValueError("no encuentro " + f)
    G = json.load(open(POLIGONOS, encoding="utf-8"))
    geoms = [shape(f["geometry"]) for f in G["features"]]
    cps = np.array([f["properties"]["cp"] for f in G["features"]])
    names = {f["properties"]["cp"]: f["properties"].get("mun", "") for f in G["features"]}
    arbol = STRtree(geoms)

    cols = ["p_created_date", "delivery_id", "city_code", "store_name", "zone_name", "delivery_status",
            "is_primary", "rider_near_customer_at", "rider_dropped_off_local_at", "customer_location",
            "vendor_location", "refund_purpose", "is_contact_customer_absent"]
    d = pd.read_csv(fd, dtype=str, keep_default_na=False, usecols=lambda c: c in cols)
    for c in cols:
        if c not in d.columns:
            d[c] = ""
    d = d.drop_duplicates("delivery_id")
    d["_c"] = d["city_code"].str.strip().map(lambda v: NODE_ALIASES.get(v, v))
    d["_d"] = pd.to_datetime(d["p_created_date"].str.slice(0, 10), errors="coerce")
    d = d[d["_d"].notna()].copy()
    iso = d["_d"].dt.isocalendar()
    d["_k"] = iso["year"].astype(int) * 100 + iso["week"].astype(int)
    keys = sorted(d["_k"].unique())[-(semanas or WEEKS_TO_SHOW):]
    d = d[d["_k"].isin(keys)]
    if cities:
        d = d[d["_c"].isin(cities)]
    if d.empty:
        raise ValueError("sin entregas para " + ", ".join(cities or []))

    # --- CP del cliente y del restaurante
    d["_cpc"] = _cp_de(pd, np, d["customer_location"], arbol, cps)
    d["_cpv"] = _cp_de(pd, np, d["vendor_location"], arbol, cps)
    prim = d["is_primary"].str.strip().str.lower().isin(["true", "1"])
    comp = d["delivery_status"].str.strip().eq("completed")
    atc = (pd.to_datetime(d["rider_dropped_off_local_at"].str.slice(0, 19), errors="coerce")
           - pd.to_datetime(d["rider_near_customer_at"].str.slice(0, 19), errors="coerce")).dt.total_seconds() / 60
    base_w = prim & comp & atc.notna() & (atc >= 0)
    d["_n"] = prim.astype(int)                                   # pedidos (entrega principal)
    d["_nw"] = base_w.astype(int)                                # base del WTD
    d["_w10"] = (base_w & (atc > WTD_MIN)).astype(int)
    d["_und"] = (prim & d["refund_purpose"].str.strip().eq("UNDELIVERED_RIDER_FRAUD")).astype(int)
    d["_aus"] = (prim & d["is_contact_customer_absent"].str.strip().str.lower().eq("true")).astype(int)

    cli = d[d["_cpc"].notna()].groupby(["_k", "_c", "_cpc"])[["_n", "_nw", "_w10", "_und", "_aus"]].sum()
    cli.index.names = ["_k", "_c", "_cp"]
    # asignaciones por CP del restaurante: entregas propias (una por delivery)
    asg = d[d["_cpv"].notna()].groupby(["_k", "_c", "_cpv"]).size().rename("_asg")
    asg.index.names = ["_k", "_c", "_cp"]

    # --- reasignaciones -> CP del restaurante (por delivery o por local+zona/ciudad)
    rea = None
    sin_ubic = 0
    if os.path.isfile(fr):
        r = pd.read_csv(fr, dtype=str, keep_default_na=False)
        r = r.drop_duplicates()
        for c in ["p_created_date", "delivery_id", "city_code", "store_name", "zone_name"]:
            if c not in r.columns:
                r[c] = ""
        r["_c"] = r["city_code"].str.strip().map(lambda v: NODE_ALIASES.get(v, v))
        r["_d"] = pd.to_datetime(r["p_created_date"].str.slice(0, 10), errors="coerce")
        r = r[r["_d"].notna()].copy()
        iso = r["_d"].dt.isocalendar()
        r["_k"] = iso["year"].astype(int) * 100 + iso["week"].astype(int)
        r = r[r["_k"].isin(keys)]
        if cities:
            r = r[r["_c"].isin(cities)]
        full = pd.read_csv(fd, dtype=str, keep_default_na=False,
                           usecols=lambda c: c in ["delivery_id", "vendor_location", "store_name", "zone_name", "city_code"])
        full = full[full["vendor_location"].str.len() > 0].drop_duplicates("delivery_id")
        loc = dict(zip(full["delivery_id"], full["vendor_location"]))
        st = full["store_name"].str.strip()
        loc_store = {}
        for col in ["zone_name", "city_code"]:
            ks = pd.DataFrame({"k": st + "|" + full[col].str.strip(), "v": full["vendor_location"]})
            for k_, v_ in ks.groupby("k")["v"].agg(lambda x: x.value_counts().index[0]).items():
                loc_store.setdefault(k_, v_)
        rl = r["delivery_id"].map(loc)
        rl = rl.fillna((r["store_name"].str.strip() + "|" + r["zone_name"].str.strip()).map(loc_store))
        rl = rl.fillna((r["store_name"].str.strip() + "|" + r["city_code"].str.strip()).map(loc_store))
        r["_cp"] = _cp_de(pd, np, rl.fillna(""), arbol, cps)
        sin_ubic = int(r["_cp"].isna().sum())
        rea = r[r["_cp"].notna()].groupby(["_k", "_c", "_cp"]).size().rename("_rea")

    parts = [cli, asg] + ([rea] if rea is not None else [])
    t = pd.concat(parts, axis=1).fillna(0).reset_index()
    if "_rea" not in t.columns:
        t["_rea"] = 0
    t["_asg"] = t["_asg"] + t["_rea"]                            # asignadas = entregadas + reasignadas
    sin_cp = int(d["_cpc"].isna().sum())
    return t, keys, names, d["_d"].max().date(), sin_cp, sin_ubic


def construir_html(cities=None, semanas=None, sello=True):
    t, keys, names, max_d, sin_cp, sin_ubic = _cargar(cities, semanas)
    kidx = {k: i for i, k in enumerate(keys)}
    weeks, wrange = [], []
    for k in keys:
        y, w = divmod(int(k), 100)
        mon = datetime.date.fromisocalendar(y, w, 1)
        weeks.append("W" + str(w))
        wrange.append(mon.strftime("%d/%m") + "–" + (mon + datetime.timedelta(days=6)).strftime("%d/%m"))
    rows = []
    for k, c, cp, n, nw, w10, und, aus, asg, rea in t[["_k", "_c", "_cp", "_n", "_nw", "_w10", "_und", "_aus", "_asg", "_rea"]].itertuples(index=False, name=None):
        rows.append([kidx[k], c, cp] + [int(round(v)) for v in (n, nw, w10, und, aus, asg, rea)])
    rows.sort(key=lambda r: (r[0], r[1], r[2]))
    used = {r[2] for r in rows}
    data = {
        "weeks": weeks, "wrange": wrange, "lastDate": max_d.isoformat(), "curPartial": max_d.weekday() < 6,
        "cities": sorted({r[1] for r in rows}), "names": {cp: names.get(cp, "") for cp in sorted(used)},
        "rows": rows, "wtdMin": WTD_MIN, "sinCp": sin_cp, "sinUbic": sin_ubic,
        "generated": datetime.datetime.now().strftime("%d/%m/%Y %H:%M") if sello else "",
    }
    html = HTML.replace("__DATA__", json.dumps(data, ensure_ascii=False, separators=(",", ":")))
    NW = sum(r[4] for r in rows); W10 = sum(r[5] for r in rows)
    res = ("WTD>10 " + ("%.1f" % (100.0 * W10 / NW if NW else 0)).replace(".", ",") + " % · "
           + str(len(used)) + " CP · " + weeks[0] + "–" + weeks[-1] + " · " + ", ".join(data["cities"]))
    return html, res


HTML = r'''<!DOCTYPE html><html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Códigos postales · impacto</title>
<style>
:root{--bg:#F6F7F9;--surface:#FFFFFF;--line:#E4E7EC;--ink:#14171F;--ink2:#4B5563;--muted:#6B7280;--acc:#0E5A6B;--chip:#EEF1F4;
--bad:#C2362B;--badbg:rgba(194,54,43,.10);--good:#0A7F4F;--goodbg:rgba(10,127,79,.10);--bar:#0E5A6B}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font-family:"Inter",-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;font-size:14px;padding:0 0 24px}
.wrap{display:flex;flex-direction:column;gap:16px}
h1{font-size:18px;font-weight:650;margin:0}
h2{font-size:12px;letter-spacing:.06em;text-transform:uppercase;font-weight:650;margin:0}
.sub{color:var(--ink2);margin:5px 0 0;max-width:110ch;line-height:1.5;font-size:13px}
.mono,.n{font-family:ui-monospace,"SF Mono",Menlo,Consolas,monospace;font-variant-numeric:tabular-nums}
.filters{background:var(--surface);border:1px solid var(--line);border-radius:12px;padding:14px 16px;display:flex;flex-wrap:wrap;gap:16px;align-items:flex-end}
.fg{display:flex;flex-direction:column;gap:6px}.fg[hidden]{display:none}
.fg>span{font-family:ui-monospace,"SF Mono",Menlo,monospace;font-size:11px;letter-spacing:.07em;text-transform:uppercase;color:var(--muted)}
.seg{display:inline-flex;flex-wrap:wrap;background:var(--bg);border:1px solid var(--line);border-radius:9px;padding:3px;gap:2px}
.seg button{font:inherit;font-size:13px;border:0;background:transparent;color:var(--ink2);border-radius:7px;padding:6px 11px;cursor:pointer}
.seg button:hover{color:var(--ink)}.seg button.on{background:var(--acc);color:#fff}
.seg button:focus-visible{outline:2px solid var(--acc);outline-offset:2px}
label.chk{display:flex;gap:6px;align-items:center;font-size:13px;color:var(--ink2);cursor:pointer;padding:6px 0}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:10px}
.kpi{background:var(--surface);border:1px solid var(--line);border-radius:12px;padding:12px 14px;display:flex;flex-direction:column;gap:4px}
.kpi b{font-size:22px;font-weight:650;font-family:ui-monospace,"SF Mono",Menlo,monospace;font-variant-numeric:tabular-nums}
.kpi span{font-size:12px;color:var(--ink2)}
.kpi em{font-style:normal;font-family:ui-monospace,"SF Mono",Menlo,monospace;font-size:11px;letter-spacing:.06em;text-transform:uppercase;color:var(--muted)}
.panel{background:var(--surface);border:1px solid var(--line);border-radius:12px;padding:14px;display:flex;flex-direction:column;gap:10px;min-width:0}
.ph{display:flex;justify-content:space-between;gap:10px;flex-wrap:wrap;align-items:baseline}.ph p{margin:0;color:var(--ink2);font-size:12.5px}
.tw{overflow-x:auto}
table{border-collapse:collapse;width:100%}
th,td{padding:6px 7px;text-align:left;border-bottom:1px solid var(--line);white-space:nowrap;font-size:12.5px}
th{font-family:ui-monospace,"SF Mono",Menlo,monospace;font-size:10.5px;letter-spacing:.05em;text-transform:uppercase;color:var(--muted);font-weight:500;background:var(--surface);position:sticky;top:0}
th.grp{text-align:center;border-bottom:0;color:var(--ink2);font-weight:650}
th.sep,td.sep{border-left:1px solid var(--line)}
th.srt{cursor:pointer}th.srt:hover{color:var(--ink)}
td.n,th.n{text-align:right}
tbody tr.row{cursor:pointer}tbody tr.row:hover td{background:var(--chip)}tr.open td{background:var(--chip)}
tr.det td{background:#FAFBFC;padding:10px 12px}
.imp{display:inline-flex;align-items:center;gap:6px;justify-content:flex-end;width:100%}
.imp i{display:inline-block;height:7px;border-radius:0 3px 3px 0;background:var(--bar);opacity:.8}
.up{color:var(--bad)}.down{color:var(--good)}.flat{color:var(--muted)}
.hi{color:var(--bad);font-weight:600}
.pill{display:inline-block;padding:1px 8px;border-radius:99px;font-size:12px;background:var(--chip);color:var(--ink2)}
.empty{color:var(--muted);padding:16px 0}
.note{color:var(--muted);font-size:12px;line-height:1.55;max-width:130ch;margin:0}
.mini{border-collapse:collapse;width:auto}.mini th,.mini td{padding:4px 10px;font-size:12px;position:static}
[data-def]{cursor:help}
.kpi em[data-def],th[data-def],h2[data-def]{text-decoration:underline dotted;text-underline-offset:3px}
#defTip{position:fixed;z-index:50;max-width:320px;background:#14171F;color:#fff;font-size:12px;line-height:1.45;padding:8px 10px;border-radius:7px;pointer-events:none;box-shadow:0 4px 14px rgba(0,0,0,.18);text-transform:none;letter-spacing:0;font-weight:400}
#defTip[hidden]{display:none}
</style></head><body>
<div class="wrap">
  <header><h1>Códigos postales · impacto en WTD, reasignaciones e incidencias</h1>
    <p class="sub" id="sub"></p></header>
  <div class="filters">
    <div class="fg" id="fgCity"><span>Ciudad</span><div class="seg" id="fCity"></div></div>
    <div class="fg"><span>Semana</span><div class="seg" id="fWeek"></div></div>
    <div class="fg"><span>Ordenar por impacto en</span><div class="seg" id="fSort"></div></div>
    <div class="fg"><span>&nbsp;</span><label class="chk"><input type="checkbox" id="fMin" checked> Solo CP con ≥ 30 pedidos</label></div>
  </div>
  <section class="kpis" id="kpis"></section>
  <section class="panel">
    <div class="ph"><h2 data-def="Una fila por código postal. «Impacto» = parte de los casos de la ciudad que salen de ese CP. «WoW» = variación en puntos de la tasa frente a la semana anterior (rojo = empeora). Clic en una fila para ver su evolución semana a semana.">Impacto por código postal</h2><p id="tSub"></p></div>
    <div class="tw" style="max-height:1100px"><table id="t"></table></div>
  </section>
  <p class="note" id="note"></p>
</div>
<script>
const D=__DATA__;
const $=id=>document.getElementById(id);
const nf=(v,d=0)=>v==null||isNaN(v)?'—':Number(v).toLocaleString('es-ES',{minimumFractionDigits:d,maximumFractionDigits:d});
const pc=v=>v==null||isNaN(v)?'—':nf(v*100,1)+' %';
const esc=s=>String(s??'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const NW=D.weeks.length;
// fila: [w, ciudad, cp, n, nw, w10, und, aus, asg, rea]
const M={wtd:{l:'WTD>10',num:r=>r[5],den:r=>r[4],d:'Entregas con más de '+D.wtdMin+' min entre llegar junto al cliente y entregar ÷ entregas completadas. CP del cliente.'},
 rr:{l:'RR',num:r=>r[9],den:r=>r[8],d:'Reasignaciones ÷ pedidos asignados (entregados + reasignados) de los restaurantes de ese CP. Se usa el CP del restaurante porque casi todas las reasignaciones ocurren antes de la recogida.'},
 inc:{l:'Incidencias',num:r=>r[6]+r[7],den:r=>r[3],d:'No entregado (reembolso por fraude de entrega) + cliente ausente (contacto de cliente ausente), ÷ pedidos. CP del cliente.'}};
const S={city:D.cities.length>1?'ALL':D.cities[0],week:NW-1,sort:'wtd',min:true,open:null,col:null,dir:-1};
if(D.cities.length<2)$('fgCity').hidden=true;
function seg(id,opts,val,on){const el=$(id);el.innerHTML=opts.map(o=>`<button data-v="${o.v}" class="${String(o.v)===String(val)?'on':''}" title="${o.t||''}">${o.l}</button>`).join('');el.onclick=e=>{const b=e.target.closest('button');if(b)on(b.dataset.v);};}
const inCity=r=>S.city==='ALL'||r[1]===S.city;
function agg(wsel){ // wsel: índice de semana o 'ALL'
  const by={},T=[0,0,0,0,0,0,0];
  D.rows.forEach(r=>{if(!inCity(r)||(wsel!=='ALL'&&r[0]!==+wsel))return;
    const k=r[1]+'|'+r[2];const a=by[k]||(by[k]={city:r[1],cp:r[2],v:[0,0,0,0,0,0,0]});
    for(let i=0;i<7;i++){a.v[i]+=r[3+i];T[i]+=r[3+i];}});
  return {by,T};
}
const rate=(m,v)=>{const x=[0,0,0].concat(v);const den=M[m].den(x);return den?M[m].num(x)/den:null;};
const cases=(m,v)=>M[m].num([0,0,0].concat(v));
function render(){
  seg('fCity',[{v:'ALL',l:'Todas'}].concat(D.cities.map(c=>({v:c,l:c}))),S.city,v=>{S.city=v;S.open=null;render();});
  seg('fWeek',D.weeks.map((w,i)=>({v:i,l:w+(i===NW-1&&D.curPartial?'*':''),t:D.wrange[i]})).concat([{v:'ALL',l:NW+' sem.',t:'Todo el periodo'}]),S.week,v=>{S.week=v==='ALL'?'ALL':+v;S.open=null;render();});
  seg('fSort',[{v:'wtd',l:'WTD>10 %'},{v:'rr',l:'RR %'},{v:'inc',l:'Incidencias'}],S.sort,v=>{S.sort=v;S.col=null;render();});
  const cur=agg(S.week);
  const pw=S.week==='ALL'?NW-2:S.week-1, cw=S.week==='ALL'?NW-1:S.week;
  const prev=pw>=0?agg(pw):null, curw=S.week==='ALL'?agg(cw):cur;
  const scope=(S.city==='ALL'?'todas las ciudades':S.city)+' · '+(S.week==='ALL'?D.weeks[0]+'–'+D.weeks[NW-1]:D.weeks[S.week]+' ('+D.wrange[S.week]+')');
  const wowTxt=S.week==='ALL'?('WoW = '+D.weeks[cw]+' vs '+D.weeks[pw]):(pw>=0?'WoW vs '+D.weeks[pw]:'sin semana anterior');
  $('sub').innerHTML='Qué códigos postales concentran los problemas de cada ciudad. '+esc(scope)+' · '+esc(wowTxt)+(D.curPartial?' · * semana en curso (datos hasta '+D.lastDate.slice(8,10)+'/'+D.lastDate.slice(5,7)+')':'');
  // KPIs de la ciudad
  const kd=(m)=>{const a=rate(m,curw.T),b=prev?rate(m,prev.T):null;return a!=null&&b!=null?(a-b):null;};
  const wowS=(x,small)=>x==null?'':`<span class="${x>0.0005?'up':x<-0.0005?'down':'flat'}">${x>0?'▲':x<0?'▼':'='} ${nf(Math.abs(x*100),1)} pp</span>`;
  const top=m=>{let b=null;Object.values(cur.by).forEach(a=>{if(S.min&&a.v[0]<30)return;const c=cases(m,a.v);if(!b||c>b.c)b={c,a};});const tot=cases(m,cur.T);return b&&tot?`Top: ${b.a.cp} ${esc(D.names[b.a.cp]||'')} · ${nf(b.c/tot*100,0)} % de los casos`:'—';};
  $('kpis').innerHTML=[
    ['Pedidos',nf(cur.T[0]),Object.keys(cur.by).length+' códigos postales','Pedidos (entrega principal) con código postal del cliente en el filtro.'],
    ['WTD>10 %',pc(rate('wtd',cur.T))+' '+wowS(kd('wtd')),top('wtd'),M.wtd.d],
    ['RR %',pc(rate('rr',cur.T))+' '+wowS(kd('rr')),top('rr'),M.rr.d],
    ['Incidencias',nf(cases('inc',cur.T))+' <span style="font-size:13px;color:var(--ink2)">('+pc(rate('inc',cur.T))+')</span> '+wowS(kd('inc')),top('inc'),M.inc.d],
  ].map(([e,b,s,d])=>`<div class="kpi"><em data-def="${esc(d)}" tabindex="0">${e}</em><b>${b}</b><span>${s}</span></div>`).join('');
  // tabla
  const cityT={};Object.values(cur.by).forEach(a=>{const t=cityT[a.city]||(cityT[a.city]=[0,0,0,0,0,0,0]);a.v.forEach((x,i)=>t[i]+=x);});
  let rs=Object.values(cur.by).filter(a=>!S.min||a.v[0]>=30);
  rs.forEach(a=>{const ct=cityT[a.city];a.m={};['wtd','rr','inc'].forEach(m=>{const c=cases(m,a.v),tc=cases(m,ct),r=rate(m,a.v),cr=rate(m,ct);
      const pv=prev&&prev.by[a.city+'|'+a.cp],cv=curw.by[a.city+'|'+a.cp];
      const wa=cv?rate(m,cv.v):null,wb=pv?rate(m,pv.v):null;
      a.m[m]={c,r,imp:tc?c/tc:0,pp:(ct&&M[m].den([0,0,0].concat(ct)))?(c-(r==null?0:M[m].den([0,0,0].concat(a.v))*cr))/M[m].den([0,0,0].concat(ct)):0,wow:wa!=null&&wb!=null?wa-wb:null};});});
  const sk=S.col||(S.sort+'.imp');
  const gv=(a,k)=>{if(k==='n')return a.v[0];if(k==='cp')return a.cp;const [m,f]=k.split('.');return a.m[m][f];};
  rs.sort((x,y)=>{const a=gv(x,sk),b=gv(y,sk);if(a==null)return 1;if(b==null)return -1;return (typeof a==='string'?a.localeCompare(b):a-b)*(S.col?S.dir:-1);});
  const mx={};['wtd','rr','inc'].forEach(m=>mx[m]=Math.max(0.0001,...rs.map(a=>a.m[m].imp)));
  const th=(k,l,d,cls)=>`<th class="srt n ${cls||''}" data-k="${k}" data-def="${esc(d)}">${l}${sk===k?(S.col&&S.dir>0?' ▲':' ▼'):''}</th>`;
  const hdr='<thead><tr><th colspan="'+(S.city==='ALL'?4:3)+'"></th>'+['wtd','rr','inc'].map(m=>`<th class="grp sep" colspan="${m==='inc'?5:4}" data-def="${esc(M[m].d)}">${M[m].l}${m==='rr'?' <span class="pill">CP restaurante</span>':''}</th>`).join('')+'</tr><tr>'+
    (S.city==='ALL'?'<th>Ciudad</th>':'')+'<th class="srt" data-k="cp">Código postal</th><th>Zona</th>'+th('n','Pedidos','Pedidos con código postal del cliente (entrega principal).')+
    ['wtd','rr','inc'].map(m=>(m==='inc'?`<th class="n sep" data-def="No entregado (reembolso por fraude de entrega) · cliente ausente (contacto; solo desde septiembre).">N.E. · aus.</th>`:'')+th(m+'.r',m==='inc'?'Tasa':'%','Tasa de '+M[m].l+' del CP.',m==='inc'?'':'sep')+th(m+'.imp','Impacto','Parte de los casos de '+M[m].l+' de la ciudad que salen de este CP. Pasa el ratón para ver cuántos puntos bajaría la tasa de la ciudad si este CP estuviera en la media.')+th(m+'.wow','WoW','Variación de la tasa del CP frente a la semana anterior, en puntos porcentuales. Rojo = empeora.')+th(m+'.c','Casos','Número de casos en el filtro.')).join('')+'</tr></thead>';
  const wowC=x=>x==null?'<span class="flat">—</span>':`<span class="${x>0.0005?'up':x<-0.0005?'down':'flat'}">${x>0?'▲':x<0?'▼':'='} ${nf(Math.abs(x*100),1)}</span>`;
  const impC=(m,a)=>{const i=a.m[m].imp;return `<span class="imp" title="${a.m[m].pp>0?'Sin este exceso la tasa de la ciudad bajaría '+nf(a.m[m].pp*100,2)+' pp':'Por debajo o en la media de la ciudad'}"><i style="width:${Math.round(i/mx[m]*46)}px"></i>${nf(i*100,1)} %</span>`;};
  const ncol=(S.city==='ALL'?4:3)+13;
  let body='';
  rs.forEach(a=>{const k=a.city+'|'+a.cp;const hiR=m=>{const cr=rate(m,cityT[a.city]);return a.m[m].r!=null&&cr!=null&&a.m[m].r>cr*1.25&&a.m[m].c>=3?'hi':'';};
    body+=`<tr class="row ${S.open===k?'open':''}" data-k="${k}">`+(S.city==='ALL'?`<td><span class="pill">${a.city}</span></td>`:'')+`<td class="mono">${a.cp}</td><td>${esc(D.names[a.cp]||'')}</td><td class="n">${nf(a.v[0])}</td>`+
    ['wtd','rr','inc'].map(m=>(m==='inc'?`<td class="n sep">${nf(a.v[3])} · ${nf(a.v[4])}</td>`:'')+`<td class="n ${m==='inc'?'':'sep'} ${hiR(m)}">${pc(a.m[m].r)}</td><td class="n">${impC(m,a)}</td><td class="n mono">${wowC(a.m[m].wow)}</td><td class="n">${nf(a.m[m].c)}</td>`).join('')+'</tr>';
    if(S.open===k)body+=`<tr class="det"><td colspan="${ncol}">${detail(a.city,a.cp)}</td></tr>`;});
  $('t').innerHTML=rs.length?hdr+'<tbody>'+body+'</tbody>':'<tbody><tr><td class="empty">Sin códigos postales con datos en este filtro.</td></tr></tbody>';
  $('t').querySelectorAll('th.srt').forEach(h=>h.onclick=()=>{const k=h.dataset.k;if(S.col===k)S.dir*=-1;else{S.col=k;S.dir=k==='cp'?1:-1;}render();});
  $('t').querySelectorAll('tr.row').forEach(tr=>tr.onclick=()=>{S.open=S.open===tr.dataset.k?null:tr.dataset.k;render();});
  $('tSub').textContent=nf(rs.length)+' códigos postales'+(S.min?' con ≥ 30 pedidos':'')+' · orden: '+(S.col?'columna elegida':'impacto en '+M[S.sort].l);
  $('note').innerHTML='Fuente: bucket GCP de Glovo (delivery_lv y reassignment_lv) y polígonos de códigos postales del CNIG. WTD e incidencias se asignan al código postal del <b>cliente</b>; las reasignaciones, al del <b>restaurante</b>. '+
    'Las tasas de esta pestaña se calculan pedido a pedido y pueden diferir unas décimas de las de la vista Semanal (que usa el agregado por rider de Glovo). CAPU no viene pedido a pedido en el bucket y no se puede repartir por código postal; «cliente ausente» por pedido solo existe desde septiembre. '+
    (D.sinCp?nf(D.sinCp)+' pedidos sin código postal (coordenadas fuera del mapa) no entran. ':'')+(D.sinUbic?nf(D.sinUbic)+' reasignaciones sin ubicación del restaurante no entran.':'');
  applyDefs();
}
function detail(city,cp){
  const W=D.weeks.map((w,i)=>{const v=[0,0,0,0,0,0,0];D.rows.forEach(r=>{if(r[0]===i&&r[1]===city&&r[2]===cp)for(let j=0;j<7;j++)v[j]+=r[3+j];});
    const ct=[0,0,0,0,0,0,0];D.rows.forEach(r=>{if(r[0]===i&&r[1]===city)for(let j=0;j<7;j++)ct[j]+=r[3+j];});return {w,v,ct};});
  return `<b>${cp} ${esc(D.names[cp]||'')}</b> · ${city} · evolución semanal (entre paréntesis, la media de ${city})<table class="mini"><thead><tr><th>Semana</th><th class="n">Pedidos</th><th class="n">WTD>10 %</th><th class="n">RR %</th><th class="n">Incidencias</th></tr></thead><tbody>`+
    W.map(x=>`<tr><td class="mono">${x.w}</td><td class="n">${nf(x.v[0])}</td>`+['wtd','rr','inc'].map(m=>`<td class="n">${pc(rate(m,x.v))} <span class="flat">(${pc(rate(m,x.ct))})</span></td>`).join('')+'</tr>').join('')+'</tbody></table>';
}
function applyDefs(){document.querySelectorAll('th[data-def],em[data-def],h2[data-def]').forEach(e=>{if(!e.tabIndex||e.tabIndex<0)e.tabIndex=0;});}
$('fMin').onchange=e=>{S.min=e.target.checked;render();};
(function(){const tip=document.createElement('div');tip.id='defTip';tip.hidden=true;document.body.appendChild(tip);
  const place=(x,y)=>{const w=tip.offsetWidth,h=tip.offsetHeight;let l=x+12,t=y+14;if(l+w>innerWidth-8)l=Math.max(8,x-w-12);if(t+h>innerHeight-8)t=Math.max(8,y-h-12);tip.style.left=l+'px';tip.style.top=t+'px';};
  document.addEventListener('mouseover',e=>{const el=e.target.closest('[data-def]');if(el){tip.textContent=el.dataset.def;tip.hidden=false;place(e.clientX,e.clientY);}});
  document.addEventListener('mousemove',e=>{if(!tip.hidden&&e.target.closest('[data-def]'))place(e.clientX,e.clientY);});
  document.addEventListener('mouseout',e=>{const el=e.target.closest('[data-def]');if(el&&!el.contains(e.relatedTarget))tip.hidden=true;});})();
render();
if(window.parent!==window){const send=()=>window.parent.postMessage({cpH:document.body.getBoundingClientRect().height},'*');
  if(window.ResizeObserver) new ResizeObserver(send).observe(document.body); send();}
</script></body></html>'''

_BTN = '<button data-v="cpostal" aria-pressed="false">Códigos postales</button>'


def integrar_en_dashboard(dash_html, cp_html):
    """Añade la pestaña 'Códigos postales' al selector Vista del dashboard (en un iframe aislado)."""
    if 'id="viewCP"' in dash_html:
        return dash_html
    ancla = None
    for a in ['<button data-v="envivo" aria-pressed="false">En vivo</button>',
              '<button data-v="capacidad" aria-pressed="false">Capacidad</button>',
              '<button data-v="noshow" aria-pressed="false">No show</button>',
              '<button data-v="utr" aria-pressed="false">UTR</button>']:
        if a in dash_html:
            ancla = a
            break
    sec_ancla = '<div id="viewSemanal">'
    if not ancla or sec_ancla not in dash_html or "</body>" not in dash_html:
        raise ValueError("la plantilla no tiene el selector de Vista esperado")
    dash_html = dash_html.replace(ancla, ancla + "\n        " + _BTN, 1)
    dash_html = dash_html.replace(sec_ancla,
        '<section id="viewCP" style="display:none"><iframe id="cpFrame" title="Códigos postales" '
        'style="width:100%;height:1200px;border:0;display:block;background:transparent"></iframe></section>\n  '
        + sec_ancla, 1)
    src = json.dumps(cp_html, ensure_ascii=False).replace("<", "\\u003c")
    js = ("<script>\n/* ==== Pestaña Códigos postales ==== */\n(function(){\n"
          "  const CP_HTML=" + src + ";\n"
          "  const seg=document.getElementById('viewSeg'),sec=document.getElementById('viewCP'),fr=document.getElementById('cpFrame');\n"
          "  if(!seg||!sec||!fr) return; let loaded=false;\n"
          "  seg.querySelectorAll('button').forEach(b=>b.addEventListener('click',()=>{\n"
          "    const on=b.dataset.v==='cpostal'; sec.style.display=on?'':'none';\n"
          "    if(on){ seg.querySelectorAll('button').forEach(x=>x.setAttribute('aria-pressed',String(x===b)));\n"
          "      document.querySelectorAll('[id^=\"view\"]').forEach(e=>{ if(e!==sec && e!==seg && e.id!=='viewSeg') e.style.display='none'; });\n"
          "      if(!loaded){ fr.srcdoc=CP_HTML; loaded=true; } window.scrollTo(0,0); }\n"
          "  }));\n"
          "  window.addEventListener('message',e=>{ if(e.source===fr.contentWindow && e.data && e.data.cpH){\n"
          "    fr.style.height=Math.max(600,Math.ceil(e.data.cpH)+20)+'px'; } });\n"
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


if __name__ == "__main__":
    main()
