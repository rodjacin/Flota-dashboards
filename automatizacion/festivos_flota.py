# -*- coding: utf-8 -*-
"""
Aviso emergente de FESTIVOS en los dashboards de flota (SAB y GRA-MAD-NOM-ALC).

  python3 festivos_flota.py <index.html> <sab|gra-mad-nom-alc>

Inyecta antes de </body> un aviso que, con la fecha del navegador, muestra los festivos laborales
(nacionales, autonómicos y locales) de los próximos 7 días en los municipios de cada zona de reparto,
con el % de entregas de la zona que cae en cada municipio. Botón 🔔 junto al sello de la cabecera.

Datos: entradas/festivos_flota.json (zonas → municipios y festivos). Los municipios de cada zona salen
de cruzar los puntos de entrega (pp_heat.json) con los límites municipales del INE (es-atlas).
No existen festivos laborales provinciales ni comarcales en Andalucía, C. Valenciana ni Madrid:
solo nacionales, autonómicos y locales (2 por municipio).
"""
import os, sys, json
AUTO = os.path.dirname(os.path.abspath(__file__))
CFG = os.path.join(AUTO, "entradas", "festivos_flota.json")


def snippet(cfg, dash):
    zonas = {z: v for z, v in cfg["zonas"].items() if z in cfg["dashboards"][dash]}
    data = dict(zonas=zonas, hol=cfg["hol"], dias=7)
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    return """
<!-- festivos_flota -->
<style>
#ffpop{position:fixed;inset:0;background:rgba(20,23,31,.45);display:none;align-items:flex-start;justify-content:center;z-index:9999;padding:70px 14px;overflow:auto;font-family:-apple-system,Segoe UI,Roboto,sans-serif}
#ffpop.on{display:flex}
#ffpop .bx{background:#fff;border:1px solid #E4E7EC;border-top:4px solid #0E5A6B;border-radius:12px;max-width:720px;width:100%;box-shadow:0 20px 50px rgba(20,23,31,.25);color:#14171F}
#ffpop .hd{padding:14px 18px;border-bottom:1px solid #E4E7EC} #ffpop .hd b{font-size:16px} #ffpop .hd div{color:#6B7280;font-size:12.5px;margin-top:3px}
#ffpop .bd{padding:4px 18px 8px;max-height:62vh;overflow:auto}
#ffpop .it{border:1px solid #E4E7EC;border-radius:10px;padding:10px 12px;margin:10px 0}
#ffpop .t{display:flex;justify-content:space-between;gap:10px;flex-wrap:wrap;align-items:baseline} #ffpop .t b{font-size:14px}
#ffpop .tg{font-size:11px;border-radius:10px;padding:1px 8px;margin-left:6px;background:#E3F0F2;color:#0E5A6B;white-space:nowrap}
#ffpop .w{font-weight:700;font-size:12px;color:#B45309} #ffpop .w.h{color:#B91C1C}
#ffpop .z{font-size:12.5px;color:#374151;margin-top:6px;line-height:1.55} #ffpop .z b{color:#0E5A6B}
#ffpop .ft{padding:12px 18px;border-top:1px solid #E4E7EC;display:flex;gap:8px;justify-content:flex-end;flex-wrap:wrap}
#ffpop button,#ffbell{font:600 12.5px -apple-system,Segoe UI,Roboto,sans-serif;border-radius:8px;padding:7px 12px;cursor:pointer;border:1px solid #E4E7EC;background:#fff;color:#14171F}
#ffpop button.p{background:#0E5A6B;color:#fff;border-color:#0E5A6B}
#ffbell{margin-left:10px;border-color:#F59E0B;color:#B45309;background:#FFFBEB;white-space:nowrap}
</style>
<div id="ffpop" role="dialog" aria-modal="true"><div class="bx">
 <div class="hd"><b>⚠ Festivos en los próximos 7 días · zonas de reparto</b><div id="ffS"></div></div>
 <div class="bd" id="ffB"></div>
 <div class="ft"><button id="ffHoy">No volver a mostrar hoy</button><button class="p" id="ffOk">Entendido</button></div>
</div></div>
<script>
(function(){
const F=""" + payload + """;
const pad=n=>String(n).padStart(2,'0'),now=new Date(),t0=new Date(now.getFullYear(),now.getMonth(),now.getDate());
const today=t0.getFullYear()+'-'+pad(t0.getMonth()+1)+'-'+pad(t0.getDate());
const DW=['domingo','lunes','martes','miércoles','jueves','viernes','sábado'];
const esc=s=>String(s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const it=[];
for(const [d,tipo,nom,terr] of F.hol){
  const x=new Date(d+'T00:00:00'),dd=Math.round((x-t0)/864e5); if(dd<0||dd>F.dias)continue;
  const zs=[];
  for(const [z,Z] of Object.entries(F.zonas)){
    const T=[].concat(terr);const ms=Z.muni.filter(m=>T.includes(m[2])||T.includes(m[0]));
    if(ms.length) zs.push({z,nombre:Z.nombre,ms,pct:ms.reduce((a,m)=>a+m[1],0)});
  }
  if(zs.length) it.push({d,dd,x,tipo,nom,terr,zs});
}
if(!it.length)return;
const host=document.querySelector('header.top .stamp')||document.querySelector('header')||document.body;
const b=document.createElement('button');b.id='ffbell';b.type='button';
b.textContent='🔔 '+it.length+' festivo'+(it.length>1?'s':'')+' (7 días)';b.title='Festivos en los próximos 7 días en las zonas de reparto';
host.parentNode&&host!==document.body?host.parentNode.insertBefore(b,host.nextSibling):document.body.appendChild(b);
const zt=new Set(it.flatMap(i=>i.zs.map(z=>z.z)));
document.getElementById('ffS').textContent='Zonas afectadas: '+[...zt].sort().join(', ')+' · % = parte de las entregas de la zona en esos municipios';
document.getElementById('ffB').innerHTML=it.map(i=>{
  const w=i.dd===0?'HOY':i.dd===1?'MAÑANA':'en '+i.dd+' días';
  const amb=[].concat(i.terr).join(' · ');
  return `<div class="it"><div class="t"><div><b>${DW[i.x.getDay()]} ${pad(i.x.getDate())}/${pad(i.x.getMonth()+1)} · ${esc(i.nom)}</b><span class="tg">${i.tipo} · ${esc(amb)}</span></div><span class="w${i.dd<=1?' h':''}">${w}</span></div>`+
    i.zs.map(z=>`<div class="z"><b>${z.z}</b> (${esc(z.nombre)}) · <b>${Math.round(z.pct)}%</b> de las entregas: ${z.ms.map(m=>esc(m[0])+' '+Math.round(m[1])+'%').join(', ')}</div>`).join('')+'</div>';}).join('');
const pop=document.getElementById('ffpop'),K='ffpop-'+location.pathname+'-'+today;
const show=()=>pop.classList.add('on'),hide=()=>pop.classList.remove('on');
b.onclick=show;document.getElementById('ffOk').onclick=hide;
document.getElementById('ffHoy').onclick=()=>{try{localStorage.setItem(K,'1');}catch(e){}hide();};
pop.onclick=e=>{if(e.target===pop)hide();};document.addEventListener('keydown',e=>{if(e.key==='Escape')hide();});
let seen=null;try{seen=localStorage.getItem(K);}catch(e){}
if(!seen)setTimeout(show,700);
})();
</script>
<!-- /festivos_flota -->
"""


def main():
    html, dash = sys.argv[1], sys.argv[2]
    cfg = json.load(open(CFG, encoding="utf-8"))
    t = open(html, encoding="utf-8").read()
    i, j = t.find("<!-- festivos_flota -->"), t.find("<!-- /festivos_flota -->")
    if i >= 0 and j > i: t = t[:i] + t[j + len("<!-- /festivos_flota -->"):]
    k = t.rfind("</body>")
    if k < 0: raise SystemExit("no encuentro </body>")
    t = t[:k] + snippet(cfg, dash) + t[k:]
    open(html, "w", encoding="utf-8").write(t)
    print(f"festivos_flota: aviso añadido a {html} ({dash})")


if __name__ == "__main__":
    main()
