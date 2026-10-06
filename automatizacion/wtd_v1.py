# -*- coding: utf-8 -*-
"""
================================================================================
 Pestaña "WTD% v1": riders parados justo después de entregar un pedido
================================================================================
 Usa el historial privado de posiciones (posiciones.py, muestra cada ~5 min con
 Live Operations, 24 h). Una entrega se detecta cuando un pedido activo del rider
 desaparece entre dos muestras, el rider se queda sin pedido y sube su contador de
 entregas completadas. Desde ahí se mide cuánto sigue a menos de 80 m del mismo
 punto sin coger otro pedido.
   · Ahora: riders que siguen parados tras su última entrega.
   · Hoy: cada parada tras entrega del día operativo (desde las 05:00).
   · Histórico: todas las paradas acumuladas, con filtro de semana y fecha.
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
.live{font-family:ui-monospace,"SF Mono",Menlo,monospace;font-variant-numeric:tabular-nums;font-weight:600}
.live .dot{display:inline-block;width:7px;height:7px;border-radius:50%;background:var(--bad);margin-right:6px;vertical-align:middle;animation:blink 1.2s infinite}
@keyframes blink{50%{opacity:.25}}
.sub2{display:block;color:var(--muted);font-size:11px;font-weight:400;margin-top:2px}
.muted{color:var(--muted)}
.empty{color:var(--muted);padding:16px 0}
.note{color:var(--muted);font-size:12px;line-height:1.55;margin:0}
[data-def]{cursor:help}
th[data-def],.kpi em[data-def],h2[data-def]{text-decoration:underline dotted;text-underline-offset:3px}
#defTip{position:fixed;z-index:50;max-width:320px;background:#14171F;color:#fff;font-size:12px;line-height:1.45;padding:8px 10px;border-radius:7px;pointer-events:none;box-shadow:0 4px 14px rgba(0,0,0,.18);text-transform:none;letter-spacing:0;font-weight:400}
#defTip[hidden]{display:none}
select{font:inherit;font-size:13px;padding:7px 10px;border:1px solid var(--line);border-radius:8px;background:var(--surface);color:var(--ink)}
.hhead{display:flex;justify-content:space-between;align-items:flex-end;gap:12px;flex-wrap:wrap}
.hfil{display:flex;gap:14px;flex-wrap:wrap;align-items:flex-end}
.bars{display:flex;align-items:flex-end;gap:6px;height:170px;padding:18px 2px 0;overflow-x:auto}
.bar{flex:1 0 34px;max-width:70px;display:flex;flex-direction:column;align-items:center;justify-content:flex-end;height:100%;gap:4px;cursor:pointer}
.bar i{display:block;width:100%;background:var(--acc);border-radius:4px 4px 0 0;min-height:2px}
.bar.sel i{background:var(--bad)}
.bar b{font-size:11px;font-family:ui-monospace,monospace;font-weight:600;color:var(--ink)}
.bar span{font-size:10.5px;color:var(--muted);white-space:nowrap}
.bar:hover i{opacity:.8}
tr.click{cursor:pointer}
.two{display:grid;grid-template-columns:1fr;gap:16px}
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
  <section class="panel"><div class="ph"><h2 id="hE" data-def="Cada vez que hoy (día operativo desde las 05:00) un rider entregó un pedido y se quedó parado al menos una muestra (~5 min) en el mismo punto sin coger otro pedido.">Paradas tras entrega</h2><p id="cntE"></p></div>
    <div class="tw" style="max-height:700px"><table id="tE"></table></div></section>
  <section class="panel" id="hist">
    <div class="hhead"><div><h2 data-def="Todas las paradas tras entrega detectadas desde que empezó a guardarse el histórico (se acumulan cada ~10 min). Usa los filtros de Área, Mostrar, Restaurante y Buscar de arriba.">Histórico · recurrencia</h2><p class="sub" id="hSub" style="margin-top:4px"></p></div>
      <div class="hfil">
        <div class="fg"><span>Semana</span><select id="hWk" aria-label="Semana"></select></div>
        <div class="fg"><span>Fecha</span><select id="hDay" aria-label="Fecha"></select></div>
      </div></div>
    <section class="kpis" id="hKpis"></section>
    <div><h2 id="hBarsT" data-def="Paradas en el periodo filtrado. Pulsa una barra para filtrar por ese día o semana.">Paradas por día</h2><div class="bars" id="hBars"></div></div>
    <div class="ph"><h2 data-def="Una fila por rider en el periodo filtrado. Pulsa un rider para ver solo sus paradas.">Recurrencia por rider</h2><p id="hCntR"></p></div>
    <div class="tw" style="max-height:520px"><table id="hR"></table></div>
    <div class="ph"><h2 data-def="Detalle de cada parada del periodo filtrado (las 500 más recientes).">Detalle de paradas</h2><p id="hCntE"></p></div>
    <div class="tw" style="max-height:520px"><table id="hDet"></table></div>
  </section>
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
  $('sub').textContent='Una entrega se detecta cuando el pedido activo desaparece entre dos muestras de Live Operations y sube el contador de entregas completadas; desde ahí se mide cuánto sigue el rider en el mismo punto sin otro pedido.'+(D.foto?' Última muestra a las '+hhmm(D.foto)+' (hora de Madrid) · fotos cada ~5 min, se publica cada ~10 min.':'');
  $('banner').hidden=!D.aviso;$('banner').textContent=D.aviso||'';
  $('hE').textContent='Paradas tras entrega · hoy desde las 05:00';}
cabecera();
function aplicarVivo(j){
  if(!j||!j.foto||!j.episodios)return;
  if(D.foto&&j.foto<D.foto)return;
  D.foto=j.foto;D.aviso='';D.tras_entrega=j.tras_entrega||{};D.episodios=j.episodios||[];
  Object.assign(D.riders,j.riders||{});cabecera();render();}
function cargarVivo(){try{fetch(new URL('wtd_vivo.json?t='+Date.now(),document.baseURI),{cache:'no-store'}).then(r=>r.ok?r.json():null).then(aplicarVivo).catch(()=>{});}catch(e){}}
$('nota').innerHTML='Cómo se calcula: se toma una muestra de posición y pedidos de cada rider cada ~5 min (la web se publica cada ~10 min). Si entre dos muestras desaparece su pedido activo, se queda sin pedido y sube su contador de entregas completadas, cuenta como <b>entrega</b> (si desaparece sin sumar entrega, es cancelación o reasignación y no se cuenta). '+
 '«Parado» = sigue a menos de 80 m del punto donde estaba tras entregar y sin coger otro pedido. El contador <b>en vivo</b> (punto rojo) cuenta desde la primera foto sin pedido tras la entrega y avanza cada segundo mientras el rider siga parado en la última foto; si el rider no aparece en la última foto (desconectado) o no llega foto nueva en 20 min, el contador se congela. Es un <b>mínimo</b> (≥): la entrega ocurrió entre dos fotos, así que la parada real puede ser hasta ~5 min mayor. '+
 '«En restaurante» = se ha quedado a menos de 100 m de un local donde se recogen pedidos (esperando el siguiente). «GPS congelado» = su ubicación no se actualiza, puede no estar parado de verdad. Las posiciones se guardan solo '+D.horas+' h (día completo); el histórico conserva únicamente cada parada (rider, horas y minutos), nunca coordenadas, durante 120 días.';
function seg(id,opts,val,on){const el=$(id);el.innerHTML=opts.map(o=>`<button data-v="${o.v}" class="${String(o.v)===String(val)?'on':''}">${o.l}${o.c!=null?`<span class="c">${o.c}</span>`:''}</button>`).join('');el.onclick=e=>{const b=e.target.closest('button');if(b)on(b.dataset.v);};}
const nombre=id=>(D.riders[id]||[])[0]||'';
const minPill=e=>{const m=liveMin(e),cls=m>=U*2?'alert':(m>=U?'mid':'');
  if(vivo(e))return `<span class="pill ${cls} live" data-desde="${e.desde}" title="Tiempo parado desde la primera foto sin pedido tras la entrega (${hhmm(e.desde)}). Puede ser hasta ~5 min más: la entrega fue entre ${hhmm(e.ent_ini)} y ${hhmm(e.ent_fin)}."><span class="dot"></span>≥ ${fmtDur(liveSec(e))}</span><span class="sub2">última foto ${hhmm(e.hasta)}</span>`;
  return `<span class="pill ${cls}" title="Entre ${e.min} y ${e.max} min">≥ ${e.min} min</span>`+(e.en_curso?`<span class="sub2">sin foto desde ${hhmm(e.hasta)}</span>`:'');};
const flags=e=>(e.local?'<span class="pill" title="A menos de 100 m de un restaurante conocido">En restaurante</span>':'')+
  (e.gps_viejo?`<span class="pill mid" title="La ubicación no se actualiza desde hace ${e.gps_viejo} min">GPS congelado ${e.gps_viejo} min</span>`:'')+
  (e.confirmada===null?'<span class="pill" title="Glovo no informó el contador de entregas: podría ser una cancelación">Sin confirmar</span>':'');
const STALE_MIN=20;   // sin foto nueva del rider en más de 20 min: se congela el contador
const vivo=e=>e.en_curso&&D.foto&&Math.abs(new Date(e.hasta)-new Date(D.foto))<90000&&(Date.now()-new Date(e.hasta).getTime())<STALE_MIN*60000;  // sigue en la última foto
const liveSec=e=>vivo(e)?Math.max(0,(Date.now()-new Date(e.desde).getTime())/1000):e.min*60;
const liveMin=e=>liveSec(e)/60;
const fmtDur=sec=>{sec=Math.floor(sec);const h=Math.floor(sec/3600),m=Math.floor(sec%3600/60),s2=sec%60;return (h?h+':'+String(m).padStart(2,'0'):m)+':'+String(s2).padStart(2,'0');};
const passMin=e=>S.min==='ALL'||liveMin(e)>=(S.min==='D'?U*2:U);
function inicioHoy(){ // 05:00 de hoy en Madrid (o de ayer si aún no son las 05:00)
  const p={};new Intl.DateTimeFormat('en-CA',{timeZone:'Europe/Madrid',year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',hourCycle:'h23'}).formatToParts(new Date()).forEach(x=>p[x.type]=x.value);
  const off=(new Date().getTime()-Date.UTC(+p.year,+p.month-1,+p.day,+p.hour,new Date().getUTCMinutes(),new Date().getUTCSeconds(),new Date().getUTCMilliseconds()));
  let t=Date.UTC(+p.year,+p.month-1,+p.day,5,0,0)+off; if(+p.hour<5)t-=864e5; return new Date(t);}
const base=()=>D.episodios.filter(e=>(S.city==='ALL'||e.city===S.city)&&(S.loc==='ALL'||!e.local)&&
  (!S.q||String(e.rid).includes(S.q)||nombre(e.rid).toLowerCase().includes(S.q)));
const CA=[
 {k:'rid',h:'Rider',v:e=>Number(e.rid)||e.rid,f:e=>esc(e.rid)+(nombre(e.rid)?`<span class="nm">${esc(nombre(e.rid))}</span>`:''),d:'ID del rider en Glovo y nombre.'},
 {k:'city',h:'Área',v:e=>e.city,f:e=>esc(e.city),d:'Área (nodo) del rider.'},
 {k:'ent',h:'Entregó entre',v:e=>e.ent_fin,f:e=>hhmm(e.ent_ini)+' – '+hhmm(e.ent_fin),d:'Muestras entre las que desapareció el pedido entregado (hora de Madrid).'},
 {k:'min',h:'Parado (en vivo)',n:1,v:e=>liveMin(e),f:minPill,d:'Tiempo que lleva parado y sin pedido desde que entregó, contado en vivo (min:seg) desde la primera foto sin pedido. Es un mínimo: la entrega ocurrió entre dos fotos, hasta ~5 min antes. Debajo, la hora de la última foto que lo confirma.'},
 {k:'status',h:'Estado Glovo',v:e=>e.status||'',f:e=>esc(ST[e.status]||e.status||'—'),d:'Estado del rider en Live Operations en la última muestra parado.'},
 {k:'fl',h:'Avisos',v:e=>(e.local?1:0)+(e.gps_viejo?2:0),f:flags,d:'En restaurante, GPS congelado o entrega sin confirmar.'},
];
const CE=[CA[0],CA[1],CA[2],
 {k:'desde',h:'Parado desde',v:e=>e.desde,f:e=>hhmm(e.desde),d:'Primera muestra tras la entrega, ya sin pedido.'},
 {k:'hasta',h:'Hasta',v:e=>e.hasta,f:e=>vivo(e)?'<span class="pill alert">Sigue parado</span>':(e.en_curso?hhmm(e.hasta)+'<span class="sub2">sin foto nueva</span>':hhmm(e.hasta)),d:'Última muestra en el mismo punto sin pedido. «Sigue parado» si es la muestra más reciente.'},
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
  seg('fMin',[{v:'U',l:'Parados ≥'+U+' min'},{v:'D',l:'≥'+(U*2)+' min'},{v:'ALL',l:'Todas'}],S.min,v=>{S.min=v;render();});
  seg('fLoc',[{v:'SIN',l:'Excluir en restaurante'},{v:'ALL',l:'Incluir'}],S.loc,v=>{S.loc=v;render();});
  const B0=base().filter(e=>passMin(e));
  const now=B0.filter(e=>e.en_curso);
  const hoy=inicioHoy();const B=B0.filter(e=>new Date(e.desde)>=hoy);
  const nA=tabla('tA',CA,now,S.sa,'Ningún rider parado tras su última entrega con estos filtros.');
  const nE=tabla('tE',CE,B,S.se,'Ninguna parada tras entrega hoy con estos filtros.');
  $('cntA').textContent=nf(nA)+' riders';$('cntE').textContent=nf(nE)+' paradas';
  const hoy0=inicioHoy();const real=all.filter(e=>!e.local&&!e.gps_viejo&&new Date(e.desde)>=hoy0);
  const sobre=real.filter(e=>liveMin(e)>=U);
  const rid=new Set(sobre.map(e=>e.rid)),rep={};sobre.forEach(e=>rep[e.rid]=(rep[e.rid]||0)+1);
  const media=sobre.length?sobre.reduce((a,e)=>a+e.min,0)/sobre.length:null;
  const ahora=real.filter(e=>vivo(e)&&liveMin(e)>=U).length;
  $('kpis').innerHTML=[
   ['Parados ahora tras entrega',`<span style="color:${ahora?'var(--bad)':'inherit'}">${nf(ahora)}</span>`,D.foto?'≥'+U+' min · a las '+hhmm(D.foto):'sin posiciones','Riders que en la última muestra llevan al menos '+U+' min sin moverse y sin pedido desde su última entrega (sin contar en restaurante ni GPS congelado).'],
   ['Paradas ≥'+U+' min hoy',nf(sobre.length),nf(rid.size)+' riders · '+nf(sobre.filter(e=>e.min>=U*2).length)+' de ≥'+(U*2)+' min','Paradas tras entrega de al menos '+U+' min hoy desde las 05:00 (sin contar en restaurante ni GPS congelado).'],
   ['Minutos medios parado',media==null?'—':nf(media,0)+' min','mínimo por parada ≥'+U+' min','Media de los minutos mínimos parado en las paradas tras entrega de al menos '+U+' min.'],
   ['Riders reincidentes hoy',nf(Object.values(rep).filter(x=>x>=2).length),'2 o más paradas ≥'+U+' min','Riders con al menos dos paradas tras entrega de '+U+' min o más hoy desde las 05:00.'],
  ].map(([e,b,s,d])=>`<div class="kpi"><em data-def="${esc(d)}" tabindex="0">${e}</em><b>${b}</b><span>${s}</span></div>`).join('');
  if(typeof renderHist==='function'&&HROWS.length)renderHist();
}
/* ===== Histórico (wtd_v1_hist.json, se acumula cada ~10 min) ===== */
const HS={wk:'ALL',day:'ALL',sr:{k:'n',d:-1},se:{k:'e1',d:-1}};let HROWS=[],HUPD=null;
const FMT=new Intl.DateTimeFormat('en-CA',{timeZone:'Europe/Madrid',year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',hourCycle:'h23'});
function diaOp(min){ // día operativo en Madrid: de 05:00 a 04:59
  const p={};FMT.formatToParts(new Date(min*60000)).forEach(x=>p[x.type]=x.value);
  let d=new Date(Date.UTC(+p.year,+p.month-1,+p.day));if(+p.hour<5)d=new Date(d-864e5);return d;}
function isoW(d){const t=new Date(d);const dn=(t.getUTCDay()+6)%7;t.setUTCDate(t.getUTCDate()-dn+3);const y=t.getUTCFullYear();
  const f=new Date(Date.UTC(y,0,4));return [y,1+Math.round(((t-f)/864e5-3+((f.getUTCDay()+6)%7))/7)];}
const ymd=d=>d.toISOString().slice(0,10);
const DOW=['dom','lun','mar','mié','jue','vie','sáb'];
const dlab=k=>{const d=new Date(k+'T00:00:00Z');return DOW[d.getUTCDay()]+' '+k.slice(8,10)+'/'+k.slice(5,7);};
const hm=min=>min==null?'—':hhmm(new Date(min*60000).toISOString());
function cargarHist(){try{fetch(new URL('wtd_v1_hist.json?t='+Date.now(),document.baseURI),{cache:'no-store'}).then(r=>r.ok?r.json():null).then(j=>{
  if(!j||!j.eps)return;HUPD=j.updated_at;
  HROWS=j.eps.filter(f=>D.cities.includes(f[1])).map(f=>{const d=diaOp(f[4]);const w=isoW(d);
    return {rid:f[0],city:f[1],status:f[2],e0:f[3],e1:f[4],h:f[5],min:f[6],max:f[7],local:!!(f[8]&1),gps:!!(f[8]&2),sc:!!(f[8]&4),day:ymd(d),wk:w[0]+'-W'+String(w[1]).padStart(2,'0')};});
  renderHist();}).catch(()=>{});}catch(e){}}
function hBase(){return HROWS.filter(e=>(S.city==='ALL'||e.city===S.city)&&(S.loc==='ALL'||!e.local)&&passMin(e)&&
  (!S.q||String(e.rid).includes(S.q)||nombre(e.rid).toLowerCase().includes(S.q)));}
function renderHist(){
  const B0=hBase();
  const wks=[...new Set(HROWS.map(e=>e.wk))].sort().reverse();
  if(HS.wk!=='ALL'&&!wks.includes(HS.wk))HS.wk='ALL';
  $('hWk').innerHTML='<option value="ALL">Todas</option>'+wks.map(w=>`<option value="${w}" ${w===HS.wk?'selected':''}>${w.slice(5)} · ${w.slice(0,4)}</option>`).join('');
  const B1=B0.filter(e=>HS.wk==='ALL'||e.wk===HS.wk);
  const days=[...new Set(HROWS.filter(e=>HS.wk==='ALL'||e.wk===HS.wk).map(e=>e.day))].sort().reverse();
  if(HS.day!=='ALL'&&!days.includes(HS.day))HS.day='ALL';
  $('hDay').innerHTML='<option value="ALL">Todas</option>'+days.map(d=>`<option value="${d}" ${d===HS.day?'selected':''}>${dlab(d)}</option>`).join('');
  const B=B1.filter(e=>HS.day==='ALL'||e.day===HS.day);
  const real=B.filter(e=>!e.gps);
  const desde=HROWS.length?HROWS.reduce((a,e)=>e.day<a?e.day:a,'9999'):null;
  $('hSub').textContent=!HROWS.length?'Todavía no hay histórico: se empieza a acumular con el muestreo de cada ~10 min.':
    ('Histórico desde el '+dlab(desde)+' · día operativo de 05:00 a 04:59 · actualizado a las '+hhmm(HUPD)+'.');
  // recurrencia por rider
  const R={};real.forEach(e=>{const r=R[e.rid]||(R[e.rid]={rid:e.rid,city:e.city,n:0,days:new Set(),wks:new Set(),tot:0,mx:0,last:0});
    r.n++;r.days.add(e.day);r.wks.add(e.wk);r.tot+=e.min;r.mx=Math.max(r.mx,e.min);r.last=Math.max(r.last,e.e1);});
  const RR=Object.values(R).map(r=>({...r,nd:r.days.size,nw:r.wks.size,avg:r.tot/r.n}));
  const rein=RR.filter(r=>r.nd>=2).length;
  const media=real.length?real.reduce((a,e)=>a+e.min,0)/real.length:null;
  const ndias=new Set(real.map(e=>e.day)).size||1;
  $('hKpis').innerHTML=[
   ['Paradas',nf(real.length),nf(real.length/ndias,1)+' por día · '+nf(ndias)+' días','Paradas tras entrega en el periodo y filtros elegidos (sin GPS congelado).'],
   ['Riders con paradas',nf(RR.length),'',"Riders distintos con al menos una parada en el periodo."],
   ['Reincidentes',`<span style="color:${rein?'var(--bad)':'inherit'}">${nf(rein)}</span>`,RR.length?nf(rein/RR.length*100,0)+' % de los riders con paradas':'','Riders con paradas en 2 o más días distintos del periodo.'],
   ['Minutos medios',media==null?'—':nf(media,0)+' min','mínimo por parada','Media de los minutos mínimos parado por parada.'],
  ].map(([e,b,s2,d])=>`<div class="kpi"><em data-def="${esc(d)}" tabindex="0">${e}</em><b>${b}</b><span>${s2}</span></div>`).join('');
  // barras: por día (o por semana si "Todas" y hay más de 21 días)
  const porSem=HS.wk==='ALL'&&HS.day==='ALL'&&new Set(real.map(e=>e.day)).size>21;
  const key=porSem?(e=>e.wk):(e=>e.day);
  const base2=B1.filter(e=>!e.gps);
  const G={};base2.forEach(e=>{const k=key(e);(G[k]||(G[k]={n:0,r:new Set()})).n++;G[k].r.add(e.rid);});
  const ks=Object.keys(G).sort();const mx=Math.max(1,...ks.map(k=>G[k].n));
  $('hBarsT').textContent=porSem?'Paradas por semana':'Paradas por día';
  $('hBars').innerHTML=ks.length?ks.map(k=>`<div class="bar ${(!porSem&&HS.day===k)||(porSem&&HS.wk===k)?'sel':''}" data-k="${k}" title="${G[k].n} paradas · ${G[k].r.size} riders"><b>${G[k].n}</b><i style="height:${G[k].n/mx*120}px"></i><span>${porSem?k.slice(5):dlab(k)}</span></div>`).join(''):'<span class="muted">Sin paradas en el histórico con estos filtros.</span>';
  $('hBars').querySelectorAll('.bar').forEach(b=>b.onclick=()=>{const k=b.dataset.k;if(porSem){HS.wk=HS.wk===k?'ALL':k;}else{HS.day=HS.day===k?'ALL':k;}renderHist();});
  const CR=[
   {k:'rid',h:'Rider',v:r=>Number(r.rid)||r.rid,f:r=>esc(r.rid)+(nombre(r.rid)?`<span class="nm">${esc(nombre(r.rid))}</span>`:''),d:'ID del rider y nombre (si se ha conectado hoy).'},
   {k:'city',h:'Área',v:r=>r.city,f:r=>esc(r.city),d:'Área del rider.'},
   {k:'n',h:'Paradas',n:1,v:r=>r.n,f:r=>`<span class="pill ${r.n>=5?'alert':(r.n>=2?'mid':'')}">${r.n}</span>`,d:'Paradas tras entrega en el periodo.'},
   {k:'nd',h:'Días',n:1,v:r=>r.nd,f:r=>nf(r.nd),d:'Días distintos con al menos una parada (recurrencia).'},
   {k:'nw',h:'Semanas',n:1,v:r=>r.nw,f:r=>nf(r.nw),d:'Semanas distintas con al menos una parada.'},
   {k:'tot',h:'Min totales',n:1,v:r=>r.tot,f:r=>nf(r.tot),d:'Suma de minutos mínimos parado.'},
   {k:'avg',h:'Min medio',n:1,v:r=>r.avg,f:r=>nf(r.avg,0),d:'Minutos medios por parada.'},
   {k:'mx',h:'Máximo',n:1,v:r=>r.mx,f:r=>nf(r.mx),d:'Parada más larga (min).'},
   {k:'last',h:'Última',v:r=>r.last,f:r=>{const d=diaOp(r.last);return dlab(ymd(d))+' '+hm(r.last);},d:'Última parada tras entrega del rider.'},
  ];
  const nR=tabla('hR',CR,RR,HS.sr,'Ningún rider con paradas en este periodo.');
  if(nR)$('hR').querySelectorAll('tbody tr').forEach((tr,i)=>{tr.className='click';tr.title='Ver solo este rider';tr.onclick=()=>{const id=tr.cells[0].firstChild.textContent;$('fQ').value=id;S.q=id;render();renderHist();};});
  $('hCntR').textContent=nf(nR)+' riders';
  const CEh=[CR[0],CR[1],
   {k:'e1',h:'Día',v:e=>e.e1,f:e=>dlab(e.day),d:'Día operativo de la parada.'},
   {k:'ent',h:'Entregó entre',v:e=>e.e1,f:e=>hm(e.e0)+' – '+hm(e.e1),d:'Muestras entre las que se entregó el pedido.'},
   {k:'h',h:'Parado hasta',v:e=>e.h,f:e=>hm(e.h),d:'Última muestra en el mismo punto sin pedido.'},
   {k:'min',h:'Parado',n:1,v:e=>e.min,f:minPill,d:'Minutos mínimos parado (al pasar el ratón, el rango).'},
   {k:'status',h:'Estado Glovo',v:e=>e.status||'',f:e=>esc(ST[e.status]||e.status||'—'),d:'Estado en la última muestra parado.'},
   {k:'fl',h:'Avisos',v:e=>(e.local?1:0)+(e.gps?2:0),f:e=>flags({local:e.local,gps_viejo:e.gps?'?':0,confirmada:e.sc?null:true}).replace('GPS congelado ? min','GPS congelado'),d:'En restaurante, GPS congelado o entrega sin confirmar.'},
  ];
  const nE=tabla('hDet',CEh,B.slice().sort((a,b)=>b.e1-a.e1).slice(0,500),HS.se,'Ninguna parada en este periodo.');
  $('hCntE').textContent=nf(B.length)+' paradas'+(B.length>500?' (se muestran 500)':'');
}
$('hWk').onchange=e=>{HS.wk=e.target.value;HS.day='ALL';renderHist();};
$('hDay').onchange=e=>{HS.day=e.target.value;renderHist();};
let qT;$('fQ').addEventListener('input',e=>{clearTimeout(qT);qT=setTimeout(()=>{S.q=e.target.value.trim().toLowerCase();render();renderHist();},150);});
(function(){const tip=document.createElement('div');tip.id='defTip';tip.hidden=true;document.body.appendChild(tip);
  const place=(x,y)=>{const w=tip.offsetWidth,h=tip.offsetHeight;let l=x+12,t=y+14;if(l+w>innerWidth-8)l=Math.max(8,x-w-12);if(t+h>innerHeight-8)t=Math.max(8,y-h-12);tip.style.left=l+'px';tip.style.top=t+'px';};
  document.addEventListener('mouseover',e=>{const el=e.target.closest('[data-def]');if(el){tip.textContent=el.dataset.def;tip.hidden=false;place(e.clientX,e.clientY);}});
  document.addEventListener('mousemove',e=>{if(!tip.hidden&&e.target.closest('[data-def]'))place(e.clientX,e.clientY);});
  document.addEventListener('mouseout',e=>{const el=e.target.closest('[data-def]');if(el&&!el.contains(e.relatedTarget))tip.hidden=true;});})();
render();
cargarVivo();setInterval(cargarVivo,60*1000);
/* contador en vivo: cada segundo actualiza los tiempos; cada minuto re-renderiza (orden y colores) */
setInterval(()=>{document.querySelectorAll('.live[data-desde]').forEach(el=>{const sec=(Date.now()-new Date(el.dataset.desde).getTime())/1000;
  const m=sec/60;el.classList.toggle('alert',m>=U*2);el.classList.toggle('mid',m>=U&&m<U*2);const d=el.querySelector('.dot');el.textContent='≥ '+fmtDur(sec);if(d)el.prepend(d);});},1000);
setInterval(render,60*1000);
cargarHist();setInterval(cargarHist,10*60*1000);renderHist();
if(window.parent!==window){const send=()=>window.parent.postMessage({v1H:document.body.getBoundingClientRect().height},'*');
  if(window.ResizeObserver) new ResizeObserver(send).observe(document.body); send();}
</script></body></html>
'''
