# -*- coding: utf-8 -*-
"""
Pestaña «Puntualidad» de los dashboards de flota (SAB y GRA-MAD-NOM-ALC): puntualidad al fichar.

Fuente: <dashboard>/liveops_hist.json, que posiciones.py acumula cada 5 min con la Live Operations API de Glovo.
  · Por turno (desde el 12/11/2026): hora de inicio planificada (active_shift_started_at), segundos de retraso
    que da Glovo (time_spent.late_seconds) y primera foto conectado. Entrada real = inicio + retraso.
  · Días anteriores: solo el nº de fotos de 5 min en estado «Con retraso» → minutos de retraso aproximados.

Uso: python3 puntualidad_flota.py <index.html> <sab|gra-mad-nom-alc>
"""
import os, sys, json, datetime as dt

DASH = {"sab": ["SAB"], "gra-mad-nom-alc": ["ALC", "GRA", "MAD", "NOM"]}
_BTN = '<button data-v="puntualidad" aria-pressed="false">Puntualidad</button>'
FOTO_MIN = 5


def datos(html_p, dash):
    p = os.path.join(os.path.dirname(os.path.abspath(html_p)), "liveops_hist.json")
    h = json.load(open(p, encoding="utf-8"))
    filas = []
    for f, dd in sorted(h.get("dias", {}).items()):
        for rid, v in dd.items():
            if not isinstance(v, list) or v[0] not in DASH[dash]:
                continue
            turnos = v[13] if len(v) > 13 and isinstance(v[13], dict) else None
            t = [[ini] + list(x) for ini, x in sorted(turnos.items())] if turnos else None
            filas.append([f, rid, v[0], v[1] or "", int(v[2] or 0), int(v[3] or 0), t])
    return {"filas": filas, "ciudades": DASH[dash], "foto_min": FOTO_MIN,
            "generado": dt.datetime.now().strftime("%Y-%m-%d %H:%M"), "actualizado": h.get("updated_at")}


def seccion():
    return r"""<section id="viewPuntualidad" style="display:none">
<style>
#viewPuntualidad .pu-card{background:#fff;border:1px solid #E4E7EC;border-radius:10px;padding:12px 14px;margin-bottom:12px}
#viewPuntualidad .pu-k{display:flex;flex-wrap:wrap;gap:10px;margin-bottom:12px}
#viewPuntualidad .pu-k div{background:#fff;border:1px solid #E4E7EC;border-radius:10px;padding:9px 14px;min-width:150px}
#viewPuntualidad .pu-k b{display:block;font-size:20px;color:#14171F} #viewPuntualidad .pu-k span{font-size:11.5px;color:#6B7280}
#viewPuntualidad table{width:100%;border-collapse:collapse;font-size:12.6px;table-layout:auto;min-width:0!important}
#viewPuntualidad th{background:#F0F2F5;padding:7px 8px;font-size:11px;color:#6B7280;text-transform:uppercase;letter-spacing:.03em;text-align:right!important;white-space:nowrap;cursor:pointer;position:sticky;top:0}
#viewPuntualidad td{padding:6px 8px;border-top:1px solid #EEF0F3;text-align:right!important;white-space:nowrap;font-variant-numeric:tabular-nums}
#viewPuntualidad th.l,#viewPuntualidad td.l{text-align:left!important}
#viewPuntualidad .mut{color:#6B7280;font-size:11.5px} #viewPuntualidad .zn{font-weight:700;color:#0E5A6B}
#viewPuntualidad .sub{display:block;font-size:10.5px;color:#9AA1AC}
#viewPuntualidad select,#viewPuntualidad input{border:1px solid #E4E7EC;border-radius:8px;padding:5px 7px;font-size:13px;background:#fff}
#viewPuntualidad input[type=number]{width:64px;text-align:right}
#viewPuntualidad .seg2{display:inline-flex;flex-wrap:wrap;gap:4px}
#viewPuntualidad .seg2 button{border:1px solid #E4E7EC;background:#fff;border-radius:8px;padding:5px 10px;font-size:12.5px;cursor:pointer}
#viewPuntualidad .seg2 button.on{background:#0E5A6B;color:#fff;border-color:#0E5A6B}
#viewPuntualidad .pill{display:inline-block;padding:2px 8px;border-radius:99px;font-weight:700;font-size:11.5px}
#viewPuntualidad .ok{background:#D1FADF;color:#05603A} #viewPuntualidad .am{background:#FEF0C7;color:#93370D} #viewPuntualidad .rd{background:#FEE4E2;color:#B42318} #viewPuntualidad .gr{background:#F0F2F5;color:#6B7280}
#viewPuntualidad tr.sel td{background:#EEF6F7} #viewPuntualidad tr.ck{cursor:pointer} #viewPuntualidad tr.ck:hover td{background:#F7F8FA}
</style>
<div class="pu-card" style="display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap;align-items:center">
  <div><b style="font-size:16px">Puntualidad al fichar</b><div class="mut" id="puSub"></div></div>
  <div style="display:flex;gap:14px;flex-wrap:wrap;align-items:center">
    <label class="mut">Periodo <select id="puPer"></select></label>
    <span class="seg2" id="puNodo"></span>
    <label class="mut" title="Retraso a partir del cual el turno cuenta como tarde.">Tolerancia (min) <input id="puTol" type="number" min="0" value="5"></label>
    <label class="mut">Buscar <input id="puBus" type="search" placeholder="ID o nombre" style="width:130px"></label>
  </div>
</div>
<div class="pu-k" id="puKpi"></div>
<div class="pu-card"><div style="font-weight:700;margin-bottom:8px">Riders · pulsa uno para ver el detalle por día</div>
<div style="overflow:auto;max-height:60vh"><table id="puTab"></table></div></div>
<div class="pu-card" id="puDetBox" style="display:none"><div style="font-weight:700;margin-bottom:8px" id="puDetT"></div>
<div style="overflow:auto"><table id="puDet"></table></div></div>
<div class="mut" id="puNota" style="margin:0 0 14px;line-height:1.55"></div>
</section>
"""


def js(data):
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    return r"""<script>
/* ==== Pestaña Puntualidad (Live Operations: inicio de turno y retraso al fichar) ==== */
(function(){
  const PU=""" + payload + r""";
  const seg=document.getElementById('viewSeg'), sec=document.getElementById('viewPuntualidad');
  if(!seg||!sec) return;
  const $=id=>document.getElementById(id);
  const nf=(v,d=0)=>v==null||isNaN(v)?'—':v.toLocaleString('es-ES',{minimumFractionDigits:d,maximumFractionDigits:d});
  const DW=['dom','lun','mar','mié','jue','vie','sáb'];
  const pd=s=>new Date(s+'T12:00:00'); const dl=s=>DW[pd(s).getDay()]+' '+s.slice(8,10)+'/'+s.slice(5,7);
  const isoW=s=>{const d=pd(s);d.setDate(d.getDate()+3-((d.getDay()+6)%7));const y=new Date(d.getFullYear(),0,4);return 1+Math.round(((d-y)/864e5-3+((y.getDay()+6)%7))/7);};
  const hm2m=t=>{const[a,b]=t.split(':').map(Number);return a*60+b;}; const m2hm=m=>{m=((Math.round(m)%1440)+1440)%1440;return String(Math.floor(m/60)).padStart(2,'0')+':'+String(m%60).padStart(2,'0');};
  const hoy=PU.filas.length?PU.filas[PU.filas.length-1][0]:'';
  // [fecha, rid, ciudad, nombre, fotos, fotos late, turnos [[ini, late_s, 1ª conectado, fotos late, fin]] | null]
  const R=PU.filas.map(a=>({f:a[0],id:a[1],c:a[2],nm:a[3],n:a[4],lt:a[5],t:a[6],w:isoW(a[0])}));
  const fechas=[...new Set(R.map(r=>r.f))].sort(); const sems=[...new Set(fechas.map(isoW))].sort((a,b)=>b-a);
  const st={per:'7',nodo:'ALL',tol:5,q:'',sort:'min',asc:false,sel:null};
  $('puPer').innerHTML=[['1','Hoy'],['7','Últimos 7 días'],['14','Últimos 14 días'],['30','Últimos 30 días'],['all','Todo']].map(([v,l])=>`<option value="${v}">${l}</option>`).join('')+sems.map(w=>`<option value="w${w}">Semana ${w}</option>`).join('');
  $('puPer').value='7';
  function enPer(f){if(st.per==='all')return true;if(st.per[0]==='w')return isoW(f)===+st.per.slice(1);const n=+st.per;const i=fechas.indexOf(f);return i>=fechas.length-n;}
  // turnos evaluados de un rider-día
  function turnos(r){
    if(r.t&&r.t.length) return r.t.map(([ini,ls,ok,fl,fin])=>{
      const min=ls/60; let e;
      if(ok) e=min>st.tol?'tarde':'puntual'; else if(fl>0) e=(r.f<hoy||(fin&&hm2m(fin)<hm2m(m2hm(Date.now()/6e4))))?'sinfichar':'pend'; else e='puntual';
      return {f:r.f,ini,fin,min:ok?min:(fl*PU.foto_min),ent:ok?m2hm(hm2m(ini)+min):null,e,aprox:false};});
    if(r.lt>0) return [{f:r.f,ini:null,fin:null,min:r.lt*PU.foto_min,ent:null,e:r.lt*PU.foto_min>st.tol?'tarde':'puntual',aprox:true}];
    return [{f:r.f,ini:null,fin:null,min:0,ent:null,e:'puntual',aprox:true}];
  }
  const EST={puntual:['ok','Puntual'],tarde:['am','Tarde'],sinfichar:['rd','Sin fichar'],pend:['gr','Aún sin fichar']};
  function pintar(){
    $('puNodo').innerHTML=['ALL'].concat(PU.ciudades).map(c=>`<button data-c="${c}" class="${st.nodo===c?'on':''}">${c==='ALL'?'Todos':c}</button>`).join('');
    if(PU.ciudades.length<2) $('puNodo').style.display='none';
    const rs=R.filter(r=>enPer(r.f)&&(st.nodo==='ALL'||r.c===st.nodo)&&(!st.q||(r.id+' '+r.nm).toLowerCase().includes(st.q)));
    const by={};rs.forEach(r=>{const o=by[r.id]=by[r.id]||{id:r.id,nm:r.nm,c:r.c,dias:0,T:[]};o.dias++;o.nm=r.nm||o.nm;o.T.push(...turnos(r));});
    const L=Object.values(by).map(o=>{const tar=o.T.filter(x=>x.e==='tarde'),sf=o.T.filter(x=>x.e==='sinfichar');
      const mins=tar.reduce((a,x)=>a+x.min,0);
      return {...o,nt:o.T.length,tar:tar.length,sf:sf.length,min:mins,med:tar.length?mins/tar.length:null,peor:tar.length?Math.max(...tar.map(x=>x.min)):null,
        pct:o.T.length?(o.T.length-tar.length-sf.length)/o.T.length:null,ult:tar.concat(sf).map(x=>x.f).sort().pop()||null};});
    const v=x=>x[st.sort]; L.sort((a,b)=>{const va=v(a),vb=v(b);if(va==null&&vb==null)return 0;if(va==null)return 1;if(vb==null)return -1;return(va<vb?-1:va>vb?1:0)*(st.asc?1:-1);});
    const all=L.flatMap(o=>o.T),tar=all.filter(x=>x.e==='tarde'),sf=all.filter(x=>x.e==='sinfichar');
    const mins=tar.reduce((a,x)=>a+x.min,0);
    $('puKpi').innerHTML=[[nf(all.length),'Turnos analizados'],[all.length?nf((all.length-tar.length-sf.length)/all.length*100,1)+' %':'—','Puntualidad (≤ '+st.tol+' min)'],
      [nf(tar.length),'Turnos con entrada tarde'],[nf(sf.length),'Turnos sin fichar'],[nf(mins/60,1)+' h','Retraso acumulado'],[tar.length?nf(mins/tar.length,0)+' min':'—','Retraso medio al llegar tarde'],
      [nf(L.filter(o=>o.tar+o.sf>=3).length),'Riders con 3+ incidencias']].map(([a,b])=>`<div><b>${a}</b><span>${b}</span></div>`).join('');
    const th=(k,l,cl,t)=>`<th class="${cl||''}" data-k="${k}" ${t?`title="${t}"`:''}>${l}${st.sort===k?(st.asc?' ▲':' ▼'):''}</th>`;
    $('puTab').innerHTML='<tr>'+th('id','Rider','l')+th('c','Nodo','l')+th('dias','Días')+th('nt','Turnos','','Turnos con hora de inicio de Live Operations; en días anteriores al 12/11, 1 por día (aproximado).')+
      th('pct','% puntual')+th('tar','Tarde','','Turnos con entrada más tarde que la tolerancia.')+th('sf','Sin fichar','','Turnos que pasaron enteros en estado «Con retraso» sin conectarse.')+
      th('min','Min. de retraso','','Suma de minutos de retraso de los turnos tarde.')+th('med','Retraso medio')+th('peor','Peor retraso')+th('ult','Última incidencia')+'</tr>'+
      L.map(o=>`<tr class="ck${st.sel===o.id?' sel':''}" data-id="${o.id}"><td class="l"><b>${o.id}</b>${o.nm?`<span class="sub">${o.nm}</span>`:''}</td><td class="l zn">${o.c}</td><td>${o.dias}</td><td>${o.nt}</td>`+
        `<td><span class="pill ${o.pct==null?'gr':o.pct>=0.95?'ok':o.pct>=0.8?'am':'rd'}">${o.pct==null?'—':nf(o.pct*100,0)+' %'}</span></td><td>${o.tar||'—'}</td><td>${o.sf?`<b style="color:#B42318">${o.sf}</b>`:'—'}</td>`+
        `<td>${o.min?nf(o.min,0):'—'}</td><td>${o.med==null?'—':nf(o.med,0)+' min'}</td><td>${o.peor==null?'—':nf(o.peor,0)+' min'}</td><td>${o.ult?dl(o.ult):'—'}</td></tr>`).join('')+
      (L.length?'':'<tr><td class="l mut" colspan="11">Sin datos para este filtro.</td></tr>');
    $('puTab').querySelectorAll('tr.ck').forEach(tr=>tr.onclick=()=>{st.sel=st.sel===tr.dataset.id?null:tr.dataset.id;pintar();});
    $('puTab').querySelectorAll('th[data-k]').forEach(h=>h.onclick=()=>{const k=h.dataset.k;if(st.sort===k)st.asc=!st.asc;else{st.sort=k;st.asc=k==='id'||k==='c'||k==='pct';}pintar();});
    const o=st.sel&&by[st.sel]?L.find(x=>x.id===st.sel):null;
    $('puDetBox').style.display=o?'':'none';
    if(o){$('puDetT').textContent='Detalle · '+o.id+(o.nm?' · '+o.nm:'')+' · '+o.c;
      $('puDet').innerHTML='<tr><th class="l">Día</th><th>Inicio planificado</th><th>Fin</th><th>Entrada real</th><th>Retraso</th><th class="l">Estado</th></tr>'+
        o.T.slice().sort((a,b)=>(b.f+(b.ini||'')).localeCompare(a.f+(a.ini||''))).map(x=>`<tr><td class="l">${dl(x.f)}</td><td>${x.ini||'<span class="mut">—</span>'}</td><td>${x.fin||'<span class="mut">—</span>'}</td><td>${x.ent||'<span class="mut">—</span>'}</td>`+
          `<td>${x.min?nf(x.min,0)+' min'+(x.aprox?' <span class="mut">(aprox.)</span>':''):'0'}</td><td class="l"><span class="pill ${EST[x.e][0]}">${EST[x.e][1]}</span></td></tr>`).join('');}
    const pre=R.some(r=>!r.t);
    $('puSub').textContent='Live Operations de Glovo · fotos cada '+PU.foto_min+' min · '+(fechas.length?dl(fechas[0])+' – '+dl(fechas[fechas.length-1]):'sin datos')+' · generado '+PU.generado;
    $('puNota').innerHTML='<b>Cómo se calcula.</b> Inicio planificado = hora de inicio del turno que da Glovo (active_shift_started_at). Retraso = segundos de retraso que da Glovo al fichar (late_seconds); entrada real = inicio + retraso. «Sin fichar» = el turno pasó entero en estado «Con retraso» sin llegar a conectarse (equivale a un no show). '+
      (pre?'Los días anteriores al 12/11 no tienen el detalle por turno: el retraso se estima con las fotos de 5 min en estado «Con retraso» (marcado como aprox.) y cuentan como un turno por día.':'');
  }
  $('puPer').onchange=e=>{st.per=e.target.value;pintar();};
  $('puNodo').addEventListener('click',e=>{const b=e.target.closest('button');if(!b)return;st.nodo=b.dataset.c;pintar();});
  $('puTol').oninput=e=>{st.tol=Math.max(0,+e.target.value||0);pintar();};
  $('puBus').oninput=e=>{st.q=e.target.value.trim().toLowerCase();pintar();};
  seg.querySelectorAll('button').forEach(b=>b.addEventListener('click',()=>{
    const on=b.dataset.v==='puntualidad';
    sec.style.display=on?'':'none';
    if(on){ seg.querySelectorAll('button').forEach(x=>x.setAttribute('aria-pressed',String(x===b)));
      ['viewSemanal','viewDiario','viewLiga','viewTemporal','viewForecast','viewScoring'].forEach(id=>{const e=document.getElementById(id); if(e) e.style.display='none';});
      window.scrollTo(0,0); pintar(); }
  }));
  pintar();
})();
</script>
"""


def integrar(html, data):
    i, j = html.find("<!-- puntualidad_flota -->"), html.find("<!-- /puntualidad_flota -->")
    if i >= 0 and j > i: html = html[:i] + html[j + len("<!-- /puntualidad_flota -->"):]
    html = html.replace(" " + _BTN, "").replace(_BTN, "")
    i = html.find('<section id="viewPuntualidad"')
    if i >= 0: html = html[:i] + html[html.find("</section>", i) + len("</section>"):]
    seg = html.find('id="viewSeg"'); end = html.find("</div>", seg)
    if seg < 0 or end < 0 or '<div id="viewSemanal">' not in html or "</body>" not in html:
        raise ValueError("la plantilla no tiene el selector de Vista esperado")
    html = html[:end] + "  " + _BTN + "\n      " + html[end:]
    html = html.replace('<div id="viewSemanal">', seccion() + '  <div id="viewSemanal">', 1)
    k = html.rindex("</body>")
    return html[:k] + "<!-- puntualidad_flota -->" + js(data) + "<!-- /puntualidad_flota -->\n" + html[k:]


def main():
    html_p, dash = sys.argv[1], sys.argv[2]
    data = datos(html_p, dash)
    h = open(html_p, encoding="utf-8").read()
    open(html_p, "w", encoding="utf-8").write(integrar(h, data))
    con = sum(1 for f in data["filas"] if f[6])
    print(f"puntualidad_flota {dash}: {len(data['filas'])} rider-días · {con} con detalle por turno")


if __name__ == "__main__":
    main()
