# -*- coding: utf-8 -*-
"""
Pestaña «Rider scoring» de los dashboards GRA-MAD-NOM-ALC y SAB.

Fuente: bucket de Glovo (copia local en ~/Downloads/fleet_data):
  · <día>/…/rider_lv.csv       métricas diarias por rider
  · billing/<periodo>/…/city_billing.csv   objetivos de desviación positiva/negativa por ciudad

Por rider y semana ISO se calculan las 8 métricas del scoring; el score final se calcula en el
navegador (así los pesos y objetivos se pueden ajustar en la propia pestaña):
  NS     no show          = total_no_shows ÷ total_booked_shifts                 objetivo 0 %
  RR     reasignación     = total_reassigned_orders ÷ total_assigned_orders      objetivo 3,5 %
  Speed  velocidad km/h   = (sp_speed_kmh_num + pd_speed_kmh_num) ÷ (… _den)     objetivo = media del 10 % más rápido del nodo y semana
  WTD    entregas >10 min = total_deliveries_over_10_min ÷ total_deliveries_completed   objetivo 5 %
  CAPU   fraude CAPU      = total_fraud_capu_count ÷ total_deliveries_completed  objetivo 0
  Motor  motorizado       = días con is_motorized ÷ días trabajados               objetivo 100 %
  PD     desviación +     = Σ max(trabajadas − planificadas, 0) ÷ Σ planificadas objetivo de city_billing (target_positive_deviation)
  ND     desviación −     = Σ max(planificadas − trabajadas, 0) ÷ Σ planificadas objetivo de city_billing (target_negative_deviation)

Uso: python3 rider_scoring.py <index.html> [gra-mad-nom-alc|sab]
"""
import os, sys, glob, json, datetime as dt
import pandas as pd

FLEET = os.environ.get("FLEET_DATA") or os.path.expanduser("~/Downloads/fleet_data")
DASH = {"sab": ["SAB"], "gra-mad-nom-alc": ["ALC", "GRA", "MAD", "NOM"]}
CIUDADES = DASH["gra-mad-nom-alc"]
CARPETA = "gra-mad-nom-alc"
ALIAS = {"NEM": "MAD"}
SEMANAS = 10
_BTN = '<button data-v="scoring" aria-pressed="false">Rider scoring</button>'
COLS = ["rider_id", "city_code", "company_name", "is_motorized", "total_deliveries_completed", "total_assigned_orders",
        "total_reassigned_orders", "total_fraud_capu_count", "sp_speed_kmh_num", "sp_speed_kmh_den", "pd_speed_kmh_num",
        "pd_speed_kmh_den", "planned_working_time", "total_booked_shifts", "total_no_shows", "total_worked_hours",
        "total_deliveries_over_10_min"]


def leer_rider_lv():
    fs = sorted(glob.glob(os.path.join(FLEET, "20*", "**", "rider_lv.csv"), recursive=True))
    hoy = dt.date.today(); desde = hoy - dt.timedelta(days=7 * SEMANAS + 7)
    parts = []
    for f in fs:
        try:
            d = dt.date.fromisoformat(os.path.relpath(f, FLEET).split(os.sep)[0][:10])
        except ValueError:
            continue
        if d < desde:
            continue
        x = pd.read_csv(f, usecols=lambda c: c in COLS)
        x["fecha"] = d
        parts.append(x)
    if not parts:
        raise ValueError("no hay rider_lv.csv en " + FLEET)
    df = pd.concat(parts, ignore_index=True)
    df = df[df.company_name.astype(str).str.upper().str.contains("MUSHDRINK")]
    df["city_code"] = df.city_code.astype(str).str.upper().replace(ALIAS)
    df = df[df.city_code.isin(CIUDADES)].copy()
    df["rider_id"] = df.rider_id.astype("int64").astype(str)
    return df.drop_duplicates(["rider_id", "fecha"], keep="last")


def objetivos_billing():
    out, periodo = {}, None
    for f in sorted(glob.glob(os.path.join(FLEET, "billing", "*", "**", "city_billing.csv"), recursive=True)):
        c = pd.read_csv(f)
        for r in c.itertuples():
            out[ALIAS.get(r.city_code, r.city_code)] = {"pd": float(r.target_positive_deviation), "nd": float(r.target_negative_deviation)}
        periodo = f"{c.billing_period_start.iloc[0]} – {c.billing_period_end.iloc[0]}"
    return out, periodo


def nombres():
    try:
        d = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", CARPETA, "liveops_hist.json"), encoding="utf-8"))
    except Exception:
        return {}
    out = {}
    for k in sorted(d.get("dias", {})):
        for rid, v in d["dias"][k].items():
            if isinstance(v, list) and len(v) > 1 and v[1]:
                out[rid] = v[1]
    return out


def datos():
    df = leer_rider_lv()
    iso = pd.to_datetime(df.fecha).dt.isocalendar()
    df["sem"] = iso.year.astype(str) + "-W" + iso.week.astype(int).map("{:02d}".format)
    df["pdx"] = (df.total_worked_hours - df.planned_working_time).clip(lower=0)
    df["ndx"] = (df.planned_working_time - df.total_worked_hours).clip(lower=0)
    df["mot"] = df.is_motorized.astype(str).str.lower().isin(["true", "1"]).astype(int)
    df["dia"] = 1
    g = df.groupby(["sem", "city_code", "rider_id"]).agg(
        dias=("dia", "sum"), mot=("mot", "sum"), ent=("total_deliveries_completed", "sum"),
        asig=("total_assigned_orders", "sum"), reas=("total_reassigned_orders", "sum"),
        capu=("total_fraud_capu_count", "sum"), o10=("total_deliveries_over_10_min", "sum"),
        bk=("total_booked_shifts", "sum"), ns=("total_no_shows", "sum"),
        plan=("planned_working_time", "sum"), trab=("total_worked_hours", "sum"),
        pdx=("pdx", "sum"), ndx=("ndx", "sum"),
        spn=("sp_speed_kmh_num", "sum"), spd=("sp_speed_kmh_den", "sum"),
        ppn=("pd_speed_kmh_num", "sum"), ppd=("pd_speed_kmh_den", "sum")).reset_index()
    g["vel"] = (g.spn + g.ppn) / (g.spd + g.ppd).where(lambda s: s > 0)
    # objetivo de velocidad: media del 10 % de riders más rápidos del nodo y semana (riders con ≥10 entregas)
    vt = {}
    for (s, c), x in g[(g.ent >= 10) & g.vel.notna()].groupby(["sem", "city_code"]):
        v = x.vel.sort_values(ascending=False)
        n = max(1, int(round(len(v) * 0.10)))
        vt.setdefault(s, {})[c] = round(float(v.head(n).mean()), 2)
    dsem = {k: int(v) for k, v in df.groupby("sem").fecha.nunique().items()}
    nm = nombres()
    filas = []
    for r in g.itertuples():
        filas.append([r.sem, r.city_code, r.rider_id, nm.get(r.rider_id, ""), int(r.dias), int(r.mot), int(r.ent),
                      int(r.asig), int(r.reas), int(r.capu), int(r.o10), int(r.bk), int(r.ns),
                      round(float(r.plan), 2), round(float(r.trab), 2), round(float(r.pdx), 2), round(float(r.ndx), 2),
                      None if pd.isna(r.vel) else round(float(r.vel), 2)])
    obj, periodo = objetivos_billing()
    return {"generado": dt.datetime.now().strftime("%Y-%m-%d %H:%M"), "ultimo_dia": str(df.fecha.max()),
            "primer_dia": str(df.fecha.min()), "filas": filas, "vel_obj": vt, "dev_obj": obj,
            "billing": periodo, "ciudades": CIUDADES, "dias_sem": dsem}


def seccion():
    return r"""<section id="viewScoring" style="display:none">
<style>
#viewScoring .sc-card{background:#fff;border:1px solid #E4E7EC;border-radius:10px;padding:12px 14px;margin-bottom:12px}
#viewScoring .sc-k{display:flex;flex-wrap:wrap;gap:10px;margin-bottom:12px}
#viewScoring .sc-k div{background:#fff;border:1px solid #E4E7EC;border-radius:10px;padding:9px 14px;min-width:140px}
#viewScoring .sc-k b{display:block;font-size:20px;color:#14171F} #viewScoring .sc-k span{font-size:11.5px;color:#6B7280}
#viewScoring table{width:100%;border-collapse:collapse;font-size:12.6px;table-layout:auto;min-width:0!important}
#viewScoring th{background:#F0F2F5;padding:7px 8px;font-size:11px;color:#6B7280;text-transform:uppercase;letter-spacing:.03em;text-align:right!important;white-space:nowrap;cursor:pointer;user-select:none}
#viewScoring td{padding:6px 8px;border-top:1px solid #EEF0F3;text-align:right!important;white-space:nowrap;font-variant-numeric:tabular-nums}
#viewScoring th.l,#viewScoring td.l{text-align:left!important}
#viewScoring .mut{color:#6B7280;font-size:11.5px} #viewScoring .zn{font-weight:700;color:#0E5A6B}
#viewScoring select,#viewScoring input{border:1px solid #E4E7EC;border-radius:8px;padding:5px 7px;font-size:13px;background:#fff}
#viewScoring input{width:72px;text-align:right}
#viewScoring .seg2{display:inline-flex;flex-wrap:wrap;gap:4px}
#viewScoring .seg2 button{border:1px solid #E4E7EC;background:#fff;border-radius:8px;padding:5px 10px;font-size:12.5px;cursor:pointer}
#viewScoring .seg2 button.on{background:#0E5A6B;color:#fff;border-color:#0E5A6B}
#viewScoring .sub{display:block;font-size:10.5px;color:#9AA1AC}
#viewScoring .pill{display:inline-block;min-width:52px;padding:2px 7px;border-radius:99px;font-weight:700;text-align:center}
#viewScoring details summary{cursor:pointer;font-weight:700}
</style>
<div class="sc-card" style="display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap;align-items:center">
  <div><b style="font-size:16px">Rider scoring</b><div class="mut" id="scSub"></div></div>
  <div style="display:flex;gap:14px;flex-wrap:wrap;align-items:center">
    <label class="mut">Semana <select id="scSem"></select></label>
    <span class="seg2" id="scNodo"></span>
    <label class="mut">Mín. entregas <input id="scMin" type="number" min="0" value="10"></label>
    <label class="mut">Buscar <input id="scBus" type="search" placeholder="ID o nombre" style="width:130px;text-align:left"></label>
  </div>
</div>
<div class="sc-k" id="scKpi"></div>
<div class="sc-card"><div style="font-weight:700;margin-bottom:8px">Score por rider</div>
<div style="overflow:auto;max-height:70vh"><table id="scTab"></table></div>
<div class="mut" style="margin-top:8px" id="scNota"></div></div>
<div class="sc-card"><details><summary>Pesos y objetivos (editables)</summary>
<div style="overflow:auto;margin-top:8px"><table id="scPar"></table></div>
<div class="mut" style="margin-top:8px" id="scParNota"></div></details></div>
</section>
"""


def js(data):
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    return r"""<script>
/* ==== Pestaña Rider scoring (rider_lv + city_billing del bucket de Glovo) ==== */
(function(){
  const S=""" + payload + r""";
  const seg=document.getElementById('viewSeg'), sec=document.getElementById('viewScoring');
  if(!seg||!sec) return;
  const $=id=>document.getElementById(id);
  const f1=v=>v==null||isNaN(v)?'—':v.toLocaleString('es-ES',{minimumFractionDigits:1,maximumFractionDigits:1});
  const s10=v=>v==null||isNaN(v)?'—':(v*10).toLocaleString('es-ES',{minimumFractionDigits:1,maximumFractionDigits:1});
  const pc=v=>v==null||isNaN(v)?'—':f1(v*100)+'%';
  // [sem,ciudad,rider,nombre,dias,mot,ent,asig,reas,capu,o10,bk,ns,plan,trab,pdx,ndx,vel]
  const R=S.filas.map(a=>({sem:a[0],c:a[1],id:a[2],nm:a[3],dias:a[4],mot:a[5],ent:a[6],asig:a[7],reas:a[8],capu:a[9],o10:a[10],bk:a[11],ns:a[12],plan:a[13],trab:a[14],pdx:a[15],ndx:a[16],vel:a[17]}));
  // Parámetros: peso, objetivo y tolerancia (score 0 % cuando el valor llega a objetivo + tolerancia)
  const P={
    ns:   {lab:'No show',  w:15.0, t:0,     tol:0.10, dir:'low',  unit:'%', m:r=>r.bk?r.ns/r.bk:null, def:'franjas no presentadas ÷ franjas reservadas'},
    rr:   {lab:'RR%',      w:22.5, t:0.035, tol:0.035,dir:'low',  unit:'%', m:r=>r.asig?r.reas/r.asig:null, def:'pedidos reasignados ÷ pedidos asignados'},
    speed:{lab:'Speed',    w:16.3, t:null,  tol:null, dir:'high', unit:'km/h', m:r=>r.vel, def:'velocidad media del rider en km/h, sumando el trayecto hasta el restaurante y el de entrega al cliente'},
    wtd10:{lab:'WTD%',     w:16.3, t:0.05,  tol:0.05, dir:'low',  unit:'%', m:r=>r.ent?r.o10/r.ent:null, def:'entregas con WTD de más de 10 min ÷ entregas completadas'},
    capu: {lab:'CAPU',     w:5.0,  t:0,     tol:0.02, dir:'low',  unit:'%', m:r=>r.ent?r.capu/r.ent:null, def:'pedidos marcados como CAPU (fraude) ÷ entregas completadas'},
    motor:{lab:'Motor',    w:10.0, t:1,     tol:null, dir:'high', unit:'%', m:r=>r.dias?r.mot/r.dias:null, def:'días con vehículo motorizado ÷ días trabajados'},
    pd:   {lab:'PD',       w:5.0,  t:null,  tol:null, dir:'low',  unit:'%', m:r=>r.plan?r.pdx/r.plan:null, def:'horas trabajadas por encima de las planificadas ÷ horas planificadas'},
    nd:   {lab:'ND',       w:10.0, t:null,  tol:null, dir:'low',  unit:'%', m:r=>r.plan?r.ndx/r.plan:null, def:'horas planificadas no trabajadas (incluye no show) ÷ horas planificadas'}
  };
  const K=Object.keys(P);
  const objetivo=(k,r)=>{
    if(k==='speed') return (S.vel_obj[r.sem]||{})[r.c]??null;
    if(k==='pd'||k==='nd'){ if(P[k].t!=null) return P[k].t; const o=S.dev_obj[r.c]; return o?o[k]:null; }
    return P[k].t;
  };
  const puntua=(k,v,t)=>{
    if(v==null||t==null) return null;
    const p=P[k];
    if(p.dir==='high') return t>0?Math.max(0,Math.min(1,v/t)):null;
    if(v<=t+1e-12) return 1;
    const tol=p.tol!=null?p.tol:(t>0?t:0.05);
    return Math.max(0,1-(v-t)/tol);
  };
  const calc=r=>{
    let sw=0,ss=0;const o={};
    K.forEach(k=>{const v=P[k].m(r),t=objetivo(k,r),s=puntua(k,v,t);o[k]={v,t,s};if(s!=null&&P[k].w>0){sw+=P[k].w;ss+=P[k].w*s;}});
    o.score=sw?ss/sw:null;o.cob=sw;return o;
  };
  const sems=[...new Set(R.map(r=>r.sem))].sort();
  const comp=sems.filter(s=>(S.dias_sem||{})[s]>=7);
  const st={sem:(comp.length?comp[comp.length-1]:sems[sems.length-1]),nodo:'ALL',min:10,q:'',sort:'score',asc:true};
  $('scSem').innerHTML=sems.slice().reverse().map(s=>`<option value="${s}" ${s===st.sem?'selected':''}>${s.replace(/^\d+-/,'')}${(S.dias_sem||{})[s]<7?' ('+(S.dias_sem||{})[s]+' días)':''}</option>`).join('');
  const color=s=>s==null?'#F0F2F5':s>=0.9?'#D1FADF':s>=0.75?'#FEF0C7':'#FEE4E2';
  const tcol=s=>s==null?'#6B7280':s>=0.9?'#05603A':s>=0.75?'#93370D':'#B42318';
  function nodos(){
    $('scNodo').innerHTML=['ALL'].concat(S.ciudades).map(c=>`<button data-c="${c}" class="${st.nodo===c?'on':''}">${c==='ALL'?'Todos':c}</button>`).join('');
  }
  function fmt(k,v){ if(v==null) return '—'; return P[k].unit==='km/h'?f1(v):pc(v); }
  function pintar(){
    nodos();
    const rows=R.filter(r=>r.sem===st.sem&&(st.nodo==='ALL'||r.c===st.nodo)&&r.ent>=st.min)
      .filter(r=>!st.q||(r.id+' '+r.nm).toLowerCase().includes(st.q.toLowerCase()))
      .map(r=>({r,o:calc(r)}));
    const key=st.sort;
    const val=x=>key==='score'?x.o.score:key==='id'?x.r.id:key==='c'?x.r.c:key==='ent'?x.r.ent:key==='trab'?x.r.trab:(x.o[key]||{}).s;
    rows.sort((a,b)=>{const va=val(a),vb=val(b);if(va==null&&vb==null)return 0;if(va==null)return 1;if(vb==null)return -1;return (va<vb?-1:va>vb?1:0)*(st.asc?1:-1);});
    const sc=rows.map(x=>x.o.score).filter(v=>v!=null);
    const avg=sc.length?sc.reduce((a,b)=>a+b,0)/sc.length:null;
    const vObj=st.nodo==='ALL'?S.ciudades.map(c=>c+' '+f1((S.vel_obj[st.sem]||{})[c])).join(' · '):f1((S.vel_obj[st.sem]||{})[st.nodo])+' km/h';
    const media=c=>{const v=rows.filter(x=>x.r.c===c&&x.o.score!=null).map(x=>x.o.score);return v.length?v.reduce((a,b)=>a+b,0)/v.length:null;};
    const porNodo=(st.nodo==='ALL'?S.ciudades:[st.nodo]).map(c=>{const m=media(c);return `<div style="border-color:${m==null?'#E4E7EC':tcol(m)}"><b style="color:${tcol(m)}">${s10(m)}</b><span>Score medio ${c} (sobre 10)</span></div>`;}).join('');
    $('scKpi').innerHTML=porNodo+[
      ['Riders',rows.length.toLocaleString('es-ES')],
      ...(st.nodo==='ALL'?[['Score medio total (sobre 10)',s10(avg)]]:[]),
      ['Score ≥ 9',sc.filter(v=>v>=0.9).length],
      ['Score 7,5–9',sc.filter(v=>v>=0.75&&v<0.9).length],
      ['Score &lt; 7,5',sc.filter(v=>v<0.75).length]
    ].map(([a,b])=>`<div><b>${b}</b><span>${a}</span></div>`).join('');
    const esc=t=>String(t).replace(/&/g,'&amp;').replace(/"/g,'&quot;').replace(/</g,'&lt;');
    const tip=k=>{const p=P[k];if(!p)return '';const t=k==='speed'?'media del 10 % más rápido del nodo en la semana':(k==='pd'||k==='nd')&&p.t==null?'el de city_billing de su ciudad ('+S.ciudades.map(c=>c+' '+pc((S.dev_obj[c]||{})[k])).join(', ')+')':(p.unit==='%'?pc(p.t):p.t);return esc(p.lab+': '+p.def.charAt(0).toUpperCase()+p.def.slice(1)+'. Objetivo (100 % del score): '+t+'. Peso: '+f1(p.w)+' %.');};
    const TIPS={id:'Rider ID de Glovo y nombre de la cuenta',c:'Nodo (ciudad) del rider',ent:'Entregas completadas en la semana',trab:'Horas trabajadas en la semana',score:'Score final sobre 10 = 10 × Σ peso × puntuación de cada métrica ÷ Σ pesos de las métricas con dato. 10 = todas las métricas en objetivo; 0 = ninguna.'};
    const th=(k,l,cls)=>`<th class="${cls||''}" data-k="${k}" title="${P[k]?tip(k):esc(TIPS[k]||'')}" style="cursor:help">${l}${st.sort===k?(st.asc?' ▲':' ▼'):''}</th>`;
    $('scTab').innerHTML='<tr>'+th('id','Rider','l')+th('c','Nodo','l')+th('ent','Entregas')+th('trab','Horas')+K.map(k=>th(k,P[k].lab+` <span style="text-transform:none">(${f1(P[k].w)}%)</span>`)).join('')+th('score','Score /10')+'</tr>'+
      rows.map(({r,o})=>`<tr><td class="l"><b>${r.id}</b>${r.nm?`<span class="sub">${r.nm}</span>`:''}</td><td class="l zn">${r.c}</td><td>${r.ent}</td><td>${f1(r.trab)}</td>`+
        K.map(k=>{const x=o[k];return `<td title="${esc(P[k].lab+': '+P[k].def)} · Objetivo ${fmt(k,x.t)}">${fmt(k,x.v)}<span class="sub" style="color:${tcol(x.s)}">${x.s==null?'sin dato':pc(x.s)}</span></td>`;}).join('')+
        `<td><span class="pill" style="background:${color(o.score)};color:${tcol(o.score)}">${s10(o.score)}</span>${o.cob<99.9?`<span class="sub">${f1(o.cob)}% del peso</span>`:''}</td></tr>`).join('')+
      (rows.length?'':'<tr><td class="l mut" colspan="14">Sin riders para este filtro.</td></tr>')+
      (rows.length?(()=>{const mean=a=>{const v=a.filter(x=>x!=null&&!isNaN(x));return v.length?v.reduce((p,q)=>p+q,0)/v.length:null;};
        const BG='background:#E8F1F3;border-top:2px solid #0E5A6B;font-weight:700';
        return `<tr><td class="l" style="${BG}" title="Media simple de los riders mostrados con el filtro actual (semana, nodo, mínimo de entregas y búsqueda). Valor medio de la métrica y, debajo, puntuación media.">Media global<span class="sub">${rows.length} riders</span></td><td class="l" style="${BG}">${st.nodo==='ALL'?'Todos':st.nodo}</td>`+
          `<td style="${BG}">${f1(mean(rows.map(x=>x.r.ent)))}</td><td style="${BG}">${f1(mean(rows.map(x=>x.r.trab)))}</td>`+
          K.map(k=>{const v=mean(rows.map(x=>x.o[k].v)),sc=mean(rows.map(x=>x.o[k].s));return `<td style="${BG}" title="${esc(P[k].lab)}: media de los riders mostrados">${fmt(k,v)}<span class="sub" style="color:${tcol(sc)}">${sc==null?'sin dato':pc(sc)}</span></td>`;}).join('')+
          `<td style="${BG}"><span class="pill" style="background:${color(avg)};color:${tcol(avg)}">${s10(avg)}</span></td></tr>`;})():'');
    $('scSub').textContent=`Bucket de Glovo · rider_lv del ${S.primer_dia} al ${S.ultimo_dia}`+(S.billing?` · objetivos PD/ND de city_billing ${S.billing}`:'')+` · generado ${S.generado}`;
    $('scNota').textContent='Score sobre 10 = 10 × Σ peso × puntuación ÷ Σ pesos de las métricas con dato (10 = todas las métricas en objetivo, 0 = ninguna). Debajo de cada valor, su puntuación (0–100 %). Una métrica sin dato (p. ej. sin pedidos asignados) no cuenta y su peso se reparte. Verde ≥ 9, ámbar 7,5–9, rojo < 7,5. Pulsa una cabecera para ordenar.';
    pintarPar();
  }
  function pintarPar(){
    const dv=st.nodo==='ALL'?S.ciudades.map(c=>{const o=S.dev_obj[c]||{};return c+' '+pc(o.pd)+' / '+pc(o.nd);}).join(' · '):(()=>{const o=S.dev_obj[st.nodo]||{};return pc(o.pd)+' / '+pc(o.nd);})();
    $('scPar').innerHTML='<tr><th class="l">Métrica</th><th>Peso %</th><th>Objetivo (100 %)</th><th>Tolerancia</th><th class="l">Cálculo</th></tr>'+
      K.map(k=>{const p=P[k];
        const tIn=k==='speed'?'<span class="mut">top 10 % del nodo</span>':(k==='pd'||k==='nd')&&p.t==null?`<span class="mut">city_billing</span>`:`<input data-p="${k}" data-f="t" type="number" step="0.1" value="${p.unit==='%'?+(p.t*100).toFixed(2):p.t}">${p.unit==='%'?' %':''}`;
        const tolIn=p.dir==='high'?'<span class="mut">score = valor ÷ objetivo</span>':`<input data-p="${k}" data-f="tol" type="number" step="0.1" value="${p.tol!=null?+(p.tol*100).toFixed(2):''}" placeholder="= obj."> %`;
        return `<tr><td class="l" title="${p.def}" style="cursor:help"><b>${p.lab}</b></td><td><input data-p="${k}" data-f="w" type="number" step="0.1" value="${p.w}"></td><td>${tIn}</td><td>${tolIn}</td><td class="l mut" style="white-space:normal">${p.def}</td></tr>`;}).join('')+
      `<tr><td class="l"><b>Total</b></td><td><b>${f1(K.reduce((a,k)=>a+(+P[k].w||0),0))}</b></td><td colspan="3"></td></tr>`;
    $('scParNota').innerHTML='Puntuación por métrica: si el valor cumple el objetivo, 100 %. Métricas «menos es mejor» (No show, RR%, WTD%, CAPU, PD, ND): bajan en línea recta desde el objetivo hasta 0 % al llegar a objetivo + tolerancia (si la tolerancia está vacía, se usa el propio objetivo, es decir, 0 % al doblarlo). Speed y Motor: valor ÷ objetivo, con tope en 100 %. Objetivos PD / ND de city_billing: '+dv+'. CAPU y Motor no tienen objetivo en el bucket: se toma 0 CAPU y 100 % de días en moto. Los cambios de esta tabla solo afectan a esta pantalla y se pierden al recargar.';
  }
  sec.addEventListener('input',e=>{
    const t=e.target;
    if(t.id==='scMin'){st.min=+t.value||0;pintar();return;}
    if(t.id==='scBus'){st.q=t.value.trim();pintar();return;}
    if(t.dataset.p){const p=P[t.dataset.p],f=t.dataset.f;let v=t.value===''?null:+t.value;
      if(v!=null&&f!=='w'&&(p.unit==='%'||f==='tol'))v=v/100;
      p[f]=f==='w'?(v||0):v;
      const keep=document.activeElement&&document.activeElement.dataset.p?[document.activeElement.dataset.p,document.activeElement.dataset.f]:null;
      pintar();
      if(keep){const el=sec.querySelector(`[data-p="${keep[0]}"][data-f="${keep[1]}"]`);if(el){el.focus();const n=el.value.length;try{el.setSelectionRange(n,n);}catch(_){}}}
    }
  });
  $('scSem').addEventListener('change',e=>{st.sem=e.target.value;pintar();});
  $('scNodo').addEventListener('click',e=>{const b=e.target.closest('button');if(!b)return;st.nodo=b.dataset.c;pintar();});
  $('scTab').addEventListener('click',e=>{const h=e.target.closest('th');if(!h)return;const k=h.dataset.k;if(st.sort===k)st.asc=!st.asc;else{st.sort=k;st.asc=k==='id'||k==='c'||k==='score';}pintar();});
  seg.querySelectorAll('button').forEach(b=>b.addEventListener('click',()=>{
    const on=b.dataset.v==='scoring';
    sec.style.display=on?'':'none';
    if(on){ seg.querySelectorAll('button').forEach(x=>x.setAttribute('aria-pressed',String(x===b)));
      ['viewSemanal','viewDiario','viewLiga','viewTemporal','viewForecast'].forEach(id=>{const e=document.getElementById(id); if(e) e.style.display='none';});
      window.scrollTo(0,0); pintar(); }
  }));
  pintar();
})();
</script>
"""


def integrar(html, data):
    i, j = html.find("<!-- rider_scoring -->"), html.find("<!-- /rider_scoring -->")
    if i >= 0 and j > i: html = html[:i] + html[j + len("<!-- /rider_scoring -->"):]
    html = html.replace(" " + _BTN, "").replace(_BTN, "")
    i = html.find('<section id="viewScoring"')
    if i >= 0: html = html[:i] + html[html.find("</section>", i) + len("</section>"):]
    seg = html.find('id="viewSeg"'); end = html.find("</div>", seg)
    if seg < 0 or end < 0 or '<div id="viewSemanal">' not in html or "</body>" not in html:
        raise ValueError("la plantilla no tiene el selector de Vista esperado")
    html = html[:end] + "  " + _BTN + "\n      " + html[end:]
    html = html.replace('<div id="viewSemanal">', seccion() + '  <div id="viewSemanal">', 1)
    k = html.rindex("</body>")
    return html[:k] + "<!-- rider_scoring -->" + js(data) + "<!-- /rider_scoring -->\n" + html[k:]


def main():
    global CIUDADES, CARPETA
    html_p = sys.argv[1]
    CARPETA = sys.argv[2] if len(sys.argv) > 2 else "gra-mad-nom-alc"
    CIUDADES = DASH[CARPETA]
    data = datos()
    h = open(html_p, encoding="utf-8").read()
    open(html_p, "w", encoding="utf-8").write(integrar(h, data))
    print(f"rider_scoring {CARPETA}: {len(data['filas'])} rider-semanas · {data['primer_dia']}..{data['ultimo_dia']} · "
          f"speed obj {data['vel_obj'].get(max(data['vel_obj'] or ['']), {})} · PD/ND {data['dev_obj']}")


if __name__ == "__main__":
    main()
