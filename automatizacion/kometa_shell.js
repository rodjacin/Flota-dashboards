/* Contenedor del panel MushDrink · tema Kometa (verde agua, naranja y blanco).
   Las pestañas siguen saliendo de los <button class="tab"> ocultos del contenedor oculto .tabs,
   que los scripts de automatización amplían; aquí solo se agrupan por secciones. */
function MDboot(DOCS){
  window.MD_DOCS=DOCS;
  const SECCIONES=[
    {k:'general',n:'Visión general',t:['Evolución del negocio','Resumen','Live Operations','Grafana']},
    {k:'riders',n:'Repartidores',t:['Repartidores · SLA','Pedidos por rider · 15 min','Pedidos por repartidor','Entregados Ilocalizables','Agrupación de pedidos','Mapa']},
    {k:'rest',n:'Restaurantes',t:['Operativa restaurantes','Pedidos por restaurante','Nº pedidos/hora','Horas valle','MCD']},
    {k:'plan',n:'Planificación',t:['Proyección vs mes anterior','Simulador','Punto de Equilibrio','Festivos']},
    {k:'com',n:'Agregadores y comercial',t:['Agregadores','Alerta agregadores','Leads delivery']}
  ];
  const ALIAS={'Grafana':'Tiempos por estado (Kometa)'};
  const $=id=>document.getElementById(id);
  const tabs=[...document.querySelectorAll('.tabs .tab')].map(b=>({i:+b.dataset.i,l:b.textContent.trim(),b}));
  const secOf={}; SECCIONES.forEach(s=>s.t.forEach(l=>secOf[l]=s.k));
  const secs=SECCIONES.map(s=>({...s,items:s.t.map(l=>tabs.find(t=>t.l===l)).filter(Boolean)}));
  const otros=tabs.filter(t=>!secOf[t.l]); if(otros.length) secs.push({k:'otros',n:'Otros',items:otros});
  const vis=secs.filter(s=>s.items.length);
  const name=t=>ALIAS[t.l]||t.l;

  /* ---- tema: las pestañas oscuras se pasan a la paleta clara de Kometa al cargarlas ---- */
  const DARK={
    '0f1115':'f4f9f8','0e1216':'f4f9f8','0b0d12':'f4f9f8','15181f':'f4f9f8','191d26':'f4f9f8','0b0e12':'f4f9f8',
    '171a21':'ffffff','151b23':'ffffff','1a1e27':'ffffff','141922':'ffffff',
    '1d212b':'f0f7f6','1a222c':'f0f7f6','1c2130':'f0f7f6','1b232d':'f0f7f6','0f1319':'f0f7f6',
    '232836':'e4f2ef','232c37':'e4f2ef','20294a':'e4f2ef','1d2430':'e4f2ef',
    '2a2f3a':'d8e7e4','28313d':'d8e7e4','2b3542':'d8e7e4','1f2731':'d8e7e4',
    '3a4252':'c3d6d2','3a4756':'c3d6d2','4a5263':'c3d6d2',
    'e6e8ee':'16302c','e9ecf1':'16302c','c9ced8':'3c5a55','cfdcff':'0b6f66',
    '9aa3b2':'58706c','98a3b3':'58706c','8b93a7':'58706c','6b7383':'8aa19d','636e7d':'8aa19d',
    '5b8cff':'14a394','9ec1ff':'0b6f66','7cc7ff':'0b6f66','3a4b7a':'7fd3c8','4fd1b4':'14a394','3fb9a8':'14a394',
    'e0a94a':'f28c28','eb8a3c':'f28c28','f6a94a':'f28c28','f0a04b':'f28c28','f0b54a':'f28c28','f0a35e':'f28c28','f6bd77':'b85a07',
    '3fb984':'1f9d63','7bd88f':'1f9d63','7fd9b3':'1f8a5c',
    'e5624d':'d6452f','ff6b5e':'d6452f','ef6b6b':'d6452f','e5484d':'d6452f','ff6b5b':'d6452f'
  };
  const LIGHT={'1f6f6a':'14a394','0e3f3c':'0b6f66','0e5a6b':'0b7f74','0b7285':'0b7f74','e8833a':'f28c28'};
  const RGB={'23,26,33':'255,255,255','0,0,0':'16,52,48','5,8,12':'16,52,48','14,18,22':'16,52,48','79,209,180':'20,163,148','246,169,74':'242,140,40','91,140,255':'20,163,148','124,199,255':'20,163,148'};
  const reHex=m=>new RegExp('#('+Object.keys(m).join('|')+')(?![0-9a-f])','gi');
  const RE_D=reHex(DARK), RE_L=reHex(LIGHT), RE_RGB=/rgba\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*,/g;
  const CSS='<style id="kometa-tema">:root{color-scheme:light}html{scrollbar-color:#bfd8d3 transparent}'+
    '::-webkit-scrollbar{width:10px;height:10px}::-webkit-scrollbar-thumb{background:#c9dfdb;border-radius:8px;border:2px solid transparent;background-clip:padding-box}'+
    '::selection{background:#bfe9e2}</style>';
  const esOscura=doc=>{const m=/--bg\s*:\s*#([0-9a-f]{6})/i.exec(doc);if(!m)return false;const n=parseInt(m[1],16);
    return (0.2126*(n>>16&255)+0.7152*(n>>8&255)+0.0722*(n&255))/255<0.35;};
  const tematiza=doc=>{
    if(doc.startsWith('<!-- EVOLUCION_NEGOCIO -->')) return doc;
    let out=esOscura(doc)?doc.replace(RE_D,(_,h)=>'#'+DARK[h.toLowerCase()]).replace(/color-scheme\s*:\s*dark/g,'color-scheme:light')
      .replace(RE_RGB,(s,a,b,c)=>{const r=RGB[a+','+b+','+c];return r?'rgba('+r+',':s;})
      :doc.replace(RE_L,(_,h)=>'#'+LIGHT[h.toLowerCase()]);
    const j=out.search(/<\/head>/i); return j>0?out.slice(0,j)+CSS+out.slice(j):CSS+out;
  };

  /* ---- pestañas: cada iframe se crea y se carga la primera vez que se abre ---- */
  const stage=$('stage'), frames={};
  const frame=i=>{if(frames[i])return frames[i];const f=document.createElement('iframe');
    f.setAttribute('sandbox','allow-scripts allow-popups allow-same-origin allow-downloads allow-modals');
    f.setAttribute('allow','web-share; clipboard-write');
    stage.appendChild(f); frames[i]=f; $('loading').classList.add('on');
    f.addEventListener('load',()=>$('loading').classList.remove('on'),{once:true});
    setTimeout(()=>{f.srcdoc=tematiza(DOCS[i]);},20); return f;};
  let cur=null;
  const secDe=t=>vis.find(s=>s.items.includes(t));
  const drawSecs=()=>{$('secs').innerHTML=vis.map(s=>`<button class="sec${secDe(cur)===s?' on':''}" data-k="${s.k}">${s.n}<span class="c">${s.items.length}</span></button>`).join('');};
  const drawSub=()=>{const s=secDe(cur);$('sub').innerHTML=s.items.map(t=>`<button class="st${t===cur?' on':''}" data-i="${t.i}">${name(t)}</button>`).join('');
    const a=$('sub').querySelector('.on'); if(a) a.scrollIntoView({block:'nearest',inline:'nearest'});};
  const go=(i,push=true)=>{const t=tabs.find(x=>x.i===+i); if(!t) return; cur=t;
    tabs.forEach(x=>x.b.classList.toggle('active',x===t));
    const f=frame(t.i); Object.values(frames).forEach(g=>g.classList.toggle('active',g===f));
    drawSecs(); drawSub(); document.title=name(t)+' · Panel operativo MushDrink';
    try{localStorage.setItem('md-tab',t.l);}catch(e){}
    if(push) history.replaceState(null,'','#'+encodeURIComponent(t.l));};
  $('secs').onclick=e=>{const b=e.target.closest('.sec');if(!b)return;const s=vis.find(x=>x.k===b.dataset.k);
    let last=null;try{last=localStorage.getItem('md-sec-'+s.k);}catch(e){}
    const t=s.items.find(x=>x.l===last)||s.items[0]; go(t.i);};
  $('sub').onclick=e=>{const b=e.target.closest('.st');if(!b)return;go(b.dataset.i);try{localStorage.setItem('md-sec-'+secDe(cur).k,cur.l);}catch(e){}};
  // los botones ocultos siguen funcionando (p. ej. «Ver pestaña Festivos» del aviso)
  tabs.forEach(t=>t.b.addEventListener('click',()=>{if(cur!==t)go(t.i);}));

  /* ---- buscador (tecla /) ---- */
  const pal=$('pal'), q=$('palq'), list=$('pall'); let kb=0, shown=[];
  const drawPal=()=>{const f=q.value.trim().toLowerCase();
    shown=[]; let h='';
    vis.forEach(s=>{const its=s.items.filter(t=>!f||name(t).toLowerCase().includes(f)||t.l.toLowerCase().includes(f)||s.n.toLowerCase().includes(f));
      if(!its.length)return; h+=`<div class="pg">${s.n}</div>`;
      its.forEach(t=>{h+=`<button class="pi${t===cur?' act':''}${shown.length===kb?' kb':''}" data-i="${t.i}">${name(t)}</button>`;shown.push(t);});});
    list.innerHTML=h||'<div class="pv">Ninguna pestaña con ese nombre.</div>';};
  const openPal=()=>{q.value='';kb=0;drawPal();pal.classList.add('on');setTimeout(()=>q.focus(),0);};
  const closePal=()=>pal.classList.remove('on');
  $('find').onclick=openPal;
  pal.onclick=e=>{if(e.target===pal)closePal();const it=e.target.closest('.pi');if(it){go(it.dataset.i);closePal();}};
  q.oninput=()=>{kb=0;drawPal();};
  q.onkeydown=e=>{if(e.key==='ArrowDown'||e.key==='ArrowUp'){e.preventDefault();kb=Math.max(0,Math.min(shown.length-1,kb+(e.key==='ArrowDown'?1:-1)));drawPal();}
    else if(e.key==='Enter'){if(shown[kb]){go(shown[kb].i);closePal();}} else if(e.key==='Escape')closePal();};
  document.addEventListener('keydown',e=>{if(e.key==='/'&&!pal.classList.contains('on')&&!/INPUT|TEXTAREA|SELECT/.test(document.activeElement.tagName)){e.preventDefault();openPal();}});

  /* ---- pestaña inicial: la del enlace (#Nombre), la última abierta o «Resumen» ---- */
  const h=decodeURIComponent(location.hash.slice(1)); let last=null; try{last=localStorage.getItem('md-tab');}catch(e){}
  const ini=tabs.find(t=>t.l===h)||tabs.find(t=>t.l===last)||tabs.find(t=>t.l==='Resumen')||tabs[0];
  go(ini.i,false);
  window.addEventListener('hashchange',()=>{const t=tabs.find(x=>x.l===decodeURIComponent(location.hash.slice(1)));if(t&&t!==cur)go(t.i,false);});
}
