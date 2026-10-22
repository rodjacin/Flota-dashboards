# -*- coding: utf-8 -*-
"""
paradas_mapa.py · Pestaña «Paradas con pedido» (mapa de calor)
===============================================================
Mapa de calor de los puntos donde los riders han estado parados 3 min o más con un pedido
activo y lejos de un restaurante (muestreo de posiciones de Live Operations, cada minuto).

La página lee <dashboard>/pp_heat.json, que escribe posiciones.py cada ~10 min con datos
AGREGADOS por celda de ~200 m, día, hora, área, tipo y duración: no lleva rider ni hora exacta.
Las posiciones de cada parada solo existen en la caché privada de GitHub Actions.

Lo usa generar_resumen_flota.py (si está junto a él).
"""

_BTN = '<button data-v="ppheat" aria-pressed="false">Paradas con pedido</button>'

_SECCION = r"""<section id="viewPpHeat" style="display:none">
<style>
#viewPpHeat .pph-wrap{display:flex;flex-direction:column;gap:12px}
#viewPpHeat .pph-f{display:flex;flex-wrap:wrap;gap:12px;align-items:flex-end}
#viewPpHeat .pph-f label{display:block;font-size:11px;color:var(--muted,#6B7280);margin-bottom:4px;text-transform:uppercase;letter-spacing:.04em}
#viewPpHeat select{border:1px solid #D4D9E1;border-radius:8px;padding:6px 9px;font:inherit;font-size:13px;background:#fff;color:#14171F}
#viewPpHeat .pph-k{display:flex;flex-wrap:wrap;gap:10px}
#viewPpHeat .pph-k div{background:#fff;border:1px solid #E4E7EC;border-radius:10px;padding:9px 14px;min-width:130px}
#viewPpHeat .pph-k b{display:block;font-size:20px;color:#14171F}
#viewPpHeat .pph-k span{font-size:11.5px;color:#6B7280}
#viewPpHeat .pph-body{display:grid;grid-template-columns:minmax(0,1fr) 330px;gap:12px}
#ppMap{height:calc(100vh - 290px);min-height:420px;border:1px solid #E4E7EC;border-radius:10px}
#viewPpHeat .pph-top{background:#fff;border:1px solid #E4E7EC;border-radius:10px;overflow:auto;max-height:calc(100vh - 290px)}
#viewPpHeat .pph-top table{width:100%;min-width:0;border-collapse:collapse;font-size:12.5px}
#viewPpHeat .pph-top th{position:sticky;top:0;background:#F0F2F5;text-align:left;padding:7px 8px;font-size:11px;color:#6B7280;text-transform:uppercase}
#viewPpHeat .pph-top td{padding:6px 8px;border-top:1px solid #EEF0F3}
#viewPpHeat .pph-top tr.o{cursor:pointer}#viewPpHeat .pph-top tr.o:hover td{background:#F5F8FA}
#viewPpHeat .pph-note{font-size:11.5px;color:#6B7280}
#viewPpHeat .pph-leg{display:inline-block;width:90px;height:9px;border-radius:4px;vertical-align:middle;background:linear-gradient(90deg,#FED976,#FD8D3C,#E31A1C,#800026)}
@media(max-width:900px){#viewPpHeat .pph-body{grid-template-columns:1fr}#ppMap{height:60vh}}
</style>
<div class="pph-wrap">
  <div>
    <h1 style="font-size:17px;margin:0">Paradas con pedido · mapa de calor</h1>
    <div class="pph-note" id="ppSub">Puntos donde los riders han estado parados 3 min o más con un pedido activo, fuera de un restaurante.</div>
  </div>
  <div class="pph-f">
    <div><label>Área</label><select id="ppArea"></select></div>
    <div><label>Semana</label><select id="ppWeek"></select></div>
    <div><label>Día</label><select id="ppDay"></select></div>
    <div><label>Franja</label><select id="ppHour"><option value="ALL">Todo el día</option><option value="c">Comida 12–16</option><option value="n">Cena 19–24</option></select></div>
    <div><label>Tipo de parada</label><select id="ppTipo"><option value="ALL">Todas</option><option value="S">En el trayecto (siguió con el pedido)</option><option value="E">En la puerta del cliente (terminó en entrega)</option><option value="N">Sin confirmar</option></select></div>
    <div><label>Duración</label><select id="ppMin"><option value="3">≥ 3 min</option><option value="5">≥ 5 min</option><option value="10">≥ 10 min</option></select></div>
  </div>
  <div class="pph-k" id="ppKpi"></div>
  <div class="pph-body">
    <div id="ppMap"></div>
    <div class="pph-top" id="ppTop"></div>
  </div>
  <div class="pph-note">Color y tamaño = nº de paradas en la celda (~200 m): <span class="pph-leg"></span> de menos a más. Fuente: muestreo de posiciones de Live Operations (cada minuto); la parada se confirma cuando Glovo actualiza la ubicación al menos dos veces en el mismo punto. Datos agregados: no incluye riders ni horas exactas. Disponible desde el 22/10/2026.</div>
</div>
</section>
"""

_JS = r"""<script>
/* ==== Pestaña Paradas con pedido (mapa de calor agregado) ==== */
(function(){
  const seg=document.getElementById('viewSeg'), sec=document.getElementById('viewPpHeat');
  if(!seg||!sec) return;
  const $=id=>document.getElementById(id);
  const DOWS=['dom','lun','mar','mié','jue','vie','sáb'];
  const dlab=d=>{const x=new Date(d+'T12:00:00');return DOWS[x.getDay()]+' '+d.slice(8,10)+'/'+d.slice(5,7);};
  const isoW=d=>{const t=new Date(d+'T12:00:00');const dn=(t.getDay()+6)%7;t.setDate(t.getDate()-dn+3);const f=new Date(t.getFullYear(),0,4);return 1+Math.round(((t-f)/864e5-3+((f.getDay()+6)%7))/7);};
  const nf=(v,d)=>v.toLocaleString('es-ES',{minimumFractionDigits:d||0,maximumFractionDigits:d||0});
  let R=[], CEL=0.002, map=null, layer=null, cargado=false, Lp=null;
  const st={area:'ALL',week:'ALL',day:'ALL',hour:'ALL',tipo:'ALL',min:3};

  function leaflet(){ if(window.L) return Promise.resolve(window.L); if(Lp) return Lp;
    Lp=new Promise((ok,ko)=>{ const l=document.createElement('link'); l.rel='stylesheet';
      l.href='https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.css'; document.head.appendChild(l);
      const s=document.createElement('script'); s.src='https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.js';
      s.onload=()=>ok(window.L); s.onerror=ko; document.head.appendChild(s); }); return Lp; }
  const RAMP=[[254,217,118],[253,141,60],[227,26,28],[128,0,38]];
  function col(t){ t=Math.max(0,Math.min(1,t)); const i=Math.min(2,Math.floor(t*3)), f=t*3-i, a=RAMP[i], b=RAMP[i+1];
    return 'rgb('+a.map((x,k)=>Math.round(x+(b[k]-x)*f)).join(',')+')'; }

  function opts(id,vals,cur){ $(id).innerHTML=vals.map(([v,l])=>'<option value="'+v+'"'+(String(v)===String(cur)?' selected':'')+'>'+l+'</option>').join(''); }
  function filtros(){
    const areas=[...new Set(R.map(r=>r.area))].sort();
    opts('ppArea',[['ALL','Todas']].concat(areas.map(a=>[a,a])),st.area);
    const ws=[...new Set(R.map(r=>r.w))].sort((a,b)=>b-a);
    if(st.week!=='ALL'&&!ws.includes(+st.week)) st.week='ALL';
    opts('ppWeek',[['ALL','Todas']].concat(ws.map(w=>[w,'W'+w])),st.week);
    const ds=[...new Set(R.filter(r=>st.week==='ALL'||r.w===+st.week).map(r=>r.dia))].sort().reverse();
    if(st.day!=='ALL'&&!ds.includes(st.day)) st.day='ALL';
    opts('ppDay',[['ALL','Todos']].concat(ds.map(d=>[d,dlab(d)])),st.day);
  }
  function filas(){ return R.filter(r=>(st.area==='ALL'||r.area===st.area)&&(st.week==='ALL'||r.w===+st.week)&&(st.day==='ALL'||r.dia===st.day)
    &&(st.tipo==='ALL'||r.tipo===st.tipo)&&r.tramo>=st.min
    &&(st.hour==='ALL'||(st.hour==='c'?(r.hora>=12&&r.hora<16):(r.hora>=19)))); }

  async function pintar(){
    filtros();
    const F=filas(), C={};
    for(const r of F){ const k=r.lat+','+r.lon; const c=C[k]||(C[k]={lat:r.lat,lon:r.lon,n:0,m:0,S:0,E:0,N:0,area:r.area,h:{}});
      c.n+=r.n; c.m+=r.min; c[r.tipo]+=r.n; c.h[r.hora]=(c.h[r.hora]||0)+r.n; }
    const cel=Object.values(C).sort((a,b)=>b.n-a.n), tot=F.reduce((a,r)=>a+r.n,0), mins=F.reduce((a,r)=>a+r.min,0);
    const tr=F.filter(r=>r.tipo==='S').reduce((a,r)=>a+r.n,0), pu=F.filter(r=>r.tipo==='E').reduce((a,r)=>a+r.n,0);
    $('ppKpi').innerHTML=[[nf(tot),'Paradas con pedido'],[tot?nf(mins/tot,1)+' min':'–','Duración media'],[nf(tr),'En el trayecto'],[nf(pu),'En la puerta del cliente'],[nf(cel.length),'Zonas (~200 m)']]
      .map(([v,l])=>'<div><b>'+v+'</b><span>'+l+'</span></div>').join('');
    const hp=c=>{const e=Object.entries(c.h).sort((a,b)=>b[1]-a[1])[0]; return e?String(e[0]).padStart(2,'0')+':00':'–';};
    $('ppTop').innerHTML=cel.length?'<table><thead><tr><th>#</th><th>Área</th><th>Paradas</th><th>Media</th><th>Trayecto / puerta</th><th>Hora pico</th></tr></thead><tbody>'+
      cel.slice(0,40).map((c,i)=>'<tr class="o" data-i="'+i+'"><td>'+(i+1)+'</td><td>'+c.area+'</td><td><b>'+c.n+'</b></td><td>'+nf(c.m/c.n,1)+'′</td><td>'+c.S+' / '+c.E+'</td><td>'+hp(c)+'</td></tr>').join('')+'</tbody></table>'
      :'<div style="padding:14px;color:#6B7280">Sin paradas para este filtro.</div>';
    let L; try{ L=await leaflet(); }catch(e){ $('ppMap').innerHTML='<div style="padding:14px">No se pudo cargar el mapa.</div>'; return; }
    if(!map){ map=L.map('ppMap'); L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}',{maxZoom:19,attribution:'Tiles © Esri'}).addTo(map); }
    if(layer) layer.remove(); layer=L.layerGroup().addTo(map);
    const mx=Math.max(1,...cel.map(c=>c.n)), mk=[];
    cel.slice().reverse().forEach(c=>{ const t=Math.sqrt(c.n/mx);
      const m=L.circleMarker([c.lat,c.lon],{radius:5+t*16,stroke:false,fillColor:col(t),fillOpacity:.55+t*.3})
        .bindPopup('<b>'+c.n+' paradas</b> con pedido · '+c.area+'<br>Duración media '+nf(c.m/c.n,1)+' min<br>En el trayecto '+c.S+' · en la puerta '+c.E+(c.N?' · sin confirmar '+c.N:'')+'<br>Hora pico '+hp(c)).addTo(layer);
      mk[cel.indexOf(c)]=m; });
    setTimeout(()=>{ map.invalidateSize(); if(cel.length){ const b=L.latLngBounds(cel.map(c=>[c.lat,c.lon])); map.fitBounds(b,{padding:[30,30],maxZoom:15}); } else map.setView([40.2,-3.7],6); },50);
    document.querySelectorAll('#ppTop tr.o').forEach(tr=>tr.onclick=()=>{ const m=mk[+tr.dataset.i]; if(m){ map.flyTo(m.getLatLng(),16,{duration:.6}); setTimeout(()=>m.openPopup(),650);} });
  }
  async function cargar(){
    try{ const r=await fetch(new URL('pp_heat.json?t='+Date.now(),document.baseURI),{cache:'no-store'}); const j=r.ok?await r.json():null;
      if(j&&j.rows){ CEL=j.celda||CEL; R=j.rows.map(x=>({dia:x[0],hora:x[1],area:x[2],lat:x[3],lon:x[4],tipo:x[5],tramo:x[6],n:x[7],min:x[8],w:isoW(x[0])}));
        if(j.updated_at) $('ppSub').textContent='Puntos donde los riders han estado parados 3 min o más con un pedido activo, fuera de un restaurante · actualizado '+new Date(j.updated_at).toLocaleString('es-ES',{day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit'}); }
    }catch(e){}
    if(!R.length){ $('ppKpi').innerHTML=''; $('ppTop').innerHTML='<div style="padding:14px;color:#6B7280">Aún no hay paradas registradas. El mapa se rellena con el muestreo de posiciones (cada minuto) y se publica cada ~10 min.</div>'; }
    pintar();
  }
  [['ppArea','area'],['ppWeek','week'],['ppDay','day'],['ppHour','hour'],['ppTipo','tipo'],['ppMin','min']].forEach(([id,k])=>$(id).addEventListener('change',e=>{ st[k]=k==='min'?+e.target.value:e.target.value; pintar(); }));
  seg.querySelectorAll('button').forEach(b=>b.addEventListener('click',()=>{
    const on=b.dataset.v==='ppheat';
    sec.style.display=on?'':'none';
    if(on){ seg.querySelectorAll('button').forEach(x=>x.setAttribute('aria-pressed',String(x===b)));
      ['viewSemanal','viewDiario','viewLiga'].forEach(id=>{const e=document.getElementById(id); if(e) e.style.display='none';});
      window.scrollTo(0,0); if(!cargado){ cargado=true; cargar(); } else if(map) setTimeout(()=>map.invalidateSize(),50); }
  }));
})();
</script>
"""


def integrar_en_dashboard(dash_html):
    """Añade la pestaña «Paradas con pedido» al selector Vista (detrás de «Mapas de calor» si existe)."""
    if 'id="viewPpHeat"' in dash_html:
        return dash_html, "ya integrada"
    ancla_sec = '<div id="viewSemanal">'
    heat_btn = '<button data-v="heat" aria-pressed="false">Mapas de calor</button>'
    liga_btn = '<button data-v="liga" aria-pressed="false">Delivery Race</button>'
    ancla_btn = heat_btn if heat_btn in dash_html else liga_btn
    if ancla_btn not in dash_html or ancla_sec not in dash_html or "</body>" not in dash_html:
        raise ValueError("la plantilla no tiene el selector de Vista esperado")
    dash_html = dash_html.replace(ancla_btn, ancla_btn + "\n        " + _BTN, 1)
    dash_html = dash_html.replace(ancla_sec, _SECCION + "  " + ancla_sec, 1)
    i = dash_html.rindex("</body>")
    return dash_html[:i] + _JS + dash_html[i:], "pestaña añadida (lee pp_heat.json)"
