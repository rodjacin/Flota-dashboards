# -*- coding: utf-8 -*-
"""
================================================================================
 Pestaña "WTD%" para los dashboards de flota
================================================================================
 Una fila por rider con:
   · %WTD Last 4 weeks : WTD>10' % de las 4 últimas semanas ISO cerradas (WK-1..WK-4)
   · %WTD WK-1         : WTD>10' % de la semana pasada
     (WTD>10' % = total_deliveries_over_10_min ÷ total_deliveries_completed, rider_lv
      del bucket GCP; la misma definición que el resto del dashboard)
   · Parado con pedido : minutos que lleva el rider sin moverse con un pedido activo y
     lejos de cualquier restaurante conocido (posiciones.py + Live Operations).
 Lo usa generar_resumen_flota.py (igual que UTR, No show, En vivo...).
================================================================================
"""
import os, json, datetime as dt

RIDER_CSV = os.path.expanduser("~/Downloads/fleet_data_combinado/rider_lv_combinado.csv")
NODE_ALIASES = {"NEM": "MAD"}
TZ = dt.timezone(dt.timedelta(hours=2))       # solo para calcular "hoy"; se corrige abajo con zoneinfo
PARADA_MIN = 5                                # umbral de aviso (minutos parado)

# Objetivo T1 de WTD>10' % por ciudad (mismo que el Resumen de performance)
T1 = {"ALC": 0.0270, "GRA": 0.0228, "NOM": 0.0405, "SAB": 0.0225, "MAD": 0.0315}


def _hoy():
    try:
        from zoneinfo import ZoneInfo
        return dt.datetime.now(ZoneInfo("Europe/Madrid")).date()
    except Exception:
        return dt.datetime.now(TZ).date()


def _semanas():
    """(WK-1, [WK-1..WK-4]) como claves (año, semana ISO)."""
    hoy = _hoy()
    ks = []
    for i in range(1, 5):
        y, w, _ = (hoy - dt.timedelta(days=7 * i)).isocalendar()
        ks.append((y, w))
    return ks[0], ks


def _wtd(cities):
    import pandas as pd
    if not os.path.isfile(RIDER_CSV):
        raise ValueError("no encuentro " + RIDER_CSV)
    cols = ["rider_id", "city_code", "fecha", "total_deliveries_over_10_min", "total_deliveries_completed"]
    df = pd.read_csv(RIDER_CSV, dtype=str, keep_default_na=False, usecols=lambda c: c in cols)
    for c in cols:
        if c not in df.columns:
            df[c] = ""
    df["_c"] = df["city_code"].str.strip().map(lambda v: NODE_ALIASES.get(v, v))
    df = df[df["_c"].isin(cities)].copy()
    df["_d"] = pd.to_datetime(df["fecha"], errors="coerce")
    df = df[df["_d"].notna()]
    iso = df["_d"].dt.isocalendar()
    df["_k"] = list(zip(iso["year"].astype(int), iso["week"].astype(int)))
    df["_o"] = pd.to_numeric(df["total_deliveries_over_10_min"], errors="coerce").fillna(0)
    df["_n"] = pd.to_numeric(df["total_deliveries_completed"], errors="coerce").fillna(0)
    wk1, l4 = _semanas()
    out = {}
    for (rid, city), g in df[df["_k"].isin(l4)].groupby(["rider_id", "_c"]):
        g1 = g[g["_k"] == wk1]
        out[(str(rid).strip(), city)] = {"o4": float(g["_o"].sum()), "n4": float(g["_n"].sum()),
                                         "o1": float(g1["_o"].sum()), "n1": float(g1["_n"].sum())}
    return out, wk1, l4


def construir_html(cities=None, semanas=None, sello=True):
    cities = sorted(set(NODE_ALIASES.get(c, c) for c in (cities or [])))
    wtd, wk1, l4 = _wtd(cities)

    # --- Paradas en vivo (si hay historial de posiciones)
    paradas, foto, nombres, aviso = {}, None, {}, ""
    try:
        import en_vivo, posiciones
        snap = en_vivo._foto(cities)
        if not snap.get("stale"):
            posiciones.registrar(snap, en_vivo._POS)
        for code, C in (snap.get("cities") or {}).items():
            for r in C.get("riders") or []:
                nombres[str(r.get("employee_id"))] = (r.get("name") or "", code)
        paradas, foto = posiciones.quietos(cities)
        if not paradas:
            aviso = "Sin posiciones recientes de Live Operations: la columna de parada aparece vacía."
    except Exception as e:
        aviso = "No se pudo calcular el tiempo parado: " + str(e)[:200]

    filas, vistos = [], set()
    for (rid, city), v in wtd.items():
        vistos.add(rid)
        filas.append({"id": rid, "city": city, "name": nombres.get(rid, ("", ""))[0],
                      "o4": v["o4"], "n4": v["n4"], "o1": v["o1"], "n1": v["n1"], "p": paradas.get(rid)})
    for rid, (nm, city) in nombres.items():          # riders conectados sin histórico en 4 semanas
        if rid not in vistos and city in cities:
            filas.append({"id": rid, "city": city, "name": nm, "o4": 0, "n4": 0, "o1": 0, "n1": 0,
                          "p": paradas.get(rid)})

    data = {"cities": cities, "rows": filas, "t1": {c: T1.get(c) for c in cities},
            "wk1": "W%02d" % wk1[1], "l4": ["W%02d" % k[1] for k in reversed(l4)],
            "foto": foto, "aviso": aviso, "umbral": PARADA_MIN}
    html = HTML.replace("__DATA__", json.dumps(data, ensure_ascii=False, separators=(",", ":")))
    np_ = sum(1 for f in filas if (f["p"] or {}).get("estado") == "parado" and f["p"]["min"] >= PARADA_MIN)
    res = "%d riders · WK-1 %s · %d parados ≥%d min%s" % (len(filas), data["wk1"], np_, PARADA_MIN,
                                                          (" · " + aviso) if aviso else "")
    return html, res


_BTN = '<button data-v="wtdpct" aria-pressed="false">WTD%</button>'


def integrar_en_dashboard(dash_html, wtd_html):
    """Añade la pestaña 'WTD%' al selector Vista del dashboard (en un iframe aislado)."""
    if 'id="viewWtd"' in dash_html:
        return dash_html
    ancla = None
    for a in ['<button data-v="cpostal" aria-pressed="false">Códigos postales</button>',
              '<button data-v="envivo" aria-pressed="false">En vivo</button>',
              '<button data-v="capacidad" aria-pressed="false">Capacidad</button>',
              '<button data-v="noshow" aria-pressed="false">No show</button>',
              '<button data-v="utr" aria-pressed="false">UTR</button>']:
        if a in dash_html:
            ancla = a
            break
    sec_ancla = '<div id="viewSemanal">'
    if not ancla or sec_ancla not in dash_html or "</body>" not in dash_html:
        raise ValueError("la plantilla no tiene el selector de Vista esperado")
    dash_html = dash_html.replace(ancla, ancla + "\n        " + _BTN, 1)
    dash_html = dash_html.replace(sec_ancla,
        '<section id="viewWtd" style="display:none"><iframe id="wtdFrame" title="WTD%" '
        'style="width:100%;height:1200px;border:0;display:block;background:transparent"></iframe></section>\n  '
        + sec_ancla, 1)
    src = json.dumps(wtd_html, ensure_ascii=False).replace("<", "\\u003c")
    js = ("<script>\n/* ==== Pestaña WTD% ==== */\n(function(){\n"
          "  const WTD_HTML=" + src + ";\n"
          "  const seg=document.getElementById('viewSeg'),sec=document.getElementById('viewWtd'),fr=document.getElementById('wtdFrame');\n"
          "  if(!seg||!sec||!fr) return; let loaded=false;\n"
          "  seg.querySelectorAll('button').forEach(b=>b.addEventListener('click',()=>{\n"
          "    const on=b.dataset.v==='wtdpct'; sec.style.display=on?'':'none';\n"
          "    if(on){ seg.querySelectorAll('button').forEach(x=>x.setAttribute('aria-pressed',String(x===b)));\n"
          "      document.querySelectorAll('[id^=\"view\"]').forEach(e=>{ if(e!==sec && e!==seg && e.id!=='viewSeg') e.style.display='none'; });\n"
          "      if(!loaded){ fr.srcdoc=WTD_HTML; loaded=true; } window.scrollTo(0,0); }\n"
          "  }));\n"
          "  window.addEventListener('message',e=>{ if(e.source===fr.contentWindow && e.data && e.data.wtdH){\n"
          "    fr.style.height=Math.max(600,Math.ceil(e.data.wtdH)+20)+'px'; } });\n"
          "})();\n</script>\n")
    i = dash_html.rindex("</body>")
    return dash_html[:i] + js + dash_html[i:]


HTML = r'''<!DOCTYPE html><html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>WTD% por rider</title>
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
.v{display:inline-block;min-width:62px;padding:2px 7px;border-radius:6px}
.v.bad{background:var(--badbg);color:var(--bad);font-weight:600}
.v.ok{color:var(--good)}
.cnt{color:var(--muted);font-size:11.5px;margin-left:6px}
.pill{display:inline-block;padding:2px 9px;border-radius:99px;font-size:12px;background:var(--chip);color:var(--ink2)}
.pill.alert{background:var(--badbg);color:var(--bad);font-weight:600}
.pill.mid{background:var(--warnbg);color:var(--warn)}
.muted{color:var(--muted)}
.empty{color:var(--muted);padding:16px 0}
.note{color:var(--muted);font-size:12px;line-height:1.55;margin:0}
[data-def]{cursor:help}
th[data-def],.kpi em[data-def]{text-decoration:underline dotted;text-underline-offset:3px}
#defTip{position:fixed;z-index:50;max-width:320px;background:#14171F;color:#fff;font-size:12px;line-height:1.45;padding:8px 10px;border-radius:7px;pointer-events:none;box-shadow:0 4px 14px rgba(0,0,0,.18)}
#defTip[hidden]{display:none}
</style></head><body>
<div class="wrap">
  <header><h1>WTD% por rider</h1><p class="sub" id="sub"></p></header>
  <div class="banner" id="banner" hidden></div>
  <div class="filters">
    <div class="fg"><span>Área</span><div class="seg" id="fCity"></div></div>
    <div class="fg"><span>Parada</span><div class="seg" id="fPar"></div></div>
    <div class="fg"><span>Buscar</span><input type="search" id="fQ" placeholder="ID o nombre de rider" aria-label="Buscar rider"></div>
  </div>
  <section class="kpis" id="kpis"></section>
  <section class="panel"><div class="ph"><h2>Riders</h2><p id="cnt"></p></div>
    <div class="tw" style="max-height:900px"><table id="tR"></table></div></section>
  <p class="note" id="nota"></p>
</div>
<script>
const D=__DATA__;
const $=id=>document.getElementById(id);
const esc=s=>String(s??'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const nf=(v,d=0)=>v==null||isNaN(v)?'—':Number(v).toLocaleString('es-ES',{minimumFractionDigits:d,maximumFractionDigits:d});
const pc=(o,n)=>n?o/n:null;
const hhmm=s=>{if(!s)return '—';const d=new Date(s);return isNaN(d)?'—':d.toLocaleTimeString('es-ES',{timeZone:'Europe/Madrid',hour:'2-digit',minute:'2-digit'});};
const U=D.umbral;
const S={city:'ALL',par:'ALL',q:'',sort:'par',dir:-1};
const parMin=r=>(r.p&&r.p.estado==='parado')?r.p.min:null;
function cabecera(){
  $('sub').textContent='%WTD>10′ de las 4 últimas semanas cerradas ('+D.l4.join(', ')+') y de la semana pasada ('+D.wk1+'), según el bucket GCP. Parada con pedido activo según Live Operations'+(D.foto?' · posiciones a las '+hhmm(D.foto)+' (hora de Madrid), se actualiza cada ~10 min':'')+'.';
  $('banner').hidden=!D.aviso;$('banner').textContent=D.aviso||'';}
cabecera();
/* Paradas en vivo: wtd_vivo.json lo publica el muestreo cada ~10 min; se relee cada 5 min */
function aplicarVivo(j){
  if(!j||!j.foto)return;
  const fresco=(Date.now()-new Date(j.foto).getTime())<20*60*1000;   // muestra de los últimos 20 min: manda sobre la foto horaria
  if(D.foto&&j.foto<=D.foto&&!fresco)return;
  D.foto=j.foto;D.aviso='';
  const P=j.paradas||{},R=j.riders||{},ids=new Set(D.rows.map(r=>r.id));
  D.rows.forEach(r=>{r.p=P[r.id]||null;if(R[r.id]&&R[r.id][0])r.name=R[r.id][0];});
  Object.keys(R).forEach(id=>{if(!ids.has(id)&&D.cities.includes(R[id][1]))D.rows.push({id,city:R[id][1],name:R[id][0],o4:0,n4:0,o1:0,n1:0,p:P[id]||null});});
  cabecera();render();}
function cargarVivo(){try{fetch(new URL('wtd_vivo.json?t='+Date.now(),document.baseURI),{cache:'no-store'}).then(r=>r.ok?r.json():null).then(aplicarVivo).catch(()=>{});}catch(e){}}
$('nota').innerHTML='WTD&gt;10′ % = pedidos en los que el rider pasó más de 10 min en el punto del cliente ÷ pedidos entregados. En rojo, por encima del objetivo T1 de su área. '+
 '«Parado con pedido» = minutos que lleva el rider a menos de 80 m del mismo punto mientras tiene un pedido activo, sin contar si está a menos de 100 m de un restaurante donde se ha recogido algún pedido. '+
 'Las posiciones se muestrean y publican cada ~10 min (GitHub puede retrasarlo unos minutos); la pestaña se refresca sola cada 5 min sin recargar la página. «≥» indica que la cuenta llega al inicio del historial disponible. No se publican coordenadas.';
function seg(id,opts,val,on){const el=$(id);el.innerHTML=opts.map(o=>`<button data-v="${o.v}" class="${String(o.v)===String(val)?'on':''}">${o.l}${o.c!=null?`<span class="c">${o.c}</span>`:''}</button>`).join('');el.onclick=e=>{const b=e.target.closest('button');if(b)on(b.dataset.v);};}
const vcell=(o,n,city)=>{const v=pc(o,n);if(v==null)return '<span class="muted">—</span>';const t=D.t1[city];const cls=t==null?'':(v>t?'bad':'ok');
  return `<span class="v ${cls}" title="${nf(o)} de ${nf(n)} pedidos${t!=null?' · objetivo T1 '+nf(t*100,2)+' %':''}">${nf(v*100,2)} %</span><span class="cnt">${nf(n)}</span>`;};
const pcell=r=>{const p=r.p;if(!p)return '<span class="muted" title="Sin posición reciente de este rider">—</span>';
  const g=p.gps_viejo?` <span class="pill mid" title="La ubicación no se actualiza desde hace ${p.gps_viejo} min">GPS ${p.gps_viejo} min</span>`:'';
  if(p.estado==='sin_pedido')return '<span class="muted">Sin pedido activo</span>'+g;
  if(p.estado==='local')return '<span class="pill" title="A menos de 100 m de un restaurante conocido">En restaurante</span>'+g;
  const m=p.min,cls=m>=U*2?'alert':(m>=U?'mid':'');
  return `<span class="pill ${cls}" title="Sin moverse desde las ${hhmm(p.desde)} con pedido activo">${p.desde_inicio?'≥ ':''}${m} min</span>`+g;};
const COLS=[
 {k:'id',h:'Rider ID',v:r=>Number(r.id)||r.id,f:r=>esc(r.id)+(r.name?`<span class="nm">${esc(r.name)}</span>`:''),d:'ID del rider en Glovo (y nombre, si está conectado ahora).'},
 {k:'city',h:'Área',v:r=>r.city,f:r=>esc(r.city),d:'Área (nodo) del rider.'},
 {k:'l4',h:'%WTD Last 4 weeks',n:1,v:r=>pc(r.o4,r.n4),f:r=>vcell(r.o4,r.n4,r.city),d:'WTD>10′ % de las 4 últimas semanas cerradas ('+D.l4.join(', ')+'). El número gris son los pedidos entregados.'},
 {k:'wk1',h:'%WTD WK-1',n:1,v:r=>pc(r.o1,r.n1),f:r=>vcell(r.o1,r.n1,r.city),d:'WTD>10′ % de la semana pasada ('+D.wk1+'). El número gris son los pedidos entregados.'},
 {k:'par',h:'Parado con pedido',n:1,v:r=>{const m=parMin(r);return m==null?(r.p&&r.p.estado==='local'?-1:-2):m;},f:pcell,d:'Minutos que lleva sin moverse (menos de 80 m) con un pedido activo, lejos de restaurantes conocidos, en la última muestra de posiciones.'},
];
function render(){
  const byCity=D.rows.filter(r=>S.city==='ALL'||r.city===S.city);
  seg('fCity',[{v:'ALL',l:'Todas',c:D.rows.length}].concat(D.cities.map(c=>({v:c,l:c,c:D.rows.filter(r=>r.city===c).length}))),S.city,v=>{S.city=v;render();});
  const nPar=byCity.filter(r=>(parMin(r)??-1)>=U).length;
  seg('fPar',[{v:'ALL',l:'Todos'},{v:'P',l:'Parados ≥'+U+' min',c:nPar},{v:'A',l:'Con pedido activo',c:byCity.filter(r=>r.p&&r.p.estado!=='sin_pedido').length}],S.par,v=>{S.par=v;render();});
  const q=S.q;
  const rows=byCity.filter(r=>(S.par==='ALL'||(S.par==='P'?(parMin(r)??-1)>=U:(r.p&&r.p.estado!=='sin_pedido')))&&(!q||String(r.id).includes(q)||String(r.name||'').toLowerCase().includes(q)));
  const s4=byCity.reduce((a,r)=>[a[0]+r.o4,a[1]+r.n4],[0,0]),s1=byCity.reduce((a,r)=>[a[0]+r.o1,a[1]+r.n1],[0,0]);
  const t=S.city==='ALL'?null:D.t1[S.city];
  const kv=(o,n)=>{const v=pc(o,n);return v==null?'—':`<span style="color:${t!=null&&v>t?'var(--bad)':'inherit'}">${nf(v*100,2)} %</span>`;};
  const over=byCity.filter(r=>r.n1&&D.t1[r.city]!=null&&pc(r.o1,r.n1)>D.t1[r.city]).length;
  $('kpis').innerHTML=[
   ['WTD>10′ % L4W',kv(...s4),nf(s4[1])+' pedidos'+(t!=null?' · T1 '+nf(t*100,2)+' %':''),'WTD>10′ % agregado del área en las 4 últimas semanas cerradas.'],
   ['WTD>10′ % '+D.wk1,kv(...s1),nf(s1[1])+' pedidos','WTD>10′ % agregado del área la semana pasada.'],
   ['Riders sobre T1 en '+D.wk1,nf(over),'de '+nf(byCity.filter(r=>r.n1).length)+' con pedidos','Riders con WTD>10′ % de la semana pasada por encima del objetivo T1 de su área.'],
   ['Parados ≥'+U+' min',`<span style="color:${nPar?'var(--bad)':'inherit'}">${nf(nPar)}</span>`,D.foto?'a las '+hhmm(D.foto):'sin posiciones','Riders con pedido activo que llevan al menos '+U+' min sin moverse lejos de un restaurante, en la última muestra.'],
  ].map(([e,b,s,d])=>`<div class="kpi"><em data-def="${esc(d)}" tabindex="0">${e}</em><b>${b}</b><span>${s}</span></div>`).join('');
  const col=COLS.find(x=>x.k===S.sort)||COLS[4];
  const sorted=rows.slice().sort((a,b)=>{const x=col.v(a),y=col.v(b);if(x==null||x==='')return 1;if(y==null||y==='')return -1;
    const c=(typeof x==='string'?x.localeCompare(y,'es'):x-y)*S.dir;return c||((pc(b.o4,b.n4)??-1)-(pc(a.o4,a.n4)??-1));});
  $('tR').innerHTML=!sorted.length?'<tbody><tr><td class="empty">Ningún rider con estos filtros.</td></tr></tbody>':
   '<thead><tr>'+COLS.map(x=>`<th class="${x.n?'n':''}" data-k="${x.k}" data-def="${esc(x.d)}">${x.h}${S.sort===x.k?`<span class="arw">${S.dir<0?'▼':'▲'}</span>`:''}</th>`).join('')+'</tr></thead><tbody>'+
   sorted.map(r=>'<tr>'+COLS.map(x=>`<td class="${x.n?'n':''}">${x.f(r)}</td>`).join('')+'</tr>').join('')+'</tbody>';
  $('tR').querySelectorAll('th[data-k]').forEach(th=>th.onclick=()=>{const k=th.dataset.k;if(S.sort===k)S.dir*=-1;else{S.sort=k;S.dir=COLS.find(x=>x.k===k).n?-1:1;}render();});
  $('cnt').textContent=nf(sorted.length)+' de '+nf(D.rows.length)+' riders';
}
let qT;$('fQ').addEventListener('input',e=>{clearTimeout(qT);qT=setTimeout(()=>{S.q=e.target.value.trim().toLowerCase();render();},150);});
(function(){const tip=document.createElement('div');tip.id='defTip';tip.hidden=true;document.body.appendChild(tip);
  const place=(x,y)=>{const w=tip.offsetWidth,h=tip.offsetHeight;let l=x+12,t=y+14;if(l+w>innerWidth-8)l=Math.max(8,x-w-12);if(t+h>innerHeight-8)t=Math.max(8,y-h-12);tip.style.left=l+'px';tip.style.top=t+'px';};
  document.addEventListener('mouseover',e=>{const el=e.target.closest('[data-def]');if(el){tip.textContent=el.dataset.def;tip.hidden=false;place(e.clientX,e.clientY);}});
  document.addEventListener('mousemove',e=>{if(!tip.hidden&&e.target.closest('[data-def]'))place(e.clientX,e.clientY);});
  document.addEventListener('mouseout',e=>{const el=e.target.closest('[data-def]');if(el&&!el.contains(e.relatedTarget))tip.hidden=true;});})();
render();
cargarVivo();setInterval(cargarVivo,5*60*1000);
if(window.parent!==window){const send=()=>window.parent.postMessage({wtdH:document.body.getBoundingClientRect().height},'*');
  if(window.ResizeObserver) new ResizeObserver(send).observe(document.body); send();}
</script></body></html>
'''
