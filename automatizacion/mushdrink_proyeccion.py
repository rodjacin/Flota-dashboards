# -*- coding: utf-8 -*-
"""
Pestaña «Proyección vs WK-1» del panel MushDrink (mushdrink/index.html).

Una fila por restaurante, fecha proyectada y franja de 30 min:
  · Pedidos y riders proyectados de la franja, del CSV «ProyeccionPedidos»
    (ID = código del restaurante, Pedidos_Proyectados, Ratio_por_Cluster = riders proyectados).
  · La misma franja del mismo día de la semana anterior (WK-1, fecha − 7 días), con datos del panel,
    asignando cada pedido a la franja por su hora de solicitud: riders distintos que entregaron
    («Pedidos por rider · 15 min»), pedidos, % >45 min, aviso HD medio y Aceptado > En camino medio (AVHD).
    Si la WK-1 aún no tiene datos (fecha futura), se usa el último mismo día de la semana con datos y se marca.
  · Las franjas de 00:00 a 06:59 son la madrugada del mismo día operativo (07:00–06:59).

Las proyecciones se acumulan en mushdrink/proyeccion_pedidos.csv (un CSV nuevo sustituye las fechas que trae).

Uso: python3 mushdrink_proyeccion.py [mushdrink/index.html] [--csv ProyeccionPedidos.csv]
     (mushdrink_dia.py lo llama cada día para refrescar la WK-1)
"""
import os, re, sys, json, csv, argparse, datetime as dt

HERE = os.path.dirname(os.path.abspath(__file__))
MARCA = "<!-- PROYECCION_WK1 -->"
TAB = "Proyección vs WK-1"
STORE = os.path.join(HERE, "..", "mushdrink", "proyeccion_pedidos.csv")
DIAS_HIST = 63


def getv(d, name):
    m = re.search(r'(?:const|let|var)\s+' + name + r'\s*=\s*', d)
    return json.JSONDecoder().raw_decode(d[m.end():])[0] if m else None


def lee_csv(p):
    rows = []
    with open(p, encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f, delimiter=";"):
            try:
                d = dt.datetime.strptime(r["Fecha"].strip(), "%d/%m/%Y").date().isoformat()
                rows.append({"ID": str(int(r["ID"])), "Fecha": d, "Hora": r["Hora"].strip()[:5],
                             "Pedidos": int(float(r["Pedidos_Proyectados"] or 0)),
                             "Riders": int(float(r["Ratio_por_Cluster"] or 0))})
            except (ValueError, KeyError):
                continue
    return rows


def store_merge(nuevo):
    viejo = []
    if os.path.exists(STORE):
        with open(STORE, encoding="utf-8", newline="") as f:
            viejo = [dict(r, Pedidos=int(r["Pedidos"]), Riders=int(r["Riders"])) for r in csv.DictReader(f)]
    fechas = {r["Fecha"] for r in nuevo}
    todo = [r for r in viejo if r["Fecha"] not in fechas] + nuevo
    todo.sort(key=lambda r: (r["Fecha"], int(r["ID"]), r["Hora"]))
    with open(STORE, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["ID", "Fecha", "Hora", "Pedidos", "Riders"]); w.writeheader(); w.writerows(todo)
    return todo


def slot_hm(hhmm):
    """franja de 30 min del día operativo (07:00–06:59): 07:00 → 14 … 06:30 → 61"""
    h, m = int(hhmm[:2]), int(hhmm[3:5])
    return (h + 24 if h < 7 else h) * 2 + m // 30


def datos(docs, proy):
    EC = getv(docs[9], "EC"); AV = getv(docs[3], "AVHD"); DS = getv(docs[3], "DS"); AGG = getv(docs[2], "AGG")
    # proyección por franja: P[fecha][code] = [[franja, pedidos, riders teóricos], …]
    P = {}
    for r in proy:
        P.setdefault(r["Fecha"], {}).setdefault(r["ID"], []).append([slot_hm(r["Hora"]), r["Pedidos"], r["Riders"]])
    for f in P:
        for c in P[f]:
            P[f][c].sort()
    # fecha WK-1 de cada fecha proyectada: fecha − 7; si no hay datos, el último mismo día de la semana con datos
    hist = sorted(AV)
    REF = {}
    for f in P:
        d = dt.date.fromisoformat(f); w1 = (d - dt.timedelta(days=7)).isoformat()
        if w1 in AV:
            REF[f] = {"f": w1, "exacta": True}
        else:
            cand = [x for x in hist if x < w1 and dt.date.fromisoformat(x).weekday() == d.weekday()]
            REF[f] = {"f": cand[-1] if cand else None, "exacta": False, "w1": w1}
    # WK-1 por franja: M[fecha_ref][code] = {franja: [riders, pedidos, >45, aviso HD medio min, acept>camino medio min]}
    M = {}
    for fr in sorted({r["f"] for r in REF.values() if r["f"]}):
        acc = {}
        for c, L in (AV.get(fr) or {}).items():
            for o in L:
                t = o[1][11:16]; sl = slot_hm(t)
                a = acc.setdefault(c, {}).setdefault(sl, [set(), 0, 0, 0.0, 0, 0.0, 0])
                a[1] += 1; a[2] += o[5] > 2700
                if o[3] is not None and 0 <= o[3] < 7200: a[3] += o[3]; a[4] += 1
                if o[4]: a[5] += sum(o[4]); a[6] += 1
        for k, arr in AGG["data"].items():
            c, f = k.split("|")
            if f != fr:
                continue
            for i in range(0, len(arr), 3):
                ri, s15 = arr[i], arr[i + 1]
                h, m = s15 // 4, (s15 % 4) * 15
                sl = (h + 24 if h < 7 else h) * 2 + m // 30
                acc.setdefault(c, {}).setdefault(sl, [set(), 0, 0, 0.0, 0, 0.0, 0])[0].add(ri)
        M[fr] = {c: {str(sl): [len(a[0]), a[1], a[2], round(a[3] / a[4] / 60, 1) if a[4] else None,
                               round(a[5] / a[6] / 60, 1) if a[6] else None] for sl, a in d.items()} for c, d in acc.items()}
    codes = set(c for v in P.values() for c in v)
    R = {}
    for r in DS["restaurants"]:
        c = str(r["code"])
        if c in codes:
            R[c] = {"n": r.get("name") or c, "o": r.get("owner") or ""}
    for c in codes:
        R.setdefault(c, {"n": (EC.get("names") or {}).get(c, c), "o": (EC.get("coord") or {}).get(c, "")})
    return {"P": P, "M": M, "REF": REF, "R": R, "hist": [hist[0], hist[-1]] if hist else None,
            "generado": dt.datetime.now().strftime("%Y-%m-%d %H:%M")}


def html_doc(data):
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    return MARCA + r"""<!DOCTYPE html>
<html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Proyección vs WK-1</title>
<style>
:root{--bg:#F6F7F9;--card:#fff;--line:#E4E7EC;--ink:#14171F;--ink2:#4B5563;--mut:#6B7280;--acc:#0E5A6B;--red:#B42318;--redbg:#FEE4E2;--amb:#93370D;--ambbg:#FEF0C7;--grn:#05603A;--grnbg:#D1FADF}
*{box-sizing:border-box} body{margin:0;background:var(--bg);color:var(--ink);font-family:Inter,-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;font-size:14px}
.wrap{max-width:1500px;margin:0 auto;padding:18px 18px 40px;display:flex;flex-direction:column;gap:14px}
h1{font-size:19px;margin:0;font-weight:650} .sub{color:var(--ink2);font-size:12.5px;margin-top:4px;max-width:130ch;line-height:1.5}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px 16px}
.filters{display:flex;flex-wrap:wrap;gap:14px;align-items:flex-end;position:sticky;top:0;z-index:5}
.fg{display:flex;flex-direction:column;gap:5px} .fg>span{font-size:10.5px;letter-spacing:.07em;text-transform:uppercase;color:var(--mut);font-weight:600}
input,select{font:inherit;font-size:13px;border:1px solid var(--line);border-radius:8px;padding:6px 9px;background:#fff;color:var(--ink);height:34px;max-width:260px}
#q{width:220px} .nav{display:flex;gap:6px} .nav button,.reset{height:34px;border:1px solid var(--line);background:#fff;border-radius:8px;padding:0 10px;cursor:pointer}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:10px}
.kpi{background:#fff;border:1px solid var(--line);border-radius:12px;padding:11px 14px} .kpi b{display:block;font-size:22px;font-variant-numeric:tabular-nums} .kpi span{font-size:12px;color:var(--ink2)}
table{border-collapse:collapse;width:100%;font-size:12.8px}
th{background:#F0F2F5;color:var(--mut);font-size:10.5px;text-transform:uppercase;letter-spacing:.03em;padding:7px 8px;text-align:right;cursor:pointer;position:sticky;top:0;vertical-align:bottom;line-height:1.3}
th.g{background:#E6EEF0;color:var(--acc)}
td{padding:6px 8px;border-top:1px solid #EEF0F3;text-align:right;white-space:nowrap;font-variant-numeric:tabular-nums}
th.l,td.l{text-align:left} .sm{display:block;font-size:11px;color:var(--mut)}
.neg{color:var(--red);font-weight:650} .ok{color:var(--grn)} .mut{color:var(--mut)} .warn{color:var(--amb)}
.pill{display:inline-block;padding:2px 9px;border-radius:99px;font-weight:700;font-size:12px;background:var(--redbg);color:var(--red)}
.flag{display:inline-block;font-size:10.5px;background:var(--ambbg);color:var(--amb);border-radius:99px;padding:1px 7px;margin-left:4px}
.note{color:var(--mut);font-size:12px;line-height:1.6;margin:0}
.tip{position:fixed;pointer-events:none;background:#14171F;color:#fff;font-size:12px;line-height:1.5;padding:7px 10px;border-radius:7px;z-index:20;max-width:340px}
.tip[hidden]{display:none} [data-t]{cursor:help}
</style></head><body>
<div class="wrap">
  <div><h1>Proyección por franja de 30 min vs mismo día de la semana anterior (WK-1)</h1>
  <div class="sub">Pedidos y riders proyectados en cada franja de 30 min, frente a la misma franja del mismo día de la semana anterior: riders que entregaron, pedidos, % &gt;45 min, aviso HD y Aceptado &gt; En camino. <span id="sub"></span></div></div>
  <div class="card filters">
    <div class="fg"><span>Buscador</span><input id="q" type="search" placeholder="Restaurante o código"></div>
    <div class="fg"><span>Código</span><select id="cod"></select></div>
    <div class="fg"><span>Restaurante</span><select id="rest"></select></div>
    <div class="fg"><span>Coordinador</span><select id="coord"></select></div>
    <div class="fg"><span>Semana</span><select id="sem"></select></div>
    <div class="fg"><span>Fecha</span><div class="nav"><button id="prev">◀</button><select id="fecha"></select><button id="next">▶</button></div></div>
    <div class="fg"><span>Franja</span><select id="fr"></select></div>
    <label style="display:flex;gap:6px;align-items:center;height:34px;font-size:13px;color:var(--ink2)"><input id="solo" type="checkbox" style="height:auto"> Solo alertas</label>
    <button class="reset" id="reset">Limpiar filtros</button>
  </div>
  <div class="kpis" id="kpis"></div>
  <div class="card" style="overflow:auto;max-height:75vh"><table id="tab"></table></div>
  <p class="note" id="note"></p>
</div>
<div class="tip" id="tip" hidden></div>
<script>
const A=""" + payload + r""";
const $=id=>document.getElementById(id);
const DW=['dom','lun','mar','mié','jue','vie','sáb'];
const pd=s=>new Date(s+'T12:00:00');
const iso=d=>d.getFullYear()+'-'+String(d.getMonth()+1).padStart(2,'0')+'-'+String(d.getDate()).padStart(2,'0');
const dl=s=>DW[pd(s).getDay()]+' '+s.slice(8,10)+'/'+s.slice(5,7);
const wk=s=>{const d=pd(s);const t=new Date(Date.UTC(d.getFullYear(),d.getMonth(),d.getDate()));const n=t.getUTCDay()||7;t.setUTCDate(t.getUTCDate()+4-n);const y=new Date(Date.UTC(t.getUTCFullYear(),0,1));return 'W'+String(Math.ceil(((t-y)/864e5+1)/7)).padStart(2,'0');};
const nf=(v,d=0)=>v==null||!isFinite(v)?'—':v.toLocaleString('es-ES',{minimumFractionDigits:d,maximumFractionDigits:d});
const FECHAS=Object.keys(A.P).sort();
const sl=n=>{const h=Math.floor(n/2)%24;return String(h).padStart(2,'0')+':'+(n%2?'30':'00');};
const REF=A.REF;
const filas=[];FECHAS.forEach(f=>{const r=REF[f];Object.entries(A.P[f]).forEach(([c,L])=>{const R=A.R[c]||{n:c,o:''};const MM=r.f&&A.M[r.f]&&A.M[r.f][c]||{};
  L.forEach(([s,p,t])=>{const tiene=Object.keys(MM).length>0;const m=MM[s]||(tiene?[0,0,0,null,null]:null);if(!p&&!t&&!(MM[s]))return;
    filas.push({f,w:wk(f),s,c,n:R.n,o:R.o||'',pd:p,rt:t,rf:r,rw:m?m[0]:null,np:m?m[1]:null,l45:m&&m[1]?m[2]/m[1]:null,hd:m?m[3]:null,tie:m?m[4]:null,dif:m?m[0]-t:null,dp:m?p-m[1]:null,al:!!(m&&m[0]-t<0&&m[1]&&m[2]/m[1]>0.10&&m[3]!=null&&m[3]<6&&m[4]!=null&&m[4]<12)?1:0,ord:c.padStart(6,'0')+'|'+f+'|'+String(s).padStart(2,'0')});});});});
const S={q:'',cod:'',rest:'',coord:'',sem:'',fecha:'',fr:'',solo:false,sort:'ord',asc:true};
const opt=(l,all)=>`<option value="">${all}</option>`+l.map(x=>`<option value="${x[0]}">${x[1]}</option>`).join('');
const uniq=(k,lab)=>[...new Map(filas.map(x=>[x[k],lab(x)])).entries()];
$('cod').innerHTML=opt(uniq('c',x=>x.c).sort((a,b)=>+a[0]-+b[0]),'Todos');
$('rest').innerHTML=opt(uniq('n',x=>x.n).sort((a,b)=>a[1].localeCompare(b[1])),'Todos');
$('coord').innerHTML=opt(uniq('o',x=>x.o||'(sin coordinador)').sort((a,b)=>a[1].localeCompare(b[1])),'Todos');
$('fr').innerHTML=opt([...new Set(filas.map(x=>x.s))].sort((a,b)=>a-b).map(x=>[String(x),sl(x)+'–'+sl(x+1)]),'Todas');
$('sem').innerHTML=opt([...new Set(FECHAS.map(wk))].map(w=>{const fs=FECHAS.filter(f=>wk(f)===w);return [w,w+' · '+dl(fs[0])+'–'+dl(fs[fs.length-1])];}),'Todas');
function fechasSem(){return FECHAS.filter(f=>!S.sem||wk(f)===S.sem);}
function fillFecha(){const fs=fechasSem();$('fecha').innerHTML=`<option value="">Todas (${fs.length})</option>`+fs.map(f=>`<option value="${f}">${dl(f)}/${f.slice(2,4)}</option>`).join('');if(S.fecha&&!fs.includes(S.fecha))S.fecha='';$('fecha').value=S.fecha;}
const sgn=(v,neutro)=>v==null?'<span class="mut">—</span>':`<b class="${neutro?(v>0?'warn':v<0?'mut':'mut'):(v<0?'neg':v>0?'ok':'mut')}">${v>0?'+':v<0?'−':''}${Math.abs(v)}</b>`;
const cell=(v,d,suf,cls)=>v==null?'<span class="mut">—</span>':`<span class="${cls||''}">${nf(v,d)}${suf||''}</span>`;
function render(){
  const rows=filas.filter(x=>(!S.q||(x.c+' '+x.n).toLowerCase().includes(S.q))&&(!S.cod||x.c===S.cod)&&(!S.rest||x.n===S.rest)&&(!S.coord||x.o===S.coord)&&(!S.sem||x.w===S.sem)&&(!S.fecha||x.f===S.fecha)&&(!S.fr||String(x.s)===S.fr)&&(!S.solo||x.al));
  const val=x=>x[S.sort];
  rows.sort((a,b)=>{const va=val(a),vb=val(b);if(va==null&&vb==null)return 0;if(va==null)return 1;if(vb==null)return -1;return(va<vb?-1:va>vb?1:0)*(S.asc?1:-1);});
  const sum=k=>rows.reduce((a,x)=>a+(x[k]||0),0);
  const np=sum('np'),late=rows.reduce((a,x)=>a+(x.np&&x.l45!=null?x.l45*x.np:0),0);
  const falt=rows.filter(x=>x.dif!=null&&x.dif<0).length,dsum=rows.reduce((a,x)=>a+(x.dif||0),0);
  $('kpis').innerHTML=[[nf(rows.length),'Franjas de 30 min'],[`<span class="${rows.some(x=>x.al)?'neg':''}">${nf(rows.filter(x=>x.al).length)}</span>`,'Franjas en alerta'],[nf(sum('pd')),'Pedidos proyectados'],[nf(sum('np')),'Pedidos WK-1'],[(()=>{const v=sum('pd')-sum('np');return (v>0?'+':v<0?'−':'')+nf(Math.abs(v));})(),'Pedidos proyectados − WK-1'],[`<span class="${falt?'neg':''}">${falt}</span>`,'Franjas con menos riders WK-1 que proyectados'],[`<span class="${dsum<0?'neg':'ok'}">${dsum>0?'+':''}${nf(dsum)}</span>`,'Suma riders WK-1 − proyectados'],[np?nf(late/np*100,1)+' %':'—','% pedidos >45 min WK-1']].map(([b,s])=>`<div class="kpi"><b>${b}</b><span>${s}</span></div>`).join('');
  const th=(k,l,t,cl)=>`<th class="${cl||''}" data-k="${k}" ${t?`data-t="${t}"`:''}>${l}${S.sort===k?(S.asc?' ▲':' ▼'):''}</th>`;
  $('tab').innerHTML='<thead><tr>'+th('o','Coordinador','','l')+th('al','Alerta','Alerta si se cumplen las 4 condiciones en la franja: riders WK-1 − proyectados &lt; 0 · % &gt;45 min WK-1 &gt; 10 % · aviso HD WK-1 &lt; 6 min · Aceptado &gt; En camino WK-1 &lt; 12 min. Es decir: hubo pedidos tarde que no se explican por HD ni por cocina, y faltaron riders.','l')+th('f','Fecha','Fecha proyectada · debajo, la fecha WK-1 con la que se compara.','l')+th('s','Franja','Intervalo de 30 min por hora de solicitud del pedido. De 00:00 a 06:59 es la madrugada del mismo día operativo.','l')+th('c','Código','','l')+th('n','Restaurante','','l')+
    th('pd','Pedidos<br>proyectados','Pedidos_Proyectados de la franja (CSV de proyección).')+th('np','Pedidos<br>WK-1','Pedidos entregados solicitados en esa franja el mismo día de la semana anterior.','g')+
    th('dp','Pedidos proy. −<br>WK-1','Pedidos proyectados menos pedidos de WK-1 en la misma franja. Positivo = se esperan más pedidos que la semana anterior; negativo = menos. Pulsa para ordenar de mayor a menor o al revés.','g')+
    th('rt','Riders<br>proyectados','Ratio_por_Cluster de la franja (CSV de proyección).')+th('rw','Riders WK-1','Riders distintos que entregaron pedidos solicitados en esa franja el mismo día de la semana anterior. En rojo si son menos que los proyectados.','g')+
    th('dif','Riders WK-1 −<br>proyectados','Riders que entregaron en la franja en WK-1 menos riders proyectados. Negativo (rojo) = en WK-1 hubo menos riders de los que se proyectan; positivo (verde) = hubo más. Pulsa para ordenar de mayor a menor o al revés.','g')+
    th('l45','% &gt;45 min<br>WK-1','Pedidos de la franja con más de 45 min desde la solicitud del cliente hasta la entrega.','g')+
    th('hd','Aviso HD<br>WK-1 (min)','Media desde que el cliente confirma el pedido hasta que llega a la API de HD, pedidos de la franja.','g')+
    th('tie','Aceptado &gt; En camino<br>WK-1 (min)','Media de minutos entre que el rider acepta y marca En camino, pedidos de la franja.','g')+'</tr></thead><tbody>'+
    rows.slice(0,4000).map(x=>`<tr${x.al?' style="background:#FFF5F4"':''}><td class="l">${x.o||'<span class="mut">—</span>'}</td><td class="l">${x.al?'<span class="pill">Alerta</span>':''}</td><td class="l"><b>${dl(x.f)}</b><span class="sm">${x.rf.f?'vs '+dl(x.rf.f)+(x.rf.exacta?'':'<span class="flag" data-t="La WK-1 ('+dl(x.rf.w1)+') todavía no tiene datos: se usa el último mismo día de la semana con datos.">sustituta</span>'):'sin WK-1'}</span></td>
      <td class="l"><b>${sl(x.s)}</b><span class="sm">–${sl(x.s+1)}</span></td><td class="l">${x.c}</td><td class="l"><b>${x.n}</b></td>
      <td><b>${nf(x.pd)}</b></td><td>${cell(x.np,0)}</td><td>${sgn(x.dp,true)}</td><td><b>${nf(x.rt)}</b></td>
      <td>${cell(x.rw,0,'',x.rw!=null&&x.rw<x.rt?'neg':'')}</td><td>${sgn(x.dif)}</td>
      <td>${x.l45==null?'<span class="mut">—</span>':`<span class="${x.l45>=.2?'neg':x.l45>=.1?'warn':''}">${nf(x.l45*100,1)} %</span>`}</td>
      <td>${cell(x.hd,1,'',x.hd>=6?'warn':'')}</td><td>${cell(x.tie,1,'',x.tie>=12?'neg':x.tie>=10?'warn':'')}</td></tr>`).join('')+
    (rows.length>4000?`<tr><td class="l mut" colspan="15">Se muestran 4.000 de ${nf(rows.length)} franjas: filtra por fecha, restaurante o coordinador.</td></tr>`:'')+
    (rows.length?'':'<tr><td class="l mut" colspan="15">Sin filas con estos filtros.</td></tr>')+'</tbody>';
  const sust=FECHAS.some(f=>REF[f].f&&!REF[f].exacta);
  $('sub').textContent='Proyección del '+dl(FECHAS[0])+' al '+dl(FECHAS[FECHAS.length-1])+' · histórico hasta el '+dl(A.hist[1])+' · generado '+A.generado+'.';
  $('note').textContent='Una fila por restaurante y franja de 30 min. Alerta = riders WK-1 por debajo de lo proyectado, más del 10 % de pedidos >45 min y, a la vez, aviso HD <6 min y Aceptado > En camino <12 min (el retraso no viene de HD ni de cocina, sino de falta de riders). WK-1 = mismo día de la semana anterior (fecha − 7 días); los pedidos y riders WK-1 se asignan a la franja por la hora de solicitud del pedido.'+(sust?' Las fechas cuya WK-1 aún no ha llegado se comparan con el último mismo día de la semana con datos (marcado «sustituta»); se actualizan solas al cargar cada día.':'')+' Colores: riders WK-1 en rojo si son menos que los teóricos · % >45 min naranja desde 10 % y rojo desde 20 % · aviso HD naranja desde 6 min · Aceptado > En camino naranja desde 10 min y rojo desde 12 min.';
}
const on=(id,k,ev='onchange')=>$(id)[ev]=e=>{S[k]=ev==='oninput'?e.target.value.trim().toLowerCase():e.target.value;if(k==='sem')fillFecha();render();};
on('q','q','oninput');on('cod','cod');on('rest','rest');on('coord','coord');on('sem','sem');on('fecha','fecha');$('solo').onchange=e=>{S.solo=e.target.checked;render();};on('fr','fr');
const mv=d=>{const fs=fechasSem();let i=fs.indexOf(S.fecha);i=S.fecha?i+d:(d>0?0:fs.length-1);if(i>=0&&i<fs.length){S.fecha=fs[i];$('fecha').value=S.fecha;render();}};
$('prev').onclick=()=>mv(-1);$('next').onclick=()=>mv(1);
$('reset').onclick=()=>{Object.assign(S,{q:'',cod:'',rest:'',coord:'',sem:'',fecha:'',fr:'',solo:false});$('solo').checked=false;['q','cod','rest','coord','sem','fr'].forEach(i=>$(i).value='');fillFecha();render();};
$('tab').addEventListener('click',e=>{const h=e.target.closest('th[data-k]');if(!h)return;const k=h.dataset.k;if(S.sort===k)S.asc=!S.asc;else{S.sort=k;S.asc=['f','s','c','n','o','ord'].includes(k);}render();});
const tip=$('tip');document.addEventListener('mouseover',e=>{const el=e.target.closest('[data-t]');if(el){tip.textContent=el.dataset.t;tip.hidden=false;}});
document.addEventListener('mousemove',e=>{if(!tip.hidden){tip.style.left=Math.min(e.clientX+12,innerWidth-360)+'px';tip.style.top=(e.clientY+14)+'px';}});
document.addEventListener('mouseout',e=>{const el=e.target.closest('[data-t]');if(el&&!el.contains(e.relatedTarget))tip.hidden=true;});
S.fecha=FECHAS[0]||'';fillFecha();render();
</script></body></html>"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("html", nargs="?", default=os.path.join(HERE, "..", "mushdrink", "index.html"))
    ap.add_argument("--csv")
    a = ap.parse_args()
    if a.csv:
        proy = store_merge(lee_csv(a.csv))
    elif os.path.exists(STORE):
        proy = store_merge([])
    else:
        print("mushdrink_proyeccion: sin proyección guardada, nada que hacer"); return
    h = open(a.html, encoding="utf-8").read()
    i0 = h.index("const DOCS=") + len("const DOCS=")
    docs, e0 = json.JSONDecoder().raw_decode(h[i0:])
    data = datos(docs, proy)
    doc = html_doc(data)
    k = next((i for i, d in enumerate(docs) if d.startswith(MARCA)), None)
    if k is None:
        docs.append(doc); k = len(docs) - 1
        j = h.index('<div class="tabs">'); j = h.index("</div>", j)
        h = h[:j] + f'<button class="tab" data-i="{k}">{TAB}</button>' + h[j:]
        i0 = h.index("const DOCS=") + len("const DOCS=")
    else:
        docs[k] = doc
    body = "[" + ",\n".join(json.dumps(x, ensure_ascii=False).replace("</", "<\\/") for x in docs) + "]"
    h = h[:i0] + body + h[i0 + e0:]
    open(a.html, "w", encoding="utf-8").write(h)
    nP = sum(len(v) for v in data["P"].values())
    print(f"mushdrink_proyeccion: pestaña {k} · {len(data['P'])} fechas ({min(data['P'])}..{max(data['P'])}) · {nP} filas · histórico {data['hist']}")


if __name__ == "__main__":
    main()
