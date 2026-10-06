# -*- coding: utf-8 -*-
"""
================================================================================
 Pestaña "WTD% v1": riders parados justo después de entregar un pedido
================================================================================
 Usa el historial privado de posiciones (posiciones.py, muestra cada ~10 min con
 Live Operations). Una entrega se detecta cuando un pedido activo del rider
 desaparece entre dos muestras, el rider se queda sin pedido y sube su contador de
 entregas completadas. Desde ahí se mide cuánto sigue a menos de 80 m del mismo
 punto sin coger otro pedido.
   · Ahora: riders que siguen parados tras su última entrega.
   · Últimas 3 h: cada parada tras entrega detectada (episodios).
 El muestreo publica <dashboard>/wtd_vivo.json cada ~10 min y la pestaña lo relee
 sola cada 5 min. No se publican coordenadas, solo minutos.
 Lo usa generar_resumen_flota.py (igual que WTD%, UTR, No show...).
================================================================================
"""
import json

NODE_ALIASES = {"NEM": "MAD"}


def construir_html(cities=None, semanas=None, sello=True):
    import posiciones
    cities = sorted(set(NODE_ALIASES.get(c, c) for c in (cities or [])))
    nombres, aviso, foto = {}, "", None
    ahora_te, eps = {}, []
    try:
        import en_vivo
        snap = en_vivo._foto(cities)
        if not snap.get("stale"):
            posiciones.registrar(snap, en_vivo._POS)
        for code, C in (snap.get("cities") or {}).items():
            for r in C.get("riders") or []:
                nombres[str(r.get("employee_id"))] = [r.get("name") or "", code]
    except Exception as e:
        aviso = "No se pudo leer Live Operations: " + str(e)[:200]
    try:
        grid = posiciones.restaurantes(cities)
        _, foto = posiciones.quietos(cities, grid)
        ahora_te, eps = posiciones.tras_entrega(cities, grid)
    except Exception as e:
        aviso = (aviso + " · " if aviso else "") + "No se pudo calcular la parada tras entrega: " + str(e)[:200]
    if not foto and not aviso:
        aviso = "Sin posiciones recientes de Live Operations: la pestaña se rellenará con el muestreo de cada ~10 min."
    data = {"cities": cities, "foto": foto, "aviso": aviso, "umbral": posiciones.TRAS_UMBRAL_MIN,
            "horas": posiciones.KEEP_HOURS, "tras_entrega": ahora_te, "episodios": eps,
            "riders": {k: v for k, v in nombres.items() if v[1] in cities}}
    html = HTML.replace("__DATA__", json.dumps(data, ensure_ascii=False, separators=(",", ":")))
    n_ahora = sum(1 for e in ahora_te.values() if e["min"] >= posiciones.TRAS_UMBRAL_MIN and not e["local"])
    return html, "%d parados tras entrega ahora · %d episodios en %d h%s" % (
        n_ahora, len(eps), posiciones.KEEP_HOURS, (" · " + aviso) if aviso else "")


_BTN = '<button data-v="wtdv1" aria-pressed="false">WTD% v1</button>'


def integrar_en_dashboard(dash_html, v1_html):
    """Añade la pestaña 'WTD% v1' al selector Vista (en un iframe aislado), detrás de WTD%."""
    if 'id="viewWtdV1"' in dash_html:
        return dash_html
    ancla = None
    for a in ['<button data-v="wtdpct" aria-pressed="false">WTD%</button>',
              '<button data-v="cpostal" aria-pressed="false">Códigos postales</button>',
              '<button data-v="envivo" aria-pressed="false">En vivo</button>',
              '<button data-v="utr" aria-pressed="false">UTR</button>']:
        if a in dash_html:
            ancla = a
            break
    sec_ancla = '<div id="viewSemanal">'
    if not ancla or sec_ancla not in dash_html or "</body>" not in dash_html:
        raise ValueError("la plantilla no tiene el selector de Vista esperado")
    dash_html = dash_html.replace(ancla, ancla + "\n        " + _BTN, 1)
    dash_html = dash_html.replace(sec_ancla,
        '<section id="viewWtdV1" style="display:none"><iframe id="wtdV1Frame" title="WTD% v1" '
        'style="width:100%;height:1200px;border:0;display:block;background:transparent"></iframe></section>\n  '
        + sec_ancla, 1)
    src = json.dumps(v1_html, ensure_ascii=False).replace("<", "\\u003c")
    js = ("<script>\n/* ==== Pestaña WTD% v1 ==== */\n(function(){\n"
          "  const V1_HTML=" + src + ";\n"
          "  const seg=document.getElementById('viewSeg'),sec=document.getElementById('viewWtdV1'),fr=document.getElementById('wtdV1Frame');\n"
          "  if(!seg||!sec||!fr) return; let loaded=false;\n"
          "  seg.querySelectorAll('button').forEach(b=>b.addEventListener('click',()=>{\n"
          "    const on=b.dataset.v==='wtdv1'; sec.style.display=on?'':'none';\n"
          "    if(on){ seg.querySelectorAll('button').forEach(x=>x.setAttribute('aria-pressed',String(x===b)));\n"
          "      document.querySelectorAll('[id^=\"view\"]').forEach(e=>{ if(e!==sec && e!==seg && e.id!=='viewSeg') e.style.display='none'; });\n"
          "      if(!loaded){ fr.srcdoc=V1_HTML; loaded=true; } window.scrollTo(0,0); }\n"
          "  }));\n"
          "  window.addEventListener('message',e=>{ if(e.source===fr.contentWindow && e.data && e.data.v1H){\n"
          "    fr.style.height=Math.max(600,Math.ceil(e.data.v1H)+20)+'px'; } });\n"
          "})();\n</script>\n")
    i = dash_html.rindex("</body>")
    return dash_html[:i] + js + dash_html[i:]


HTML = r'''<!DOCTYPE html><html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>WTD% v1 · parados tras entregar</title>
<style>
:root{--bg:#F6F7F9;--surface:#FFFFFF;--line:#E4E7EC;--ink:#14171F;--ink2:#4B5563;--muted:#6B7280;--acc:#0E5A6B;--chip:#EEF1F4;--bad:#C2362F;--badbg:#FDECEA;--warn:#8A5A00;--warnbg:#FFF4DB;--good:#0A7A3E}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font-family:"Inter",-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;font-size:14px;padding:0 0 24px}
.wrap{display:flex;flex-direction:column;gap:16px}
h1{font-size:18px;font-weight:650;margin:0}
h2{font-size:12px;letter-spacing:.06em;text-transform:uppercase;font-weight:650;margin:0}
.sub{color:var(--ink2);margin:5px 0 0;line-height:1.5;font-size:13px}
.banner{border-radius:8px;padding:9px 12px;font-size:13px;background:#FFF7E6;border:1px solid #F5D9A8;color:#7A5200}
.banner[hidden]{display:none}
.filters{background:var(--surface);border:1px solid var(--line);border-radius:12px;padding:14px 16px;display:flex;flex-wrap:wrap;gap:16px;align-items:flex-end}
.fg{display:flex;flex-direction:column;gap:6px}
.fg>span{font-family:ui-monospace,"SF Mono",Menlo,monospace;font-size:11px;letter-spacing:.07em;text-transform:uppercase;color:var(--muted)}
.seg{display:inline-flex;flex-wrap:wrap;background:var(--bg);border:1px solid var(--line);border-radius:9px;padding:3px;gap:2px}
.seg button{font:inherit;font-size:13px;border:0;background:transparent;color:var(--ink2);border-radius:7px;padding:6px 11px;cursor:pointer}
.seg button:hover{color:var(--ink)}.seg button.on{background:var(--acc);color:#fff}
.seg button .c{font-family:ui-monospace,monospace;font-size:11px;opacity:.75;margin-left:5px}
input[type=search]{font:inherit;font-size:13px;padding:7px 11px;border:1px solid var(--line);border-radius:8px;width:220px;max-width:100%;background:var(--surface);color:var(--ink)}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:10px}
.kpi{background:var(--surface);border:1px solid var(--line);border-radius:12px;padding:12px 14px;display:flex;flex-direction:column;gap:4px}
.kpi b{font-size:22px;font-weight:650;font-family:ui-monospace,"SF Mono",Menlo,monospace;font-variant-numeric:tabular-nums}
.kpi span{font-size:12px;color:var(--ink2)}
.kpi b span{font-size:inherit;color:inherit}
.kpi em{font-style:normal;font-family:ui-monospace,"SF Mono",Menlo,monospace;font-size:11px;letter-spacing:.06em;text-transform:uppercase;color:var(--muted)}
.panel{background:var(--surface);border:1px solid var(--line);border-radius:12px;padding:14px;display:flex;flex-direction:column;gap:10px;min-width:0}
.ph{display:flex;justify-content:space-between;gap:10px;flex-wrap:wrap;align-items:baseline}.ph p{margin:0;color:var(--ink2);font-size:12.5px}
.tw{overflow-x:auto}
table{border-collapse:collapse;width:100%}
th,td{padding:7px 10px;text-align:left;border-bottom:1px solid var(--line);white-space:nowrap;font-size:13px}
th{font-family:ui-monospace,"SF Mono",Menlo,monospace;font-size:10.5px;letter-spacing:.05em;text-transform:uppercase;color:var(--muted);font-weight:500;cursor:pointer;position:sticky;top:0;background:var(--surface)}
th .arw{margin-left:4px}
td.n,th.n{text-align:right;font-family:ui-monospace,"SF Mono",Menlo,monospace;font-variant-numeric:tabular-nums}
tbody tr:hover td{background:var(--chip)}
.nm{color:var(--muted);font-size:12px;margin-left:6px}
.pill{display:inline-block;padding:2px 9px;border-radius:99px;font-size:12px;background:var(--chip);color:var(--ink2);margin-right:4px}
.pill.alert{background:var(--badbg);color:var(--bad);font-weight:600}
.pill.mid{background:var(--warnbg);color:var(--warn)}
.muted{color:var(--muted)}
.empty{color:var(--muted);padding:16px 0}
.note{color:var(--muted);font-size:12px;line-height:1.55;margin:0}
[data-def]{cursor:help}
th[data-def],.kpi em[data-def],h2[data-def]{text-decoration:underline dotted;text-underline-offset:3px}
#defTip{position:fixed;z-index:50;max-width:320px;background:#14171F;color:#fff;font-size:12px;line-height:1.45;padding:8px 10px;border-radius:7px;pointer-events:none;box-shadow:0 4px 14px rgba(0,0,0,.18);text-transform:none;letter-spacing:0;font-weight:400}
#defTip[hidden]{display:none}
</style></head><body>
<div class="wrap">
  <header><h1>WTD% v1 · riders parados justo después de entregar</h1><p class="sub" id="sub"></p></header>
  <div class="banner" id="banner" hidden></div>
  <div class="filters">
    <div class="fg"><span>Área</span><div class="seg" id="fCity"></div></div>
    <div class="fg"><span>Mostrar</span><div class="seg" id="fMin"></div></div>
    <div class="fg"><span>Restaurante</span><div class="seg" id="fLoc"></div></div>
    <div class="fg"><span>Buscar</span><input type="search" id="fQ" placeholder="ID o nombre de rider" aria-label="Buscar rider"></div>
  </div>
  <section class="kpis" id="kpis"></section>
  <section class="panel"><div class="ph"><h2 data-def="Riders que en la última muestra siguen sin moverse (menos de 80 m) y sin pedido desde que entregaron su último pedido.">Ahora · parados tras su última entrega</h2><p id="cntA"></p></div>
    <div class="tw" style="max-height:520px"><table id="tA"></table></div></section>
  <section class="panel"><div class="ph"><h2 id="hE" data-def="Cada vez que un rider entregó un pedido y se quedó parado al menos una muestra (~10 min) en el mismo punto sin coger otro pedido.">Paradas tras entrega</h2><p id="cntE"></p></div>
    <div class="tw" style="max-height:700px"><table id="tE"></table></div></section>
  <p class="note" id="nota"></p>
</div>
<script>
const D=__DATA__;
const $=id=>document.getElementById(id);
const esc=s=>String(s??'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const nf=(v,d=0)=>v==null||isNaN(v)?'—':Number(v).toLocaleString('es-ES',{minimumFractionDigits:d,maximumFractionDigits:d});
const hhmm=s=>{if(!s)return '—';const d=new Date(s);return isNaN(d)?'—':d.toLocaleTimeString('es-ES',{timeZone:'Europe/Madrid',hour:'2-digit',minute:'2-digit'});};
const U=D.umbral;
const ST={working:'Trabajando',ready:'Listo',available:'Disponible',late:'Con retraso',break:'En pausa',starting:'Empezando',ending:'Terminando',temp_not_working:'Parado temporalmente',not_working:'No trabajando'};
const S={city:'ALL',min:'U',loc:'SIN',q:'',sa:{k:'min',d:-1},se:{k:'desde',d:-1}};
function cabecera(){
  $('sub').textContent='Una entrega se detecta cuando el pedido activo desaparece entre dos muestras de Live Operations y sube el contador de entregas completadas; desde ahí se mide cuánto sigue el rider en el mismo punto sin otro pedido.'+(D.foto?' Última muestra a las '+hhmm(D.foto)+' (hora de Madrid) · se actualiza cada ~10 min.':'');
  $('banner').hidden=!D.aviso;$('banner').textContent=D.aviso||'';
  $('hE').textContent='Paradas tras entrega · últimas '+D.horas+' h';}
cabecera();
function aplicarVivo(j){
  if(!j||!j.foto||!j.episodios)return;
  if(D.foto&&j.foto<D.foto)return;
  D.foto=j.foto;D.aviso='';D.tras_entrega=j.tras_entrega||{};D.episodios=j.episodios||[];
  Object.assign(D.riders,j.riders||{});cabecera();render();}
function cargarVivo(){try{fetch(new URL('wtd_vivo.json?t='+Date.now(),document.baseURI),{cache:'no-store'}).then(r=>r.ok?r.json():null).then(aplicarVivo).catch(()=>{});}catch(e){}}
$('nota').innerHTML='Cómo se calcula: se toma una muestra de posición y pedidos de cada rider cada ~10 min. Si entre dos muestras desaparece su pedido activo, se queda sin pedido y sube su contador de entregas completadas, cuenta como <b>entrega</b> (si desaparece sin sumar entrega, es cancelación o reasignación y no se cuenta). '+
 '«Parado» = sigue a menos de 80 m del punto donde estaba tras entregar y sin coger otro pedido. Los minutos son un <b>mínimo</b> (≥): la entrega ocurrió entre las dos muestras, así que la parada real puede ser hasta ~10 min mayor. '+
 '«En restaurante» = se ha quedado a menos de 100 m de un local donde se recogen pedidos (esperando el siguiente). «GPS congelado» = su ubicación no se actualiza, puede no estar parado de verdad. Historial de las últimas '+D.horas+' h; no se publican coordenadas.';
function seg(id,opts,val,on){const el=$(id);el.innerHTML=opts.map(o=>`<button data-v="${o.v}" class="${String(o.v)===String(val)?'on':''}">${o.l}${o.c!=null?`<span class="c">${o.c}</span>`:''}</button>`).join('');el.onclick=e=>{const b=e.target.closest('button');if(b)on(b.dataset.v);};}
const nombre=id=>(D.riders[id]||[])[0]||'';
const minPill=e=>{const cls=e.min>=U*2?'alert':(e.min>=U?'mid':'');return `<span class="pill ${cls}" title="Entre ${e.min} y ${e.max} min">≥ ${e.min} min</span>`;};
const flags=e=>(e.local?'<span class="pill" title="A menos de 100 m de un restaurante conocido">En restaurante</span>':'')+
  (e.gps_viejo?`<span class="pill mid" title="La ubicación no se actualiza desde hace ${e.gps_viejo} min">GPS congelado ${e.gps_viejo} min</span>`:'')+
  (e.confirmada===null?'<span class="pill" title="Glovo no informó el contador de entregas: podría ser una cancelación">Sin confirmar</span>':'');
const base=()=>D.episodios.filter(e=>(S.city==='ALL'||e.city===S.city)&&(S.loc==='ALL'||!e.local)&&
  (!S.q||String(e.rid).includes(S.q)||nombre(e.rid).toLowerCase().includes(S.q)));
const CA=[
 {k:'rid',h:'Rider',v:e=>Number(e.rid)||e.rid,f:e=>esc(e.rid)+(nombre(e.rid)?`<span class="nm">${esc(nombre(e.rid))}</span>`:''),d:'ID del rider en Glovo y nombre.'},
 {k:'city',h:'Área',v:e=>e.city,f:e=>esc(e.city),d:'Área (nodo) del rider.'},
 {k:'ent',h:'Entregó entre',v:e=>e.ent_fin,f:e=>hhmm(e.ent_ini)+' – '+hhmm(e.ent_fin),d:'Muestras entre las que desapareció el pedido entregado (hora de Madrid).'},
 {k:'min',h:'Parado',n:1,v:e=>e.min,f:minPill,d:'Minutos mínimos sin moverse y sin pedido desde la entrega. Al pasar el ratón: rango mínimo–máximo.'},
 {k:'status',h:'Estado Glovo',v:e=>e.status||'',f:e=>esc(ST[e.status]||e.status||'—'),d:'Estado del rider en Live Operations en la última muestra parado.'},
 {k:'fl',h:'Avisos',v:e=>(e.local?1:0)+(e.gps_viejo?2:0),f:flags,d:'En restaurante, GPS congelado o entrega sin confirmar.'},
];
const CE=[CA[0],CA[1],CA[2],
 {k:'desde',h:'Parado desde',v:e=>e.desde,f:e=>hhmm(e.desde),d:'Primera muestra tras la entrega, ya sin pedido.'},
 {k:'hasta',h:'Hasta',v:e=>e.hasta,f:e=>e.en_curso?'<span class="pill alert">Sigue parado</span>':hhmm(e.hasta),d:'Última muestra en el mismo punto sin pedido. «Sigue parado» si es la muestra más reciente.'},
 CA[3],CA[4],CA[5]];
function tabla(id,cols,rows,st,empty){
  const col=cols.find(x=>x.k===st.k)||cols[0];
  const s=rows.slice().sort((a,b)=>{const x=col.v(a),y=col.v(b);if(x==null||x==='')return 1;if(y==null||y==='')return -1;return (typeof x==='string'?x.localeCompare(y,'es'):x-y)*st.d;});
  $(id).innerHTML=!s.length?`<tbody><tr><td class="empty">${empty}</td></tr></tbody>`:
   '<thead><tr>'+cols.map(x=>`<th class="${x.n?'n':''}" data-k="${x.k}" data-def="${esc(x.d)}">${x.h}${st.k===x.k?`<span class="arw">${st.d<0?'▼':'▲'}</span>`:''}</th>`).join('')+'</tr></thead><tbody>'+
   s.map(r=>'<tr>'+cols.map(x=>`<td class="${x.n?'n':''}">${x.f(r)}</td>`).join('')+'</tr>').join('')+'</tbody>';
  $(id).querySelectorAll('th[data-k]').forEach(th=>th.onclick=()=>{const k=th.dataset.k;if(st.k===k)st.d*=-1;else{st.k=k;st.d=cols.find(x=>x.k===k).n?-1:1;}render();});
  return s.length;}
function render(){
  const all=D.episodios.filter(e=>S.city==='ALL'||e.city===S.city);
  seg('fCity',[{v:'ALL',l:'Todas'}].concat(D.cities.map(c=>({v:c,l:c,c:D.episodios.filter(e=>e.city===c&&e.min>=U&&!e.local).length}))),S.city,v=>{S.city=v;render();});
  seg('fMin',[{v:'U',l:'Parados ≥'+U+' min'},{v:'ALL',l:'Todas las paradas'}],S.min,v=>{S.min=v;render();});
  seg('fLoc',[{v:'SIN',l:'Excluir en restaurante'},{v:'ALL',l:'Incluir'}],S.loc,v=>{S.loc=v;render();});
  const B=base().filter(e=>S.min==='ALL'||e.min>=U);
  const now=B.filter(e=>e.en_curso);
  const nA=tabla('tA',CA,now,S.sa,'Ningún rider parado tras su última entrega con estos filtros.');
  const nE=tabla('tE',CE,B,S.se,'Ninguna parada tras entrega con estos filtros en las últimas '+D.horas+' h.');
  $('cntA').textContent=nf(nA)+' riders';$('cntE').textContent=nf(nE)+' paradas';
  const real=all.filter(e=>!e.local&&!e.gps_viejo);
  const sobre=real.filter(e=>e.min>=U);
  const rid=new Set(sobre.map(e=>e.rid)),rep={};sobre.forEach(e=>rep[e.rid]=(rep[e.rid]||0)+1);
  const media=sobre.length?sobre.reduce((a,e)=>a+e.min,0)/sobre.length:null;
  const ahora=real.filter(e=>e.en_curso&&e.min>=U).length;
  $('kpis').innerHTML=[
   ['Parados ahora tras entrega',`<span style="color:${ahora?'var(--bad)':'inherit'}">${nf(ahora)}</span>`,D.foto?'≥'+U+' min · a las '+hhmm(D.foto):'sin posiciones','Riders que en la última muestra llevan al menos '+U+' min sin moverse y sin pedido desde su última entrega (sin contar en restaurante ni GPS congelado).'],
   ['Paradas ≥'+U+' min · '+D.horas+' h',nf(sobre.length),nf(rid.size)+' riders','Paradas tras entrega de al menos '+U+' min en las últimas '+D.horas+' h (sin contar en restaurante ni GPS congelado).'],
   ['Minutos medios parado',media==null?'—':nf(media,0)+' min','mínimo por parada ≥'+U+' min','Media de los minutos mínimos parado en las paradas tras entrega de al menos '+U+' min.'],
   ['Riders reincidentes',nf(Object.values(rep).filter(x=>x>=2).length),'2 o más paradas ≥'+U+' min','Riders con al menos dos paradas tras entrega de '+U+' min o más en las últimas '+D.horas+' h.'],
  ].map(([e,b,s,d])=>`<div class="kpi"><em data-def="${esc(d)}" tabindex="0">${e}</em><b>${b}</b><span>${s}</span></div>`).join('');
}
let qT;$('fQ').addEventListener('input',e=>{clearTimeout(qT);qT=setTimeout(()=>{S.q=e.target.value.trim().toLowerCase();render();},150);});
(function(){const tip=document.createElement('div');tip.id='defTip';tip.hidden=true;document.body.appendChild(tip);
  const place=(x,y)=>{const w=tip.offsetWidth,h=tip.offsetHeight;let l=x+12,t=y+14;if(l+w>innerWidth-8)l=Math.max(8,x-w-12);if(t+h>innerHeight-8)t=Math.max(8,y-h-12);tip.style.left=l+'px';tip.style.top=t+'px';};
  document.addEventListener('mouseover',e=>{const el=e.target.closest('[data-def]');if(el){tip.textContent=el.dataset.def;tip.hidden=false;place(e.clientX,e.clientY);}});
  document.addEventListener('mousemove',e=>{if(!tip.hidden&&e.target.closest('[data-def]'))place(e.clientX,e.clientY);});
  document.addEventListener('mouseout',e=>{const el=e.target.closest('[data-def]');if(el&&!el.contains(e.relatedTarget))tip.hidden=true;});})();
render();
cargarVivo();setInterval(cargarVivo,5*60*1000);
if(window.parent!==window){const send=()=>window.parent.postMessage({v1H:document.body.getBoundingClientRect().height},'*');
  if(window.ResizeObserver) new ResizeObserver(send).observe(document.body); send();}
</script></body></html>
'''
