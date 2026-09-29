#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
================================================================================
 Parche "Resumen de performance" + definiciones al pasar el ratón
================================================================================

 Lo aplica generar_resumen_flota.py (igual que patch_delivery_race.py) si este
 archivo está en la misma carpeta. Añade al dashboard:

   1. Resumen de performance con filtro de MÉTRICA (semanal y diario):
        WTD>10′ % · RR % · No Show % · % Incidencias totales · UTR
      Botón «Todas» o una/varias métricas. Con una sola métrica se dibuja
      además la línea del Objetivo T1 (WTD y RR). UTR va en su propio eje.
   2. Definición de cada métrica al pasar el ratón por la cabecera de la
      tabla (vista agregada y semanal), por la tabla Diario y por las
      tarjetas del Resumen de performance.
   3. Arreglo: en vista agregada, RR % (y sus desgloses) mostraban solo la
      primera semana del rider; ahora es el total del periodo.

 Se puede probar sobre un dashboard ya generado:
   python3 patch_perf_metricas.py entrada.html salida.html
================================================================================
"""

import sys

MARK = "/* ==== patch_perf_metricas ==== */"

# ------------------------------------------------------------------------------
#  Definiciones (edítalas libremente). Se muestran al pasar el ratón.
# ------------------------------------------------------------------------------
DEFS_JS = r"""
const METRIC_DEFS = {
  rider:        ['Rider ID', 'Identificador del rider en Glovo.'],
  city:         ['Área', 'Nodo / ciudad en la que trabaja el rider (NEM se muestra como MAD).'],
  vehicle:      ['Vehículo', 'Vehículo más usado por el rider en el periodo.'],
  week:         ['Semana', 'Semana ISO (lunes a domingo). En vista agregada: nº de semanas con actividad del rider.'],
  day:          ['Día', 'Día de la semana en curso.'],
  delivered:    ['Entregados', 'Pedidos entregados (completados) por el rider.'],
  undelivered:  ['No entregados', 'Pedidos cancelados / no entregados del rider.'],
  _noshows:     ['No Show %', 'Parte del horario reservado al que el rider no se presentó: franjas de 30 min no presentadas ÷ franjas reservadas. Mide turnos reservados y no trabajados.'],
  capu:         ['CAPU %', 'Incidencias CAPU (reportadas como fraude por Glovo) ÷ pedidos entregados.'],
  notMoving:    ['Sin mov.', 'Nº de franjas de 30 min de no show registradas por Glovo en el periodo (mismo dato que alimenta No Show %).'],
  bundling:     ['Bundling %', 'Entregas hechas en pedido agrupado (varios pedidos en el mismo viaje) ÷ pedidos entregados.'],
  wtd10:        ['WTD>10′ %', 'Pedidos en los que el rider pasó más de 10 minutos en el punto del cliente ÷ pedidos entregados. Cuanto más bajo, mejor.'],
  reassign:     ['RR % (Reassignment)', 'Pedidos reasignados a otro rider ÷ pedidos asignados al rider. Cuanto más bajo, mejor.'],
  notSeen:      ['Not Seen %', 'Reasignados porque el rider no llegó a ver el aviso ÷ pedidos asignados.'],
  ignored:      ['Ignored %', 'Reasignados porque el rider vio el aviso y no respondió ÷ pedidos asignados.'],
  decline:      ['Decline %', 'Reasignados porque el rider rechazó el pedido ÷ pedidos asignados.'],
  redispatch:   ['Redispatch %', 'Reasignados por el sistema de Glovo (redespacho) ÷ pedidos asignados.'],
  cnm:          ['CNM %', 'Reasignados porque el rider no avanzaba hacia el local o el cliente (courier not moving) ÷ pedidos asignados.'],
  agent:        ['Agent %', 'Reasignados a mano por un agente de soporte ÷ pedidos asignados.'],
  deliveryTime: ['T. entrega', 'Tiempo medio de entrega del rider, en minutos.'],
  wtd:          ['WTD', 'Minutos en el punto del cliente (campo at_customer_min de Glovo, sumado en el periodo).'],
  workingHours: ['H. trabajadas', 'Horas trabajadas (conectado en turno) en el periodo.'],
  utr:          ['UTR', 'Entregas completadas ÷ horas trabajadas. Cuanto más alto, mejor aprovechadas están las horas.'],
  ineligible:   ['H. no elegible', 'Horas en las que el rider estaba conectado pero no podía recibir pedidos.'],
  efficiency:   ['Eficiencia %', 'Tiempo ocupado con pedidos ÷ tiempo trabajado.'],
  incidents:    ['Incidencias', 'Nº de incidencias S&L: CAPU + no entregado + cliente ausente.'],
  slInc:        ['Incid. S&L', 'Nº de incidencias S&L: CAPU + no entregado + cliente ausente.'],
  slCapu:       ['Inc. CAPU', 'Nº de incidencias CAPU.'],
  slUndel:      ['Inc. No entregado', 'Nº de incidencias por pedido no entregado.'],
  slAbsent:     ['Inc. Cliente ausente', 'Nº de incidencias por cliente ausente.'],
  slGlovo:      ['Coste Glovo', 'Parte del coste de las incidencias que asume Glovo.'],
  slCharge:     ['Coste imputado', 'Parte del coste de las incidencias que se imputa a la flota.'],
  incpct:       ['% Incidencias totales', 'Incidencias S&L (CAPU + no entregado + cliente ausente) ÷ pedidos entregados. Cuanto más bajo, mejor.'],
};
const AGG_NOTE = {
  sum:   'Vista agregada: suma de todas las semanas del rider.',
  avg:   'Vista agregada: media de las semanas del rider.',
  first: 'Vista agregada: total del periodo (reasignados ÷ asignados de todas las semanas).',
  weeks: '',
};
"""

# ------------------------------------------------------------------------------
#  Tooltip flotante: cualquier elemento con data-def="clave" (o data-deftext)
# ------------------------------------------------------------------------------
TOOLTIP = r"""
<style id="metric-def-css">
.mdef-tip{position:fixed;z-index:9999;max-width:300px;background:#14171F;color:#fff;border-radius:8px;padding:9px 11px;
  font:12px/1.45 "Inter",-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;box-shadow:0 6px 18px rgba(0,0,0,.22);
  pointer-events:none;opacity:0;transition:opacity .08s;text-transform:none;letter-spacing:0;text-align:left;white-space:normal}
.mdef-tip b{display:block;font-size:12.5px;margin-bottom:3px}
.mdef-tip .ag{display:block;margin-top:5px;color:#b9c2cc;font-size:11.5px}
[data-def]{cursor:help}
thead th[data-def]{text-decoration:underline dotted rgba(107,114,128,.55);text-underline-offset:3px}
</style>
<script>
""" + MARK + r"""
(function(){
  if(typeof METRIC_DEFS==='undefined') return;
  const tip=document.createElement('div'); tip.className='mdef-tip'; document.body.appendChild(tip);
  const esc=s=>String(s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
  let cur=null;
  function place(e){
    const r=tip.getBoundingClientRect(), vw=window.innerWidth, vh=window.innerHeight;
    let x=e.clientX+14, y=e.clientY+16;
    if(x+r.width>vw-8) x=Math.max(8,e.clientX-r.width-10);
    if(y+r.height>vh-8) y=Math.max(8,e.clientY-r.height-12);
    tip.style.left=x+'px'; tip.style.top=y+'px';
  }
  document.addEventListener('mouseover',e=>{
    const el=e.target.closest&&e.target.closest('[data-def]');
    if(!el){ if(cur){cur=null; tip.style.opacity=0;} return; }
    if(el!==cur){
      cur=el; const d=METRIC_DEFS[el.dataset.def]||[el.textContent,''];
      const ag=el.dataset.agg&&AGG_NOTE[el.dataset.agg]?AGG_NOTE[el.dataset.agg]:'';
      tip.innerHTML='<b>'+esc(d[0])+'</b>'+esc(d[1])+(ag?'<span class="ag">'+esc(ag)+'</span>':'');
      tip.style.opacity=1;
    }
    place(e);
  });
  document.addEventListener('mousemove',e=>{ if(cur) place(e); });
  window.addEventListener('scroll',()=>{ if(cur){cur=null; tip.style.opacity=0;} },true);
  // cabeceras de la tabla diaria (se regeneran con innerHTML en cada render)
  const dh=document.getElementById('dayHead');
  if(dh && window.MutationObserver){
    const tag=()=>{ const ks=(window.__DAY_COLS__||[]); dh.querySelectorAll('th').forEach((th,i)=>{ if(ks[i]&&METRIC_DEFS[ks[i]]) th.dataset.def=ks[i]; }); };
    new MutationObserver(tag).observe(dh,{childList:true}); tag();
  }
})();
</script>
"""

# ------------------------------------------------------------------------------
#  Nuevo "Resumen de performance" (sustituye al script original)
# ------------------------------------------------------------------------------
PERF_JS = r"""<script>
/* ==== Resumen de performance: filtro por métrica (WTD>10′ %, RR %, No Show %, % Incidencias, UTR) ==== */
(function(){
  const host = document.getElementById('perfSummary');
  if(!host) return;

  const WDATA  = (typeof DATA!=='undefined'       && Array.isArray(DATA))       ? DATA       : [];
  const WORDER = (typeof WEEK_ORDER!=='undefined' && Array.isArray(WEEK_ORDER)) ? WEEK_ORDER : [];
  const WLABEL = (typeof WEEK_LABEL!=='undefined' && WEEK_LABEL)                 ? WEEK_LABEL : {};
  const DDATA  = Array.isArray(window.__DAILY_DATA__) ? window.__DAILY_DATA__ : [];

  if(!WDATA.length && !DDATA.length){ host.style.display='none'; return; }
  host.style.display='';

  // unit: pct (eje izquierdo, %) | num (eje derecho) · better: down = más bajo es mejor
  const METRICS = [
    {k:'wtd10',    label:"WTD>10′ %",         short:"WTD>10′", color:'#0E5A6B', unit:'pct', better:'down'},
    {k:'reassign', label:'RR %',                   short:'RR',           color:'#5B54B8', unit:'pct', better:'down'},
    {k:'_noshows', label:'No Show %',              short:'No Show',      color:'#B5342A', unit:'pct', better:'down'},
    {k:'incpct',   label:'% Incidencias totales',  short:'Incidencias',  color:'#C07A12', unit:'pct', better:'down'},
    {k:'utr',      label:'UTR',                    short:'UTR',          color:'#167C58', unit:'num', better:'up'},
  ];

  // ==== Objetivo T1: sólo WTD>10' % (wtd10) y RR % (reassign). Fracción (2,29% = 0.0229) ====
  const TARGETS = {
    ALC:{wtd10:0.0270, reassign:0.0229},
    GRA:{wtd10:0.0228, reassign:0.0390},
    NOM:{wtd10:0.0405, reassign:0.0390},
    SAB:{wtd10:0.0225, reassign:0.0540},
    MAD:{wtd10:0.0315, reassign:0.0351},
  };
  const TARGETED = new Set(['wtd10','reassign']);

  const NODES = [...new Set([...WDATA.map(d=>d.city), ...DDATA.map(d=>d.city)].filter(Boolean))].sort();
  const cst = { node:'ALL', mode: WDATA.length ? 'weekly' : 'daily', sel: new Set(METRICS.map(m=>m.k)) };
  const selMetrics = ()=> METRICS.filter(m=>cst.sel.has(m.k));

  // ---- agregación a nivel de nodo ----
  const num = v => (typeof v==='number' && isFinite(v)) ? v : null;
  function wrate(rows, key){           // media ponderada por entregas; fallback media simple
    let n=0, d=0, sm=0, nm=0;
    for(const r of rows){
      const v=num(r[key]); if(v==null) continue;
      const w=(num(r.delivered)||0)>0 ? r.delivered : 0;
      n+=v*w; d+=w; sm+=v; nm++;
    }
    if(d>0) return n/d;
    return nm>0 ? sm/nm : null;
  }
  function reassignRate(rows){         // recuentos brutos (_reassign/_assigned) si existen
    let asg=0, rea=0, have=false;
    for(const r of rows){
      if(num(r._assigned)!=null){ asg+=r._assigned; have=true; }
      if(num(r._reassign)!=null){ rea+=r._reassign; }
    }
    if(have && asg>0) return rea/asg;
    return wrate(rows,'reassign');
  }
  function noShowRate(rows){           // franjas no show ÷ franjas reservadas (recuentos brutos)
    let ns=0, bk=0, have=false;
    for(const r of rows){
      if(num(r._ns)!=null && num(r._bk)!=null){ ns+=r._ns; bk+=r._bk; have=true; }
    }
    if(have) return bk>0 ? ns/bk : null;
    return wrate(rows,'_noshows');
  }
  function incRate(rows){              // incidencias S&L ÷ entregas
    let inc=0, dl=0, have=false;
    for(const r of rows){
      const i=num(r.incidents)!=null ? r.incidents : num(r.slInc);
      if(i!=null){ inc+=i; have=true; }
      dl+=(num(r.delivered)||0);
    }
    return (have && dl>0) ? inc/dl : null;
  }
  function utrRate(rows){              // entregas ÷ horas trabajadas
    let dl=0, wh=0;
    for(const r of rows){ dl+=(num(r.delivered)||0); wh+=(num(r.workingHours)||0); }
    return wh>0 ? dl/wh : null;
  }
  function metricVal(rows,k){
    if(k==='reassign') return reassignRate(rows);
    if(k==='_noshows') return noShowRate(rows);
    if(k==='incpct')   return incRate(rows);
    if(k==='utr')      return utrRate(rows);
    return wrate(rows,k);
  }

  function series(){
    const ms=selMetrics();
    if(cst.mode==='weekly'){
      const keys = WORDER.filter(w=>WDATA.some(d=>d.week===w));
      const labels = keys.map(w=>WLABEL[w]||w);
      const rowsFor = w => WDATA.filter(d=> d.week===w && (cst.node==='ALL'||d.city===cst.node));
      return { labels, lines: ms.map(m=>({m, vals: keys.map(w=>metricVal(rowsFor(w), m.k))})) };
    } else {
      const dateOf={}; DDATA.forEach(d=>{ dateOf[d.day]=d.date; });
      const keys = [...new Set(DDATA.map(d=>d.day))].sort((a,b)=> (dateOf[a]<dateOf[b]?-1:1));
      const rowsFor = dd => DDATA.filter(d=> d.day===dd && (cst.node==='ALL'||d.city===cst.node));
      return { labels: keys.slice(), lines: ms.map(m=>({m, vals: keys.map(dd=>metricVal(rowsFor(dd), m.k))})) };
    }
  }

  const fPct  = v => v==null ? '–' : (v*100).toLocaleString('es-ES',{minimumFractionDigits:1,maximumFractionDigits:1})+'%';
  const fPct2 = v => v==null ? '–' : (v*100).toLocaleString('es-ES',{minimumFractionDigits:2,maximumFractionDigits:2})+'%';
  const fNum  = v => v==null ? '–' : v.toLocaleString('es-ES',{minimumFractionDigits:2,maximumFractionDigits:2});
  const fmtM  = (m,v) => m.unit==='pct' ? fPct(v) : fNum(v);

  const wrap   = document.getElementById('perfChartWrap');
  const legend = document.getElementById('perfLegend');
  let tip = null;

  function poolRows(){
    const src = cst.mode==='weekly' ? WDATA : DDATA;
    return src.filter(d=> cst.node==='ALL' || d.city===cst.node);
  }
  function lastDelta(vals){
    const idx=[]; vals.forEach((v,i)=>{ if(v!=null) idx.push(i); });
    if(idx.length<2) return null;
    return vals[idx[idx.length-1]] - vals[idx[idx.length-2]];
  }
  function deltaHtml(m,d){
    if(d==null) return '';
    const isPct=m.unit==='pct';
    if(Math.abs(d)<(isPct?0.00005:0.005)) return '<small class="dlt flat">'+(isPct?'0,0 pp':'0,00')+'</small>';
    const txt = isPct ? Math.abs(d*100).toLocaleString('es-ES',{minimumFractionDigits:1,maximumFractionDigits:1})+' pp'
                      : Math.abs(d).toLocaleString('es-ES',{minimumFractionDigits:2,maximumFractionDigits:2});
    const worse = m.better==='down' ? d>0 : d<0;
    return `<small class="dlt ${worse?'bad':'good'}">${d>0?'▲':'▼'} ${txt}</small>`;
  }
  // Objetivo T1 del nodo actual. Nodo concreto -> su objetivo; 'Todos' -> media ponderada por volumen.
  function targetFor(k){
    if(!TARGETED.has(k)) return null;
    if(cst.node!=='ALL') return (TARGETS[cst.node]||{})[k] ?? null;
    let n=0, d=0; const byCity={};
    for(const r of poolRows()){
      const c=r.city; if(!c) continue;
      const w = (k==='reassign' && num(r._assigned)>0) ? r._assigned : (r.delivered||0);
      byCity[c]=(byCity[c]||0)+w;
    }
    for(const c in byCity){
      const t=(TARGETS[c]||{})[k]; if(t==null) continue;
      n+=t*byCity[c]; d+=byCity[c];
    }
    return d>0 ? n/d : null;
  }
  function gapHtml(overall, k){
    const t=targetFor(k);
    if(t==null || overall==null) return '';
    const gap=overall-t;
    const over=gap>0.00005, under=gap<-0.00005;
    const cls=over?'bad':(under?'good':'flat');
    const arrow=over?'▲':(under?'▼':'–');
    const pp=Math.abs(gap*100).toLocaleString('es-ES',{minimumFractionDigits:2,maximumFractionDigits:2});
    return `<div class="perf-target">Obj. T1 <b>${fPct2(t)}</b> · gap <span class="gap ${cls}">${arrow} ${pp} pp</span></div>`;
  }
  function renderNumbers(labels, lines){
    const pool=poolRows();
    document.getElementById('perfKpis').innerHTML = lines.map(s=>{
      const overall=metricVal(pool, s.m.k);
      return `<div class="stat perfstat" style="--c:${s.m.color}"><div class="k" data-def="${s.m.k}">${s.m.label}</div><div class="v">${fmtM(s.m,overall)} ${deltaHtml(s.m,lastDelta(s.vals))}</div>${gapHtml(overall, s.m.k)}</div>`;
    }).join('');
    const cap=document.getElementById('perfTableCap');
    cap.textContent=(cst.mode==='weekly'?'Datos por semana':'Datos por día')+(cst.node==='ALL'?' · todos los nodos':' · '+cst.node);
    const perLbl = cst.mode==='weekly' ? 'Semana' : 'Día';
    let h='<thead><tr><th class="lft">'+perLbl+'</th>'+lines.map(s=>'<th data-def="'+s.m.k+'">'+s.m.label+'</th>').join('')+'</tr></thead><tbody>';
    if(!labels.length){
      h+='<tr><td class="lft" colspan="'+(lines.length+1)+'">Sin datos para este nodo.</td></tr>';
    } else {
      labels.forEach((lb,i)=>{ h+='<tr><td class="lft">'+String(lb)+'</td>'+lines.map(s=>'<td>'+fmtM(s.m,s.vals[i])+'</td>').join('')+'</tr>'; });
      h+='<tr class="perf-tot"><td class="lft">Global</td>'+lines.map(s=>'<td>'+fmtM(s.m,metricVal(pool,s.m.k))+'</td>').join('')+'</tr>';
      if(lines.some(s=>TARGETED.has(s.m.k))){
        h+='<tr class="perf-tgt"><td class="lft">Objetivo T1</td>'+lines.map(s=>{const t=targetFor(s.m.k);return '<td>'+(t==null?'–':fPct2(t))+'</td>';}).join('')+'</tr>';
        h+='<tr class="perf-gap"><td class="lft">Gap vs T1</td>'+lines.map(s=>{const t=targetFor(s.m.k),ov=metricVal(pool,s.m.k);if(t==null||ov==null)return '<td>–</td>';const g=ov-t,cls=g>0.00005?'cell-bad':(g<-0.00005?'cell-good':'');const sg=g>0?'+':'';return '<td class="'+cls+'">'+sg+(g*100).toLocaleString('es-ES',{minimumFractionDigits:2,maximumFractionDigits:2})+' pp</td>';}).join('')+'</tr>';
      }
    }
    h+='</tbody>';
    document.getElementById('perfTable').innerHTML=h;
  }
  function niceTop(v, step){ let t=Math.ceil(v/step)*step; return t<=0?step:t; }

  function draw(){
    const {labels, lines} = series();
    const n = labels.length;
    legend.innerHTML = lines.map(s=>`<span class="lg" data-def="${s.m.k}"><span class="sw" style="background:${s.m.color}"></span>${s.m.label}${s.m.unit==='num'&&lines.some(x=>x.m.unit==='pct')?' <span style="color:var(--faint)">(eje dcho.)</span>':''}</span>`).join('')
      + (lines.length===1 && TARGETED.has(lines[0].m.k) ? `<span class="lg"><span class="sw" style="background:repeating-linear-gradient(90deg,${lines[0].m.color} 0 4px,transparent 4px 7px)"></span>Objetivo T1</span>` : '');
    renderNumbers(labels, lines);

    if(!n){ wrap.innerHTML='<div class="chartempty">Sin datos para este nodo.</div>'; return; }

    const pctL=lines.filter(s=>s.m.unit==='pct'), numL=lines.filter(s=>s.m.unit==='num');
    const dual = pctL.length && numL.length;
    const W=920, H=360, pad={t:20,r:dual?58:22,b:54,l:54};
    const iw=W-pad.l-pad.r, ih=H-pad.t-pad.b;

    const single = lines.length===1 ? lines[0] : null;
    const tgt = single ? targetFor(single.m.k) : null;
    const maxOf = (ls, extra) => { let mx=extra||0, any=false; ls.forEach(s=>s.vals.forEach(v=>{ if(v!=null){ any=true; if(v>mx)mx=v; } })); return {mx, any}; };
    const P=maxOf(pctL, tgt||0), N=maxOf(numL, 0);
    if(!P.any && !N.any){ wrap.innerHTML='<div class="chartempty">Sin datos para este nodo.</div>'; return; }
    const topP = niceTop(Math.max(P.mx,0.02)*1.05, P.mx*1.05>0.2?0.05:0.02);
    const topN = niceTop(Math.max(N.mx,0.5)*1.08, 0.5);

    const xOf = i => n<=1 ? pad.l+iw/2 : pad.l + iw*i/(n-1);
    const yP  = v => pad.t + ih*(1-(v/topP));
    const yN  = v => pad.t + ih*(1-(v/topN));
    const yOf = m => m.unit==='pct' ? yP : yN;

    let svg = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Tendencia de performance">`;
    const yt=4, leftIsPct = pctL.length>0;
    for(let i=0;i<=yt;i++){
      const y=pad.t+ih*(1-i/yt);
      svg += `<line class="gl" x1="${pad.l}" y1="${y}" x2="${W-pad.r}" y2="${y}"></line>`;
      const lv = leftIsPct ? (topP*i/yt*100).toLocaleString('es-ES',{maximumFractionDigits:1})+'%'
                           : (topN*i/yt).toLocaleString('es-ES',{maximumFractionDigits:2});
      svg += `<text class="ylab" x="${pad.l-8}" y="${y+3.5}" text-anchor="end">${lv}</text>`;
      if(dual) svg += `<text class="ylab" x="${W-pad.r+8}" y="${y+3.5}" text-anchor="start" style="fill:${numL[0].m.color}">${(topN*i/yt).toLocaleString('es-ES',{maximumFractionDigits:2})}</text>`;
    }
    const rot = n>7;
    labels.forEach((lb,i)=>{
      const x=xOf(i);
      svg += `<text class="xlab" x="${x}" y="${H-pad.b+18}" text-anchor="${rot?'end':'middle'}" transform="${rot?`rotate(-32 ${x} ${H-pad.b+18})`:''}">${String(lb)}</text>`;
    });
    svg += `<line class="axis" x1="${pad.l}" y1="${pad.t}" x2="${pad.l}" y2="${H-pad.b}"></line>`;
    if(dual) svg += `<line class="axis" x1="${W-pad.r}" y1="${pad.t}" x2="${W-pad.r}" y2="${H-pad.b}"></line>`;
    svg += `<line class="axis" x1="${pad.l}" y1="${H-pad.b}" x2="${W-pad.r}" y2="${H-pad.b}"></line>`;
    if(tgt!=null){
      const y=yP(tgt);
      svg += `<line x1="${pad.l}" y1="${y}" x2="${W-pad.r}" y2="${y}" stroke="${single.m.color}" stroke-width="1.6" stroke-dasharray="6 5" opacity=".75"></line>`;
      svg += `<text x="${pad.l+6}" y="${y-6}" text-anchor="start" style="fill:${single.m.color};font-family:var(--mono);font-size:10.5px">Obj. T1 ${fPct2(tgt)}</text>`;
    }
    svg += `<line class="cross" id="perfCross" x1="0" y1="${pad.t}" x2="0" y2="${H-pad.b}"></line>`;

    lines.forEach(s=>{
      const Y=yOf(s.m); let seg=[];
      const flush=()=>{ if(seg.length>=2){ svg += `<polyline fill="none" stroke="${s.m.color}" stroke-width="2.4" stroke-linejoin="round" stroke-linecap="round"${s.m.unit==='num'&&dual?' stroke-dasharray="1 0"':''} points="${seg.map(p=>p[0]+','+p[1]).join(' ')}"></polyline>`; } seg=[]; };
      s.vals.forEach((v,i)=>{ if(v==null){ flush(); } else { seg.push([xOf(i),Y(v)]); } });
      flush();
      s.vals.forEach((v,i)=>{ if(v!=null) svg += `<circle class="dot" cx="${xOf(i)}" cy="${Y(v)}" r="${single?4:3.4}" fill="${s.m.color}"></circle>`; });
      if(single){   // etiqueta de valor en cada punto cuando hay una sola métrica
        s.vals.forEach((v,i)=>{ if(v!=null) svg += `<text x="${xOf(i)}" y="${Y(v)-9}" text-anchor="middle" style="fill:${s.m.color};font-family:var(--mono);font-size:10.5px;font-weight:600">${fmtM(s.m,v)}</text>`; });
      }
    });

    for(let i=0;i<n;i++){
      const x0 = n<=1 ? pad.l : pad.l+iw*(i-0.5)/(n-1);
      const x1 = n<=1 ? W-pad.r : pad.l+iw*(i+0.5)/(n-1);
      const cx0=Math.max(pad.l,x0), cx1=Math.min(W-pad.r,x1);
      svg += `<rect class="hit" data-i="${i}" x="${cx0}" y="${pad.t}" width="${Math.max(1,cx1-cx0)}" height="${ih}"></rect>`;
    }
    svg += '</svg>';
    wrap.innerHTML = svg;

    if(!tip){ tip=document.createElement('div'); tip.className='charttip'; }
    wrap.appendChild(tip); tip.style.opacity=0;

    const svgEl = wrap.querySelector('svg');
    const cross = wrap.querySelector('#perfCross');
    const show = i => {
      const x=xOf(i);
      cross.setAttribute('x1',x); cross.setAttribute('x2',x); cross.style.opacity=1;
      const rows = lines.map(s=>`<div class="tt-row"><span class="tt-sw" style="background:${s.m.color}"></span>${s.m.label}<span class="tt-v">${fmtM(s.m,s.vals[i])}</span></div>`).join('')
        + (tgt!=null ? `<div class="tt-row" style="color:#cbd2da">Objetivo T1<span class="tt-v">${fPct2(tgt)}</span></div>` : '');
      tip.innerHTML = `<div class="tt-x">${String(labels[i])}</div>${rows}`;
      const r=svgEl.getBoundingClientRect();
      const px=r.width*(x/W);
      tip.style.left=Math.max(88,Math.min(r.width-88,px))+'px';
      tip.style.top=(r.height*(pad.t/H)+4)+'px';
      tip.style.opacity=1;
    };
    const hide = ()=>{ cross.style.opacity=0; tip.style.opacity=0; };
    wrap.querySelectorAll('.hit').forEach(h=>{
      const i=+h.dataset.i;
      h.addEventListener('mouseenter',()=>show(i));
      h.addEventListener('mousemove',()=>show(i));
    });
    svgEl.addEventListener('mouseleave',hide);
  }

  // ---- selector de métrica ----
  const metSeg = document.getElementById('perfMetricSeg');
  function buildMetrics(){
    const all = cst.sel.size===METRICS.length;
    let h = `<button data-k="ALL" aria-pressed="${all}">Todas</button>`;
    METRICS.forEach(m=> h += `<button data-k="${m.k}" data-def="${m.k}" aria-pressed="${!all && cst.sel.has(m.k)}"><span class="msw" style="background:${m.color}"></span>${m.short}</button>`);
    metSeg.innerHTML=h;
    metSeg.querySelectorAll('button').forEach(b=> b.onclick=()=>{
      const k=b.dataset.k;
      if(k==='ALL'){ cst.sel=new Set(METRICS.map(m=>m.k)); }
      else if(cst.sel.size===METRICS.length){ cst.sel=new Set([k]); }       // desde «Todas»: sólo esa
      else if(cst.sel.has(k)){ if(cst.sel.size>1) cst.sel.delete(k); else cst.sel=new Set(METRICS.map(m=>m.k)); }
      else { cst.sel.add(k); }
      buildMetrics(); draw();
    });
  }

  // ---- selector de nodo ----
  const nodeSeg = document.getElementById('perfNodeSeg');
  function buildNodes(){
    let h = `<button data-n="ALL" aria-pressed="${cst.node==='ALL'}">Todos</button>`;
    NODES.forEach(nd=> h += `<button data-n="${nd}" aria-pressed="${cst.node===nd}">${nd}</button>`);
    nodeSeg.innerHTML=h;
    nodeSeg.querySelectorAll('button').forEach(b=> b.onclick=()=>{ cst.node=b.dataset.n; buildNodes(); draw(); });
  }

  // ---- selector de modo (semanal / diario) ----
  const modeSeg = document.getElementById('perfModeSeg');
  modeSeg.querySelectorAll('button').forEach(b=>{
    const hasData = b.dataset.m==='weekly' ? WDATA.length : DDATA.length;
    if(!hasData){ b.disabled=true; b.style.opacity=.4; b.style.cursor='not-allowed'; }
    b.setAttribute('aria-pressed', String(b.dataset.m===cst.mode));
    b.addEventListener('click',()=>{
      if(b.disabled) return;
      cst.mode=b.dataset.m;
      modeSeg.querySelectorAll('button').forEach(x=>x.setAttribute('aria-pressed', String(x===b)));
      draw();
    });
  });

  buildMetrics();
  buildNodes();
  draw();
})();
</script>"""

PERF_CSS = """<style id="perf-metric-css">
  .perfkpis{grid-template-columns:repeat(auto-fit,minmax(190px,1fr))!important}
  #perfMetricSeg .msw{display:inline-block;width:9px;height:9px;border-radius:2px;margin-right:6px;vertical-align:0}
  #perfMetricSeg button[aria-pressed="true"] .msw{box-shadow:0 0 0 1.5px #fff}
  .perfhint{font-size:11.5px;color:var(--faint)}
</style>
"""


def _rep(h, old, new, what, required=True):
    if old not in h:
        if required:
            raise ValueError("no encuentro el ancla: " + what)
        return h
    return h.replace(old, new, 1)


def patch(html):
    """Devuelve el HTML del dashboard con el filtro de métricas y las definiciones."""
    if MARK in html:
        return html
    h = html

    # 1) Resumen de performance: subtítulo + fila de filtro de métrica
    h = _rep(h,
        '<div class="perfsub">Tendencia de WTD&gt;10&#8242; %, Reassignment % y No Show % a nivel de nodo · Gap vs Objetivo T1 (WTD% y RR%)</div>',
        '<div class="perfsub">Tendencia de WTD&gt;10&#8242; %, RR %, No Show %, % Incidencias totales y UTR a nivel de nodo · Gap vs Objetivo T1 (WTD% y RR%)</div>',
        "subtítulo del resumen", required=False)
    h = _rep(h,
        '<div class="field" style="margin-bottom:6px">\n      <span class="lbl">Nodo</span>',
        '<div class="field" style="margin-bottom:6px">\n      <span class="lbl">Métrica</span>\n'
        '      <div class="seg" id="perfMetricSeg"></div>\n'
        '      <span class="perfhint">Pulsa una métrica para verla sola (con su objetivo); pulsa otras para compararlas</span>\n'
        '    </div>\n'
        '    <div class="field" style="margin-bottom:6px">\n      <span class="lbl">Nodo</span>',
        "selector de nodo del resumen")

    # 2) Sustituir el script del resumen de performance
    ini = h.find("/* ==== Resumen de performance: WTD>10' %, Reassignment %, No Show % ==== */")
    if ini < 0:
        raise ValueError("no encuentro el script del Resumen de performance")
    s0 = h.rfind("<script>", 0, ini)
    s1 = h.find("</script>", ini) + len("</script>")
    h = h[:s0] + PERF_JS + h[s1:]
    h = _rep(h, "</head>", PERF_CSS + "</head>", "</head>")

    # 3) Definiciones en las cabeceras de la tabla principal
    h = _rep(h, "    th.textContent=label;\n",
             "    th.textContent=label;\n"
             "    if(typeof METRIC_DEFS!=='undefined' && METRIC_DEFS[c.k]){ th.dataset.def=c.k; if(isAgg() && c.grp!=='id') th.dataset.agg=c.agg; }\n",
             "cabecera de la tabla semanal")
    # METRIC_DEFS tiene que existir antes del primer render: se define arriba del todo
    h = _rep(h, "<script>\nconst DATA = ", "<script>\n" + DEFS_JS + "\nconst DATA = ", "inicio de DATA")

    # 4) Vista agregada: los % "first" (RR y desgloses) pasan a total/media del periodo
    h = _rep(h,
        '      if(c.agg==="first"){ rec[c.k]=list[0][c.k]; }\n',
        '      if(c.agg==="first"){\n'
        '        if(c.grp==="id" || typeof list[0][c.k]!=="number"){ rec[c.k]=list[0][c.k]; }\n'
        '        else if(c.k==="reassign" && list.some(x=>typeof x._assigned==="number")){\n'
        '          const a=list.reduce((s,x)=>s+(x._assigned||0),0), r=list.reduce((s,x)=>s+(x._reassign||0),0);\n'
        '          rec[c.k]=a>0?r/a:null;\n'
        '        } else {\n'
        '          // media ponderada por pedidos asignados si existen; si no, media simple\n'
        '          let n=0,d=0,sm=0,nm=0; list.forEach(x=>{const v=x[c.k]; if(v==null)return; const w=x._assigned||0; n+=v*w; d+=w; sm+=v; nm++;});\n'
        '          rec[c.k]=d>0?n/d:(nm?sm/nm:null);\n'
        '        }\n'
        '      }\n',
        "agregado 'first'")
    h = _rep(h,
        '&#183; &#916; = variaci&#243;n del &#250;ltimo periodo vs anterior (pp), &#9660; = mejora',
        '&#183; &#916; = variaci&#243;n del &#250;ltimo periodo vs anterior (pp; en UTR, unidades) &#183; verde = mejora, rojo = empeora &#183; pasa el rat&#243;n por una m&#233;trica para ver su definici&#243;n',
        "nota del resumen", required=False)

    # 5) Tabla diaria: exponer las claves de columna para el tooltip
    h = _rep(h, "  const dateOf={}; DAILY.forEach(d=>{dateOf[d.day]=d.date;});",
             "  window.__DAY_COLS__=COLS.map(c=>c.k);\n  const dateOf={}; DAILY.forEach(d=>{dateOf[d.day]=d.date;});",
             "tabla diaria", required=False)

    # 6) Tooltip global (al final, antes de </body>)
    i = h.rindex("</body>")
    h = h[:i] + TOOLTIP + h[i:]
    return h


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Uso: python3 patch_perf_metricas.py entrada.html salida.html"); sys.exit(1)
    src = open(sys.argv[1], encoding="utf-8").read()
    open(sys.argv[2], "w", encoding="utf-8").write(patch(src))
    print("OK -> " + sys.argv[2])
