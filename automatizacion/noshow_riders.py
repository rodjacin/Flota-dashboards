#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
================================================================================
 Pestaña "No show" para los dashboards de flota
================================================================================
 No show desglosado por rider:
   · % de no show de cada rider por semana, con los días de la semana en que
     falló (para ver patrones y evaluar si las acciones funcionan)
   · Rider × día de la semana (Lun..Dom)
   · Registro de cada día con no show (día completo o parcial)

 Definición (igual que el dato de Glovo):
   total_no_shows y total_booked_shifts son FRANJAS DE 30 MIN.
   % no show = franjas no presentadas ÷ franjas reservadas.
   Horas de no show = franjas × 0,5.

 Lo usa generar_resumen_flota.py (si está junto a él). También funciona solo:
   python3 noshow_riders.py   ->  ~/Downloads/dashboards/no_show_riders.html
================================================================================
"""

import os
import sys
import json
import datetime

INPUT_FILE = os.path.expanduser("~/Downloads/fleet_data_combinado/rider_lv_combinado.csv")
OUTPUT_DIR = os.path.expanduser("~/Downloads/dashboards")
OUTPUT_FILE = "no_show_riders.html"
NODE_ALIASES = {"NEM": "MAD"}
WEEKS_TO_SHOW = 8
SLOT_H = 0.5          # cada franja reservada = 30 min


def _cargar(cities, semanas):
    import pandas as pd
    if not os.path.isfile(INPUT_FILE):
        raise ValueError("no encuentro " + INPUT_FILE)
    df = pd.read_csv(INPUT_FILE, dtype=str, keep_default_na=False)
    for c in ["fecha", "rider_id", "city_code", "total_no_shows", "total_booked_shifts"]:
        if c not in df.columns:
            raise ValueError("falta la columna '" + c + "' en " + os.path.basename(INPUT_FILE))
    df["_c"] = df["city_code"].astype(str).str.strip().map(lambda v: NODE_ALIASES.get(v, v))
    if cities:
        df = df[df["_c"].isin(cities)]
    df["_d"] = pd.to_datetime(df["fecha"], errors="coerce")
    df = df[df["_d"].notna()].copy()
    if df.empty:
        raise ValueError("sin datos para " + ", ".join(cities or []))
    num = lambda c: pd.to_numeric(df[c], errors="coerce").fillna(0.0) if c in df.columns else 0.0
    df["_b"] = num("total_booked_shifts")
    df["_n"] = num("total_no_shows")
    df["_w"] = num("total_worked_hours")
    iso = df["_d"].dt.isocalendar()
    df["_k"] = iso["year"].astype(int) * 100 + iso["week"].astype(int)
    keys = sorted(df["_k"].unique())[-(semanas or WEEKS_TO_SHOW):]
    df = df[df["_k"].isin(keys)]
    g = df.groupby(["rider_id", "_c", "_d", "_k"], as_index=False)[["_b", "_n", "_w"]].sum()
    return g, keys


def construir_html(cities=None, semanas=None, sello=True):
    g, keys = _cargar(cities, semanas)
    kidx = {k: i for i, k in enumerate(keys)}
    weeks, wrange = [], []
    for k in keys:
        y, w = divmod(int(k), 100)
        mon = datetime.date.fromisocalendar(y, w, 1)
        weeks.append("W" + str(w))
        wrange.append(mon.strftime("%d/%m") + "–" + (mon + datetime.timedelta(days=6)).strftime("%d/%m"))
    max_d = g["_d"].max().date()
    cur_partial = max_d.weekday() < 6          # la última semana no llega a domingo
    rows = []
    for rid, c, d, k, b, n, w in g.itertuples(index=False, name=None):
        if b <= 0:
            continue
        dd = d.date()
        rows.append([dd.isoformat(), kidx[k], dd.weekday(), c, str(rid), int(round(b)), int(round(n)), round(float(w), 2)])
    rows.sort(key=lambda r: (r[0], r[3], r[4]))
    B = sum(r[5] for r in rows)
    N = sum(r[6] for r in rows)
    data = {
        "weeks": weeks, "wrange": wrange, "curPartial": cur_partial, "lastDate": max_d.isoformat(),
        "cities": sorted(set(r[3] for r in rows)), "slotH": SLOT_H, "rows": rows,
        "generated": datetime.datetime.now().strftime("%d/%m/%Y %H:%M") if sello else "",
    }
    html = HTML.replace("__DATA__", json.dumps(data, ensure_ascii=False, separators=(",", ":")))
    pct = (100.0 * N / B) if B else 0.0
    res = ("No show " + ("%.1f" % pct).replace(".", ",") + " % · " + str(int(N * SLOT_H)) + " h · "
           + weeks[0] + "–" + weeks[-1] + " · " + ", ".join(data["cities"]))
    return html, res


_BTN = '<button data-v="noshow" aria-pressed="false">No show</button>'


def integrar_en_dashboard(dash_html, ns_html):
    """Añade la pestaña 'No show' al selector Vista del dashboard (en un iframe aislado)."""
    if 'id="viewNoShow"' in dash_html:
        return dash_html
    ancla = None
    for a in ['<button data-v="utr" aria-pressed="false">UTR</button>',
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
        '<section id="viewNoShow" style="display:none"><iframe id="nsFrame" title="No show por rider" '
        'style="width:100%;height:1200px;border:0;display:block;background:transparent"></iframe></section>\n  '
        + sec_ancla, 1)
    # "<" -> <: sin etiquetas literales dentro (el perl de publicar_dashboards.sh no puede romperlo)
    src = json.dumps(ns_html, ensure_ascii=False).replace("<", "\\u003c")
    js = ("<script>\n/* ==== Pestaña No show por rider ==== */\n(function(){\n"
          "  const NS_HTML=" + src + ";\n"
          "  const seg=document.getElementById('viewSeg'),sec=document.getElementById('viewNoShow'),fr=document.getElementById('nsFrame');\n"
          "  if(!seg||!sec||!fr) return; let loaded=false;\n"
          "  seg.querySelectorAll('button').forEach(b=>b.addEventListener('click',()=>{\n"
          "    const on=b.dataset.v==='noshow'; sec.style.display=on?'':'none';\n"
          "    if(on){ seg.querySelectorAll('button').forEach(x=>x.setAttribute('aria-pressed',String(x===b)));\n"
          "      ['viewSemanal','viewDiario','viewLiga','viewHeat','viewUtr'].forEach(id=>{const e=document.getElementById(id); if(e) e.style.display='none';});\n"
          "      if(!loaded){ fr.srcdoc=NS_HTML; loaded=true; } window.scrollTo(0,0); }\n"
          "  }));\n"
          "  window.addEventListener('message',e=>{ if(e.source===fr.contentWindow && e.data && e.data.nsH){\n"
          "    fr.style.height=Math.max(600,Math.ceil(e.data.nsH)+20)+'px'; } });\n"
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
<title>No show por rider</title>
<style>
:root{--bg:#F6F7F9;--panel:#FFFFFF;--panel2:#F9FAFB;--line:#E4E7EC;--line2:#D3D8E0;--tx:#14171F;--tx2:#374151;--dim:#6B7280;--dimmer:#C2C8D0;--acc:#0E5A6B;--accsoft:#E3F0F2;--hover:#EEF2F5;--bad:#B5342A;--good:#167C58}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--tx);font:14px/1.45 "Inter",-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif}
.wrap{padding:0 0 24px}
h1{font-size:17px;margin:0 0 2px}.sub{color:var(--dim);font-size:12.5px}
.bar{display:flex;flex-wrap:wrap;gap:14px;align-items:flex-end;margin:14px 0 12px;padding:12px;background:var(--panel);border:1px solid var(--line);border-radius:12px}
.field{display:flex;flex-direction:column;gap:5px}
.lbl{font-size:11px;text-transform:uppercase;letter-spacing:.06em;color:var(--dim)}
select,input{background:#fff;color:var(--tx);border:1px solid var(--line2);border-radius:8px;padding:7px 10px;font:inherit;font-size:13px}
select{min-width:150px}input{width:150px}
.seg{display:flex;flex-wrap:wrap;gap:4px}
.seg button,.tabs button{background:#fff;color:var(--dim);border:1px solid var(--line2);border-radius:8px;padding:6px 11px;font:inherit;font-size:13px;cursor:pointer}
.seg button.on,.tabs button.on{background:var(--accsoft);color:var(--acc);border-color:var(--acc)}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:10px;margin-bottom:12px}
.kpi{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:10px 14px}
.kpi b{display:block;font-size:20px;font-variant-numeric:tabular-nums}.kpi span{font-size:11.5px;color:var(--dim)}
.kpi em{font-style:normal;font-size:12px;font-weight:600;margin-left:6px}
.trend{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:10px 14px 6px;margin-bottom:12px}
.trend h3{font-size:13px;margin:0 0 2px}.trend .s{font-size:12px;color:var(--dim)}
.trend svg{width:100%;height:auto;display:block}
.tabs{display:flex;flex-wrap:wrap;gap:6px;margin-bottom:10px}
.card{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:14px}
.hbox{border:1px solid var(--line2);border-radius:10px;padding:10px 12px;font-size:12.5px;color:var(--tx2);background:var(--panel2);margin-bottom:12px}
.hbox b.t{display:block;font-size:11px;text-transform:uppercase;letter-spacing:.06em;color:var(--dim);margin-bottom:3px}
.scroll{overflow-x:auto}
table.hm{border-collapse:separate;border-spacing:2px;font-size:12px;font-variant-numeric:tabular-nums}
table.hm th{color:var(--dim);font-weight:600;padding:4px 6px;white-space:nowrap;text-align:center;background:var(--panel);vertical-align:bottom}
table.hm th small{display:block;font-weight:400;font-size:10.5px}
table.hm td{padding:4px 6px;text-align:center;border-radius:4px;min-width:58px;white-space:nowrap;color:#14171F}
table.hm .lft{text-align:left;position:sticky;left:0;background:var(--panel);z-index:1;min-width:130px}
table.hm td.tot{font-weight:650;color:var(--tx2)}
table.hm tr.totrow td{font-weight:650;color:var(--tx2);border-top:1px solid var(--line2)}
table.hm td .d{display:block;font-size:10.5px;color:#7A2A22;font-weight:600;margin-top:1px}
table.hm td.z{color:var(--dimmer)}
table.hm tr.rw{cursor:pointer}table.hm tr.rw:hover td.lft{background:var(--hover)}
table.hm tr.det td{background:var(--panel2);text-align:left;white-space:normal;padding:8px 12px;color:var(--tx2)}
.car{display:inline-block;width:12px;color:var(--dim)}
.chips{display:flex;flex-wrap:wrap;gap:6px}
.chip{background:#fff;border:1px solid var(--line2);border-radius:8px;padding:4px 8px;font-size:12px}
.tag{display:inline-block;font-size:11px;padding:1px 8px;border-radius:999px;font-weight:600}
.tag.r{background:#FBE9E7;color:var(--bad)}.tag.a{background:#FBF1DD;color:#9A6B12}
.bad{color:var(--bad)}.good{color:var(--good)}.dim{color:var(--dimmer)}
.foot{display:flex;justify-content:space-between;align-items:center;margin-top:10px;font-size:12px;color:var(--dim);gap:10px;flex-wrap:wrap}
.btn{background:#fff;color:var(--tx);border:1px solid var(--line2);border-radius:8px;padding:6px 12px;font:inherit;font-size:12.5px;cursor:pointer}
.leg{display:inline-block;width:80px;height:9px;border-radius:3px;vertical-align:middle;margin:0 6px;background:linear-gradient(90deg,rgba(229,98,77,.15),rgba(229,98,77,.75))}
.empty{padding:40px;text-align:center;color:var(--dim)}
</style></head><body><div class="wrap">
<h1>No show por rider</h1>
<div class="sub" id="sub"></div>

<div class="bar">
  <div class="field" id="cityField"><span class="lbl">Ciudad</span><div class="seg" id="citySeg"></div></div>
  <div class="field"><span class="lbl">Semana</span><select id="weekSel"></select></div>
  <div class="field"><span class="lbl">Riders</span><select id="onlySel"><option value="1">Solo con no show</option><option value="0">Todos con turno</option></select></div>
  <div class="field"><span class="lbl">Buscar rider</span><input id="q" type="search" placeholder="ID del rider" inputmode="numeric"></div>
</div>

<div class="kpis" id="kpis"></div>
<div class="trend"><h3>% de no show por semana</h3><div class="s" id="trendSub"></div><div id="trend"></div></div>

<div class="tabs" id="tabs">
  <button data-v="rs" class="on">Rider × semana</button>
  <button data-v="rd">Rider × día de la semana</button>
  <button data-v="lg">Registro de no shows</button>
</div>

<div class="card">
  <div id="help"></div>
  <div class="scroll" id="out"></div>
  <div class="foot"><span id="foot"></span><span id="legend"></span><button class="btn" id="csvBtn">Descargar CSV</button></div>
</div>
</div>
<script>
const D=__DATA__;
const R=D.rows;   // [fecha, semana(idx), díaSemana 0=Lun, ciudad, rider, franjasReservadas, franjasNoShow, horasTrabajadas]
const W=D.weeks,DOW=['Lun','Mar','Mié','Jue','Vie','Sáb','Dom'],SH=D.slotH;
const LASTW=W.length-1,CUR=D.curPartial?LASTW:-1;
const st={city:'ALL',week:'ALL',view:'rs',only:true,q:'',open:new Set()};
let last=null;
const fmt=(n,d)=>n==null||isNaN(n)?'–':n.toLocaleString('es-ES',{minimumFractionDigits:d||0,maximumFractionDigits:d||0});
const esc=s=>String(s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const P=(n,b)=>b>0?100*n/b:null;
const pf=v=>v==null?'–':fmt(v,v>0&&v<10?1:0)+'%';
const hf=s=>fmt(s*SH,1).replace(/,0$/,'')+' h';
const dLbl=r=>DOW[r[2]]+' '+r[0].slice(8,10)+'/'+r[0].slice(5,7);
const wName=i=>W[i]+(i===CUR?' (en curso)':'');
const cellBg=p=>p>0?'background:rgba(229,98,77,'+(0.15+0.6*Math.min(1,p/40)).toFixed(2)+')':'';

const base=()=>R.filter(r=>(st.city==='ALL'||r[3]===st.city)&&(!st.q||r[4].indexOf(st.q)>=0));
const inWeek=r=>st.week==='ALL'||r[1]===+st.week;
const rows=()=>base().filter(inWeek);
function sum(rs){let b=0,n=0,full=0;const rid=new Set(),rns=new Set();rs.forEach(r=>{b+=r[5];n+=r[6];rid.add(r[4]+r[3]);if(r[6]>0){rns.add(r[4]+r[3]);if(r[6]===r[5])full++;}});
  return {b,n,p:P(n,b),riders:rid.size,rns:rns.size,full};}
function byRider(rs){const g=new Map();rs.forEach(r=>{const k=r[4]+' · '+r[3];let o=g.get(k);if(!o){o={k,id:r[4],c:r[3],rs:[],b:0,n:0};g.set(k,o);}o.rs.push(r);o.b+=r[5];o.n+=r[6];});
  let a=[...g.values()];if(st.only)a=a.filter(o=>o.n>0);
  return a.sort((x,y)=>(y.n-x.n)||((P(y.n,y.b)||0)-(P(x.n,x.b)||0)));}

function kpis(){
  const s=sum(rows());let dl='';
  if(st.week!=='ALL'&&+st.week>0){const pv=sum(base().filter(r=>r[1]===+st.week-1));
    if(s.p!=null&&pv.p!=null){const d=s.p-pv.p;dl='<em class="'+(d>0?'bad':'good')+'">'+(d>0?'▲ +':'▼ ')+fmt(d,1)+' pp vs '+W[+st.week-1]+'</em>';}}
  const k=[[pf(s.p)+dl,'% no show (franjas no presentadas ÷ reservadas)'],
    [hf(s.n),'Horas de no show de '+hf(s.b)+' reservadas'],
    [fmt(s.rns)+' <em class="dim" style="color:var(--dim)">de '+fmt(s.riders)+'</em>','Riders con algún no show'],
    [fmt(s.full),'Días en que no se presentó a ningún turno']];
  document.getElementById('kpis').innerHTML=k.map(x=>'<div class="kpi"><b>'+x[0]+'</b><span>'+esc(x[1])+'</span></div>').join('');}

function trend(){
  const b=base(),v=W.map((w,i)=>sum(b.filter(r=>r[1]===i)));
  const Wd=900,H=170,ml=10,mr=10,mt=24,mb=34,bw=(Wd-ml-mr)/W.length;
  const mx=Math.max(5,...v.map(x=>x.p||0))*1.15;const Y=p=>mt+(H-mt-mb)*(1-p/mx);
  let s='<svg viewBox="0 0 '+Wd+' '+H+'" role="img" aria-label="Porcentaje de no show por semana">';
  s+='<line x1="'+ml+'" x2="'+(Wd-mr)+'" y1="'+Y(0)+'" y2="'+Y(0)+'" stroke="#D3D8E0"/>';
  v.forEach((x,i)=>{const X=ml+i*bw+bw*.2,w=bw*.6,sel=st.week!=='ALL'&&+st.week===i,p=x.p||0;
    const col=sel?'#B5342A':'#E5624D',op=i===CUR?'.45':(st.week==='ALL'||sel?'.85':'.35');
    s+='<g style="cursor:pointer" data-w="'+i+'"><rect x="'+X+'" y="'+mt+'" width="'+w+'" height="'+(H-mt-mb)+'" fill="transparent"/>';
    if(x.b>0) s+='<rect x="'+X+'" y="'+Y(p)+'" width="'+w+'" height="'+Math.max(1,Y(0)-Y(p))+'" rx="3" fill="'+col+'" fill-opacity="'+op+'"'+(i===CUR?' stroke="#E5624D" stroke-dasharray="3 3"':'')+'/>';
    s+='<text x="'+(X+w/2)+'" y="'+(Y(p)-6)+'" text-anchor="middle" font-size="12" font-weight="650" fill="#14171F">'+(x.b>0?pf(x.p):'–')+'</text>';
    s+='<text x="'+(X+w/2)+'" y="'+(H-mb+15)+'" text-anchor="middle" font-size="11.5" fill="'+(sel?'#B5342A':'#374151')+'" font-weight="'+(sel?'700':'500')+'">'+W[i]+(i===CUR?'*':'')+'</text>';
    s+='<text x="'+(X+w/2)+'" y="'+(H-mb+28)+'" text-anchor="middle" font-size="10" fill="#6B7280">'+hf(x.n)+'</text>';
    s+='<title>'+wName(i)+' · '+D.wrange[i]+'\n'+pf(x.p)+' no show · '+hf(x.n)+' de '+hf(x.b)+' reservadas\n'+x.rns+' riders con no show</title></g>';});
  s+='</svg>';
  document.getElementById('trend').innerHTML=s;
  document.getElementById('trendSub').textContent='Barras = % de no show de '+(st.city==='ALL'?'todas las ciudades':st.city)+(st.q?' (rider '+st.q+')':'')+'; debajo, horas de no show. Clic en una barra para filtrar esa semana.'+(CUR>=0?' * '+W[CUR]+' en curso (datos hasta '+D.lastDate.slice(8,10)+'/'+D.lastDate.slice(5,7)+').':'');
  document.querySelectorAll('#trend g[data-w]').forEach(g=>g.onclick=()=>{const w=g.dataset.w;st.week=(st.week===w)?'ALL':w;ws.value=st.week;render();});}

const HELP={
 rs:['¿QUÉ RIDERS FALLAN, CUÁNTO Y QUÉ DÍAS?','Cada celda es el % de no show del rider esa semana (franjas no presentadas ÷ franjas reservadas) y, debajo, los días de la semana en que faltó. Rojo más intenso = más % de no show. «·» = sin turno reservado esa semana. «Tendencia» compara la última semana completa con la media de las semanas anteriores: sirve para ver si una acción (aviso, conversación, sanción) ha tenido efecto. Haz clic en un rider para ver cada día con no show. Si eliges una semana arriba, las columnas pasan a ser los días de esa semana.'],
 rd:['¿HAY DÍAS DE LA SEMANA EN LOS QUE CADA RIDER FALLA MÁS?','Cada celda es el % de no show del rider ese día de la semana en el periodo elegido; debajo, cuántos de esos días tuvo no show (p. ej. «2 de 5» = faltó 2 de los 5 sábados que tenía turno). Un rider rojo siempre en la misma columna tiene un patrón fijo: conviene no darle turnos ese día o hablar con él.'],
 lg:['CADA DÍA CON NO SHOW, UNO A UNO','Una fila por rider y día con no show, del más reciente al más antiguo. «Todo el día» = tenía turnos reservados y no se presentó a ninguno; «Parcial» = faltó solo a una parte (llegó tarde, se fue antes o saltó alguna franja).'],
};

function tipOf(rs){return rs.filter(r=>r[6]>0).map(r=>dLbl(r)+': '+hf(r[6])+' de '+hf(r[5])).join('\n');}
function cell(rs,dayMode){if(!rs||!rs.length)return {h:'<td class="z" title="Sin turno reservado">·</td>',v:null};
  let b=0,n=0;rs.forEach(r=>{b+=r[5];n+=r[6];});const p=P(n,b);
  const sub=dayMode?(n>0?hf(n):''):[...new Set(rs.filter(r=>r[6]>0).map(r=>r[2]))].sort().map(i=>DOW[i]).join(' ');
  const t=(n>0?tipOf(rs)+'\n':'')+'Reservado: '+hf(b)+' · No show: '+hf(n);
  return {h:'<td'+(n>0?'':' class="z"')+' style="'+cellBg(p)+'" title="'+esc(t)+'">'+pf(p)+(sub?'<span class="d">'+esc(sub)+'</span>':'')+'</td>',v:p};}

function viewRS(){
  const rs=rows(),g=byRider(rs),wk=st.week!=='ALL';
  let cols,colOf,heads;
  if(wk){cols=[...new Set(rs.map(r=>r[0]))].sort();colOf=r=>r[0];heads=cols.map(f=>{const r=rs.find(x=>x[0]===f);return esc(DOW[r[2]])+'<small>'+f.slice(8,10)+'/'+f.slice(5,7)+'</small>';});}
  else{cols=W.map((w,i)=>i);colOf=r=>r[1];heads=W.map((w,i)=>esc(w)+(i===CUR?'*':'')+'<small>'+D.wrange[i]+'</small>');}
  if(!g.length){last=null;return {h:'<div class="empty"><b>Sin no shows</b><br>Ningún rider tiene no show con estos filtros.</div>',f:''};}
  const lc=CUR>=0?LASTW-1:LASTW;
  let h='<table class="hm"><thead><tr><th class="lft">Rider · ciudad</th>'+heads.map(x=>'<th>'+x+'</th>').join('')+'<th>Total<small>% periodo</small></th><th>Horas<small>no show</small></th><th>Días<small>con no show</small></th>'+
    (wk?'':'<th title="Última semana completa ('+W[lc]+') frente a la media de las semanas anteriores">Tendencia<small>'+W[lc]+' vs antes</small></th>')+'</tr></thead><tbody>';
  const csv=[];
  g.forEach(o=>{const by={};o.rs.forEach(r=>{(by[colOf(r)]=by[colOf(r)]||[]).push(r);});
    const cs=cols.map(c=>cell(by[c],wk)),nd=o.rs.filter(r=>r[6]>0).length,op=st.open.has(o.k);
    let tr='';if(!wk){const a=o.rs.filter(r=>r[1]===lc),bf=o.rs.filter(r=>r[1]<lc);
      const pa=P(a.reduce((s,r)=>s+r[6],0),a.reduce((s,r)=>s+r[5],0)),pb=P(bf.reduce((s,r)=>s+r[6],0),bf.reduce((s,r)=>s+r[5],0));
      if(pa==null||pb==null)tr='<td class="z">–</td>';else{const d=pa-pb;
        tr='<td class="tot '+(Math.abs(d)<0.5?'':d>0?'bad':'good')+'" title="'+W[lc]+': '+pf(pa)+' · antes: '+pf(pb)+'">'+(Math.abs(d)<0.5?'= ':d>0?'▲ +':'▼ ')+fmt(d,1)+' pp</td>';}}
    h+='<tr class="rw" data-k="'+esc(o.k)+'"><td class="lft"><span class="car">'+(op?'▾':'▸')+'</span>'+esc(o.k)+'</td>'+cs.map(x=>x.h).join('')+
      '<td class="tot" style="'+cellBg(P(o.n,o.b))+'">'+pf(P(o.n,o.b))+'</td><td class="tot">'+hf(o.n)+'</td><td class="tot">'+nd+'</td>'+tr+'</tr>';
    if(op){const ev=o.rs.filter(r=>r[6]>0).sort((x,y)=>x[0]<y[0]?1:-1);
      h+='<tr class="det"><td colspan="'+(cols.length+(wk?4:5))+'">'+(ev.length?'<div class="chips">'+ev.map(r=>'<span class="chip"><b>'+dLbl(r)+'</b> ('+W[r[1]]+') · '+hf(r[6])+' de '+hf(r[5])+' · '+(r[6]===r[5]?'<span class="tag r">Todo el día</span>':'<span class="tag a">Parcial</span>')+'</span>').join('')+'</div>':'Sin no shows en el periodo.')+'</td></tr>';}
    csv.push([o.id,o.c].concat(cs.map(x=>x.v)).concat([P(o.n,o.b),o.n*SH,nd]));});
  const tot=cols.map(c=>{const x=rs.filter(r=>colOf(r)===c);return P(x.reduce((s,r)=>s+r[6],0),x.reduce((s,r)=>s+r[5],0));}),S=sum(rs);
  h+='<tr class="totrow"><td class="lft">Total '+(st.city==='ALL'?'':st.city)+'</td>'+tot.map(p=>'<td>'+pf(p)+'</td>').join('')+'<td>'+pf(S.p)+'</td><td>'+hf(S.n)+'</td><td>'+rs.filter(r=>r[6]>0).length+'</td>'+(wk?'':'<td></td>')+'</tr>';
  h+='</tbody></table>';
  last={name:'no_show_rider_semana',head:['Rider','Ciudad'].concat(wk?cols:W).concat(['% periodo','Horas no show','Días con no show']),rows:csv};
  return {h,f:g.length+' riders'+(st.only?' con no show':' con turno')+' · ordenados por horas de no show · clic en un rider para ver sus días'};}

function viewRD(){
  const rs=rows(),g=byRider(rs);
  if(!g.length){last=null;return {h:'<div class="empty"><b>Sin no shows</b><br>Ningún rider tiene no show con estos filtros.</div>',f:''};}
  const cellD=x=>{if(!x.length)return {h:'<td class="z" title="Sin turno ese día">·</td>',v:null};
    let b=0,n=0;x.forEach(r=>{b+=r[5];n+=r[6];});const p=P(n,b),dn=x.filter(r=>r[6]>0).length;
    return {h:'<td'+(n>0?'':' class="z"')+' style="'+cellBg(p)+'" title="'+esc((n>0?tipOf(x)+'\n':'')+dn+' de '+x.length+' días con no show')+'">'+pf(p)+'<span class="d">'+(n>0?dn+' de '+x.length:'')+'</span></td>',v:p};};
  let h='<table class="hm"><thead><tr><th class="lft">Rider · ciudad</th>'+DOW.map(d=>'<th>'+d+'</th>').join('')+'<th>Total<small>% periodo</small></th><th>Peor día</th></tr></thead><tbody>';
  const csv=[];
  g.forEach(o=>{const cs=DOW.map((d,i)=>cellD(o.rs.filter(r=>r[2]===i)));let wi=-1,wv=0;cs.forEach((c,i)=>{if(c.v!=null&&c.v>wv){wv=c.v;wi=i;}});
    h+='<tr><td class="lft">'+esc(o.k)+'</td>'+cs.map(c=>c.h).join('')+'<td class="tot" style="'+cellBg(P(o.n,o.b))+'">'+pf(P(o.n,o.b))+'</td><td class="tot">'+(wi>=0?DOW[wi]:'–')+'</td></tr>';
    csv.push([o.id,o.c].concat(cs.map(c=>c.v)).concat([P(o.n,o.b),wi>=0?DOW[wi]:'']));});
  const tc=DOW.map((d,i)=>{const x=rs.filter(r=>r[2]===i);return P(x.reduce((s,r)=>s+r[6],0),x.reduce((s,r)=>s+r[5],0));});
  h+='<tr class="totrow"><td class="lft">Total '+(st.city==='ALL'?'':st.city)+'</td>'+tc.map(p=>'<td style="'+cellBg(p)+'">'+pf(p)+'</td>').join('')+'<td>'+pf(sum(rs).p)+'</td><td></td></tr></tbody></table>';
  last={name:'no_show_rider_dia_semana',head:['Rider','Ciudad'].concat(DOW).concat(['% periodo','Peor día']),rows:csv};
  return {h,f:g.length+' riders · «2 de 5» = días con no show de los días con turno'};}

function viewLG(){
  const ev=rows().filter(r=>r[6]>0).sort((x,y)=>(x[0]<y[0]?1:x[0]>y[0]?-1:y[6]-x[6]));
  if(!ev.length){last=null;return {h:'<div class="empty"><b>Sin no shows</b><br>No hay no shows con estos filtros.</div>',f:''};}
  const show=ev.slice(0,500);
  let h='<table class="hm"><thead><tr><th class="lft">Fecha</th><th>Día</th><th>Semana</th><th>Rider</th><th>Ciudad</th><th>Reservado</th><th>No show</th><th>% del día</th><th>Horas trabajadas</th><th style="text-align:left">Tipo</th></tr></thead><tbody>'+
    show.map(r=>'<tr><td class="lft">'+r[0].slice(8,10)+'/'+r[0].slice(5,7)+'/'+r[0].slice(0,4)+'</td><td>'+DOW[r[2]]+'</td><td>'+W[r[1]]+'</td><td>'+esc(r[4])+'</td><td>'+esc(r[3])+'</td><td>'+hf(r[5])+'</td><td>'+hf(r[6])+'</td>'+
      '<td style="'+cellBg(P(r[6],r[5]))+'">'+pf(P(r[6],r[5]))+'</td><td>'+fmt(r[7],1)+' h</td><td style="text-align:left">'+(r[6]===r[5]?'<span class="tag r">Todo el día</span>':'<span class="tag a">Parcial</span>')+'</td></tr>').join('')+'</tbody></table>';
  last={name:'no_show_registro',head:['Fecha','Día','Semana','Rider','Ciudad','Horas reservadas','Horas no show','% del día','Horas trabajadas','Tipo'],
    rows:ev.map(r=>[r[0],DOW[r[2]],W[r[1]],r[4],r[3],r[5]*SH,r[6]*SH,P(r[6],r[5]),r[7],r[6]===r[5]?'Todo el día':'Parcial'])};
  const full=ev.filter(r=>r[6]===r[5]).length;
  return {h,f:ev.length+' días con no show ('+full+' de todo el día, '+(ev.length-full)+' parciales)'+(ev.length>500?' · se muestran los 500 más recientes; el CSV los incluye todos':'')};}

function render(){
  kpis();trend();
  document.getElementById('help').innerHTML='<div class="hbox"><b class="t">Cómo leer esta vista · '+HELP[st.view][0]+'</b>'+esc(HELP[st.view][1])+'</div>';
  const r=st.view==='rs'?viewRS():st.view==='rd'?viewRD():viewLG();
  document.getElementById('out').innerHTML=r.h;document.getElementById('foot').textContent=r.f;
  document.getElementById('legend').innerHTML=st.view==='lg'?'':'0 % <span class="leg"></span> 40 %+';
  document.querySelectorAll('#out tr.rw').forEach(tr=>tr.onclick=()=>{const k=tr.dataset.k;st.open.has(k)?st.open.delete(k):st.open.add(k);render();});}

function buildCity(){const el=document.getElementById('citySeg');
  if(D.cities.length<2){document.getElementById('cityField').style.display='none';return;}
  const opts=[['ALL','Todas']].concat(D.cities.map(c=>[c,c]));
  el.innerHTML=opts.map(o=>'<button data-v="'+o[0]+'"'+(o[0]===st.city?' class="on"':'')+'>'+o[1]+'</button>').join('');
  el.querySelectorAll('button').forEach(b=>b.onclick=()=>{st.city=b.dataset.v;buildCity();render();});}
const ws=document.getElementById('weekSel');
ws.innerHTML='<option value="ALL">Todas ('+W[0]+'–'+W[LASTW]+')</option>'+W.map((w,i)=>i).reverse().map(i=>'<option value="'+i+'">'+wName(i)+' · '+D.wrange[i]+'</option>').join('');
ws.onchange=e=>{st.week=e.target.value;render();};
document.getElementById('onlySel').onchange=e=>{st.only=e.target.value==='1';render();};
document.getElementById('q').oninput=e=>{st.q=e.target.value.trim();render();};
document.querySelectorAll('#tabs button').forEach(b=>b.onclick=()=>{st.view=b.dataset.v;
  document.querySelectorAll('#tabs button').forEach(x=>x.classList.toggle('on',x===b));render();});
document.getElementById('csvBtn').onclick=()=>{if(!last)return;const q=s=>'"'+String(s).replace(/"/g,'""')+'"';
  const n=v=>v==null?'':typeof v==='number'?String(Math.round(v*100)/100).replace('.',','):q(v);
  const lines=[last.head.map(q).join(';')].concat(last.rows.map(r=>r.map(n).join(';')));
  const a=document.createElement('a');a.href=URL.createObjectURL(new Blob(['﻿'+lines.join('\n')],{type:'text/csv;charset=utf-8'}));
  a.download=last.name+'_'+st.city+(st.week==='ALL'?'':'_'+W[+st.week])+'.csv';a.click();};
document.getElementById('sub').textContent='Fuente: rider_lv (Glovo) · '+W[0]+'–'+W[LASTW]+' · % no show = franjas de 30 min no presentadas ÷ franjas reservadas'+(D.generated?' · generado '+D.generated:'');
buildCity();render();
if(window.parent!==window){const send=()=>window.parent.postMessage({nsH:document.body.getBoundingClientRect().height},'*');
  if(window.ResizeObserver) new ResizeObserver(send).observe(document.body); send();}
</script></body></html>
"""

if __name__ == "__main__":
    main()
