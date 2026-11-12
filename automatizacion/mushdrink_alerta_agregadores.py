# -*- coding: utf-8 -*-
"""
Pestaña «Alerta agregadores» del panel MushDrink (mushdrink/index.html).

Sin visibilidad de los pedidos que reparten otras flotas (Glovo, Uber, Catcher…), una activación se detecta
porque caen los pedidos de MushDrink de ese restaurante frente a lo habitual, sin que caiga su zona ni haya festivo:

  esperado  = media del mismo día de la semana en las 4 semanas anteriores (mín. 2 semanas con datos)
  ratio     = pedidos reales ÷ esperados, ajustado por la tendencia de su zona (ratio zona = Σ reales ÷ Σ esperados)
  caída     = 1 − ratio ajustado (día completo y cena 20–23 h)
  alerta    = caída ≥ umbral en N días operativos seguidos (los festivos del restaurante no rompen ni suman la racha)

Datos (todos ya en el panel): HTAVG y DS de «Operativa restaurantes», F de «Festivos» y AG de «Agregadores»
(último % conocido de pedidos repartidos por otras flotas, hasta que se dejó de tener acceso).

Uso: python3 mushdrink_alerta_agregadores.py [mushdrink/index.html]   (mushdrink_dia.py lo llama cada día)
"""
import os, re, sys, json, datetime as dt

HERE = os.path.dirname(os.path.abspath(__file__))
MARCA = "<!-- ALERTA_AGREGADORES -->"
TAB = "Alerta agregadores"
DIAS = 70          # días de historia que viajan a la pestaña (28 visibles + 4 semanas de base + margen)


def getv(d, name):
    m = re.search(r'(?:const|let|var)\s+' + name + r'\s*=\s*', d)
    return json.JSONDecoder().raw_decode(d[m.end():])[0] if m else None


def buscar(docs, var, claves):
    """primer valor JSON llamado `var` en cualquier pestaña que tenga todas las `claves`"""
    for d in docs:
        for m in re.finditer(r'(?:const|let|var)\s+' + var + r'\s*=\s*', d):
            try:
                v = json.JSONDecoder().raw_decode(d[m.end():])[0]
            except ValueError:
                continue
            if isinstance(v, dict) and all(k in v for k in claves):
                return v
    return {}


def datos(docs):
    ht = getv(docs[3], "HTAVG"); ds = getv(docs[3], "DS")
    fechas = sorted({f for dd in ht["H"].values() for f in dd})
    fechas = fechas[-DIAS:]
    fi = {f: i for i, f in enumerate(fechas)}
    T = {}
    for c, dd in ht["H"].items():
        filas = []
        for f, flat in dd.items():
            if f not in fi:
                continue
            tot = cena = 0
            for i in range(0, len(flat), 4):
                h, n = int(flat[i]), int(flat[i + 1])
                tot += n
                if 20 <= h <= 23:
                    cena += n
            filas.append([fi[f], tot, cena])
        if filas:
            T[c] = sorted(filas)
    R = {}
    for r in ds["restaurants"]:
        c = str(r["code"])
        if c in T:
            R[c] = {"n": r.get("name") or c, "z": r.get("zona") or "", "o": r.get("owner") or ""}
    for c in T:
        R.setdefault(c, {"n": (ht.get("names") or {}).get(c, c), "z": "", "o": ""})
    # festivos que aplican a cada restaurante
    F = buscar(docs, "F", ["hol", "rest"])
    hol = {}
    for c, info in (F.get("rest") or {}).items():
        if c not in R:
            continue
        ds_c = [h[0] + " · " + h[2] for h in F.get("hol", []) if h[0] in fi and (h[3] == "ES" or h[3] == info.get("c") or h[3] == info.get("m"))]
        if ds_c:
            hol[c] = ds_c
        if not R[c]["z"]:
            R[c]["z"] = info.get("z") or ""
    # último % conocido de otras flotas (AG, 28 días hasta la última fecha con datos)
    AG = buscar(docs, "AG", ["D", "tipos"])
    ag, ag_hasta = {}, None
    if AG.get("D"):
        fs = sorted(AG["D"]); ag_hasta = fs[-1]; ult = fs[-28:]
        acc = {}
        for f in ult:
            for c, flat in AG["D"][f].items():
                a = acc.setdefault(c, [0, 0])
                for i in range(0, len(flat), 3):
                    n = int(flat[i + 2]); a[1] += n
                    if int(flat[i]) != 0:
                        a[0] += n
        ag = {c: round(a[0] / a[1], 4) for c, a in acc.items() if a[1] >= 20 and c in R}
    return {"dates": fechas, "R": R, "T": T, "hol": hol, "ag": ag, "ag_hasta": ag_hasta,
            "ag_desde": (sorted(AG["D"])[-28:][0] if AG.get("D") else None),
            "generado": dt.datetime.now().strftime("%Y-%m-%d %H:%M")}


def html_doc(data):
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    return MARCA + r"""<!DOCTYPE html>
<html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Alerta agregadores</title>
<style>
:root{--bg:#F6F7F9;--card:#fff;--line:#E4E7EC;--ink:#14171F;--ink2:#4B5563;--mut:#6B7280;--acc:#0E5A6B;--red:#B42318;--redbg:#FEE4E2;--amb:#93370D;--ambbg:#FEF0C7;--grn:#05603A;--grnbg:#D1FADF}
*{box-sizing:border-box} body{margin:0;background:var(--bg);color:var(--ink);font-family:Inter,-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;font-size:14px}
.wrap{max-width:1500px;margin:0 auto;padding:18px 18px 40px;display:flex;flex-direction:column;gap:14px}
h1{font-size:19px;margin:0;font-weight:650} .sub{color:var(--ink2);font-size:12.5px;margin-top:4px;max-width:120ch;line-height:1.5}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px 16px}
.filters{display:flex;flex-wrap:wrap;gap:14px;align-items:flex-end;position:sticky;top:0;z-index:5}
.fg{display:flex;flex-direction:column;gap:5px} .fg>span{font-size:10.5px;letter-spacing:.07em;text-transform:uppercase;color:var(--mut);font-weight:600}
input,select{font:inherit;font-size:13px;border:1px solid var(--line);border-radius:8px;padding:6px 9px;background:#fff;color:var(--ink);height:34px}
input[type=number]{width:70px;text-align:right} #q{width:220px}
.nav{display:flex;gap:6px} .nav button{height:34px;border:1px solid var(--line);background:#fff;border-radius:8px;padding:0 10px;cursor:pointer}
label.chk{display:flex;gap:6px;align-items:center;height:34px;font-size:13px;color:var(--ink2)} label.chk input{height:auto}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:10px}
.kpi{background:#fff;border:1px solid var(--line);border-radius:12px;padding:11px 14px} .kpi b{display:block;font-size:22px;font-variant-numeric:tabular-nums} .kpi span{font-size:12px;color:var(--ink2)}
table{border-collapse:collapse;width:100%;font-size:12.8px}
th{background:#F0F2F5;color:var(--mut);font-size:10.5px;text-transform:uppercase;letter-spacing:.03em;padding:7px 8px;text-align:right;white-space:nowrap;cursor:pointer;position:sticky;top:0}
td{padding:6px 8px;border-top:1px solid #EEF0F3;text-align:right;white-space:nowrap;font-variant-numeric:tabular-nums}
th.l,td.l{text-align:left} .sm{display:block;font-size:11px;color:var(--mut)}
.pill{display:inline-block;padding:2px 8px;border-radius:99px;font-weight:700;font-size:12px}
.p-r{background:var(--redbg);color:var(--red)} .p-a{background:var(--ambbg);color:var(--amb)} .p-g{background:var(--grnbg);color:var(--grn)} .p-n{background:#F0F2F5;color:var(--mut)}
.neg{color:var(--red);font-weight:650} .pos{color:var(--grn)} .mut{color:var(--mut)}
.note{color:var(--mut);font-size:12px;line-height:1.6;margin:0}
.tip{position:fixed;pointer-events:none;background:#14171F;color:#fff;font-size:12px;line-height:1.5;padding:7px 10px;border-radius:7px;z-index:20;max-width:340px}
.tip[hidden]{display:none} [data-t]{cursor:help}
</style></head><body>
<div class="wrap">
  <div><h1>Alerta agregadores · caídas de pedidos MushDrink por restaurante</h1>
  <div class="sub">Sin acceso a los pedidos de otras flotas, una activación de Glovo, Uber, Catcher… se ve como una caída sostenida de los pedidos de MushDrink frente a lo habitual del restaurante, sin que caiga su zona ni haya festivo. <span id="sub"></span></div></div>
  <div class="card filters">
    <div class="fg"><span>Fecha</span><div class="nav"><button id="prev">◀</button><select id="fecha"></select><button id="next">▶</button></div></div>
    <div class="fg"><span>Zona</span><select id="zona"></select></div>
    <div class="fg"><span>Coordinador</span><select id="coord"></select></div>
    <div class="fg"><span>Buscar</span><input id="q" type="search" placeholder="Restaurante o código"></div>
    <div class="fg"><span data-t="Caída mínima (ajustada por la zona) para contar un día como día con caída.">Umbral caída %</span><input id="umb" type="number" value="20" min="5" max="80"></div>
    <div class="fg"><span data-t="Días operativos seguidos con caída para marcar alerta roja.">Días seguidos</span><input id="dias" type="number" value="2" min="1" max="7"></div>
    <div class="fg"><span data-t="Pedidos esperados mínimos en el día para evaluar el restaurante (con poco volumen la variación es ruido).">Mín. esperados</span><input id="minv" type="number" value="8" min="1"></div>
    <label class="chk"><input id="solo" type="checkbox" checked> Solo alertas</label>
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
const dl=s=>DW[pd(s).getDay()]+' '+s.slice(8,10)+'/'+s.slice(5,7);
const nf=(v,d=0)=>v==null||!isFinite(v)?'—':v.toLocaleString('es-ES',{minimumFractionDigits:d,maximumFractionDigits:d});
const pc=v=>v==null||!isFinite(v)?'—':nf(v*100,0)+' %';
const N=A.dates.length, IDX=Object.fromEntries(A.dates.map((d,i)=>[d,i]));
const codes=Object.keys(A.T);
// matriz de pedidos: V[c][i]=[total,cena] (0 si el día existe y el restaurante no tuvo pedidos)
const V={};codes.forEach(c=>{const a=Array.from({length:N},()=>[0,0]);A.T[c].forEach(([i,t,ce])=>a[i]=[t,ce]);V[c]=a;});
const HOL={};Object.entries(A.hol).forEach(([c,l])=>{HOL[c]={};l.forEach(x=>{HOL[c][x.slice(0,10)]=x.slice(13);});});
const prevIdx=i=>{const d=pd(A.dates[i]);const o=[];for(let k=1;k<=4;k++){const x=new Date(d);x.setDate(x.getDate()-7*k);const s=x.getFullYear()+'-'+String(x.getMonth()+1).padStart(2,'0')+'-'+String(x.getDate()).padStart(2,'0');if(s in IDX)o.push(IDX[s]);}return o;};
const PREV=A.dates.map((_,i)=>prevIdx(i));
function esperado(c,i,k){const p=PREV[i];if(p.length<2)return null;return p.reduce((a,j)=>a+V[c][j][k],0)/p.length;}
// ratio de zona por día (real ÷ esperado de todos los restaurantes evaluables de la zona)
const ZR={};
function zonaRatio(z,i,k){const key=z+'|'+i+'|'+k;if(key in ZR)return ZR[key];let r=0,e=0;
  codes.forEach(c=>{if((A.R[c]||{}).z!==z)return;const x=esperado(c,i,k);if(x==null||x<3)return;if(HOL[c]&&HOL[c][A.dates[i]])return;r+=V[c][i][k];e+=x;});
  return ZR[key]=e>=20?r/e:1;}
function evalua(c,i,k){const e=esperado(c,i,k);if(e==null)return null;const r=V[c][i][k];const z=(A.R[c]||{}).z;const zr=Math.max(0.5,Math.min(1.5,zonaRatio(z,i,k)));
  return {r,e,raw:e>0?r/e:null,adj:e>0?r/(e*zr):null,zr};}
const S={i:N-1,zona:'',coord:'',q:'',umb:20,dias:2,minv:8,solo:true,sort:'sev',asc:false};
$('fecha').innerHTML=A.dates.map((d,i)=>`<option value="${i}">${dl(d)}/${d.slice(2,4)}</option>`).reverse().join('');
const zonas=[...new Set(codes.map(c=>(A.R[c]||{}).z).filter(Boolean))].sort();
$('zona').innerHTML='<option value="">Todas</option>'+zonas.map(z=>`<option>${z}</option>`).join('');
const coords=[...new Set(codes.map(c=>(A.R[c]||{}).o).filter(Boolean))].sort();
$('coord').innerHTML='<option value="">Todos</option>'+coords.map(z=>`<option>${z}</option>`).join('');
function analiza(c){
  const u=S.umb/100;const d=A.dates[S.i];
  const day=evalua(c,S.i,0),cena=evalua(c,S.i,1);
  if(!day||day.e<S.minv) return null;
  // racha: días seguidos hasta la fecha con caída ≥ umbral (festivos se saltan)
  let racha=0,drops=[];
  for(let j=S.i;j>=0&&j>S.i-14;j--){const dj=A.dates[j];if(HOL[c]&&HOL[c][dj])continue;const x=evalua(c,j,0);if(!x||x.e<S.minv/2)break;const dr=1-x.adj;if(dr>=u){racha++;drops.push(dr);}else break;}
  const hol=HOL[c]&&HOL[c][d];
  const drop=1-day.adj, dropC=cena&&cena.e>=3?1-cena.adj:null;
  let sev=0; // 3 roja, 2 ámbar, 1 vigilar, 0 ok
  if(!hol){ if(racha>=S.dias) sev=3; else if(drop>=u||(dropC!=null&&dropC>=u+0.05)) sev=2; else if(drop>=u/2) sev=1; }
  const est=racha>=S.dias?drops.reduce((a,b)=>a+b,0)/drops.length:(drop>=u?drop:null);
  const spark=[];for(let j=Math.max(0,S.i-13);j<=S.i;j++){const x=evalua(c,j,0);spark.push(x&&x.e>=S.minv/2?{v:x.adj,h:!!(HOL[c]&&HOL[c][A.dates[j]]),d:A.dates[j]}:null);}
  return {c,day,cena,drop,dropC,racha,sev,est,hol,spark,ag:A.ag[c]};
}
function sparkSvg(s){const W=112,H=26;const n=s.length;const bw=W/n;let o=`<svg width="${W}" height="${H}" viewBox="0 0 ${W} ${H}" style="vertical-align:middle">`;
  const y1=H/2;o+=`<line x1="0" x2="${W}" y1="${y1}" y2="${y1}" stroke="#D0D5DD" stroke-dasharray="2 2"/>`;
  s.forEach((x,k)=>{if(!x)return;const v=Math.max(0,Math.min(2,x.v));const y=H-(v/2)*H;const col=x.h?'#9AA1AC':v<1-S.umb/100?'#B42318':v<1?'#E8833A':'#0E5A6B';
    o+=`<rect x="${k*bw+1}" y="${Math.min(y,y1)}" width="${bw-2}" height="${Math.max(1,Math.abs(y-y1))}" fill="${col}"><title>${dl(x.d)}: ${nf(x.v*100,0)} % de lo esperado${x.h?' (festivo)':''}</title></rect>`;});
  return o+'</svg>';}
const SEV=[['p-g','OK'],['p-n','Vigilar'],['p-a','Caída hoy'],['p-r','Alerta']];
function render(){
  $('fecha').value=String(S.i);
  const d=A.dates[S.i];
  let rows=codes.filter(c=>{const r=A.R[c]||{};return(!S.zona||r.z===S.zona)&&(!S.coord||r.o===S.coord)&&(!S.q||(c+' '+r.n).toLowerCase().includes(S.q));}).map(analiza).filter(Boolean);
  const all=rows;
  if(S.solo) rows=rows.filter(x=>x.sev>=2);
  const val=x=>({sev:x.sev*1000+(x.est||0),n:(A.R[x.c]||{}).n,z:(A.R[x.c]||{}).z,e:x.day.e,r:x.day.r,drop:x.drop,dropC:x.dropC,racha:x.racha,est:x.est,ag:x.ag})[S.sort];
  rows.sort((a,b)=>{const va=val(a),vb=val(b);if(va==null&&vb==null)return 0;if(va==null)return 1;if(vb==null)return -1;return(va<vb?-1:va>vb?1:0)*(S.asc?1:-1);});
  const red=all.filter(x=>x.sev===3),amb=all.filter(x=>x.sev===2);
  const perd=red.reduce((a,x)=>a+Math.max(0,x.day.e*x.day.zr-x.day.r),0);
  $('kpis').innerHTML=[[all.length,'Restaurantes evaluados · '+dl(d)],[`<span style="color:var(--red)">${red.length}</span>`,'En alerta (caída '+S.dias+'+ días seguidos)'],[`<span style="color:var(--amb)">${amb.length}</span>`,'Con caída solo hoy'],[nf(perd),'Pedidos/día que faltan en los restaurantes en alerta']].map(([b,s])=>`<div class="kpi"><b>${b}</b><span>${s}</span></div>`).join('');
  const th=(k,l,t,cl)=>`<th class="${cl||''}" data-k="${k}" ${t?`data-t="${t}"`:''}>${l}${S.sort===k?(S.asc?' ▲':' ▼'):''}</th>`;
  $('tab').innerHTML='<thead><tr>'+th('sev','Estado','Alerta: caída ≥ umbral varios días seguidos · Caída hoy: solo la fecha elegida (día o cena) · Vigilar: caída de la mitad del umbral.','l')+th('n','Restaurante','','l')+th('z','Zona / coordinador','','l')+
    th('e','Esperados','Media del mismo día de la semana en las 4 semanas anteriores.')+th('r','Reales','Pedidos MushDrink entregados ese día operativo.')+
    th('drop','Caída día','1 − reales ÷ esperados, ajustado por la tendencia de la zona ese día (si toda la zona cae, no se atribuye al restaurante).')+
    th('dropC','Caída cena','Lo mismo solo de 20:00 a 23:59, donde más venden los agregadores.')+th('racha','Días seguidos','Días operativos seguidos hasta la fecha con caída ≥ umbral (los festivos del restaurante se saltan).')+
    th('est','% estimado a otras flotas','Media de la caída en la racha: aproximación del % de pedidos que puede estar saliendo por otras flotas.')+
    th('ag','% otras flotas (último conocido)','% de pedidos repartidos por flotas distintas de MushDrink en los 28 días hasta '+(A.ag_hasta||'—')+', del informe «Resumen pedidos». Sirve de referencia: si era 0 % y ahora cae un 25 %, es probable una activación nueva.')+
    '<th class="l" data-t="Pedidos reales ÷ esperados (ajustado por zona), últimos 14 días. Línea discontinua = 100 %. Rojo: por debajo del umbral · naranja: por debajo de lo esperado · gris: festivo.">Últimos 14 días</th></tr></thead><tbody>'+
    rows.map(x=>{const r=A.R[x.c]||{};const sv=SEV[x.sev];const dc=v=>v==null?'<span class="mut">—</span>':`<span class="${v>=S.umb/100?'neg':v<0?'pos':''}">${v>0?'−':'+'}${nf(Math.abs(v)*100,0)} %</span>`;
      return `<tr><td class="l"><span class="pill ${sv[0]}">${sv[1]}</span>${x.hol?`<span class="sm">Festivo: ${x.hol}</span>`:''}</td><td class="l"><b>${r.n}</b><span class="sm">${x.c}</span></td><td class="l">${r.z||'—'}<span class="sm">${r.o||''}</span></td>
      <td>${nf(x.day.e,1)}</td><td><b>${x.day.r}</b></td><td>${dc(x.drop)}</td><td>${dc(x.dropC)}${x.cena?`<span class="sm">${x.cena.r} vs ${nf(x.cena.e,1)}</span>`:''}</td><td>${x.racha||'—'}</td>
      <td>${x.est!=null&&x.sev>=2?`<b class="neg">${nf(x.est*100,0)} %</b>`:'<span class="mut">—</span>'}</td><td>${x.ag==null?'<span class="mut">—</span>':pc(x.ag)}</td><td class="l">${sparkSvg(x.spark)}</td></tr>`;}).join('')+
    (rows.length?'':`<tr><td class="l mut" colspan="11">${S.solo?'Ningún restaurante en alerta con estos filtros.':'Sin restaurantes con estos filtros.'}</td></tr>`)+'</tbody>';
  $('sub').textContent='Datos hasta el '+dl(A.dates[N-1])+' · generado '+A.generado+'.';
  $('note').textContent='Cómo leerlo: «Esperados» es lo normal para ese restaurante ese día de la semana. La caída se ajusta por la zona: si toda la zona baja un 15 % (lluvia, partido, puente), solo cuenta lo que el restaurante cae de más. Un festivo del municipio o de la comunidad no cuenta. Una alerta no confirma la activación: confírmala abriendo Glovo, Uber Eats y Just Eat con una dirección de la zona del restaurante, o preguntando al restaurante. Las caídas también pueden deberse a cierres, obras, problemas de tablet o cambios de horario.';
}
$('fecha').onchange=e=>{S.i=+e.target.value;render();};
$('prev').onclick=()=>{if(S.i>0){S.i--;render();}};$('next').onclick=()=>{if(S.i<N-1){S.i++;render();}};
$('zona').onchange=e=>{S.zona=e.target.value;render();};$('coord').onchange=e=>{S.coord=e.target.value;render();};
$('q').oninput=e=>{S.q=e.target.value.trim().toLowerCase();render();};
['umb','dias','minv'].forEach(k=>$(k).oninput=e=>{const v=+e.target.value;if(v>0){S[k]=v;render();}});
$('solo').onchange=e=>{S.solo=e.target.checked;render();};
$('tab').addEventListener('click',e=>{const h=e.target.closest('th[data-k]');if(!h)return;const k=h.dataset.k;if(S.sort===k)S.asc=!S.asc;else{S.sort=k;S.asc=k==='n'||k==='z';}render();});
const tip=$('tip');document.addEventListener('mouseover',e=>{const el=e.target.closest('[data-t]');if(el){tip.textContent=el.dataset.t;tip.hidden=false;}});
document.addEventListener('mousemove',e=>{if(!tip.hidden){tip.style.left=Math.min(e.clientX+12,innerWidth-360)+'px';tip.style.top=(e.clientY+14)+'px';}});
document.addEventListener('mouseout',e=>{const el=e.target.closest('[data-t]');if(el&&!el.contains(e.relatedTarget))tip.hidden=true;});
render();
</script></body></html>"""


def main():
    p = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "..", "mushdrink", "index.html")
    h = open(p, encoding="utf-8").read()
    i0 = h.index("const DOCS=") + len("const DOCS=")
    docs, e0 = json.JSONDecoder().raw_decode(h[i0:])
    data = datos(docs)
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
    open(p, "w", encoding="utf-8").write(h)
    print(f"mushdrink_alerta_agregadores: pestaña {k} · {len(data['T'])} restaurantes · {data['dates'][0]}..{data['dates'][-1]} · "
          f"festivos en {len(data['hol'])} · % otras flotas de {len(data['ag'])} (hasta {data['ag_hasta']})")


if __name__ == "__main__":
    main()
