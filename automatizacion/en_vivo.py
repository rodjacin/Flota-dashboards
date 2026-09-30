# -*- coding: utf-8 -*-
"""
================================================================================
 Pestaña "En vivo" para los dashboards de flota (Glovo Live Operations API)
================================================================================
 En cada actualización del dashboard:
   1. Genera un token STS con la clave de ~/claves-pem (client_id mushdrinks-87).
   2. Averigua el id de cada ciudad (fijo, en caché o a partir de los contratos
      de tus riders en Rooster).
   3. Descarga de Live Operations (v1) los riders, el resumen de empresas y el
      detalle de tu empresa por ciudad.
   4. Quita teléfono, email y coordenadas GPS (los links son públicos).
 Si Glovo no responde, se muestra la última foto guardada, marcada como antigua.
 Lo usa generar_resumen_flota.py (igual que UTR, No show y Capacidad).
================================================================================
"""
import os, re, json, time, uuid, base64, subprocess, datetime as dt, collections, urllib.request, urllib.parse, urllib.error

HOST = "https://gv-es.usehurrier.com"
STS_URL = "https://sts.dh-auth.io/oauth2/token"
CLIENT_ID = "mushdrinks-87"
KID = "291f0e9a-3c59-46bc-9511-f3b440cbe465"   # kid de la clave registrada en septiembre (antes: mushdrinks-87)
KEY_FILE = os.path.expanduser("~/claves-pem/private_key.pem")
KEY_FILES = [KEY_FILE, os.path.expanduser("~/Desktop/Glovo API/3pl-docs-v2/key_old.pem")]
CACHE_DIR = os.path.expanduser("~/Downloads/dashboards/en_vivo")
RIDER_CSV = os.path.expanduser("~/Downloads/fleet_data_combinado/rider_lv_combinado.csv")
NODE_ALIASES = {"NEM": "MAD"}
CITY_IDS_FIJOS = {"GRA": 1015}          # ids confirmados a mano; el resto se averigua
TIMEOUT = 25
_MEMO = {}                              # una sola descarga por ejecución del generador


def _ssl_ctx():
    """Python de python.org/Homebrew a veces no trae certificados: usa certifi o los del sistema macOS."""
    import ssl
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        pass
    for f in ("/etc/ssl/cert.pem", "/opt/homebrew/etc/openssl@3/cert.pem", "/usr/local/etc/openssl@3/cert.pem",
              "/opt/homebrew/etc/ca-certificates/cert.pem"):
        if os.path.exists(f):
            return ssl.create_default_context(cafile=f)
    return ssl.create_default_context()


_CTX = None


def _open(req):
    global _CTX
    if _CTX is None:
        _CTX = _ssl_ctx()
    return urllib.request.urlopen(req, timeout=TIMEOUT, context=_CTX)
_LOG = []


def _log(m):
    _LOG.append(m)
    print("    [en vivo] " + m)


def _b64(b):
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def _asercion(variante, keyfile=None):
    now = int(time.time())
    head = _b64(json.dumps({"alg": "RS256", "typ": "JWT", "kid": KID}, separators=(",", ":")).encode())
    pl = {"aud": "https://sts.deliveryhero.io", "jti": str(uuid.uuid4()).upper(), "exp": now + 240, "iss": CLIENT_ID, "sub": CLIENT_ID}
    if variante == 1:
        pl["iat"] = now
    body = _b64(json.dumps(pl, separators=(",", ":")).encode())
    msg = (head + "." + body).encode()
    sig = subprocess.run(["openssl", "dgst", "-sha256", "-sign", keyfile or KEY_FILE], input=msg,
                         capture_output=True, check=True).stdout
    return head + "." + body + "." + _b64(sig)


def _token():
    if "token" in _MEMO:
        return _MEMO["token"]
    if _MEMO.get("token_fallo"):
        raise RuntimeError(_MEMO["token_fallo"])
    ultimo = ""
    for keyfile in KEY_FILES:
      if not os.path.exists(keyfile):
        _log("clave no accesible: " + os.path.basename(keyfile)); continue
      for variante in (0,):
        try:
            asercion = _asercion(variante, keyfile)
        except Exception as e:
            _log("no pude firmar con %s: %s" % (os.path.basename(keyfile), e)); continue
        _log("probando clave " + os.path.basename(keyfile))
        data = urllib.parse.urlencode({
            "grant_type": "client_credentials",
            "client_assertion_type": "urn:ietf:params:oauth:client-assertion-type:jwt-bearer",
            "client_assertion": asercion}).encode()
        req = urllib.request.Request(STS_URL, data=data, headers={"Content-Type": "application/x-www-form-urlencoded"})
        _log("pidiendo token al STS (formato %d)" % variante)
        try:
            with _open(req) as r:
                tok = json.loads(r.read().decode())["access_token"]
            _MEMO["token"] = tok
            _log("token STS OK")
            return tok
        except urllib.error.HTTPError as e:
            cuerpo = e.read().decode(errors="replace")[:400]
            ultimo = "STS HTTP %s: %s" % (e.code, cuerpo)
            _log(ultimo)
    _MEMO["token_fallo"] = ultimo
    raise RuntimeError(ultimo)


def _get(path, params=None):
    url = HOST + path + ("?" + urllib.parse.urlencode(params, doseq=True) if params else "")
    req = urllib.request.Request(url, headers={"Authorization": "Bearer " + _token(), "Accept": "application/json",
                                               "User-Agent": "mushdrink-dashboards/1.0 (client_id=" + CLIENT_ID + ")"})
    with _open(req) as r:
        return json.loads(r.read().decode())


def _rider_cities():
    """rider_id -> código de ciudad (ALC, GRA...) según los datos de la flota."""
    out = {}
    try:
        import csv
        with open(RIDER_CSV, encoding="utf-8-sig") as fh:
            for r in csv.DictReader(fh):
                c = (r.get("city_code") or "").strip()
                if c:
                    out[str(r.get("rider_id")).strip()] = NODE_ALIASES.get(c, c)
    except Exception as e:
        _log("no pude leer los riders de la flota: " + str(e))
    return out


def _city_ids(codigos):
    os.makedirs(CACHE_DIR, exist_ok=True)
    cache_f = os.path.join(CACHE_DIR, "city_ids.json")
    ids = {}
    try:
        ids.update(json.load(open(cache_f)))
    except Exception:
        pass
    ids.update(CITY_IDS_FIJOS)
    falta = [c for c in codigos if c not in ids]
    if falta:
        # contratos activos de los riders -> id de ciudad; se cruza con la ciudad que tiene cada rider en la flota
        rc = _rider_cities()
        votos = collections.defaultdict(collections.Counter)
        nombres = {}
        for page in range(0, 40):
            try:
                emps = _get("/api/rooster/v3/external/employees", {"page": page, "size": 200})
            except Exception as e:
                _log("lista de riders (Rooster) no disponible: " + str(e))
                break
            if isinstance(emps, dict):
                emps = emps.get("content") or []
            if not emps:
                break
            for e in emps:
                ac = e.get("active_contract") or {}
                cid = ac.get("city_id") or e.get("city_id")
                code = rc.get(str(e.get("id")))
                if cid and code:
                    votos[code][int(cid)] += 1
                    nombres[int(cid)] = ac.get("city_name") or nombres.get(int(cid))
            if len(emps) < 200:
                break
        for code, cnt in votos.items():
            if code not in ids:
                cid = cnt.most_common(1)[0][0]
                ids[code] = cid
                _log("ciudad %s -> id %s (%s)" % (code, cid, nombres.get(cid) or "?"))
        try:
            with open(cache_f, "w") as fh:
                json.dump({k: v for k, v in ids.items() if k not in CITY_IDS_FIJOS}, fh)
        except Exception:
            pass
    return ids


_PII = ("email", "phone_number")

# Posición de cada rider en la última descarga: SOLO en memoria (la usan posiciones.py y la
# pestaña WTD% para medir paradas). Nunca se escribe en la foto publicada.
_POS = {}


def _coords(loc):
    """Devuelve (lat, lng) de current_location sea cual sea su formato, o None."""
    if not isinstance(loc, dict):
        return None
    for la, lo in (("latitude", "longitude"), ("lat", "lng"), ("lat", "lon")):
        if loc.get(la) is not None and loc.get(lo) is not None:
            try:
                return float(loc[la]), float(loc[lo])
            except (TypeError, ValueError):
                return None
    for k in ("coordinates", "location", "point"):
        v = loc.get(k)
        if isinstance(v, dict):
            c = _coords(v)
            if c:
                return c
        if isinstance(v, (list, tuple)) and len(v) >= 2:      # GeoJSON: [lng, lat]
            try:
                return float(v[1]), float(v[0])
            except (TypeError, ValueError):
                return None
    return None


def _limpiar(r, code):
    r = dict(r)
    for k in _PII:
        r.pop(k, None)
    loc = r.pop("current_location", None) or {}
    r["location_updated_at"] = loc.get("location_updated_at")
    r["city"] = code
    c = _coords(loc)
    if c and r.get("employee_id") is not None:
        _POS[str(r["employee_id"])] = {"lat": c[0], "lng": c[1], "loc_at": loc.get("location_updated_at")}
    elif loc and not _MEMO.get("aviso_coords"):
        _MEMO["aviso_coords"] = True
        _log("current_location sin coordenadas reconocibles (claves: %s)" % ", ".join(sorted(loc)))
    return r


def _descargar(codigos):
    snap = {"fetched_at": dt.datetime.now(dt.timezone.utc).isoformat(), "cities": {}, "errors": []}
    ids = _city_ids(codigos)
    for code in codigos:
        cid = ids.get(code)
        if not cid:
            snap["errors"].append("%s: id de ciudad desconocido" % code)
            continue
        riders, page = [], 0
        try:
            while page < 30:
                res = _get("/api/rider-live-operations/v1/external/city/%d/riders" % cid,
                           {"page": page, "size": 100, "sort_by": "user_id", "sort_direction": "asc"})
                riders += [_limpiar(r, code) for r in (res.get("content") or [])]
                if res.get("is_last", True) or not res.get("content"):
                    break
                page += 1
        except urllib.error.HTTPError as e:
            snap["errors"].append("%s (ciudad %s): riders HTTP %s" % (code, cid, e.code))
        except Exception as e:
            snap["errors"].append("%s (ciudad %s): riders %s" % (code, cid, e))
        comp = None
        try:
            comp = _get("/api/rider-live-operations/v1/external/city/%d/companies" % cid)
        except Exception as e:
            snap["errors"].append("%s: resumen de empresas no disponible (%s)" % (code, getattr(e, "code", e)))
        mine = {}
        for co in sorted({r.get("company_id") for r in riders if r.get("company_id")}):
            try:
                mine[str(co)] = _get("/api/rider-live-operations/v1/external/city/%d/company/%d" % (cid, co))
            except Exception as e:
                snap["errors"].append("%s: detalle de la empresa %s no disponible (%s)" % (code, co, getattr(e, "code", e)))
        snap["cities"][code] = {"city_id": cid, "riders": riders, "companies": comp, "company": mine}
        _log("%s (ciudad %s): %d riders" % (code, cid, len(riders)))
    return snap


def _foto(codigos):
    """Descarga (una vez por ejecución) o, si falla, usa la última foto guardada."""
    key = ",".join(sorted(codigos))
    if key in _MEMO:
        return _MEMO[key]
    os.makedirs(CACHE_DIR, exist_ok=True)
    f = os.path.join(CACHE_DIR, "foto_" + "_".join(sorted(codigos)) + ".json")
    try:
        snap = _descargar(codigos)
        ok = any(v["riders"] or v["companies"] for v in snap["cities"].values())
        if ok:
            snap["stale"] = False
            with open(f, "w", encoding="utf-8") as fh:
                json.dump(snap, fh, ensure_ascii=False)
        else:
            raise RuntimeError("; ".join(snap["errors"]) or "sin datos")
    except Exception as e:
        _log("sin conexión con Live Operations: " + str(e))
        try:
            snap = json.load(open(f, encoding="utf-8"))
            snap["stale"] = True
            snap.setdefault("errors", []).append("Glovo no respondió en la última actualización: " + str(e)[:200])
        except Exception:
            snap = {"fetched_at": None, "cities": {}, "errors": ["Todavía no hay datos: " + str(e)[:200]], "stale": True}
    _MEMO[key] = snap
    return snap


def construir_html(cities=None, semanas=None, sello=True):
    codigos = sorted(set(NODE_ALIASES.get(c, c) for c in (cities or [])))
    snap = _foto(codigos)
    html = HTML.replace("__DATA__", json.dumps(snap, ensure_ascii=False, separators=(",", ":")))
    n = sum(len(v.get("riders") or []) for v in snap["cities"].values())
    res = ("%d riders · foto %s%s · %s" % (n, (snap.get("fetched_at") or "—")[:16].replace("T", " "),
           " (antigua)" if snap.get("stale") else "", ", ".join(codigos)))
    return html, res


_BTN = '<button data-v="envivo" aria-pressed="false">En vivo</button>'
_VIEWS = ["viewSemanal", "viewDiario", "viewLiga", "viewHeat", "viewUtr", "viewNoShow", "viewCap"]


def integrar_en_dashboard(dash_html, vivo_html):
    """Añade la pestaña 'En vivo' al selector Vista del dashboard (en un iframe aislado)."""
    if 'id="viewVivo"' in dash_html:
        return dash_html
    ancla = None
    for a in ['<button data-v="capacidad" aria-pressed="false">Capacidad</button>',
              '<button data-v="noshow" aria-pressed="false">No show</button>',
              '<button data-v="utr" aria-pressed="false">UTR</button>']:
        if a in dash_html:
            ancla = a
            break
    sec_ancla = '<div id="viewSemanal">'
    if not ancla or sec_ancla not in dash_html or "</body>" not in dash_html:
        raise ValueError("la plantilla no tiene el selector de Vista esperado")
    dash_html = dash_html.replace(ancla, ancla + "\n        " + _BTN, 1)
    dash_html = dash_html.replace(sec_ancla,
        '<section id="viewVivo" style="display:none"><iframe id="vivoFrame" title="En vivo" '
        'style="width:100%;height:1400px;border:0;display:block;background:transparent"></iframe></section>\n  '
        + sec_ancla, 1)
    src = json.dumps(vivo_html, ensure_ascii=False).replace("<", "\\u003c")
    js = ("<script>\n/* ==== Pestaña En vivo (Live Operations) ==== */\n(function(){\n"
          "  const VIVO_HTML=" + src + ";\n"
          "  const seg=document.getElementById('viewSeg'),sec=document.getElementById('viewVivo'),fr=document.getElementById('vivoFrame');\n"
          "  if(!seg||!sec||!fr) return; let loaded=false;\n"
          "  seg.querySelectorAll('button').forEach(b=>b.addEventListener('click',()=>{\n"
          "    const on=b.dataset.v==='envivo'; sec.style.display=on?'':'none';\n"
          "    if(on){ seg.querySelectorAll('button').forEach(x=>x.setAttribute('aria-pressed',String(x===b)));\n"
          "      " + json.dumps(_VIEWS) + ".forEach(id=>{const e=document.getElementById(id); if(e) e.style.display='none';});\n"
          "      if(!loaded){ fr.srcdoc=VIVO_HTML; loaded=true; } window.scrollTo(0,0); }\n"
          "  }));\n"
          "  window.addEventListener('message',e=>{ if(e.source===fr.contentWindow && e.data && e.data.vivoH){\n"
          "    fr.style.height=Math.max(700,Math.ceil(e.data.vivoH)+20)+'px'; } });\n"
          "})();\n</script>\n")
    i = dash_html.rindex("</body>")
    return dash_html[:i] + js + dash_html[i:]


HTML = '<!DOCTYPE html><html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>En vivo · riders</title>\n<style>\n:root{--bg:#F6F7F9;--surface:#FFFFFF;--line:#E4E7EC;--ink:#14171F;--ink2:#4B5563;--muted:#6B7280;--acc:#0E5A6B;--chip:#EEF1F4;\n--working:#2a78d6;--ready:#0a7f0a;--late:#d03b3b;--break:#b7791f;--starting:#6d5bd0;--ending:#7a8699;--off:#9AA1AC}\n*{box-sizing:border-box}\nbody{margin:0;background:var(--bg);color:var(--ink);font-family:"Inter",-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;font-size:14px;padding:0 0 24px}\n.wrap{display:flex;flex-direction:column;gap:16px}\nh1{font-size:18px;font-weight:650;margin:0}\nh2{font-size:12px;letter-spacing:.06em;text-transform:uppercase;font-weight:650;margin:0}\n.sub{color:var(--ink2);margin:5px 0 0;line-height:1.5;font-size:13px}\n.mono,.n{font-family:ui-monospace,"SF Mono",Menlo,Consolas,monospace;font-variant-numeric:tabular-nums}\n.banner{border-radius:8px;padding:9px 12px;font-size:13px}\n.banner.warn{background:#FFF7E6;border:1px solid #F5D9A8;color:#7A5200}\n.banner[hidden]{display:none}\n.filters{background:var(--surface);border:1px solid var(--line);border-radius:12px;padding:14px 16px;display:flex;flex-wrap:wrap;gap:16px;align-items:flex-end}\n.fg{display:flex;flex-direction:column;gap:6px}.fg[hidden]{display:none}\n.fg>span{font-family:ui-monospace,"SF Mono",Menlo,monospace;font-size:11px;letter-spacing:.07em;text-transform:uppercase;color:var(--muted)}\n.seg{display:inline-flex;flex-wrap:wrap;background:var(--bg);border:1px solid var(--line);border-radius:9px;padding:3px;gap:2px}\n.seg button{font:inherit;font-size:13px;border:0;background:transparent;color:var(--ink2);border-radius:7px;padding:6px 11px;cursor:pointer}\n.seg button:hover{color:var(--ink)}.seg button.on{background:var(--acc);color:#fff}\n.seg button .c{font-family:ui-monospace,monospace;font-size:11px;opacity:.75;margin-left:5px}\ninput[type=search]{font:inherit;font-size:13px;padding:7px 11px;border:1px solid var(--line);border-radius:8px;width:220px;background:var(--surface);color:var(--ink)}\n.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px}\n.kpi{background:var(--surface);border:1px solid var(--line);border-radius:12px;padding:12px 14px;display:flex;flex-direction:column;gap:4px}\n.kpi b{font-size:22px;font-weight:650;font-family:ui-monospace,"SF Mono",Menlo,monospace;font-variant-numeric:tabular-nums}\n.kpi span{font-size:12px;color:var(--ink2)}\n.kpi b span{font-size:inherit}\n.kpi b span.bad{color:var(--late)}\n.kpi em{font-style:normal;font-family:ui-monospace,"SF Mono",Menlo,monospace;font-size:11px;letter-spacing:.06em;text-transform:uppercase;color:var(--muted)}\n.bad{color:var(--late)}\n.panel{background:var(--surface);border:1px solid var(--line);border-radius:12px;padding:14px;display:flex;flex-direction:column;gap:10px;min-width:0}\n.ph{display:flex;justify-content:space-between;gap:10px;flex-wrap:wrap;align-items:baseline}.ph p{margin:0;color:var(--ink2);font-size:12.5px}\n.stack{display:flex;height:22px;border-radius:6px;overflow:hidden;background:var(--chip)}\n.stack i{display:block;height:100%}\n.legend{display:flex;flex-wrap:wrap;gap:12px;color:var(--ink2);font-size:12px}\n.legend i{display:inline-block;width:10px;height:10px;border-radius:3px;margin-right:6px;vertical-align:middle}\n.cgrid{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:12px}\n.ccard{border:1px solid var(--line);border-radius:10px;padding:12px;display:flex;flex-direction:column;gap:8px}\n.ccard h3{margin:0;font-size:14px;font-weight:650}\n.kv{display:grid;grid-template-columns:1fr auto;gap:4px 12px;font-size:13px}.kv span{color:var(--ink2)}.kv b{font-weight:600;font-family:ui-monospace,monospace;font-variant-numeric:tabular-nums;text-align:right}\n.tw{overflow-x:auto}\ntable{border-collapse:collapse;width:100%}\nth,td{padding:7px 9px;text-align:left;border-bottom:1px solid var(--line);white-space:nowrap;font-size:13px}\nth{font-family:ui-monospace,"SF Mono",Menlo,monospace;font-size:10.5px;letter-spacing:.05em;text-transform:uppercase;color:var(--muted);font-weight:500;cursor:pointer;position:sticky;top:0;background:var(--surface)}\nth .arw{margin-left:4px}\ntd.n,th.n{text-align:right}\ntbody tr:hover td{background:var(--chip)}\n.pill{display:inline-flex;align-items:center;gap:6px;padding:2px 9px;border-radius:99px;font-size:12px;background:var(--chip)}\n.pill i{width:8px;height:8px;border-radius:50%;display:inline-block}\n.muted{color:var(--muted)}\n.empty{color:var(--muted);padding:16px 0}\n.note{color:var(--muted);font-size:12px;line-height:1.55;margin:0}\n[data-def]{cursor:help}\n.kpi em[data-def],h2[data-def],th[data-def]{text-decoration:underline dotted;text-underline-offset:3px}\n#defTip{position:fixed;z-index:50;max-width:300px;background:#14171F;color:#fff;font-size:12px;line-height:1.45;padding:8px 10px;border-radius:7px;pointer-events:none;box-shadow:0 4px 14px rgba(0,0,0,.18);text-transform:none;letter-spacing:0;font-weight:400}\n#defTip[hidden]{display:none}\n.tcount{color:var(--muted);font-size:11.5px}\n</style></head><body>\n<div class="wrap">\n  <header><h1>En vivo · riders en tiempo real</h1>\n    <p class="sub" id="sub"></p></header>\n  <div class="banner warn" id="banner" hidden></div>\n  <div class="filters">\n    <div class="fg" id="fgCity"><span>Ciudad</span><div class="seg" id="fCity"></div></div>\n    <div class="fg"><span>Estado</span><div class="seg" id="fSt"></div></div>\n    <div class="fg"><span>Buscar</span><input type="search" id="fQ" placeholder="Nombre o ID de rider" aria-label="Buscar rider"></div>\n  </div>\n  <section class="kpis" id="kpis"></section>\n  <section class="panel"><div class="ph"><h2 data-def="Reparto de los riders por estado en el momento de la foto (ciudad y búsqueda aplicadas).">Riders por estado</h2><p id="stSub"></p></div>\n    <div class="stack" id="stBar"></div><div class="legend" id="stLeg"></div></section>\n  <section class="panel"><div class="ph"><h2 data-def="Resumen que da Glovo para tu empresa en cada ciudad: fichajes, pedidos aceptados y rechazados, UTR, reasignaciones y riders por vehículo.">Resumen de la empresa</h2><p>Según Glovo · por ciudad</p></div>\n    <div class="cgrid" id="comp"></div></section>\n  <section class="panel"><div class="ph"><h2 data-def="Una fila por rider con todo lo que devuelve Live Operations, salvo teléfono, email y coordenadas GPS (los links son públicos). Clic en una columna para ordenar.">Riders</h2><p class="tcount" id="rCount"></p></div>\n    <div class="tw" style="max-height:900px"><table id="tR"></table></div></section>\n  <p class="note">Datos de la Live Operations API de Glovo (v1). La foto se toma en cada actualización del dashboard (cada hora); el estado real cambia minuto a minuto. No se publican teléfono, email ni posición GPS de los riders porque estos links son públicos.</p>\n</div>\n<script>\nconst SNAP=__DATA__;\nconst ST={working:[\'Trabajando\',\'var(--working)\'],ready:[\'Listo\',\'var(--ready)\'],available:[\'Disponible\',\'var(--ready)\'],late:[\'Con retraso\',\'var(--late)\'],break:[\'En pausa\',\'var(--break)\'],starting:[\'Empezando\',\'var(--starting)\'],ending:[\'Terminando\',\'var(--ending)\'],temp_not_working:[\'Parado temporalmente\',\'var(--off)\'],not_working:[\'No trabajando\',\'var(--off)\']};\nconst ORDER=[\'working\',\'ready\',\'available\',\'starting\',\'late\',\'break\',\'ending\',\'temp_not_working\',\'not_working\'];\nconst $=id=>document.getElementById(id);\nconst nf=(v,d=0)=>v==null||isNaN(v)?\'—\':Number(v).toLocaleString(\'es-ES\',{minimumFractionDigits:d,maximumFractionDigits:d});\nconst pct=v=>v==null||isNaN(v)?\'—\':nf(v<=1?v*100:v,1)+\' %\';\nconst tz={timeZone:\'Europe/Madrid\'};\nconst hhmm=s=>{if(!s)return \'—\';const d=new Date(s);return isNaN(d)?\'—\':d.toLocaleTimeString(\'es-ES\',{...tz,hour:\'2-digit\',minute:\'2-digit\'});};\nconst dmhm=s=>{if(!s)return \'—\';const d=new Date(s);return isNaN(d)?\'—\':d.toLocaleString(\'es-ES\',{...tz,day:\'2-digit\',month:\'2-digit\',hour:\'2-digit\',minute:\'2-digit\'});};\nconst hm=sec=>sec==null?\'—\':(sec>=3600?Math.floor(sec/3600)+\' h \'+String(Math.round(sec%3600/60)).padStart(2,\'0\')+\' min\':Math.round(sec/60)+\' min\');\nconst esc=s=>String(s??\'\').replace(/[&<>"]/g,c=>({\'&\':\'&amp;\',\'<\':\'&lt;\',\'>\':\'&gt;\',\'"\':\'&quot;\'}[c]));\nconst CITIES=Object.keys(SNAP.cities||{}).sort();\nconst ALL=CITIES.flatMap(c=>SNAP.cities[c].riders||[]);\nconst S={city:\'ALL\',st:\'ALL\',q:\'\',sort:\'status\',dir:1};\nif(CITIES.length<2)$(\'fgCity\').hidden=true;\n$(\'sub\').textContent=SNAP.fetched_at?(\'Foto del \'+dmhm(SNAP.fetched_at)+\' (hora de Madrid) · \'+ALL.length+\' riders en \'+CITIES.length+\' ciudad\'+(CITIES.length===1?\'\':\'es\')):\'Todavía no hay datos de Live Operations.\';\nconst errs=(SNAP.errors||[]);\nif(SNAP.stale||errs.length){$(\'banner\').hidden=false;$(\'banner\').textContent=(SNAP.stale?\'Glovo no respondió en la última actualización: se muestra la última foto disponible. \':\'\')+(errs.length?\'Avisos: \'+errs.join(\' · \'):\'\');}\nfunction seg(id,opts,val,on){const el=$(id);el.innerHTML=opts.map(o=>`<button data-v="${o.v}" class="${String(o.v)===String(val)?\'on\':\'\'}">${o.l}${o.c!=null?`<span class="c">${o.c}</span>`:\'\'}</button>`).join(\'\');el.onclick=e=>{const b=e.target.closest(\'button\');if(b)on(b.dataset.v);};}\nconst baseRows=()=>ALL.filter(r=>(S.city===\'ALL\'||r.city===S.city)&&(!S.q||String(r.name||\'\').toLowerCase().includes(S.q)||String(r.employee_id).includes(S.q)));\nconst COLS=[\n {k:\'employee_id\',h:\'ID\',n:1,v:r=>r.employee_id,f:r=>r.employee_id,d:\'ID del rider en Glovo (employee_id).\'},\n {k:\'name\',h:\'Rider\',v:r=>r.name||\'\',f:r=>esc(r.name),d:\'Nombre del rider en Glovo.\'},\n {k:\'city\',h:\'Ciudad\',v:r=>r.city,f:r=>r.city,d:\'Ciudad del dashboard.\'},\n {k:\'status\',h:\'Estado\',v:r=>ORDER.indexOf(r.status)<0?99:ORDER.indexOf(r.status),f:r=>{const s=ST[r.status]||[r.status||\'—\',\'var(--off)\'];return `<span class="pill"><i style="background:${s[1]}"></i>${esc(s[0])}</span>`;},d:\'Estado en tiempo real: trabajando (con pedido o en ruta), listo o disponible (esperando pedido), con retraso (no se ha conectado a la hora de su turno), en pausa, empezando o terminando el turno, parado temporalmente o no trabajando.\'},\n {k:\'reason\',h:\'Motivo\',v:r=>(r.status_metadata||{}).reason||\'\',f:r=>esc((r.status_metadata||{}).reason||\'—\'),d:\'Motivo del estado actual, si Glovo lo informa (y quién lo cambió).\'},\n {k:\'sp\',h:\'Punto de inicio\',v:r=>(r.starting_point||{}).name||\'\',f:r=>esc((r.starting_point||{}).name||\'—\'),d:\'Punto de inicio (starting point) del rider.\'},\n {k:\'zone\',h:\'Zona\',v:r=>(r.zone||{}).name||\'\',f:r=>esc((r.zone||{}).name||\'—\'),d:\'Zona en la que está operando.\'},\n {k:\'veh\',h:\'Vehículo\',v:r=>(r.vehicle||{}).name||\'\',f:r=>esc((r.vehicle||{}).name||\'—\'),d:\'Vehículo con el que ha empezado el turno.\'},\n {k:\'ss\',h:\'Inicio turno\',v:r=>r.active_shift_started_at||\'\',f:r=>hhmm(r.active_shift_started_at),d:\'Hora de inicio del turno activo (hora de Madrid).\'},\n {k:\'se\',h:\'Fin turno\',v:r=>r.active_shift_ended_at||\'\',f:r=>hhmm(r.active_shift_ended_at),d:\'Hora de fin del turno activo (hora de Madrid).\'},\n {k:\'act\',h:\'Pedido activo\',v:r=>actv(r)?1:0,f:r=>{const n=((r.deliveries_info||{}).active_delivery_ids||[]).length;return actv(r)?(\'Sí\'+(n>1?` (${n})`:\'\')):\'No\';},d:\'Si ahora mismo lleva algún pedido (entre paréntesis, cuántos si son varios).\'},\n {k:\'notif\',h:\'Notificados\',n:1,v:r=>(r.deliveries_info||{}).notified_deliveries_count,f:r=>nf((r.deliveries_info||{}).notified_deliveries_count),d:\'Pedidos que Glovo le ha ofrecido (notificado).\'},\n {k:\'comp\',h:\'Completadas\',n:1,v:r=>(r.deliveries_info||{}).completed_deliveries_count,f:r=>nf((r.deliveries_info||{}).completed_deliveries_count),d:\'Entregas completadas en el turno o el día (según Glovo).\'},\n {k:\'canc\',h:\'Canceladas\',n:1,v:r=>(r.deliveries_info||{}).cancelled_deliveries_count,f:r=>nf((r.deliveries_info||{}).cancelled_deliveries_count),d:\'Entregas canceladas.\'},\n {k:\'acc\',h:\'Aceptadas\',n:1,v:r=>(r.deliveries_info||{}).accepted_deliveries_count,f:r=>nf((r.deliveries_info||{}).accepted_deliveries_count),d:\'Pedidos aceptados.\'},\n {k:\'utr\',h:\'UTR\',n:1,v:r=>(r.performance||{}).utilization_rate,f:r=>nf((r.performance||{}).utilization_rate,2),d:\'Utilization rate: entregas por hora trabajada, según Glovo.\'},\n {k:\'ar\',h:\'Aceptación\',n:1,v:r=>(r.performance||{}).acceptance_rate,f:r=>pct((r.performance||{}).acceptance_rate),d:\'Tasa de aceptación de pedidos ofrecidos.\'},\n {k:\'rr\',h:\'Reasignación\',n:1,v:r=>(r.performance||{}).reassignment_rate,f:r=>pct((r.performance||{}).reassignment_rate),d:\'Tasa de pedidos reasignados a otro rider.\'},\n {k:\'wk\',h:\'Trabajado\',n:1,v:r=>((r.performance||{}).time_spent||{}).worked_seconds,f:r=>hm(((r.performance||{}).time_spent||{}).worked_seconds),d:\'Tiempo trabajado.\'},\n {k:\'lt\',h:\'Retraso\',n:1,v:r=>((r.performance||{}).time_spent||{}).late_seconds,f:r=>{const s=((r.performance||{}).time_spent||{}).late_seconds;return s?`<span class="bad">${hm(s)}</span>`:hm(s);},d:\'Tiempo de retraso acumulado.\'},\n {k:\'br\',h:\'Pausas\',n:1,v:r=>((r.performance||{}).time_spent||{}).break_seconds,f:r=>{const t=(r.performance||{}).time_spent||{};return hm(t.break_seconds)+(t.number_of_breaks?` (${t.number_of_breaks})`:\'\');},d:\'Tiempo en pausa y número de pausas.\'},\n {k:\'wal\',h:\'Monedero\',n:1,v:r=>(r.wallet_info||{}).balance,f:r=>nf((r.wallet_info||{}).balance,2)+\' €\',d:\'Saldo del monedero (efectivo cobrado pendiente de liquidar).\'},\n {k:\'wls\',h:\'Límite monedero\',v:r=>(r.wallet_info||{}).limit_status||\'\',f:r=>{const s=(r.wallet_info||{}).limit_status||\'—\';return /hard|over|above/i.test(s)?`<span class="bad">${esc(s)}</span>`:esc(s);},d:\'Situación del saldo frente a los límites del monedero.\'},\n {k:\'loc\',h:\'Ubicación actualizada\',v:r=>r.location_updated_at||\'\',f:r=>hhmm(r.location_updated_at),d:\'Última actualización de la ubicación (se refresca cada ~5 min). Las coordenadas no se publican.\'},\n];\nconst actv=r=>{const d=r.deliveries_info||{};return !!(d.has_active_deliveries||d.has_active_delivery||(d.active_delivery_ids||[]).length);};\nconst avg=(rs,f)=>{const v=rs.map(f).filter(x=>x!=null&&!isNaN(x));return v.length?v.reduce((a,b)=>a+b,0)/v.length:null;};\nconst sum=(rs,f)=>rs.reduce((a,r)=>a+(Number(f(r))||0),0);\nfunction render(){\n  const cityRows=ALL.filter(r=>S.city===\'ALL\'||r.city===S.city);\n  seg(\'fCity\',[{v:\'ALL\',l:\'Todas\',c:ALL.length}].concat(CITIES.map(c=>({v:c,l:c,c:(SNAP.cities[c].riders||[]).length}))),S.city,v=>{S.city=v;render();});\n  const cnt=collections(cityRows);\n  seg(\'fSt\',[{v:\'ALL\',l:\'Todos\',c:cityRows.length}].concat(ORDER.filter(s=>cnt[s]).map(s=>({v:s,l:ST[s][0],c:cnt[s]}))),S.st,v=>{S.st=v;render();});\n  const base=baseRows();const rows=base.filter(r=>S.st===\'ALL\'||r.status===S.st);\n  const on=base.filter(r=>r.status&&r.status!==\'not_working\');\n  const c=collections(base);\n  $(\'kpis\').innerHTML=[\n   [\'Conectados\',nf(on.length),\'de \'+nf(base.length)+\' riders\',\'Riders en cualquier estado salvo «no trabajando».\'],\n   [\'Trabajando\',nf(c.working||0),\'con pedido o en ruta\',\'Riders en estado «working».\'],\n   [\'Esperando pedido\',nf((c.ready||0)+(c.available||0)),\'listos o disponibles\',\'Riders conectados sin pedido: estados «ready» y «available».\'],\n   [\'Con retraso\',`<span class="${c.late?\'bad\':\'\'}">${nf(c.late||0)}</span>`,\'no conectados a su hora\',\'Riders con turno empezado que aún no se han conectado (estado «late»).\'],\n   [\'En pausa\',nf(c.break||0),\'\',\'Riders en pausa.\'],\n   [\'Pedidos activos\',nf(base.filter(actv).length),\'riders con un pedido ahora\',\'Riders que llevan al menos un pedido en este momento.\'],\n   [\'Entregas completadas\',nf(sum(base,r=>(r.deliveries_info||{}).completed_deliveries_count)),\'canceladas: \'+nf(sum(base,r=>(r.deliveries_info||{}).cancelled_deliveries_count)),\'Suma de entregas completadas de los riders mostrados.\'],\n   [\'UTR medio\',nf(avg(on,r=>(r.performance||{}).utilization_rate),2),\'aceptación \'+pct(avg(on,r=>(r.performance||{}).acceptance_rate)),\'Media del UTR (entregas por hora) de los riders conectados.\'],\n   [\'Reasignación media\',pct(avg(on,r=>(r.performance||{}).reassignment_rate)),\'riders conectados\',\'Media de la tasa de reasignación de los riders conectados.\'],\n  ].map(([e,b,s,d])=>`<div class="kpi"><em data-def="${esc(d)}" tabindex="0">${e}</em><b>${b}</b><span>${s}</span></div>`).join(\'\');\n  const tot=base.length||1;\n  $(\'stBar\').innerHTML=ORDER.filter(s=>c[s]).map(s=>`<i style="width:${c[s]/tot*100}%;background:${ST[s][1]}" title="${ST[s][0]}: ${c[s]}"></i>`).join(\'\');\n  $(\'stLeg\').innerHTML=ORDER.filter(s=>c[s]).map(s=>`<span><i style="background:${ST[s][1]}"></i>${ST[s][0]} · ${c[s]}</span>`).join(\'\')||\'<span class="muted">Sin riders</span>\';\n  $(\'stSub\').textContent=nf(base.length)+\' riders\';\n  const cs=S.city===\'ALL\'?CITIES:[S.city];\n  $(\'comp\').innerHTML=cs.map(ct=>{const C=SNAP.cities[ct]||{};const mine=Object.values(C.company||{})[0]||C.companies;if(!mine)return `<div class="ccard"><h3>${ct}</h3><span class="muted">Sin resumen de empresa</span></div>`;\n    const w=mine.workers||{},o=mine.orders||{},v=mine.workers_per_vehicle||{};\n    return `<div class="ccard"><h3>${ct} <span class="muted" style="font-weight:400;font-size:12px">ciudad ${C.city_id}</span></h3><div class="kv">\n     <span data-def="Riders que han fichado (conectado) su turno.">Fichados</span><b>${nf(w.checked_in)}</b>\n     <span data-def="Riders que han fichado tarde.">Fichados tarde</span><b class="${w.checked_in_late?\'bad\':\'\'}">${nf(w.checked_in_late)}</b>\n     <span data-def="Riders con turno que no han fichado.">Sin fichar</span><b class="${w.not_checked_in?\'bad\':\'\'}">${nf(w.not_checked_in)}</b>\n     <span data-def="Riders con retraso ahora.">Con retraso</span><b>${nf(mine.late_workers)}</b>\n     <span data-def="Pedidos aceptados por tus riders.">Pedidos aceptados</span><b>${nf(o.accepted)}</b>\n     <span data-def="Pedidos rechazados por tus riders.">Pedidos rechazados</span><b>${nf(o.declined)}</b>\n     <span data-def="UTR de la empresa: entregas por hora trabajada.">UTR</span><b>${nf(mine.utilization_rate,2)}</b>\n     <span data-def="Tasa de reasignación de la empresa.">Reasignación</span><b>${pct(mine.reassignment_rate)}</b>\n     <span data-def="Riders en pausa ahora.">En pausa</span><b>${nf(w.workers_on_break)}</b>\n     ${(Array.isArray(v)?v.map(x=>[((x.vehicle||{}).profile||(x.vehicle||{}).name||\'?\'),x.total_workers]):Object.entries(v)).map(([k,x])=>`<span>Riders en ${esc(k)}</span><b>${nf(x)}</b>`).join(\'\')}\n    </div></div>`;}).join(\'\');\n  const col=COLS.find(x=>x.k===S.sort)||COLS[3];\n  const sorted=rows.slice().sort((a,b)=>{const x=col.v(a),y=col.v(b);if(x==null||x===\'\')return 1;if(y==null||y===\'\')return -1;return (typeof x===\'string\'?x.localeCompare(y,\'es\'):x-y)*S.dir;});\n  $(\'tR\').innerHTML=!sorted.length?\'<tbody><tr><td class="empty">Ningún rider con estos filtros.</td></tr></tbody>\':\n   \'<thead><tr>\'+COLS.map(x=>`<th class="${x.n?\'n\':\'\'}" data-k="${x.k}" data-def="${esc(x.d)}">${x.h}${S.sort===x.k?`<span class="arw">${S.dir<0?\'▼\':\'▲\'}</span>`:\'\'}</th>`).join(\'\')+\'</tr></thead><tbody>\'+\n   sorted.map(r=>\'<tr>\'+COLS.map(x=>`<td class="${x.n?\'n\':\'\'}">${x.f(r)}</td>`).join(\'\')+\'</tr>\').join(\'\')+\'</tbody>\';\n  $(\'tR\').querySelectorAll(\'th[data-k]\').forEach(th=>th.onclick=()=>{const k=th.dataset.k;if(S.sort===k)S.dir*=-1;else{S.sort=k;const cc=COLS.find(x=>x.k===k);S.dir=cc.n?-1:1;}render();});\n  $(\'rCount\').textContent=nf(sorted.length)+\' de \'+nf(ALL.length)+\' riders\';\n}\nfunction collections(rs){const o={};rs.forEach(r=>{o[r.status]=(o[r.status]||0)+1;});return o;}\nlet qT;$(\'fQ\').addEventListener(\'input\',e=>{clearTimeout(qT);qT=setTimeout(()=>{S.q=e.target.value.trim().toLowerCase();render();},150);});\n(function(){const tip=document.createElement(\'div\');tip.id=\'defTip\';tip.hidden=true;document.body.appendChild(tip);\n  const place=(x,y)=>{const w=tip.offsetWidth,h=tip.offsetHeight;let l=x+12,t=y+14;if(l+w>innerWidth-8)l=Math.max(8,x-w-12);if(t+h>innerHeight-8)t=Math.max(8,y-h-12);tip.style.left=l+\'px\';tip.style.top=t+\'px\';};\n  document.addEventListener(\'mouseover\',e=>{const el=e.target.closest(\'[data-def]\');if(el){tip.textContent=el.dataset.def;tip.hidden=false;place(e.clientX,e.clientY);}});\n  document.addEventListener(\'mousemove\',e=>{if(!tip.hidden&&e.target.closest(\'[data-def]\'))place(e.clientX,e.clientY);});\n  document.addEventListener(\'mouseout\',e=>{const el=e.target.closest(\'[data-def]\');if(el&&!el.contains(e.relatedTarget))tip.hidden=true;});})();\nrender();\nif(window.parent!==window){const send=()=>window.parent.postMessage({vivoH:document.body.getBoundingClientRect().height},\'*\');\n  if(window.ResizeObserver) new ResizeObserver(send).observe(document.body); send();}\n</script></body></html>\n'
