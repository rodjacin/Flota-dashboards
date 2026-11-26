# -*- coding: utf-8 -*-
"""
Pestaña «Proyección vs mes anterior» del panel MushDrink (mushdrink/index.html).

Una fila por restaurante, fecha proyectada y franja de 30 min:
  · Pedidos y riders proyectados de la franja, del CSV «ProyeccionPedidos»
    (ID = código del restaurante, Pedidos_Proyectados, Ratio_por_Cluster = riders proyectados).
  · La misma franja del mismo día de la semana en la misma semana del mes anterior (M-1: 1.er sábado de dic →
    1.er sábado de nov; sin 5.º en el mes anterior, el último), con datos del panel,
    asignando cada pedido a la franja por su hora de solicitud: riders distintos que entregaron
    («Pedidos por rider · 15 min»), pedidos, % >45 min, aviso HD medio y Aceptado > En camino medio (AVHD).
    Si la M-1 aún no tiene datos (fecha futura), se usa el último mismo día de la semana con datos y se marca.
  · Las franjas de 00:00 a 06:59 son la madrugada del mismo día operativo (07:00–06:59).

Las proyecciones se acumulan en mushdrink/proyeccion_pedidos.csv (un CSV nuevo sustituye las fechas que trae).

Uso: python3 mushdrink_proyeccion.py [mushdrink/index.html] [--csv ProyeccionPedidos.csv]
     (mushdrink_dia.py lo llama cada día para refrescar la M-1)
"""
import os, re, sys, json, csv, argparse, datetime as dt

HERE = os.path.dirname(os.path.abspath(__file__))
MARCA = "<!-- PROYECCION_WK1 -->"
TAB = "Proyección vs mes anterior"
STORE = os.path.join(HERE, "..", "mushdrink", "proyeccion_pedidos.csv")
DIAS_HIST = 63


def getv(d, name):
    m = re.search(r'(?:const|let|var)\s+' + name + r'\s*=\s*', d)
    return json.JSONDecoder().raw_decode(d[m.end():])[0] if m else None


def lee_csv(p):
    rows = []
    with open(p, encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f, delimiter=";"):
            try:
                d = dt.datetime.strptime(r["Fecha"].strip(), "%d/%m/%Y").date().isoformat()
                rows.append({"ID": str(int(r["ID"])), "Fecha": d, "Hora": r["Hora"].strip()[:5],
                             "Pedidos": int(float(r["Pedidos_Proyectados"] or 0)),
                             "Riders": int(float(r["Ratio_por_Cluster"] or 0)),
                             "Asig": (r.get("Recursos_Asignados") or "").strip(),
                             "Rev": (r.get("Cambio_de_proyecciones") or "").strip()})
            except (ValueError, KeyError):
                continue
    return rows


def store_merge(nuevo):
    viejo = []
    if os.path.exists(STORE):
        with open(STORE, encoding="utf-8", newline="") as f:
            viejo = [dict(r, Pedidos=int(r["Pedidos"]), Riders=int(r["Riders"]), Asig=r.get("Asig") or "", Rev=r.get("Rev") or "") for r in csv.DictReader(f)]
    fechas = {r["Fecha"] for r in nuevo}
    todo = [r for r in viejo if r["Fecha"] not in fechas] + nuevo
    todo.sort(key=lambda r: (r["Fecha"], int(r["ID"]), r["Hora"]))
    with open(STORE, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["ID", "Fecha", "Hora", "Pedidos", "Riders", "Asig", "Rev"]); w.writeheader(); w.writerows(todo)
    return todo


def slot_hm(hhmm):
    """franja de 30 min del día operativo (07:00–06:59): 07:00 → 14 … 06:30 → 61"""
    h, m = (int(x) for x in hhmm.strip().split(":")[:2])
    return (h + 24 if h < 7 else h) * 2 + m // 30


def mes_anterior(d):
    """n-ésimo <día de la semana> de d en su mes → el n-ésimo del mes anterior (o el último si no hay n-ésimo)."""
    n = (d.day - 1) // 7
    m1 = (d.replace(day=1) - dt.timedelta(days=1)).replace(day=1)
    first = m1 + dt.timedelta(days=(d.weekday() - m1.weekday()) % 7)
    out = first + dt.timedelta(days=7 * n)
    while out.month != m1.month: out -= dt.timedelta(days=7)
    return out


COBRO = 28   # día de cobro


def sab_cobro(y, m):
    """Sábado del fin de semana de cobro del mes (y, m): el que contiene el 28 o, si no cae en fin de semana, el siguiente."""
    d = dt.date(y, m, COBRO)
    return d - dt.timedelta(days=1) if d.weekday() == 6 else d + dt.timedelta(days=(5 - d.weekday()) % 7)


def finde_cobro(sat):
    """Si el fin de semana que empieza en `sat` es de cobro, devuelve (año, mes) del cobro; si no, None."""
    for k in (0, -1):
        y, m = sat.year, sat.month + k
        if m == 0: y, m = y - 1, 12
        if sab_cobro(y, m) == sat: return (y, m)
    return None


def referencia(d):
    """Fecha M-1 con la que se compara d y si es fin de semana de cobro.
    · Laborables: mes_anterior(d).
    · Fin de semana de cobro (el que contiene el 28 o el siguiente): el fin de semana de cobro del mes anterior.
    · Otro fin de semana: el n-ésimo fin de semana del mes anterior (por su sábado); si ese es de cobro, el anterior
      (o el siguiente si no hay anterior en el mes)."""
    if d.weekday() < 5:
        return mes_anterior(d), False
    sat = d - dt.timedelta(days=d.weekday() - 5); off = d - sat
    c = finde_cobro(sat)
    if c:
        y, m = c[0], c[1] - 1
        if m == 0: y, m = y - 1, 12
        return sab_cobro(y, m) + off, True
    r = mes_anterior(sat)
    if finde_cobro(r):
        r2 = r - dt.timedelta(days=7)
        r = r2 if r2.month == r.month else r + dt.timedelta(days=7)
    return r + off, False


def datos(docs, proy):
    EC = getv(docs[9], "EC"); AV = getv(docs[3], "AVHD"); DS = getv(docs[3], "DS"); AGG = getv(docs[2], "AGG")
    # proyección por franja: P[fecha][code] = [[franja, pedidos, riders teóricos], …]
    P = {}
    for r in proy:
        P.setdefault(r["Fecha"], {}).setdefault(r["ID"], []).append([slot_hm(r["Hora"]), r["Pedidos"], r["Riders"], int(float(r["Asig"])) if str(r.get("Asig") or "").strip() else None,
                                                                   1 if (r.get("Rev") or "").strip() else 0])
    for f in P:
        for c in P[f]:
            P[f][c].sort()
    # fechas cuyo CSV no trae Recursos_Asignados: se toman los de la fecha proyectada anterior del mismo día de la
    # semana que sí los trae (p. ej. WK50 ← WK49, que son los fichajes IN/OUT de Kometa de la semana 9–15/11),
    # por restaurante y franja
    AR = {}
    con = sorted(f for f in P if any(x[3] is not None for L in P[f].values() for x in L))
    for f in sorted(P):
        if f in con: continue
        wd = dt.date.fromisoformat(f).weekday()
        src = [g for g in con if g < f and dt.date.fromisoformat(g).weekday() == wd]
        if not src: continue
        g = src[-1]; AR[f] = g
        for c, L in P[f].items():
            S = {x[0]: x[3] for x in P[g].get(c, [])}
            for x in L: x[3] = S.get(x[0])
    # fecha M-1 de cada fecha proyectada: el mismo día de la semana en la misma semana del mes anterior
    # (n-ésimo lunes, martes… del mes → n-ésimo del mes anterior; si no existe el 5.º, el último);
    # si no hay datos, el último mismo día de la semana con datos
    hist = sorted(AV)
    REF = {}
    for f in P:
        d = dt.date.fromisoformat(f); w1d, cob = referencia(d); w1 = w1d.isoformat()
        if w1 in AV:
            REF[f] = {"f": w1, "exacta": True, "cobro": cob}
        else:
            cand = [x for x in hist if x < w1 and dt.date.fromisoformat(x).weekday() == d.weekday()]
            REF[f] = {"f": cand[-1] if cand else None, "exacta": False, "w1": w1, "cobro": cob}
    # M-1 por franja: M[fecha_ref][code] = {franja: [riders, pedidos, >45, aviso HD medio min, acept>camino medio min]}
    M = {}; DIA = {}
    for fr in sorted({r["f"] for r in REF.values() if r["f"]}):
        acc = {}
        for c, L in (AV.get(fr) or {}).items():
            for o in L:
                t = o[1][11:16]; sl = slot_hm(t)
                a = acc.setdefault(c, {}).setdefault(sl, [set(), 0, 0, 0.0, 0, 0.0, 0])
                a[1] += 1; a[2] += bool(o[5]) if isinstance(o[5], bool) else o[5] > 2700   # antes del 04/11 AVHD guarda >45 como booleano
                if o[3] is not None and 0 <= o[3] < 7200: a[3] += o[3]; a[4] += 1
                if o[4]: a[5] += sum(o[4]); a[6] += 1
        for k, arr in AGG["data"].items():
            c, f = k.split("|")
            if f != fr:
                continue
            for i in range(0, len(arr), 3):
                ri, s15 = arr[i], arr[i + 1]
                h, m = s15 // 4, (s15 % 4) * 15
                sl = (h + 24 if h < 7 else h) * 2 + m // 30
                acc.setdefault(c, {}).setdefault(sl, [set(), 0, 0, 0.0, 0, 0.0, 0])[0].add(ri)
        DIA.setdefault(fr, {})
        for c, d in acc.items():
            ped = sum(a[1] for a in d.values()); rid = set().union(*[a[0] for a in d.values()])
            if rid and ped:
                DIA[fr][c] = [ped, len(rid), round(ped / len(rid), 2)]
        M[fr] = {c: {str(sl): [len(a[0]), a[1], a[2], round(a[3] / a[4] / 60, 1) if a[4] else None,
                               round(a[5] / a[6] / 60, 1) if a[6] else None] for sl, a in d.items()} for c, d in acc.items()}
    codes = set(c for v in P.values() for c in v)
    R = {}
    for r in DS["restaurants"]:
        c = str(r["code"])
        if c in codes:
            R[c] = {"n": r.get("name") or c, "o": r.get("owner") or ""}
    for c in codes:
        R.setdefault(c, {"n": (EC.get("names") or {}).get(c, c), "o": (EC.get("coord") or {}).get(c, "")})
    return {"P": P, "M": M, "DIA": DIA, "REF": REF, "AR": AR, "R": R, "hist": [hist[0], hist[-1]] if hist else None,
            "generado": dt.datetime.now().strftime("%Y-%m-%d %H:%M")}


def html_doc(data):
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    return MARCA + r"""<!DOCTYPE html>
<html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Proyección vs mes anterior</title>
<style>
:root{--bg:#F6F7F9;--card:#fff;--line:#E4E7EC;--ink:#14171F;--ink2:#4B5563;--mut:#6B7280;--acc:#0E5A6B;--red:#B42318;--redbg:#FEE4E2;--amb:#93370D;--ambbg:#FEF0C7;--grn:#05603A;--grnbg:#D1FADF}
*{box-sizing:border-box} body{margin:0;background:var(--bg);color:var(--ink);font-family:Inter,-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;font-size:14px}
.wrap{max-width:1500px;margin:0 auto;padding:18px 18px 40px;display:flex;flex-direction:column;gap:14px}
h1{font-size:19px;margin:0;font-weight:650} .sub{color:var(--ink2);font-size:12.5px;margin-top:4px;max-width:130ch;line-height:1.5}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px 16px}
.filters{display:flex;flex-wrap:wrap;gap:14px;align-items:flex-end;position:sticky;top:0;z-index:5}
.fg{display:flex;flex-direction:column;gap:5px} .fg>span{font-size:10.5px;letter-spacing:.07em;text-transform:uppercase;color:var(--mut);font-weight:600}
input,select{font:inherit;font-size:13px;border:1px solid var(--line);border-radius:8px;padding:6px 9px;background:#fff;color:var(--ink);height:34px;max-width:260px}
#q{width:220px} .nav{display:flex;gap:6px} .nav button,.reset{height:34px;border:1px solid var(--line);background:#fff;border-radius:8px;padding:0 10px;cursor:pointer}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:10px}
.kpi{background:#fff;border:1px solid var(--line);border-radius:12px;padding:11px 14px} .kpi b{display:block;font-size:22px;font-variant-numeric:tabular-nums} .kpi span{font-size:12px;color:var(--ink2)} .kpi b span{font-size:inherit}
table{border-collapse:collapse;width:100%;font-size:12.8px}
th{background:#F0F2F5;color:var(--mut);font-size:10.5px;text-transform:uppercase;letter-spacing:.03em;padding:7px 8px;text-align:right;cursor:pointer;position:sticky;top:0;vertical-align:bottom;line-height:1.3}
th.g{background:#E6EEF0;color:var(--acc)}
th[data-t]{text-decoration:underline dotted;text-underline-offset:3px;text-decoration-color:#9AA3AF}
th[data-t]::after{content:' ⓘ';font-size:10px;opacity:.55;text-decoration:none;display:inline-block}
td{padding:6px 8px;border-top:1px solid #EEF0F3;text-align:right;white-space:nowrap;font-variant-numeric:tabular-nums}
th.l,td.l{text-align:left} .sm{display:block;font-size:11px;color:var(--mut)}
.neg{color:var(--red);font-weight:650} .ok{color:var(--grn)} .mut{color:var(--mut)} .warn{color:var(--amb)}
.pill{display:inline-block;padding:2px 9px;border-radius:99px;font-weight:700;font-size:12px;background:var(--redbg);color:var(--red)}
.flag{display:inline-block;font-size:10.5px;background:var(--ambbg);color:var(--amb);border-radius:99px;padding:1px 7px;margin-left:4px}
.note{color:var(--mut);font-size:12px;line-height:1.6;margin:0}
.tip{position:fixed;pointer-events:none;background:#14171F;color:#fff;font-size:12px;line-height:1.5;padding:7px 10px;border-radius:7px;z-index:20;max-width:340px}
.tip[hidden]{display:none} [data-t]{cursor:help}
</style></head><body>
<div class="wrap">
  <div><h1>Proyección por franja de 30 min vs mismo día de la misma semana del mes anterior (M-1)</h1>
  <div class="sub">Pedidos y riders proyectados en cada franja de 30 min, frente a la misma franja del mismo día de la semana en la misma semana del mes anterior (1.er martes de diciembre → 1.er martes de noviembre; el fin de semana de cobro, día 28, con el de cobro del mes anterior): riders que entregaron, pedidos, % &gt;45 min, aviso HD y Aceptado &gt; En camino. <span id="sub"></span></div></div>
  <div class="card filters">
    <div class="fg"><span>Buscador</span><input id="q" type="search" placeholder="Restaurante o código"></div>
    <div class="fg"><span>Código</span><select id="cod"></select></div>
    <div class="fg"><span>Restaurante</span><select id="rest"></select></div>
    <div class="fg"><span>Coordinador</span><select id="coord"></select></div>
    <div class="fg"><span>Semana</span><select id="sem"></select></div>
    <div class="fg"><span>Fecha</span><div class="nav"><button id="prev">◀</button><select id="fecha"></select><button id="next">▶</button></div></div>
    <div class="fg"><span>Franja</span><select id="fr"></select></div>
    <div class="fg"><span data-t="Columna Cambio_de_proyecciones del CSV de proyección: franjas marcadas «A revisar por flota».">Cambio de proyecciones</span><select id="rev"><option value="">Todas</option><option value="1">A revisar por flota</option><option value="0">Sin marca</option></select></div>
    <div class="fg"><span data-t="Según Riders M-1 − proyectados en la franja: Infradimensionado &lt; 0 · Bien dimensionado = 0 · Sobredimensionado &gt; 0.">Dimensionamiento</span><select id="dim"><option value="">Todos</option><option value="infra">Infradimensionado (&lt; 0)</option><option value="bien">Bien dimensionado (= 0)</option><option value="sobre">Sobredimensionado (&gt; 0)</option></select></div>
    <label style="display:flex;gap:6px;align-items:center;height:34px;font-size:13px;color:var(--ink2)"><input id="solo" type="checkbox" style="height:auto"> Solo alertas</label>
    <button class="reset" id="reset">Limpiar filtros</button>
    <button class="reset" id="xls" style="background:#0E5A6B;color:#fff;border-color:#0E5A6B;font-weight:600">⬇ Descargar Excel</button>
  </div>
  <div class="kpis" id="kpis"></div>
  <div class="card" style="overflow:auto;max-height:75vh"><table id="tab"></table></div>
  <p class="note" id="note"></p>
</div>
<div class="tip" id="tip" hidden></div>
<script>
const A=""" + payload + r""";
const $=id=>document.getElementById(id);
const DW=['dom','lun','mar','mié','jue','vie','sáb'];
const pd=s=>new Date(s+'T12:00:00');
const iso=d=>d.getFullYear()+'-'+String(d.getMonth()+1).padStart(2,'0')+'-'+String(d.getDate()).padStart(2,'0');
const dl=s=>DW[pd(s).getDay()]+' '+s.slice(8,10)+'/'+s.slice(5,7);
const wk=s=>{const d=pd(s);const t=new Date(Date.UTC(d.getFullYear(),d.getMonth(),d.getDate()));const n=t.getUTCDay()||7;t.setUTCDate(t.getUTCDate()+4-n);const y=new Date(Date.UTC(t.getUTCFullYear(),0,1));return 'W'+String(Math.ceil(((t-y)/864e5+1)/7)).padStart(2,'0');};
const nf=(v,d=0)=>v==null||!isFinite(v)?'—':v.toLocaleString('es-ES',{minimumFractionDigits:d,maximumFractionDigits:d});
const FECHAS=Object.keys(A.P).sort();
const sl=n=>{const h=Math.floor(n/2)%24;return String(h).padStart(2,'0')+':'+(n%2?'30':'00');};
const REF=A.REF;
const filas=[];FECHAS.forEach(f=>{const r=REF[f];Object.entries(A.P[f]).forEach(([c,L])=>{const R=A.R[c]||{n:c,o:''};const MM=r.f&&A.M[r.f]&&A.M[r.f][c]||{};
  L.forEach(([s,p,t,ra,rv])=>{const tiene=Object.keys(MM).length>0;const m=MM[s]||(tiene?[0,0,0,null,null]:null);if(!p&&!t&&!(MM[s]))return;
    filas.push({f,w:wk(f),s,c,n:R.n,o:R.o||'',pd:p,rt:t,rf:r,rw:m?m[0]:null,np:m?m[1]:null,l45:m&&m[1]?m[2]/m[1]:null,hd:m?m[3]:null,tie:m?m[4]:null,dif:m?m[0]-t:null,dp:m?p-m[1]:null,ra:ra==null?null:ra,rv:rv?1:0,dra:ra==null?null:ra-t,rpr:(r.f&&A.DIA[r.f]&&A.DIA[r.f][c])?A.DIA[r.f][c][2]:null,rprD:(r.f&&A.DIA[r.f]&&A.DIA[r.f][c])||null,al:!!(m&&m[0]-t<0&&m[1]&&m[2]/m[1]>0.10&&m[3]!=null&&m[3]<6&&m[4]!=null&&m[4]<12&&r.f&&A.DIA[r.f]&&A.DIA[r.f][c]&&A.DIA[r.f][c][2]>17)?1:0,ord:c.padStart(6,'0')+'|'+f+'|'+String(s).padStart(2,'0')});});});});
const S={q:'',cod:'',rest:'',coord:'',sem:'',fecha:'',fr:'',dim:'',rev:'',solo:false,sort:'ord',asc:true};
const opt=(l,all)=>`<option value="">${all}</option>`+l.map(x=>`<option value="${x[0]}">${x[1]}</option>`).join('');
const uniq=(k,lab)=>[...new Map(filas.map(x=>[x[k],lab(x)])).entries()];
$('cod').innerHTML=opt(uniq('c',x=>x.c).sort((a,b)=>+a[0]-+b[0]),'Todos');
$('rest').innerHTML=opt(uniq('n',x=>x.n).sort((a,b)=>a[1].localeCompare(b[1])),'Todos');
$('coord').innerHTML=opt(uniq('o',x=>x.o||'(sin coordinador)').sort((a,b)=>a[1].localeCompare(b[1])),'Todos');
$('fr').innerHTML=opt([...new Set(filas.map(x=>x.s))].sort((a,b)=>a-b).map(x=>[String(x),sl(x)+'–'+sl(x+1)]),'Todas');
$('sem').innerHTML=opt([...new Set(FECHAS.map(wk))].map(w=>{const fs=FECHAS.filter(f=>wk(f)===w);return [w,w+' · '+dl(fs[0])+'–'+dl(fs[fs.length-1])];}),'Todas');
function fechasSem(){return FECHAS.filter(f=>!S.sem||wk(f)===S.sem);}
function fillFecha(){const fs=fechasSem();$('fecha').innerHTML=`<option value="">Todas (${fs.length})</option>`+fs.map(f=>`<option value="${f}">${dl(f)}/${f.slice(2,4)}</option>`).join('');if(S.fecha&&!fs.includes(S.fecha))S.fecha='';$('fecha').value=S.fecha;}
const sgn=(v,neutro)=>v==null?'<span class="mut">—</span>':`<b class="${neutro?(v>0?'warn':v<0?'mut':'mut'):(v<0?'neg':v>0?'ok':'mut')}">${v>0?'+':v<0?'−':''}${Math.abs(v)}</b>`;
const cell=(v,d,suf,cls)=>v==null?'<span class="mut">—</span>':`<span class="${cls||''}">${nf(v,d)}${suf||''}</span>`;
let ROWS=[];
// ---- Excel (.xlsx) de las filas filtradas, sin librerías ----
const CRC=(()=>{const t=new Uint32Array(256);for(let n=0;n<256;n++){let c=n;for(let k=0;k<8;k++)c=c&1?0xEDB88320^(c>>>1):c>>>1;t[n]=c>>>0;}return t;})();
const crc32=b=>{let c=0xFFFFFFFF;for(let i=0;i<b.length;i++)c=CRC[(c^b[i])&255]^(c>>>8);return(c^0xFFFFFFFF)>>>0;};
function zip(files){const enc=new TextEncoder();const parts=[],cen=[];let off=0;
  files.forEach(([name,txt])=>{const nb=enc.encode(name),db=enc.encode(txt),crc=crc32(db);
    const lh=new DataView(new ArrayBuffer(30));lh.setUint32(0,0x04034b50,true);lh.setUint16(4,20,true);lh.setUint16(8,0,true);lh.setUint32(14,crc,true);lh.setUint32(18,db.length,true);lh.setUint32(22,db.length,true);lh.setUint16(26,nb.length,true);
    parts.push(new Uint8Array(lh.buffer),nb,db);
    const ch=new DataView(new ArrayBuffer(46));ch.setUint32(0,0x02014b50,true);ch.setUint16(4,20,true);ch.setUint16(6,20,true);ch.setUint32(16,crc,true);ch.setUint32(20,db.length,true);ch.setUint32(24,db.length,true);ch.setUint16(28,nb.length,true);ch.setUint32(42,off,true);
    cen.push(new Uint8Array(ch.buffer),nb);off+=30+nb.length+db.length;});
  const cs=cen.reduce((a,x)=>a+x.length,0);const e=new DataView(new ArrayBuffer(22));e.setUint32(0,0x06054b50,true);e.setUint16(8,files.length,true);e.setUint16(10,files.length,true);e.setUint32(12,cs,true);e.setUint32(16,off,true);
  return new Blob([...parts,...cen,new Uint8Array(e.buffer)],{type:'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'});}
const xe=v=>String(v).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const colL=i=>{let s='';i++;while(i){const m=(i-1)%26;s=String.fromCharCode(65+m)+s;i=Math.floor((i-1)/26);}return s;};
function descargaExcel(){
  // una fila por restaurante y fecha: almuerzo = franjas 13:00–15:30 (13:00–16:00) · cena = 20:00–22:30 (20:00–23:00)
  // respeta los filtros de restaurante, coordinador, semana y fecha (no los de franja, alertas o dimensionamiento)
  const base=filas.filter(x=>(!S.q||(x.c+' '+x.n).toLowerCase().includes(S.q))&&(!S.cod||x.c===S.cod)&&(!S.rest||x.n===S.rest)&&(!S.coord||x.o===S.coord)&&(!S.sem||x.w===S.sem)&&(!S.fecha||x.f===S.fecha));
  const T={al:[26,32],ce:[40,46]};const G=new Map();
  base.forEach(x=>{const k=x.f+'|'+x.c;let g=G.get(k);if(!g){g={o:x.o,f:x.f,c:x.c,n:x.n,tot:0,pk:null,rr:null};for(const t in T)g[t]={pd:0,rt:0,ra:0,raN:0,np:0,l:0};G.set(k,g);}
    g.tot+=x.pd||0;if(x.pd>0&&(!g.pk||x.pd>g.pk.pd||(x.pd===g.pk.pd&&x.rt>g.pk.rt)))g.pk={pd:x.pd,rt:x.rt,s:x.s};if(x.rprD){g.rr=x.rprD[2];g.rM=x.rprD[1];}
    for(const t in T){if(x.s<T[t][0]||x.s>=T[t][1])continue;const a=g[t];a.pd+=x.pd||0;a.rt+=x.rt||0;if(x.ra!=null){a.ra+=x.ra;a.raN++;}
      if(x.np){a.np+=x.np;a.l+=Math.round((x.l45||0)*x.np);}}});
  const rows=[...G.values()].sort((a,b)=>(a.o||'').localeCompare(b.o||'')||a.f.localeCompare(b.f)||(+a.c)-(+b.c));
  const ra=a=>a.raN?a.ra:null,p45=a=>a.np?a.l/a.np:null,rp=x=>x.rM?x.tot/x.rM:null,
    alerta=(x,t)=>{const r=rp(x),q=p45(x[t]);return r!=null&&r>17&&q!=null&&q>0.12?'⚠️ Alerta':'';};
  const C=[['Coordinador',x=>x.o,0,16],['Fecha',x=>x.f.split('-').reverse().join('/'),0,12],['Código',x=>+x.c,0,9],['Restaurante',x=>x.n,0,38],
    ['Ratio proyectado (pedidos proyectados del día / riders reales M-1 del día)',rp,3,20],['Ratio real M-1 (pedidos del día M-1 / riders que repartieron ese día)',x=>x.rr,3,20],
    ['Pedidos proyectados almuerzo (13:00–16:00)',x=>x.al.pd,0,16],['Pedidos reales almuerzo M-1 (13:00–16:00)',x=>x.al.np,0,16],['Riders proyectados almuerzo (ratio por cluster, suma 13:00–16:00)',x=>x.al.rt,0,18],
    ['Riders actuales almuerzo (recursos asignados, 13:00–16:00)',x=>ra(x.al),0,18],['RIDERS NECESARIOS ALMUERZO',x=>ra(x.al)==null?x.al.rt:Math.max(x.al.rt,ra(x.al)),0,20,5,6],['Riders asignados − proyectados almuerzo (13:00–16:00)',x=>ra(x.al)==null?null:ra(x.al)-x.al.rt,0,18],['% tiempo de pedido >45 min almuerzo (M-1, 13:00–16:00)',x=>p45(x.al),2,18],
    ['Pedidos proyectados cena (20:00–23:00)',x=>x.ce.pd,0,16],['Pedidos reales cena M-1 (20:00–23:00)',x=>x.ce.np,0,16],['Riders proyectados cena (ratio por cluster, suma 20:00–23:00)',x=>x.ce.rt,0,18],
    ['Riders actuales cena (recursos asignados, 20:00–23:00)',x=>ra(x.ce),0,18],['RIDERS NECESARIOS CENA',x=>ra(x.ce)==null?x.ce.rt:Math.max(x.ce.rt,ra(x.ce)),0,20,5,6],['Riders asignados − proyectados cena (20:00–23:00)',x=>ra(x.ce)==null?null:ra(x.ce)-x.ce.rt,0,18],['% tiempo de pedido >45 min cena (M-1, 20:00–23:00)',x=>p45(x.ce),2,18],
    ['ALERTA ALMUERZO (ratio proyectado >17 y % >45 min almuerzo >12 %)',x=>alerta(x,'al'),0,18,7,4],['ALERTA CENA (ratio proyectado >17 y % >45 min cena >12 %)',x=>alerta(x,'ce'),0,18,7,4]];
  const cellX=(r,ci,v,st)=>{const ref=colL(ci)+r;if(v==null||v==='')return '';if(typeof v==='number'&&isFinite(v))return `<c r="${ref}"${st?` s="${st}"`:''}><v>${v}</v></c>`;return `<c r="${ref}" t="inlineStr"${st?` s="${st}"`:''}><is><t>${xe(v)}</t></is></c>`;};
  let sd='<row r="1">'+C.map((c,i)=>cellX(1,i,c[0],c[4]||1)).join('')+'</row>';
  rows.forEach((x,k)=>{const r=k+2;sd+=`<row r="${r}">`+C.map((c,i)=>cellX(r,i,c[1](x),c[5]||c[2])).join('')+'</row>';});
  const last=colL(C.length-1)+(rows.length+1);
  const sheet=`<?xml version="1.0" encoding="UTF-8" standalone="yes"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/></sheetView></sheetViews><cols>${C.map((c,i)=>`<col min="${i+1}" max="${i+1}" width="${c[3]}" customWidth="1"/>`).join('')}</cols><sheetData>${sd}</sheetData><autoFilter ref="A1:${last}"/></worksheet>`;
  const styles='<?xml version="1.0" encoding="UTF-8" standalone="yes"?><styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><numFmts count="1"><numFmt numFmtId="164" formatCode="0.0"/></numFmts><fonts count="4"><font><sz val="11"/><name val="Calibri"/></font><font><b/><sz val="11"/><color rgb="FFFFFFFF"/><name val="Calibri"/></font><font><b/><sz val="11"/><color rgb="FFB42318"/><name val="Calibri"/></font><font><b/><sz val="11"/><name val="Calibri"/></font></fonts><fills count="6"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill><fill><patternFill patternType="solid"><fgColor rgb="FF0E5A6B"/></patternFill></fill><fill><patternFill patternType="solid"><fgColor rgb="FFE8590C"/></patternFill></fill><fill><patternFill patternType="solid"><fgColor rgb="FFFFE8CC"/></patternFill></fill><fill><patternFill patternType="solid"><fgColor rgb="FFB42318"/></patternFill></fill></fills><borders count="1"><border/></borders><cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs><cellXfs count="8"><xf/><xf fontId="1" fillId="2" applyFont="1" applyFill="1"><alignment wrapText="1" vertical="center"/></xf><xf numFmtId="10" applyNumberFormat="1"/><xf numFmtId="164" applyNumberFormat="1"/><xf fontId="2" applyFont="1"/><xf fontId="1" fillId="3" applyFont="1" applyFill="1"><alignment wrapText="1" vertical="center"/></xf><xf fontId="3" fillId="4" applyFont="1" applyFill="1"><alignment horizontal="center"/></xf><xf fontId="1" fillId="5" applyFont="1" applyFill="1"><alignment wrapText="1" vertical="center"/></xf></cellXfs><cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles></styleSheet>';
  const files=[['[Content_Types].xml','<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/><Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/></Types>'],
    ['_rels/.rels','<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>'],
    ['xl/workbook.xml','<?xml version="1.0" encoding="UTF-8" standalone="yes"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Proyección vs M-1" sheetId="1" r:id="rId1"/></sheets><definedNames><definedName name="_xlnm._FilterDatabase" localSheetId="0" hidden="1">\'Proyección vs M-1\'!$A$1:$'+colL(C.length-1)+'$'+(rows.length+1)+'</definedName></definedNames></workbook>'],
    ['xl/_rels/workbook.xml.rels','<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>'],
    ['xl/worksheets/sheet1.xml',sheet],['xl/styles.xml',styles]];
  const a=document.createElement('a');a.href=URL.createObjectURL(zip(files));
  a.download='Proyeccion_vs_M1_almuerzo_cena'+(S.fecha?'_'+S.fecha:S.sem?'_'+S.sem:'')+'.xlsx';document.body.appendChild(a);a.click();setTimeout(()=>{URL.revokeObjectURL(a.href);a.remove();},1000);}
function render(){
  const rows=filas.filter(x=>(!S.q||(x.c+' '+x.n).toLowerCase().includes(S.q))&&(!S.cod||x.c===S.cod)&&(!S.rest||x.n===S.rest)&&(!S.coord||x.o===S.coord)&&(!S.sem||x.w===S.sem)&&(!S.fecha||x.f===S.fecha)&&(!S.fr||String(x.s)===S.fr)&&(!S.rev||String(x.rv)===S.rev)&&(!S.solo||x.al)&&(!S.dim||(x.dif!=null&&(S.dim==='infra'?x.dif<0:S.dim==='sobre'?x.dif>0:x.dif===0))));
  ROWS=rows;
  const val=x=>x[S.sort];
  rows.sort((a,b)=>{const va=val(a),vb=val(b);if(va==null&&vb==null)return 0;if(va==null)return 1;if(vb==null)return -1;return(va<vb?-1:va>vb?1:0)*(S.asc?1:-1);});
  const sum=k=>rows.reduce((a,x)=>a+(x[k]||0),0);
  const np=sum('np'),late=rows.reduce((a,x)=>a+(x.np&&x.l45!=null?x.l45*x.np:0),0);
  const falt=rows.filter(x=>x.dif!=null&&x.dif<0).length,dsum=rows.reduce((a,x)=>a+(x.dif||0),0);
  $('kpis').innerHTML=[[nf(rows.length),'Franjas de 30 min'],[`<span class="${rows.some(x=>x.al)?'neg':''}">${nf(rows.filter(x=>x.al).length)}</span>`,'Franjas en alerta'],[nf(rows.filter(x=>x.rv).length),'Franjas «A revisar por flota»'],[nf(sum('pd')),'Pedidos proyectados'],[nf(sum('np')),'Pedidos M-1'],[(()=>{const v=sum('pd')-sum('np');return (v>0?'+':v<0?'−':'')+nf(Math.abs(v));})(),'Pedidos proyectados − M-1'],[`<span class="${falt?'neg':''}">${falt}</span>`,'Franjas con menos riders M-1 que proyectados'],[`<span class="${dsum<0?'neg':'ok'}">${dsum>0?'+':''}${nf(dsum)}</span>`,'Suma riders M-1 − proyectados'],[np?nf(late/np*100,1)+' %':'—','% pedidos >45 min M-1']].map(([b,s])=>`<div class="kpi"><b>${b}</b><span>${s}</span></div>`).join('');
  const th=(k,l,t,cl)=>`<th class="${cl||''}" data-k="${k}" ${t?`data-t="${t}"`:''}>${l}${S.sort===k?(S.asc?' ▲':' ▼'):''}</th>`;
  $('tab').innerHTML='<thead><tr>'+th('o','Coordinador','Coordinador responsable del restaurante, según la asignación del panel MushDrink.','l')+th('al','Alerta','Alerta si se cumplen las 5 condiciones en la franja: riders M-1 − proyectados &lt; 0 · % &gt;45 min M-1 &gt; 10 % · aviso HD M-1 &lt; 6 min · Aceptado &gt; En camino M-1 &lt; 12 min · pedidos/rider M-1 del día &gt; 17. Es decir: hubo pedidos tarde que no se explican por HD ni por cocina, y faltaron riders.','l')+th('f','Fecha','Fecha proyectada · debajo, la fecha M-1 con la que se compara.','l')+th('s','Franja','Intervalo de 30 min por hora de solicitud del pedido. De 00:00 a 06:59 es la madrugada del mismo día operativo.','l')+th('c','Código','Código del restaurante (columna ID del CSV de proyección).','l')+th('n','Restaurante','Nombre del restaurante en el panel MushDrink.','l')+
    th('pd','Pedidos<br>proyectados','Pedidos_Proyectados de la franja (CSV de proyección).')+th('np','Pedidos<br>M-1','Pedidos entregados solicitados en esa franja el mismo día de la semana y semana del mes anterior.','g')+
    th('dp','Pedidos proy. −<br>M-1','Pedidos proyectados menos pedidos de M-1 en la misma franja. Positivo = se esperan más pedidos que el mes anterior; negativo = menos. Pulsa para ordenar de mayor a menor o al revés.','g')+
    th('rt','Riders<br>proyectados','Ratio_por_Cluster de la franja (CSV de proyección).')+th('ra','Recursos<br>asignados','Recursos_Asignados del CSV de proyección: riders fichados en la tienda en esa franja el mismo día de la semana y semana del mes anterior con registro (fichajes IN/OUT de Kometa).')+th('dra','Asignados −<br>proyectados','Recursos asignados menos riders proyectados. Negativo = faltan riders respecto a la proyección.')+th('rw','Riders M-1','Riders distintos que entregaron pedidos solicitados en esa franja el mismo día de la semana y semana del mes anterior. En rojo si son menos que los proyectados.','g')+
    th('dif','Riders M-1 −<br>proyectados','Riders que entregaron en la franja en M-1 menos riders proyectados. Negativo (rojo) = en M-1 hubo menos riders de los que se proyectan; positivo (verde) = hubo más. Pulsa para ordenar de mayor a menor o al revés.','g')+
    th('rpr','Pedidos/rider<br>M-1 (día)','Pedidos entregados ÷ riders distintos del restaurante en todo el día M-1 (no solo la franja). Mismo valor en todas las franjas de ese restaurante y fecha.','g')+th('l45','% &gt;45 min<br>M-1','Pedidos de la franja con más de 45 min desde la solicitud del cliente hasta la entrega.','g')+
    th('hd','Aviso HD<br>M-1 (min)','Media desde que el cliente confirma el pedido hasta que llega a la API de HD, pedidos de la franja.','g')+
    th('tie','Aceptado &gt; En camino<br>M-1 (min)','Media de minutos entre que el rider acepta y marca En camino, pedidos de la franja.','g')+'</tr></thead><tbody>'+
    rows.slice(0,4000).map(x=>`<tr${x.al?' style="background:#FFF5F4"':''}><td class="l">${x.o||'<span class="mut">—</span>'}</td><td class="l">${x.al?'<span class="pill">Alerta</span>':''}</td><td class="l"><b>${dl(x.f)}</b><span class="sm">${x.rf.f?'vs '+dl(x.rf.f)+(x.rf.cobro?'<span class="flag" data-t="Fin de semana de cobro (día 28): se compara con el fin de semana de cobro del mes anterior.">cobro</span>':'')+(x.rf.exacta?'':'<span class="flag" data-t="La M-1 ('+dl(x.rf.w1)+') no tiene datos: se usa el último mismo día de la semana con datos.">sustituta</span>'):'sin M-1'}</span></td>
      <td class="l"><b>${sl(x.s)}</b><span class="sm">–${sl(x.s+1)}</span></td><td class="l">${x.c}</td><td class="l"><b>${x.n}</b>${x.rv?'<span class="flag" data-t="Cambio_de_proyecciones: A revisar por flota">A revisar</span>':''}</td>
      <td><b>${nf(x.pd)}</b></td><td>${cell(x.np,0)}</td><td>${sgn(x.dp,true)}</td><td><b>${nf(x.rt)}</b></td><td>${cell(x.ra,0)}</td><td>${sgn(x.dra)}</td>
      <td>${cell(x.rw,0,'',x.rw!=null&&x.rw<x.rt?'neg':'')}</td><td>${sgn(x.dif)}</td><td>${x.rpr==null?'<span class="mut">—</span>':`<b>${nf(x.rpr,1)}</b><span class="sm">${x.rprD[0]} ped. / ${x.rprD[1]} riders</span>`}</td>
      <td>${x.l45==null?'<span class="mut">—</span>':`<span class="${x.l45>=.2?'neg':x.l45>=.1?'warn':''}">${nf(x.l45*100,1)} %</span>`}</td>
      <td>${cell(x.hd,1,'',x.hd>=6?'warn':'')}</td><td>${cell(x.tie,1,'',x.tie>=12?'neg':x.tie>=10?'warn':'')}</td></tr>`).join('')+
    (rows.length>4000?`<tr><td class="l mut" colspan="18">Se muestran 4.000 de ${nf(rows.length)} franjas: filtra por fecha, restaurante o coordinador.</td></tr>`:'')+
    (rows.length?'':'<tr><td class="l mut" colspan="18">Sin filas con estos filtros.</td></tr>')+'</tbody>';
  const sust=FECHAS.some(f=>REF[f].f&&!REF[f].exacta);
  $('sub').textContent='Proyección del '+dl(FECHAS[0])+' al '+dl(FECHAS[FECHAS.length-1])+' · histórico hasta el '+dl(A.hist[1])+' · generado '+A.generado+'.';
  $('note').textContent='Una fila por restaurante y franja de 30 min. Alerta = riders M-1 por debajo de lo proyectado, más del 10 % de pedidos >45 min, más de 17 pedidos por rider en el día y, a la vez, aviso HD <6 min y Aceptado > En camino <12 min (el retraso no viene de HD ni de cocina, sino de falta de riders). M-1 = mismo día de la semana en la misma semana del mes anterior (p. ej. 1.er martes de diciembre → 1.er martes de noviembre; si el mes anterior no tiene 5.º, se usa el último). Fines de semana: el fin de semana de cobro (el que contiene el día 28 o el siguiente) se compara con el fin de semana de cobro del mes anterior (marcado «cobro»); el resto, con el mismo n.º de fin de semana del mes anterior sin contar el de cobro, emparejando sábado con sábado y domingo con su sábado; los pedidos y riders M-1 se asignan a la franja por la hora de solicitud del pedido.'+(sust?' Las fechas cuya M-1 aún no tiene datos se comparan con el último mismo día de la semana con datos (marcado «sustituta»); se actualizan solas al cargar cada día.':'')+(A.AR&&Object.keys(A.AR).length?' Recursos asignados: '+Object.keys(A.AR).sort().map(f=>dl(f)+' ← '+dl(A.AR[f])).join(', ')+' (el CSV de esas fechas no los trae; se usan los del mismo día de la semana de la proyección anterior, fichajes IN/OUT de Kometa de la semana 9–15/11).':'')+' Colores: riders M-1 en rojo si son menos que los teóricos · % >45 min naranja desde 10 % y rojo desde 20 % · aviso HD naranja desde 6 min · Aceptado > En camino naranja desde 10 min y rojo desde 12 min.';
}
const on=(id,k,ev='onchange')=>$(id)[ev]=e=>{S[k]=ev==='oninput'?e.target.value.trim().toLowerCase():e.target.value;if(k==='sem')fillFecha();render();};
on('q','q','oninput');on('cod','cod');on('rest','rest');on('coord','coord');on('sem','sem');on('fecha','fecha');on('dim','dim');$('xls').onclick=()=>descargaExcel();$('solo').onchange=e=>{S.solo=e.target.checked;render();};on('fr','fr');on('rev','rev');
const mv=d=>{const fs=fechasSem();let i=fs.indexOf(S.fecha);i=S.fecha?i+d:(d>0?0:fs.length-1);if(i>=0&&i<fs.length){S.fecha=fs[i];$('fecha').value=S.fecha;render();}};
$('prev').onclick=()=>mv(-1);$('next').onclick=()=>mv(1);
$('reset').onclick=()=>{Object.assign(S,{q:'',cod:'',rest:'',coord:'',sem:'',fecha:'',fr:'',dim:'',rev:'',solo:false});$('dim').value='';$('rev').value='';$('solo').checked=false;['q','cod','rest','coord','sem','fr'].forEach(i=>$(i).value='');fillFecha();render();};
$('tab').addEventListener('click',e=>{const h=e.target.closest('th[data-k]');if(!h)return;const k=h.dataset.k;if(S.sort===k)S.asc=!S.asc;else{S.sort=k;S.asc=['f','s','c','n','o','ord'].includes(k);}render();});
const tip=$('tip');document.addEventListener('mouseover',e=>{const el=e.target.closest('[data-t]');if(el){tip.textContent=el.dataset.t;tip.hidden=false;}});
document.addEventListener('mousemove',e=>{if(!tip.hidden){tip.style.left=Math.min(e.clientX+12,innerWidth-360)+'px';tip.style.top=(e.clientY+14)+'px';}});
document.addEventListener('mouseout',e=>{const el=e.target.closest('[data-t]');if(el&&!el.contains(e.relatedTarget))tip.hidden=true;});
S.fecha=FECHAS[0]||'';fillFecha();render();
</script></body></html>"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("html", nargs="?", default=os.path.join(HERE, "..", "mushdrink", "index.html"))
    ap.add_argument("--csv")
    a = ap.parse_args()
    if a.csv:
        proy = store_merge(lee_csv(a.csv))
    elif os.path.exists(STORE):
        proy = store_merge([])
    else:
        print("mushdrink_proyeccion: sin proyección guardada, nada que hacer"); return
    h = open(a.html, encoding="utf-8").read()
    i0 = h.index("const DOCS=") + len("const DOCS=")
    docs, e0 = json.JSONDecoder().raw_decode(h[i0:])
    data = datos(docs, proy)
    doc = html_doc(data)
    k = next((i for i, d in enumerate(docs) if d.startswith(MARCA)), None)
    if k is None:
        docs.append(doc); k = len(docs) - 1
        j = h.index('<div class="tabs">'); j = h.index("</div>", j)
        h = h[:j] + f'<button class="tab" data-i="{k}">{TAB}</button>' + h[j:]
        i0 = h.index("const DOCS=") + len("const DOCS=")
    else:
        docs[k] = doc
    body = "[" + ",\n".join(json.dumps(x, ensure_ascii=False).replace("</", "<\\/") for x in docs) + "]"
    h = h[:i0] + body + h[i0 + e0:]
    open(a.html, "w", encoding="utf-8").write(h)
    nP = sum(len(v) for v in data["P"].values())
    print(f"mushdrink_proyeccion: pestaña {k} · {len(data['P'])} fechas ({min(data['P'])}..{max(data['P'])}) · {nP} filas · histórico {data['hist']}")


if __name__ == "__main__":
    main()
