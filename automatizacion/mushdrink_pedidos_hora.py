# -*- coding: utf-8 -*-
"""
Pestaña «Pedidos por restaurante» del panel MushDrink (mushdrink/index.html).

Gráfico de barras con los pedidos de un restaurante (o de todos) por hora, en un día concreto; en cada
barra, el nº de pedidos y entre paréntesis la media de las 4 semanas anteriores ese mismo día de la semana.

Datos: HTAVG de la pestaña «Operativa restaurantes» (docs[3]), que mushdrink_dia.py actualiza cada día:
por restaurante y día operativo (07:00–06:59), pedidos entregados por hora de solicitud del cliente.

Uso: python3 mushdrink_pedidos_hora.py [mushdrink/index.html]
     (mushdrink_dia.py lo llama al final de cada actualización)
"""
import os, re, sys, json

HERE = os.path.dirname(os.path.abspath(__file__))
MARCA = "<!-- PEDIDOS_HORA_RESTAURANTE -->"
TAB = "Pedidos por restaurante"


def getv(d, name):
    m = re.search(r'(?:const|let|var)\s+' + name + r'\s*=\s*', d)
    return json.JSONDecoder().raw_decode(d[m.end():])[0]


def datos(docs):
    ht = getv(docs[3], "HTAVG")
    D, fechas = {}, set()
    for c, dd in ht["H"].items():
        for f, flat in dd.items():
            pares = []
            for i in range(0, len(flat), 4):
                if flat[i + 1]:
                    pares += [int(flat[i]), int(flat[i + 1])]
            if pares:
                D.setdefault(f, {})[c] = pares
                fechas.add(f)
    nombres = {c: n for c, n in (ht.get("names") or {}).items() if any(c in D[f] for f in D)}
    return {"names": nombres, "dates": sorted(fechas), "D": D}


def html_doc(data):
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    return MARCA + r"""<!DOCTYPE html>
<html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Pedidos por restaurante · por hora</title>
<style>
:root{--bg:#F6F7F9;--card:#fff;--line:#E4E7EC;--ink:#14171F;--ink2:#4B5563;--mut:#6B7280;--bar:#0E5A6B;--avg:#E8833A;--chip:#EEF1F4}
*{box-sizing:border-box} body{margin:0;background:var(--bg);color:var(--ink);font-family:Inter,-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;font-size:14px}
.wrap{max-width:1400px;margin:0 auto;padding:18px 18px 40px;display:flex;flex-direction:column;gap:14px}
h1{font-size:19px;margin:0;font-weight:650} .sub{color:var(--ink2);font-size:12.5px;margin-top:4px}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px 16px}
.filters{display:flex;flex-wrap:wrap;gap:16px;align-items:flex-end;position:sticky;top:0;z-index:5}
.fg{display:flex;flex-direction:column;gap:5px} .fg>span{font-size:10.5px;letter-spacing:.07em;text-transform:uppercase;color:var(--mut);font-weight:600}
input,select{font:inherit;font-size:13px;border:1px solid var(--line);border-radius:8px;padding:7px 10px;background:#fff;color:var(--ink);height:36px}
#q{width:280px} #rest{width:340px} .nav button{height:36px;border:1px solid var(--line);background:#fff;border-radius:8px;padding:0 10px;cursor:pointer;font-size:13px}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:10px}
.kpi{background:#fff;border:1px solid var(--line);border-radius:12px;padding:11px 14px} .kpi b{display:block;font-size:22px;font-variant-numeric:tabular-nums}
.kpi span{font-size:12px;color:var(--ink2)} .up{color:#047857} .dn{color:#B42318}
.legend{display:flex;gap:16px;color:var(--ink2);font-size:12px;margin-bottom:6px;flex-wrap:wrap}
.legend i{display:inline-block;width:12px;height:12px;border-radius:3px;margin-right:6px;vertical-align:-2px}
svg{display:block;width:100%;height:auto} svg text{font-family:inherit}
.tip{position:fixed;pointer-events:none;background:#14171F;color:#fff;font-size:12px;line-height:1.5;padding:7px 10px;border-radius:7px;z-index:20;white-space:nowrap}
.tip[hidden]{display:none} .note{color:var(--mut);font-size:12px;line-height:1.55}
table{border-collapse:collapse;width:100%;font-size:12.5px} th,td{padding:6px 8px;border-top:1px solid #EEF0F3;text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
th{background:#F0F2F5;color:var(--mut);font-size:11px;text-transform:uppercase;letter-spacing:.03em} th:first-child,td:first-child{text-align:left}
</style></head><body>
<div class="wrap">
  <div><h1>Pedidos por restaurante · por hora</h1><div class="sub" id="sub"></div></div>
  <div class="card filters">
    <div class="fg"><span>Buscar restaurante</span><input id="q" type="search" placeholder="Nombre o código (p. ej. 25021)" autocomplete="off"></div>
    <div class="fg"><span>Restaurante</span><select id="rest"></select></div>
    <div class="fg"><span>Fecha</span><div class="nav" style="display:flex;gap:6px"><button id="prev" title="Día anterior">◀</button><input id="fecha" type="date"><button id="next" title="Día siguiente">▶</button></div></div>
  </div>
  <div class="kpis" id="kpis"></div>
  <div class="card">
    <div class="legend"><span><i style="background:var(--bar)"></i>Pedidos del día</span><span><i style="background:var(--avg);height:3px;vertical-align:3px"></i>Media de las 4 semanas anteriores, mismo día de la semana</span><span>Etiqueta: nº de pedidos (media 4 semanas)</span></div>
    <div id="chart"></div>
  </div>
  <div class="card" style="overflow:auto"><table id="tab"></table></div>
  <p class="note" id="note"></p>
</div>
<div class="tip" id="tip" hidden></div>
<script>
const P=""" + payload + r""";
const $=id=>document.getElementById(id);
const DOW=['domingo','lunes','martes','miércoles','jueves','viernes','sábado'];
const pd=s=>new Date(s+'T12:00:00');
const iso=d=>d.getFullYear()+'-'+String(d.getMonth()+1).padStart(2,'0')+'-'+String(d.getDate()).padStart(2,'0');
const ddmm=s=>s.slice(8,10)+'/'+s.slice(5,7);
const nf=(v,d=0)=>v==null||isNaN(v)?'—':v.toLocaleString('es-ES',{minimumFractionDigits:d,maximumFractionDigits:d});
const f1=v=>v==null?'—':(Math.abs(v-Math.round(v))<0.05?nf(v,0):nf(v,1));
const HORAS=[7,8,9,10,11,12,13,14,15,16,17,18,19,20,21,22,23,0,1,2,3,4,5,6];
const DATES=new Set(P.dates);
const codes=Object.keys(P.names).sort((a,b)=>P.names[a].localeCompare(P.names[b],'es'));
const S={c:'ALL',f:P.dates[P.dates.length-1]};
$('sub').textContent='Pedidos entregados por hora de solicitud del cliente (día operativo de 07:00 a 06:59) · datos del '+ddmm(P.dates[0])+'/'+P.dates[0].slice(0,4)+' al '+ddmm(P.dates[P.dates.length-1])+'/'+P.dates[P.dates.length-1].slice(0,4);
$('fecha').min=P.dates[0];$('fecha').max=P.dates[P.dates.length-1];
function opciones(){
  const q=$('q').value.trim().toLowerCase();
  const list=codes.filter(c=>!q||(c+' '+P.names[c]).toLowerCase().includes(q));
  const inc=S.c==='ALL'||list.includes(S.c);
  $('rest').innerHTML=(q?'':'<option value="ALL">Todos los restaurantes</option>')+list.map(c=>`<option value="${c}">${P.names[c]} · ${c}</option>`).join('')+(!list.length?'<option value="" disabled>Sin resultados</option>':'');
  if(!inc||(q&&S.c==='ALL')){ if(list.length) S.c=list[0]; }
  $('rest').value=S.c;
}
function porHora(f,c){
  const o=Object.fromEntries(HORAS.map(h=>[h,0]));const day=P.D[f]||{};
  const add=a=>{for(let i=0;i<a.length;i+=2)o[a[i]]+=a[i+1];};
  if(c==='ALL') Object.values(day).forEach(add); else if(day[c]) add(day[c]);
  return o;
}
function render(){
  const f=S.f,c=S.c;
  $('fecha').value=f;
  const cur=porHora(f,c);
  const prev=[1,2,3,4].map(k=>{const d=pd(f);d.setDate(d.getDate()-7*k);return iso(d);}).filter(d=>DATES.has(d));
  const avg=Object.fromEntries(HORAS.map(h=>[h,prev.length?prev.reduce((a,d)=>a+porHora(d,c)[h],0)/prev.length:null]));
  let hs=HORAS.filter(h=>cur[h]>0||(avg[h]||0)>=0.25);
  if(!hs.length) hs=HORAS.slice(4,17);
  const i0=HORAS.indexOf(hs[0]),i1=HORAS.indexOf(hs[hs.length-1]); hs=HORAS.slice(i0,i1+1);
  const tot=hs.reduce((a,h)=>a+cur[h],0), tavg=prev.length?HORAS.reduce((a,h)=>a+avg[h],0):null;
  let pk=hs[0];hs.forEach(h=>{if(cur[h]>cur[pk])pk=h;});
  const dlt=tavg?(tot/tavg-1)*100:null;
  const nm=c==='ALL'?'Todos los restaurantes':P.names[c]+' · '+c;
  $('kpis').innerHTML=[
    [nf(tot),'Pedidos · '+DOW[pd(f).getDay()]+' '+ddmm(f)],
    [f1(tavg),'Media 4 semanas ('+DOW[pd(f).getDay()]+')'],
    [dlt==null?'—':`<span class="${dlt>=0?'up':'dn'}">${dlt>=0?'+':'−'}${nf(Math.abs(dlt),1)} %</span>`,'Día vs media 4 semanas'],
    [tot?String(pk).padStart(2,'0')+':00':'—','Hora pico ('+nf(cur[pk])+' pedidos)']
  ].map(([b,s])=>`<div class="kpi"><b>${b}</b><span>${s}</span></div>`).join('');
  // gráfico
  const W=1200,H=380,L=40,R=12,T=34,B=34, n=hs.length, bw=(W-L-R)/n;
  const vmax=Math.max(1,...hs.map(h=>cur[h]),...hs.map(h=>avg[h]||0));
  const st=[1,2,5,10,20,25,50,100,200,500].find(s=>vmax/s<=6)||1000, ym=Math.ceil(vmax/st)*st;
  const Y=v=>T+(H-T-B)*(1-v/ym);
  let s=`<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Pedidos por hora">`;
  for(let v=0;v<=ym;v+=st) s+=`<line x1="${L}" x2="${W-R}" y1="${Y(v)}" y2="${Y(v)}" stroke="#EEF0F3"/><text x="${L-6}" y="${Y(v)+4}" text-anchor="end" font-size="11" fill="#6B7280">${v}</text>`;
  hs.forEach((h,i)=>{
    const x=L+i*bw, w=Math.max(4,bw*0.62), xb=x+(bw-w)/2, v=cur[h], a=avg[h];
    s+=`<g class="b" data-h="${h}"><rect x="${x}" y="${T}" width="${bw}" height="${H-T-B}" fill="transparent"/>`;
    if(v>0) s+=`<rect x="${xb}" y="${Y(v)}" width="${w}" height="${Y(0)-Y(v)}" rx="3" fill="#0E5A6B"/>`;
    if(a!=null) s+=`<line x1="${xb-3}" x2="${xb+w+3}" y1="${Y(a)}" y2="${Y(a)}" stroke="#E8833A" stroke-width="3" stroke-linecap="round"/>`;
    const ly=Math.min(Y(v),a!=null?Y(a):Y(v))-8;
    s+=`<text x="${x+bw/2}" y="${ly}" text-anchor="middle" font-size="${bw<46?10.5:12}" font-weight="650" fill="#14171F">${v}<tspan font-weight="400" fill="#6B7280"> (${a==null?'—':f1(a)})</tspan></text>`;
    s+=`<text x="${x+bw/2}" y="${H-12}" text-anchor="middle" font-size="11.5" fill="#4B5563">${String(h).padStart(2,'0')}h</text></g>`;
  });
  s+='</svg>';
  $('chart').innerHTML=s;
  const tip=$('tip');
  $('chart').querySelectorAll('g.b').forEach(g=>{
    g.addEventListener('mousemove',e=>{const h=+g.dataset.h;const a=avg[h];
      tip.innerHTML=`<b>${String(h).padStart(2,'0')}:00–${String((h+1)%24).padStart(2,'0')}:00</b><br>Pedidos ${DOW[pd(f).getDay()]} ${ddmm(f)}: <b>${cur[h]}</b><br>Media 4 semanas: <b>${a==null?'—':f1(a)}</b>`+(prev.length?'<br><span style="opacity:.75">'+prev.map(d=>ddmm(d)+': '+porHora(d,c)[h]).join(' · ')+'</span>':'');
      tip.hidden=false;tip.style.left=Math.min(e.clientX+12,innerWidth-260)+'px';tip.style.top=(e.clientY+14)+'px';});
    g.addEventListener('mouseleave',()=>tip.hidden=true);
  });
  // tabla
  $('tab').innerHTML='<tr><th>Hora</th>'+hs.map(h=>`<th>${String(h).padStart(2,'0')}h</th>`).join('')+'<th>Total</th></tr>'+
    `<tr><td><b>${DOW[pd(f).getDay()]} ${ddmm(f)}</b></td>`+hs.map(h=>`<td><b>${cur[h]}</b></td>`).join('')+`<td><b>${tot}</b></td></tr>`+
    prev.map(d=>{const o=porHora(d,c);return `<tr><td>${DOW[pd(d).getDay()]} ${ddmm(d)}</td>`+hs.map(h=>`<td>${o[h]}</td>`).join('')+`<td>${HORAS.reduce((a,h)=>a+o[h],0)}</td></tr>`;}).join('')+
    (prev.length?`<tr><td style="color:#E8833A"><b>Media 4 semanas</b></td>`+hs.map(h=>`<td style="color:#E8833A">${f1(avg[h])}</td>`).join('')+`<td style="color:#E8833A">${f1(tavg)}</td></tr>`:'');
  $('note').textContent=nm+'. La media usa los '+prev.length+' '+DOW[pd(f).getDay()]+(prev.length===1||/s$/.test(DOW[pd(f).getDay()])?'':'s')+' anteriores con datos ('+(prev.map(ddmm).join(', ')||'ninguno')+'); un día sin pedidos de ese restaurante cuenta como 0. Las horas de 00h a 06h pertenecen a la madrugada siguiente (día operativo de 07:00 a 06:59).';
}
$('q').addEventListener('input',()=>{opciones();render();});
$('rest').addEventListener('change',e=>{S.c=e.target.value;render();});
$('fecha').addEventListener('change',e=>{let v=e.target.value;if(!v)return;if(!DATES.has(v)){const ok=P.dates.filter(d=>d<=v);v=ok.length?ok[ok.length-1]:P.dates[0];}S.f=v;render();});
const step=k=>{const i=P.dates.indexOf(S.f)+k;if(i>=0&&i<P.dates.length){S.f=P.dates[i];render();}};
$('prev').onclick=()=>step(-1);$('next').onclick=()=>step(1);
opciones();render();
</script></body></html>"""


def main():
    p = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "..", "mushdrink", "index.html")
    h = open(p, encoding="utf-8").read()
    i0 = h.index("const DOCS=") + len("const DOCS=")
    docs, e0 = json.JSONDecoder().raw_decode(h[i0:])
    data = datos(docs)
    doc = html_doc(data)
    k = next((i for i, d in enumerate(docs) if d.startswith(MARCA)), None)
    if k is None:
        docs.append(doc); k = len(docs) - 1
        btn = f'<button class="tab" data-i="{k}">{TAB}</button>'
        j = h.index('<div class="tabs">'); j = h.index("</div>", j)
        h = h[:j] + btn + h[j:]
        i0 = h.index("const DOCS=") + len("const DOCS=")
    else:
        docs[k] = doc
    body = "[" + ",\n".join(json.dumps(x, ensure_ascii=False).replace("</", "<\\/") for x in docs) + "]"
    h = h[:i0] + body + h[i0 + e0:]
    open(p, "w", encoding="utf-8").write(h)
    print(f"mushdrink_pedidos_hora: pestaña {k} · {len(data['names'])} restaurantes · {len(data['dates'])} días "
          f"({data['dates'][0]}..{data['dates'][-1]})")


if __name__ == "__main__":
    main()
