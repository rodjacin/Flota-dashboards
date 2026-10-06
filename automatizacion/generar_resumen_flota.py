#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
================================================================================
 Generar los 2 dashboards "Consola de Flota · Resumen por Rider"
 (formato Fleet Partner Report 2.0) desde los CSV combinados
================================================================================

 · Vista SEMANAL: semanas ISO reales (W34, W35 ...), lunes a domingo.
 · Vista DIARIA : apartado nuevo con una fila por rider y dia de la SEMANA EN
                  CURSO, mas el agregado de esa semana.

 Entradas (en ~/Downloads/):
   - fleet_data_combinado/rider_lv_combinado.csv
   - plantilla_resumen_SAB.html
   - plantilla_resumen_GRA_MAD_NOM_ALC.html
 Salidas (en ~/Downloads/dashboards/):
   - resumen_flota_riders_SAB.html
   - resumen_flota_riders_GRA_MAD_NOM_ALC.html

 USO:
   pip3 install pandas
   python3 generar_resumen_flota.py
================================================================================
"""

import os
import sys
import json
import datetime

# --- Delivery Race de tendencia: aplica patch_delivery_race.py si está junto a este script ---
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from patch_delivery_race import patch as _apply_race_trend
except Exception:
    _apply_race_trend = None

# --- Resumen de performance con filtro de métrica + definiciones al pasar el ratón ---
try:
    from patch_perf_metricas import patch as _apply_perf
except Exception:
    _apply_perf = None

# --- Pestaña "Mapas de calor" (reasignaciones del bucket GCP): usa heatmaps_reasignaciones.py ---
try:
    import heatmaps_reasignaciones as _heat
except Exception:
    _heat = None

# --- Pestaña "UTR" (UTR por hora/rider y arranque de turno): usa utr_arranque.py ---
try:
    import utr_arranque as _utr
except Exception:
    _utr = None

# --- Pestaña "No show" (no show por rider, semana y día de la semana): usa noshow_riders.py ---
try:
    import noshow_riders as _ns
except Exception:
    _ns = None

# --- Pestaña "Capacidad" (forecast vs real por media hora): usa capacidad_forecast.py ---
try:
    import capacidad_forecast as _cap
except Exception:
    _cap = None

# --- Pestaña "En vivo" (Glovo Live Operations API): usa en_vivo.py ---
try:
    import en_vivo as _vivo
except Exception:
    _vivo = None

# --- Pestaña "Códigos postales" (impacto por CP en WTD, RR e incidencias): usa cp_impacto.py ---
try:
    import cp_impacto as _cpi
except Exception:
    _cpi = None

# --- Pestaña "WTD%" (WTD por rider L4W / WK-1 + paradas con pedido activo): usa wtd_riders.py ---
try:
    import wtd_riders as _wtdr
except Exception:
    _wtdr = None

# --- Pestaña "WTD% v1" (riders parados justo después de entregar): usa wtd_v1.py + posiciones.py ---
try:
    import wtd_v1 as _wtdv1
except Exception:
    _wtdv1 = None

# ==============================================================================
#  CONFIGURACION
# ==============================================================================

INPUT_FILE   = os.path.expanduser("~/Downloads/fleet_data_combinado/rider_lv_combinado.csv")
TEMPLATE_SAB = os.path.expanduser("~/Downloads/plantilla_resumen_SAB.html")
TEMPLATE_BIG = os.path.expanduser("~/Downloads/plantilla_resumen_GRA_MAD_NOM_ALC.html")
OUTPUT_DIR   = os.path.expanduser("~/Downloads/dashboards")

NODE_COLUMN = "city_code"
NODE_ALIASES = {"NEM": "MAD"}            # Madrid en el CSV = NEM -> se muestra MAD

CITIES_SAB = ["SAB"]
CITIES_BIG = ["ALC", "GRA", "MAD", "NOM"]

# Cuantas semanas ISO mostrar en la vista semanal (las mas recientes).
WEEKS_TO_SHOW = 8

# Pestaña "Mapas de calor": descargar tambien con gcloud antes de generar (True/False)
HEAT_DESCARGAR = False   # los datos ya los baja extraer_datos_fleet.py a ~/Downloads/fleet_data

# Reparto del coste de fraude (deben sumar 1.0)
COST_SHARE_GLOVO  = 0.0
COST_SHARE_CHARGE = 1.0

# ==============================================================================
#  A partir de aqui NO necesitas tocar nada.
# ==============================================================================

DIAS_ES = ["Lun", "Mar", "Mie", "Jue", "Vie", "Sab", "Dom"]


def err(m):
    print("\nERROR: " + m + "\n"); sys.exit(1)


def num(df, name, pd):
    if name in df.columns:
        return pd.to_numeric(df[name], errors="coerce").fillna(0.0)
    return pd.Series([0.0] * len(df), index=df.index)


def rate(a, b):
    return (a / b) if b else None


def metrics_from_sums(S):
    deliv = S["deliv"]; assigned = S["assigned"]
    return {
        "delivered": deliv,
        "undelivered": S["cancelled"],
        "capu": rate(S["capu"], deliv),
        "notMoving": S["noshows"],
	"_noshows": rate(S["noshows"], S["booked"]),  # franjas de 30 min no presentadas ÷ franjas reservadas
        "bundling": rate(S["stacked"], deliv),
        "wtd10": rate(S["over10"], deliv),
        "reassign": rate(S["reassign"], assigned),
        "notSeen": rate(S["not_seen"], assigned),
        "ignored": rate(S["ignored"], assigned),
        "decline": rate(S["decline"], assigned),
        "redispatch": rate(S["redispatch"], assigned),
        "cnm": rate(S["cnm"], assigned),
        "agent": rate(S["agent"], assigned),
        "deliveryTime": rate(S["cdt_num"], S["cdt_den"]),
        "wtd": S["atcust"],
        "workingHours": S["worked"],
	"utr": rate(deliv, S["worked"]),
        "ineligible": S["inelig"],
        "efficiency": rate(S["busy"], S["working"]),
        "slInc": S["capu"] + S["undel"] + S["absent"],
        "slCapu": S["capu"],
        "slUndel": S["undel"],
        "slAbsent": S["absent"],
        "slGlovo": S["fraudcost"] * COST_SHARE_GLOVO,
        "slCharge": S["fraudcost"] * COST_SHARE_CHARGE,
    }


def main():
    for p in [INPUT_FILE, TEMPLATE_SAB, TEMPLATE_BIG]:
        if not os.path.isfile(p):
            err("No encuentro:\n   " + p)
    try:
        import pandas as pd
    except ImportError:
        err("Falta 'pandas'. Instalalo con:  pip3 install pandas")

    print("Delivery Race de tendencia: " + ("ACTIVO" if _apply_race_trend else "no encontrado (usa el ranking clásico)"))
    print("Mapas de calor (GCP): " + ("ACTIVO" if _heat else "no encontrado (falta heatmaps_reasignaciones.py junto a este script)"))
    print("Resumen de performance con filtro de métrica: " + ("ACTIVO" if _apply_perf else "no encontrado (falta patch_perf_metricas.py junto a este script)"))
    print("Pestaña UTR: " + ("ACTIVA" if _utr else "no encontrada (falta utr_arranque.py junto a este script)"))
    print("Pestaña No show: " + ("ACTIVA" if _ns else "no encontrada (falta noshow_riders.py junto a este script)"))
    print("Pestaña Capacidad: " + ("ACTIVA" if _cap else "no encontrada (falta capacidad_forecast.py junto a este script)"))
    print("Pestaña En vivo: " + ("ACTIVA" if _vivo else "no encontrada (falta en_vivo.py junto a este script)"))
    print("Pestaña Códigos postales: " + ("ACTIVA" if _cpi else "no encontrada (falta cp_impacto.py o la librería shapely)"))
    print("Pestaña WTD%: " + ("ACTIVA" if _wtdr else "no encontrada (falta wtd_riders.py junto a este script)"))
    print("Pestaña WTD% v1: " + ("ACTIVA" if _wtdv1 else "no encontrada (falta wtd_v1.py junto a este script)"))
    if _heat and HEAT_DESCARGAR:
        _heat.descargar()
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    df = pd.read_csv(INPUT_FILE, dtype=str, keep_default_na=False)
    if NODE_COLUMN not in df.columns:
        err("No existe la columna de nodo '" + NODE_COLUMN + "'.")

    df["_city"] = df[NODE_COLUMN].astype(str).str.strip().map(lambda v: NODE_ALIASES.get(v, v))
    df["_date"] = pd.to_datetime(df["fecha"], errors="coerce").dt.date
    df = df[df["_date"].notna()].copy()
    if df.empty:
        err("No hay fechas validas en 'fecha'.")

    def iso_key(d):
        y, w, _ = d.isocalendar(); return (y, w)
    def iso_label(d):
        return "W" + str(d.isocalendar()[1])
    df["_isokey"] = df["_date"].map(iso_key)
    df["_week"] = df["_date"].map(iso_label)

    max_date = max(df["_date"])
    cur_key = iso_key(max_date)
    cur_label = iso_label(max_date)

    all_keys = sorted(set(df["_isokey"]))
    keep_keys = all_keys[-WEEKS_TO_SHOW:]
    keep_set = set(keep_keys)
    key_to_label = {k: ("W" + str(k[1])) for k in keep_keys}
    week_order = [key_to_label[k] for k in keep_keys]
    week_label = {}
    for k in keep_keys:
        lbl = key_to_label[k]
        week_label[lbl] = (lbl + " - Actual") if k == cur_key else lbl

    print("Ciudades encontradas: " + ", ".join(sorted(set(df["_city"]))))
    print("Semanas mostradas: " + ", ".join(week_order) + "   (en curso: " + cur_label + ")\n")

    cols = {
        "deliv": "total_deliveries_completed", "assigned": "total_assigned_orders",
        "reassign": "total_reassigned_orders", "not_seen": "total_orders_reassigned_not_seen",
        "ignored": "total_orders_reassigned_ignored", "decline": "total_orders_reassigned_decline",
        "redispatch": "total_orders_reassigned_redispatch", "cnm": "total_orders_reassigned_cnm",
        "agent": "total_orders_reassigned_agent", "stacked": "total_stacked_deliveries",
        "over10": "total_deliveries_over_10_min", "cdt_num": "courier_delivery_time_num",
        "cdt_den": "courier_delivery_time_den", "worked": "total_worked_hours",
        "inelig": "total_ineligibility_hrs", "atcust": "at_customer_min",
        "busy": "transition_busy_time", "working": "transition_working_time",
        "cancelled": "total_cancelled_deliveries", "noshows": "total_no_shows", "booked": "total_booked_shifts",
        "capu": "total_fraud_capu_count", "undel": "total_fraud_undelivered_count",
        "absent": "total_fraud_customer_absent_count", "fraudcost": "total_fraud_cost_eur",
    }
    if "total_assigned_orders" not in df.columns and "total_orders_assigned" in df.columns:
        cols["assigned"] = "total_orders_assigned"
    if "total_reassigned_orders" not in df.columns and "total_orders_reassigned" in df.columns:
        cols["reassign"] = "total_orders_reassigned"
    for short, real in cols.items():
        df["_" + short] = num(df, real, pd)
    if "vehicle_type" not in df.columns:
        df["vehicle_type"] = ""

    def veh_of(g):
        m = g["vehicle_type"].mode()
        return str(m.iloc[0]) if len(m) else ""

    # SEMANAL
    weekly = []
    dfx = df[df["_isokey"].isin(keep_set)]
    gkeys = ["rider_id", "_city", "_isokey"] if "rider_id" in df.columns else ["_city", "_isokey"]
    for kv, g in dfx.groupby(gkeys):
        rider = str(kv[0]) if "rider_id" in df.columns else "-"
        city = str(kv[-2]); key = kv[-1]
        S = {s: float(g["_" + s].sum()) for s in cols}
        rec = {"city": city, "vehicle": veh_of(g), "rider": rider, "week": key_to_label[key]}
        rec.update(metrics_from_sums(S))
        # recuentos brutos: el Resumen de performance agrega RR % y No Show % con ellos
        rec["_assigned"], rec["_reassign"], rec["_ns"], rec["_bk"] = S["assigned"], S["reassign"], S["noshows"], S["booked"]
        weekly.append(rec)

    # DIARIO (semana en curso)
    daily = []
    dcur = df[df["_isokey"] == cur_key]
    cur_dates = sorted(set(dcur["_date"]))
    cwrange = ""
    if cur_dates:
        cwrange = cur_label + " - " + cur_dates[0].strftime("%d/%m") + "-" + cur_dates[-1].strftime("%d/%m")
    dkeys = ["rider_id", "_city", "_date"] if "rider_id" in df.columns else ["_city", "_date"]
    for kv, g in dcur.groupby(dkeys):
        rider = str(kv[0]) if "rider_id" in df.columns else "-"
        city = str(kv[-2]); d = kv[-1]
        S = {s: float(g["_" + s].sum()) for s in cols}
        m = metrics_from_sums(S)
        daily.append({
            "rider": rider, "city": city, "date": d.isoformat(),
            "day": DIAS_ES[d.weekday()] + " " + d.strftime("%d/%m"),
            "delivered": m["delivered"], "undelivered": m["undelivered"],
	    "_noshows": m["_noshows"],
            "capu": m["capu"], "wtd10": m["wtd10"], "reassign": m["reassign"],
            "deliveryTime": m["deliveryTime"], "wtd": m["wtd"],
            "workingHours": m["workingHours"], "utr": m["utr"], "incidents": m["slInc"],
            "_assigned": S["assigned"], "_reassign": S["reassign"], "_ns": S["noshows"], "_bk": S["booked"],
        })

    def escribir(cities, template_path, salida_nombre):
        recs = [r for r in weekly if r["city"] in cities]
        drecs = [r for r in daily if r["city"] in cities]
        if not recs and not drecs:
            print("Sin datos para " + str(cities) + " -> no genero " + salida_nombre)
            return
        recs.sort(key=lambda r: (r["city"], r["rider"], r["week"]))
        tpl = open(template_path, encoding="utf-8").read()
        tpl = tpl.replace("__DATA__", json.dumps(recs, ensure_ascii=False))
        tpl = tpl.replace("__WEEK_ORDER__", json.dumps(week_order, ensure_ascii=False))
        tpl = tpl.replace("__WEEK_LABEL__", json.dumps(week_label, ensure_ascii=False))
        tpl = tpl.replace("__DAILY__", json.dumps(drecs, ensure_ascii=False))
        tpl = tpl.replace("__CWLABEL__", cur_label)
        tpl = tpl.replace("__CWRANGE__", cwrange)
        if _apply_race_trend:
            try:
                tpl = _apply_race_trend(tpl)   # Delivery Race -> tendencia por rider x semana
            except Exception as _e:
                print("  (aviso) no apliqué el Delivery Race de tendencia: " + str(_e))
        if _apply_perf:
            try:
                tpl = _apply_perf(tpl)         # filtro de métrica en el Resumen + definiciones
            except Exception as _e:
                print("  (aviso) no apliqué el filtro de métricas del Resumen: " + str(_e))
        if _heat:
            try:
                heat_html, heat_res = _heat.construir_html(cities, WEEKS_TO_SHOW, sello=False)
                tpl = _heat.integrar_en_dashboard(tpl, heat_html)
                print("  + pestaña Mapas de calor: " + heat_res)
            except Exception as _e:
                print("  (aviso) sin pestaña Mapas de calor: " + str(_e))
        if _utr:
            try:
                utr_html, utr_res = _utr.construir_html(cities, WEEKS_TO_SHOW, sello=False)
                tpl = _utr.integrar_en_dashboard(tpl, utr_html)
                print("  + pestaña UTR: " + utr_res)
            except Exception as _e:
                print("  (aviso) sin pestaña UTR: " + str(_e))
        if _ns:
            try:
                ns_html, ns_res = _ns.construir_html(cities, WEEKS_TO_SHOW, sello=False)
                tpl = _ns.integrar_en_dashboard(tpl, ns_html)
                print("  + pestaña No show: " + ns_res)
            except Exception as _e:
                print("  (aviso) sin pestaña No show: " + str(_e))
        if _cap:
            try:
                cap_html, cap_res = _cap.construir_html(cities, WEEKS_TO_SHOW, sello=False)
                tpl = _cap.integrar_en_dashboard(tpl, cap_html)
                print("  + pestaña Capacidad: " + cap_res)
            except Exception as _e:
                print("  (aviso) sin pestaña Capacidad: " + str(_e))
        if _vivo:
            try:
                vivo_html, vivo_res = _vivo.construir_html(cities, WEEKS_TO_SHOW, sello=False)
                tpl = _vivo.integrar_en_dashboard(tpl, vivo_html)
                print("  + pestaña En vivo: " + vivo_res)
            except Exception as _e:
                print("  (aviso) sin pestaña En vivo: " + str(_e))
        if _cpi:
            try:
                cpi_html, cpi_res = _cpi.construir_html(cities, WEEKS_TO_SHOW, sello=False)
                tpl = _cpi.integrar_en_dashboard(tpl, cpi_html)
                print("  + pestaña Códigos postales: " + cpi_res)
            except Exception as _e:
                print("  (aviso) sin pestaña Códigos postales: " + str(_e))
        if _wtdr:
            try:
                wtd_html, wtd_res = _wtdr.construir_html(cities, WEEKS_TO_SHOW, sello=False)
                tpl = _wtdr.integrar_en_dashboard(tpl, wtd_html)
                print("  + pestaña WTD%: " + wtd_res)
            except Exception as _e:
                print("  (aviso) sin pestaña WTD%: " + str(_e))
        if _wtdv1:
            try:
                v1_html, v1_res = _wtdv1.construir_html(cities, WEEKS_TO_SHOW, sello=False)
                tpl = _wtdv1.integrar_en_dashboard(tpl, v1_html)
                print("  + pestaña WTD% v1: " + v1_res)
            except Exception as _e:
                print("  (aviso) sin pestaña WTD% v1: " + str(_e))
        with open(os.path.join(OUTPUT_DIR, salida_nombre), "w", encoding="utf-8") as f:
            f.write(tpl)
        print("OK " + salida_nombre + ": " + str(len(recs)) + " filas semana - " +
              str(len(drecs)) + " filas dia - ciudades " +
              ", ".join(sorted(set(r["city"] for r in recs) | set(r["city"] for r in drecs))))

    escribir(CITIES_SAB, TEMPLATE_SAB, "resumen_flota_riders_SAB.html")
    escribir(CITIES_BIG, TEMPLATE_BIG, "resumen_flota_riders_GRA_MAD_NOM_ALC.html")

    print("\nDashboards en: " + OUTPUT_DIR)
    print("Abrelos con:\n   open \"" + OUTPUT_DIR + "\"\n")


if __name__ == "__main__":
    main()
