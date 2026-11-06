# -*- coding: utf-8 -*-
"""
MushDrink · pestaña «Repartidores · SLA»: detalle por tramos de 1 h (20:00–23:00).

Al pulsar el nº de pedidos de una jornada en la tabla se abre un pop-up con, para cada
tramo 20-21, 21-22 y 22-23 h y para el total 20:00-23:00:
  · pedidos confirmados en el tramo (hora de confirmación)        -> HTAVG de «Operativa restaurantes»
  · pedidos > 45 min y % sobre los pedidos del tramo               -> HTAVG
  · repartidores distintos que entregaron pedidos en el tramo      -> AGG de «Pedidos por rider · 15 min»

No necesita datos nuevos: se recalcula con lo que ya hay en el panel. Es idempotente;
conviene relanzarlo después de añadir un día:
    python3 automatizacion/mushdrink_sla_tramos.py mushdrink/index.html
"""
import sys, re, json, collections

TRAMOS = (20, 21, 22)
INI, FIN = "/*__SLA_TRAMOS_INI__*/", "/*__SLA_TRAMOS_FIN__*/"


def _get(doc, name):
    m = re.search(r"(?:const|let|var)\s+" + name + r"\s*=\s*", doc)
    return json.JSONDecoder().raw_decode(doc[m.end():])[0]


def build_hr(d1, d2, d3):
    DATA, AGG = _get(d1, "DATA"), _get(d2, "AGG")
    DS, HT = _get(d3, "DS"), _get(d3, "HTAVG")
    codes = collections.defaultdict(list)                     # nombre -> códigos (día + noche LN)
    for r in DS["restaurants"]:
        codes[r["name"]].append(str(r["code"]))
    HR = {}
    for name, pts in DATA["series"].items():
        cs = codes.get(name)
        if not cs:
            continue
        out = {}
        for p in pts:
            dm = p[2]
            iso = "2026-%s-%s" % (dm[3:], dm[:2])
            n = collections.Counter(); o45 = collections.Counter()
            rid = collections.defaultdict(set); found = False
            for c in cs:
                h = HT["H"].get(c, {}).get(iso)
                if h:
                    found = True
                    for k in range(0, len(h), 4):
                        if h[k] in TRAMOS:
                            n[h[k]] += h[k + 1]; o45[h[k]] += h[k + 3]
                flat = AGG["data"].get(c + "|" + iso)
                if flat:
                    found = True
                    for k in range(0, len(flat), 3):
                        hh = flat[k + 1] // 4
                        if hh in TRAMOS:
                            rid[hh].add(flat[k])
            if not found:
                continue
            row = []
            for t in TRAMOS:
                row += [n[t], o45[t], len(rid[t])]
            row.append(len(set().union(*rid.values())) if rid else 0)
            out[dm] = row
        if out:
            HR[name] = out
    return HR


CSS = """
.ped-btn{background:none;border:0;padding:2px 6px;margin:-2px -6px;border-radius:6px;color:var(--focus);font:inherit;cursor:pointer;text-decoration:underline dotted;text-underline-offset:3px}
.ped-btn:hover{background:rgba(124,199,255,.12)}
#trPop{position:fixed;inset:0;background:rgba(5,8,12,.66);display:none;align-items:flex-start;justify-content:center;z-index:50;padding:70px 14px;overflow:auto}
#trPop.on{display:flex}
#trPop .box{background:var(--panel);border:1px solid var(--line);border-radius:var(--r);max-width:720px;width:100%;box-shadow:0 20px 60px rgba(0,0,0,.5)}
#trPop .hd{padding:16px 18px;border-bottom:1px solid var(--line);display:flex;gap:12px;align-items:flex-start;justify-content:space-between}
#trPop .hd b{font-family:"Space Grotesk",sans-serif;font-size:16px;display:block}
#trPop .hd span{color:var(--dim);font-size:12.5px}
#trPop .x{background:var(--panel2);border:1px solid var(--line);color:var(--ink);border-radius:8px;padding:4px 10px;cursor:pointer;font-size:14px}
#trPop .bd{padding:6px 18px 14px}
#trPop table{width:100%;border-collapse:collapse;font-size:13px}
#trPop th{text-align:right;color:var(--dim);font-weight:600;font-size:11.5px;text-transform:uppercase;letter-spacing:.4px;padding:10px 8px;border-bottom:1px solid var(--line)}
#trPop th:first-child,#trPop td:first-child{text-align:left}
#trPop td{text-align:right;padding:9px 8px;border-bottom:1px solid var(--line-soft);font-family:"IBM Plex Mono",monospace}
#trPop tr.tot td{font-weight:600;border-top:1px solid var(--line);border-bottom:0}
#trPop .nt{color:var(--faint);font-size:11.5px;margin-top:10px;line-height:1.5}
"""

JS = r"""
(function(){
  const pop=document.createElement('div'); pop.id='trPop';
  pop.innerHTML='<div class="box" role="dialog" aria-modal="true"><div class="hd"><div><b id="trT"></b><span id="trS"></span></div><button class="x" id="trX" aria-label="Cerrar">✕</button></div><div class="bd" id="trB"></div></div>';
  document.body.appendChild(pop);
  const close=()=>pop.classList.remove('on');
  pop.addEventListener('click',e=>{if(e.target===pop)close();});
  document.getElementById('trX').addEventListener('click',close);
  document.addEventListener('keydown',e=>{if(e.key==='Escape')close();});
  const pc=(a,b)=>b?a/b*100:null;
  window.openTramos=function(rest,dm){
    const p=(DATA.series[rest]||[]).map(mapPt).find(x=>x.date===dm);
    const v=(HR[rest]||{})[dm];
    document.getElementById('trT').textContent=rest;
    document.getElementById('trS').textContent=p?`${DAYS_ES[DAYS[p.dow]]} ${dm} · W${p.wk} · pedidos confirmados por tramo de 1 h`:dm;
    if(!v){document.getElementById('trB').innerHTML='<p class="nt">Sin detalle por tramos para esta jornada.</p>';pop.classList.add('on');return;}
    const rows=[];let N=0,O=0;
    [20,21,22].forEach((h,i)=>{const n=v[i*3],o=v[i*3+1],r=v[i*3+2];N+=n;O+=o;rows.push([`${h}:00 – ${h+1}:00`,n,r,o]);});
    const cell=(n,o)=>{const q=pc(o,n),c=pctColor(q);return `<span class="pctcell" style="background:${c.bg};color:${c.fg}">${q==null?'—':q.toFixed(1)+'%'}</span>`;};
    document.getElementById('trB').innerHTML=`<table><thead><tr><th>Tramo</th><th>Pedidos</th><th>Repartidores</th><th>&gt;45 min</th><th>% &gt;45 min</th></tr></thead><tbody>`+
      rows.map(x=>`<tr><td>${x[0]}</td><td>${fmt(x[1])}</td><td class="riders-num">${x[2]}</td><td>${fmt(x[3])}</td><td>${cell(x[1],x[3])}</td></tr>`).join('')+
      `<tr class="tot"><td>20:00 – 23:00</td><td>${fmt(N)}</td><td class="riders-num">${v[9]}</td><td>${fmt(O)}</td><td>${cell(N,O)}</td></tr></tbody></table>`+
      `<p class="nt">Pedidos y &gt;45 min por hora de confirmación del pedido (tiempo total &gt; 45 min). Repartidores: distintos que entregaron pedidos del restaurante en ese tramo (hora de entrega); en el total, sin duplicar.</p>`;
    pop.classList.add('on');
  };
  document.getElementById('c1body').addEventListener('click',e=>{const b=e.target.closest('.ped-btn');if(b)openTramos(state.c1rest,b.dataset.dm);});
})();
"""


def patch_d1(d1, HR):
    # 1) datos (idempotente)
    payload = INI + "const HR=" + json.dumps(HR, ensure_ascii=False, separators=(",", ":")) + ";" + FIN
    if INI in d1:
        d1 = re.sub(re.escape(INI) + r".*?" + re.escape(FIN), lambda m: payload, d1, flags=re.S)
    else:
        d1 = d1.replace("const DAYS = DATA.days_order;", payload + "\nconst DAYS = DATA.days_order;", 1)
    # 2) CSS + JS + celda clicable (solo la primera vez)
    if "openTramos" not in d1:
        d1 = d1.replace("</style>", CSS + "</style>", 1)
        d1 = d1.replace("<td>${fmt(p.orders)}</td>",
                        '<td><button class="ped-btn" data-dm="${p.date}" title="Ver por tramos 20:00–23:00">${fmt(p.orders)}</button></td>', 1)
        d1 = d1.replace("renderKPIs(); renderChart1();\n</script>", "renderKPIs(); renderChart1();\n" + JS + "</script>", 1)
        if "openTramos" not in d1 or "ped-btn\" data-dm" not in d1:
            raise SystemExit("No encuentro los puntos de inserción de la pestaña Repartidores · SLA")
    return d1


def main(path):
    html = open(path, encoding="utf-8").read()
    i = html.index("const DOCS=") + len("const DOCS=")
    docs, e = json.JSONDecoder().raw_decode(html[i:])
    HR = build_hr(docs[1], docs[2], docs[3])
    docs[1] = patch_d1(docs[1], HR)
    payload = ",\n".join(json.dumps(d, ensure_ascii=False).replace("</", "<\\/") for d in docs)
    open(path, "w", encoding="utf-8").write(html[:i] + "[" + payload + "]" + html[i + e:])
    print(f"Repartidores · SLA: tramos 20-23 h para {len(HR)} restaurantes, "
          f"{sum(len(v) for v in HR.values())} jornadas")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "mushdrink/index.html")
