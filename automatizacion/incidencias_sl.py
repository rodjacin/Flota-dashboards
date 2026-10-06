# -*- coding: utf-8 -*-
"""
================================================================================
 Pestaña "Incidencias" (S&L de Glovo: CAPU, no entregado, cliente ausente)
================================================================================
 Fuente: los informes «mushdrink_s_l_report*.html» que Glovo envía (Fraud
 chargeability & incident report). Se juntan TODOS los que haya en Descargas
 (histórico + semana en curso) y se guardan sin coordenadas en
 automatizacion/entradas/incidencias_sl.json:

   python3 incidencias_sl.py --extraer ~/Downloads <ruta/incidencias_sl.json>

 La pestaña tiene filtros de área, semana, fecha, intervalo horario y tipo.
 PRIVACIDAD: los links son públicos; NO se publican las ubicaciones de
 restaurante ni de cliente que trae el informe.
================================================================================
"""
import os, re, sys, json, glob, datetime as dt

NODE_ALIASES = {"NEM": "MAD"}
JSON_IN = os.path.expanduser("~/Downloads/incidencias_sl.json")
TIPOS = {"C": "CAPU", "U": "No entregado", "A": "Cliente ausente"}


def _leer_informe(path):
    t = open(path, encoding="utf-8", errors="replace").read()
    m = re.search(r"var D = (\{.*?\});\s*var COMPANY", t, re.S)
    return json.loads(m.group(1)) if m else None


def extraer(carpeta, salida):
    """Junta las incidencias de todos los informes (el más reciente manda) y guarda el JSON."""
    previo = {}
    if os.path.exists(salida):
        try:
            previo = json.load(open(salida, encoding="utf-8"))
        except Exception:
            previo = {}
    pedidos = {r[1]: r for r in previo.get("rows", [])}
    totales = dict(previo.get("semanas", {}))
    fs = sorted(glob.glob(os.path.join(os.path.expanduser(carpeta), "mushdrink_s_l_report*.html")), key=os.path.getmtime)
    for f in fs:
        D = _leer_informe(f)
        if not D:
            continue
        for per in ("weekly", "monthly"):
            for p, cs in (D.get(per, {}).get("orders") or {}).items():
                for co, lst in cs.items():
                    for o in lst:
                        # [fecha, pedido, rider, área, tipo, coste, tienda, (vend), (cli), hora, pago] -> sin ubicaciones
                        hora = str(o[9] or "")
                        pedidos[str(o[1])] = [str(o[0])[:10], str(o[1]), str(o[2]), NODE_ALIASES.get(o[3], o[3]) or "",
                                              o[4], round(float(o[5] or 0), 2), o[6] or "", hora[11:16] if len(hora) >= 16 else "",
                                              o[10] or ""]
        for p, cs in (D.get("weekly", {}).get("totals") or {}).items():
            for co, v in cs.items():
                totales[p] = {"pedidos": v.get("total_orders"), "incidencias": v.get("total_incidents"),
                              "coste_glovo": v.get("total_glovo_cost"), "coste_cargable": v.get("total_chargeable_cost")}
    rows = sorted(pedidos.values(), key=lambda r: (r[0], r[7], r[1]))
    # la fecha solo cambia si cambian los datos (así no hay commits vacíos)
    sello = previo.get("extraido") if previo.get("rows") == rows and previo.get("semanas") == totales else dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    out = {"extraido": sello, "informes": len(fs),
           "cols": ["fecha", "pedido", "rider", "area", "tipo", "coste", "tienda", "hora", "pago"],
           "rows": rows, "semanas": totales}
    os.makedirs(os.path.dirname(os.path.abspath(salida)), exist_ok=True)
    json.dump(out, open(salida, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    print("incidencias_sl: %d informes · %d incidencias (%s → %s)" % (len(fs), len(rows),
          rows[0][0] if rows else "-", rows[-1][0] if rows else "-"))
    return out


def construir_html(cities=None, semanas=None, sello=True):
    cities = sorted(set(NODE_ALIASES.get(c, c) for c in (cities or [])))
    if not os.path.isfile(JSON_IN):
        raise ValueError("no encuentro " + JSON_IN)
    d = json.load(open(JSON_IN, encoding="utf-8"))
    rows = [r for r in d["rows"] if r[3] in cities]
    data = {"cities": cities, "rows": rows, "extraido": d.get("extraido") or d.get("actualizado"), "tipos": TIPOS}
    html = HTML.replace("__DATA__", json.dumps(data, ensure_ascii=False, separators=(",", ":")))
    return html, "%d incidencias (%s → %s)" % (len(rows), rows[0][0] if rows else "-", rows[-1][0] if rows else "-")


_BTN = '<button data-v="incid" aria-pressed="false">Incidencias</button>'


def integrar_en_dashboard(dash_html, inc_html):
    if 'id="viewIncid"' in dash_html:
        return dash_html
    ancla = None
    for a in ['<button data-v="wtdv1" aria-pressed="false">WTD% v1</button>',
              '<button data-v="wtdpct" aria-pressed="false">WTD%</button>',
              '<button data-v="cpostal" aria-pressed="false">Códigos postales</button>',
              '<button data-v="envivo" aria-pressed="false">En vivo</button>']:
        if a in dash_html:
            ancla = a
            break
    sec_ancla = '<div id="viewSemanal">'
    if not ancla or sec_ancla not in dash_html or "</body>" not in dash_html:
        raise ValueError("la plantilla no tiene el selector de Vista esperado")
    dash_html = dash_html.replace(ancla, ancla + "\n        " + _BTN, 1)
    dash_html = dash_html.replace(sec_ancla,
        '<section id="viewIncid" style="display:none"><iframe id="incidFrame" title="Incidencias" '
        'style="width:100%;height:1400px;border:0;display:block;background:transparent"></iframe></section>\n  '
        + sec_ancla, 1)
    src = json.dumps(inc_html, ensure_ascii=False).replace("<", "\\u003c")
    js = ("<script>\n/* ==== Pestaña Incidencias ==== */\n(function(){\n"
          "  const INC_HTML=" + src + ";\n"
          "  const seg=document.getElementById('viewSeg'),sec=document.getElementById('viewIncid'),fr=document.getElementById('incidFrame');\n"
          "  if(!seg||!sec||!fr) return; let loaded=false;\n"
          "  seg.querySelectorAll('button').forEach(b=>b.addEventListener('click',()=>{\n"
          "    const on=b.dataset.v==='incid'; sec.style.display=on?'':'none';\n"
          "    if(on){ seg.querySelectorAll('button').forEach(x=>x.setAttribute('aria-pressed',String(x===b)));\n"
          "      document.querySelectorAll('[id^=\"view\"]').forEach(e=>{ if(e!==sec && e!==seg && e.id!=='viewSeg') e.style.display='none'; });\n"
          "      if(!loaded){ fr.srcdoc=INC_HTML; loaded=true; } window.scrollTo(0,0); }\n"
          "  }));\n"
          "  window.addEventListener('message',e=>{ if(e.source===fr.contentWindow && e.data && e.data.incH){\n"
          "    fr.style.height=Math.max(600,Math.ceil(e.data.incH)+20)+'px'; } });\n"
          "})();\n</script>\n")
    i = dash_html.rindex("</body>")
    return dash_html[:i] + js + dash_html[i:]


HTML = r'''<!DOCTYPE html><html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Incidencias S&amp;L</title>
<style>
:root{--bg:#F6F7F9;--surface:#FFFFFF;--line:#E4E7EC;--ink:#14171F;--ink2:#4B5563;--muted:#6B7280;--acc:#0E5A6B;--chip:#EEF1F4;--bad:#C2362F;--badbg:#FDECEA;--c:#C2362F;--u:#D9822B;--a:#5B54B8}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font-family:"Inter",-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;font-size:14px;padding:0 0 24px}
.wrap{display:flex;flex-direction:column;gap:16px}
h1{font-size:18px;font-weight:650;margin:0}
h2{font-size:12px;letter-spacing:.06em;text-transform:uppercase;font-weight:650;margin:0}
.sub{color:var(--ink2);margin:5px 0 0;line-height:1.5;font-size:13px}
.filters{background:var(--surface);border:1px solid var(--line);border-radius:12px;padding:14px 16px;display:flex;flex-wrap:wrap;gap:16px;align-items:flex-end}
.fg{display:flex;flex-direction:column;gap:6px}
.fg>span{font-family:ui-monospace,"SF Mono",Menlo,monospace;font-size:11px;letter-spacing:.07em;text-transform:uppercase;color:var(--muted)}
.seg{display:inline-flex;flex-wrap:wrap;background:var(--bg);border:1px solid var(--line);border-radius:9px;padding:3px;gap:2px}
.seg button{font:inherit;font-size:13px;border:0;background:transparent;color:var(--ink2);border-radius:7px;padding:6px 11px;cursor:pointer}
.seg button:hover{color:var(--ink)}.seg button.on{background:var(--acc);color:#fff}
.seg button .c{font-family:ui-monospace,monospace;font-size:11px;opacity:.75;margin-left:5px}
select,input[type=search]{font:inherit;font-size:13px;padding:7px 10px;border:1px solid var(--line);border-radius:8px;background:var(--surface);color:var(--ink)}
input[type=search]{width:200px}
.hr{display:flex;gap:6px;align-items:center}.hr span{color:var(--muted);font-size:12px}
.reset{font:inherit;font-size:12.5px;background:transparent;color:var(--muted);border:1px solid var(--line);border-radius:8px;padding:7px 12px;cursor:pointer}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:10px}
.kpi{background:var(--surface);border:1px solid var(--line);border-radius:12px;padding:12px 14px;display:flex;flex-direction:column;gap:4px}
.kpi b{font-size:22px;font-weight:650;font-family:ui-monospace,"SF Mono",Menlo,monospace;font-variant-numeric:tabular-nums}
.kpi span{font-size:12px;color:var(--ink2)}
.kpi em{font-style:normal;font-family:ui-monospace,"SF Mono",Menlo,monospace;font-size:11px;letter-spacing:.06em;text-transform:uppercase;color:var(--muted)}
.grid2{display:grid;grid-template-columns:3fr 2fr;gap:16px}
@media(max-width:900px){.grid2{grid-template-columns:1fr}}
.panel{background:var(--surface);border:1px solid var(--line);border-radius:12px;padding:14px;display:flex;flex-direction:column;gap:10px;min-width:0}
.ph{display:flex;justify-content:space-between;gap:10px;flex-wrap:wrap;align-items:baseline}.ph p{margin:0;color:var(--ink2);font-size:12.5px}
.bars{display:flex;align-items:flex-end;gap:5px;height:190px;padding-top:18px;overflow-x:auto}
.bar{flex:1 0 26px;max-width:90px;display:flex;flex-direction:column;align-items:center;justify-content:flex-end;height:100%;gap:3px;cursor:pointer}
.bar .stk{width:100%;display:flex;flex-direction:column-reverse;border-radius:4px 4px 0 0;overflow:hidden;min-height:1px}
.bar .stk i{display:block;width:100%}
.bar b{font-size:10.5px;font-family:ui-monospace,monospace;color:var(--ink)}
.bar span{font-size:10px;color:var(--muted);white-space:nowrap}
.bar.sel span{color:var(--ink);font-weight:700}.bar.cur span{color:var(--acc);font-weight:700}
.bar:hover .stk{opacity:.85}

.legend{display:flex;gap:14px;flex-wrap:wrap;font-size:12px;color:var(--ink2)}.legend i{display:inline-block;width:10px;height:10px;border-radius:3px;margin-right:5px;vertical-align:middle}
.tw{overflow-x:auto}
table{border-collapse:collapse;width:100%}
th,td{padding:7px 10px;text-align:left;border-bottom:1px solid var(--line);white-space:nowrap;font-size:13px}
th{font-family:ui-monospace,"SF Mono",Menlo,monospace;font-size:10.5px;letter-spacing:.05em;text-transform:uppercase;color:var(--muted);font-weight:500;cursor:pointer;position:sticky;top:0;background:var(--surface)}
td.n,th.n{text-align:right;font-family:ui-monospace,"SF Mono",Menlo,monospace;font-variant-numeric:tabular-nums}
tbody tr:hover td{background:var(--chip)}
tr.click{cursor:pointer}
.flag{display:inline-block;min-width:34px;text-align:center;padding:2px 9px;border-radius:99px;font-weight:700;font-family:ui-monospace,monospace}
.flag.amber{background:#FFF4DB;color:#8A5A00;border:1px solid #F5D9A8}.flag.red{background:#FDECEA;color:#C2362F;border:1px solid #F5C2BD}.flag.ok{color:var(--ink2)}
.tp{display:inline-block;padding:2px 8px;border-radius:99px;font-size:11.5px;font-weight:600;color:#fff}
.muted{color:var(--muted)}
.empty{color:var(--muted);padding:16px 0}
.note{color:var(--muted);font-size:12px;line-height:1.55;margin:0}
</style></head><body>
<div class="wrap">
  <header><h1>Incidencias S&amp;L por pedido</h1><p class="sub" id="sub"></p></header>
  <div class="filters">
    <div class="fg"><span>Área</span><div class="seg" id="fCity"></div></div>
    <div class="fg"><span>Semana</span><select id="fWk" aria-label="Semana"></select></div>
    <div class="fg"><span>Fecha</span><select id="fDay" aria-label="Fecha"></select></div>
    <div class="fg"><span>Tipo</span><div class="seg" id="fTipo"></div></div>
    <div class="fg"><span>Buscar</span><input type="search" id="fQ" placeholder="Rider, pedido o tienda"></div>
    <div class="fg"><span>&nbsp;</span><button class="reset" id="fReset">Limpiar</button></div>
  </div>
  <section class="kpis" id="kpis"></section>
  <section class="panel"><div class="ph"><h2 id="tBars">Incidencias por semana</h2><p>Pulsa una barra para filtrar</p></div>
    <div class="bars" id="bars"></div><div class="legend" id="leg"></div></section>
  <section class="panel"><div class="ph"><h2>Riders con incidencias</h2><p id="cR"></p></div>
    <div class="tw" style="max-height:460px"><table id="tR"></table></div></section>
  <section class="panel"><div class="ph"><h2>Detalle de incidencias</h2><p id="cE"></p></div>
    <div class="tw" style="max-height:620px"><table id="tE"></table></div></section>
  <p class="note" id="nota"></p>
</div>
<script>
const D=__DATA__;
const $=id=>document.getElementById(id);
const esc=s=>String(s??'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const nf=(v,d=0)=>v==null||isNaN(v)?'—':Number(v).toLocaleString('es-ES',{minimumFractionDigits:d,maximumFractionDigits:d});
const eur=v=>nf(v,0)+' €';
const COL={C:'var(--c)',U:'var(--u)',A:'var(--a)'};
const DOW=['dom','lun','mar','mié','jue','vie','sáb'];
function isoW(s){const t=new Date(s+'T00:00:00Z');const dn=(t.getUTCDay()+6)%7;t.setUTCDate(t.getUTCDate()-dn+3);const y=t.getUTCFullYear();const f=new Date(Date.UTC(y,0,4));return y+'-W'+String(1+Math.round(((t-f)/864e5-3+((f.getUTCDay()+6)%7))/7)).padStart(2,'0');}
const dlab=s=>{const d=new Date(s+'T00:00:00Z');return DOW[d.getUTCDay()]+' '+s.slice(8,10)+'/'+s.slice(5,7);};
const R=D.rows.map(r=>({f:r[0],id:r[1],rid:r[2],city:r[3],t:r[4],cost:r[5],store:r[6],h:r[7],pay:r[8],hh:r[7]?+r[7].slice(0,2):null,wk:isoW(r[0])}));
const today=new Date().toISOString().slice(0,10), CUR=isoW(today);
const S={city:'ALL',wk:'ALL',day:'ALL',tipo:'ALL',q:'',sr:{k:'n',d:-1},se:{k:'f',d:-1}};
$('sub').textContent='Incidencias que Glovo imputa a la flota (informe «Fraud chargeability & incident report»): CAPU, pedido no entregado y cliente ausente. Datos del '+(R.length?dlab(R[0].f)+' al '+dlab(R[R.length-1].f):'—')+' · semana en curso '+CUR.slice(5)+' · datos extraídos el '+(D.extraido||'—')+'.';
$('nota').innerHTML='Fuente: informes S&amp;L de Glovo (todos los recibidos, histórico y semana en curso). Coste = importe del pedido con incidencia según Glovo. No se publican ubicaciones de restaurante ni de cliente.';
function seg(id,opts,val,on){const el=$(id);el.innerHTML=opts.map(o=>`<button data-v="${o.v}" class="${String(o.v)===String(val)?'on':''}">${o.l}${o.c!=null?`<span class="c">${o.c}</span>`:''}</button>`).join('');el.onclick=e=>{const b=e.target.closest('button');if(b)on(b.dataset.v);};}
const base=()=>R.filter(r=>(S.city==='ALL'||r.city===S.city)&&(S.tipo==='ALL'||r.t===S.tipo)&&(!S.q||(r.rid+' '+r.id+' '+r.store).toLowerCase().includes(S.q)));
function tabla(id,cols,rows,st,empty,lim){
  const col=cols.find(x=>x.k===st.k)||cols[0];
  const s=rows.slice().sort((a,b)=>{const x=col.v(a),y=col.v(b);return (typeof x==='string'?String(x).localeCompare(y,'es'):x-y)*st.d;}).slice(0,lim||1e9);
  $(id).innerHTML=!s.length?`<tbody><tr><td class="empty">${empty}</td></tr></tbody>`:'<thead><tr>'+cols.map(x=>`<th class="${x.n?'n':''}" data-k="${x.k}">${x.h}${st.k===x.k?(st.d<0?' ▼':' ▲'):''}</th>`).join('')+'</tr></thead><tbody>'+s.map(r=>`<tr data-rid="${esc(r.rid)}">`+cols.map(x=>`<td class="${x.n?'n':''}">${x.f(r)}</td>`).join('')+'</tr>').join('')+'</tbody>';
  $(id).querySelectorAll('th[data-k]').forEach(th=>th.onclick=()=>{const k=th.dataset.k;if(st.k===k)st.d*=-1;else{st.k=k;st.d=cols.find(x=>x.k===k).n?-1:1;}render();});
  return s.length;}
const tp=t=>`<span class="tp" style="background:${COL[t]}">${esc(D.tipos[t]||t)}</span>`;
function render(){
  const B0=base();
  seg('fCity',[{v:'ALL',l:'Todas',c:R.length}].concat(D.cities.map(c=>({v:c,l:c,c:R.filter(r=>r.city===c).length}))),S.city,v=>{S.city=v;render();});
  seg('fTipo',[{v:'ALL',l:'Todos'}].concat(['C','U','A'].map(t=>({v:t,l:D.tipos[t]}))),S.tipo,v=>{S.tipo=v;render();});
  const wks=[...new Set(R.map(r=>r.wk))].sort().reverse();
  $('fWk').innerHTML='<option value="ALL">Todas</option>'+wks.map(w=>`<option value="${w}" ${w===S.wk?'selected':''}>${w.slice(5)}${w===CUR?' · en curso':''}</option>`).join('');
  const days=[...new Set(R.filter(r=>S.wk==='ALL'||r.wk===S.wk).map(r=>r.f))].sort().reverse();
  if(S.day!=='ALL'&&!days.includes(S.day))S.day='ALL';
  $('fDay').innerHTML='<option value="ALL">Todas</option>'+days.map(d=>`<option value="${d}" ${d===S.day?'selected':''}>${dlab(d)}</option>`).join('');
  const B1=B0.filter(r=>S.wk==='ALL'||r.wk===S.wk);
  const B=B1.filter(r=>S.day==='ALL'||r.f===S.day);
  const cnt=t=>B.filter(r=>r.t===t).length, cost=B.reduce((a,r)=>a+(r.cost||0),0), riders=new Set(B.map(r=>r.rid));
  const rep={};B.forEach(r=>rep[r.rid]=(rep[r.rid]||0)+1);
  $('kpis').innerHTML=[['Incidencias',nf(B.length),S.day!=='ALL'?dlab(S.day):(S.wk!=='ALL'?S.wk.slice(5)+(S.wk===CUR?' · en curso':''):'todo el histórico')],
   ['CAPU',nf(cnt('C')),B.length?nf(cnt('C')/B.length*100,0)+' %':''],['No entregado',nf(cnt('U')),B.length?nf(cnt('U')/B.length*100,0)+' %':''],
   ['Cliente ausente',nf(cnt('A')),B.length?nf(cnt('A')/B.length*100,0)+' %':''],['Coste de los pedidos',eur(cost),'según Glovo'],
   ['Riders con incidencias',nf(riders.size),`<span class="flag amber" style="min-width:0">${nf(Object.values(rep).filter(x=>x>=2&&x<=3).length)}</span> con 2–3 · <span class="flag red" style="min-width:0">${nf(Object.values(rep).filter(x=>x>3).length)}</span> con más de 3`]]
   .map(([e,b,s])=>`<div class="kpi"><em>${e}</em><b>${b}</b><span>${s}</span></div>`).join('');
  // barras por semana (o por día si hay semana elegida)
  const porDia=S.wk!=='ALL', key=porDia?(r=>r.f):(r=>r.wk);
  $('tBars').textContent=porDia?'Incidencias por día · '+S.wk.slice(5):'Incidencias por semana';
  const src=porDia?B1:B0;const G={};src.forEach(r=>{const k=key(r);(G[k]||(G[k]={C:0,U:0,A:0}))[r.t]++;});
  let ks=Object.keys(G).sort(); if(!porDia)ks=ks.slice(-20);
  const mx=Math.max(1,...ks.map(k=>G[k].C+G[k].U+G[k].A));
  $('bars').innerHTML=ks.length?ks.map(k=>{const g=G[k],n=g.C+g.U+g.A;const sel=porDia?S.day===k:S.wk===k;
    return `<div class="bar ${sel?'sel':''} ${!porDia&&k===CUR?'cur':''}" data-k="${k}" title="${n} incidencias · CAPU ${g.C} · No entregado ${g.U} · Cliente ausente ${g.A}"><b>${n}</b><div class="stk" style="height:${n/mx*140}px">${['C','U','A'].map(t=>g[t]?`<i style="height:${g[t]/n*100}%;background:${COL[t]}"></i>`:'').join('')}</div><span>${porDia?dlab(k):k.slice(5)+(k===CUR?'*':'')}</span></div>`;}).join(''):'<span class="muted">Sin incidencias con estos filtros.</span>';
  $('bars').querySelectorAll('.bar').forEach(b=>b.onclick=()=>{const k=b.dataset.k;if(porDia)S.day=S.day===k?'ALL':k;else{S.wk=S.wk===k?'ALL':k;S.day='ALL';}render();});
  $('leg').innerHTML=['C','U','A'].map(t=>`<span><i style="background:${COL[t]}"></i>${D.tipos[t]}</span>`).join('')+(porDia?'':'<span class="muted">* semana en curso</span>');
  // riders
  const M={};B.forEach(r=>{const m=M[r.rid]||(M[r.rid]={rid:r.rid,city:r.city,n:0,C:0,U:0,A:0,cost:0,last:''});m.n++;m[r.t]++;m.cost+=r.cost||0;if(r.f+' '+r.h>m.last)m.last=r.f+' '+r.h;});
  const nR=tabla('tR',[
    {k:'rid',h:'Rider',v:m=>Number(m.rid)||0,f:m=>esc(m.rid)},{k:'city',h:'Área',v:m=>m.city,f:m=>esc(m.city)},
    {k:'n',h:'Incidencias',n:1,v:m=>m.n,f:m=>`<span class="flag ${m.n>3?'red':(m.n>=2?'amber':'ok')}" title="${m.n>3?'Más de 3 incidencias':(m.n>=2?'2 o 3 incidencias':'1 incidencia')} en el periodo filtrado">${m.n}</span>`},{k:'C',h:'CAPU',n:1,v:m=>m.C,f:m=>m.C||''},{k:'U',h:'No entregado',n:1,v:m=>m.U,f:m=>m.U||''},
    {k:'A',h:'Cliente ausente',n:1,v:m=>m.A,f:m=>m.A||''},{k:'cost',h:'Coste',n:1,v:m=>m.cost,f:m=>eur(m.cost)},{k:'last',h:'Última',v:m=>m.last,f:m=>dlab(m.last.slice(0,10))+' '+m.last.slice(11)}],
    Object.values(M),S.sr,'Ningún rider con incidencias con estos filtros.');
  $('cR').innerHTML=nf(nR)+' riders · <span class="flag amber" style="min-width:0">2–3</span> <span class="flag red" style="min-width:0">&gt;3</span> incidencias en el periodo · pulsa uno para ver sus incidencias';
  $('tR').querySelectorAll('tbody tr[data-rid]').forEach(tr=>{tr.className='click';tr.onclick=()=>{$('fQ').value=tr.dataset.rid;S.q=tr.dataset.rid.toLowerCase();render();};});
  const nE=tabla('tE',[
    {k:'f',h:'Fecha y hora',v:r=>r.f+' '+r.h,f:r=>dlab(r.f)+' '+esc(r.h)},{k:'t',h:'Tipo',v:r=>r.t,f:r=>tp(r.t)},
    {k:'rid',h:'Rider',v:r=>Number(r.rid)||0,f:r=>esc(r.rid)},{k:'city',h:'Área',v:r=>r.city,f:r=>esc(r.city)},
    {k:'store',h:'Tienda',v:r=>r.store,f:r=>esc(r.store)},{k:'id',h:'Pedido',v:r=>r.id,f:r=>`<span class="muted">${esc(r.id)}</span>`},
    {k:'cost',h:'Coste',n:1,v:r=>r.cost||0,f:r=>nf(r.cost,2)+' €'},{k:'pay',h:'Pago',v:r=>r.pay,f:r=>esc(r.pay)}],B,S.se,'Ninguna incidencia con estos filtros.',800);
  $('cE').textContent=nf(B.length)+' incidencias'+(B.length>800?' (se muestran 800)':'');
}
$('fWk').onchange=e=>{S.wk=e.target.value;S.day='ALL';render();};
$('fDay').onchange=e=>{S.day=e.target.value;render();};
let qT;$('fQ').addEventListener('input',e=>{clearTimeout(qT);qT=setTimeout(()=>{S.q=e.target.value.trim().toLowerCase();render();},150);});
$('fReset').onclick=()=>{Object.assign(S,{city:'ALL',wk:'ALL',day:'ALL',tipo:'ALL',q:''});$('fQ').value='';render();};
render();
if(window.parent!==window){const send=()=>window.parent.postMessage({incH:document.body.getBoundingClientRect().height},'*');
  if(window.ResizeObserver) new ResizeObserver(send).observe(document.body); send();}
</script></body></html>
'''

if __name__ == "__main__":
    if len(sys.argv) >= 2 and sys.argv[1] == "--extraer":
        carpeta = sys.argv[2] if len(sys.argv) > 2 else "~/Downloads"
        salida = sys.argv[3] if len(sys.argv) > 3 else os.path.join(os.path.dirname(os.path.abspath(__file__)), "entradas", "incidencias_sl.json")
        extraer(carpeta, salida)
