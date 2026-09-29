#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
================================================================================
 Mapas de calor de REASIGNACIONES (buckets GCP de Glovo · mushdrink)
================================================================================

 Que hace:
   1. Descarga del bucket de Google Cloud SOLO los dias nuevos
      (usa la sesion de gcloud que ya activaste; NO lee tu clave .json).
   2. Lee todos los reassignment_lv.csv (+ la ubicacion del restaurante
      desde delivery_lv.csv).
   3. Genera un dashboard HTML con 5 mapas de calor:
        - Hora del dia x dia de la semana
        - Zona x semana
        - Restaurante x semana
        - Rider x motivo
        - Mapa real (ubicacion del restaurante)
      con filtros de ciudad, motivo, semana y "realizado por".

 USO (en la Terminal):
   python3 ~/Downloads/heatmaps_reasignaciones.py

 Salida:
   ~/Downloads/dashboards/heatmaps_reasignaciones.html
================================================================================
"""

import os
import re
import sys
import glob
import json
import datetime
import subprocess

# ==============================================================================
#  CONFIGURACION
# ==============================================================================

BUCKET      = "gs://dhub-glovo-es-external-fleet-mushdrink"
# Datos del bucket: usa la carpeta que ya mantiene al dia extraer_datos_fleet.py (fleet_data);
# si no existe, la de la descarga manual con gcloud (mushdrink_raw).
_FLEET = os.path.expanduser("~/Downloads/fleet_data")
RAW_DIR     = os.environ.get("MUSHDRINK_RAW") or (_FLEET if os.path.isdir(_FLEET) else os.path.expanduser("~/Downloads/mushdrink_raw"))
OUTPUT_DIR  = os.environ.get("MUSHDRINK_OUT", os.path.expanduser("~/Downloads/dashboards"))
OUTPUT_FILE = "heatmaps_reasignaciones.html"

DESCARGAR      = True          # False = no conecta al bucket, usa lo ya descargado
WEEKS_TO_SHOW  = 12            # semanas ISO mas recientes que entran en el dashboard
NODE_ALIASES   = {"NEM": "MAD"}

# ------------------------------------------------------------------------------
#  GUIA DE MOTIVOS (puedes editar los textos libremente)
#   es     = nombre en español
#   fam    = familia: Rider | Recogida | Pedido | Sistema | Sin clasificar
#   que    = que significa
#   accion = que hacer
#   conf   = "alta"  -> el significado se deduce claramente del nombre
#            "media" -> interpretacion razonable
#            "baja"  -> significado NO confirmado: preguntar a Glovo
# ------------------------------------------------------------------------------
REASON_INFO = {
    "PickupIdleOrder": dict(
        es="Pedido parado en recogida", fam="Recogida", conf="media",
        que="El sistema de Glovo detecta que el pedido lleva demasiado tiempo sin avanzar en la "
            "fase de recogida (el rider no llega al local o no lo recoge) y lo reasigna solo, sin agente.",
        accion="Mira la pestaña Restaurante: si se repiten los mismos locales, son esperas en cocina. "
               "Si se repiten los mismos riders (Rider × motivo), es un problema del rider."),
    "Order Issues": dict(
        es="Incidencia del pedido", fam="Pedido", conf="media",
        que="Hay un problema con el propio pedido (producto, pago, dirección, cambios del cliente…) "
            "que obliga a reasignarlo. Suele venir sin dato de quién lo reasignó.",
        accion="Si se concentra en pocos restaurantes, coméntalo con Glovo: no suele depender del rider."),
    "SENT": dict(
        es="SENT (sin detalle)", fam="Sin clasificar", conf="baja",
        que="Parece un estado técnico («enviado») más que un motivo real. Glovo no da más detalle.",
        accion="Úsalo solo como volumen. Pregunta a Glovo qué significa para poder actuar."),
    "Equipment Issue": dict(
        es="Problema de equipo", fam="Rider", conf="media",
        que="El rider no puede hacer el pedido por un problema de su equipo (mochila, vehículo, móvil…).",
        accion="Revisa qué riders lo acumulan y si necesitan material o reparar el vehículo."),
    "": dict(
        es="(sin motivo)", fam="Sin clasificar", conf="alta",
        que="Glovo no registró ningún motivo para esta reasignación.",
        accion="Solo sirve como volumen. Si crece mucho, coméntalo con Glovo."),
    "Rider - Not accepting": dict(
        es="Rider no acepta", fam="Rider", conf="alta",
        que="El rider rechaza el pedido y un agente de soporte lo reasigna a otro.",
        accion="Busca riders reincidentes en Rider × motivo y habla con ellos: afecta a tu tasa de reasignación."),
    "Order - Special vehicle/equipment needed": dict(
        es="Pedido requiere vehículo/equipo especial", fam="Pedido", conf="alta",
        que="El pedido es demasiado grande o pesado, o necesita un equipo que el rider asignado no tiene.",
        accion="Si se concentra en pocos restaurantes, avisa a Glovo para que asignen el vehículo correcto."),
    "CHANNEL_INACTIVE": dict(
        es="Canal inactivo", fam="Sistema", conf="baja",
        que="Probablemente, el canal de comunicación con el rider (app/notificaciones) estaba inactivo y "
            "no se le pudo avisar.",
        accion="Si un rider lo acumula, revisa su app y permisos de notificación. Confirma el significado con Glovo."),
    "DispatchDeliveryNotSeen": dict(
        es="No visto", fam="Rider", conf="alta",
        que="Se avisó al rider del pedido pero no llegó a abrir la notificación a tiempo.",
        accion="Riders con muchos casos: móvil en silencio, app en segundo plano o desconexiones. Habla con ellos."),
    "Rider - Vehicle/Equipment/Phone issue": dict(
        es="Rider · problema vehículo/equipo/móvil", fam="Rider", conf="alta",
        que="El rider informa a soporte de una avería (vehículo, equipo o móvil) durante el pedido.",
        accion="Revisa riders reincidentes: puede hacer falta revisar su vehículo o su móvil."),
    "DispatchDeliveryIgnored": dict(
        es="Ignorado", fam="Rider", conf="alta",
        que="El rider vio el aviso del pedido pero no respondió (ni aceptó ni rechazó).",
        accion="Riders reincidentes: es la señal más clara de baja implicación. Habla con ellos."),
    "NO_CHANNEL": dict(
        es="Sin canal", fam="Sistema", conf="baja",
        que="Probablemente, no había ningún canal para avisar al rider (app sin conexión o sin sesión).",
        accion="Si un rider lo acumula, revisa su conexión y su sesión en la app. Confirma el significado con Glovo."),
    "PERMANENT_ERROR": dict(
        es="Error permanente", fam="Sistema", conf="baja",
        que="Probablemente, un error técnico al enviar el pedido al rider que no se pudo reintentar.",
        accion="Normalmente fuera de tu control. Si aparecen picos, coméntalo con Glovo."),
    "System - Delivery not in rider's zone/area": dict(
        es="Sistema · fuera de la zona del rider", fam="Sistema", conf="alta",
        que="El pedido se asignó a un rider que no trabaja en esa zona y se reasignó.",
        accion="Si se repite en una zona, pide a Glovo que revise la configuración de zonas."),
    "Rider - Accident": dict(
        es="Rider · accidente", fam="Rider", conf="alta",
        que="El rider sufrió un accidente durante el pedido.",
        accion="Contacta con el rider. Si se repite en un punto del mapa, puede ser un tramo peligroso."),
    "Rider - Not moving towards Pickup/Dropoff and Not Reachable": dict(
        es="Rider · no avanza y no localizable", fam="Rider", conf="alta",
        que="El rider no se mueve hacia el local ni hacia el cliente y soporte no consigue contactar con él.",
        accion="Caso grave: habla con los riders que aparezcan aquí."),
    "System - Distance to pickup/dropoff too far - not willing to proceed": dict(
        es="Distancia excesiva, rider no continúa", fam="Sistema", conf="alta",
        que="La distancia al local o al cliente es demasiado grande y el rider no quiere seguir.",
        accion="Si se repite en una zona, coméntalo con Glovo: la asignación está mandando riders demasiado lejos."),
    "Rider - Break request": dict(
        es="Rider · pide pausa", fam="Rider", conf="alta",
        que="El rider pide una pausa con un pedido ya asignado.",
        accion="Revisa la planificación de pausas en los turnos largos."),
    "Vendor - Late preparation, additional 15 min needed": dict(
        es="Restaurante · preparación tardía", fam="Pedido", conf="alta",
        que="El restaurante necesita al menos 15 minutos más para preparar el pedido.",
        accion="Mira qué restaurantes se repiten y coméntalo con Glovo."),
}

FAMILIAS = {
    "Rider": dict(
        color="#3B8FD9", desc="La causa está en el rider: no ve, ignora o rechaza el pedido, o tiene un problema.",
        tips=dict(
            hora="Picos al final de los turnos o a última hora suelen indicar cansancio o riders desconectándose.",
            zona="Si una zona destaca, revisa si los riders de esa zona tienen turnos muy largos o están lejos de su base.",
            rest="El restaurante no suele ser la causa en este grupo. Usa mejor la vista Rider × motivo.",
            rider="Es la vista clave para este grupo: los riders de arriba son los reincidentes con los que hablar.",
            mapa="Si hay una concentración clara, puede ser un área con mala cobertura o de difícil acceso.")),
    "Recogida": dict(
        color="#D08A1E", desc="El pedido se queda atascado antes de la recogida. Puede ser el rider o la cocina.",
        tips=dict(
            hora="Si se concentra en 13–15h y 20–22h, apunta a saturación: cocinas lentas o pocos riders en los picos.",
            zona="Las zonas que suben semana a semana suelen tener locales lentos o pocos riders.",
            rest="Es la vista clave: los locales que se repiten cada semana generan esperas largas.",
            rider="Si pocos riders acumulan muchos casos, el problema es del rider (no llega o no recoge).",
            mapa="Los círculos grandes son locales donde los pedidos se quedan parados. Revisa las esperas en ellos.")),
    "Pedido": dict(
        color="#9B5DE5", desc="El problema está en el pedido o en el restaurante (tamaño, preparación, incidencias).",
        tips=dict(
            hora="Coincide con los picos de comida y cena si la causa es la saturación de las cocinas.",
            zona="Mira si una zona concentra locales problemáticos.",
            rest="Es la vista clave: identifica los locales que repiten y coméntalo con Glovo.",
            rider="No suele depender del rider. Si uno destaca, puede estar asignado siempre a los mismos locales.",
            mapa="Muestra en qué locales se concentran estas incidencias.")),
    "Sistema": dict(
        color="#7A8494", desc="Fallos técnicos o de asignación de Glovo. Normalmente, fuera de tu control.",
        tips=dict(
            hora="Un pico aislado en una hora concreta suele ser una incidencia técnica puntual de Glovo.",
            zona="Si se repite en una zona, puede ser la configuración de zonas. Coméntalo con Glovo.",
            rest="Normalmente no depende del restaurante.",
            rider="Si un mismo rider acumula muchos, revisa su app y su móvil (versión, permisos, notificaciones).",
            mapa="Poco informativo para este grupo.")),
    "Sin clasificar": dict(
        color="#8C95A1", desc="Motivos sin detalle o de significado no confirmado.",
        tips=dict(
            hora="Úsalo para ver volumen. Sin saber el motivo, no se puede concluir la causa.",
            zona="Úsalo para ver volumen por zona.",
            rest="Úsalo para ver volumen por local.",
            rider="Úsalo para ver volumen por rider.",
            mapa="Úsalo para ver volumen en el mapa.")),
}

PERF_INFO = {
    "": ("(sin dato)", "Glovo no registró quién hizo la reasignación."),
    "issue_service": ("Sistema automático", "La reasignó el sistema de Glovo sin intervención humana (p. ej., pedido parado)."),
    "Agent": ("Agente de soporte", "La reasignó a mano un operador de soporte de Glovo, normalmente tras hablar con el rider."),
    "event_bus_consumer": ("Sistema (eventos)", "Reasignación automática disparada por un evento técnico del sistema."),
}

# ==============================================================================
#  A partir de aqui NO necesitas tocar nada.
# ==============================================================================


def err(m):
    print("\nERROR: " + m + "\n"); sys.exit(1)


def descargar():
    os.makedirs(RAW_DIR, exist_ok=True)
    print("1/3 Descargando días nuevos del bucket…")
    try:
        gc = "gcloud"
        for c in [os.path.expanduser("~/google-cloud-sdk/bin/gcloud"), "/opt/homebrew/bin/gcloud"]:
            if os.path.isfile(c):
                gc = c; break
        r = subprocess.run([gc, "storage", "cp", "-r", "-n", BUCKET + "/*", RAW_DIR + "/"],
                           capture_output=True, text=True)
    except FileNotFoundError:
        print("    (aviso) no encuentro 'gcloud'; sigo con lo ya descargado."); return
    if r.returncode != 0:
        last = (r.stderr.strip().splitlines() or ["?"])[-1]
        print("    (aviso) la descarga falló, sigo con lo ya descargado:\n    " + last)
        if "credential" in r.stderr.lower() or "login" in r.stderr.lower():
            print("    Vuelve a activar la clave con:\n"
                  '    gcloud auth activate-service-account --key-file="$HOME/.gcp/gcp_mushdrink.json"')
        return
    n = r.stderr.count("Copying ")
    print("    OK · archivos nuevos: " + str(n))


def leer(pd, nombre, cols=None):
    partes = []
    for f in sorted(glob.glob(os.path.join(RAW_DIR, "*", "*", nombre))):
        try:
            d = pd.read_csv(f, dtype=str, keep_default_na=False,
                            usecols=(lambda c: c in cols) if cols else None)
        except Exception:
            continue          # archivo vacio o corrupto
        if len(d):
            partes.append(d)
    return pd.concat(partes, ignore_index=True) if partes else pd.DataFrame()


POINT_RE = re.compile(r"POINT\s*\(\s*(-?\d+(?:\.\d+)?)\s+(-?\d+(?:\.\d+)?)\s*\)", re.I)


def punto(s):
    m = POINT_RE.search(s or "")
    if not m:
        return None, None
    lon, lat = float(m.group(1)), float(m.group(2))
    return round(lat, 5), round(lon, 5)


_CACHE = {}


def _cargar():
    """Lee (una sola vez) todas las reasignaciones y la ubicacion de los restaurantes."""
    if "df" in _CACHE:
        return _CACHE["df"], _CACHE["loc"]
    import pandas as pd
    re_df = leer(pd, "reassignment_lv.csv")
    if re_df.empty:
        raise ValueError("No encuentro ningún reassignment_lv.csv en " + RAW_DIR)
    re_df = re_df.drop_duplicates()
    for c in ["p_created_date", "delivery_id", "rider_id", "store_name", "city_code", "zone_name",
              "notified_at_local", "reassigned_at_local", "reassignment_reason", "reassignment_performed_by"]:
        if c not in re_df.columns:
            re_df[c] = ""
    for c in ["city_code", "reassignment_reason", "reassignment_performed_by", "zone_name", "store_name", "rider_id"]:
        re_df[c] = re_df[c].astype(str).str.strip()
    re_df["_city"] = re_df["city_code"].map(lambda v: NODE_ALIASES.get(v, v) or "?")

    # ubicacion del restaurante (solo esa: no se usan datos del cliente)
    dl = leer(pd, "delivery_lv.csv", cols=["delivery_id", "vendor_location", "store_name", "city_code", "zone_name"])
    loc, loc_store = {}, {}
    if not dl.empty and "vendor_location" in dl.columns:
        dl = dl[dl["vendor_location"] != ""]
        loc = dict(zip(dl.drop_duplicates("delivery_id")["delivery_id"], dl.drop_duplicates("delivery_id")["vendor_location"]))
        # muchos pedidos reasignados acabaron en riders de otra flota y no estan en nuestro delivery_lv:
        # para esos se usa la ubicacion del mismo restaurante (nombre + ciudad) vista en otras entregas
        if "store_name" in dl.columns:
            st_ = dl["store_name"].astype(str).str.strip()
            for col in ["zone_name", "city_code"]:          # primero mismo local+zona, si no local+ciudad
                if col not in dl.columns:
                    continue
                ks = pd.DataFrame({"k": st_ + "|" + dl[col].astype(str).str.strip(), "v": dl["vendor_location"]})
                for k_, v_ in ks.groupby("k")["v"].agg(lambda x: x.value_counts().index[0]).items():
                    loc_store.setdefault(k_, v_)
    _CACHE["loc_store"] = loc_store

    ts = pd.to_datetime(re_df["notified_at_local"].str.slice(0, 19), errors="coerce")
    ts = ts.fillna(pd.to_datetime(re_df["reassigned_at_local"].str.slice(0, 19), errors="coerce"))
    day = pd.to_datetime(re_df["p_created_date"].str.slice(0, 10), errors="coerce")
    day = day.fillna(ts.dt.normalize())
    re_df["_ts"], re_df["_day"] = ts, day
    re_df = re_df[re_df["_day"].notna()].copy()
    iso = re_df["_day"].dt.isocalendar()
    re_df["_wkey"] = list(zip(iso["year"].astype(int), iso["week"].astype(int)))
    _CACHE["df"], _CACHE["loc"] = re_df, loc
    return re_df, loc


def _info(r):
    i = REASON_INFO.get(r)
    if i:
        return dict(raw=r, **i)
    return dict(raw=r, es=r, fam="Sin clasificar", conf="baja",
                que="Motivo nuevo que aún no está en la guía.",
                accion="Añádelo a REASON_INFO en el script cuando sepas qué significa.")


def construir_html(cities=None, semanas=None, sello=True):
    """Devuelve (html, resumen) con los mapas de calor. cities=None -> todas las ciudades."""
    import pandas as pd
    re_df, loc = _cargar()
    if cities:
        re_df = re_df[re_df["_city"].isin(set(cities))]
    if re_df.empty:
        raise ValueError("no hay reasignaciones para " + ", ".join(cities or []))
    keys = sorted(set(re_df["_wkey"]))[-(semanas or WEEKS_TO_SHOW):]
    re_df = re_df[re_df["_wkey"].isin(set(keys))]
    weeks = ["W" + str(k[1]) for k in keys]

    reasons = re_df["reassignment_reason"].value_counts().index.tolist()
    r_idx = {r: i for i, r in enumerate(reasons)}
    perfs = re_df["reassignment_performed_by"].value_counts().index.tolist()
    p_idx = {p: i for i, p in enumerate(perfs)}

    rows, sin_loc = [], 0
    cols = ["_day", "_ts", "_wkey", "_city", "zone_name", "store_name", "rider_id",
            "reassignment_reason", "reassignment_performed_by", "delivery_id", "city_code"]
    for dday, t, wk, city, zone, store, rider, reason, perf, did, city_raw in re_df[cols].itertuples(index=False, name=None):
        ls_ = _CACHE["loc_store"]
        lat, lon = punto(loc.get(did) or ls_.get(store + "|" + zone) or ls_.get(store + "|" + city_raw)
                         or ls_.get(store + "|" + city, ""))
        if lat is None:
            sin_loc += 1
        has_t = not pd.isna(t)
        rows.append([
            dday.strftime("%Y-%m-%d"), "W" + str(wk[1]),
            (t.weekday() if has_t else dday.weekday()),
            (t.hour if has_t else -1),
            city, zone, store, rider, r_idx[reason], p_idx[perf], lat, lon,
        ])

    data = {
        "rows": rows,
        "reasons": reasons,
        "reasonsEs": [_info(r)["es"] for r in reasons],
        "info": [_info(r) for r in reasons],
        "fams": FAMILIAS,
        "perf": [PERF_INFO.get(p, (p, ""))[0] for p in perfs],
        "perfInfo": [PERF_INFO.get(p, (p, "Sin descripción."))[1] for p in perfs],
        "weeks": weeks,
        "cities": sorted(set(r[4] for r in rows)),
        "generated": datetime.datetime.now().strftime("%d/%m/%Y %H:%M") if sello else "",
        "range": (min(r[0] for r in rows) + " → " + max(r[0] for r in rows)) if rows else "",
    }
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    resumen = (str(len(rows)) + " reasignaciones · " + weeks[0] + "–" + weeks[-1] +
               " · " + ", ".join(data["cities"]) +
               ((" · " + str(sin_loc) + " sin ubicación") if sin_loc else ""))
    return HTML.replace("__DATA__", payload), resumen


# ------------------------------------------------------------------------------
#  Integracion en los dashboards "Consola de Flota" (pestaña nueva)
# ------------------------------------------------------------------------------
_TAB_BTN = '<button data-v="heat" aria-pressed="false">Mapas de calor</button>'


def integrar_en_dashboard(dash_html, heat_html):
    """Añade la pestaña 'Mapas de calor' al selector Vista del dashboard.
    El mapa va dentro de un iframe para que su CSS/JS no choque con el del dashboard."""
    if 'id="viewHeat"' in dash_html:
        return dash_html
    ancla_btn = '<button data-v="liga" aria-pressed="false">Delivery Race</button>'
    ancla_sec = '<div id="viewSemanal">'
    if ancla_btn not in dash_html or ancla_sec not in dash_html or "</body>" not in dash_html:
        raise ValueError("la plantilla no tiene el selector de Vista esperado")
    dash_html = dash_html.replace(ancla_btn, ancla_btn + "\n        " + _TAB_BTN, 1)
    seccion = ('<section id="viewHeat" style="display:none">'
               '<iframe id="heatFrame" title="Mapas de calor de reasignaciones" '
               'style="width:100%;height:1400px;border:0;display:block;background:transparent"></iframe>'
               '</section>\n  ')
    dash_html = dash_html.replace(ancla_sec, seccion + ancla_sec, 1)
    heat_html = heat_html.replace("<body>", '<body class="light">', 1)
    # "<" -> \u003c: el HTML embebido no contiene ninguna etiqueta literal (<head>, </script>...),
    # asi ningun post-proceso del dashboard (p. ej. el perl de publicar_dashboards.sh) puede romperlo
    src = json.dumps(heat_html, ensure_ascii=False).replace("<", "\\u003c")
    js = ("<script>\n/* ==== Pestaña Mapas de calor (reasignaciones GCP) ==== */\n(function(){\n"
          "  const HEAT_HTML=" + src + ";\n"
          "  const seg=document.getElementById('viewSeg'),sec=document.getElementById('viewHeat'),fr=document.getElementById('heatFrame');\n"
          "  if(!seg||!sec||!fr) return;\n"
          "  let loaded=false;\n"
          "  seg.querySelectorAll('button').forEach(b=>b.addEventListener('click',()=>{\n"
          "    const on=b.dataset.v==='heat';\n"
          "    sec.style.display=on?'':'none';\n"
          "    if(on){ seg.querySelectorAll('button').forEach(x=>x.setAttribute('aria-pressed',String(x===b)));\n"
          "      ['viewSemanal','viewDiario','viewLiga'].forEach(id=>{const e=document.getElementById(id); if(e) e.style.display='none';});\n"
          "      if(!loaded){ fr.srcdoc=HEAT_HTML; loaded=true; } window.scrollTo(0,0); }\n"
          "  }));\n"
          "  window.addEventListener('message',e=>{ if(e.source===fr.contentWindow && e.data && e.data.heatH){\n"
          "    fr.style.height=Math.max(600,Math.ceil(e.data.heatH)+20)+'px'; } });\n"
          "})();\n</script>\n")
    i = dash_html.rindex("</body>")
    return dash_html[:i] + js + dash_html[i:]


def main():
    try:
        import pandas  # noqa: F401
    except ImportError:
        err("Falta 'pandas'. Instálalo con:  pip3 install pandas")

    if DESCARGAR:
        descargar()

    print("2/3 Leyendo reasignaciones…")
    try:
        html, resumen = construir_html(None)
    except ValueError as e:
        err(str(e))

    print("3/3 Generando dashboard…")
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    out = os.path.join(OUTPUT_DIR, OUTPUT_FILE)
    with open(out, "w", encoding="utf-8") as f:
        f.write(html)
    print("\nOK · " + resumen)
    print("\nÁbrelo con:\n   open \"" + out + "\"\n")


HTML = r"""<!DOCTYPE html>
<html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Mapas de calor · Reasignaciones</title>
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.css">
<script src="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.js"></script>
<style>
:root{--bg:#0F141A;--panel:#161C24;--panel2:#121820;--field:#0F141A;--hover:#1c2430;--track:#232c37;--line:#2A3440;--line2:#333F4D;--tx:#E9ECF1;--tx2:#cfd6df;--dim:#98A3B3;--dimmer:#4b5663;--acc:#4FD1B4;--accsoft:rgba(79,209,180,.14);--acctx:#E9ECF1;--c-alta-bg:rgba(63,185,132,.15);--c-alta:#6fd3a4;--c-media-bg:rgba(224,169,74,.15);--c-media:#e8c27c;--c-baja-bg:rgba(229,98,77,.15);--c-baja:#f0907f;--hl:rgba(124,199,255,.6)}
/* tema claro: se activa al integrarlo en la Consola de Flota */
body.light{--bg:#F6F7F9;--panel:#FFFFFF;--panel2:#F9FAFB;--field:#FFFFFF;--hover:#EEF2F5;--track:#E4E7EC;--line:#E4E7EC;--line2:#D3D8E0;--tx:#14171F;--tx2:#374151;--dim:#6B7280;--dimmer:#C2C8D0;--acc:#0E5A6B;--accsoft:#E3F0F2;--acctx:#0E5A6B;--c-alta-bg:#E7F4EE;--c-alta:#167C58;--c-media-bg:#FBF1DD;--c-media:#9A6B12;--c-baja-bg:#FBE9E7;--c-baja:#B5342A;--hl:rgba(14,90,107,.55)}
body.light .wrap{max-width:none;padding:0 0 24px}
body.light h1{font-size:17px}
body.light table.hm td{color:#14171F}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--tx);font:14px/1.45 -apple-system,BlinkMacSystemFont,"Segoe UI",Inter,Roboto,sans-serif}
.wrap{max-width:1500px;margin:0 auto;padding:20px 16px 40px}
h1{font-size:19px;margin:0 0 2px}
.sub{color:var(--dim);font-size:12.5px}
.bar{display:flex;flex-wrap:wrap;gap:14px;align-items:flex-end;margin:16px 0 12px;padding:12px;background:var(--panel);border:1px solid var(--line);border-radius:12px}
.field{display:flex;flex-direction:column;gap:5px}
.lbl{font-size:11px;text-transform:uppercase;letter-spacing:.06em;color:var(--dim)}
select{background:var(--field);color:var(--tx);border:1px solid var(--line2);border-radius:8px;padding:7px 10px;font:inherit;font-size:13px;min-width:170px}
.seg{display:flex;flex-wrap:wrap;gap:4px}
.seg button,.tabs button{background:var(--field);color:var(--dim);border:1px solid var(--line2);border-radius:8px;padding:6px 11px;font:inherit;font-size:13px;cursor:pointer}
.seg button.on,.tabs button.on{background:var(--accsoft);color:var(--acctx);border-color:var(--acc)}
.seg button small{color:var(--dim);margin-left:4px}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:10px;margin-bottom:12px}
.kpi{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:10px 14px}
.kpi b{display:block;font-size:20px;font-variant-numeric:tabular-nums}
.kpi span{font-size:11.5px;color:var(--dim)}
.tabs{display:flex;flex-wrap:wrap;gap:6px;margin-bottom:10px}
.card{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:14px}
.note{color:var(--dim);font-size:12px;margin:0 0 10px}
.scroll{overflow-x:auto}
table.hm{border-collapse:separate;border-spacing:2px;font-size:12px;font-variant-numeric:tabular-nums}
table.hm th{color:var(--dim);font-weight:600;padding:4px 6px;white-space:nowrap;text-align:center;position:sticky;top:0;background:var(--panel)}
table.hm td{padding:5px 7px;text-align:center;border-radius:4px;min-width:34px;white-space:nowrap}
table.hm .lft{text-align:left;position:sticky;left:0;background:var(--panel);max-width:260px;overflow:hidden;text-overflow:ellipsis;z-index:1}
table.hm td.tot,table.hm tr.totrow td{font-weight:650;color:var(--tx2)}
table.hm tr.totrow td{border-top:1px solid var(--line2)}
table.hm .hl{outline:1px solid var(--hl)}
.dim{color:var(--dimmer)}
.foot{display:flex;justify-content:space-between;align-items:center;margin-top:10px;font-size:12px;color:var(--dim);gap:10px;flex-wrap:wrap}
.btn{background:var(--field);color:var(--tx);border:1px solid var(--line2);border-radius:8px;padding:6px 12px;font:inherit;font-size:12.5px;cursor:pointer}
#mapwrap{display:grid;grid-template-columns:minmax(0,1fr) 300px;gap:12px}
@media(max-width:900px){#mapwrap{grid-template-columns:1fr}}
#map{height:660px;border-radius:10px;background:#dfe3e8}
#maplist{max-height:660px;overflow:auto;background:var(--panel2);border:1px solid var(--line2);border-radius:10px;padding:8px}
#maplist h4{margin:4px 6px 8px;font-size:11px;text-transform:uppercase;letter-spacing:.06em;color:var(--dim);font-weight:600}
.ml-item{display:flex;gap:8px;align-items:center;padding:6px 8px;border-radius:8px;cursor:pointer;font-size:12.5px}
.ml-item:hover{background:var(--hover)}
.ml-item .nm{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.ml-item .zn{color:var(--dim);font-size:11px}
.ml-rk{color:var(--dim);width:18px;text-align:right;flex:none;font-variant-numeric:tabular-nums}
.ml-dot{width:12px;height:12px;border-radius:50%;border:1.5px solid #1b1b1b;flex:none}
.ml-n{margin-left:auto;font-weight:650;font-variant-numeric:tabular-nums}
.maplegend{background:rgba(255,255,255,.94);color:#1b1f24;padding:8px 10px;border-radius:8px;font:12px/1.3 -apple-system,Segoe UI,sans-serif;box-shadow:0 1px 5px rgba(0,0,0,.3)}
.maplegend .g{width:150px;height:10px;border-radius:3px;background:linear-gradient(90deg,#FEE08B,#FC8D59,#D7301F,#7F0000);margin:5px 0 2px;border:1px solid rgba(0,0,0,.2)}
.maplegend .ends{display:flex;justify-content:space-between;color:#555}
.leaflet-tooltip{font-size:12.5px}
.empty{padding:40px;text-align:center;color:var(--dim)}
.leg{display:inline-block;width:60px;height:9px;border-radius:3px;vertical-align:middle;margin:0 6px;background:linear-gradient(90deg,rgba(46,158,123,.8),rgba(224,169,74,.8),rgba(229,98,77,.8))}
.help{display:grid;grid-template-columns:1fr;gap:8px;margin-bottom:12px}
.hbox{border:1px solid var(--line2);border-radius:10px;padding:10px 12px;font-size:12.5px;color:var(--tx2);background:var(--panel2)}
.hbox b.t{display:block;font-size:11px;text-transform:uppercase;letter-spacing:.06em;color:var(--dim);margin-bottom:3px}
.hbox.reason{border-left:3px solid var(--fc,#4FD1B4)}
.fam{display:inline-block;font-size:11px;padding:1px 8px;border-radius:999px;border:1px solid var(--fc);color:var(--fc);margin-right:6px}
.conf{display:inline-block;font-size:11px;padding:1px 8px;border-radius:999px;margin-left:4px}
.conf.alta{background:var(--c-alta-bg);color:var(--c-alta)}.conf.media{background:var(--c-media-bg);color:var(--c-media)}.conf.baja{background:var(--c-baja-bg);color:var(--c-baja)}
.guide h2{font-size:15px;margin:22px 0 8px}.guide h2:first-child{margin-top:0}
.guide p{color:var(--tx2);font-size:13px;margin:0 0 8px;max-width:900px}
.gviews{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:8px}
.gviews div{background:var(--panel2);border:1px solid var(--line2);border-radius:10px;padding:10px 12px;font-size:12.5px;color:var(--tx2)}
.gviews b{display:block;color:var(--tx);margin-bottom:2px}
.gfam{margin:18px 0 6px;display:flex;align-items:baseline;gap:10px;flex-wrap:wrap}
.gfam h3{margin:0;font-size:14px;color:var(--fc)}.gfam span{color:var(--dim);font-size:12.5px}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:10px}
.rcard{background:var(--panel2);border:1px solid var(--line2);border-left:3px solid var(--fc);border-radius:10px;padding:12px 14px;font-size:12.5px;color:var(--tx2);display:flex;flex-direction:column;gap:6px}
.rcard .hd{display:flex;justify-content:space-between;gap:8px;align-items:baseline}
.rcard .hd b{font-size:13.5px;color:var(--tx)}.rcard .n{color:var(--dim);white-space:nowrap;font-variant-numeric:tabular-nums}
.rcard code{font-size:11px;color:var(--dim)}
.rcard .lab{color:var(--dim);font-size:11px;text-transform:uppercase;letter-spacing:.05em}
.rcard .go{align-self:flex-start;margin-top:2px}
.bar2{height:4px;border-radius:2px;background:var(--track);overflow:hidden}.bar2 i{display:block;height:100%;background:var(--fc)}
</style></head><body><div class="wrap">
<h1>Mapas de calor · Reasignaciones (GCP)</h1>
<div class="sub" id="sub"></div>

<div class="bar">
  <div class="field"><span class="lbl">Ciudad</span><div class="seg" id="citySeg"></div></div>
  <div class="field"><span class="lbl">Motivo</span><select id="reasonSel"></select></div>
  <div class="field"><span class="lbl">Semana</span><select id="weekSel"></select></div>
  <div class="field"><span class="lbl">Día</span><select id="daySel"></select></div>
  <div class="field"><span class="lbl">Realizado por</span><select id="perfSel"></select></div>
</div>

<div class="kpis" id="kpis"></div>

<div class="tabs" id="tabs">
  <button data-v="guia" class="on">📘 Guía</button>
  <button data-v="hora">Hora × día</button>
  <button data-v="zona">Zona</button>
  <button data-v="rest">Restaurante</button>
  <button data-v="rider">Rider × motivo</button>
  <button data-v="mapa">Mapa</button>
</div>

<div class="card">
  <div class="help" id="help"></div>
  <p class="note" id="note"></p>
  <div class="scroll" id="out"></div>
  <div id="mapwrap" style="display:none"><div id="map"></div><div id="maplist"></div></div>
  <div class="foot" id="footbar"><span id="foot"></span>
    <span>Menos <span class="leg"></span> Más · <button class="btn" id="csvBtn">Descargar CSV</button></span></div>
</div>
</div>

<script>
const D=__DATA__;
const R=D.rows; // [fecha, semana, diaSemana, hora, ciudad, zona, restaurante, rider, motivo, realizadoPor, lat, lon]
const DOW=['Lun','Mar','Mié','Jue','Vie','Sáb','Dom'];
const st={city:'ALL',reason:-1,fam:null,week:'ALL',day:'ALL',perf:-1,view:'guia'};
const DIAS=['Dom','Lun','Mar','Mié','Jue','Vie','Sáb'];
const dayLbl=d=>{const x=new Date(d+'T12:00:00');return DIAS[x.getDay()]+' '+d.slice(8,10)+'/'+d.slice(5,7);};
// columnas de Zona/Restaurante: semanas, o dias si hay una semana o un dia elegido
function periodCols(){
  if(st.day!=='ALL') return {keys:[st.day],lbl:[dayLbl(st.day)],key:r=>r[0]};
  if(st.week!=='ALL'){const ks=[...new Set(R.filter(r=>r[1]===st.week).map(r=>r[0]))].sort();return {keys:ks,lbl:ks.map(dayLbl),key:r=>r[0]};}
  return {keys:D.weeks,lbl:D.weeks,key:r=>r[1]};}
let last=null, map=null, layer=null;
const FAM_ORDER=['Rider','Recogida','Pedido','Sistema','Sin clasificar'];
const famOf=i=>D.info[i].fam;
const famColor=f=>(D.fams[f]||{}).color||'#4FD1B4';
const CONF_TXT={alta:'Significado claro',media:'Interpretación razonable',baja:'No confirmado · preguntar a Glovo'};
const VIEW_HELP={
  hora:['¿CUÁNDO pasan?','Filas = día de la semana; columnas = hora del día. Cada celda cuenta las reasignaciones en esa franja. Busca bloques rojos: son las horas problemáticas.'],
  zona:['¿DÓNDE pasan y cómo evolucionan?','Filas = zonas; columnas = semanas (o días, si eliges una semana arriba). Lee cada fila de izquierda a derecha: si se vuelve más roja, esa zona está empeorando.'],
  rest:['¿QUÉ LOCALES las generan?','Filas = restaurantes (los 50 con más casos); columnas = semanas (o días, si eliges una semana arriba). Un local rojo en todas las columnas es un problema recurrente, no puntual.'],
  rider:['¿QUIÉN las acumula y por qué?','Filas = riders (los 60 con más casos); columnas = motivos. Te dice con qué riders hablar y de qué. Elige un motivo arriba para ordenar por él.'],
  mapa:['¿DÓNDE en la ciudad?','Cada círculo es un restaurante. Cuanto más grande y rojo, más reasignaciones tienen sus pedidos. Pasa el ratón por encima para ver el nombre.'],
};
const COLOR_NOTE='El color compara las celdas de esta tabla entre sí: rojo = el valor más alto de la tabla, verde = de los más bajos. No es un objetivo de Glovo.';

const fmt=n=>n.toLocaleString('es-ES');
const esc=s=>String(s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
function rgb(t){t=Math.max(0,Math.min(1,t));const S=[[0,[46,158,123]],[.5,[224,169,74]],[1,[229,98,77]]];
  const [a,b]=t<=.5?[S[0],S[1]]:[S[1],S[2]];const f=(t-a[0])/(b[0]-a[0]);return a[1].map((x,k)=>Math.round(x+(b[1][k]-x)*f));}
const heat=t=>{const c=rgb(t);return 'rgba('+c+','+(0.22+0.5*t).toFixed(2)+')';};
const solid=t=>'rgb('+rgb(t)+')';

function filt(ignoreReason){return R.filter(r=>(st.city==='ALL'||r[4]===st.city)&&(st.week==='ALL'||r[1]===st.week)&&(st.day==='ALL'||r[0]===st.day)
  &&(st.perf<0||r[9]===st.perf)&&(st.fam==null||famOf(r[8])===st.fam)&&(ignoreReason||st.reason<0||r[8]===st.reason));}

function countBy(rows,f){const m=new Map();rows.forEach(r=>{const k=f(r);m.set(k,(m.get(k)||0)+1);});return [...m.entries()].sort((a,b)=>b[1]-a[1]);}

function group(rows,rowKey,cols,colKey,limit,sortCol){
  const ci=new Map(cols.map((c,j)=>[c,j])),g=new Map();
  rows.forEach(r=>{const j=ci.get(colKey(r));if(j==null)return;const k=rowKey(r);let a=g.get(k);if(!a){a=Array(cols.length).fill(0);g.set(k,a);}a[j]++;});
  let e=[...g.entries()].map(([k,a])=>[k,a,sortCol>=0?a[sortCol]:a.reduce((x,y)=>x+y,0),a.reduce((x,y)=>x+y,0)])
    .sort((x,y)=>(y[2]-x[2])||(y[3]-x[3]));
  const more=Math.max(0,e.length-limit);e=e.slice(0,limit);
  return {rowL:e.map(x=>x[0]),M:e.map(x=>x[1]),more};
}

function matrix(rowHead,rowL,colL,M,hl){
  last={rowHead,rowL,colL,M};
  if(!M.length) return '<div class="empty"><b>Sin datos</b><br>No hay reasignaciones con estos filtros.</div>';
  let mx=0;M.forEach(r=>r.forEach(v=>{if(v>mx)mx=v;}));
  const colT=colL.map((_,j)=>M.reduce((s,r)=>s+r[j],0));
  let h='<table class="hm"><thead><tr><th class="lft">'+esc(rowHead)+'</th>'+colL.map((c,j)=>'<th'+(j===hl?' class="hl"':'')+'>'+esc(c)+'</th>').join('')+'<th>Total</th></tr></thead><tbody>';
  M.forEach((r,i)=>{h+='<tr><td class="lft" title="'+esc(rowL[i])+'">'+esc(rowL[i])+'</td>'+
    r.map((v,j)=>'<td'+(j===hl?' class="hl"':'')+(v?' style="background:'+heat(v/mx)+'"':'')+'>'+(v?fmt(v):'<span class="dim">·</span>')+'</td>').join('')+
    '<td class="tot">'+fmt(r.reduce((a,b)=>a+b,0))+'</td></tr>';});
  h+='<tr class="totrow"><td class="lft">Total</td>'+colT.map(v=>'<td>'+fmt(v)+'</td>').join('')+'<td>'+fmt(colT.reduce((a,b)=>a+b,0))+'</td></tr>';
  return h+'</tbody></table>';
}

function kpis(rows){
  const all=filt(true), tr=countBy(all,r=>r[8])[0], tz=countBy(rows,r=>r[5]||'(sin zona)')[0];
  const th=countBy(rows.filter(r=>r[3]>=0),r=>DOW[r[2]]+' '+r[3]+'h')[0];
  const k=[[fmt(rows.length),'Reasignaciones'+(st.reason>=0?' · '+D.reasonsEs[st.reason]:(st.fam?' · familia '+st.fam:''))],
    [tr?Math.round(100*tr[1]/all.length)+'%':'–','Motivo principal: '+(tr?D.reasonsEs[tr[0]]:'–')],
    [tz?fmt(tz[1]):'–','Zona con más: '+(tz?tz[0]:'–')],
    [th?fmt(th[1]):'–','Franja pico: '+(th?th[0]:'–')]];
  document.getElementById('kpis').innerHTML=k.map(x=>'<div class="kpi"><b>'+x[0]+'</b><span>'+esc(x[1])+'</span></div>').join('');
}

function helpHTML(){
  const v=VIEW_HELP[st.view]; if(!v) return '';
  let h='<div class="hbox"><b class="t">Cómo leer esta vista · '+v[0]+'</b>'+esc(v[1])+(st.view!=='mapa'?' <span style="color:var(--dim)">'+esc(COLOR_NOTE)+'</span>':'')+'</div>';
  if(st.reason>=0){const I=D.info[st.reason],F=D.fams[I.fam]||{tips:{}};
    h+='<div class="hbox reason" style="--fc:'+famColor(I.fam)+'"><b class="t">Motivo seleccionado</b>'+
      '<span class="fam" style="--fc:'+famColor(I.fam)+'">'+esc(I.fam)+'</span><b>'+esc(I.es)+'</b><span class="conf '+I.conf+'">'+CONF_TXT[I.conf]+'</span>'+
      '<div style="margin-top:6px">'+esc(I.que)+'</div>'+
      '<div style="margin-top:6px"><b>En esta vista:</b> '+esc(F.tips[st.view]||'')+'</div>'+
      '<div style="margin-top:4px"><b>Qué hacer:</b> '+esc(I.accion)+'</div></div>';
  } else if(st.fam){const F=D.fams[st.fam];
    h+='<div class="hbox reason" style="--fc:'+famColor(st.fam)+'"><b class="t">Familia seleccionada</b>'+
      '<span class="fam" style="--fc:'+famColor(st.fam)+'">'+esc(st.fam)+'</span>'+esc(F.desc)+
      '<div style="margin-top:6px"><b>En esta vista:</b> '+esc(F.tips[st.view]||'')+'</div></div>';
  } else {
    h+='<div class="hbox"><b class="t">Consejo</b>Elige un motivo o una familia en el filtro «Motivo» para ver aquí qué significa y qué buscar en este mapa. La pestaña 📘 Guía explica todos los motivos.</div>';
  }
  return h;
}

function guideHTML(){
  const base=filt(true), tot=base.length||1, cnt=new Map();
  base.forEach(r=>cnt.set(r[8],(cnt.get(r[8])||0)+1));
  let h='<div class="guide">';
  h+='<h2>1 · Qué es una reasignación</h2><p>Un pedido se <b>reasigna</b> cuando deja de estar en manos del rider al que se asignó y pasa a otro rider. '+
    'Cada fila de estos datos es una reasignación, con su <b>motivo</b> (por qué pasó), <b>quién la hizo</b> (sistema automático o agente de soporte), la hora, la zona, el restaurante y el rider. '+
    'Cuantas menos reasignaciones, mejor: afectan a tu tasa RR % frente a Glovo.</p>';
  h+='<h2>2 · Qué responde cada mapa de calor</h2><div class="gviews">'+
    Object.entries(VIEW_HELP).map(([k,v])=>'<div><b>'+esc({hora:'Hora × día',zona:'Zona',rest:'Restaurante',rider:'Rider × motivo',mapa:'Mapa'}[k])+' · '+esc(v[0])+'</b>'+esc(v[1])+'</div>').join('')+
    '</div><p style="margin-top:10px"><b>Colores:</b> '+esc(COLOR_NOTE)+'</p>';
  h+='<h2>3 · Qué significa cada motivo</h2><p>Los motivos se agrupan en familias según dónde está la causa. La etiqueta de color indica cuánto nos fiamos del significado: '+
    '<span class="conf alta">'+CONF_TXT.alta+'</span> <span class="conf media">'+CONF_TXT.media+'</span> <span class="conf baja">'+CONF_TXT.baja+'</span>. '+
    'Los porcentajes usan los filtros de ciudad, semana y «realizado por» que tengas puestos arriba.</p>';
  FAM_ORDER.concat(Object.keys(D.fams).filter(f=>!FAM_ORDER.includes(f))).forEach(f=>{
    const idx=D.info.map((_,i)=>i).filter(i=>famOf(i)===f).sort((a,b)=>(cnt.get(b)||0)-(cnt.get(a)||0));
    if(!idx.length) return;
    const F=D.fams[f]||{desc:'',tips:{}}, n=idx.reduce((s,i)=>s+(cnt.get(i)||0),0);
    h+='<div class="gfam" style="--fc:'+famColor(f)+'"><h3>'+esc(f)+' · '+Math.round(100*n/tot)+'%</h3><span>'+esc(F.desc)+'</span>'+
      '<button class="btn go" data-fam="'+esc(f)+'">Ver familia en los mapas →</button></div><div class="cards">';
    idx.forEach(i=>{const I=D.info[i],c=cnt.get(i)||0;
      h+='<div class="rcard" style="--fc:'+famColor(f)+'"><div class="hd"><b>'+esc(I.es)+'</b><span class="n">'+fmt(c)+' · '+(100*c/tot).toFixed(1).replace('.',',')+'%</span></div>'+
        '<div class="bar2"><i style="width:'+(100*c/tot).toFixed(1)+'%"></i></div>'+
        '<div><code>'+esc(I.raw||'(vacío)')+'</code><span class="conf '+I.conf+'">'+CONF_TXT[I.conf]+'</span></div>'+
        '<div><span class="lab">Qué significa</span><br>'+esc(I.que)+'</div>'+
        '<div><span class="lab">Qué hacer</span><br>'+esc(I.accion)+'</div>'+
        '<div><span class="lab">Mejor mapa para analizarlo</span><br>'+esc(bestView(f))+'</div>'+
        '<button class="btn go" data-r="'+i+'">Ver en los mapas →</button></div>';});
    h+='</div>';
  });
  h+='<h2>4 · «Realizado por»</h2><div class="gviews">'+D.perf.map((p,i)=>'<div><b>'+esc(p)+'</b>'+esc(D.perfInfo[i])+'</div>').join('')+'</div>';
  return h+'</div>';
}
function bestView(f){return {Rider:'Rider × motivo, para ver qué riders reinciden.',Recogida:'Restaurante y Mapa (locales lentos), y Rider × motivo (riders que no recogen).',
  Pedido:'Restaurante y Mapa.',Sistema:'Hora × día (picos puntuales) y Zona.','Sin clasificar':'Solo sirve como volumen.'}[f]||'Hora × día.';}

function render(){
  const rows=filt(false), P=periodCols();
  kpis(rows);
  const out=document.getElementById('out'),mapEl=document.getElementById('mapwrap'),note=document.getElementById('note');
  document.getElementById('help').innerHTML=helpHTML();
  document.getElementById('footbar').style.display=st.view==='guia'?'none':'';
  note.style.display='none'; // la ayuda contextual ya explica cada vista
  out.style.display='';mapEl.style.display='none';let foot='';
  if(st.view==='guia'){
    last=null; out.innerHTML=guideHTML();
    out.querySelectorAll('button[data-r]').forEach(b=>b.onclick=()=>{setReason(String(b.dataset.r));goView('hora');});
    out.querySelectorAll('button[data-fam]').forEach(b=>b.onclick=()=>{setReason('f:'+b.dataset.fam);goView('hora');});
    return;
  }
  if(st.view==='hora'){
    const M=DOW.map(()=>Array(24).fill(0));let sin=0;
    rows.forEach(r=>{if(r[3]>=0)M[r[2]][r[3]]++;else sin++;});
    note.textContent='Nº de reasignaciones por día de la semana y hora (hora local del aviso al rider).';
    out.innerHTML=matrix('Día',DOW,[...Array(24).keys()].map(h=>h+'h'),M,-1);
    foot=sin?sin+' sin hora registrada':'';
  } else if(st.view==='zona'){
    const g=group(rows,r=>(r[4]+' · '+(r[5]||'(sin zona)')),P.keys,P.key,80,-1);
    note.textContent='Nº de reasignaciones por zona y semana ISO.';
    out.innerHTML=matrix('Zona',g.rowL,P.lbl,g.M,-1);foot=g.more?'+'+g.more+' zonas más':'';
  } else if(st.view==='rest'){
    const g=group(rows,r=>r[6]||'(sin restaurante)',P.keys,P.key,50,-1);
    note.textContent='Top 50 restaurantes con más reasignaciones, por semana ISO.';
    out.innerHTML=matrix('Restaurante',g.rowL,P.lbl,g.M,-1);foot=g.more?'+'+g.more+' restaurantes más':'';
  } else if(st.view==='rider'){
    const base=filt(true);let top=countBy(base,r=>r[8]).slice(0,8).map(x=>x[0]);
    if(st.reason>=0&&!top.includes(st.reason))top.push(st.reason);
    const cols=top.map(i=>D.reasonsEs[i]),hasOtros=countBy(base,r=>r[8]).length>top.length;
    if(hasOtros)cols.push('Otros');
    const hl=st.reason>=0?top.indexOf(st.reason):-1;
    const g=group(base,r=>r[7]+' · '+r[4],cols,r=>{const j=top.indexOf(r[8]);return j>=0?cols[j]:'Otros';},60,hl);
    note.textContent='Top 60 riders por nº de reasignaciones y motivo'+(hl>=0?' (ordenado por «'+D.reasonsEs[st.reason]+'»)':'')+'. Aquí el filtro de motivo solo ordena y resalta la columna.';
    out.innerHTML=matrix('Rider',g.rowL,cols,g.M,hl);foot=g.more?'+'+g.more+' riders más':'';
  } else {
    out.style.display='none';mapEl.style.display='';last=null;
    note.textContent='Cada círculo es un restaurante: tamaño y color = nº de reasignaciones de sus pedidos. Pasa el ratón por encima para ver el detalle.';
    foot=drawMap(rows);
  }
  document.getElementById('foot').textContent=foot;
  document.getElementById('csvBtn').style.display=st.view==='mapa'?'none':'';
}

const MAPC=[[0,[254,224,139]],[.35,[252,141,89]],[.7,[215,48,31]],[1,[127,0,0]]];
function mapColor(t){t=Math.max(0,Math.min(1,t));let i=0;while(i<MAPC.length-2&&t>MAPC[i+1][0])i++;
  const a=MAPC[i],b=MAPC[i+1],f=(t-a[0])/(b[0]-a[0]);return 'rgb('+a[1].map((x,k)=>Math.round(x+(b[1][k]-x)*f))+')';}
let legendDiv=null, markers=[];
function drawMap(rows){
  const el=document.getElementById('map'),list=document.getElementById('maplist');
  if(typeof L==='undefined'){el.innerHTML='<div class="empty" style="color:#333">No se pudo cargar el mapa. Comprueba tu conexión a internet.</div>';list.innerHTML='';return '';}
  if(!map){
    map=L.map(el,{preferCanvas:true,zoomSnap:.5});
    const esri='https://server.arcgisonline.com/ArcGIS/rest/services/';
    const at='Tiles © Esri — Esri, HERE, Garmin, OpenStreetMap contributors';
    const gris=L.layerGroup([
      L.tileLayer(esri+'Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}',{attribution:at,maxZoom:19,maxNativeZoom:16}),
      L.tileLayer(esri+'Canvas/World_Light_Gray_Reference/MapServer/tile/{z}/{y}/{x}',{maxZoom:19,maxNativeZoom:16})]);
    const calles=L.tileLayer(esri+'World_Street_Map/MapServer/tile/{z}/{y}/{x}',{attribution:at,maxZoom:19});
    const sat=L.tileLayer(esri+'World_Imagery/MapServer/tile/{z}/{y}/{x}',{attribution:'Tiles © Esri — Maxar, Earthstar Geographics',maxZoom:19});
    gris.addTo(map);
    L.control.layers({'Gris claro':gris,'Calles':calles,'Satélite':sat},null,{position:'topright'}).addTo(map);
    const lg=L.control({position:'bottomright'});
    lg.onAdd=()=>{legendDiv=L.DomUtil.create('div','maplegend');return legendDiv;};lg.addTo(map);
    layer=L.layerGroup().addTo(map);map.setView([40.2,-3.7],6);
  }
  map.invalidateSize();layer.clearLayers();markers=[];
  const g=new Map();let sin=0;
  rows.forEach(r=>{if(r[10]==null){sin++;return;}const k=r[10].toFixed(4)+','+r[11].toFixed(4);let o=g.get(k);
    if(!o){o={lat:r[10],lon:r[11],n:0,store:r[6]||'(sin nombre)',zone:r[5],city:r[4]};g.set(k,o);}o.n++;});
  const pts=[...g.values()].sort((a,b)=>a.n-b.n);
  if(!pts.length){list.innerHTML='<div class="empty">Sin ubicaciones</div>';legendDiv.innerHTML='';return 'Sin ubicaciones para estos filtros';}
  const mx=pts[pts.length-1].n;
  pts.forEach(p=>{const t=Math.sqrt(p.n/mx);p.col=mapColor(t);
    p.m=L.circleMarker([p.lat,p.lon],{radius:5+17*t,color:'#1b1b1b',weight:1.5,fillColor:p.col,fillOpacity:.85})
      .bindTooltip('<b>'+esc(p.store)+'</b><br>'+esc(p.city+' · '+(p.zone||''))+'<br><b>'+fmt(p.n)+'</b> reasignaciones',{direction:'top'}).addTo(layer);});
  legendDiv.innerHTML='<b>Reasignaciones por local</b><div class="g"></div><div class="ends"><span>1</span><span>'+fmt(Math.round(mx/2))+'</span><span>'+fmt(mx)+'</span></div>';
  const top=pts.slice().reverse().slice(0,25);
  list.innerHTML='<h4>Top '+top.length+' locales · clic para ir</h4>'+top.map((p,i)=>
    '<div class="ml-item" data-i="'+i+'"><span class="ml-rk">'+(i+1)+'</span><span class="ml-dot" style="background:'+p.col+'"></span>'+
    '<span style="min-width:0"><div class="nm">'+esc(p.store)+'</div><div class="zn">'+esc(p.city+' · '+(p.zone||''))+'</div></span><span class="ml-n">'+fmt(p.n)+'</span></div>').join('');
  list.querySelectorAll('.ml-item').forEach(d=>d.onclick=()=>{const p=top[+d.dataset.i];map.setView([p.lat,p.lon],16);p.m.openTooltip();});
  map.fitBounds(L.latLngBounds(pts.map(p=>[p.lat,p.lon])).pad(0.08),{maxZoom:15});
  return pts.length+' restaurantes'+(sin?' · '+sin+' reasignaciones sin ubicación':'')+(st.city==='ALL'?' · Elige una ciudad arriba para acercar el mapa':'');
}

// ---- controles ----
function buildCity(){const el=document.getElementById('citySeg');
  const opts=[['ALL','Todas',R.length]].concat(D.cities.map(c=>[c,c,R.filter(r=>r[4]===c).length]));
  el.innerHTML=opts.map(o=>'<button data-v="'+o[0]+'"'+(o[0]===st.city?' class="on"':'')+'>'+o[1]+'<small>'+fmt(o[2])+'</small></button>').join('');
  el.querySelectorAll('button').forEach(b=>b.onclick=()=>{st.city=b.dataset.v;buildCity();render();});}
const cnt=new Array(D.reasons.length).fill(0);R.forEach(r=>cnt[r[8]]++);
const rs=document.getElementById('reasonSel');
rs.innerHTML='<option value="-1">Todos los motivos</option>'+
  FAM_ORDER.concat(Object.keys(D.fams).filter(f=>!FAM_ORDER.includes(f))).map(f=>{
    const idx=D.info.map((_,i)=>i).filter(i=>famOf(i)===f); if(!idx.length) return '';
    const n=idx.reduce((s,i)=>s+cnt[i],0);
    return '<optgroup label="'+esc(f)+'"><option value="f:'+esc(f)+'">▸ Toda la familia '+esc(f)+' ('+fmt(n)+')</option>'+
      idx.map(i=>'<option value="'+i+'">'+esc(D.reasonsEs[i])+' ('+fmt(cnt[i])+')</option>').join('')+'</optgroup>';}).join('');
function setReason(v){rs.value=v;
  if(v.indexOf('f:')===0){st.fam=v.slice(2);st.reason=-1;} else {st.fam=null;st.reason=+v;}}
function goView(v){st.view=v;document.querySelectorAll('#tabs button').forEach(x=>x.classList.toggle('on',x.dataset.v===v));render();window.scrollTo({top:0,behavior:'smooth'});}
rs.onchange=e=>{setReason(e.target.value);render();};
const ws=document.getElementById('weekSel');
ws.innerHTML='<option value="ALL">Todas ('+D.weeks[0]+'–'+D.weeks[D.weeks.length-1]+')</option>'+D.weeks.slice().reverse().map(w=>'<option>'+w+'</option>').join('');
const dsel=document.getElementById('daySel');
function buildDays(){const ds=[...new Set(R.filter(r=>st.week==='ALL'||r[1]===st.week).map(r=>r[0]))].sort().reverse();
  if(st.day!=='ALL'&&!ds.includes(st.day)) st.day='ALL';
  dsel.innerHTML='<option value="ALL">Todos los días</option>'+ds.map(d=>'<option value="'+d+'"'+(d===st.day?' selected':'')+'>'+dayLbl(d)+'</option>').join('');}
ws.onchange=e=>{st.week=e.target.value;buildDays();render();};
dsel.onchange=e=>{st.day=e.target.value;render();};
buildDays();
const ps=document.getElementById('perfSel');
ps.innerHTML='<option value="-1">Todos</option>'+D.perf.map((n,i)=>'<option value="'+i+'">'+esc(n)+'</option>').join('');
ps.onchange=e=>{st.perf=+e.target.value;render();};
document.querySelectorAll('#tabs button').forEach(b=>b.onclick=()=>goView(b.dataset.v));
document.getElementById('csvBtn').onclick=()=>{if(!last)return;
  const q=s=>'"'+String(s).replace(/"/g,'""')+'"';
  const lines=[[last.rowHead].concat(last.colL).concat(['Total']).map(q).join(',')];
  last.M.forEach((r,i)=>lines.push([q(last.rowL[i])].concat(r).concat([r.reduce((a,b)=>a+b,0)]).join(',')));
  const a=document.createElement('a');a.href=URL.createObjectURL(new Blob(['\ufeff'+lines.join('\n')],{type:'text/csv;charset=utf-8'}));
  a.download='heatmap_'+st.view+'_'+st.city+'.csv';a.click();};
document.getElementById('sub').textContent='Fuente: bucket GCP de Glovo · '+D.range+(D.generated?' · generado '+D.generated:'');
buildCity();render();
// si va dentro de la Consola de Flota (iframe), avisa de su altura para que no haya doble scroll
if(window.parent!==window){const send=()=>window.parent.postMessage({heatH:document.body.getBoundingClientRect().height},'*');
  if(window.ResizeObserver) new ResizeObserver(send).observe(document.body); send();}
</script></body></html>
"""

if __name__ == "__main__":
    main()
