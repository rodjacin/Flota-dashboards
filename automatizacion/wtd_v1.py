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
import os, csv, json, datetime as dt

NODE_ALIASES = {"NEM": "MAD"}
DELIV_CSV = os.path.expanduser("~/Downloads/fleet_data_combinado/delivery_lv_combinado.csv")
WP_DIAS = 56          # días de pedidos que se analizan (8 semanas)


def _ts(v):
    try:
        return dt.datetime.fromisoformat(str(v).strip()[:19])
    except Exception:
        return None


def _f(v):
    try:
        return float(v)
    except Exception:
        return None


def wtd_pedidos(cities):
    """WTD>10′ pedido a pedido (bucket delivery_lv, llega con 1 día de retraso).
    espera = llegada a la puerta (rider_near_customer_at) -> marcado entregado (rider_dropped_off_local_at).
    Esperado por rider = probabilidad de WTD>10′ de pedidos parecidos (misma área, tramo de distancia
    restaurante->cliente y de peso) en el periodo; índice = real ÷ esperado."""
    if not os.path.isfile(DELIV_CSV):
        return None
    cs = set(cities)
    hoy = dt.date.today()
    desde = (hoy - dt.timedelta(days=WP_DIAS)).isoformat()
    P = []
    with open(DELIV_CSV, encoding="utf-8-sig") as fh:
        for x in csv.DictReader(fh):
            if (x.get("delivery_status") or "") != "completed":
                continue
            c = NODE_ALIASES.get((x.get("city_code") or "").strip(), (x.get("city_code") or "").strip())
            f = (x.get("fecha") or "")[:10]
            if c not in cs or f < desde:
                continue
            a, b = _ts(x.get("rider_near_customer_at")), _ts(x.get("rider_dropped_off_local_at"))
            if not a or not b:
                continue
            w = (b - a).total_seconds() / 60
            if w < 0 or w > 180:
                continue
            ca = (x.get("is_contact_customer_absent") or "").strip().lower()
            d = _f(x.get("pd_distance_google_km")) or _f(x.get("pd_distance_manhattan_km"))
            kg = _f(x.get("total_weight"))
            P.append((str(x.get("rider_id") or "").strip(), c, f, w, "S" if ca == "true" else ("N" if ca == "false" else ""),
                      d, kg if kg and kg > 0 else None, a, b, x.get("store_name") or "", str(x.get("order_id") or "")))
    if not P:
        return None
    pesos = sorted(p[6] for p in P if p[6])
    t1 = pesos[len(pesos) // 3] if pesos else 0
    t2 = pesos[2 * len(pesos) // 3] if pesos else 0
    def dband(d):
        if d is None: return 9
        return 0 if d < 1 else 1 if d < 2 else 2 if d < 3 else 3 if d < 5 else 4
    def wband(k):
        if not k: return 0
        return 1 if k <= t1 else 2 if k <= t2 else 3
    tot = {}
    for p in P:
        k = (p[1], dband(p[5]), wband(p[6]))
        t = tot.setdefault(k, [0, 0]); t[0] += 1; t[1] += p[3] > 10
    city_rate = {}
    for (c, _, _), (n, n10) in tot.items():
        z = city_rate.setdefault(c, [0, 0]); z[0] += n; z[1] += n10
    def prob(p):
        n, n10 = tot[(p[1], dband(p[5]), wband(p[6]))]
        if n >= 30:
            return n10 / n
        cn, c10 = city_rate[p[1]]
        return (n10 + 30 * c10 / cn) / (n + 30)          # suavizado hacia la media del área
    AG, DET = {}, []
    for p in P:
        k = (p[0], p[1], p[2])
        g = AG.setdefault(k, [0, 0, 0, 0, 0, 0.0, 0.0, 0.0, 0, 0.0, 0])
        # n, n10, n10 con contacto, n10 sin contacto, n10 sin dato, esperado, suma espera, suma km, n km, suma kg, n kg
        g[0] += 1; g[5] += prob(p); g[6] += p[3]
        if p[5] is not None: g[7] += p[5]; g[8] += 1
        if p[6]: g[9] += p[6]; g[10] += 1
        if p[3] > 10:
            g[1] += 1
            g[2 if p[4] == "S" else 3 if p[4] == "N" else 4] += 1
            DET.append([p[2], p[0], p[1], p[7].strftime("%H:%M"), p[8].strftime("%H:%M"), round(p[3], 1), p[4],
                        None if p[5] is None else round(p[5], 2), None if not p[6] else round(p[6], 1), p[9], p[10]])
    ag = [[k[0], k[1], k[2], g[0], g[1], g[2], g[3], g[4], round(g[5], 3), round(g[6], 1), round(g[7], 2), g[8], round(g[9], 1), g[10]]
          for k, g in AG.items()]
    DET.sort(key=lambda r: (r[0], r[3]), reverse=True)
    return {"hasta": max(p[2] for p in P), "desde": min(p[2] for p in P), "ag": ag, "det": DET,
            "contacto_desde": min((p[2] for p in P if p[4]), default=None)}


PP_DIAS = 28          # días del histórico de paradas con pedido que se clasifican
PP_TOL_MIN = 5        # holgura (min) alrededor de la ventana en la puerta: la posición llega cada ~5 min


def _hist_pp(cities):
    """Lee <dashboard>/wtd_pp_hist.json (lo escribe el muestreo) del repo."""
    import posiciones
    cs = set(cities)
    carpeta = next((k for k, v in posiciones.DASHBOARDS.items() if set(NODE_ALIASES.get(c, c) for c in v) == cs), None)
    if not carpeta:
        return []
    for repo in (os.environ.get("GITHUB_WORKSPACE"), os.path.expanduser("~/flota-dashboards")):
        p = os.path.join(repo or "", carpeta, posiciones.HIST_PP)
        if repo and os.path.isfile(p):
            try:
                return json.load(open(p, encoding="utf-8")).get("eps") or []
            except Exception:
                return []
    return []


def clasificar_pp(cities, eps=None, deliv_csv=None):
    """Cruza cada parada con pedido (rider, desde, hasta en minutos epoch UTC) con las entregas
    de delivery_lv del mismo rider: si la parada cae en la ventana en la que el rider estaba en la
    puerta del cliente (rider_near_customer_at -> rider_dropped_off_local_at, hora de Madrid, con
    PP_TOL_MIN de holgura) al menos la mitad de su duración, la parada fue «en la puerta del cliente».
    Fila: [rider, área, desde, hasta, min, clase, espera_puerta_min, pedido, tienda]
    clase: 'P' en la puerta del cliente · 'F' fuera de la puerta · 'N' pendiente (aún sin delivery_lv)."""
    from zoneinfo import ZoneInfo
    eps = _hist_pp(cities) if eps is None else eps
    deliv_csv = deliv_csv or DELIV_CSV
    if not eps:
        return {"rows": [], "hasta": None}
    lim = int(dt.datetime.now(dt.timezone.utc).timestamp() // 60) - PP_DIAS * 1440
    eps = [e for e in eps if e[2] >= lim]
    riders = {str(e[0]) for e in eps}
    mad = ZoneInfo("Europe/Madrid")
    def utc_min(t):
        return int(t.replace(tzinfo=mad).timestamp() // 60)
    def dia_local(m):
        return dt.datetime.fromtimestamp(m * 60, mad).date().isoformat()
    desde_dia = (dt.datetime.fromtimestamp(min(e[2] for e in eps) * 60, mad).date() - dt.timedelta(days=1)).isoformat()
    puertas, hasta = {}, None
    if os.path.isfile(deliv_csv):
        with open(deliv_csv, encoding="utf-8-sig") as fh:
            for x in csv.DictReader(fh):
                f = (x.get("fecha") or "")[:10]
                if f and (hasta is None or f > hasta):
                    hasta = f
                rid = str(x.get("rider_id") or "").strip()
                if rid not in riders or f < desde_dia:
                    continue
                a, b = _ts(x.get("rider_near_customer_at")), _ts(x.get("rider_dropped_off_local_at"))
                if not a or not b or b < a:
                    continue
                puertas.setdefault(rid, []).append((utc_min(a), utc_min(b), str(x.get("order_id") or ""),
                                                    x.get("store_name") or ""))
    rows = []
    for e in eps:
        rid, area, d0, d1, mn = str(e[0]), e[1], e[2], e[3], e[4]
        dur = max(d1 - d0, 1)
        best = None
        for a, b, oid, tienda in puertas.get(rid, []):
            ov = min(d1, b + PP_TOL_MIN) - max(d0, a - PP_TOL_MIN)
            if ov >= dur * 0.5 and (best is None or ov > best[0]):
                best = (ov, b - a, oid, tienda)
        if best:
            rows.append([rid, area, d0, d1, mn, "P", best[1], best[2], best[3]])
        elif hasta and dia_local(d0) <= hasta:
            rows.append([rid, area, d0, d1, mn, "F", None, "", ""])
        else:
            rows.append([rid, area, d0, d1, mn, "N", None, "", ""])
    return {"rows": rows, "hasta": hasta}


def construir_html(cities=None, semanas=None, sello=True):
    import posiciones
    cities = sorted(set(NODE_ALIASES.get(c, c) for c in (cities or [])))
    nombres, aviso, foto, paradas = {}, "", None, {}
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
        paradas, foto = posiciones.quietos(cities, grid)
        ahora_te, eps = posiciones.tras_entrega(cities, grid)
    except Exception as e:
        aviso = (aviso + " · " if aviso else "") + "No se pudo calcular la parada tras entrega: " + str(e)[:200]
    if not foto and not aviso:
        aviso = "Sin posiciones recientes de Live Operations: la pestaña se rellenará con el muestreo de cada ~10 min."
    try:
        wp = wtd_pedidos(cities)
    except Exception as e:
        wp = None; print("  (aviso) WTD por pedido: " + str(e)[:200])
    try:
        pph = clasificar_pp(cities)
    except Exception as e:
        pph = {"rows": [], "hasta": None}; print("  (aviso) paradas con pedido en puerta: " + str(e)[:200])
    data = {"cities": cities, "foto": foto, "aviso": aviso, "umbral": posiciones.TRAS_UMBRAL_MIN, "wp": wp, "pph": pph,
            "horas": posiciones.KEEP_HOURS, "tras_entrega": ahora_te, "episodios": eps,
            "paradas": {k: v for k, v in (paradas or {}).items() if v.get("estado") == "parado"},
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
          "  setTimeout(()=>{ if(!loaded){ fr.srcdoc=V1_HTML; loaded=true; } },1500);  // avisos activos desde que se abre el dashboard\n"
          "})();\n</script>\n" + _ALERT_JS)
    i = dash_html.rindex("</body>")
    return dash_html[:i] + js + dash_html[i:]


# Pop-up en la página principal (fuera del iframe, para que se vea aunque se haga scroll):
# la pestaña WTD% v1 envía {v1Alert:{nuevos, activos}} cada minuto; aquí se muestra el aviso,
# suena un pitido y, si se activan, salta una notificación del navegador con la pestaña en segundo plano.
_ALERT_JS = r'''<style>
#v1Alert{position:fixed;right:16px;bottom:16px;z-index:9999;width:340px;max-width:calc(100vw - 32px);background:#fff;color:#14171F;
  border:1px solid #F1B8B3;border-left:5px solid #C2362F;border-radius:12px;box-shadow:0 10px 30px rgba(0,0,0,.22);
  font:13px/1.45 Inter,-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;display:none}
#v1Alert.on{display:block;animation:v1In .25s ease-out}
@keyframes v1In{from{transform:translateY(12px);opacity:0}to{transform:none;opacity:1}}
#v1Alert .hd{display:flex;align-items:center;gap:8px;padding:11px 12px 6px 12px}
#v1Alert .hd b{font-size:14px;flex:1}
#v1Alert .x{border:0;background:transparent;font-size:18px;line-height:1;cursor:pointer;color:#6B7280;padding:2px 4px}
#v1Alert ul{list-style:none;margin:0;padding:0 12px;max-height:260px;overflow:auto}
#v1Alert li{display:flex;justify-content:space-between;gap:8px;padding:7px 0;border-top:1px solid #EEF1F4}
#v1Alert li span{color:#6B7280;font-size:12px;display:block}
#v1Alert li i{font-style:normal;font-family:ui-monospace,"SF Mono",Menlo,monospace;font-weight:700;color:#8A5A00;white-space:nowrap}
#v1Alert li i.d{color:#C2362F}
#v1Alert li.nw{background:#FFF4F3}
#v1Alert .ft{display:flex;gap:8px;flex-wrap:wrap;padding:10px 12px 12px}
#v1Alert .ft button{font:inherit;font-size:12px;border:1px solid #E4E7EC;background:#F6F7F9;color:#14171F;border-radius:8px;padding:6px 10px;cursor:pointer}
#v1Alert .ft button.p{background:#C2362F;border-color:#C2362F;color:#fff}
</style>
<div id="v1Alert" role="alertdialog" aria-live="assertive" aria-labelledby="v1AlertT">
  <div class="hd"><b id="v1AlertT">Rider parado con pedido</b><button class="x" id="v1AlertX" aria-label="Cerrar">×</button></div>
  <ul id="v1AlertL"></ul>
  <div class="ft"><button class="p" id="v1AlertVer">Ver en WTD% v1</button><button id="v1AlertSnd"></button><button id="v1AlertNot"></button></div>
</div>
<script>
/* ==== Pop-up WTD% v1: riders parados tras entregar ==== */
(function(){
  const box=document.getElementById('v1Alert'),L=document.getElementById('v1AlertL');
  const fr=document.getElementById('wtdV1Frame'); if(!box||!fr) return;
  const T0=document.title; let act=[],nuevosIds=new Set(),U=5,cerrado=false;
  let sonido=true; try{sonido=localStorage.getItem('wtdv1_sonido')!=='0';}catch(e){}
  const esc=s=>String(s??'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
  const dur=s=>{s=Math.max(0,Math.floor(s));return Math.floor(s/60)+':'+String(s%60).padStart(2,'0');};
  const hhmm=s=>new Date(s).toLocaleTimeString('es-ES',{timeZone:'Europe/Madrid',hour:'2-digit',minute:'2-digit'});
  function botones(){
    document.getElementById('v1AlertSnd').textContent=sonido?'🔔 Sonido activado':'🔕 Sonido desactivado';
    const n=document.getElementById('v1AlertNot');
    if(!('Notification' in window)){n.style.display='none';return;}
    n.textContent=Notification.permission==='granted'?'Notificaciones activadas':(Notification.permission==='denied'?'Notificaciones bloqueadas':'Activar avisos en el escritorio');
    n.disabled=Notification.permission!=='default';}
  function pitar(){ if(!sonido) return; try{const C=window.AudioContext||window.webkitAudioContext;const a=new C();
    [0,0.28].forEach(t=>{const o=a.createOscillator(),g=a.createGain();o.type='sine';o.frequency.value=880;o.connect(g);g.connect(a.destination);
      g.gain.setValueAtTime(0.0001,a.currentTime+t);g.gain.exponentialRampToValueAtTime(0.25,a.currentTime+t+0.02);g.gain.exponentialRampToValueAtTime(0.0001,a.currentTime+t+0.22);
      o.start(a.currentTime+t);o.stop(a.currentTime+t+0.24);});setTimeout(()=>a.close(),1200);}catch(e){} }
  function pintar(){
    if(!act.length){box.classList.remove('on');document.title=T0;return;}
    document.getElementById('v1AlertT').textContent=act.length===1?'1 rider parado ≥'+U+' min con pedido':act.length+' riders parados ≥'+U+' min con pedido';
    act.sort((a,b)=>new Date(a.desde)-new Date(b.desde));
    L.innerHTML=act.map(r=>{const s=(Date.now()-new Date(r.desde).getTime())/1000;
      return `<li class="${nuevosIds.has(r.rid)?'nw':''}"><div><b>${esc(r.name||r.rid)}</b><span>${esc(r.rid)} · ${esc(r.city)} · ${r.txt?esc(r.txt):'entregó entre '+hhmm(r.ent_ini)+' y '+hhmm(r.ent_fin)}</span></div><i class="${s>=U*120?'d':''}" data-desde="${esc(r.desde)}">≥ ${dur(s)}</i></li>`;}).join('');
    document.title='('+act.length+') ⚠ Parados · '+T0;
    if(!cerrado) box.classList.add('on');}
  window.addEventListener('message',e=>{
    if(e.source!==fr.contentWindow||!e.data||!e.data.v1Alert) return;
    const m=e.data.v1Alert; U=m.umbral||U; act=m.activos||[];
    if((m.nuevos||[]).length){ nuevosIds=new Set(m.nuevos.map(r=>r.rid)); cerrado=false; pitar();
      if('Notification' in window&&Notification.permission==='granted'){
        try{const n=new Notification(m.nuevos.length===1?'Rider parado con pedido asignado':m.nuevos.length+' riders parados con pedido asignado',
          {body:m.nuevos.map(r=>(r.name||r.rid)+' ('+r.city+') · ≥'+(r.nivel===2?U*2:U)+' min parado con pedido').join('\n'),tag:'wtdv1-'+Date.now(),requireInteraction:true});
          n.onclick=()=>{window.focus();document.getElementById('v1AlertVer').click();n.close();};}catch(err){} } }
    pintar();});
  setInterval(()=>box.querySelectorAll('i[data-desde]').forEach(el=>{const s=(Date.now()-new Date(el.dataset.desde).getTime())/1000;
    el.textContent='≥ '+dur(s);el.classList.toggle('d',s>=U*120);}),1000);
  document.getElementById('v1AlertX').onclick=()=>{cerrado=true;box.classList.remove('on');};
  document.getElementById('v1AlertVer').onclick=()=>{const b=document.querySelector('#viewSeg button[data-v="wtdv1"]');
    if(b&&b.getAttribute('aria-pressed')!=='true') b.click(); setTimeout(()=>{fr.scrollIntoView({behavior:'smooth'});try{const t=fr.contentDocument.getElementById('secPP');if(t)window.scrollTo({top:fr.getBoundingClientRect().top+window.scrollY+t.offsetTop-10,behavior:'smooth'});}catch(e){}},80);};
  document.getElementById('v1AlertSnd').onclick=()=>{sonido=!sonido;try{localStorage.setItem('wtdv1_sonido',sonido?'1':'0');}catch(e){}botones();if(sonido)pitar();};
  document.getElementById('v1AlertNot').onclick=()=>{try{Notification.requestPermission().then(botones);}catch(e){}};
  // el navegador solo deja pedir permiso tras un clic: se pide con el primer clic en cualquier parte del dashboard
  document.addEventListener('click',function pedir(){ document.removeEventListener('click',pedir,true);
    try{ if('Notification' in window&&Notification.permission==='default') Notification.requestPermission().then(botones); }catch(e){} },true);
  botones();
})();
</script>
<style>
#lateAlert{position:fixed;right:16px;bottom:16px;z-index:9998;width:340px;max-width:calc(100vw - 32px);background:#fff;color:#14171F;
  border:1px solid #F3D9A4;border-left:5px solid #B7791F;border-radius:12px;box-shadow:0 10px 30px rgba(0,0,0,.22);
  font:13px/1.45 Inter,-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;display:none}
#lateAlert.on{display:block;animation:v1In .25s ease-out}
#lateAlert .hd{display:flex;align-items:center;gap:8px;padding:11px 12px 6px 12px}
#lateAlert .hd b{font-size:14px;flex:1}
#lateAlert .x{border:0;background:transparent;font-size:18px;line-height:1;cursor:pointer;color:#6B7280;padding:2px 4px}
#lateAlert ul{list-style:none;margin:0;padding:0 12px;max-height:220px;overflow:auto}
#lateAlert li{display:flex;justify-content:space-between;gap:8px;padding:7px 0;border-top:1px solid #EEF1F4}
#lateAlert li span{color:#6B7280;font-size:12px;display:block}
#lateAlert li i{font-style:normal;font-family:ui-monospace,"SF Mono",Menlo,monospace;font-weight:700;color:#8A5A00;white-space:nowrap}
#lateAlert li i.d{color:#C2362F}
#lateAlert li.nw{background:#FFF8EB}
#lateAlert .ft{display:flex;gap:8px;flex-wrap:wrap;padding:10px 12px 12px}
#lateAlert .ft button{font:inherit;font-size:12px;border:1px solid #E4E7EC;background:#F6F7F9;color:#14171F;border-radius:8px;padding:6px 10px;cursor:pointer}
#lateAlert .ft button.p{background:#B7791F;border-color:#B7791F;color:#fff}
</style>
<div id="lateAlert" role="alertdialog" aria-live="assertive" aria-labelledby="lateAlertT">
  <div class="hd"><b id="lateAlertT">Rider sin conectar a su turno</b><button class="x" id="lateAlertX" aria-label="Cerrar">×</button></div>
  <ul id="lateAlertL"></ul>
  <div class="ft"><button class="p" id="lateAlertVer">Ver en En vivo</button></div>
</div>
<script>
/* ==== Pop-up: riders con el turno empezado y sin conectar (estado «late») ====
   La pestaña WTD% v1 envía {lateAlert:{nuevos, activos}} con cada muestra (cada minuto).
   Sonido y notificaciones usan los mismos ajustes que el aviso de parados. */
(function(){
  const box=document.getElementById('lateAlert'),L=document.getElementById('lateAlertL'),v1=document.getElementById('v1Alert');
  const fr=document.getElementById('wtdV1Frame'); if(!box||!fr) return;
  let act=[],nuevosIds=new Set(),cerrado=false;
  const esc=s=>String(s??'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
  const dur=s=>{s=Math.max(0,Math.floor(s));return Math.floor(s/60)+':'+String(s%60).padStart(2,'0');};
  const hhmm=s=>s?new Date(s).toLocaleTimeString('es-ES',{timeZone:'Europe/Madrid',hour:'2-digit',minute:'2-digit'}):'—';
  const sonido=()=>{try{return localStorage.getItem('wtdv1_sonido')!=='0';}catch(e){return true;}};
  function pitar(){ if(!sonido()) return; try{const C=window.AudioContext||window.webkitAudioContext;const a=new C();
    [0,0.22,0.44].forEach(t=>{const o=a.createOscillator(),g=a.createGain();o.type='triangle';o.frequency.value=660;o.connect(g);g.connect(a.destination);
      g.gain.setValueAtTime(0.0001,a.currentTime+t);g.gain.exponentialRampToValueAtTime(0.22,a.currentTime+t+0.02);g.gain.exponentialRampToValueAtTime(0.0001,a.currentTime+t+0.16);
      o.start(a.currentTime+t);o.stop(a.currentTime+t+0.18);});setTimeout(()=>a.close(),1200);}catch(e){} }
  // si el aviso de parados también está abierto, este se coloca encima para no taparlo
  function colocar(){ box.style.bottom=(v1&&v1.classList.contains('on')?v1.offsetHeight+28:16)+'px'; }
  function pintar(){
    if(!act.length){box.classList.remove('on');return;}
    document.getElementById('lateAlertT').textContent=act.length===1?'1 rider sin conectar a su turno':act.length+' riders sin conectar a su turno';
    act.sort((a,b)=>String(a.ini).localeCompare(String(b.ini)));
    L.innerHTML=act.map(r=>{const s=(Date.now()-new Date(r.ini).getTime())/1000;
      return `<li class="${nuevosIds.has(r.rid)?'nw':''}"><div><b>${esc(r.name||r.rid)}</b><span>${esc(r.rid)} · ${esc(r.city)} · turno ${hhmm(r.ini)}–${hhmm(r.fin)}${r.sp?' · '+esc(r.sp):''}</span></div><i class="${s>=900?'d':''}" data-ini="${esc(r.ini)}" title="Tiempo desde el inicio del turno">+${dur(s)}</i></li>`;}).join('');
    if(!cerrado) box.classList.add('on');
    colocar();}
  window.addEventListener('message',e=>{
    if(e.source!==fr.contentWindow||!e.data||!e.data.lateAlert) return;
    const m=e.data.lateAlert; act=m.activos||[];
    if((m.nuevos||[]).length){ nuevosIds=new Set(m.nuevos.map(r=>r.rid)); cerrado=false; pitar();
      if('Notification' in window&&Notification.permission==='granted'){
        try{const n=new Notification(m.nuevos.length===1?'Rider sin conectar a su turno':m.nuevos.length+' riders sin conectar a su turno',
          {body:m.nuevos.map(r=>(r.name||r.rid)+' ('+r.city+') · turno desde las '+hhmm(r.ini)).join('\n'),tag:'late-'+Date.now(),requireInteraction:true});
          n.onclick=()=>{window.focus();document.getElementById('lateAlertVer').click();n.close();};}catch(err){} } }
    pintar();});
  setInterval(()=>{box.querySelectorAll('i[data-ini]').forEach(el=>{const s=(Date.now()-new Date(el.dataset.ini).getTime())/1000;
    el.textContent='+'+dur(s);el.classList.toggle('d',s>=900);}); if(box.classList.contains('on')) colocar();},1000);
  document.getElementById('lateAlertX').onclick=()=>{cerrado=true;box.classList.remove('on');};
  document.getElementById('lateAlertVer').onclick=()=>{const b=document.querySelector('#viewSeg button[data-v="envivo"]');
    if(b){ if(b.getAttribute('aria-pressed')!=='true') b.click(); window.scrollTo({top:0,behavior:'smooth'}); }};
})();
</script>
'''


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
.pill.ok2{background:#E7F6EC;color:var(--good);font-weight:600}
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
  <section class="panel" id="secPP"><div class="ph"><h2 data-def="Riders que en la última muestra llevan al menos el umbral sin moverse (menos de 80 m) con un pedido asignado, fuera de un restaurante (sin contar GPS congelado). Son los que saltan en el aviso emergente.">Ahora · parados con pedido asignado</h2><p id="cntP"></p></div>
    <div class="tw" style="max-height:420px"><table id="tP"></table></div></section>
  <section class="panel" id="secPPH">
    <div class="hhead"><div><h2 data-def="Paradas con pedido asignado ya terminadas, cruzadas con los datos de entregas de Glovo (delivery_lv, llegan con 1 día de retraso). «En la puerta del cliente» = la parada coincide con el tiempo entre que el rider llegó a la dirección del cliente y marcó la entrega (espera del WTD). «Fuera de la puerta» = el rider estaba parado con el pedido en otro sitio.">Histórico · ¿parados con pedido en la puerta del cliente?</h2><p class="sub" id="phSub" style="margin-top:4px"></p></div>
      <div class="hfil"><div class="fg"><span>Fecha</span><select id="phDay" aria-label="Fecha"></select></div></div></div>
    <div class="seg" id="phCls" style="margin:6px 0 10px"></div>
    <section class="kpis" id="phKpis"></section>
    <div class="tw" style="max-height:520px"><table id="tPH"></table></div></section>
  <section class="panel"><div class="ph"><h2 data-def="Riders que en la última muestra siguen sin moverse (menos de 80 m) y sin pedido desde que entregaron su último pedido.">Ahora · parados tras su última entrega</h2><p id="cntA"></p></div>
    <div class="tw" style="max-height:520px"><table id="tA"></table></div></section>
  <section class="panel"><div class="ph"><h2 id="hE" data-def="Cada vez que hoy (día operativo desde las 05:00) un rider entregó un pedido y se quedó parado al menos una muestra (~5 min) en el mismo punto sin coger otro pedido.">Paradas tras entrega</h2><p id="cntE"></p></div>
    <div class="tw" style="max-height:700px"><table id="tE"></table></div></section>
  <section class="panel" id="wp">
    <div class="hhead"><div><h2 data-def="Análisis pedido a pedido con los datos del bucket de Glovo (llegan con 1 día de retraso). Espera en cliente = desde que el rider llega a la puerta hasta que marca el pedido como entregado.">WTD&gt;10′ por pedido · ¿espera del cliente o del rider?</h2><p class="sub" id="wpSub" style="margin-top:4px"></p></div>
      <div class="hfil">
        <div class="fg"><span>Semana</span><select id="wpWk" aria-label="Semana"></select></div>
        <div class="fg"><span>Fecha</span><select id="wpDay" aria-label="Fecha"></select></div>
      </div></div>
    <section class="kpis" id="wpKpis"></section>
    <div class="ph"><h2 data-def="Índice = WTD>10′ real ÷ esperado. El esperado es la tasa de WTD>10′ de pedidos parecidos (misma área, mismo tramo de distancia restaurante→cliente y de peso). Índice >1,3 en rojo: el rider espera más de lo que justifican sus repartos; <0,8 en verde.">Riders · WTD&gt;10′ ajustado por distancia y peso</h2><p id="wpCntR"></p></div>
    <div class="tw" style="max-height:480px"><table id="wpR"></table></div>
    <div class="ph"><h2 data-def="Cada pedido con más de 10 min entre la llegada a la puerta y el marcado de entrega (los 600 más recientes del filtro).">Pedidos con WTD&gt;10′</h2><p id="wpCntE"></p></div>
    <div class="tw" style="max-height:480px"><table id="wpE"></table></div>
  </section>
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
  $('sub').textContent='Una entrega se detecta cuando el pedido activo desaparece entre dos muestras de Live Operations y sube el contador de entregas completadas; desde ahí se mide cuánto sigue el rider en el mismo punto sin otro pedido.'+(D.foto?' Última muestra a las '+hhmm(D.foto)+' (hora de Madrid) · muestras cada minuto; Glovo actualiza la ubicación de cada rider cada ~5 min.':'');
  $('banner').hidden=!D.aviso;$('banner').textContent=D.aviso||'';
  $('hE').textContent='Paradas tras entrega · hoy desde las 05:00';}
cabecera();
function aplicarVivo(j){
  if(!j||!j.foto||!j.episodios)return;
  if(D.foto&&j.foto<D.foto)return;
  D.foto=j.foto;D.aviso='';D.tras_entrega=j.tras_entrega||{};D.episodios=j.episodios||[];
  if(Array.isArray(j.retrasos)){D.retrasos=j.retrasos;D.retrasos_foto=j.retrasos_foto||j.foto;}
  D.paradas=Object.fromEntries(Object.entries(j.paradas||{}).filter(([k,v])=>v&&v.estado==='parado'));
  Object.assign(D.riders,j.riders||{});cabecera();render();}
/* Datos en vivo: primero la rama «vivo» del repositorio (una muestra por minuto, un fichero por minuto
   para esquivar la caché de 5 min de raw.githubusercontent); si no está, el wtd_vivo.json de la web (cada ~10 min). */
const RAW_VIVO='https://raw.githubusercontent.com/rodjacin/Flota-dashboards/vivo/';
const CARPETA=(()=>{try{const s=new URL(document.baseURI).pathname.split('/').filter(x=>x&&!/\.html?$/i.test(x));return s[s.length-1]||'';}catch(e){return '';}})();
let vivoM=0;
async function cargarRapido(){
  if(!/^(sab|gra-mad-nom-alc)$/.test(CARPETA)||!window.fetch) return false;
  const now=Date.now(),M=Math.floor(now/60000),k0=(now%60000)<25000?1:0;   // el minuto en curso se publica a los ~15 s
  for(let k=k0;k<9;k++){const m=M-k; if(m<=vivoM) return true;
    try{const r=await fetch(RAW_VIVO+CARPETA+'/m/'+m+'.json'); if(r.ok){const j=await r.json(); vivoM=m; aplicarVivo(j); return true;}}catch(e){return false;}}
  return false;}
function cargarWeb(){try{fetch(new URL('wtd_vivo.json?t='+Date.now(),document.baseURI),{cache:'no-store'}).then(r=>r.ok?r.json():null).then(aplicarVivo).catch(()=>{});}catch(e){}}
function cargarVivo(){cargarRapido().then(ok=>{if(!ok)cargarWeb();}).catch(cargarWeb);}
$('nota').innerHTML='Cómo se calcula: se toma una muestra de posición y pedidos de cada rider cada minuto y llega a esta pestaña en 1–2 min (Glovo actualiza la ubicación de cada rider cada ~5 min, así que una parada se confirma cuando dos ubicaciones seguidas están en el mismo punto). Si entre dos muestras desaparece su pedido activo, se queda sin pedido y sube su contador de entregas completadas, cuenta como <b>entrega</b> (si desaparece sin sumar entrega, es cancelación o reasignación y no se cuenta). '+
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
const vivo=e=>e.en_curso&&e.conf!==false&&D.foto&&Math.abs(new Date(e.hasta)-new Date(D.foto))<90000&&(Date.now()-new Date(e.hasta).getTime())<STALE_MIN*60000;  // sigue en la última foto
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
  if(typeof renderWP==='function')renderWP();
  renderPP();
  renderPPH();
  revisarAlertas();
}
/* ===== Parados con pedido asignado (estado «parado» de la foto: quieto <80 m con pedido activo, fuera de restaurante) ===== */
D.paradas=D.paradas||{};
const SP={k:'min',d:-1};
const ciudadR=rid=>(D.riders[rid]||[])[1]||'';
// confirmado = quieto en al menos dos fotos seguidas (con una sola foto no se sabe si estaba parado o pasando)
const pConf=p=>p.conf!==undefined?!!p.conf:!!(p.t&&p.desde&&(new Date(p.t)-new Date(p.desde))>=4*60000);
const pVivo=p=>!!(pConf(p)&&D.foto&&Math.abs(new Date(p.t)-new Date(D.foto))<90000&&(Date.now()-new Date(p.t).getTime())<STALE_MIN*60000);
const pSec=p=>pVivo(p)?Math.max(0,(Date.now()-new Date(p.desde).getTime())/1000):(p.min||0)*60;
function conPedido(){return Object.entries(D.paradas).map(([rid,p])=>({rid,city:ciudadR(rid),...p}))
  .filter(p=>p.estado==='parado'&&!p.gps_viejo&&pVivo(p)&&pSec(p)/60>=U&&D.cities.includes(p.city)&&(S.city==='ALL'||p.city===S.city)&&
    (!S.q||String(p.rid).includes(S.q)||nombre(p.rid).toLowerCase().includes(S.q)));}
const CP=[CA[0],CA[1],
 {k:'desde',h:'Parado desde',v:p=>p.desde,f:p=>hhmm(p.desde)+(p.desde_inicio?'<span class="sub2">o antes</span>':''),d:'Primera muestra en la que ya estaba quieto en ese punto con el pedido.'},
 {k:'min',h:'Parado con pedido (en vivo)',n:1,v:p=>pSec(p),f:p=>{const m=pSec(p)/60,c=m>=U*2?'alert':'mid';return `<span class="pill ${c} live" data-desde="${p.desde}"><span class="dot"></span>≥ ${fmtDur(pSec(p))}</span><span class="sub2">última foto ${hhmm(p.t)}</span>`;},d:'Tiempo quieto con un pedido asignado, en vivo desde la primera muestra parado. Es un mínimo (fotos cada ~5 min).'},
];
function renderPP(){const L=conPedido();const n=tabla('tP',CP,L,SP,'Ningún rider parado ≥'+U+' min con un pedido asignado ahora.');$('cntP').textContent=nf(n)+' riders';}
/* ===== Histórico de paradas con pedido: ¿en la puerta del cliente? (cruce con delivery_lv al generar) ===== */
const PH={day:'ALL',cls:'F',st:{k:'d0',d:-1}};
const PHFMT=new Intl.DateTimeFormat('en-CA',{timeZone:'Europe/Madrid',year:'numeric',month:'2-digit',day:'2-digit'});
const PHDOW=['dom','lun','mar','mié','jue','vie','sáb'];
const phDay=m=>PHFMT.format(new Date(m*60000));
const phLab=k=>{const d=new Date(k+'T00:00:00Z');return PHDOW[d.getUTCDay()]+' '+k.slice(8,10)+'/'+k.slice(5,7);};
const phHm=m=>hhmm(new Date(m*60000).toISOString());
const PHCLS={P:['En la puerta del cliente','pill'],F:['Fuera de la puerta','pill alert'],N:['Pendiente','pill mid']};
const PHROWS=((D.pph||{}).rows||[]).map(r=>({rid:r[0],city:r[1],d0:r[2],d1:r[3],min:r[4],cls:r[5],esp:r[6],oid:r[7],tienda:r[8],day:phDay(r[2])}));
const CPH=[CA[0],CA[1],
 {k:'d0',h:'Fecha y hora',v:e=>e.d0,f:e=>phLab(e.day)+'<span class="sub2">'+phHm(e.d0)+' – '+phHm(e.d1)+'</span>',d:'Día y tramo en el que estuvo parado con el pedido (hora de Madrid, según las muestras de posición).'},
 {k:'min',h:'Parado con pedido',n:1,v:e=>e.min,f:e=>`<span class="pill ${e.min>=U*2?'alert':'mid'}">≥ ${nf(e.min)} min</span>`,d:'Minutos parado con el pedido asignado (mínimo, fotos cada ~5 min).'},
 {k:'cls',h:'Dónde',v:e=>e.cls,f:e=>`<span class="${PHCLS[e.cls][1]}">${PHCLS[e.cls][0]}</span>`,d:'En la puerta del cliente: la parada coincide con su espera en la dirección de entrega. Fuera de la puerta: parado con el pedido en otro sitio. Pendiente: aún no hay datos de entregas de ese día.'},
 {k:'esp',h:'Pedido · espera en puerta',v:e=>e.esp,f:e=>e.cls==='P'?esc(e.tienda||'—')+'<span class="sub2">pedido '+esc(e.oid||'—')+' · '+nf(e.esp)+' min en la puerta</span>':'—',d:'Pedido que estaba entregando, tienda y minutos entre llegar a la dirección del cliente y marcar la entrega (WTD).'},
];
function renderPPH(){
  if(!$('tPH'))return;
  const minU=S.min==='ALL'?0:(S.min==='D'?U*2:U);
  const B0=PHROWS.filter(e=>D.cities.includes(e.city)&&(S.city==='ALL'||e.city===S.city)&&e.min>=minU&&
    (!S.q||String(e.rid).includes(S.q)||nombre(e.rid).toLowerCase().includes(S.q)));
  const days=[...new Set(B0.map(e=>e.day))].sort().reverse();
  if(PH.day!=='ALL'&&!days.includes(PH.day))PH.day='ALL';
  $('phDay').innerHTML='<option value="ALL">Todas</option>'+days.map(d=>`<option value="${d}" ${d===PH.day?'selected':''}>${phLab(d)}</option>`).join('');
  $('phDay').onchange=ev=>{PH.day=ev.target.value;renderPPH();};
  const B=B0.filter(e=>PH.day==='ALL'||e.day===PH.day);
  const n={P:0,F:0,N:0};B.forEach(e=>n[e.cls]++);const cl=n.P+n.F;
  seg('phCls',[{v:'F',l:'Fuera de la puerta',c:n.F},{v:'P',l:'En la puerta del cliente',c:n.P},{v:'N',l:'Pendientes',c:n.N},{v:'ALL',l:'Todas',c:B.length}],PH.cls,v=>{PH.cls=v;renderPPH();});
  const h=(D.pph||{}).hasta;
  $('phSub').textContent=!PHROWS.length?'Todavía no hay histórico: las paradas con pedido se empiezan a guardar con el muestreo de cada minuto.':
    'Paradas de '+(minU?'≥'+minU+' min':'cualquier duración')+' en los últimos 28 días · datos de entregas hasta el '+(h?phLab(h):'—')+' (llegan con 1 día de retraso).';
  $('phKpis').innerHTML=[
   ['Paradas con pedido',nf(B.length),nf(n.N)+' pendientes de cruzar','Paradas con pedido asignado terminadas en el periodo y filtros elegidos.'],
   ['En la puerta del cliente',nf(n.P),cl?nf(n.P/cl*100,0)+' % de las cruzadas':'','Paradas que coinciden con la espera del rider en la dirección del cliente (WTD): no es una parada improductiva del rider.'],
   ['Fuera de la puerta',`<span style="color:${n.F?'var(--bad)':'inherit'}">${nf(n.F)}</span>`,cl?nf(n.F/cl*100,0)+' % de las cruzadas':'','Paradas con el pedido en otro sitio: las que hay que revisar.'],
   ['Riders fuera de la puerta',nf(new Set(B.filter(e=>e.cls==='F').map(e=>e.rid)).size),'','Riders distintos con alguna parada con pedido fuera de la puerta del cliente.'],
  ].map(([e,b,s2,d])=>`<div class="kpi"><em data-def="${esc(d)}" tabindex="0">${e}</em><b>${b}</b><span>${s2}</span></div>`).join('');
  tabla('tPH',CPH,B.filter(e=>PH.cls==="ALL"||e.cls===PH.cls),PH.st,'Ninguna parada con pedido con estos filtros.');
}
/* ===== Pop-up: rider parado ≥U min con pedido asignado ===== */
const AL_SEEN=(()=>{try{return JSON.parse(sessionStorage.getItem('wtdv1_alertas')||'{}');}catch(e){return {};}})();
function revisarAlertas(){
  const act=Object.entries(D.paradas).map(([rid,p])=>({rid,city:ciudadR(rid),...p}))
    .filter(p=>p.estado==='parado'&&!p.gps_viejo&&pVivo(p)&&pSec(p)/60>=U&&D.cities.includes(p.city)&&(S.city==='ALL'||p.city===S.city));
  const lvl=p=>pSec(p)/60>=U*2?2:1;
  const info=p=>({rid:p.rid,name:nombre(p.rid),city:p.city,desde:p.desde,nivel:lvl(p),txt:'con pedido asignado · quieto desde las '+hhmm(p.desde)});
  const nuevos=act.filter(p=>{const k='P|'+p.rid+'|'+p.desde+'|'+lvl(p);if(AL_SEEN[k])return false;AL_SEEN[k]=Date.now();return true;});
  try{const lim=Date.now()-864e5;for(const k in AL_SEEN)if(AL_SEEN[k]<lim)delete AL_SEEN[k];sessionStorage.setItem('wtdv1_alertas',JSON.stringify(AL_SEEN));}catch(e){}
  const msg={v1Alert:{umbral:U,nuevos:nuevos.map(info),activos:act.map(info)}};
  if(window.parent!==window){try{window.parent.postMessage(msg,'*');}catch(e){}}
  revisarRetrasos();
}
/* ===== Pop-up: rider con turno empezado y sin conectar (estado «late» de Live Operations) ===== */
function revisarRetrasos(){
  const f=D.retrasos_foto, fresca=!!(f&&(Date.now()-new Date(f).getTime())<STALE_MIN*60000);
  const act=(fresca?(D.retrasos||[]):[]).map(r=>({rid:String(r[0]),city:r[1],ini:r[2],fin:r[3],sp:r[4]||''}))
    .filter(r=>D.cities.includes(r.city)&&(S.city==='ALL'||r.city===S.city));
  const info=r=>({rid:r.rid,name:nombre(r.rid),city:r.city,ini:r.ini,fin:r.fin,sp:r.sp});
  const nuevos=act.filter(r=>{const k='L|'+r.rid+'|'+r.ini;if(AL_SEEN[k])return false;AL_SEEN[k]=Date.now();return true;});
  try{sessionStorage.setItem('wtdv1_alertas',JSON.stringify(AL_SEEN));}catch(e){}
  if(window.parent!==window){try{window.parent.postMessage({lateAlert:{nuevos:nuevos.map(info),activos:act.map(info)}},'*');}catch(e){}}
}
/* ===== WTD>10′ por pedido (bucket delivery_lv) ===== */
const WS={wk:'ALL',day:'ALL',sr:{k:'n10',d:-1},se:{k:'f',d:-1}};
const WP=D.wp?{ag:D.wp.ag.map(r=>({rid:r[0],city:r[1],f:r[2],n:r[3],n10:r[4],c:r[5],s:r[6],u:r[7],exp:r[8],ws:r[9],ds:r[10],dn:r[11],ks:r[12],kn:r[13]})),
  det:D.wp.det.map(r=>({f:r[0],rid:r[1],city:r[2],h0:r[3],h1:r[4],w:r[5],c:r[6],d:r[7],kg:r[8],store:r[9],oid:r[10]}))}:null;
function wpWeek(f){const d=new Date(f+'T00:00:00Z');return isoW(d);}
function renderWP(){
  if(!WP){$('wp').style.display='none';return;}
  WP.ag.forEach(r=>{if(!r.wk){const w=isoW(new Date(r.f+'T00:00:00Z'));r.wk=w[0]+'-W'+String(w[1]).padStart(2,'0');}});
  WP.det.forEach(r=>{if(!r.wk){const w=isoW(new Date(r.f+'T00:00:00Z'));r.wk=w[0]+'-W'+String(w[1]).padStart(2,'0');}});
  const wks=[...new Set(WP.ag.map(r=>r.wk))].sort().reverse();
  $('wpWk').innerHTML='<option value="ALL">Todas</option>'+wks.map(w=>`<option value="${w}" ${w===WS.wk?'selected':''}>${w.slice(5)} · ${w.slice(0,4)}</option>`).join('');
  const days=[...new Set(WP.ag.filter(r=>WS.wk==='ALL'||r.wk===WS.wk).map(r=>r.f))].sort().reverse();
  if(WS.day!=='ALL'&&!days.includes(WS.day))WS.day='ALL';
  $('wpDay').innerHTML='<option value="ALL">Todas</option>'+days.map(d=>`<option value="${d}" ${d===WS.day?'selected':''}>${dlab(d)}</option>`).join('');
  const ok=r=>(S.city==='ALL'||r.city===S.city)&&(WS.wk==='ALL'||r.wk===WS.wk)&&(WS.day==='ALL'||r.f===WS.day)&&(!S.q||String(r.rid).includes(S.q)||nombre(r.rid).toLowerCase().includes(S.q));
  const A=WP.ag.filter(ok), E=WP.det.filter(ok);
  const sm=k=>A.reduce((a,r)=>a+r[k],0);
  const n=sm('n'),n10=sm('n10'),c=sm('c'),s_=sm('s'),u=sm('u'),exp=sm('exp');
  $('wpSub').textContent='Datos del bucket de Glovo del '+dlab(D.wp.desde)+' al '+dlab(D.wp.hasta)+' (llegan con 1 día de retraso). «Contactó al cliente» lo informa Glovo desde el '+(D.wp.contacto_desde?dlab(D.wp.contacto_desde):'—')+'; en pedidos anteriores aparece como «sin dato».';
  const idx=exp?n10/exp:null;
  $('wpKpis').innerHTML=[
   ['WTD>10′',n?nf(n10/n*100,2)+' %':'—',nf(n10)+' de '+nf(n)+' pedidos','Pedidos con más de 10 min entre llegar a la puerta y marcar entregado ÷ pedidos completados.'],
   ['Espera media en puerta',n?nf(sm('ws')/n,1)+' min':'—','todas las entregas','Media de minutos entre la llegada a la puerta y el marcado de entrega.'],
   ['Con contacto al cliente',(c+s_)?nf(c/(c+s_)*100,0)+' %':'—',nf(c)+' de '+nf(c+s_)+' WTD>10′ con dato','WTD>10′ en los que el rider contactó al cliente ausente: espera justificada por el cliente.'],
   ['Sin contacto registrado',nf(s_),'posible marcado tardío o espera no declarada','WTD>10′ sin contacto al cliente: el rider no avisó de cliente ausente; revisar si marca tarde la entrega.'],
   ['Índice ajustado',idx==null?'—':nf(idx,2),'real ÷ esperado por distancia y peso','1,00 = lo esperable para pedidos de esa distancia y peso en su área.'],
  ].map(([e,b,s2,d])=>`<div class="kpi"><em data-def="${esc(d)}" tabindex="0">${e}</em><b>${b}</b><span>${s2}</span></div>`).join('');
  const M={};A.forEach(r=>{const m=M[r.rid]||(M[r.rid]={rid:r.rid,city:r.city,n:0,n10:0,c:0,s:0,u:0,exp:0,ws:0,ds:0,dn:0,ks:0,kn:0});
    ['n','n10','c','s','u','exp','ws','ds','dn','ks','kn'].forEach(k=>m[k]+=r[k]);});
  const RR=Object.values(M).filter(m=>m.n>=5).map(m=>({...m,p:m.n10/m.n,pe:m.exp/m.n,ix:m.exp?m.n10/m.exp:null}));
  const ixc=v=>v==null?'':(v>1.3?'alert':(v<0.8?'ok2':''));
  const cols=[
   {k:'rid',h:'Rider',v:m=>Number(m.rid)||0,f:m=>esc(m.rid)+(nombre(m.rid)?`<span class="nm">${esc(nombre(m.rid))}</span>`:''),d:'Rider (mínimo 5 pedidos en el filtro).'},
   {k:'city',h:'Área',v:m=>m.city,f:m=>esc(m.city),d:'Área.'},
   {k:'n',h:'Pedidos',n:1,v:m=>m.n,f:m=>nf(m.n),d:'Pedidos completados.'},
   {k:'n10',h:'WTD>10′',n:1,v:m=>m.n10,f:m=>nf(m.n10)+` <span class="muted">(${nf(m.p*100,1)} %)</span>`,d:'Pedidos con WTD>10′ y su %.'},
   {k:'pe',h:'Esperado',n:1,v:m=>m.pe,f:m=>nf(m.pe*100,1)+' %',d:'% de WTD>10′ esperable para pedidos de la misma área, distancia y peso.'},
   {k:'ix',h:'Índice',n:1,v:m=>m.ix??-1,f:m=>m.ix==null?'—':`<span class="pill ${ixc(m.ix)}">${nf(m.ix,2)}</span>`,d:'Real ÷ esperado. Rojo >1,3: espera más de lo que justifican sus repartos. Verde <0,8.'},
   {k:'c',h:'Con contacto',n:1,v:m=>m.c,f:m=>m.c||'',d:'WTD>10′ en los que contactó al cliente ausente.'},
   {k:'s',h:'Sin contacto',n:1,v:m=>m.s,f:m=>m.s?`<b>${m.s}</b>`:'',d:'WTD>10′ sin contacto al cliente (con dato de Glovo).'},
   {k:'ws',h:'Espera media',n:1,v:m=>m.ws/m.n,f:m=>nf(m.ws/m.n,1)+' min',d:'Minutos medios en puerta.'},
   {k:'ds',h:'Km último tramo',n:1,v:m=>m.dn?m.ds/m.dn:0,f:m=>m.dn?nf(m.ds/m.dn,1):'—',d:'Distancia media restaurante → cliente (km).'},
   {k:'ks',h:'Peso medio',n:1,v:m=>m.kn?m.ks/m.kn:0,f:m=>m.kn?nf(m.ks/m.kn,1):'—',d:'Peso medio de los pedidos que lo informan.'},
  ];
  const nR=tabla('wpR',cols,RR,WS.sr,'Ningún rider con al menos 5 pedidos en este filtro.');
  $('wpCntR').textContent=nf(nR)+' riders con 5 o más pedidos';
  const ce=[
   {k:'f',h:'Día',v:e=>e.f+e.h0,f:e=>dlab(e.f),d:'Día del pedido.'},
   {k:'rid',h:'Rider',v:e=>Number(e.rid)||0,f:e=>esc(e.rid)+(nombre(e.rid)?`<span class="nm">${esc(nombre(e.rid))}</span>`:''),d:'Rider.'},
   {k:'city',h:'Área',v:e=>e.city,f:e=>esc(e.city),d:'Área.'},
   {k:'h0',h:'Llega a la puerta',v:e=>e.h0,f:e=>esc(e.h0),d:'Hora en que el rider llega junto al cliente.'},
   {k:'h1',h:'Marca entregado',v:e=>e.h1,f:e=>esc(e.h1),d:'Hora en que marca el pedido como entregado.'},
   {k:'w',h:'Espera',n:1,v:e=>e.w,f:e=>`<span class="pill ${e.w>=20?'alert':'mid'}">${nf(e.w,1)} min</span>`,d:'Minutos entre llegar a la puerta y marcar entregado.'},
   {k:'c',h:'Contactó al cliente',v:e=>e.c,f:e=>e.c==='S'?'<span class="pill ok2">Sí</span>':(e.c==='N'?'<span class="pill alert">No</span>':'<span class="muted">sin dato</span>'),d:'Si el rider contactó al cliente ausente antes de entregar.'},
   {k:'d',h:'Km',n:1,v:e=>e.d??-1,f:e=>e.d==null?'—':nf(e.d,1),d:'Distancia restaurante → cliente.'},
   {k:'kg',h:'Peso',n:1,v:e=>e.kg??-1,f:e=>e.kg==null?'—':nf(e.kg,1),d:'Peso del pedido (si Glovo lo informa).'},
   {k:'store',h:'Tienda',v:e=>e.store,f:e=>esc(e.store),d:'Restaurante.'},
  ];
  tabla('wpE',ce,E.slice().sort((a,b)=>(b.f+b.h0).localeCompare(a.f+a.h0)).slice(0,600),WS.se,'Ningún pedido con WTD>10′ en este filtro.');
  $('wpCntE').textContent=nf(E.length)+' pedidos'+(E.length>600?' (se muestran 600)':'');
}
$('wpWk').onchange=e=>{WS.wk=e.target.value;WS.day='ALL';renderWP();};
$('wpDay').onchange=e=>{WS.day=e.target.value;renderWP();};

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
cargarVivo();setInterval(cargarVivo,30*1000);
/* contador en vivo: cada segundo actualiza los tiempos; cada minuto re-renderiza (orden y colores) */
setInterval(()=>{document.querySelectorAll('.live[data-desde]').forEach(el=>{const sec=(Date.now()-new Date(el.dataset.desde).getTime())/1000;
  const m=sec/60;el.classList.toggle('alert',m>=U*2);el.classList.toggle('mid',m>=U&&m<U*2);const d=el.querySelector('.dot');el.textContent='≥ '+fmtDur(sec);if(d)el.prepend(d);});},1000);
setInterval(render,60*1000);
cargarHist();setInterval(cargarHist,10*60*1000);renderHist();renderWP();
if(window.parent!==window){const send=()=>window.parent.postMessage({v1H:document.body.getBoundingClientRect().height},'*');
  if(window.ResizeObserver) new ResizeObserver(send).observe(document.body); send();}
</script></body></html>
'''
