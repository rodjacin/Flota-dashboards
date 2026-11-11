# -*- coding: utf-8 -*-
"""
Pestaña «Forecast» de los dashboards de flota (SAB y GRA-MAD-NOM-ALC).

Fuente: bucket de Glovo, carpeta forecast/<viernes>/.../forecast_demand.csv (copia local en
~/Downloads/fleet_data). Glovo lo publica cada viernes con las horas de demanda previstas por zona
para las semanas W2, W3, W4 y W5.

  · W2..W5 se cuentan desde la semana de publicación: W1 = la semana siguiente al viernes de publicación,
    W2 = la de después, etc. (viernes 06/11 → W2 = semana del 16/11).
  · Reservas = medias horas reservadas en la Fleet Tool (calendario_fleet.json: presentadas + no show +
    en evaluación) / 2, solo para semanas leídas completas (7 días).

Uso: python3 forecast_flota.py <index.html> <sab|gra-mad-nom-alc>
"""
import os, sys, csv, glob, json, datetime as dt

AUTO = os.path.dirname(os.path.abspath(__file__))
FLEET = os.path.expanduser("~/Downloads/fleet_data")
CAL = os.path.join(AUTO, "entradas", "calendario_fleet.json")
DASH = {"sab": ["SAB"], "gra-mad-nom-alc": ["ALC", "GRA", "MAD", "NOM"]}
ALIAS = {"NEM": "MAD"}
_BTN = '<button data-v="forecast" aria-pressed="false">Forecast</button>'


def _lunes(d):
    return d - dt.timedelta(days=d.weekday())


def leer_forecasts():
    """{fecha_publicación: {zona: {semana_lunes: horas}}}"""
    out = {}
    for f in sorted(glob.glob(os.path.join(FLEET, "forecast", "*", "**", "forecast_demand*.csv"), recursive=True)):
        with open(f, encoding="utf-8-sig") as fh:
            for r in csv.DictReader(fh):
                try:
                    pub = dt.date.fromisoformat((r.get("forecast_date") or "").strip()[:10])
                except ValueError:
                    continue
                z = (r.get("zone_code") or "").strip().upper()
                z = ALIAS.get(z, z)
                base = _lunes(pub) + dt.timedelta(days=7)          # W1 = semana siguiente a la publicación
                for k in ("w2", "w3", "w4", "w5"):
                    try:
                        v = float(r.get(k) or "")
                    except ValueError:
                        continue
                    sem = base + dt.timedelta(days=7 * (int(k[1]) - 1))
                    out.setdefault(pub.isoformat(), {}).setdefault(z, {})[sem.isoformat()] = round(v, 2)
    return out


def leer_reservas():
    """{zona: {semana_lunes: horas reservadas}} solo semanas con los 7 días leídos."""
    try:
        d = json.load(open(CAL, encoding="utf-8"))
    except Exception:
        return {}, None
    tmp = {}
    for k, v in d.get("dias", {}).items():
        z, f = k.split("|")
        f = dt.date.fromisoformat(f)
        sem = _lunes(f).isoformat()
        s = sum(v.get("b", [])) + sum(v.get("nc", [])) + sum(v.get("ev", []))
        t = tmp.setdefault(z, {}).setdefault(sem, [0, set()])
        t[0] += s / 2.0
        t[1].add(f)
    res = {z: {s: round(h, 1) for s, (h, dias) in w.items() if len(dias) == 7} for z, w in tmp.items()}
    return res, d.get("generado")


def datos(dash):
    zonas = DASH[dash]
    fc = leer_forecasts()
    fc = {p: {z: w for z, w in v.items() if z in zonas} for p, v in fc.items()}
    fc = {p: v for p, v in fc.items() if v}
    res, gen = leer_reservas()
    res = {z: res.get(z, {}) for z in zonas}
    return dict(zonas=zonas, fc=fc, res=res, cal_generado=gen,
                generado=dt.datetime.now(dt.timezone(dt.timedelta(hours=1))).strftime("%d/%m/%Y %H:%M"))


def seccion():
    return r"""<section id="viewForecast" style="display:none">
<style>
#viewForecast .fc-card{background:#fff;border:1px solid #E4E7EC;border-radius:10px;padding:12px 14px;margin-bottom:12px}
#viewForecast .fc-k{display:flex;flex-wrap:wrap;gap:10px;margin-bottom:12px}
#viewForecast .fc-k div{background:#fff;border:1px solid #E4E7EC;border-radius:10px;padding:9px 14px;min-width:150px}
#viewForecast .fc-k b{display:block;font-size:20px;color:#14171F} #viewForecast .fc-k span{font-size:11.5px;color:#6B7280}
#viewForecast table{width:100%;border-collapse:collapse;font-size:12.8px;table-layout:auto;min-width:0!important}
#viewForecast th{background:#F0F2F5;padding:7px 8px;font-size:11px;color:#6B7280;text-transform:uppercase;letter-spacing:.03em;text-align:right!important;white-space:nowrap}
#viewForecast td{padding:7px 8px;border-top:1px solid #EEF0F3;text-align:right!important;white-space:nowrap;font-variant-numeric:tabular-nums}
#viewForecast th.l,#viewForecast td.l{text-align:left!important}
#viewForecast .mut{color:#6B7280;font-size:11.5px} #viewForecast .zn{font-weight:700;color:#0E5A6B}
#viewForecast .up{color:#B42318} #viewForecast .dn{color:#047857} #viewForecast .tot td{font-weight:700;background:#F7F8FA}
#viewForecast select{border:1px solid #E4E7EC;border-radius:8px;padding:6px 8px;font-size:13px;background:#fff}
#viewForecast .gap.neg{color:#B42318;font-weight:700} #viewForecast .gap.pos{color:#047857;font-weight:700}
</style>
<div class="fc-card" style="display:flex;justify-content:space-between;gap:10px;flex-wrap:wrap;align-items:center">
  <div><b style="font-size:16px">Forecast de demanda · Glovo</b><div class="mut" id="fcSub"></div></div>
  <label class="mut">Publicación <select id="fcPub"></select></label>
</div>
<div class="fc-k" id="fcKpi"></div>
<div class="fc-card"><div style="font-weight:700;margin-bottom:8px">Horas de demanda previstas por zona</div><div style="overflow:auto"><table id="fcTab"></table></div>
<div class="mut" style="margin-top:8px" id="fcNota1"></div></div>
<div class="fc-card"><div style="font-weight:700;margin-bottom:8px">Demanda prevista vs horas reservadas en la Fleet Tool</div><div style="overflow:auto"><table id="fcRes"></table></div>
<div class="mut" style="margin-top:8px" id="fcNota2"></div></div>
<div class="fc-card"><div style="font-weight:700;margin-bottom:8px">Evolución del forecast por semana</div><div style="overflow:auto"><table id="fcHist"></table></div>
<div class="mut" style="margin-top:8px">Cada fila es una semana; cada columna, el viernes en que Glovo publicó el forecast. Sirve para ver si la previsión de una misma semana sube o baja de una publicación a otra.</div></div>
</section>
"""


def js(data):
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    return r"""<script>
/* ==== Pestaña Forecast (forecast_demand.csv del bucket de Glovo) ==== */
(function(){
  const F=""" + payload + r""";
  const seg=document.getElementById('viewSeg'), sec=document.getElementById('viewForecast');
  if(!seg||!sec) return;
  const $=id=>document.getElementById(id);
  const n0=v=>v==null?'—':Math.round(v).toLocaleString('es-ES');
  const n1=v=>v==null?'—':v.toLocaleString('es-ES',{minimumFractionDigits:1,maximumFractionDigits:1});
  const p2=n=>String(n).padStart(2,'0');
  const D=s=>new Date(s+'T12:00:00');
  const wk=s=>{const d=D(s);d.setDate(d.getDate()+3-((d.getDay()+6)%7));const y=new Date(d.getFullYear(),0,4);return 1+Math.round(((d-y)/864e5-3+((y.getDay()+6)%7))/7);};
  const rango=s=>{const a=D(s),b=D(s);b.setDate(b.getDate()+6);return p2(a.getDate())+'/'+p2(a.getMonth()+1)+'–'+p2(b.getDate())+'/'+p2(b.getMonth()+1);};
  const fpub=s=>{const d=D(s);return ['dom','lun','mar','mié','jue','vie','sáb'][d.getDay()]+' '+p2(d.getDate())+'/'+p2(d.getMonth()+1);};
  const pubs=Object.keys(F.fc).sort();
  const dl=(v,b)=>{if(v==null||b==null||!b)return '';const p=(v-b)/b*100;return ` <span class="${p>0?'up':p<0?'dn':'mut'}">${p>0?'+':''}${n1(p)}%</span>`;};
  function pintar(){
    if(!pubs.length){$('fcSub').textContent='Todavía no hay ningún forecast_demand.csv en el bucket.';return;}
    const sel=$('fcPub'); if(!sel.options.length){sel.innerHTML=pubs.slice().reverse().map(p=>`<option value="${p}">${fpub(p)}</option>`).join(''); sel.onchange=pintar;}
    const P=sel.value, Z=F.fc[P]||{}, prev=pubs[pubs.indexOf(P)-1];
    const sems=[...new Set(Object.values(Z).flatMap(w=>Object.keys(w)))].sort();
    $('fcSub').textContent='Publicado el '+fpub(P)+' · zonas '+F.zonas.join(', ')+' · W2 a W5 = semanas '+sems.map(wk).join(', ')+' · actualizado '+F.generado;
    const tot=s=>F.zonas.reduce((a,z)=>a+((Z[z]||{})[s]||0),0);
    $('fcKpi').innerHTML=sems.map((s,i)=>`<div><span>W${i+2} · sem. ${wk(s)} (${rango(s)})</span><b>${n0(tot(s))} h</b></div>`).join('');
    const PZ=prev?F.fc[prev]||{}:{};
    $('fcTab').innerHTML='<tr><th class="l">Zona</th>'+sems.map((s,i)=>`<th>W${i+2} · sem. ${wk(s)}<br><span style="font-weight:400;text-transform:none">${rango(s)}</span></th>`).join('')+'</tr>'+
      F.zonas.filter(z=>Z[z]).map(z=>`<tr><td class="l zn">${z}</td>`+sems.map(s=>`<td>${n0(Z[z][s])} h${dl(Z[z][s],(PZ[z]||{})[s])}</td>`).join('')+'</tr>').join('')+
      (F.zonas.filter(z=>Z[z]).length>1?'<tr class="tot"><td class="l">Total</td>'+sems.map(s=>`<td>${n0(tot(s))} h${prev?dl(tot(s),F.zonas.reduce((a,z)=>a+((PZ[z]||{})[s]||0),0)||null):''}</td>`).join('')+'</tr>':'');
    $('fcNota1').textContent='Horas de demanda que Glovo prevé por zona y semana (fichero forecast_demand.csv del '+P+'). '+(prev?'Entre paréntesis de color: variación frente a lo que preveía para la misma semana el forecast del '+fpub(prev)+'. ':'')+'W1 = semana siguiente a la publicación (no viene en el fichero).';
    // demanda vs reservas: semanas con forecast (de cualquier publicación, la más reciente) y reservas completas
    const ult={}; pubs.forEach(p=>Object.entries(F.fc[p]).forEach(([z,w])=>Object.entries(w).forEach(([s,v])=>{(ult[z]=ult[z]||{})[s]={v,p};})));
    const filas=[]; F.zonas.forEach(z=>Object.entries(F.res[z]||{}).forEach(([s,h])=>{const f=(ult[z]||{})[s]; filas.push({z,s,h,f});}));
    filas.sort((a,b)=>a.s<b.s?-1:a.s>b.s?1:a.z<b.z?-1:1);
    const conF=filas.filter(x=>x.f);
    $('fcRes').innerHTML='<tr><th class="l">Semana</th><th class="l">Zona</th><th>Demanda prevista</th><th>Horas reservadas</th><th>Diferencia</th><th>Cobertura</th><th class="l">Forecast usado</th></tr>'+
      (conF.length?conF.map(x=>{const g=x.h-x.f.v;return `<tr><td class="l">sem. ${wk(x.s)} · ${rango(x.s)}</td><td class="l zn">${x.z}</td><td>${n0(x.f.v)} h</td><td>${n0(x.h)} h</td><td class="gap ${g<0?'neg':'pos'}">${g>0?'+':''}${n0(g)} h</td><td>${n1(x.h/x.f.v*100)}%</td><td class="l mut">publicado ${fpub(x.f.p)}</td></tr>`;}).join('')
       :`<tr><td class="l mut" colspan="7">Aún no hay ninguna semana con forecast y reservas a la vez. Las reservas leídas de la Fleet Tool cubren ${filas.length?[...new Set(filas.map(x=>'sem. '+wk(x.s)))].join(', '):'ninguna semana completa'}; el forecast publicado empieza en la semana ${sems.length?wk(sems[0]):'—'}.</td></tr>`);
    $('fcNota2').textContent='Horas reservadas = medias horas reservadas en el calendario de la Fleet Tool (presentadas + no show + en evaluación) ÷ 2, solo semanas leídas completas. '+(F.cal_generado?'Última lectura del calendario: '+F.cal_generado.replace('T',' ').slice(0,16)+'.':'');
    const allS=[...new Set(pubs.flatMap(p=>Object.values(F.fc[p]).flatMap(w=>Object.keys(w))))].sort();
    $('fcHist').innerHTML='<tr><th class="l">Semana</th>'+pubs.map(p=>`<th>Publ. ${fpub(p)}</th>`).join('')+'</tr>'+
      allS.map(s=>`<tr><td class="l">sem. ${wk(s)} · ${rango(s)}</td>`+pubs.map(p=>{const v=F.zonas.reduce((a,z)=>a+((F.fc[p][z]||{})[s]||0),0);return `<td>${v?n0(v)+' h':'—'}</td>`;}).join('')+'</tr>').join('');
  }
  seg.querySelectorAll('button').forEach(b=>b.addEventListener('click',()=>{
    const on=b.dataset.v==='forecast';
    sec.style.display=on?'':'none';
    if(on){ seg.querySelectorAll('button').forEach(x=>x.setAttribute('aria-pressed',String(x===b)));
      ['viewSemanal','viewDiario','viewLiga','viewTemporal'].forEach(id=>{const e=document.getElementById(id); if(e) e.style.display='none';});
      window.scrollTo(0,0); pintar(); }
  }));
  pintar();
})();
</script>
"""


def integrar(html, data):
    i, j = html.find("<!-- forecast_flota -->"), html.find("<!-- /forecast_flota -->")
    if i >= 0 and j > i: html = html[:i] + html[j + len("<!-- /forecast_flota -->"):]
    html = html.replace(" " + _BTN, "").replace(_BTN, "")
    i = html.find('<section id="viewForecast"')
    if i >= 0: html = html[:i] + html[html.find("</section>", i) + len("</section>"):]
    seg = html.find('id="viewSeg"'); end = html.find("</div>", seg)
    if seg < 0 or end < 0 or '<div id="viewSemanal">' not in html or "</body>" not in html:
        raise ValueError("la plantilla no tiene el selector de Vista esperado")
    html = html[:end] + "  " + _BTN + "\n      " + html[end:]
    html = html.replace('<div id="viewSemanal">', seccion() + '  <div id="viewSemanal">', 1)
    k = html.rindex("</body>")
    return html[:k] + "<!-- forecast_flota -->" + js(data) + "<!-- /forecast_flota -->\n" + html[k:]


def main():
    html_p, dash = sys.argv[1], sys.argv[2]
    data = datos(dash)
    h = open(html_p, encoding="utf-8").read()
    open(html_p, "w", encoding="utf-8").write(integrar(h, data))
    print(f"forecast_flota: {dash} · {len(data['fc'])} publicaciones · zonas {data['zonas']} · "
          f"reservas completas: {sum(len(v) for v in data['res'].values())} zona-semanas")


if __name__ == "__main__":
    main()
