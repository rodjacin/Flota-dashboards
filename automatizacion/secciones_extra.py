# -*- coding: utf-8 -*-
"""
================================================================================
 Secciones extra para pestañas existentes de los dashboards de flota
================================================================================
 · motivos()     -> pestaña Incidencias: responsable y motivo de cancelaciones;
                    motivo del contacto (3 niveles) y resultado del reembolso.
 · cobertura()   -> pestaña No show: horas planificadas vs trabajadas, franjas
                    reservadas y no presentadas, horas no elegibles, trabajo nocturno.
 · utr_franja()  -> pestaña UTR: UTR por hora con el tiempo disponible real (shift_lv).
 · liveops()     -> pestaña En vivo: histórico de Live Operations (retrasos, pausas,
                    aceptación, monedero, motivo del estado) que acumula el muestreo
                    cada 5 min en <dashboard>/liveops_hist.json.
 Todas: datos del bucket GCP de las últimas 8 semanas (llegan con 1 día de retraso),
 sin coordenadas. añadir(html, seccion) inserta la sección al final de la pestaña.
================================================================================
"""
import os, csv, json, datetime as dt, collections

NODE_ALIASES = {"NEM": "MAD"}
BASE = os.path.expanduser("~/Downloads/fleet_data_combinado")
DIAS = 56


def _city(v):
    v = (v or "").strip()
    return NODE_ALIASES.get(v, v)


def _f(v):
    try:
        return float(v)
    except Exception:
        return 0.0


def _ts(v):
    try:
        return dt.datetime.fromisoformat(str(v).strip()[:19])
    except Exception:
        return None


def _desde():
    return (dt.date.today() - dt.timedelta(days=DIAS)).isoformat()


def _rows(name):
    p = os.path.join(BASE, name + "_combinado.csv")
    if not os.path.isfile(p):
        return
    with open(p, encoding="utf-8-sig") as fh:
        for x in csv.DictReader(fh):
            yield x


def añadir(html, seccion):
    if not seccion or "</body>" not in html:
        return html
    i = html.rindex("</body>")
    return html[:i] + seccion + html[i:]


CSS = r"""<style>
.xs{background:#fff;border:1px solid #E4E7EC;border-radius:12px;padding:14px;margin-top:16px;display:flex;flex-direction:column;gap:12px;font-family:"Inter",-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;color:#14171F;font-size:14px}
.xs h2{font-size:12px;letter-spacing:.06em;text-transform:uppercase;font-weight:650;margin:0}
.xs h3{font-size:11.5px;letter-spacing:.05em;text-transform:uppercase;font-weight:650;margin:6px 0 0;color:#4B5563}
.xs .xsub{color:#4B5563;font-size:12.5px;margin:4px 0 0;line-height:1.5}
.xs .xhead{display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap;align-items:flex-end}
.xs .xfil{display:flex;gap:12px;flex-wrap:wrap;align-items:flex-end}
.xs .xfg{display:flex;flex-direction:column;gap:5px}.xs .xfg>span{font-family:ui-monospace,monospace;font-size:10.5px;letter-spacing:.07em;text-transform:uppercase;color:#6B7280}
.xs select{font:inherit;font-size:13px;padding:6px 9px;border:1px solid #E4E7EC;border-radius:8px;background:#fff;color:#14171F}
.xs .xk{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:10px}
.xs .xk div{border:1px solid #E4E7EC;border-radius:10px;padding:10px 12px;display:flex;flex-direction:column;gap:3px}
.xs .xk em{font-style:normal;font-family:ui-monospace,monospace;font-size:10.5px;letter-spacing:.06em;text-transform:uppercase;color:#6B7280}
.xs .xk b{font-size:20px;font-weight:650;font-family:ui-monospace,monospace}.xs .xk span{font-size:12px;color:#4B5563}
.xs .xtw{overflow-x:auto;max-height:460px}
.xs table{border-collapse:collapse;width:100%}
.xs th,.xs td{padding:6px 9px;text-align:left;border-bottom:1px solid #E4E7EC;white-space:nowrap;font-size:12.5px}
.xs th{font-family:ui-monospace,monospace;font-size:10px;letter-spacing:.05em;text-transform:uppercase;color:#6B7280;font-weight:500;position:sticky;top:0;background:#fff;cursor:pointer}
.xs td.n,.xs th.n{text-align:right;font-family:ui-monospace,monospace}
.xs .hb{display:flex;align-items:center;gap:8px}.xs .hb i{display:block;height:12px;border-radius:3px;background:#0E5A6B;min-width:2px}
.xs .p{display:inline-block;padding:1px 8px;border-radius:99px;font-size:11.5px;font-weight:600}
.xs .p.r{background:#FDECEA;color:#C2362F}.xs .p.a{background:#FFF4DB;color:#8A5A00}.xs .p.g{background:#E7F6EC;color:#0A7A3E}
.xs .muted{color:#6B7280}.xs .empty{color:#6B7280;padding:10px 0}
.xs .two{display:grid;grid-template-columns:1fr 1fr;gap:16px}@media(max-width:900px){.xs .two{grid-template-columns:1fr}}
.xs .bars{display:flex;align-items:flex-end;gap:4px;height:170px;padding-top:16px}
.xs .bar{flex:1 0 14px;display:flex;flex-direction:column;align-items:center;justify-content:flex-end;height:100%;gap:3px}
.xs .bar i{display:block;width:100%;background:#0E5A6B;border-radius:3px 3px 0 0;min-height:1px}.xs .bar b{font-size:9.5px;font-family:ui-monospace,monospace}
.xs .bar span{font-size:9.5px;color:#6B7280}
.xs .note{color:#6B7280;font-size:11.5px;line-height:1.5;margin:0}
</style>"""

JS_COMMON = r"""
const $x=id=>document.getElementById(id);
const xesc=s=>String(s??'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const xnf=(v,d=0)=>v==null||!isFinite(v)?'—':Number(v).toLocaleString('es-ES',{minimumFractionDigits:d,maximumFractionDigits:d});
function xisoW(s){const t=new Date(s+'T00:00:00Z');const dn=(t.getUTCDay()+6)%7;t.setUTCDate(t.getUTCDate()-dn+3);const y=t.getUTCFullYear();const f=new Date(Date.UTC(y,0,4));return y+'-W'+String(1+Math.round(((t-f)/864e5-3+((f.getUTCDay()+6)%7))/7)).padStart(2,'0');}
const XDOW=['dom','lun','mar','mié','jue','vie','sáb'];
const xdlab=s=>{const d=new Date(s+'T00:00:00Z');return XDOW[d.getUTCDay()]+' '+s.slice(8,10)+'/'+s.slice(5,7);};
function xsel(id,opts,val){$x(id).innerHTML=opts.map(o=>`<option value="${xesc(o[0])}" ${String(o[0])===String(val)?'selected':''}>${xesc(o[1])}</option>`).join('');}
function xtable(id,cols,rows,st,empty,lim,rerender){
  const col=cols.find(c=>c.k===st.k)||cols[0];
  const s=rows.slice().sort((a,b)=>{const x=col.v(a),y=col.v(b);return (typeof x==='string'?String(x).localeCompare(y,'es'):(x??-1e9)-(y??-1e9))*st.d;}).slice(0,lim||1e9);
  $x(id).innerHTML=!s.length?`<tbody><tr><td class="empty">${empty}</td></tr></tbody>`:'<thead><tr>'+cols.map(c=>`<th class="${c.n?'n':''}" data-k="${c.k}" title="${xesc(c.d||'')}">${c.h}${st.k===c.k?(st.d<0?' ▼':' ▲'):''}</th>`).join('')+'</tr></thead><tbody>'+s.map(r=>'<tr>'+cols.map(c=>`<td class="${c.n?'n':''}">${c.f(r)}</td>`).join('')+'</tr>').join('')+'</tbody>';
  $x(id).querySelectorAll('th[data-k]').forEach(th=>th.onclick=()=>{const k=th.dataset.k;if(st.k===k)st.d*=-1;else{st.k=k;st.d=cols.find(c=>c.k===k).n?-1:1;}rerender();});}
"""


def _seccion(uid, data, body, js):
    return (CSS + body + "<script>(function(){\nconst X=" +
            json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c") +
            ";\n" + JS_COMMON + js + "\n})();</script>")


# =============================================================================
# 1 · Motivos de cancelación y reembolsos  (pestaña Incidencias)
# =============================================================================
OWNER = {"TRANSPORT": "Rider / reparto", "VENDOR": "Restaurante", "CUSTOMER": "Cliente", "PLATFORM": "Glovo", "": "Sin dato"}
REASON = {"UNABLE_TO_FIND": "No encuentra la dirección / al cliente", "MISTAKE_ERROR": "Error", "ITEM_UNAVAILABLE": "Producto no disponible",
          "CLOSED": "Restaurante cerrado", "UNPROFESSIONAL_BEHAVIOUR": "Comportamiento no profesional", "NO_COURIER": "Sin rider",
          "WRONG_ORDER_ITEMS_DELIVERED": "Pedido equivocado", "LATE_DELIVERY": "Entrega tarde", "TOO_BUSY": "Restaurante saturado",
          "ADDRESS_INCOMPLETE_MISSTATED": "Dirección incompleta", "UNREACHABLE": "Cliente ilocalizable", "": "Sin motivo"}
OUTCOME = {"refund_compensate": "Compensación", "full_refund": "Reembolso total", "partial_refund": "Reembolso parcial"}


def motivos(cities):
    cs, desde = set(cities), _desde()
    canc, ref = collections.Counter(), []
    for x in _rows("delivery_lv") or []:
        c, f = _city(x.get("city_code")), (x.get("fecha") or "")[:10]
        if c not in cs or f < desde:
            continue
        if x.get("delivery_status") == "cancelled":
            canc[(f, c, x.get("cancellation_owner") or "", x.get("cancellation_reason") or "")] += 1
        if x.get("fraud_contact_reason_l1") or x.get("refund_outcome") or x.get("refund_purpose"):
            ref.append([f, c, str(x.get("rider_id") or ""), x.get("fraud_contact_reason_l1") or "", x.get("fraud_contact_reason_l2") or "",
                        x.get("fraud_contact_reason_l3") or "", x.get("refund_outcome") or "", x.get("refund_purpose") or "",
                        round(_f(x.get("fraud_cost_eur")), 2), x.get("store_name") or ""])
    if not canc and not ref:
        return None
    data = {"cities": sorted(cs), "canc": [list(k) + [n] for k, n in canc.items()], "ref": ref,
            "owner": OWNER, "reason": REASON, "outcome": OUTCOME}
    body = """
<section class="xs" id="xsMot">
  <div class="xhead"><div><h2>Motivos: cancelaciones y reembolsos</h2><p class="xsub">Del bucket de Glovo (pedido a pedido, llega con 1 día de retraso) · últimas 8 semanas. Responde a <b>quién</b> canceló y <b>por qué</b>, y si la queja del cliente acabó en reembolso.</p></div>
    <div class="xfil"><div class="xfg"><span>Área</span><select id="xmC"></select></div><div class="xfg"><span>Semana</span><select id="xmW"></select></div></div></div>
  <div class="xk" id="xmK"></div>
  <div class="two">
    <div><h3>Cancelaciones por responsable</h3><div id="xmO"></div></div>
    <div><h3>Motivos de cancelación</h3><div class="xtw" style="max-height:300px"><table id="xmR"></table></div></div>
  </div>
  <h3>Quejas y reembolsos (motivo del contacto en 3 niveles)</h3>
  <div class="xtw"><table id="xmF"></table></div>
  <p class="note">«Rider / reparto» = cancelación atribuida al transporte (TRANSPORT). Coste = importe que Glovo asocia al fraude o reembolso.</p>
</section>"""
    js = r"""
const S={c:'ALL',w:'ALL',sr:{k:'n',d:-1},sf:{k:'f',d:-1}};
const C=X.canc.map(r=>({f:r[0],c:r[1],o:r[2],r:r[3],n:r[4],w:xisoW(r[0])})), F=X.ref.map(r=>({f:r[0],c:r[1],rid:r[2],l1:r[3],l2:r[4],l3:r[5],oc:r[6],pu:r[7],cost:r[8],st:r[9],w:xisoW(r[0])}));
function R(){
  xsel('xmC',[['ALL','Todas']].concat(X.cities.map(c=>[c,c])),S.c);
  const ws=[...new Set(C.map(r=>r.w).concat(F.map(r=>r.w)))].sort().reverse();
  xsel('xmW',[['ALL','Todas']].concat(ws.map(w=>[w,w.slice(5)])),S.w);
  const ok=r=>(S.c==='ALL'||r.c===S.c)&&(S.w==='ALL'||r.w===S.w);
  const c=C.filter(ok), f=F.filter(ok), tot=c.reduce((a,r)=>a+r.n,0);
  const by=k=>{const m={};c.forEach(r=>m[r[k]]=(m[r[k]]||0)+r.n);return m;};
  const O=by('o'), rid=O['TRANSPORT']||0;
  $x('xmK').innerHTML=[['Cancelaciones',xnf(tot),''],['Atribuidas al rider',xnf(rid),tot?xnf(rid/tot*100,0)+' %':''],
    ['Restaurante',xnf(O['VENDOR']||0),tot?xnf((O['VENDOR']||0)/tot*100,0)+' %':''],['Cliente',xnf(O['CUSTOMER']||0),tot?xnf((O['CUSTOMER']||0)/tot*100,0)+' %':''],
    ['Reembolsos por queja',xnf(f.length),xnf(f.reduce((a,r)=>a+r.cost,0),0)+' €']].map(k=>`<div><em>${k[0]}</em><b>${k[1]}</b><span>${k[2]}</span></div>`).join('');
  const om=Math.max(1,...Object.values(O));
  $x('xmO').innerHTML=Object.entries(O).sort((a,b)=>b[1]-a[1]).map(([k,v])=>`<div class="hb" style="margin:6px 0"><span style="width:130px">${xesc(X.owner[k]||k)}</span><i style="width:${v/om*60}%;background:${k==='TRANSPORT'?'#C2362F':'#0E5A6B'}"></i><b class="muted">${v} · ${xnf(v/tot*100,0)} %</b></div>`).join('')||'<p class="empty">Sin cancelaciones.</p>';
  const RM={};c.forEach(r=>{const k=r.r+'|'+r.o;RM[k]=RM[k]||{r:r.r,o:r.o,n:0};RM[k].n+=r.n;});
  xtable('xmR',[{k:'r',h:'Motivo',v:x=>X.reason[x.r]||x.r,f:x=>xesc(X.reason[x.r]||x.r)},{k:'o',h:'Responsable',v:x=>x.o,f:x=>x.o==='TRANSPORT'?'<span class="p r">Rider</span>':xesc(X.owner[x.o]||x.o)},{k:'n',h:'Pedidos',n:1,v:x=>x.n,f:x=>xnf(x.n)}],Object.values(RM),S.sr,'Sin cancelaciones.',0,R);
  xtable('xmF',[{k:'f',h:'Día',v:x=>x.f,f:x=>xdlab(x.f)},{k:'c',h:'Área',v:x=>x.c,f:x=>xesc(x.c)},{k:'rid',h:'Rider',v:x=>Number(x.rid)||0,f:x=>xesc(x.rid)},
    {k:'l1',h:'Motivo (nivel 1)',v:x=>x.l1,f:x=>xesc(x.l1)},{k:'l2',h:'Nivel 2',v:x=>x.l2,f:x=>xesc(x.l2)},{k:'l3',h:'Nivel 3',v:x=>x.l3,f:x=>xesc(x.l3)},
    {k:'oc',h:'Resultado',v:x=>x.oc,f:x=>`<span class="p ${x.oc==='full_refund'?'r':'a'}">${xesc(X.outcome[x.oc]||x.oc||'—')}</span>`},{k:'cost',h:'Coste',n:1,v:x=>x.cost,f:x=>xnf(x.cost,2)+' €'},{k:'st',h:'Tienda',v:x=>x.st,f:x=>xesc(x.st)}],
    f,S.sf,'Sin reembolsos en este filtro.',500,R);
}
$x('xmC').onchange=e=>{S.c=e.target.value;R();};$x('xmW').onchange=e=>{S.w=e.target.value;R();};R();"""
    return _seccion("mot", data, body, js)


# =============================================================================
# 2 · Cobertura de horas y franjas  (pestaña No show)
# =============================================================================
def cobertura(cities):
    cs, desde = set(cities), _desde()
    A = collections.defaultdict(lambda: [0.0] * 9)
    for x in _rows("rider_lv") or []:
        c, f = _city(x.get("city_code")), (x.get("fecha") or "")[:10]
        if c not in cs or f < desde:
            continue
        g = A[(str(x.get("rider_id") or ""), c, f)]
        for i, k in enumerate(("planned_working_time", "total_worked_hours", "total_booked_shifts", "total_no_shows",
                               "total_ineligibility_hrs", "total_night_deliveries_completed", "total_night_worked_hours",
                               "total_deliveries_completed", "total_slots")):
            g[i] += _f(x.get(k))
    if not A:
        return None
    rows = [[k[0], k[1], k[2]] + [round(v, 2) for v in g] for k, g in A.items() if any(g)]
    data = {"cities": sorted(cs), "rows": rows}
    body = """
<section class="xs" id="xsCob">
  <div class="xhead"><div><h2>Cobertura de las horas comprometidas</h2><p class="xsub">Horas planificadas frente a trabajadas, franjas de 30 min reservadas y no presentadas, horas no elegibles y trabajo nocturno · bucket de Glovo, últimas 8 semanas (1 día de retraso).</p></div>
    <div class="xfil"><div class="xfg"><span>Área</span><select id="xcC"></select></div><div class="xfg"><span>Semana</span><select id="xcW"></select></div></div></div>
  <div class="xk" id="xcK"></div>
  <div class="xtw"><table id="xcT"></table></div>
  <p class="note">Cobertura = horas trabajadas ÷ horas planificadas (en rojo por debajo del 90 %, ámbar del 90 al 97 %). No show = franjas no presentadas ÷ franjas reservadas. Nocturno = entregas y horas de noche según Glovo.</p>
</section>"""
    js = r"""
const S={c:'ALL',w:'ALL',st:{k:'cov',d:1}};
const R0=X.rows.map(r=>({rid:r[0],c:r[1],f:r[2],pl:r[3],wk:r[4],bk:r[5],ns:r[6],ie:r[7],nd:r[8],nh:r[9],dl:r[10],w:xisoW(r[2])}));
const cp=v=>v==null?'':(v<.9?'r':(v<.97?'a':'g'));
function R(){
  xsel('xcC',[['ALL','Todas']].concat(X.cities.map(c=>[c,c])),S.c);
  const ws=[...new Set(R0.map(r=>r.w))].sort().reverse();xsel('xcW',[['ALL','Todas']].concat(ws.map(w=>[w,w.slice(5)])),S.w);
  const A=R0.filter(r=>(S.c==='ALL'||r.c===S.c)&&(S.w==='ALL'||r.w===S.w));
  const s=k=>A.reduce((a,r)=>a+r[k],0);
  const pl=s('pl'),wk=s('wk'),bk=s('bk'),ns=s('ns'),ie=s('ie'),nd=s('nd'),nh=s('nh'),dl=s('dl');
  $x('xcK').innerHTML=[['Cobertura de horas',pl?xnf(wk/pl*100,1)+' %':'—',xnf(wk,0)+' h de '+xnf(pl,0)+' h planificadas'],['No show (franjas)',bk?xnf(ns/bk*100,1)+' %':'—',xnf(ns)+' de '+xnf(bk)+' franjas'],
    ['Horas no elegibles',xnf(ie,0)+' h',wk?xnf(ie/wk*100,1)+' % de las trabajadas':''],['Entregas nocturnas',xnf(nd),dl?xnf(nd/dl*100,1)+' % del total':''],
    ['UTR nocturno',nh?xnf(nd/nh,2):'—',xnf(nh,0)+' h de noche · UTR total '+(wk?xnf(dl/wk,2):'—')]].map(k=>`<div><em>${k[0]}</em><b>${k[1]}</b><span>${k[2]}</span></div>`).join('');
  const M={};A.forEach(r=>{const m=M[r.rid]||(M[r.rid]={rid:r.rid,c:r.c,pl:0,wk:0,bk:0,ns:0,ie:0,nd:0,nh:0,dl:0});['pl','wk','bk','ns','ie','nd','nh','dl'].forEach(k=>m[k]+=r[k]);});
  const L=Object.values(M).filter(m=>m.pl>0||m.wk>0).map(m=>({...m,cov:m.pl?m.wk/m.pl:null,nsr:m.bk?m.ns/m.bk:null}));
  xtable('xcT',[{k:'rid',h:'Rider',v:m=>Number(m.rid)||0,f:m=>xesc(m.rid)},{k:'c',h:'Área',v:m=>m.c,f:m=>xesc(m.c)},
    {k:'pl',h:'H planificadas',n:1,v:m=>m.pl,f:m=>xnf(m.pl,1)},{k:'wk',h:'H trabajadas',n:1,v:m=>m.wk,f:m=>xnf(m.wk,1)},
    {k:'cov',h:'Cobertura',n:1,v:m=>m.cov,f:m=>m.cov==null?'—':`<span class="p ${cp(m.cov)}">${xnf(m.cov*100,0)} %</span>`,d:'Horas trabajadas ÷ planificadas'},
    {k:'bk',h:'Franjas reservadas',n:1,v:m=>m.bk,f:m=>xnf(m.bk)},{k:'ns',h:'No presentadas',n:1,v:m=>m.ns,f:m=>m.ns?`<b>${xnf(m.ns)}</b>`:''},
    {k:'nsr',h:'No show %',n:1,v:m=>m.nsr,f:m=>m.nsr==null?'—':xnf(m.nsr*100,1)+' %'},{k:'ie',h:'H no elegibles',n:1,v:m=>m.ie,f:m=>m.ie?xnf(m.ie,1):''},
    {k:'nd',h:'Entregas noche',n:1,v:m=>m.nd,f:m=>m.nd?xnf(m.nd):''},{k:'nh',h:'H noche',n:1,v:m=>m.nh,f:m=>m.nh?xnf(m.nh,1):''}],L,S.st,'Sin datos en este filtro.',0,R);
}
$x('xcC').onchange=e=>{S.c=e.target.value;R();};$x('xcW').onchange=e=>{S.w=e.target.value;R();};R();"""
    return _seccion("cob", data, body, js)


# =============================================================================
# 3 · UTR por franja con tiempo disponible real  (pestaña UTR)
# =============================================================================
def utr_franja(cities):
    cs, desde = set(cities), _desde()
    AV = collections.defaultdict(float)
    for x in _rows("shift_lv") or []:
        c, f = _city(x.get("city_code")), (x.get("fecha") or "")[:10]
        if c not in cs or f < desde:
            continue
        a, b = _ts(x.get("interval_start")), _ts(x.get("interval_finish"))
        if not a or not b or b <= a:
            continue
        t = a
        while t < b:
            nxt = min(b, (t.replace(minute=0, second=0, microsecond=0) + dt.timedelta(hours=1)))
            AV[(t.date().isoformat(), c, t.hour)] += (nxt - t).total_seconds() / 3600
            t = nxt
    DL = collections.Counter()
    for x in _rows("delivery_lv") or []:
        if x.get("delivery_status") != "completed":
            continue
        c, f = _city(x.get("city_code")), (x.get("fecha") or "")[:10]
        if c not in cs or f < desde:
            continue
        b = _ts(x.get("rider_dropped_off_local_at"))
        if b:
            DL[(b.date().isoformat(), c, b.hour)] += 1
    keys = set(AV) | set(DL)
    if not keys:
        return None
    rows = [[k[0], k[1], k[2], round(AV.get(k, 0.0), 2), DL.get(k, 0)] for k in sorted(keys)]
    data = {"cities": sorted(cs), "rows": rows}
    body = """
<section class="xs" id="xsUtr">
  <div class="xhead"><div><h2>UTR por hora con tiempo disponible real</h2><p class="xsub">Entregas ÷ horas en las que el rider estaba realmente disponible (intervalos de conexión de la tabla de turnos), por hora del día · bucket de Glovo, últimas 8 semanas.</p></div>
    <div class="xfil"><div class="xfg"><span>Área</span><select id="xuC"></select></div><div class="xfg"><span>Semana</span><select id="xuW"></select></div><div class="xfg"><span>Día</span><select id="xuD"></select></div></div></div>
  <div class="xk" id="xuK"></div>
  <div class="bars" id="xuB"></div>
  <div class="xtw" style="max-height:340px"><table id="xuT"></table></div>
  <p class="note">Cada barra es el UTR de esa hora: entregas completadas ÷ horas disponibles. Una hora con mucho tiempo disponible y UTR bajo indica riders de más; UTR muy alto, riders de menos.</p>
</section>"""
    js = r"""
const S={c:'ALL',w:'ALL',d:'ALL',st:{k:'h',d:1}};
const R0=X.rows.map(r=>({f:r[0],c:r[1],h:r[2],av:r[3],dl:r[4],w:xisoW(r[0]),dw:(new Date(r[0]+'T00:00:00Z').getUTCDay()+6)%7}));
const DW=['Lunes','Martes','Miércoles','Jueves','Viernes','Sábado','Domingo'];
function R(){
  xsel('xuC',[['ALL','Todas']].concat(X.cities.map(c=>[c,c])),S.c);
  const ws=[...new Set(R0.map(r=>r.w))].sort().reverse();xsel('xuW',[['ALL','Todas']].concat(ws.map(w=>[w,w.slice(5)])),S.w);
  xsel('xuD',[['ALL','Todos']].concat(DW.map((d,i)=>[i,d])),S.d);
  const A=R0.filter(r=>(S.c==='ALL'||r.c===S.c)&&(S.w==='ALL'||r.w===S.w)&&(S.d==='ALL'||r.dw===+S.d));
  const H=Array.from({length:24},(_,h)=>({h,av:0,dl:0}));A.forEach(r=>{H[r.h].av+=r.av;H[r.h].dl+=r.dl;});
  const av=H.reduce((a,x)=>a+x.av,0),dl=H.reduce((a,x)=>a+x.dl,0);
  const L=H.filter(x=>x.av>0||x.dl>0).map(x=>({...x,u:x.av?x.dl/x.av:null}));
  const best=L.filter(x=>x.av>=5).sort((a,b)=>a.u-b.u);
  $x('xuK').innerHTML=[['UTR sobre tiempo disponible',av?xnf(dl/av,2):'—',xnf(dl)+' entregas · '+xnf(av,0)+' h disponibles'],
    ['Hora con UTR más bajo',best.length?String(best[0].h).padStart(2,'0')+':00':'—',best.length?'UTR '+xnf(best[0].u,2)+' · '+xnf(best[0].av,0)+' h disponibles':''],
    ['Hora con UTR más alto',best.length?String(best[best.length-1].h).padStart(2,'0')+':00':'—',best.length?'UTR '+xnf(best[best.length-1].u,2):'']].map(k=>`<div><em>${k[0]}</em><b>${k[1]}</b><span>${k[2]}</span></div>`).join('');
  const mx=Math.max(.01,...L.map(x=>x.u||0));
  $x('xuB').innerHTML=H.map(x=>{const u=x.av?x.dl/x.av:0;return `<div class="bar" title="${String(x.h).padStart(2,'0')}:00 · UTR ${xnf(u,2)} · ${xnf(x.dl)} entregas en ${xnf(x.av,1)} h"><b>${x.av?xnf(u,1):''}</b><i style="height:${u/mx*120}px;opacity:${x.av?1:.2}"></i><span>${String(x.h).padStart(2,'0')}</span></div>`;}).join('');
  xtable('xuT',[{k:'h',h:'Hora',v:x=>x.h,f:x=>String(x.h).padStart(2,'0')+':00–'+String(x.h).padStart(2,'0')+':59'},{k:'av',h:'H disponibles',n:1,v:x=>x.av,f:x=>xnf(x.av,1)},
    {k:'dl',h:'Entregas',n:1,v:x=>x.dl,f:x=>xnf(x.dl)},{k:'u',h:'UTR real',n:1,v:x=>x.u,f:x=>x.u==null?'—':xnf(x.u,2)}],L,S.st,'Sin datos en este filtro.',0,R);
}
$x('xuC').onchange=e=>{S.c=e.target.value;R();};$x('xuW').onchange=e=>{S.w=e.target.value;R();};$x('xuD').onchange=e=>{S.d=e.target.value;R();};R();"""
    return _seccion("utr", data, body, js)


# =============================================================================
# 4 · Histórico de Live Operations  (pestaña En vivo) · datos: liveops_hist.json
# =============================================================================
def liveops(cities):
    data = {"cities": sorted(set(NODE_ALIASES.get(c, c) for c in cities))}
    body = """
<section class="xs" id="xsLo">
  <div class="xhead"><div><h2>Histórico de Live Operations</h2><p class="xsub" id="xlSub">Lo que la foto en vivo enseña solo un momento, acumulado con el muestreo de cada ~5 min: retrasos de conexión, pausas, aceptación de pedidos, monedero por encima del límite y motivo del estado.</p></div>
    <div class="xfil"><div class="xfg"><span>Área</span><select id="xlC"></select></div><div class="xfg"><span>Semana</span><select id="xlW"></select></div><div class="xfg"><span>Fecha</span><select id="xlD"></select></div></div></div>
  <div class="xk" id="xlK"></div>
  <div class="xtw"><table id="xlT"></table></div>
  <h3>Motivos del estado</h3>
  <div class="xtw" style="max-height:260px"><table id="xlM"></table></div>
  <p class="note">Minutos ≈ nº de fotos en ese estado × 5. Aceptación = pedidos aceptados ÷ notificados (último valor del día). Monedero sobre el límite = fotos con el saldo de efectivo por encima del límite de Glovo (el rider puede dejar de recibir pedidos).</p>
</section>"""
    js = r"""
const S={c:'ALL',w:'ALL',d:'ALL',st:{k:'late',d:-1},sm:{k:'n',d:-1}};let R0=[],MOT=[];
function load(){try{fetch(new URL('liveops_hist.json?t='+Date.now(),document.baseURI),{cache:'no-store'}).then(r=>r.ok?r.json():null).then(j=>{
  if(!j||!j.dias){$x('xlSub').textContent+=' Todavía no hay histórico: empieza a acumularse con el muestreo.';return;}
  R0=[];MOT=[];Object.entries(j.dias).forEach(([f,rs])=>Object.entries(rs).forEach(([rid,v])=>{if(!X.cities.includes(v[0]))return;
    R0.push({f,w:xisoW(f),rid,c:v[0],nm:v[1],n:v[2],late:v[3],brk:v[4],brkn:v[5],brks:v[6],nt:v[7],ac:v[8],ar:v[9],ol:v[10],wal:v[11]});
    Object.entries(v[12]||{}).forEach(([m,k])=>MOT.push({f,w:xisoW(f),c:v[0],rid,m,n:k}));}));
  R();}).catch(()=>{});}catch(e){}}
function R(){
  xsel('xlC',[['ALL','Todas']].concat(X.cities.map(c=>[c,c])),S.c);
  const ws=[...new Set(R0.map(r=>r.w))].sort().reverse();xsel('xlW',[['ALL','Todas']].concat(ws.map(w=>[w,w.slice(5)])),S.w);
  const ds=[...new Set(R0.filter(r=>S.w==='ALL'||r.w===S.w).map(r=>r.f))].sort().reverse();if(S.d!=='ALL'&&!ds.includes(S.d))S.d='ALL';
  xsel('xlD',[['ALL','Todas']].concat(ds.map(d=>[d,xdlab(d)])),S.d);
  const ok=r=>(S.c==='ALL'||r.c===S.c)&&(S.w==='ALL'||r.w===S.w)&&(S.d==='ALL'||r.f===S.d);
  const A=R0.filter(ok);
  const M={};A.forEach(r=>{const m=M[r.rid]||(M[r.rid]={rid:r.rid,nm:r.nm,c:r.c,dias:0,n:0,late:0,brk:0,brkn:0,brks:0,nt:0,ac:0,ol:0,wal:0});
    m.dias++;m.n+=r.n;m.late+=r.late;m.brk+=r.brk;m.brkn+=r.brkn;m.brks+=r.brks;m.nt+=r.nt;m.ac+=r.ac;m.ol+=r.ol;m.wal=Math.max(m.wal,r.wal);if(r.nm)m.nm=r.nm;});
  const L=Object.values(M);
  const s=k=>L.reduce((a,m)=>a+m[k],0);
  $x('xlK').innerHTML=[['Riders con retraso',xnf(L.filter(m=>m.late>0).length),xnf(s('late')*5)+' min en estado «con retraso»'],
    ['Pausas',xnf(s('brkn')),xnf(s('brks')/60)+' min en pausa'],['Aceptación',s('nt')?xnf(s('ac')/s('nt')*100,1)+' %':'—',xnf(s('ac'))+' de '+xnf(s('nt'))+' notificados'],
    ['Monedero sobre el límite',xnf(L.filter(m=>m.ol>0).length)+' riders',xnf(s('ol')*5)+' min bloqueables']].map(k=>`<div><em>${k[0]}</em><b>${k[1]}</b><span>${k[2]}</span></div>`).join('');
  xtable('xlT',[{k:'rid',h:'Rider',v:m=>Number(m.rid)||0,f:m=>xesc(m.rid)+(m.nm?` <span class="muted">${xesc(m.nm)}</span>`:'')},{k:'c',h:'Área',v:m=>m.c,f:m=>xesc(m.c)},
    {k:'dias',h:'Días',n:1,v:m=>m.dias,f:m=>xnf(m.dias)},{k:'late',h:'Min con retraso',n:1,v:m=>m.late,f:m=>m.late?`<span class="p ${m.late*5>=30?'r':'a'}">${xnf(m.late*5)}</span>`:''},
    {k:'brkn',h:'Pausas',n:1,v:m=>m.brkn,f:m=>m.brkn?xnf(m.brkn):''},{k:'brks',h:'Min en pausa',n:1,v:m=>m.brks,f:m=>m.brks?xnf(m.brks/60):''},
    {k:'ar',h:'Aceptación',n:1,v:m=>m.nt?m.ac/m.nt:null,f:m=>m.nt?`<span class="p ${m.ac/m.nt<.9?'r':(m.ac/m.nt<.97?'a':'g')}">${xnf(m.ac/m.nt*100,0)} %</span>`:'—'},
    {k:'nt',h:'Notificados',n:1,v:m=>m.nt,f:m=>xnf(m.nt)},{k:'ol',h:'Min sobre límite',n:1,v:m=>m.ol,f:m=>m.ol?`<span class="p r">${xnf(m.ol*5)}</span>`:''},
    {k:'wal',h:'Saldo máx.',n:1,v:m=>m.wal,f:m=>m.wal?xnf(m.wal,2)+' €':''}],L,S.st,'Sin histórico en este filtro todavía.',0,R);
  const MM={};MOT.filter(ok).forEach(x=>{MM[x.m]=MM[x.m]||{m:x.m,n:0,r:new Set()};MM[x.m].n+=x.n;MM[x.m].r.add(x.rid);});
  xtable('xlM',[{k:'m',h:'Estado · motivo',v:x=>x.m,f:x=>xesc(x.m)},{k:'n',h:'Min aprox.',n:1,v:x=>x.n,f:x=>xnf(x.n*5)},{k:'r',h:'Riders',n:1,v:x=>x.r.size,f:x=>xnf(x.r.size)}],Object.values(MM),S.sm,'Sin motivos registrados.',0,R);
}
$x('xlC').onchange=e=>{S.c=e.target.value;R();};$x('xlW').onchange=e=>{S.w=e.target.value;S.d='ALL';R();};$x('xlD').onchange=e=>{S.d=e.target.value;R();};
R();load();setInterval(load,10*60*1000);"""
    return _seccion("lo", data, body, js)
