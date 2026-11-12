# -*- coding: utf-8 -*-
"""
Pestaña «Actividad del rider» de los dashboards de flota (SAB y GRA-MAD-NOM-ALC).

Qué está haciendo ahora cada rider y qué ha hecho hoy, con datos de la Live Operations API de Glovo:
  · posiciones.py escribe cada minuto <dashboard>/actividad_hoy.json (estado actual de cada rider + línea de
    tiempo del día en franjas de 5 min). Sin teléfono, email ni GPS: los links son públicos.
  · La pestaña lo lee al abrirse y cada minuto: primero la rama «vivo» (un fichero por minuto, llega en 1–2 min);
    si no está, el actividad_hoy.json de la web (se publica cada ~10 min).

Uso: python3 actividad_flota.py <index.html> <sab|gra-mad-nom-alc>
"""
import sys, json

DASH = {"sab": ["SAB"], "gra-mad-nom-alc": ["ALC", "GRA", "MAD", "NOM"]}
_BTN = '<button data-v="actividad" aria-pressed="false">Actividad del rider</button>'


def seccion():
    return r"""<section id="viewActividad" style="display:none">
<style>
#viewActividad .ac-card{background:#fff;border:1px solid #E4E7EC;border-radius:10px;padding:12px 14px;margin-bottom:12px}
#viewActividad .ac-k{display:flex;flex-wrap:wrap;gap:10px;margin-bottom:12px}
#viewActividad .ac-k div{background:#fff;border:1px solid #E4E7EC;border-radius:10px;padding:9px 14px;min-width:130px}
#viewActividad .ac-k b{display:block;font-size:20px;color:#14171F} #viewActividad .ac-k span{font-size:11.5px;color:#6B7280}
#viewActividad table{width:100%;border-collapse:collapse;font-size:12.6px;min-width:0!important}
#viewActividad th{background:#F0F2F5;padding:7px 8px;font-size:11px;color:#6B7280;text-transform:uppercase;letter-spacing:.03em;text-align:right!important;white-space:nowrap;cursor:pointer;position:sticky;top:0;z-index:1}
#viewActividad td{padding:6px 8px;border-top:1px solid #EEF0F3;text-align:right!important;white-space:nowrap;font-variant-numeric:tabular-nums}
#viewActividad th.l,#viewActividad td.l{text-align:left!important}
#viewActividad .mut{color:#6B7280;font-size:11.5px} #viewActividad .zn{font-weight:700;color:#0E5A6B} #viewActividad .sub{display:block;font-size:10.5px;color:#9AA1AC}
#viewActividad input,#viewActividad select{border:1px solid #E4E7EC;border-radius:8px;padding:5px 8px;font-size:13px;background:#fff}
#viewActividad .seg2{display:inline-flex;flex-wrap:wrap;gap:4px}
#viewActividad .seg2 button{border:1px solid #E4E7EC;background:#fff;border-radius:8px;padding:5px 10px;font-size:12.5px;cursor:pointer}
#viewActividad .seg2 button.on{background:#0E5A6B;color:#fff;border-color:#0E5A6B}
#viewActividad .pill{display:inline-flex;align-items:center;gap:6px;padding:2px 9px;border-radius:99px;font-size:12px;background:#F0F2F5}
#viewActividad .pill i{width:8px;height:8px;border-radius:50%;display:inline-block}
#viewActividad tr.ck{cursor:pointer} #viewActividad tr.ck:hover td{background:#F7F8FA} #viewActividad tr.sel td{background:#EEF6F7}
#viewActividad .bad{color:#B42318;font-weight:650}
#viewActividad .kv{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:8px 18px;font-size:13px;margin-top:10px}
#viewActividad .kv div span{display:block;font-size:11px;color:#6B7280;text-transform:uppercase;letter-spacing:.03em}
#viewActividad .leg{display:flex;flex-wrap:wrap;gap:12px;font-size:12px;color:#4B5563;margin:6px 0}
#viewActividad .leg i{display:inline-block;width:10px;height:10px;border-radius:3px;margin-right:5px;vertical-align:-1px}
</style>
<div class="ac-card" style="display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap;align-items:center">
  <div><b style="font-size:16px">Actividad del rider</b><div class="mut" id="acSub">Cargando datos en vivo…</div></div>
  <div style="display:flex;gap:14px;flex-wrap:wrap;align-items:center">
    <span class="seg2" id="acNodo"></span>
    <label class="mut">Estado <select id="acEst"></select></label>
    <label class="mut">Buscar <input id="acBus" type="search" placeholder="ID o nombre" style="width:150px"></label>
  </div>
</div>
<div class="ac-k" id="acKpi"></div>
<div class="ac-card" id="acDetBox" style="display:none"></div>
<div class="ac-card"><div style="font-weight:700;margin-bottom:4px">Riders con actividad hoy · pulsa uno para ver su día</div>
<div class="leg" id="acLeg"></div>
<div style="overflow:auto;max-height:65vh"><table id="acTab"></table></div></div>
<div class="mut" style="margin:0 0 14px;line-height:1.55">Datos de la Live Operations API de Glovo, muestreados cada minuto; la pestaña se refresca sola cada minuto mientras está abierta. Línea del día: estado de cada franja de 5 min desde las 07:00 (la madrugada al final). No se publican teléfono, email ni posición GPS porque estos links son públicos.</div>
</section>
"""


def js(dash):
    cfg = json.dumps({"ciudades": DASH[dash]})
    return r"""<script>
/* ==== Pestaña Actividad del rider (Live Operations cada minuto: actividad_hoy.json) ==== */
(function(){
  const CFG=""" + cfg + r""";
  const seg=document.getElementById('viewSeg'), sec=document.getElementById('viewActividad');
  if(!seg||!sec) return;
  const $=id=>document.getElementById(id);
  const RAW='https://raw.githubusercontent.com/rodjacin/Flota-dashboards/vivo/';
  const CARP=(()=>{try{const s=new URL(document.baseURI).pathname.split('/').filter(x=>x&&!/\.html?$/i.test(x));return s[s.length-1]||'';}catch(e){return '';}})();
  const ST={w:['Trabajando','#2a78d6'],r:['Esperando pedido','#0a7f0a'],l:['Con retraso','#d03b3b'],b:['En pausa','#b7791f'],s:['Empezando','#6d5bd0'],e:['Terminando','#7a8699'],t:['Parado temporalmente','#9AA1AC'],n:['No trabajando','#E4E7EC']};
  const COD={working:'w',ready:'r',available:'r',late:'l',break:'b',starting:'s',ending:'e',temp_not_working:'t',not_working:'n'};
  const nf=(v,d=0)=>v==null||isNaN(v)?'—':Number(v).toLocaleString('es-ES',{minimumFractionDigits:d,maximumFractionDigits:d});
  const pc=v=>v==null||isNaN(v)?'—':nf(v<=1?v*100:v,1)+' %';
  const hhmm=s=>{if(!s)return '—';const d=new Date(s);return isNaN(d)?'—':d.toLocaleTimeString('es-ES',{timeZone:'Europe/Madrid',hour:'2-digit',minute:'2-digit'});};
  const hm=sec=>sec==null?'—':(sec>=3600?Math.floor(sec/3600)+' h '+String(Math.round(sec%3600/60)).padStart(2,'0')+' min':Math.round(sec/60)+' min');
  const esc=s=>String(s??'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
  // orden de franjas: 07:00 → 06:55 (la madrugada al final)
  const ORDEN=[...Array(288)].map((_,i)=>(i+84)%288);
  let A=null, vivoM=0, timer=null;
  const st={nodo:'ALL',est:'ALL',q:'',sort:'st',asc:true,sel:null};
  const P=r=>({c:r[0],nm:r[1],st:r[2],mot:r[3],por:r[4],ini:r[5],fin:r[6],act:r[7],notif:r[8],comp:r[9],canc:r[10],acc:r[11],utr:r[12],ar:r[13],rr:r[14],wk:r[15],lt:r[16],br:r[17],nb:r[18],wal:r[19],wls:r[20],zona:r[21],sp:r[22],veh:r[23],loc:r[24]});
  function barra(tl,w,h,eje){
    if(!tl) return '';
    const sw=w/288; let o=`<svg width="${w}" height="${h+(eje?14:0)}" viewBox="0 0 ${w} ${h+(eje?14:0)}" style="display:block">`;
    o+=`<rect x="0" y="0" width="${w}" height="${h}" fill="#F7F8FA" rx="3"/>`;
    let k=0; while(k<288){const ch=tl[ORDEN[k]];let j=k;while(j+1<288&&tl[ORDEN[j+1]]===ch)j++;
      if(ch&&ch!=='.'&&ST[ch]) o+=`<rect x="${(k*sw).toFixed(1)}" y="0" width="${((j-k+1)*sw).toFixed(1)}" height="${h}" fill="${ST[ch][1]}"><title>${ST[ch][0]} · ${lab(ORDEN[k])}–${lab((ORDEN[j]+1)%288)}</title></rect>`;
      k=j+1;}
    if(eje) for(let i=0;i<=288;i+=24){const x=Math.min(w-1,i*sw);o+=`<line x1="${x}" x2="${x}" y1="${h}" y2="${h+4}" stroke="#9AA1AC"/><text x="${Math.min(w-14,Math.max(0,x-13))}" y="${h+13}" font-size="10" fill="#6B7280">${lab(ORDEN[i%288])}</text>`;}
    if(A&&A.slot!=null){const p=ORDEN.indexOf(A.slot);o+=`<line x1="${(p+1)*sw}" x2="${(p+1)*sw}" y1="0" y2="${h}" stroke="#14171F" stroke-width="1.5"/>`;}
    return o+'</svg>';}
  const lab=s=>String(Math.floor(s/12)).padStart(2,'0')+':'+String(s%12*5).padStart(2,'0');
  const minutos=tl=>{const o={};if(tl)for(const ch of tl)if(ch!=='.')o[ch]=(o[ch]||0)+5;return o;};
  function pintar(){
    if(!A){$('acSub').textContent='Todavía no hay datos de actividad (se generan con el muestreo de cada minuto).';return;}
    const foto=A.foto?new Date(A.foto):null, hace=foto?Math.round((Date.now()-foto)/60000):null;
    $('acSub').innerHTML=`Foto de las <b>${hhmm(A.foto)}</b>`+(hace!=null?` · hace ${hace} min`:'')+(hace!=null&&hace>15?' <span class="bad">(datos atrasados)</span>':'')+` · día ${A.fecha.slice(8,10)}/${A.fecha.slice(5,7)}`;
    $('acNodo').innerHTML=CFG.ciudades.length<2?'':['ALL'].concat(CFG.ciudades).map(c=>`<button data-c="${c}" class="${st.nodo===c?'on':''}">${c==='ALL'?'Todos':c}</button>`).join('');
    // riders: actuales + los que tuvieron actividad hoy
    const ids=new Set([...Object.keys(A.act||{}),...Object.keys(A.tl||{})]);
    let L=[...ids].map(id=>{const r=A.act&&A.act[id]?P(A.act[id]):{c:(A.nm[id]||[])[0],nm:(A.nm[id]||[])[1],st:'not_working'};return {id,...r,cod:COD[r.st]||'n',tl:(A.tl||{})[id]};})
      .filter(r=>CFG.ciudades.includes(r.c));
    const base=L.filter(r=>(st.nodo==='ALL'||r.c===st.nodo)&&(!st.q||(r.id+' '+(r.nm||'')).toLowerCase().includes(st.q)));
    const cnt={};base.forEach(r=>cnt[r.cod]=(cnt[r.cod]||0)+1);
    const ests=['w','r','s','l','b','e','t','n'].filter(k=>cnt[k]);
    $('acEst').innerHTML=`<option value="ALL">Todos (${base.length})</option>`+ests.map(k=>`<option value="${k}">${ST[k][0]} (${cnt[k]})</option>`).join('');$('acEst').value=ests.includes(st.est)?st.est:'ALL';
    L=base.filter(r=>st.est==='ALL'||r.cod===st.est);
    const ord='wrslbetn';const val=r=>({st:ord.indexOf(r.cod),id:r.id,c:r.c,comp:r.comp,utr:r.utr,rr:r.rr,lt:r.lt,br:r.br,wal:r.wal,wk:r.wk})[st.sort];
    L.sort((a,b)=>{const x=val(a),y=val(b);if(x==null&&y==null)return 0;if(x==null)return 1;if(y==null)return -1;return(x<y?-1:x>y?1:0)*(st.asc?1:-1);});
    const on=base.filter(r=>r.cod!=='n');
    $('acKpi').innerHTML=[[on.length,'Conectados ahora'],[cnt.w||0,'Trabajando'],[cnt.r||0,'Esperando pedido'],[`<span class="${cnt.l?'bad':''}">${cnt.l||0}</span>`,'Con retraso'],[cnt.b||0,'En pausa'],[cnt.t||0,'Parados temporalmente'],[base.length,'Riders con actividad hoy']]
      .map(([a,b])=>`<div><b>${a}</b><span>${b}</span></div>`).join('');
    $('acLeg').innerHTML=['w','r','s','l','b','e','t'].map(k=>`<span><i style="background:${ST[k][1]}"></i>${ST[k][0]}</span>`).join('');
    const th=(k,l,cl)=>`<th class="${cl||''}" data-k="${k}">${l}${st.sort===k?(st.asc?' ▲':' ▼'):''}</th>`;
    $('acTab').innerHTML='<tr>'+th('id','Rider','l')+th('c','Nodo','l')+th('st','Estado','l')+'<th class="l">Turno</th><th class="l">Pedido</th>'+th('comp','Entregas')+th('utr','UTR')+th('rr','Reasig.')+th('lt','Retraso')+th('br','Pausas')+th('wal','Monedero')+'<th class="l">Hoy (07:00 → madrugada)</th></tr>'+
      L.map(r=>{const s=ST[r.cod]||ST.n;return `<tr class="ck${st.sel===r.id?' sel':''}" data-id="${r.id}"><td class="l"><b>${r.id}</b><span class="sub">${esc(r.nm||'')}</span></td><td class="l zn">${r.c}</td>`+
        `<td class="l"><span class="pill"><i style="background:${s[1]}"></i>${s[0]}</span>${r.mot?`<span class="sub">${esc(r.mot)}${r.por?' · por '+esc(r.por):''}</span>`:''}</td>`+
        `<td class="l">${r.ini?hhmm(r.ini)+'–'+hhmm(r.fin):'<span class="mut">—</span>'}</td><td class="l">${r.act?'<b>Sí</b>':'<span class="mut">No</span>'}</td>`+
        `<td>${nf(r.comp)}</td><td>${nf(r.utr,2)}</td><td>${pc(r.rr)}</td><td>${r.lt?`<span class="bad">${hm(r.lt)}</span>`:'—'}</td><td>${r.br?hm(r.br)+(r.nb?` (${r.nb})`:''):'—'}</td>`+
        `<td>${r.wal==null?'—':nf(r.wal,2)+' €'}</td><td class="l">${barra(r.tl,220,12,false)}</td></tr>`;}).join('')+
      (L.length?'':'<tr><td class="l mut" colspan="12">Ningún rider con estos filtros.</td></tr>');
    $('acTab').querySelectorAll('tr.ck').forEach(tr=>tr.onclick=()=>{st.sel=st.sel===tr.dataset.id?null:tr.dataset.id;pintar();});
    $('acTab').querySelectorAll('th[data-k]').forEach(h=>h.onclick=()=>{const k=h.dataset.k;if(st.sort===k)st.asc=!st.asc;else{st.sort=k;st.asc=['st','id','c'].includes(k);}pintar();});
    const r=st.sel?([...ids].includes(st.sel)?(A.act[st.sel]?{id:st.sel,...P(A.act[st.sel]),tl:A.tl[st.sel]}:{id:st.sel,c:(A.nm[st.sel]||[])[0],nm:(A.nm[st.sel]||[])[1],st:'not_working',tl:A.tl[st.sel]}):null):null;
    const box=$('acDetBox');box.style.display=r?'':'none';
    if(r){const s=ST[COD[r.st]||'n'];const m=minutos(r.tl);
      box.innerHTML=`<div style="display:flex;justify-content:space-between;gap:10px;flex-wrap:wrap;align-items:center"><div><b style="font-size:16px">${r.id} · ${esc(r.nm||'')}</b> <span class="zn">${r.c}</span> <span class="pill" style="margin-left:6px"><i style="background:${s[1]}"></i>${s[0]}</span>`+
        (r.mot?` <span class="mut">${esc(r.mot)}${r.por?' · cambiado por '+esc(r.por):''}</span>`:'')+`</div><button class="pill" style="cursor:pointer;border:0" id="acCerrar">Cerrar ✕</button></div>`+
        `<div style="margin-top:12px;overflow:auto">${barra(r.tl,900,22,true)}</div>`+
        `<div class="leg">${Object.entries(m).filter(([k])=>ST[k]&&k!=='n').map(([k,v])=>`<span><i style="background:${ST[k][1]}"></i>${ST[k][0]}: <b>${hm(v*60)}</b></span>`).join('')||'<span class="mut">Sin actividad registrada hoy</span>'}</div>`+
        `<div class="kv">`+[['Turno',r.ini?hhmm(r.ini)+' – '+hhmm(r.fin):'—'],['Zona',r.zona||'—'],['Punto de inicio',r.sp||'—'],['Vehículo',r.veh||'—'],['Pedido activo',r.act?'Sí':'No'],
          ['Notificados / aceptados',nf(r.notif)+' / '+nf(r.acc)],['Entregas completadas',nf(r.comp)],['Canceladas',nf(r.canc)],['UTR',nf(r.utr,2)],['Aceptación',pc(r.ar)],['Reasignación',pc(r.rr)],
          ['Tiempo trabajado',hm(r.wk)],['Retraso al fichar',hm(r.lt)],['Pausas',hm(r.br)+(r.nb?` (${r.nb})`:'')],['Monedero',r.wal==null?'—':nf(r.wal,2)+' €'+(r.wls?` · ${esc(r.wls)}`:'')],['Ubicación actualizada',hhmm(r.loc)]]
          .map(([a,b])=>`<div><span>${a}</span>${b}</div>`).join('')+`</div>`;
      $('acCerrar').onclick=()=>{st.sel=null;pintar();};}
  }
  async function cargar(){
    let ok=false;
    if(/^(sab|gra-mad-nom-alc)$/.test(CARP)&&window.fetch){const now=Date.now(),M=Math.floor(now/60000),k0=(now%60000)<25000?1:0;
      for(let k=k0;k<9&&!ok;k++){const m=M-k;if(m<=vivoM){ok=true;break;}try{const r=await fetch(RAW+CARP+'/a/'+m+'.json');if(r.ok){A=await r.json();vivoM=m;ok=true;}}catch(e){break;}}}
    if(!ok){try{const r=await fetch(new URL('actividad_hoy.json?t='+Date.now(),document.baseURI),{cache:'no-store'});if(r.ok)A=await r.json();}catch(e){}}
    pintar();
  }
  $('acNodo').addEventListener('click',e=>{const b=e.target.closest('button');if(!b)return;st.nodo=b.dataset.c;pintar();});
  $('acEst').onchange=e=>{st.est=e.target.value;pintar();};
  $('acBus').oninput=e=>{st.q=e.target.value.trim().toLowerCase();pintar();};
  seg.querySelectorAll('button').forEach(b=>b.addEventListener('click',()=>{
    const on=b.dataset.v==='actividad';
    sec.style.display=on?'':'none';
    clearInterval(timer);
    if(on){ seg.querySelectorAll('button').forEach(x=>x.setAttribute('aria-pressed',String(x===b)));
      ['viewSemanal','viewDiario','viewLiga','viewTemporal','viewForecast','viewScoring','viewPuntualidad'].forEach(id=>{const e=document.getElementById(id); if(e) e.style.display='none';});
      window.scrollTo(0,0); cargar(); timer=setInterval(cargar,60000); }
  }));
})();
</script>
"""


def integrar(html, dash):
    i, j = html.find("<!-- actividad_flota -->"), html.find("<!-- /actividad_flota -->")
    if i >= 0 and j > i: html = html[:i] + html[j + len("<!-- /actividad_flota -->"):]
    html = html.replace(" " + _BTN, "").replace(_BTN, "")
    i = html.find('<section id="viewActividad"')
    if i >= 0: html = html[:i] + html[html.find("</section>", i) + len("</section>"):]
    seg = html.find('id="viewSeg"'); end = html.find("</div>", seg)
    if seg < 0 or end < 0 or '<div id="viewSemanal">' not in html or "</body>" not in html:
        raise ValueError("la plantilla no tiene el selector de Vista esperado")
    html = html[:end] + "  " + _BTN + "\n      " + html[end:]
    html = html.replace('<div id="viewSemanal">', seccion() + '  <div id="viewSemanal">', 1)
    k = html.rindex("</body>")
    return html[:k] + "<!-- actividad_flota -->" + js(dash) + "<!-- /actividad_flota -->\n" + html[k:]


def main():
    html_p, dash = sys.argv[1], sys.argv[2]
    h = open(html_p, encoding="utf-8").read()
    open(html_p, "w", encoding="utf-8").write(integrar(h, dash))
    print(f"actividad_flota {dash}: pestaña añadida")


if __name__ == "__main__":
    main()
