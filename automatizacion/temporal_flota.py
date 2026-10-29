# -*- coding: utf-8 -*-
"""
temporal_flota.py · Pestaña «Alertas por temporal» de los dashboards de flota (SAB y GRA-MAD-NOM-ALC)
=====================================================================================================
Lee los avisos oficiales de AEMET (Meteoalerta, formato CAP 1.2, hoy + 2 días = 72 h) de las
comunidades donde están las zonas de reparto, se queda con los de nivel AMARILLO, NARANJA o ROJO por
LLUVIAS o TORMENTAS y los cruza con cada zona de reparto:

  · % de las entregas de la zona dentro del polígono del aviso (puntos de entrega de pp_heat.json,
    últimos 7 días; si no hay puntos, por los municipios de la zona)
  · municipios de la zona afectados (punto representativo de cada municipio, INE)
  · intervalo horario del aviso (inicio → fin, hora peninsular) y zona de aviso AEMET

  python3 temporal_flota.py <index.html> <sab|gra-mad-nom-alc> [<pp_heat.json>]

Fuentes: canales RSS de avisos de AEMET por comunidad autónoma
  https://www.aemet.es/documentos_d/eltiempo/prediccion/avisos/rss/CAP_AFAC{61,72,77}_RSS.xml
y, si AEMET no responde, el canal de MeteoAlarm para España (mismos avisos de AEMET).
Las descargas se guardan 30 min en una caché (/tmp) para no repetirlas al pasar por los dos dashboards.
"""
import os, re, io, sys, json, time, tarfile, gzip, datetime, urllib.request
import xml.etree.ElementTree as ET
from zoneinfo import ZoneInfo

AUTO = os.path.dirname(os.path.abspath(__file__))
ZONAS = os.path.join(AUTO, "entradas", "temporal_zonas.json")
TZ = ZoneInfo("Europe/Madrid")
CACHE = os.path.join(os.environ.get("TMPDIR", "/tmp"), "aemet_avisos_cache.json")
FEEDS = {  # comunidad → canal AEMET
    "Andalucía": "https://www.aemet.es/documentos_d/eltiempo/prediccion/avisos/rss/CAP_AFAC61_RSS.xml",
    "Comunidad de Madrid": "https://www.aemet.es/documentos_d/eltiempo/prediccion/avisos/rss/CAP_AFAC72_RSS.xml",
    "Comunitat Valenciana": "https://www.aemet.es/documentos_d/eltiempo/prediccion/avisos/rss/CAP_AFAC77_RSS.xml",
}
METEOALARM = "https://feeds.meteoalarm.org/feeds/meteoalarm-legacy-atom-spain"
PROV_CCAA = {"Alicante": "Comunitat Valenciana", "Valencia": "Comunitat Valenciana", "Granada": "Andalucía", "Madrid": "Comunidad de Madrid"}
DASH = {"sab": ["SAB"], "gra-mad-nom-alc": ["ALC", "GRA", "MAD", "NOM"]}
NIVEL_SEV = {"minor": "verde", "moderate": "amarillo", "severe": "naranja", "extreme": "rojo"}
NIVELES = ("amarillo", "naranja", "rojo")
UA = {"User-Agent": "Mozilla/5.0 (flota-dashboards; avisos AEMET)", "Accept": "*/*"}


# ----------------------------------------------------------------------------- descargas
def _get(url, timeout=25):
    r = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(r, timeout=timeout) as resp:
        b = resp.read()
    if b[:2] == b"\x1f\x8b":
        try: b = gzip.decompress(b)
        except Exception: pass
    return b


def _xmls_de(b):
    """Devuelve los XML CAP contenidos en b (XML suelto o .tar/.tar.gz)."""
    if b.lstrip()[:1] == b"<":
        return [b]
    out = []
    try:
        with tarfile.open(fileobj=io.BytesIO(b)) as tf:
            for m in tf.getmembers():
                if m.isfile() and m.name.lower().endswith(".xml"):
                    out.append(tf.extractfile(m).read())
    except Exception:
        pass
    return out


def _links(feed_bytes):
    """URLs de mensajes CAP (o del fichero con el estado completo) en un canal RSS/Atom."""
    t = feed_bytes.decode("utf-8", "replace")
    urls = re.findall(r"https?://[^\s<>\"']+?\.(?:xml|tar\.gz|tgz|tar)(?=[\s<>\"']|$)", t)
    urls += re.findall(r"<link[^>]+href=\"([^\"]+)\"", t)          # Atom
    urls += re.findall(r"<link>\s*([^<\s]+)\s*</link>", t)          # RSS
    seen, out = set(), []
    for u in urls:
        u = u.replace("&amp;", "&")
        if u in seen or u.endswith("_RSS.xml") or u.endswith("_ATOM.xml") or "rss_info" in u: continue
        seen.add(u); out.append(u)
    return out


def descargar():
    try:
        c = json.load(open(CACHE, encoding="utf-8"))
        if time.time() - c.get("t", 0) < 1800: return c
    except Exception:
        pass
    caps, errores, fuente = [], [], "AEMET"
    for ccaa, url in FEEDS.items():
        try:
            fb = _get(url)
            links = _links(fb)
            got = 0
            for u in links:
                try:
                    for x in _xmls_de(_get(u)):
                        if b"urn:oasis:names:tc:emergency:cap" in x[:4000] or b"<alert" in x[:4000]:
                            caps.append(x.decode("utf-8", "replace")); got += 1
                except Exception as e:
                    errores.append(f"{ccaa}: {u[-60:]} → {e}")
            if not got and not links:
                errores.append(f"{ccaa}: canal sin enlaces CAP")
        except Exception as e:
            errores.append(f"{ccaa}: {e}")
    if not caps:                                   # plan B: MeteoAlarm (redistribuye los CAP de AEMET)
        try:
            fb = _get(METEOALARM, 40)
            for u in _links(fb)[:400]:
                if "aemet" not in u.lower() and "meteoalarm" not in u.lower(): continue
                try:
                    for x in _xmls_de(_get(u)):
                        caps.append(x.decode("utf-8", "replace"))
                except Exception:
                    pass
            fuente = "MeteoAlarm (avisos de AEMET)"
        except Exception as e:
            errores.append(f"MeteoAlarm: {e}")
    c = {"t": time.time(), "caps": caps, "errores": errores[:20], "fuente": fuente,
         "consulta": datetime.datetime.now(TZ).strftime("%d/%m/%Y %H:%M")}
    try: json.dump(c, open(CACHE, "w", encoding="utf-8"))
    except Exception: pass
    return c


# ----------------------------------------------------------------------------- CAP
def _ns(tag): return tag.split("}")[-1]


def _txt(el, name):
    for ch in el:
        if _ns(ch.tag) == name: return (ch.text or "").strip()
    return ""


def _kv(el, name):
    out = {}
    for ch in el:
        if _ns(ch.tag) == name:
            k = v = ""
            for x in ch:
                if _ns(x.tag) == "valueName": k = (x.text or "").strip()
                if _ns(x.tag) == "value": v = (x.text or "").strip()
            out[k] = v
    return out


def _dt(s):
    try: return datetime.datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(TZ)
    except Exception: return None


def parse_caps(caps):
    avisos = {}
    for xml in caps:
        try: root = ET.fromstring(xml.encode("utf-8") if isinstance(xml, str) else xml)
        except Exception: continue
        if _txt(root, "msgType").lower() == "cancel": continue
        ident = _txt(root, "identifier")
        infos = [i for i in root if _ns(i.tag) == "info"]
        info = next((i for i in infos if _txt(i, "language").lower().startswith("es")), infos[0] if infos else None)
        if info is None: continue
        par, ec = _kv(info, "parameter"), _kv(info, "eventCode")
        nivel = (par.get("AEMET-Meteoalerta nivel") or "").lower() or NIVEL_SEV.get(_txt(info, "severity").lower(), "")
        if nivel not in NIVELES: continue
        fen = " ".join([_txt(info, "event"), par.get("AEMET-Meteoalerta parametro", ""), ec.get("AEMET-Meteoalerta fenomeno", ""),
                        " ".join(v for k, v in ec.items())]).lower()
        cod = (ec.get("AEMET-Meteoalerta fenomeno") or par.get("AEMET-Meteoalerta parametro") or "").split(";")[0].strip().upper()
        if cod:                                    # código Meteoalerta: PR = lluvias, TO = tormentas
            if cod not in ("PR", "TO"): continue
            tipo = "Tormentas" if cod == "TO" else "Lluvias"
        else:
            if not re.search(r"lluvi|precipit|torment|thunder|rain", fen): continue
            tipo = "Tormentas" if re.search(r"torment|thunder", fen) else "Lluvias"
        ini = _dt(_txt(info, "onset") or _txt(info, "effective")); fin = _dt(_txt(info, "expires"))
        if not ini or not fin: continue
        for area in (a for a in info if _ns(a.tag) == "area"):
            polys = []
            for ch in area:
                if _ns(ch.tag) == "polygon" and ch.text:
                    pts = []
                    for pr in ch.text.split():
                        try:
                            la, lo = pr.split(","); pts.append((float(la), float(lo)))
                        except Exception:
                            pass
                    if len(pts) >= 3: polys.append(pts)
            geo = _kv(area, "geocode")
            zona = geo.get("AEMET-Meteoalerta zona") or geo.get("EMMA_ID") or ""
            k = (zona or _txt(area, "areaDesc"), tipo, nivel, ini.isoformat(), fin.isoformat())
            avisos[k] = dict(id=ident, zona_aemet=_txt(area, "areaDesc"), cod=zona, tipo=tipo, nivel=nivel,
                             ini=ini, fin=fin, polys=polys, titulo=_txt(info, "headline"),
                             detalle=(par.get("AEMET-Meteoalerta parametro", "").split(";")[1:2] or [""])[0],
                             prob=par.get("AEMET-Meteoalerta probabilidad", ""), desc=_txt(info, "description"))
    return list(avisos.values())


def _dentro(la, lo, poly):
    ins, n = False, len(poly)
    for i in range(n):
        y1, x1 = poly[i]; y2, x2 = poly[(i + 1) % n]
        if (y1 > la) != (y2 > la) and lo < (x2 - x1) * (la - y1) / ((y2 - y1) or 1e-12) + x1:
            ins = not ins
    return ins


# ----------------------------------------------------------------------------- cruce con zonas
def cruzar(avisos, zonas, puntos):
    ahora = datetime.datetime.now(TZ)
    out = []
    for z, Z in zonas.items():
        pts = puntos.get(z) or [(m[2], m[3], m[1]) for m in Z["muni"]]
        tot = sum(w for _, _, w in pts) or 1
        for a in avisos:
            if a["fin"] < ahora or not a["polys"]: continue
            inn = lambda la, lo: any(_dentro(la, lo, p) for p in a["polys"])
            w = sum(wt for la, lo, wt in pts if inn(la, lo))
            ms = [m for m in Z["muni"] if inn(m[2], m[3])]
            if not w and not ms: continue
            out.append(dict(zona=z, zona_nombre=Z["nombre"], pct=round(100 * w / tot, 1),
                            munis=[[m[0], m[1]] for m in ms], zona_aemet=a["zona_aemet"], tipo=a["tipo"], nivel=a["nivel"],
                            ini=a["ini"].strftime("%Y-%m-%dT%H:%M"), fin=a["fin"].strftime("%Y-%m-%dT%H:%M"),
                            titulo=a["titulo"], detalle=a["detalle"], prob=a["prob"], desc=a["desc"][:400]))
    rank = {"rojo": 0, "naranja": 1, "amarillo": 2}
    out.sort(key=lambda x: (x["ini"], rank[x["nivel"]], x["zona"]))
    return out


def puntos_heat(path, zonas):
    """Puntos de entrega (lat, lon, nº) por zona en los últimos 7 días de pp_heat.json."""
    try: d = json.load(open(path, encoding="utf-8"))
    except Exception: return {}
    ci = {c: i for i, c in enumerate(d.get("cols", []))}
    if not all(k in ci for k in ("dia", "area", "lat", "lon", "n")): return {}
    desde = (datetime.date.today() - datetime.timedelta(days=7)).isoformat()
    acc = {}
    for r in d.get("rows", []):
        if r[ci["dia"]] < desde or r[ci["area"]] not in zonas: continue
        k = (r[ci["area"]], r[ci["lat"]], r[ci["lon"]])
        acc[k] = acc.get(k, 0) + (r[ci["n"]] or 1)
    out = {}
    for (z, la, lo), n in acc.items(): out.setdefault(z, []).append((la, lo, n))
    return out


# ----------------------------------------------------------------------------- HTML
_BTN = '<button data-v="temporal" aria-pressed="false">Alertas por temporal</button>'


def seccion(data):
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    return r"""<section id="viewTemporal" style="display:none">
<style>
#viewTemporal .tp-k{display:flex;flex-wrap:wrap;gap:10px;margin-bottom:12px}
#viewTemporal .tp-k div{background:#fff;border:1px solid #E4E7EC;border-radius:10px;padding:9px 14px;min-width:150px}
#viewTemporal .tp-k b{display:block;font-size:20px;color:#14171F} #viewTemporal .tp-k span{font-size:11.5px;color:#6B7280}
#viewTemporal .tp-card{background:#fff;border:1px solid #E4E7EC;border-radius:10px;padding:12px 14px;margin-bottom:12px}
#viewTemporal table{width:100%;border-collapse:collapse;font-size:12.8px}
#viewTemporal th{background:#F0F2F5;text-align:left;padding:7px 8px;font-size:11px;color:#6B7280;text-transform:uppercase;letter-spacing:.03em}
#viewTemporal td{padding:7px 8px;border-top:1px solid #EEF0F3;vertical-align:top}
#viewTemporal table th,#viewTemporal table td{text-align:left!important;white-space:normal!important;min-width:0!important;font-family:inherit}
#viewTemporal table{table-layout:auto;min-width:0!important}
#viewTemporal td:nth-child(4){white-space:nowrap!important}
#viewTemporal .lv{display:inline-block;border-radius:6px;padding:2px 8px;font-weight:700;font-size:11.5px;white-space:nowrap}
#viewTemporal .lv.amarillo{background:#FEF3C7;color:#92400E;border:1px solid #FCD34D}
#viewTemporal .lv.naranja{background:#FFEDD5;color:#9A3412;border:1px solid #FDBA74}
#viewTemporal .lv.rojo{background:#FEE2E2;color:#991B1B;border:1px solid #FCA5A5}
#viewTemporal .zn{font-weight:700;color:#0E5A6B} #viewTemporal .mut{color:#6B7280;font-size:11.5px}
#viewTemporal .grid3{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px}
#viewTemporal .day h4{margin:0 0 6px;font-size:13px} #viewTemporal .day .z{border:1px solid #EEF0F3;border-radius:8px;padding:7px 9px;margin-bottom:6px;font-size:12.5px}
#viewTemporal .ok{color:#047857;font-weight:600}
#viewTemporal .err{background:#FEF2F2;border:1px solid #FECACA;color:#991B1B;border-radius:10px;padding:10px 12px;margin-bottom:12px;font-size:12.5px}
@media(max-width:900px){#viewTemporal .grid3{grid-template-columns:1fr}}
</style>
<div class="tp-card" style="display:flex;justify-content:space-between;gap:10px;flex-wrap:wrap;align-items:center">
  <div><b style="font-size:16px">Alertas por temporal · AEMET (72 h)</b><div class="mut" id="tpSub"></div></div>
  <div class="mut" id="tpSrc"></div>
</div>
<div id="tpErr"></div>
<div class="tp-k" id="tpKpi"></div>
<div class="tp-card"><div style="font-weight:700;margin-bottom:8px">Resumen por día y zona de reparto</div><div class="grid3" id="tpDias"></div></div>
<div class="tp-card"><div style="font-weight:700;margin-bottom:8px">Detalle de avisos</div><div style="overflow:auto"><table>
<thead><tr><th>Zona</th><th>Nivel</th><th>Fenómeno</th><th>Intervalo</th><th>% entregas</th><th>Municipios afectados</th><th>Zona de aviso AEMET</th></tr></thead>
<tbody id="tpBody"></tbody></table></div>
<div class="mut" style="margin-top:8px">Avisos de nivel amarillo, naranja o rojo por lluvias o tormentas. «% entregas» = parte de las entregas de los últimos 7 días de la zona de reparto que cae dentro del área del aviso. Horas en hora peninsular. Fuente: AEMET Meteoalerta (CAP).</div></div>
</section>
"""


def js(data):
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    return r"""<script>
/* ==== Pestaña Alertas por temporal (avisos AEMET) ==== */
(function(){
  const T=""" + payload + r""";
  const seg=document.getElementById('viewSeg'), sec=document.getElementById('viewTemporal');
  if(!seg||!sec) return;
  const $=id=>document.getElementById(id);
  const esc=s=>String(s??'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
  const DW=['dom','lun','mar','mié','jue','vie','sáb'];
  const p2=n=>String(n).padStart(2,'0');
  const now=new Date();
  const A=T.avisos.filter(a=>new Date(a.fin)>now);
  const fd=s=>{const d=new Date(s);return DW[d.getDay()]+' '+p2(d.getDate())+'/'+p2(d.getMonth()+1);};
  const fh=s=>s.slice(11,16);
  const iv=a=>{const si=a.ini.slice(0,10),sf=a.fin.slice(0,10);return fd(a.ini)+' '+fh(a.ini)+' → '+(si===sf?'':fd(a.fin)+' ')+fh(a.fin);};
  const lvl=n=>'<span class="lv '+n+'">'+n.toUpperCase()+'</span>';
  const ico=t=>t==='Tormentas'?'⛈️':'🌧️';
  // pestaña con contador
  const btn=seg.querySelector('button[data-v="temporal"]');
  if(btn&&A.length){const peor=A.some(a=>a.nivel==='rojo')?'#B91C1C':A.some(a=>a.nivel==='naranja')?'#C2410C':'#B45309';
    btn.innerHTML='Alertas por temporal <span style="background:'+peor+';color:#fff;border-radius:9px;padding:0 7px;font-size:11px;margin-left:4px">'+A.length+'</span>';}
  function pintar(){
    $('tpSub').textContent='Zonas de reparto: '+T.zonas.join(', ')+' · hoy y los 2 días siguientes';
    $('tpSrc').textContent='Consulta: '+T.consulta+' · '+T.fuente;
    $('tpErr').innerHTML=(!T.ok?'<div class="err">⚠ No se ha podido consultar AEMET en la última actualización'+(T.errores.length?': '+esc(T.errores.slice(0,3).join(' · ')):'')+'. Se reintentará en la próxima actualización horaria.</div>':'');
    const zs=[...new Set(A.map(a=>a.zona))];
    $('tpKpi').innerHTML=[[A.length,'Avisos activos o previstos'],[zs.length+' / '+T.zonas.length,'Zonas de reparto afectadas'],
      [A.filter(a=>a.nivel==='rojo').length,'Avisos rojos'],[A.filter(a=>a.nivel==='naranja').length,'Avisos naranjas'],[A.filter(a=>a.nivel==='amarillo').length,'Avisos amarillos']]
      .map(([v,l])=>'<div><b>'+v+'</b><span>'+l+'</span></div>').join('');
    const t0=new Date(now.getFullYear(),now.getMonth(),now.getDate());
    $('tpDias').innerHTML=[0,1,2].map(k=>{const d=new Date(t0);d.setDate(d.getDate()+k);const iso=d.getFullYear()+'-'+p2(d.getMonth()+1)+'-'+p2(d.getDate());
      const dd=A.filter(a=>a.ini.slice(0,10)<=iso&&a.fin.slice(0,10)>=iso);
      const by={};dd.forEach(a=>(by[a.zona]=by[a.zona]||[]).push(a));
      return '<div class="day"><h4>'+(k===0?'Hoy':k===1?'Mañana':'Pasado mañana')+' · '+DW[d.getDay()]+' '+p2(d.getDate())+'/'+p2(d.getMonth()+1)+'</h4>'+
        (Object.keys(by).length?Object.entries(by).sort().map(([z,l])=>'<div class="z"><span class="zn">'+z+'</span> '+
          l.map(a=>lvl(a.nivel)+' '+ico(a.tipo)+' '+a.tipo+' <b>'+(a.ini.slice(0,10)<iso?'00:00':fh(a.ini))+'–'+(a.fin.slice(0,10)>iso?'24:00':fh(a.fin))+'</b> <span class="mut">('+a.pct+'% entregas)</span>').join('<br>')+'</div>').join('')
        :'<div class="ok">Sin avisos de lluvia/tormenta</div>')+'</div>';}).join('');
    $('tpBody').innerHTML=A.length?A.map(a=>'<tr><td><span class="zn">'+a.zona+'</span><div class="mut">'+esc(a.zona_nombre)+'</div></td><td>'+lvl(a.nivel)+'</td><td>'+ico(a.tipo)+' '+esc(a.tipo)+(a.detalle?'<div class="mut">'+esc(a.detalle)+'</div>':'')+(a.prob?'<div class="mut">Prob. '+esc(a.prob)+'</div>':'')+'</td>'+
      '<td style="white-space:nowrap"><b>'+iv(a)+'</b></td><td><b>'+a.pct+'%</b></td><td>'+(a.munis.length?a.munis.map(m=>esc(m[0])+' <span class="mut">'+Math.round(m[1])+'%</span>').join(', '):'<span class="mut">—</span>')+'</td><td>'+esc(a.zona_aemet)+(a.desc?'<div class="mut">'+esc(a.desc)+'</div>':'')+'</td></tr>').join('')
      :'<tr><td colspan="7" class="ok">✓ Ninguna zona de reparto tiene aviso amarillo, naranja o rojo por lluvias o tormentas en las próximas 72 h.</td></tr>';
  }
  seg.querySelectorAll('button').forEach(b=>b.addEventListener('click',()=>{
    const on=b.dataset.v==='temporal';
    sec.style.display=on?'':'none';
    if(on){ seg.querySelectorAll('button').forEach(x=>x.setAttribute('aria-pressed',String(x===b)));
      ['viewSemanal','viewDiario','viewLiga'].forEach(id=>{const e=document.getElementById(id); if(e) e.style.display='none';});
      window.scrollTo(0,0); pintar(); }
  }));
  pintar();
})();
</script>
"""


def integrar(html, data):
    i, j = html.find("<!-- temporal_flota -->"), html.find("<!-- /temporal_flota -->")
    if i >= 0 and j > i: html = html[:i] + html[j + len("<!-- /temporal_flota -->"):]
    html = html.replace(" " + _BTN, "").replace(_BTN, "")
    i, j = html.find('<section id="viewTemporal"'), html.find("</section>", html.find('<section id="viewTemporal"'))
    if i >= 0 and j > i: html = html[:i] + html[j + len("</section>"):]
    seg = html.find('id="viewSeg"')
    end = html.find("</div>", seg)
    if seg < 0 or end < 0 or '<div id="viewSemanal">' not in html or "</body>" not in html:
        raise ValueError("la plantilla no tiene el selector de Vista esperado")
    html = html[:end] + "  " + _BTN + "\n      " + html[end:]
    html = html.replace('<div id="viewSemanal">', seccion(data) + '  <div id="viewSemanal">', 1)
    k = html.rindex("</body>")
    return html[:k] + "<!-- temporal_flota -->" + js(data) + "<!-- /temporal_flota -->\n" + html[k:]


def main():
    html_p, dash = sys.argv[1], sys.argv[2]
    heat_p = sys.argv[3] if len(sys.argv) > 3 else os.path.join(os.path.dirname(html_p), "pp_heat.json")
    zall = json.load(open(ZONAS, encoding="utf-8"))
    zonas = {z: zall[z] for z in DASH[dash]}
    c = descargar()
    avisos = parse_caps(c["caps"])
    res = cruzar(avisos, zonas, puntos_heat(heat_p, zonas))
    data = dict(zonas=list(zonas), avisos=res, consulta=c["consulta"], fuente=c["fuente"],
                ok=bool(c["caps"]) or not c["errores"], errores=c["errores"], n_cap=len(c["caps"]), n_lluvia=len(avisos))
    h = open(html_p, encoding="utf-8").read()
    open(html_p, "w", encoding="utf-8").write(integrar(h, data))
    print(f"temporal_flota: {dash} · {len(c['caps'])} CAP leídos ({c['fuente']}) · {len(avisos)} avisos lluvia/tormenta ≥ amarillo · "
          f"{len(res)} cruces con zonas" + (f" · errores: {c['errores'][:2]}" if c["errores"] else ""))


if __name__ == "__main__":
    main()
