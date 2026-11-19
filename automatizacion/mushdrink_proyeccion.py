# -*- coding: utf-8 -*-
"""
Pestaña «Proyección vs WK-1» del panel MushDrink (mushdrink/index.html).

Por restaurante y fecha proyectada:
  · Pedidos proyectados y riders teóricos del CSV «ProyeccionPedidos» (franjas de 30 min:
    ID = código del restaurante, Pedidos_Proyectados, Ratio_por_Cluster = riders teóricos de la franja).
    Día = todas las franjas de la fecha · cena = franjas de 20:00 a 22:30 (20:00–23:00).
    Riders teóricos = máximo de la franja 20:00–23:00 (y máximo del día como dato secundario).
  · Mismo día de la semana anterior (WK-1, fecha − 7 días), con los datos que ya tiene el panel:
    riders distintos que entregaron entre las 20:00 y las 23:00 («Nº pedidos/hora»), % de pedidos >45 min,
    aviso HD medio y Aceptado > En camino medio («Operativa restaurantes», AVHD).
    Si la WK-1 aún no tiene datos (fecha futura), la pestaña usa el último mismo día de la semana con datos
    y lo marca.

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


def datos(docs, proy):
    EC = getv(docs[9], "EC"); AV = getv(docs[3], "AVHD"); DS = getv(docs[3], "DS")
    # proyección: P[fecha][code] = [ped_dia, ped_cena, riders_pico_cena, riders_pico_dia]
    P = {}
    for r in proy:
        a = P.setdefault(r["Fecha"], {}).setdefault(r["ID"], [0, 0, 0, 0])
        cena = "20:00" <= r["Hora"] < "23:00"
        a[0] += r["Pedidos"]; a[3] = max(a[3], r["Riders"])
        if cena:
            a[1] += r["Pedidos"]; a[2] = max(a[2], r["Riders"])
    # histórico: M[fecha][code] = [riders 20-23, pedidos, >45, aviso HD medio min, acept>camino medio min]
    fechas = sorted(set(AV) | {f for v in EC["H"].values() for f in v})[-DIAS_HIST:]
    M = {}
    for f in fechas:
        out = {}
        for c, dd in EC["H"].items():
            hs = dd.get(f)
            if hs:
                rid = {x for h in hs if 20 <= h[0] <= 22 for x in h[6]}
                out.setdefault(c, [None] * 5)[0] = len(rid)
        for c, L in (AV.get(f) or {}).items():
            n = len(L)
            if not n:
                continue
            late = sum(1 for o in L if o[5] > 2700)
            sol = [o[3] for o in L if o[3] is not None and 0 <= o[3] < 7200]
            tie = [sum(o[4]) for o in L if o[4]]
            a = out.setdefault(c, [None] * 5)
            a[1], a[2] = n, late
            a[3] = round(sum(sol) / len(sol) / 60, 1) if sol else None
            a[4] = round(sum(tie) / len(tie) / 60, 1) if tie else None
        M[f] = out
    codes = set(c for v in P.values() for c in v)
    R = {}
    for r in DS["restaurants"]:
        c = str(r["code"])
        if c in codes:
            R[c] = {"n": r.get("name") or c, "o": r.get("owner") or ""}
    for c in codes:
        R.setdefault(c, {"n": (EC.get("names") or {}).get(c, c), "o": (EC.get("coord") or {}).get(c, "")})
    return {"P": P, "M": M, "R": R, "hist": [fechas[0], fechas[-1]] if fechas else None,
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
.flag{display:inline-block;font-size:10.5px;background:var(--ambbg);color:var(--amb);border-radius:99px;padding:1px 7px;margin-left:4px}
.note{color:var(--mut);font-size:12px;line-height:1.6;margin:0}
.tip{position:fixed;pointer-events:none;background:#14171F;color:#fff;font-size:12px;line-height:1.5;padding:7px 10px;border-radius:7px;z-index:20;max-width:340px}
.tip[hidden]{display:none} [data-t]{cursor:help}
</style></head><body>
<div class="wrap">
  <div><h1>Proyección de pedidos vs mismo día de la semana anterior (WK-1)</h1>
  <div class="sub">Pedidos y riders teóricos de la proyección, frente a lo que pasó el mismo día de la semana anterior: riders que entregaron de 20:00 a 23:00, % de pedidos &gt;45 min, aviso HD y Aceptado &gt; En camino. <span id="sub"></span></div></div>
  <div class="card filters">
    <div class="fg"><span>Buscador</span><input id="q" type="search" placeholder="Restaurante o código"></div>
    <div class="fg"><span>Código</span><select id="cod"></select></div>
    <div class="fg"><span>Restaurante</span><select id="rest"></select></div>
    <div class="fg"><span>Coordinador</span><select id="coord"></select></div>
    <div class="fg"><span>Semana</span><select id="sem"></select></div>
    <div class="fg"><span>Fecha</span><div class="nav"><button id="prev">◀</button><select id="fecha"></select><button id="next">▶</button></div></div>
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
const FECHAS=Object.keys(A.P).sort(), HIST=Object.keys(A.M).sort();
// WK-1: fecha − 7; si aún no hay datos, último mismo día de la semana con datos
function ref(f){const d=pd(f);d.setDate(d.getDate()-7);const w1=iso(d);if(A.M[w1])return {f:w1,exacta:true};
  for(let i=HIST.length-1;i>=0;i--){const h=HIST[i];if(h<w1&&pd(h).getDay()===pd(f).getDay())return {f:h,exacta:false,w1};}return {f:null,exacta:false,w1};}
const REF=Object.fromEntries(FECHAS.map(f=>[f,ref(f)]));
const filas=[];FECHAS.forEach(f=>{const r=REF[f];Object.entries(A.P[f]).forEach(([c,p])=>{const m=r.f&&A.M[r.f][c]||[null,null,null,null,null];const R=A.R[c]||{n:c,o:''};
  filas.push({f,w:wk(f),c,n:R.n,o:R.o||'',pd:p[0],pc:p[1],rt:p[2],rtd:p[3],rf:r,rw:m[0],np:m[1],l45:m[1]?m[2]/m[1]:null,hd:m[3],tie:m[4]});});});
const S={q:'',cod:'',rest:'',coord:'',sem:'',fecha:'',sort:'pd',asc:false};
const opt=(l,all)=>`<option value="">${all}</option>`+l.map(x=>`<option value="${x[0]}">${x[1]}</option>`).join('');
const uniq=(k,lab)=>[...new Map(filas.map(x=>[x[k],lab(x)])).entries()];
$('cod').innerHTML=opt(uniq('c',x=>x.c).sort((a,b)=>+a[0]-+b[0]),'Todos');
$('rest').innerHTML=opt(uniq('n',x=>x.n).sort((a,b)=>a[1].localeCompare(b[1])),'Todos');
$('coord').innerHTML=opt(uniq('o',x=>x.o||'(sin coordinador)').sort((a,b)=>a[1].localeCompare(b[1])),'Todos');
$('sem').innerHTML=opt([...new Set(FECHAS.map(wk))].map(w=>{const fs=FECHAS.filter(f=>wk(f)===w);return [w,w+' · '+dl(fs[0])+'–'+dl(fs[fs.length-1])];}),'Todas');
function fechasSem(){return FECHAS.filter(f=>!S.sem||wk(f)===S.sem);}
function fillFecha(){const fs=fechasSem();$('fecha').innerHTML=`<option value="">Todas (${fs.length})</option>`+fs.map(f=>`<option value="${f}">${dl(f)}/${f.slice(2,4)}</option>`).join('');if(S.fecha&&!fs.includes(S.fecha))S.fecha='';$('fecha').value=S.fecha;}
const cell=(v,d,suf,cls)=>v==null?'<span class="mut">—</span>':`<span class="${cls||''}">${nf(v,d)}${suf||''}</span>`;
function render(){
  const rows=filas.filter(x=>(!S.q||(x.c+' '+x.n).toLowerCase().includes(S.q))&&(!S.cod||x.c===S.cod)&&(!S.rest||x.n===S.rest)&&(!S.coord||x.o===S.coord)&&(!S.sem||x.w===S.sem)&&(!S.fecha||x.f===S.fecha));
  const val=x=>x[S.sort];
  rows.sort((a,b)=>{const va=val(a),vb=val(b);if(va==null&&vb==null)return 0;if(va==null)return 1;if(vb==null)return -1;return(va<vb?-1:va>vb?1:0)*(S.asc?1:-1);});
  const sum=k=>rows.reduce((a,x)=>a+(x[k]||0),0);
  const np=sum('np'),late=rows.reduce((a,x)=>a+(x.np&&x.l45!=null?x.l45*x.np:0),0);
  const falt=rows.filter(x=>x.rw!=null&&x.rw<x.rt).length;
  $('kpis').innerHTML=[[nf(rows.length),'Filas (restaurante × fecha)'],[nf(sum('pd')),'Pedidos proyectados'],[nf(sum('pc')),'Pedidos proyectados 20–23 h'],[nf(sum('rt')),'Riders teóricos (pico 20–23 h)'],[nf(sum('rw')),'Riders WK-1 20–23 h'],[`<span class="${falt?'neg':''}">${falt}</span>`,'Filas con menos riders en WK-1 que teóricos'],[np?nf(late/np*100,1)+' %':'—','% pedidos >45 min WK-1']].map(([b,s])=>`<div class="kpi"><b>${b}</b><span>${s}</span></div>`).join('');
  const th=(k,l,t,cl)=>`<th class="${cl||''}" data-k="${k}" ${t?`data-t="${t}"`:''}>${l}${S.sort===k?(S.asc?' ▲':' ▼'):''}</th>`;
  $('tab').innerHTML='<thead><tr>'+th('f','Fecha','Fecha proyectada · debajo, la fecha WK-1 con la que se compara.','l')+th('c','Código','','l')+th('n','Restaurante','','l')+th('o','Coordinador','','l')+
    th('pd','Pedidos<br>proyectados','Suma de todas las franjas de 30 min de la fecha (CSV de proyección).')+th('pc','Proyectados<br>20–23 h','Franjas de 20:00 a 22:30.')+
    th('rt','Riders<br>teóricos','Ratio_por_Cluster del CSV: máximo de las franjas de 20:00 a 23:00. Debajo, el máximo del día.')+
    th('rw','Riders WK-1<br>20–23 h','Riders distintos que entregaron pedidos entre las 20:00 y las 23:00 el mismo día de la semana anterior. En rojo si son menos que los teóricos.','g')+
    th('l45','% &gt;45 min<br>WK-1','Pedidos entregados con más de 45 min desde la solicitud del cliente, sobre el total del día WK-1.','g')+
    th('hd','Aviso HD<br>WK-1 (min)','Media desde que el cliente confirma el pedido hasta que llega a la API de HD, día WK-1.','g')+
    th('tie','Aceptado &gt; En camino<br>WK-1 (min)','Media de minutos entre que el rider acepta y marca En camino, día WK-1.','g')+'</tr></thead><tbody>'+
    rows.slice(0,3000).map(x=>`<tr><td class="l"><b>${dl(x.f)}</b><span class="sm">${x.rf.f?'vs '+dl(x.rf.f)+(x.rf.exacta?'':'<span class="flag" data-t="La WK-1 ('+dl(x.rf.w1)+') todavía no tiene datos: se usa el último mismo día de la semana con datos.">sustituta</span>'):'sin WK-1'}</span></td>
      <td class="l">${x.c}</td><td class="l"><b>${x.n}</b></td><td class="l">${x.o||'<span class="mut">—</span>'}</td>
      <td><b>${nf(x.pd)}</b></td><td>${nf(x.pc)}</td><td><b>${nf(x.rt)}</b><span class="sm">día ${nf(x.rtd)}</span></td>
      <td>${cell(x.rw,0,'',x.rw!=null&&x.rw<x.rt?'neg':'')}</td>
      <td>${x.l45==null?'<span class="mut">—</span>':`<span class="${x.l45>=.2?'neg':x.l45>=.1?'warn':''}">${nf(x.l45*100,1)} %</span><span class="sm">${x.np} ped.</span>`}</td>
      <td>${cell(x.hd,1,'',x.hd>=6?'warn':'')}</td><td>${cell(x.tie,1,'',x.tie>=12?'neg':x.tie>=10?'warn':'')}</td></tr>`).join('')+
    (rows.length?'':'<tr><td class="l mut" colspan="11">Sin filas con estos filtros.</td></tr>')+'</tbody>';
  const sust=FECHAS.some(f=>REF[f].f&&!REF[f].exacta);
  $('sub').textContent='Proyección del '+dl(FECHAS[0])+' al '+dl(FECHAS[FECHAS.length-1])+' · histórico hasta el '+dl(A.hist[1])+' · generado '+A.generado+'.';
  $('note').textContent='WK-1 = mismo día de la semana anterior (fecha − 7 días).'+(sust?' Las fechas cuya WK-1 aún no ha llegado se comparan con el último mismo día de la semana con datos (marcado «sustituta»); se actualizan solas al cargar cada día.':'')+' Colores: riders WK-1 en rojo si son menos que los teóricos · % >45 min naranja desde 10 % y rojo desde 20 % · aviso HD naranja desde 6 min · Aceptado > En camino naranja desde 10 min y rojo desde 12 min.';
}
const on=(id,k,ev='onchange')=>$(id)[ev]=e=>{S[k]=ev==='oninput'?e.target.value.trim().toLowerCase():e.target.value;if(k==='sem')fillFecha();render();};
on('q','q','oninput');on('cod','cod');on('rest','rest');on('coord','coord');on('sem','sem');on('fecha','fecha');
const mv=d=>{const fs=fechasSem();let i=fs.indexOf(S.fecha);i=S.fecha?i+d:(d>0?0:fs.length-1);if(i>=0&&i<fs.length){S.fecha=fs[i];$('fecha').value=S.fecha;render();}};
$('prev').onclick=()=>mv(-1);$('next').onclick=()=>mv(1);
$('reset').onclick=()=>{Object.assign(S,{q:'',cod:'',rest:'',coord:'',sem:'',fecha:''});['q','cod','rest','coord','sem'].forEach(i=>$(i).value='');fillFecha();render();};
$('tab').addEventListener('click',e=>{const h=e.target.closest('th[data-k]');if(!h)return;const k=h.dataset.k;if(S.sort===k)S.asc=!S.asc;else{S.sort=k;S.asc=['f','c','n','o'].includes(k);}render();});
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
