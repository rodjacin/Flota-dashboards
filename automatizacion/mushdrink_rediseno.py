#!/usr/bin/env python3
"""
MushDrink · rediseño del panel con los colores de Kometa (verde agua, naranja y blanco),
pestañas agrupadas por secciones y nueva pestaña «Evolución del negocio».

  python3 automatizacion/mushdrink_rediseno.py                 # aplica sobre mushdrink/index.html (idempotente)
  python3 automatizacion/mushdrink_rediseno.py --preview DIR   # genera una vista previa en DIR que lee los
                                                               # datos en vivo de ../index.html (no toca el panel)

No cambia los datos: mushdrink_dia.py y el resto de scripts siguen parcheando DOCS por índice y añadiendo
pestañas en <div class="tabs">. La pestaña «Evolución del negocio» calcula todo en el navegador a partir de
la pestaña «Operativa restaurantes», así que se actualiza sola con cada día que se añade.
"""
import argparse, json, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
# Las plantillas con datos de negocio (p. ej. Evolución del negocio) viven en el repo PRIVADO
# rodjacin/mushdrink-datos, carpeta plantillas/ (junto a mushdrink/, que aquí es un enlace a ese repo).
PRIVADAS = os.path.join(os.path.dirname(os.path.realpath(os.path.join(HERE, '..', 'mushdrink'))), 'plantillas')


def plantilla(nombre):
    for d in (PRIVADAS, HERE):
        f = os.path.join(d, nombre)
        if os.path.exists(f):
            return open(f, encoding='utf-8').read()
    sys.exit(f'No encuentro {nombre}: ¿está enlazado mushdrink/ con el repo privado mushdrink-datos?')
MARCA_EVO = '<!-- EVOLUCION_NEGOCIO -->'
TAB_EVO = 'Evolución del negocio'
MARCA_SHELL = '<!-- KOMETA_SHELL -->'

CSS = r"""
  :root{--aqua:#14A394;--aqua-d:#0B6F66;--aqua-l:#E3F5F2;--orange:#F28C28;--orange-d:#B85A07;--bg:#F4F9F8;--line:#DCE9E6;--ink:#16302C;--mut:#5E7471;}
  *{box-sizing:border-box} html,body{margin:0;height:100%}
  body{background:var(--bg);color:var(--ink);font-family:Inter,-apple-system,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;display:flex;flex-direction:column;height:100vh;-webkit-font-smoothing:antialiased}
  .tabs{display:none}
  .topbar{display:flex;align-items:center;gap:12px;background:#fff;padding:0 14px;height:50px;flex:0 0 auto;border-bottom:1px solid var(--line)}
  .brand{display:flex;align-items:center;gap:9px;white-space:nowrap;margin-right:4px}
  .brand .klogo{width:32px;height:32px;display:block;flex:0 0 auto}
  .brand .sep{width:1px;height:22px;background:var(--line);margin:0 2px}
  .brand b{font-size:14.5px;letter-spacing:-.1px} .brand span{color:var(--mut);font-size:12.5px;font-weight:500}
  .secs{display:flex;gap:4px;overflow-x:auto;scrollbar-width:none;min-width:0}
  .secs::-webkit-scrollbar{display:none}
  .sec{display:flex;align-items:center;gap:7px;background:transparent;border:0;color:var(--mut);font:inherit;font-size:13px;font-weight:600;padding:7px 12px;border-radius:9px;cursor:pointer;white-space:nowrap}
  .sec:hover{background:var(--aqua-l);color:var(--aqua-d)}
  .sec.on{background:var(--aqua);color:#fff}
  .sec .c{font-size:10.5px;font-weight:700;background:rgba(20,163,148,.12);color:var(--aqua-d);border-radius:999px;padding:1px 6px}
  .sec.on .c{background:rgba(255,255,255,.25);color:#fff}
  #find{margin-left:auto;display:flex;align-items:center;gap:8px;background:var(--bg);border:1px solid var(--line);color:var(--mut);font:inherit;font-size:12.5px;padding:6px 10px;border-radius:9px;cursor:pointer;white-space:nowrap}
  #find:hover{border-color:var(--aqua);color:var(--aqua-d)} #find kbd{font:600 11px ui-monospace,Menlo,monospace;background:#fff;border:1px solid var(--line);border-radius:5px;padding:0 5px}
  .updated{color:var(--mut);font-size:11.5px;font-family:ui-monospace,Menlo,Consolas,monospace;white-space:nowrap}
  .subbar{display:flex;align-items:stretch;background:#fff;border-bottom:1px solid var(--line);padding:0 10px;height:38px;flex:0 0 auto;overflow-x:auto;scrollbar-width:none;box-shadow:0 1px 0 rgba(22,48,44,.03)}
  .subbar::-webkit-scrollbar{display:none}
  .st{position:relative;background:transparent;border:0;color:var(--mut);font:inherit;font-size:13px;font-weight:600;padding:0 12px;cursor:pointer;white-space:nowrap}
  .st:hover{color:var(--ink)}
  .st.on{color:var(--aqua-d)}
  .st.on:after{content:"";position:absolute;left:10px;right:10px;bottom:0;height:3px;border-radius:3px 3px 0 0;background:var(--orange)}
  .stage{position:relative;flex:1 1 auto;min-height:0;background:var(--bg)}
  iframe{position:absolute;inset:0;width:100%;height:100%;border:0;background:var(--bg);display:none}
  iframe.active{display:block}
  #loading{position:absolute;left:0;right:0;top:0;height:3px;background:linear-gradient(90deg,var(--aqua),var(--orange),var(--aqua));background-size:200% 100%;animation:mdl 1.1s linear infinite;opacity:0;transition:opacity .2s;z-index:5;pointer-events:none}
  #loading.on{opacity:1} @keyframes mdl{to{background-position:-200% 0}}
  #pal{position:fixed;inset:0;background:rgba(16,52,48,.28);display:none;align-items:flex-start;justify-content:center;padding:70px 14px;z-index:1000}
  #pal.on{display:flex}
  #pal .bx{background:#fff;border-radius:14px;width:min(560px,100%);box-shadow:0 24px 60px rgba(16,52,48,.25);overflow:hidden}
  #palq{width:100%;border:0;border-bottom:1px solid var(--line);padding:14px 16px;font:inherit;font-size:14px;outline:none;color:var(--ink)}
  #pall{max-height:60vh;overflow:auto;padding:6px}
  #pall .pg{font-size:11px;font-weight:700;color:var(--mut);text-transform:uppercase;letter-spacing:.5px;padding:10px 10px 4px}
  #pall .pi{display:block;width:100%;text-align:left;background:transparent;border:0;font:inherit;font-size:13.5px;color:var(--ink);padding:8px 10px;border-radius:8px;cursor:pointer}
  #pall .pi:hover,#pall .pi.kb{background:var(--aqua-l)} #pall .pi.act{color:var(--aqua-d);font-weight:700}
  #pall .pv{padding:14px;color:var(--mut)}
  /* aviso de festivos con la paleta clara */
  body #fpop{background:rgba(16,52,48,.30)}
  body #fpop .box{background:#fff;border-color:var(--line);color:var(--ink);box-shadow:0 24px 60px rgba(16,52,48,.25)}
  body #fpop .hd,body #fpop .ft{border-color:var(--line)} body #fpop .hd span,body #fpop .tag,body #fpop .rs i{color:var(--mut)}
  body #fpop .h{background:var(--bg);border-color:var(--line)} body #fpop .rs{color:#3C5A55} body #fpop .tag{border-color:var(--line)}
  body #fpop .d{color:var(--orange-d)} body #fpop .d.hoy{color:#C2402B}
  body #fpop button,body #fbell{background:#fff;color:var(--ink);border-color:var(--line)}
  body #fpop button.pri{background:var(--aqua);color:#fff;border-color:var(--aqua)}
  body #fbell{margin-left:0;padding:6px 10px;white-space:nowrap} body #fbell.hot{border-color:var(--orange);color:var(--orange-d);background:#FEF0E2}
  @media(max-width:900px){.brand span{display:none} #find span{display:none}}
  @media(max-width:640px){.topbar{gap:8px;padding:0 8px}.brand b{display:none}.updated{display:none}#fbell{font-size:0!important;padding:6px 8px!important}#fbell:first-letter{font-size:14px}}
"""

TOPBAR = """  <div class="topbar">
    <div class="brand" title="Kometa Delivery"><img class="klogo" src="{LOGO}" alt="Kometa Delivery"><b>MushDrink - Kometa</b></div>
    <nav class="secs" id="secs"></nav>
    <button id="find" title="Buscar pestaña (tecla /)">⌕ <span>Buscar pestaña</span> <kbd>/</kbd></button>
    {UPDATED}
  </div>
  <div class="tabs">{TABS}</div>
  <nav class="subbar" id="sub"></nav>
  <div class="stage" id="stage"><div id="loading"></div></div>
  <div id="pal" role="dialog" aria-modal="true"><div class="bx"><input id="palq" type="search" placeholder="Buscar pestaña o sección…" autocomplete="off"><div id="pall"></div></div></div>"""


def logo_uri():
    import base64
    return 'data:image/png;base64,' + base64.b64encode(open(os.path.join(HERE, 'kometa_logo.png'), 'rb').read()).decode()


def shell_js():
    return open(os.path.join(HERE, 'kometa_shell.js'), encoding='utf-8').read()


def evo_doc():
    return plantilla('plantilla_evolucion_negocio.html')


def split(h):
    """Devuelve las piezas del index actual: tabs (botones), span updated, docs, resto del body tras el script de DOCS."""
    tabs = re.search(r'<div class="tabs">(.*?)</div>', h, re.S).group(1)
    upd = re.search(r'<span class="updated">[^<]*</span>', h).group(0)
    i0 = h.index('const DOCS=') + len('const DOCS=')
    docs, e0 = json.JSONDecoder().raw_decode(h[i0:])
    s_end = h.index('</script>', i0 + e0) + len('</script>')
    tail = h[s_end:]                     # aviso de festivos y cierre
    return tabs, upd, docs, tail


def head(extra=''):
    return ('<!DOCTYPE html>\n<html lang="es"><head><meta name="robots" content="noindex,nofollow"><meta charset="utf-8">\n'
            '<meta name="viewport" content="width=device-width, initial-scale=1">\n' + MARCA_SHELL + '\n'
            '<title>Panel operativo · MushDrink</title>\n<link rel="icon" type="image/png" href="' + logo_uri() + '">\n<style>' + CSS + '</style>\n'
            '<script>\n' + shell_js() + '\n</script>' + extra + '</head>\n<body>\n')


def dump_docs(docs):
    return "[" + ",\n".join(json.dumps(x, ensure_ascii=False).replace("</", "<\\/") for x in docs) + "]"


# Pestañas propias del rediseño: (marca al inicio del documento, nombre de la pestaña, plantilla)
EXTRA = [(MARCA_EVO, TAB_EVO, 'plantilla_evolucion_negocio.html'),
         ('<!-- PERFORMANCE_DIARIO -->', 'Performance diario', 'plantilla_performance_diario.html')]


def add_evo(tabs, docs):
    for marca, tab, fichero in EXTRA:
        html = plantilla(fichero)
        k = next((i for i, d in enumerate(docs) if d.startswith(marca)), None)
        if k is None:
            docs.append(html); k = len(docs) - 1
            tabs += f'<button class="tab" data-i="{k}">{tab}</button>'
        else:
            docs[k] = html
    return tabs, docs


def apply(path):
    h = open(path, encoding='utf-8').read()
    tabs, upd, docs, tail = split(h)
    tabs, docs = add_evo(tabs, docs)
    out = (head() + TOPBAR.replace('{LOGO}', logo_uri()).replace('{UPDATED}', upd).replace('{TABS}', tabs) +
           '\n<script>\nconst DOCS=' + dump_docs(docs) + ';\nMDboot(DOCS);\n</script>' + tail)
    open(path, 'w', encoding='utf-8').write(out)
    print(f'mushdrink_rediseno: {len(docs)} pestañas · tema Kometa aplicado en {path}')


PREVIEW_JS = r"""
<script>
(async function(){
  const bar=document.getElementById('pbar'), txt=document.getElementById('ptxt');
  try{
    const r=await fetch('../index.html',{cache:'no-cache'}); const tot=+r.headers.get('content-length')||0;
    const rd=r.body.getReader(); const parts=[]; let n=0;
    for(;;){const {done,value}=await rd.read(); if(done)break; parts.push(value); n+=value.length;
      txt.textContent='Cargando datos del panel… '+(n/1048576).toFixed(0)+' MB'; if(tot) bar.style.width=Math.min(100,n/tot*100)+'%';}
    const h=new TextDecoder().decode(await new Blob(parts).arrayBuffer());
    txt.textContent='Preparando pestañas…';
    const i0=h.indexOf('const DOCS=')+11; let e=h.indexOf('];\nconst stage=',i0); if(e<0) e=h.indexOf('];\nMDboot(',i0);
    const DOCS=JSON.parse(h.slice(i0,e+1));
    const tabs=[...h.slice(0,i0).matchAll(/<button class="tab[^"]*" data-i="(\d+)">([^<]*)<\/button>/g)];
    const evo=await (await fetch('evolucion.html',{cache:'no-cache'})).text();
    DOCS.push(evo);
    const tb=document.querySelector('.tabs');
    tb.innerHTML=tabs.map(m=>`<button class="tab" data-i="${m[1]}">${m[2]}</button>`).join('')+`<button class="tab" data-i="${DOCS.length-1}">Evolución del negocio</button>`;
    const u=/<span class="updated">([^<]*)<\/span>/.exec(h); if(u) document.querySelector('.updated').textContent=u[1];
    // aviso de festivos del panel real
    const f0=h.indexOf('<style>\n  #fpop'); const f1=h.lastIndexOf('</body>');
    if(f0>0&&f1>f0){const box=document.createElement('div');box.innerHTML=h.slice(f0,f1);
      const scr=[...box.querySelectorAll('script')].map(s=>s.textContent); box.querySelectorAll('script').forEach(s=>s.remove());
      document.body.appendChild(box); MDboot(DOCS); scr.forEach(c=>{try{(new Function(c))();}catch(err){console.warn(err);}});}
    else MDboot(DOCS);
    document.getElementById('pload').remove();
  }catch(err){ console.error(err); txt.textContent='No se ha podido cargar el panel: '+err.message; }
})();
</script>"""

PREVIEW_OVERLAY = """<div id="pload" style="position:fixed;inset:0;background:#F4F9F8;z-index:2000;display:grid;place-items:center;font:14px Inter,system-ui,sans-serif;color:#16302C">
  <div style="width:min(420px,86vw);text-align:center"><div style="font-weight:700;font-size:16px;margin-bottom:6px">Vista previa · diseño Kometa</div>
  <div id="ptxt" style="color:#5E7471;margin-bottom:12px">Cargando datos del panel…</div>
  <div style="height:6px;background:#E3F5F2;border-radius:3px;overflow:hidden"><div id="pbar" style="height:100%;width:4%;background:#14A394;transition:width .2s"></div></div>
  <div style="color:#8FA3A0;font-size:12px;margin-top:12px">Usa los mismos datos que el panel publicado; no lo modifica.</div></div></div>
<div style="position:fixed;right:12px;bottom:12px;z-index:1500;background:#F28C28;color:#fff;font:700 11.5px Inter,system-ui,sans-serif;padding:6px 10px;border-radius:999px;box-shadow:0 6px 18px rgba(184,90,7,.3)">VISTA PREVIA</div>
"""


def preview(outdir):
    os.makedirs(outdir, exist_ok=True)
    body = TOPBAR.replace('{LOGO}', logo_uri()).replace('{UPDATED}', '<span class="updated">…</span>').replace('{TABS}', '')
    out = head().replace('<meta name="robots"', '<meta name="robots"') + PREVIEW_OVERLAY + body + PREVIEW_JS + '\n</body></html>\n'
    open(os.path.join(outdir, 'index.html'), 'w', encoding='utf-8').write(out)
    open(os.path.join(outdir, 'evolucion.html'), 'w', encoding='utf-8').write(evo_doc())
    print(f'mushdrink_rediseno: vista previa escrita en {outdir}')


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--html', default=os.path.join(HERE, '..', 'mushdrink', 'index.html'))
    ap.add_argument('--preview', help='carpeta de salida para la vista previa')
    a = ap.parse_args()
    preview(a.preview) if a.preview else apply(a.html)
