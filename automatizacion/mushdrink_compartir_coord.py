#!/usr/bin/env python3
"""
MushDrink · Resumen › «Pedidos por repartidor · coordinadores (resumen)»: botón «Compartir».

Genera, para cada coordinador, una imagen PNG de la tabla tal y como se ve (mismo periodo, filtros y orden) en la
que solo aparece su nombre; los nombres del resto de coordinadores se ocultan, pero sus cifras se mantienen para
que cada uno vea su posición. Desde la ventana se puede compartir (WhatsApp, etc. con el menú del sistema),
copiar o descargar cada imagen, o descargarlas todas.

Idempotente:  python3 automatizacion/mushdrink_compartir_coord.py [mushdrink/index.html]
"""
import json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
MARCA = '/*__COMPARTIR_COORD__*/'
BTN_ANCLA = '<button class="btn sm" data-csv="oT2">⤓ CSV</button>'
BTN = '<button class="btn sm" id="o2Share" title="Imagen de la tabla para cada coordinador, sin los nombres del resto">⇪ Compartir</button>'

CSS = """
  #shOv{position:fixed;inset:0;background:rgba(0,0,0,.45);display:none;align-items:flex-start;justify-content:center;padding:28px 14px;z-index:9999;overflow:auto}
  #shOv.on{display:flex}
  #shOv .bx{background:var(--panel);border:1px solid var(--line);border-radius:14px;width:min(1180px,100%);box-shadow:0 20px 60px rgba(0,0,0,.25)}
  #shOv .hd{display:flex;align-items:center;gap:10px;padding:12px 16px;border-bottom:1px solid var(--line)}
  #shOv .hd b{font-size:14px} #shOv .hd span{color:var(--muted);font-size:12px} #shOv .hd .grow{flex:1}
  #shOv .gr{display:grid;grid-template-columns:repeat(auto-fill,minmax(340px,1fr));gap:12px;padding:14px 16px}
  #shOv .it{border:1px solid var(--line);border-radius:10px;padding:10px;background:var(--panel2)}
  #shOv .it .tt{display:flex;align-items:center;gap:8px;margin-bottom:8px;font-weight:600;font-size:13px}
  #shOv .it .tt .rk{color:var(--muted);font-weight:500;font-size:12px}
  #shOv .it img{width:100%;display:block;border-radius:6px;border:1px solid var(--line);background:#fff;cursor:zoom-in}
  #shOv .it .ac{display:flex;gap:6px;margin-top:8px;flex-wrap:wrap}
  #shOv .msg{font-size:11.5px;color:var(--muted);padding:0 16px 12px}
"""

JS = MARCA + r"""
(function(){
  const $s=id=>document.getElementById(id);
  const FONT='Inter,-apple-system,"Segoe UI",Roboto,Helvetica,Arial,sans-serif';
  const K={ink:'#16302C',mut:'#5E7471',line:'#DCE9E6',head:'#F4F9F8',aqua:'#14A394',aquaD:'#0B6F66',aquaL:'#E3F5F2',orange:'#F28C28',good:'#1F8A5C',bad:'#C2402B'};
  const txt=el=>el.textContent.replace(/\s+/g,' ').trim();
  const tono=td=>{const s=td.querySelector('.good,.bad,.muted');return s?(s.classList.contains('good')?K.good:s.classList.contains('bad')?K.bad:K.mut):K.ink;};
  function leeTabla(){
    const T=$s('oT2'); if(!T||!T.tHead) return null;
    const head=[...T.tHead.rows[0].cells].map(th=>txt(th).replace(/[▲▼]$/,'').trim());
    const ci=head.findIndex(h=>/coordinador/i.test(h));
    const rows=[...T.tBodies[0].rows].filter(tr=>tr.cells.length===head.length).map(tr=>[...tr.cells].map(td=>({t:txt(td),c:tono(td),b:!!td.querySelector('b')})));
    return {head,ci,rows,periodo:($s('o2Badge')||{}).textContent||''};
  }
  function dibuja(D,yo){
    const S=2, pad=22, rowH=34, headH=34, titleH=70, footH=34;
    const cv=document.createElement('canvas'), g=cv.getContext('2d');
    const fnt=(w,s)=>`${w} ${s}px ${FONT}`;
    // anchos de columna
    g.font=fnt(600,12); const wH=D.head.map(h=>g.measureText(h.toUpperCase()).width);
    const wC=D.head.map((_,j)=>Math.max(...D.rows.map(r=>{g.font=fnt(r[j].b?700:500,14);return g.measureText(j===D.ci?'Coordinador oculto':r[j].t).width;})));
    const W=D.head.map((_,j)=>Math.max(wH[j],wC[j])+(j===D.ci?60:34));
    const tw=W.reduce((a,b)=>a+b,0), cw=tw+pad*2, ch=titleH+headH+rowH*D.rows.length+footH+pad;
    cv.width=cw*S; cv.height=ch*S; g.scale(S,S);
    g.fillStyle='#fff'; g.fillRect(0,0,cw,ch);
    g.fillStyle=K.aqua; g.fillRect(0,0,cw,5); g.fillStyle=K.orange; g.fillRect(cw-90,0,90,5);
    g.fillStyle=K.ink; g.font=fnt(700,17); g.textBaseline='alphabetic';
    g.fillText('Pedidos por repartidor · coordinadores',pad,34);
    g.fillStyle=K.mut; g.font=fnt(500,12.5); g.fillText(D.periodo+'   ·   Ranking para '+yo,pad,56);
    let y=titleH;
    g.fillStyle=K.head; g.fillRect(pad,y,tw,headH); g.strokeStyle=K.line; g.lineWidth=1; g.strokeRect(pad+.5,y+.5,tw-1,headH+rowH*D.rows.length-1);
    let x=pad; g.font=fnt(600,11.5); g.fillStyle=K.mut; g.textBaseline='middle';
    D.head.forEach((h,j)=>{const l=j<=D.ci; g.textAlign=l?'left':'right'; g.fillText(h.toUpperCase(),l?x+12:x+W[j]-12,y+headH/2); x+=W[j];});
    y+=headH;
    D.rows.forEach((r,i)=>{
      const mio=r[D.ci].t===yo;
      if(mio){g.fillStyle=K.aquaL; g.fillRect(pad+1,y,tw-2,rowH); g.fillStyle=K.aqua; g.fillRect(pad+1,y,4,rowH);}
      g.strokeStyle=K.line; g.beginPath(); g.moveTo(pad,y+.5); g.lineTo(pad+tw,y+.5); g.stroke();
      let x=pad;
      r.forEach((c,j)=>{
        const l=j<=D.ci; g.textAlign=l?'left':'right'; const xx=l?x+12:x+W[j]-12;
        if(j===D.ci&&!mio){ // nombre oculto
          g.fillStyle='#E3ECEA'; const bw=Math.min(W[j]-40,96); g.beginPath(); g.roundRect?g.roundRect(x+12,y+rowH/2-7,bw,14,7):g.rect(x+12,y+rowH/2-7,bw,14); g.fill();
        } else {
          g.font=fnt(mio&&j===D.ci?700:(c.b?700:500),14); g.fillStyle=mio&&j===D.ci?K.aquaD:c.c; g.fillText(c.t,xx,y+rowH/2+1);
        }
        x+=W[j];
      });
      y+=rowH;
    });
    g.textAlign='left'; g.fillStyle=K.mut; g.font=fnt(500,11); g.textBaseline='alphabetic';
    g.fillText('Panel operativo MushDrink · Kometa Delivery · solo se muestra tu nombre',pad,ch-pad+4);
    return cv;
  }
  const blobDe=cv=>new Promise(r=>cv.toBlob(r,'image/png'));
  const nombreF=(yo,D)=>('Ranking coordinadores '+(D.periodo||'').split(' vs ')[0]+' - '+yo).replace(/[\\/:*?"<>|]+/g,'-').replace(/\s+/g,' ').trim()+'.png';
  function descarga(blob,nombre){const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download=nombre;document.body.appendChild(a);a.click();setTimeout(()=>{URL.revokeObjectURL(a.href);a.remove();},800);}
  const aviso=t=>{const m=$s('shMsg');if(m)m.textContent=t;};
  async function comparte(blob,nombre,yo){
    const f=new File([blob],nombre,{type:'image/png'});
    try{ if(navigator.canShare&&navigator.canShare({files:[f]})){ await navigator.share({files:[f],title:'Ranking coordinadores',text:'Ranking de coordinadores · '+yo}); return; } }
    catch(e){ if(e&&e.name==='AbortError') return; }
    try{ await navigator.clipboard.write([new ClipboardItem({'image/png':blob})]); aviso('Este navegador no permite compartir directamente: imagen de '+yo+' copiada al portapapeles (pégala en WhatsApp) y descargada.'); }catch(e){ aviso('Imagen de '+yo+' descargada: adjúntala en WhatsApp.'); }
    descarga(blob,nombre);
  }
  function abre(){
    const D=leeTabla(); if(!D||D.ci<0||!D.rows.length){alert('No hay datos en la tabla para compartir.');return;}
    let ov=$s('shOv');
    if(!ov){ov=document.createElement('div');ov.id='shOv';document.body.appendChild(ov);
      ov.addEventListener('click',e=>{if(e.target===ov||e.target.id==='shX')ov.classList.remove('on');});
      document.addEventListener('keydown',e=>{if(e.key==='Escape')ov.classList.remove('on');});}
    const yos=D.rows.map(r=>r[D.ci].t).filter(Boolean);
    ov.innerHTML=`<div class="bx"><div class="hd"><b>Compartir ranking por coordinador</b><span>${D.periodo} · cada imagen solo muestra el nombre de su coordinador</span><span class="grow"></span><button class="btn sm" id="shAll">⤓ Descargar todas</button><button class="btn sm" id="shX">Cerrar</button></div>
      <div class="msg" id="shMsg">«Compartir» abre el menú del móvil/ordenador (WhatsApp, correo…). Si el navegador no lo permite, la imagen se copia y se descarga.</div><div class="gr" id="shGr"></div></div>`;
    const GR=$s('shGr'), B={};
    yos.forEach((yo,i)=>{
      const cv=dibuja(D,yo), url=cv.toDataURL('image/png'), rk=D.rows[i][0].t;
      const it=document.createElement('div'); it.className='it';
      it.innerHTML=`<div class="tt">${yo.replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]))}<span class="rk">${rk}</span></div><img alt="" src="${url}"><div class="ac"><button class="btn sm pri" data-a="sh">⇪ Compartir</button><button class="btn sm" data-a="cp">Copiar</button><button class="btn sm" data-a="dl">⤓ Descargar</button></div>`;
      GR.appendChild(it);
      const get=async()=>B[yo]||(B[yo]=await blobDe(cv));
      it.querySelector('img').onclick=()=>window.open(url,'_blank');
      it.querySelector('[data-a="sh"]').onclick=async()=>comparte(await get(),nombreF(yo,D),yo);
      it.querySelector('[data-a="dl"]').onclick=async()=>descarga(await get(),nombreF(yo,D));
      it.querySelector('[data-a="cp"]').onclick=async()=>{try{await navigator.clipboard.write([new ClipboardItem({'image/png':await get()})]);aviso('Imagen de '+yo+' copiada: pégala en WhatsApp.');}catch(e){aviso('No se ha podido copiar; usa Descargar.');}};
    });
    $s('shAll').onclick=async()=>{for(const yo of yos){descarga(B[yo]||(B[yo]=await blobDe(dibuja(D,yo))),nombreF(yo,D));await new Promise(r=>setTimeout(r,350));}};
    ov.classList.add('on');
  }
  const b=$s('o2Share'); if(b) b.onclick=abre;
})();
"""


def main():
    p = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, '..', 'mushdrink', 'index.html')
    h = open(p, encoding='utf-8').read()
    i0 = h.index('const DOCS=') + len('const DOCS=')
    docs, e0 = json.JSONDecoder().raw_decode(h[i0:])
    k = next(i for i, d in enumerate(docs) if 'id="sCoord2"' in d)
    d = docs[k]
    if MARCA in d:
        print('mushdrink_compartir_coord: ya estaba aplicado'); return
    assert d.count(BTN_ANCLA) == 1, 'ancla del botón CSV no encontrada'
    d = d.replace(BTN_ANCLA, BTN + BTN_ANCLA)
    d = d.replace('</style>', CSS + '</style>', 1)
    j = d.rindex('</body>')
    d = d[:j] + '<script>\n' + JS + '\n</script>\n' + d[j:]
    docs[k] = d
    body = "[" + ",\n".join(json.dumps(x, ensure_ascii=False).replace("</", "<\\/") for x in docs) + "]"
    open(p, 'w', encoding='utf-8').write(h[:i0] + body + h[i0 + e0:])
    print(f'mushdrink_compartir_coord: botón Compartir añadido en la pestaña {k}')


if __name__ == '__main__':
    main()
