# -*- coding: utf-8 -*-
"""patch_delivery_race.py - convierte la vista Delivery Race en tendencia por rider x semana
con selector de metrica (WTD%, RR%, UTR, No Show, buckets de incidencia GCP y S&L).

Uso (aplicar a las PLANTILLAS para que sea permanente):
  python3 patch_delivery_race.py ~/Downloads/plantilla_resumen_SAB.html ~/Downloads/plantilla_resumen_GRA_MAD_NOM_ALC.html

Tambien sirve para HTML ya generados. Idempotente; deja copia .bak la primera vez.
"""
import sys, os

CSS = """<style id="liga-trend-css">
.metricsel{background:#161C24;color:#E9ECF1;border:1px solid #333F4D;border-radius:8px;padding:7px 10px;font-family:inherit;font-size:13px;cursor:pointer;min-width:210px}
.metricsel:focus{outline:none;border-color:#4FD1B4}
table.ligatbl.trend th,table.ligatbl.trend td{text-align:center;white-space:nowrap}
table.ligatbl.trend th.lft,table.ligatbl.trend td.lft{text-align:left}
table.ligatbl.trend td,table.ligatbl.trend th{display:table-cell}
table.ligatbl.trend td.trendwk{font-variant-numeric:tabular-nums;font-size:12px}
table.ligatbl.trend td.trendwk.last{box-shadow:inset 0 0 0 1px rgba(124,199,255,.55)}
.trend-delta{font-variant-numeric:tabular-nums;font-weight:650}
.trend-delta.up{color:#E5624D}.trend-delta.down{color:#3FB984}.trend-delta.flat{color:#8a94a3}
.sparkcell svg{display:block;margin:0 auto}
.liga-leg{display:flex;gap:16px;flex-wrap:wrap;align-items:center;font-size:11.5px;color:#98A3B3;margin:2px 0 10px}
.liga-leg .sw{display:inline-block;width:34px;height:10px;border-radius:3px;vertical-align:middle;margin-right:5px;background:linear-gradient(90deg,rgba(46,158,123,.6),rgba(224,169,74,.6),rgba(229,98,77,.6))}
</style>"""


NEW_JS = r"""<script>
/* ==== Delivery Race · Tendencia por rider y semana (multi-metrica) ==== */
(function(){
  const host=document.getElementById('viewLiga');
  if(!host) return;
  const D    = (typeof DATA!=='undefined'       && Array.isArray(DATA))       ? DATA       : [];
  const WORD = (typeof WEEK_ORDER!=='undefined' && Array.isArray(WEEK_ORDER)) ? WEEK_ORDER : [...new Set(D.map(d=>d.week).filter(Boolean))];
  const WLBL = (typeof WEEK_LABEL!=='undefined' && WEEK_LABEL)                 ? WEEK_LABEL : {};

  // Target 1 por ciudad (WTD>10' % y RR %) en fraccion
  const TARGETS = {
    ALC:{wtd10:0.0270, reassign:0.0229}, GRA:{wtd10:0.0228, reassign:0.0390},
    NOM:{wtd10:0.0405, reassign:0.0390}, SAB:{wtd10:0.0225, reassign:0.0540},
    MAD:{wtd10:0.0315, reassign:0.0351},
  };

  // catalogo de metricas: kind pct|num2|int ; worse up|down ; target opcional
  const METRICS = {
    wtd10:   {label:"WTD>10' %",      kind:'pct',  worse:'up',   target:'wtd10'},
    reassign:{label:"RR % (reasign.)",kind:'pct',  worse:'up',   target:'reassign'},
    utr:     {label:"UTR (entr/h)",   kind:'num2', worse:'down'},
    _noshows:{label:"No Show %",      kind:'pct',  worse:'up'},
    notSeen: {label:"No visto %",     kind:'pct',  worse:'up'},
    ignored: {label:"Ignorado %",     kind:'pct',  worse:'up'},
    decline: {label:"Rechazo %",      kind:'pct',  worse:'up'},
    redispatch:{label:"Redispatch %", kind:'pct',  worse:'up'},
    cnm:     {label:"CNM %",          kind:'pct',  worse:'up'},
    agent:   {label:"Agente %",       kind:'pct',  worse:'up'},
    slCapu:  {label:"CAPU (n)",       kind:'int',  worse:'up'},
    slUndel: {label:"No entregado (n)",kind:'int', worse:'up'},
    slAbsent:{label:"Ausente (n)",    kind:'int',  worse:'up'},
  };
  const GROUPS = [
    ["Metrica clave", ["wtd10","reassign","utr","_noshows"]],
    ["Tipo de incidencia · GCP (reasignacion)", ["notSeen","ignored","decline","redispatch","cnm","agent"]],
    ["Tipo de incidencia · S&L", ["slCapu","slUndel","slAbsent"]],
  ];

  const st={area:'ALL', q:'', metric:'wtd10', sort:'last', dir:'desc'};
  const areasL=[...new Set(D.map(d=>d.city).filter(Boolean))].sort();

  const dispVal=(m,v)=>{ if(v==null||Number.isNaN(v)) return '<span class="dim">–</span>'; const M=METRICS[m];
    if(M.kind==='pct')  return (v*100).toLocaleString('es-ES',{minimumFractionDigits:1,maximumFractionDigits:1})+'%';
    if(M.kind==='num2') return v.toLocaleString('es-ES',{minimumFractionDigits:2,maximumFractionDigits:2});
    return Math.round(v).toLocaleString('es-ES'); };
  const dispDelta=(m,d)=>{ if(d==null) return '<span class="dim">–</span>'; const M=METRICS[m];
    const worse = M.worse==='down' ? (d<0) : (d>0);
    const cls = Math.abs(d)<1e-9 ? 'flat' : (worse?'up':'down');
    const arr = Math.abs(d)<1e-9 ? '–' : (d>0?'▲':'▼');
    let txt; if(M.kind==='pct') txt=(Math.abs(d)*100).toLocaleString('es-ES',{minimumFractionDigits:1,maximumFractionDigits:1})+' pp';
    else if(M.kind==='num2') txt=Math.abs(d).toLocaleString('es-ES',{minimumFractionDigits:2,maximumFractionDigits:2});
    else txt=Math.round(Math.abs(d)).toLocaleString('es-ES');
    return '<span class="trend-delta '+cls+'">'+arr+' '+txt+'</span>'; };

  function pivot(){
    const g={};
    for(const r of D){
      if(st.area!=='ALL' && r.city!==st.area) continue;
      let o=g[r.rider]; if(!o){ o=g[r.rider]={rider:r.rider, city:r.city, vals:{}}; }
      o.city=r.city; const v=r[st.metric];
      if(v!=null && !Number.isNaN(+v)) o.vals[r.week]=+v;
    }
    let out=Object.values(g).map(o=>{
      const arr=WORD.map(w=> (w in o.vals)? o.vals[w] : null);
      const pres=arr.filter(x=>x!=null);
      const last=pres.length?pres[pres.length-1]:null, first=pres.length?pres[0]:null;
      const delta=(last!=null&&first!=null)?(last-first):null;
      const mean=pres.length?pres.reduce((s,x)=>s+x,0)/pres.length:null;
      return {rider:o.rider, city:o.city, arr, last, first, delta, mean, n:pres.length};
    });
    const q=st.q.trim(); if(q) out=out.filter(r=>String(r.rider).includes(q));
    return out;
  }

  function scaleOf(rows){ let mn=Infinity,mx=-Infinity;
    rows.forEach(r=>r.arr.forEach(v=>{ if(v!=null){ if(v<mn)mn=v; if(v>mx)mx=v; }}));
    if(mn===Infinity){mn=0;mx=1;} if(mn===mx){mx=mn+ (mn===0?1:Math.abs(mn)*.1);} return [mn,mx]; }
  function heat(t){ t=Math.max(0,Math.min(1,t));
    const stops=[[0,[46,158,123]],[0.5,[224,169,74]],[1,[229,98,77]]];
    let a=stops[0],b=stops[2];
    for(let i=0;i<stops.length-1;i++){ if(t>=stops[i][0]&&t<=stops[i+1][0]){a=stops[i];b=stops[i+1];break;} }
    const f=(t-a[0])/((b[0]-a[0])||1); const c=a[1].map((x,k)=>Math.round(x+(b[1][k]-x)*f));
    return 'rgba('+c[0]+','+c[1]+','+c[2]+',0.24)'; }
  function cellStyle(v,mn,mx){ if(v==null) return ''; let t=(v-mn)/(mx-mn||1);
    if(METRICS[st.metric].worse==='down') t=1-t; return 'background:'+heat(t); }
  function spark(arr,mn,mx){ const W=66,H=20,pad=3; const pts=[]; const n=arr.length;
    arr.forEach((v,i)=>{ if(v==null)return; const x=pad+(W-2*pad)*(n<=1?.5:i/(n-1));
      let t=(v-mn)/(mx-mn||1); const y=pad+(H-2*pad)*(1-t); pts.push([x,y]); });
    if(!pts.length) return '<span class="dim">–</span>';
    const lp=pts[pts.length-1];
    return '<svg width="'+W+'" height="'+H+'" viewBox="0 0 '+W+' '+H+'">'+
      '<polyline points="'+pts.map(p=>p[0].toFixed(1)+','+p[1].toFixed(1)).join(' ')+'" fill="none" stroke="#7CC7FF" stroke-width="1.6" stroke-linejoin="round" stroke-linecap="round"/>'+
      '<circle cx="'+lp[0].toFixed(1)+'" cy="'+lp[1].toFixed(1)+'" r="2" fill="#7CC7FF"/></svg>'; }

  function sortRows(rows){
    const {sort,dir}=st, sign=dir==='asc'?1:-1;
    const wkIdx = sort.indexOf('w:')===0 ? WORD.indexOf(sort.slice(2)) : -1;
    return rows.slice().sort((a,b)=>{
      if(sort==='rider') return (+a.rider-+b.rider)*sign;
      if(sort==='city')  return (String(a.city).localeCompare(String(b.city))*sign)||(+a.rider-+b.rider);
      let x,y;
      if(wkIdx>=0){ x=a.arr[wkIdx]; y=b.arr[wkIdx]; }
      else { x=a[sort]; y=b[sort]; }
      if(x==null&&y==null) return 0; if(x==null) return 1; if(y==null) return -1;
      if(x===y) return (+a.rider-+b.rider);
      return (x-y)*sign;
    });
  }

  // selector de metrica
  const sel=document.getElementById('ligaMetricSel');
  if(sel){
    sel.innerHTML=GROUPS.map(([g,ks])=>'<optgroup label="'+g+'">'+
      ks.map(k=>'<option value="'+k+'"'+(k===st.metric?' selected':'')+'>'+METRICS[k].label+'</option>').join('')+
      '</optgroup>').join('');
    sel.addEventListener('change',e=>{ st.metric=e.target.value;
      st.sort='last'; st.dir=(METRICS[st.metric].worse==='down')?'asc':'desc'; render(); });
  }

  function render(){
    if(typeof buildSeg==='function'){
      buildSeg(document.getElementById('ligaAreaSeg'),
        areasL.map(a=>[a,a, D.filter(d=>d.city===a).length]), st.area, v=>{st.area=v; render();});
    }
    const rows=pivot();
    const [mn,mx]=scaleOf(rows);
    const M=METRICS[st.metric];

    // cabecera
    const cols=[{k:'rank',h:'#',lft:true,s:false},{k:'rider',h:'Rider ID',lft:true,s:true},{k:'city',h:'Área',lft:true,s:true}]
      .concat(WORD.map(w=>({k:'w:'+w, h:(WLBL[w]||w), s:true})))
      .concat([{k:'spark',h:'Tendencia',s:false},{k:'last',h:'Última',s:true},{k:'delta',h:'Δ (últ−prim)',s:true}]);
    const head=document.getElementById('ligaHead');
    head.innerHTML=cols.map(c=>{ const ar=c.s?(st.sort===c.k?(st.dir==='asc'?'▲':'▼'):'↕'):'';
      return '<th class="'+(c.lft?'lft':'')+(c.s?' sortable':'')+'" data-k="'+c.k+'">'+c.h+(ar?' <span class="ar2">'+ar+'</span>':'')+'</th>'; }).join('');
    head.querySelectorAll('th.sortable').forEach(th=>{ th.style.cursor='pointer';
      th.onclick=()=>{ const k=th.dataset.k;
        if(st.sort===k){ st.dir=st.dir==='asc'?'desc':'asc'; }
        else { st.sort=k; st.dir=(k==='rider'||k==='city')?'asc':(M.worse==='down'?'asc':'desc'); }
        render(); }; });

    const srt=sortRows(rows);
    const body=document.getElementById('ligaBody');
    if(!srt.length){ body.innerHTML='<tr><td colspan="'+cols.length+'"><div class="empty"><b>Sin datos</b>No hay riders para este filtro.</div></td></tr>'; }
    else {
      const lastIdx=(function(){ for(let i=WORD.length-1;i>=0;i--){ if(srt.some(r=>r.arr[i]!=null)) return i; } return WORD.length-1; })();
      body.innerHTML=srt.map((r,i)=>{
        const cells=r.arr.map((v,wi)=>'<td class="trendwk'+(wi===lastIdx?' last':'')+'" style="'+cellStyle(v,mn,mx)+'">'+dispVal(st.metric,v)+'</td>').join('');
        return '<tr>'+
          '<td class="lft rankcell">'+(i+1)+'</td>'+
          '<td class="lft rider">'+r.rider+'</td>'+
          '<td class="lft"><span class="pill">'+r.city+'</span></td>'+
          cells+
          '<td class="sparkcell">'+spark(r.arr,mn,mx)+'</td>'+
          '<td>'+dispVal(st.metric,r.last)+'</td>'+
          '<td>'+dispDelta(st.metric,r.delta)+'</td>'+
        '</tr>'; }).join('');
    }
    document.getElementById('ligaFoot').textContent=srt.length+' riders · '+(st.area==='ALL'?'todas las áreas':st.area)+' · '+M.label+' por semana';
    const note=document.getElementById('ligaNote');
    if(note){ let t='';
      if(M.target){ const tg=(st.area!=='ALL'&&TARGETS[st.area])?TARGETS[st.area][M.target]:null;
        t = tg!=null ? ' · Objetivo T1 '+st.area+': '+(tg*100).toLocaleString('es-ES',{minimumFractionDigits:2,maximumFractionDigits:2})+'%' : ' · con Objetivo T1 por área'; }
      note.innerHTML='<span class="liga-leg"><span><span class="sw"></span>Color: verde = mejor → rojo = peor (según la métrica)</span>'+
        '<span>▲/▼ Δ = última vs primera semana ('+(M.worse==='down'?'▲ sube = mejora':'▼ baja = mejora')+')</span></span>'+
        '<b>'+M.label+'</b> por rider y semana ('+WORD[0]+'–'+WORD[WORD.length-1]+')'+t+'.'; }
  }

  window.__renderLiga=render;
  render();

  const sb=document.getElementById('ligaSearch');
  if(sb) sb.addEventListener('input',e=>{ st.q=e.target.value; render(); });
  const btn=document.getElementById('ligaCsvBtn');
  if(btn) btn.onclick=()=>{
    const rows=sortRows(pivot());
    const H=['Rider','Area'].concat(WORD).concat(['Ultima','Delta']);
    const val=v=> v==null?'':(METRICS[st.metric].kind==='pct'?(v*100).toFixed(2):(METRICS[st.metric].kind==='num2'?v.toFixed(2):Math.round(v)));
    const lines=[H.join(',')];
    rows.forEach(r=>lines.push([r.rider,r.city].concat(r.arr.map(val)).concat([val(r.last), r.delta==null?'':val(r.delta)]).join(',')));
    const blob=new Blob([lines.join('\n')],{type:'text/csv;charset=utf-8'});
    const a=document.createElement('a'); a.href=URL.createObjectURL(blob);
    a.download='delivery_race_trend_'+st.metric+'.csv'; a.click(); URL.revokeObjectURL(a.href);
  };
})();
</script>"""


def patch(html):
    # 1) inyectar CSS antes de </head>
    if 'liga-trend-css' not in html:
        html=html.replace('</head>', CSS+'\n</head>', 1)
    # 2) cabecera + sub
    html=html.replace(
      '<h1 style="font-size:17px">Delivery Race · Score de performance</h1>\n        <div class="sub">Media de todas las semanas en WTD&gt;10&#8242; %, RR % y No Show % · Score sobre 100</div>',
      '<h1 style="font-size:17px">Delivery Race · Tendencia por rider</h1>\n        <div class="sub">Performance por rider y semana para ver tendencias · elige la métrica clave o el tipo de incidencia (GCP)</div>',1)
    # 3) anadir campo Metrica tras Area
    html=html.replace(
      '<span class="lbl">Área</span>\n        <div class="seg" id="ligaAreaSeg"></div>\n      </div>',
      '<span class="lbl">Área</span>\n        <div class="seg" id="ligaAreaSeg"></div>\n      </div>\n      <div class="field">\n        <span class="lbl">Métrica</span>\n        <select id="ligaMetricSel" class="metricsel"></select>\n      </div>',1)
    # 4) ensanchar tabla + clase trend
    html=html.replace('<table class="ligatbl" style="min-width:900px">',
                      '<table class="ligatbl trend" style="min-width:1180px">',1)
    # 5) reemplazar el IIFE del liga (anclaje unico: el IIFE usa viewLiga)
    anchor=html.find("const host=document.getElementById('viewLiga')")
    if anchor==-1: raise SystemExit('no encuentro el IIFE del liga')
    s=html.rfind('<script>', 0, anchor)
    e=html.index('</script>', anchor)+len('</script>')
    if not (0<=s<anchor<e): raise SystemExit('límites del script incorrectos')
    html=html[:s]+NEW_JS+html[e:]
    return html


def main(argv):
    files = argv[1:]
    if not files:
        print("Uso: python3 patch_delivery_race.py <archivo.html> [<archivo2.html> ...]"); return 1
    for f in files:
        if not os.path.isfile(f):
            print("  !! no existe:", f); continue
        html=open(f,encoding="utf-8").read()
        if "liga-trend-css" in html and "Tendencia por rider y semana (multi-metrica)" in html:
            print("  = ya parcheado:", f); continue
        try:
            out=patch(html)
        except SystemExit as e:
            print("  !! no pude parchear", f, "->", e); continue
        if not os.path.exists(f+".bak"):
            open(f+".bak","w",encoding="utf-8").write(html)
        open(f,"w",encoding="utf-8").write(out)
        print("  OK parcheado:", f)
    return 0

if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
