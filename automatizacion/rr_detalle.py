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


def _eta_por_tienda(H):
    """Mediana (s) del tiempo planeado por Glovo hasta la recogida en cada tienda:
    estimated_pickup_arrival_local_at − rider_notified_local_at de sus entregas (últimos 28 días)."""
    import pandas as pd
    dl = H.leer(pd, "delivery_lv.csv", cols=["vendor_location", "rider_notified_local_at",
                                             "estimated_pickup_arrival_local_at"])
    if dl.empty or "estimated_pickup_arrival_local_at" not in dl.columns or "rider_notified_local_at" not in dl.columns:
        return {}
    a = pd.to_datetime(dl["rider_notified_local_at"].str.slice(0, 19), errors="coerce")
    m = a >= a.max() - pd.Timedelta(days=28)
    dl, a = dl[m].copy(), a[m]
    b = pd.to_datetime(dl["estimated_pickup_arrival_local_at"].str.slice(0, 19), errors="coerce")
    dl["eta"] = (b - a).dt.total_seconds()
    dl = dl[(dl["eta"] > 0) & (dl["eta"] < 3600)]
    out = {}
    # por restaurante concreto (su ubicación): el nombre se repite en cadenas (McDonald's, DIA…)
    if "vendor_location" in dl.columns:
        k = dl["vendor_location"].map(lambda v: "%s,%s" % H.punto(v))
        for key, g in dl.groupby(k)["eta"]:
            if key != "None,None":
                out[key] = (int(round(g.median())), int(len(g)))
    return out


def construir_datos(cities, semana_label):
    """{rider: [[fecha, order_id, restaurante, aviso, reasignado, segundos, motivo, quien, lat, lon], ...]}"""
    import heatmaps_reasignaciones as H
    re_df, loc = H._cargar()
    ls_ = H._CACHE.get("loc_store", {})
    df = re_df[re_df["_city"].isin(set(cities))]
    df = df[df["_wkey"].map(lambda k: "W" + str(k[1])) == semana_label]
    try:
        eta = _eta_por_tienda(H)
    except Exception:
        eta = {}
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
        ] + list(eta.get("%s,%s" % (lat, lon)) or (None, 0)))
    return out


JS = r"""<script>
/* ==== Delivery Race · detalle de RR % (pedidos reasignados de la semana en curso) ==== */
(function(){
  const RRD=__RRDET__, SEM='__SEM__', LIM=__LIM__;
  /* fila: [fecha, pedido, tienda, aviso, reasignado, s_tardó, motivo, quién, auto, lat, lon, s_planeado, n_entregas] */
  const MET=new Set(['reassign','notSeen','ignored','decline','redispatch','cnm','agent']);
  const body=document.getElementById('ligaBody'), sel=document.getElementById('ligaMetricSel');
  if(!body||!sel) return;
  const css=document.createElement('style');
  css.textContent='td.trendwk.rrclick{cursor:pointer;text-decoration:underline dotted;text-underline-offset:3px}'+
   'td.trendwk.rrclick:hover{outline:1px solid #4FD1B4}'+
   '#rrOv{position:fixed;inset:0;background:rgba(0,0,0,.55);z-index:2147483000;display:none;align-items:center;justify-content:center}'+
   '#rrOv.on{display:flex}#rrBox{background:#161C24;color:#E9ECF1;border:1px solid #333F4D;border-radius:12px;width:min(1100px,96vw);height:94vh;max-height:94vh;display:flex;flex-direction:column;overflow:hidden}'+
   '#rrHd{display:flex;gap:10px;align-items:center;padding:12px 16px;border-bottom:1px solid #333F4D}#rrHd b{flex:1}#rrHd button{all:unset;cursor:pointer;padding:2px 8px;border:1px solid #333F4D;border-radius:6px}'+
   '#rrBd{display:flex;flex-direction:column;min-height:0;flex:1}'+
   '#rrList{overflow:auto;flex:0 1 auto;max-height:40%;border-bottom:1px solid #333F4D}#rrMap{flex:1 1 auto;min-height:220px}'+
   '#rrList table{width:100%;min-width:0;border-collapse:collapse;font-size:12.5px}#rrList th{position:sticky;top:0;background:#1B232D;color:#98A3B3;text-align:left;padding:7px 8px;font-weight:600;white-space:nowrap}'+
   '#rrList td{padding:5px 8px;border-top:1px solid #222B36;white-space:nowrap}#rrList td .cut{display:inline-block;max-width:230px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;vertical-align:bottom}#rrList td .cut.m{max-width:190px}#rrList tr.o{cursor:pointer}#rrList tr.o:hover td{background:#1D2733}#rrList tr.sel td{background:#203040}'+
   '.rrbar{display:inline-block;height:6px;border-radius:3px;vertical-align:middle;margin-left:6px}'+
   '@media(max-width:760px){#rrList{max-height:45%}}';
  document.head.appendChild(css);
  const ov=document.createElement('div'); ov.id='rrOv';
  ov.innerHTML='<div id="rrBox"><div id="rrHd"><b id="rrT"></b><span id="rrS" style="color:#98A3B3;font-size:12px"></span><span id="rrPwBox" style="display:none;font-size:12px;color:#98A3B3">Trazas: <input id="rrPw" type="password" placeholder="contraseña" style="width:110px;background:#0F141A;color:#E9ECF1;border:1px solid #333F4D;border-radius:6px;padding:3px 6px"> <button id="rrPwB">Ver paradas</button></span><span id="rrTz" style="font-size:12px"></span><button id="rrX">Cerrar</button></div>'+
    '<div id="rrBd"><div id="rrList"></div><div id="rrMap"></div></div>'+
    '<div style="padding:8px 16px;color:#98A3B3;font-size:11.5px;border-top:1px solid #333F4D">Fuente: reassignment_lv del bucket GCP de Glovo. «Tardó» = tiempo que tuvo el rider el pedido hasta la reasignación. «Planeado» = tiempo estimado por Glovo desde el aviso hasta la recogida en esa tienda (mediana de sus entregas de los últimos 28 días): el bucket no trae la estimación del rider al que se le reasignó, por eso se usa la de la tienda. El sistema reasigna solo a los '+LIM+' min un pedido parado en recogida. Paradas (con contraseña): posiciones de Live Operations del rider entre el aviso y la reasignación; <b style="color:#E5624D">●</b> no explicada = 3 min o más quieto a más de 100 m del restaurante, <b style="color:#8a94a3">●</b> en el restaurante. «Empieza a moverse» = primera posición a más de 80 m del punto donde recibió el aviso (○ en el mapa). Disponible desde el 22/10 a las 16:50 y cuando el bucket trae el día.</div></div>';
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

  // ---- trazas por pedido (pedidos_trazas.json cifrado; misma contraseña que el buscador de Paradas con pedido)
  let TENV=null, TDEC=null;
  const b64=s=>Uint8Array.from(atob(s),c=>c.charCodeAt(0));
  async function trazas(pw){
    if(TDEC) return TDEC;
    if(!TENV){ const r=await fetch(new URL('pedidos_trazas.json?t='+Date.now(),document.baseURI),{cache:'no-store'}); if(!r.ok) throw new Error('sin fichero de trazas'); TENV=await r.json(); }
    const km=await crypto.subtle.importKey('raw',new TextEncoder().encode(pw),'PBKDF2',false,['deriveKey']);
    const key=await crypto.subtle.deriveKey({name:'PBKDF2',salt:b64(TENV.salt),iterations:TENV.iter,hash:'SHA-256'},km,{name:'AES-GCM',length:256},false,['decrypt']);
    let raw; try{ raw=await crypto.subtle.decrypt({name:'AES-GCM',iv:b64(TENV.iv)},key,b64(TENV.data)); }catch(e){ throw new Error('contraseña incorrecta'); }
    const st=new Blob([raw]).stream().pipeThrough(new DecompressionStream('deflate'));
    TDEC=JSON.parse(await new Response(st).text()); try{ sessionStorage.setItem('pq_pw',pw); }catch(e){} return TDEC;
  }
  const hav=(a,b)=>{ const R=6371000,r=Math.PI/180,dl=(b[0]-a[0])*r,dn=(b[1]-a[1])*r; const h=Math.sin(dl/2)**2+Math.cos(a[0]*r)*Math.cos(b[0]*r)*Math.sin(dn/2)**2; return 2*R*Math.asin(Math.sqrt(h)); };
  function tramoDe(o,rid){ if(!TDEC) return null; const t=TDEC[o[1]]; if(!t) return null;
    const X=t.tramos.filter(x=>x.tipo==='X'); return X.find(x=>String(x.rider)===String(rid))||X[0]||null; }
  // primera muestra a más de 80 m de donde estaba al recibir el aviso -> empieza a moverse
  function arranque(o,tr){ if(!tr||!tr.pts||!tr.pts.length) return null;
    const P=tr.pts; let k=0; for(let i=0;i<P.length;i++){ if(P[i][0]<=0) k=i; }
    const ini=[P[k][1],P[k][2]];
    for(let i=k+1;i<P.length;i++){ if(hav(ini,[P[i][1],P[i][2]])>80){ const m=Math.max(0,P[i][0]);
      const t=(o[3]||tr.t0||'').split(':'); let h='';
      if(t.length===2){ const x=(+t[0])*60+(+t[1])+Math.round(m); h=String(Math.floor(x/60)%24).padStart(2,'0')+':'+String(x%60).padStart(2,'0'); }
      return {min:m,h:h,lat:P[i][1],lon:P[i][2]}; } }
    return {min:null}; }
  function paradas(o,tr){ const rest=(o[9]!=null)?[o[9],o[10]]:null;
    return (tr?tr.par:[]).map(p=>({lat:p[0],lon:p[1],h:p[2],min:p[3],local:rest?hav([p[0],p[1]],rest)<=100:!!p[4]})); }

  const dif=(r,p)=>(r==null||p==null)?'–':((r>=p?'+':'−')+mmss(Math.abs(r-p)));
  function popup(o){ const [f,oid,st,av,re,secs,mot,quien,auto,la,lo,plan,np]=o;
    return '<b>'+esc(st)+'</b><br>Pedido <b>'+esc(oid)+'</b> · '+ddmm(f)+'<br>'+
      'Aviso '+esc(av||'–')+' → reasignado '+esc(re||'–')+'<br>'+
      'Tardó el rider (hasta reasignar): <b>'+mmss(secs)+' min</b><br>'+
      'Planeado por Glovo hasta recogida: <b>'+(plan!=null?mmss(plan)+' min':'sin dato')+'</b>'+(plan!=null?' <span style="color:#666">(mediana de '+np+' entregas en la tienda)</span>':'')+'<br>'+
      'Diferencia: <b style="color:'+((secs!=null&&plan!=null&&secs>plan)?'#C0392B':'#1E7D3A')+'">'+dif(secs,plan)+' min</b><br>'+
      '<span style="color:#666">'+esc(mot)+' · '+esc(quien)+' · el sistema reasigna solo a los '+LIM+' min</span>'; }

  async function abrir(rid){
    const cnm=sel.value==='cnm';
    const L0=(RRD[rid]||[]).filter(o=>!cnm||o[8]||/no avanza/i.test(o[6]||''));
    document.getElementById('rrT').textContent='Rider '+rid+' · '+(cnm?'pedidos CNM (no avanza / parado en recogida) ':'pedidos reasignados ')+SEM;
    let pw=''; try{ pw=sessionStorage.getItem('pq_pw')||''; }catch(e){}
    if(!TDEC&&pw){ try{ await trazas(pw); }catch(e){} }
    document.getElementById('rrPwBox').style.display=TDEC?'none':'';
    const conTr=L0.filter(o=>tramoDe(o,rid)).length;
    document.getElementById('rrTz').innerHTML=TDEC?'<span style="color:#4FD1B4">'+conTr+' de '+L0.length+' con traza</span>':'';
    const tot=L0.length, med=tot?L0.reduce((a,o)=>a+(o[5]||0),0)/tot:0;
    document.getElementById('rrS').textContent=tot+' pedidos · media '+mmss(Math.round(med))+' min hasta reasignar';
    const lim=LIM*60;
    document.getElementById('rrList').innerHTML=tot?'<table><thead><tr><th>Día</th><th>Pedido</th><th>Restaurante</th><th>Aviso</th><th>Reasig.</th><th title="Tiempo planeado por Glovo desde el aviso hasta la recogida en esa tienda (mediana de sus entregas, últimos 28 días)">Planeado</th><th title="Tiempo que tuvo el rider el pedido hasta que se le reasignó">Tardó</th><th>Dif.</th><th title="Paradas de 3 min o más del rider entre el aviso y la reasignación, a más de 100 m del restaurante">Paradas</th><th title="Hora en que el rider se aleja más de 80 m de donde estaba al recibir el aviso (minutos desde el aviso). Glovo actualiza la ubicación cada ~5 min">Empieza a moverse</th><th>Motivo</th></tr></thead><tbody>'+
      L0.map((o,i)=>{ const s=o[5], pl=o[11]; const ref=pl!=null?pl:lim; const w=s!=null?Math.min(60,Math.round(s/ref*30)):0; const c=s==null?'#555':(s>ref?'#E5624D':'#3FB984');
        return '<tr class="o" data-i="'+i+'"><td>'+ddmm(o[0])+'</td><td style="font-family:ui-monospace,monospace">'+esc(o[1])+'</td><td title="'+esc(o[2])+'"><span class="cut">'+esc(o[2])+'</span></td><td>'+esc(o[3]||'–')+'</td><td>'+esc(o[4]||'–')+'</td>'+
          '<td>'+(pl!=null?mmss(pl):'–')+'</td><td><b>'+mmss(s)+'</b><span class="rrbar" style="width:'+w+'px;background:'+c+'"></span></td><td style="color:'+c+';font-weight:650">'+dif(s,pl)+'</td>'+(()=>{ const tr=tramoDe(o,rid); if(!TDEC) return '<td style="color:#555" title="Pon la contraseña arriba">🔒</td><td style="color:#555">🔒</td>'; if(!tr) return '<td style="color:#555" title="Sin traza (pedido anterior al 22/10 16:50 o sin posiciones)">–</td><td style="color:#555">–</td>'; const P=paradas(o,tr).filter(p=>!p.local); const A=arranque(o,tr); const ac=A.min==null?'<td style="color:#E5624D;font-weight:650" title="No se alejó más de 80 m del punto del aviso antes de la reasignación">no se movió</td>':'<td style="color:'+(A.min>5?'#E5624D':'#E9ECF1')+'"><b>'+(A.h||'–')+'</b> <span style="color:#98A3B3">+'+A.min.toFixed(0)+'′</span></td>';
          return '<td style="color:'+(P.length?'#E5624D':'#3FB984')+';font-weight:650">'+P.length+(P.length?' · '+P.reduce((a,p)=>a+p.min,0).toFixed(0)+'′':'')+'</td>'+ac; })()+'<td style="color:#98A3B3" title="'+esc(o[6])+' · '+esc(o[7])+'"><span class="cut m">'+esc(o[6])+'</span></td></tr>'; }).join('')+'</tbody></table>'
      :'<div style="padding:16px;color:#98A3B3">El bucket no trae pedidos '+(cnm?'CNM':'reasignados')+' de este rider en '+SEM+' (puede ir con un día de retraso respecto al RR %).</div>';
    ov.classList.add('on');
    let L; try{ L=await leaflet(); }catch(e){ document.getElementById('rrMap').innerHTML='<div style="padding:16px;color:#98A3B3">No se pudo cargar el mapa.</div>'; return; }
    if(!map){ map=L.map('rrMap',{zoomControl:true}); L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}',{maxZoom:19,attribution:'Tiles © Esri'}).addTo(map); }
    if(layer) layer.remove(); layer=L.layerGroup().addTo(map);
    const mk=[]; const pts=[];
    L0.forEach((o,i)=>{ const lat=o[9],lon=o[10]; if(lat==null||lon==null){ mk[i]=null; return; }
      const s=o[5], ref=o[11]!=null?o[11]:lim, c=s==null?'#888':(s>ref?'#E5624D':'#3FB984');
      const m=L.circleMarker([lat,lon],{radius:8,color:'#fff',weight:1.5,fillColor:c,fillOpacity:.9}).bindPopup(popup(o)).addTo(layer);
      m.on('click',()=>marcar(i)); mk[i]=m; pts.push([lat,lon]); });
    setTimeout(()=>{ map.invalidateSize(); if(pts.length) map.fitBounds(pts,{padding:[30,30],maxZoom:15}); else map.setView([40.2,-3.7],6); },60);
    function marcar(i){ document.querySelectorAll('#rrList tr.o').forEach(tr=>tr.classList.toggle('sel',+tr.dataset.i===i)); }
    let trLayer=null;
    function dibujar(i){
      if(trLayer){ trLayer.remove(); trLayer=null; }
      const o=L0[i], tr=tramoDe(o,rid); if(!tr) return false;
      trLayer=L.layerGroup().addTo(map); const pts=tr.pts.map(p=>[p[1],p[2]]);
      L.polyline(pts,{color:'#E8833A',weight:4,opacity:.85}).addTo(trLayer);
      tr.pts.forEach(p=>L.circleMarker([p[1],p[2]],{radius:2.5,color:'#E8833A',weight:1,fillOpacity:1}).bindTooltip('+'+p[0].toFixed(1)+' min desde el aviso').addTo(trLayer));
      if(pts.length) L.circleMarker(pts[0],{radius:6,color:'#fff',weight:2,fillColor:'#E8833A',fillOpacity:1}).bindTooltip('Posición al recibir el aviso ('+tr.t0+')').addTo(trLayer);
      const A=arranque(o,tr); if(A&&A.min!=null) L.circleMarker([A.lat,A.lon],{radius:6,color:'#E8833A',weight:3,fillColor:'#fff',fillOpacity:1}).bindTooltip('Empieza a moverse '+(A.h||'')+' (+'+A.min.toFixed(0)+' min desde el aviso)').addTo(trLayer);
      paradas(o,tr).forEach(p=>L.circleMarker([p.lat,p.lon],{radius:7+Math.min(14,p.min),color:'#fff',weight:1.5,fillColor:p.local?'#8a94a3':'#E5624D',fillOpacity:.85})
        .bindPopup('<b>'+(p.local?'Parada en el restaurante':'Parada no explicada')+'</b><br>'+p.min.toFixed(1)+' min quieto desde las '+p.h+'<br>Pedido '+esc(o[1])+' · rider '+esc(rid)).addTo(trLayer));
      const all=pts.concat(o[9]!=null?[[o[9],o[10]]]:[]); if(all.length) map.fitBounds(all,{padding:[40,40],maxZoom:17});
      return true;
    }
    document.querySelectorAll('#rrList tr.o').forEach(tr=>tr.onclick=()=>{ const i=+tr.dataset.i, m=mk[i]; marcar(i);
      if(dibujar(i)){ if(m) setTimeout(()=>m.openPopup(),400); return; }
      if(m){ map.flyTo(m.getLatLng(),16,{duration:.6}); setTimeout(()=>m.openPopup(),650); }
      else L.popup().setLatLng(map.getCenter()).setContent(popup(L0[i])+'<br><i>Sin ubicación del restaurante</i>').openOn(map); });
  }

  let ultimo=null;
  const pwGo=async()=>{ const v=document.getElementById('rrPw').value; if(!v) return;
    try{ TDEC=null; await trazas(v); if(ultimo) abrir(ultimo); }catch(e){ document.getElementById('rrTz').innerHTML='<span style="color:#E5624D">'+esc(e.message)+'</span>'; } };
  document.getElementById('rrPwB').addEventListener('click',pwGo);
  document.getElementById('rrPw').addEventListener('keydown',e=>{ if(e.key==='Enter') pwGo(); });

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
    const r=td.parentElement.querySelector('td.rider'); if(r){ ultimo=r.textContent.trim(); abrir(ultimo); } });
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
