#!/usr/bin/env python3
"""
MushDrink · columna «PIN» en «Operativa restaurantes» (docs[3]).

PIN = tiempo medio entre que se genera el PIN de recogida y el rider lo introduce para marcar el pedido En camino
(«T. Comprobación de recogida» del export de Torre de Control). Los datos por pedido ya se guardan en la pestaña
«Agrupación de pedidos» (variable PIN, con los riders de STK; ver mushdrink_stacking.pin_set). Este script:
  1. copia esos datos a «Operativa restaurantes» como variable PINR = {R: [riders], D: {fecha: {código: [rider, seg, …]}}};
  2. la primera vez, añade la columna, el total y la ventana emergente por rider (idempotente).
Se ejecuta en cada actualización diaria (mushdrink_dia.py) y se puede lanzar suelto:
    python3 automatizacion/mushdrink_pin_operativa.py [mushdrink/index.html]
"""
import json, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
J = lambda v: json.dumps(v, ensure_ascii=False, separators=(',', ':'))
MARCA = '/*__PIN_OPERATIVA__*/'

CSS = """
  td.pin{cursor:pointer;text-decoration:underline dotted;text-underline-offset:3px}
  td.pin:hover{color:var(--accent)}
  #pinOv .avhd-box{max-width:620px}
  #pinOv td.r{text-align:right;font-variant-numeric:tabular-nums}
"""

JS = MARCA + r"""
const PIN_MAX=3600;   // más de 60 min se considera error de registro y no entra en la media
function pinList(code,dates){ const out=[]; for(const d of dates){ const x=((PINR.D||{})[d]||{})[code]; if(x) for(let i=0;i<x.length;i+=2) out.push([x[i],x[i+1]]); } return out; }
function pinOk(list){ return list.filter(p=>p[1]!=null&&p[1]<=PIN_MAX); }
function pinMean(list){ const v=pinOk(list); return v.length?v.reduce((s,p)=>s+p[1],0)/v.length:null; }
function pinMed(arr){ if(!arr.length) return null; const v=arr.slice().sort((a,b)=>a-b); const m=v.length>>1; return v.length%2?v[m]:(v[m-1]+v[m])/2; }
function pinFmt(s){ if(s==null||!isFinite(s)) return '—'; s=Math.round(s); return Math.floor(s/60)+':'+String(s%60).padStart(2,'0'); }
function pinOpen(title,list){
  let ov=document.getElementById('pinOv');
  if(!ov){ov=document.createElement('div');ov.id='pinOv';ov.className='avhd-ov';
    ov.innerHTML='<div class="avhd-box"><div class="avhd-hd"><b id="pinT"></b><span id="pinS"></span><button id="pinX">Cerrar</button></div><div class="avhd-bd"><table><thead><tr><th class="l">Rider</th><th class="r">Pedidos</th><th class="r">PIN medio</th><th class="r">Mediana</th><th class="r">Máximo</th></tr></thead><tbody id="pinB"></tbody></table></div></div>';
    document.body.appendChild(ov);
    ov.addEventListener('click',e=>{if(e.target===ov||e.target.id==='pinX')ov.classList.remove('on');});
    document.addEventListener('keydown',e=>{if(e.key==='Escape')ov.classList.remove('on');});}
  const ok=pinOk(list), fuera=list.length-ok.length, by={};
  for(const [r,s] of ok){ (by[r]||(by[r]=[])).push(s); }
  const rows=Object.entries(by).map(([r,v])=>({r:(PINR.R||[])[r]||('#'+r),n:v.length,m:v.reduce((a,b)=>a+b,0)/v.length,md:pinMed(v),mx:Math.max(...v)})).sort((a,b)=>b.m-a.m);
  document.getElementById('pinT').textContent=title;
  document.getElementById('pinS').textContent=ok.length+' pedidos · '+rows.length+' riders · media '+pinFmt(pinMean(list))+' · mediana '+pinFmt(pinMed(ok.map(p=>p[1])))+(fuera?' · '+fuera+' fuera de la media (>60 min)':'');
  document.getElementById('pinB').innerHTML=rows.length?rows.map(x=>`<tr><td class="l">${x.r}</td><td class="r">${x.n}</td><td class="r"><b>${pinFmt(x.m)}</b></td><td class="r">${pinFmt(x.md)}</td><td class="r">${pinFmt(x.mx)}</td></tr>`).join(''):'<tr><td class="l muted" colspan="5">Sin datos de PIN para este filtro.</td></tr>';
  ov.classList.add('on');
}
"""

COL = ("  {k:'pin', l:'PIN', tip:'Tiempo medio, mm:ss, entre que se genera el PIN de recogida y el rider lo introduce para marcar el pedido "
       "En camino («T. Comprobación de recogida» de Torre de Control). Pulsa la cifra para ver el tiempo medio de cada rider. "
       "No cuentan registros de más de 60 min. Solo hay dato en los días cargados con el export de Torre de Control.', sort:'pin'},\n")

PARCHES = [
    # (ancla, texto a insertar, posición: 'antes' | 'despues')
    ("  {k:'rep',  l:'T. medio reparto'", COL, 'antes'),
    ("_av:avhdList([[String(a.code),a._d||[]]]), avhd:null,", " _pin:pinList(String(a.code),a._d||[]), pin:null,", 'despues'),
    ("r.acam=acamMean(r._av); }", " for(const r of out){ r.pin=pinMean(r._pin); }", 'despues'),
    ("${acamPct(r._av)}</td>`:`<td class=\"muted\">—</td>`)+",
     "\n      (r._pin&&r._pin.length?`<td class=\"pin${r.pin>60?' hi':''}\" data-c=\"${r.code}\" title=\"${pinOk(r._pin).length} pedidos · pulsa para ver cada rider\">${pinFmt(r.pin)}</td>`:`<td class=\"muted\">—</td>`)+", 'despues'),
    ("${acamPct(out.flatMap(r=>r._av))}</td>",
     "<td class=\"pin\" id=\"pinTot\">${pinFmt(pinMean(out.flatMap(r=>r._pin||[])))}</td>", 'despues'),
    ("  tb.querySelectorAll('td.avhd').forEach(",
     "  tb.querySelectorAll('td.pin').forEach(td=>td.onclick=()=>{const r=out.find(x=>String(x.code)===td.dataset.c); if(r) pinOpen(r.name+' · PIN de recogida',r._pin);});\n", 'antes'),
    ("  {const ft=document.getElementById('avhdTot');",
     "  {const fp=document.getElementById('pinTot'); if(fp) fp.onclick=()=>pinOpen('Todos los restaurantes del filtro · PIN de recogida',out.flatMap(r=>r._pin||[]));}\n", 'antes'),
]


def datos(docs):
    d = docs[15]
    def get(name):
        m = re.search(r'(?:const|let|var)\s+' + name + r'\s*=\s*', d)
        return json.JSONDecoder().raw_decode(d[m.end():])[0] if m else None
    stk, pin = get('STK') or {'riders': []}, get('PIN') or {'dates': [], 'D': {}}
    return {'R': stk['riders'], 'dates': pin['dates'], 'D': pin['D']}


def parchea(doc, pinr):
    if MARCA not in doc:
        for ancla, txt, pos in PARCHES:
            if doc.count(ancla) != 1:
                sys.exit(f'mushdrink_pin_operativa: ancla no encontrada o repetida: {ancla[:60]}')
            doc = doc.replace(ancla, (txt + ancla) if pos == 'antes' else (ancla + txt))
        doc = doc.replace('colspan="27" class="empty"', 'colspan="28" class="empty"')
        doc = doc.replace('</style>', CSS + '</style>', 1)
        i = doc.index('/*__AVHD__*/')
        doc = doc[:i] + 'const PINR = ' + J(pinr) + ';\n' + JS + '\n' + doc[i:]
        return doc, True
    m = re.search(r'const PINR\s*=\s*', doc)
    v, e = json.JSONDecoder().raw_decode(doc[m.end():])
    return doc[:m.end()] + J(pinr) + doc[m.end() + e:], False


def main():
    p = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, '..', 'mushdrink', 'index.html')
    h = open(p, encoding='utf-8').read()
    i0 = h.index('const DOCS=') + len('const DOCS=')
    docs, e0 = json.JSONDecoder().raw_decode(h[i0:])
    pinr = datos(docs)
    docs[3], nuevo = parchea(docs[3], pinr)
    body = "[" + ",\n".join(json.dumps(x, ensure_ascii=False).replace("</", "<\\/") for x in docs) + "]"
    open(p, 'w', encoding='utf-8').write(h[:i0] + body + h[i0 + e0:])
    n = sum(len(L) // 2 for d in pinr['D'].values() for L in d.values())
    print(f"mushdrink_pin_operativa: {'columna añadida · ' if nuevo else ''}{n} pedidos con PIN en {len(pinr['dates'])} días "
          f"({', '.join(x[8:10] + '/' + x[5:7] for x in pinr['dates'])})")


if __name__ == '__main__':
    main()
