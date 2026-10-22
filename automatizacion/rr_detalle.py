# -*- coding: utf-8 -*-
"""
rr_detalle.py · Detalle de RR % en la pestaña Delivery Race
=============================================================
Con la métrica «RR %» (o un tipo de incidencia GCP) seleccionada en Delivery Race, la celda
de la semana en curso de cada rider se puede pulsar: abre la lista de sus pedidos
reasignados esa semana (reassignment_lv del bucket GCP) con un mapa. Al pulsar un pedido,
el mapa se centra en su restaurante y muestra el tiempo real hasta la reasignación frente
al tiempo máximo de recogida del sistema (15 min, reasignación automática de Glovo).

Solo se publica la ubicación del RESTAURANTE (como en Mapas de calor); el bucket no trae la
posición ni la hora planeada del rider al que se le reasignó el pedido.

Lo usa generar_resumen_flota.py (si está junto a él).
"""
import json

LIMITE_RECOGIDA_MIN = 15        # reasignación automática por «pedido parado en recogida»


def _hhmm(s):
    s = str(s or "")
    return s[11:16] if len(s) >= 16 else ""


def construir_datos(cities, semana_label):
    """{rider: [[fecha, order_id, restaurante, aviso, reasignado, segundos, motivo, quien, lat, lon], ...]}"""
    import heatmaps_reasignaciones as H
    re_df, loc = H._cargar()
    ls_ = H._CACHE.get("loc_store", {})
    df = re_df[re_df["_city"].isin(set(cities))]
    df = df[df["_wkey"].map(lambda k: "W" + str(k[1])) == semana_label]
    out = {}
    for g in df.sort_values("_ts").to_dict("records"):
        did = str(g.get("delivery_id", "")); store = str(g.get("store_name", ""))
        lat, lon = H.punto(loc.get(did) or ls_.get(store + "|" + str(g.get("zone_name", "")))
                           or ls_.get(store + "|" + str(g.get("city_code", ""))) or "")
        try:
            secs = int(float(g.get("time_to_reassign_seconds") or 0))
        except Exception:
            secs = None
        reason = str(g.get("reassignment_reason", ""))
        perf = str(g.get("reassignment_performed_by", ""))
        out.setdefault(str(g.get("rider_id", "")).strip(), []).append([
            g["_day"].strftime("%Y-%m-%d"),
            str(g.get("order_id", "")).strip(),
            store,
            _hhmm(g.get("notified_at_local")),
            _hhmm(g.get("reassigned_at_local")),
            secs,
            H._info(reason)["es"],
            H.PERF_INFO.get(perf, (perf or "(sin dato)", ""))[0],
            reason == "PickupIdleOrder",
            lat, lon,
        ])
    return out


JS = r"""<script>
/* ==== Delivery Race · detalle de RR % (pedidos reasignados de la semana en curso) ==== */
(function(){
  const RRD=__RRDET__, SEM='__SEM__', LIM=__LIM__;
  const MET=new Set(['reassign','notSeen','ignored','decline','redispatch','cnm','agent']);
  const body=document.getElementById('ligaBody'), sel=document.getElementById('ligaMetricSel');
  if(!body||!sel) return;
  const css=document.createElement('style');
  css.textContent='td.trendwk.rrclick{cursor:pointer;text-decoration:underline dotted;text-underline-offset:3px}'+
   'td.trendwk.rrclick:hover{outline:1px solid #4FD1B4}'+
   '#rrOv{position:fixed;inset:0;background:rgba(0,0,0,.55);z-index:9999;display:none;align-items:center;justify-content:center}'+
   '#rrOv.on{display:flex}#rrBox{background:#161C24;color:#E9ECF1;border:1px solid #333F4D;border-radius:12px;width:min(1100px,96vw);max-height:90vh;display:flex;flex-direction:column;overflow:hidden}'+
   '#rrHd{display:flex;gap:10px;align-items:center;padding:12px 16px;border-bottom:1px solid #333F4D}#rrHd b{flex:1}#rrHd button{all:unset;cursor:pointer;padding:2px 8px;border:1px solid #333F4D;border-radius:6px}'+
   '#rrBd{display:grid;grid-template-columns:minmax(0,1.15fr) minmax(0,1fr);gap:0;min-height:0;flex:1}'+
   '#rrList{overflow:auto;max-height:76vh}#rrMap{min-height:440px;height:100%}'+
   '#rrList table{width:100%;border-collapse:collapse;font-size:12.5px}#rrList th{position:sticky;top:0;background:#1B232D;color:#98A3B3;text-align:left;padding:7px 8px;font-weight:600;white-space:nowrap}'+
   '#rrList td{padding:6px 8px;border-top:1px solid #222B36;white-space:nowrap}#rrList tr.o{cursor:pointer}#rrList tr.o:hover td{background:#1D2733}#rrList tr.sel td{background:#203040}'+
   '.rrbar{display:inline-block;height:6px;border-radius:3px;vertical-align:middle;margin-left:6px}'+
   '@media(max-width:760px){#rrBd{grid-template-columns:1fr}#rrMap{min-height:300px}}';
  document.head.appendChild(css);
  const ov=document.createElement('div'); ov.id='rrOv';
  ov.innerHTML='<div id="rrBox"><div id="rrHd"><b id="rrT"></b><span id="rrS" style="color:#98A3B3;font-size:12px"></span><button id="rrX">Cerrar</button></div>'+
    '<div id="rrBd"><div id="rrList"></div><div id="rrMap"></div></div>'+
    '<div style="padding:8px 16px;color:#98A3B3;font-size:11.5px;border-top:1px solid #333F4D">Fuente: reassignment_lv del bucket GCP de Glovo. «Máx. recogida» = '+LIM+' min, tiempo a partir del cual el sistema reasigna solo un pedido parado en recogida. El bucket no trae la posición ni la hora estimada del rider al que se le reasignó: en el mapa solo se marca el restaurante.</div></div>';
  document.body.appendChild(ov);
  ov.addEventListener('click',e=>{ if(e.target===ov||e.target.id==='rrX') ov.classList.remove('on'); });
  const esc=s=>String(s??'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
  const mmss=s=>s==null?'–':Math.floor(s/60)+':'+String(s%60).padStart(2,'0');
  const ddmm=d=>d.slice(8,10)+'/'+d.slice(5,7);

  let map=null, layer=null, Lp=null;
  function leaflet(){ if(window.L) return Promise.resolve(window.L); if(Lp) return Lp;
    Lp=new Promise((ok,ko)=>{ const l=document.createElement('link'); l.rel='stylesheet';
      l.href='https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.css'; document.head.appendChild(l);
      const s=document.createElement('script'); s.src='https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.js';
      s.onload=()=>ok(window.L); s.onerror=ko; document.head.appendChild(s); }); return Lp; }

  function popup(o){ const [f,oid,st,av,re,secs,mot,quien,auto]=o; const lim=LIM*60;
    const pct=secs!=null?Math.min(100,Math.round(secs/lim*100)):0;
    return '<b>'+esc(st)+'</b><br>Pedido <b>'+esc(oid)+'</b> · '+ddmm(f)+'<br>'+
      'Aviso '+esc(av||'–')+' → reasignado '+esc(re||'–')+'<br>'+
      'Real hasta reasignar: <b>'+mmss(secs)+' min</b><br>'+
      'Máx. recogida (sistema): <b>'+LIM+':00 min</b>'+(secs!=null?' ('+(secs>=lim?'+':'')+mmss(Math.abs(secs-lim))+(secs>=lim?' por encima':' por debajo')+')':'')+'<br>'+
      '<span style="color:#666">'+esc(mot)+' · '+esc(quien)+'</span>'; }

  async function abrir(rid){
    const L0=RRD[rid]||[];
    document.getElementById('rrT').textContent='Rider '+rid+' · pedidos reasignados '+SEM;
    const tot=L0.length, med=tot?L0.reduce((a,o)=>a+(o[5]||0),0)/tot:0;
    document.getElementById('rrS').textContent=tot+' pedidos · media '+mmss(Math.round(med))+' min hasta reasignar';
    const lim=LIM*60;
    document.getElementById('rrList').innerHTML=tot?'<table><thead><tr><th>Día</th><th>Pedido</th><th>Restaurante</th><th>Aviso</th><th>Reasig.</th><th title="Tiempo máximo de recogida del sistema">Máx. recogida</th><th>Real</th><th>Motivo</th></tr></thead><tbody>'+
      L0.map((o,i)=>{ const s=o[5]; const w=s!=null?Math.min(60,Math.round(s/lim*40)):0; const c=s==null?'#555':(s>=lim?'#E5624D':'#3FB984');
        return '<tr class="o" data-i="'+i+'"><td>'+ddmm(o[0])+'</td><td style="font-family:ui-monospace,monospace">'+esc(o[1])+'</td><td>'+esc(o[2])+'</td><td>'+esc(o[3]||'–')+'</td><td>'+esc(o[4]||'–')+'</td>'+
          '<td>'+LIM+':00</td><td><b>'+mmss(s)+'</b><span class="rrbar" style="width:'+w+'px;background:'+c+'"></span></td><td style="color:#98A3B3">'+esc(o[6])+'<br><span style="font-size:11px">'+esc(o[7])+'</span></td></tr>'; }).join('')+'</tbody></table>'
      :'<div style="padding:16px;color:#98A3B3">El bucket no trae pedidos reasignados de este rider en '+SEM+' (puede ir con un día de retraso respecto al RR %).</div>';
    ov.classList.add('on');
    let L; try{ L=await leaflet(); }catch(e){ document.getElementById('rrMap').innerHTML='<div style="padding:16px;color:#98A3B3">No se pudo cargar el mapa.</div>'; return; }
    if(!map){ map=L.map('rrMap',{zoomControl:true}); L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png',{maxZoom:19,attribution:'© OpenStreetMap · © CARTO'}).addTo(map); }
    if(layer) layer.remove(); layer=L.layerGroup().addTo(map);
    const mk=[]; const pts=[];
    L0.forEach((o,i)=>{ const lat=o[9],lon=o[10]; if(lat==null||lon==null){ mk[i]=null; return; }
      const s=o[5], c=s==null?'#888':(s>=lim?'#E5624D':'#3FB984');
      const m=L.circleMarker([lat,lon],{radius:8,color:'#fff',weight:1.5,fillColor:c,fillOpacity:.9}).bindPopup(popup(o)).addTo(layer);
      m.on('click',()=>marcar(i)); mk[i]=m; pts.push([lat,lon]); });
    setTimeout(()=>{ map.invalidateSize(); if(pts.length) map.fitBounds(pts,{padding:[30,30],maxZoom:15}); else map.setView([40.2,-3.7],6); },60);
    function marcar(i){ document.querySelectorAll('#rrList tr.o').forEach(tr=>tr.classList.toggle('sel',+tr.dataset.i===i)); }
    document.querySelectorAll('#rrList tr.o').forEach(tr=>tr.onclick=()=>{ const i=+tr.dataset.i, m=mk[i]; marcar(i);
      if(m){ map.flyTo(m.getLatLng(),16,{duration:.6}); setTimeout(()=>m.openPopup(),650); }
      else L.popup().setLatLng(map.getCenter()).setContent(popup(L0[i])+'<br><i>Sin ubicación del restaurante</i>').openOn(map); });
  }

  function marcarCeldas(){
    if(!MET.has(sel.value)) return;
    body.querySelectorAll('tr').forEach(tr=>{ const td=tr.querySelector('td.trendwk.last'), r=tr.querySelector('td.rider');
      if(!td||!r) return; const rid=r.textContent.trim();
      if(RRD[rid]&&RRD[rid].length&&td.textContent.trim()!=='–'){ td.classList.add('rrclick'); td.title='Ver los '+RRD[rid].length+' pedidos reasignados de '+SEM+' en el mapa'; } });
  }
  new MutationObserver(marcarCeldas).observe(body,{childList:true});
  sel.addEventListener('change',()=>setTimeout(marcarCeldas,0));
  marcarCeldas();
  body.addEventListener('click',e=>{ const td=e.target.closest('td.trendwk.rrclick'); if(!td||!MET.has(sel.value)) return;
    const r=td.parentElement.querySelector('td.rider'); if(r) abrir(r.textContent.trim()); });
})();
</script>
"""


def integrar(dash_html, cities, semana_label):
    if "liga-trend-css" not in dash_html or 'id="ligaBody"' not in dash_html:
        raise ValueError("no encuentro la tabla de Delivery Race de tendencia")
    if "Delivery Race · detalle de RR %" in dash_html:
        return dash_html, "ya integrado"
    datos = construir_datos(cities, semana_label)
    payload = json.dumps(datos, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c")
    js = (JS.replace("__RRDET__", payload).replace("__SEM__", semana_label)
            .replace("__LIM__", str(LIMITE_RECOGIDA_MIN)))
    i = dash_html.rindex("</body>")
    n = sum(len(v) for v in datos.values())
    return dash_html[:i] + js + dash_html[i:], "%d pedidos reasignados de %d riders en %s" % (n, len(datos), semana_label)
