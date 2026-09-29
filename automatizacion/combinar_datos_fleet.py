#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
================================================================================
 Combinar los CSV descargados del bucket en ficheros únicos por tipo
================================================================================

Toma la carpeta que generó el primer script (fleet_data), que tiene esta forma:

    fleet_data/
        2026-08-05/batch_number=1/delivery_lv.csv
        2026-08-05/batch_number=1/rider_lv.csv
        2026-08-06/batch_number=1/delivery_lv.csv
        ...

y junta TODOS los ficheros del mismo tipo en uno solo, añadiendo una columna
"fecha" para saber de qué día es cada fila. Resultado:

    fleet_data_combinado/
        delivery_lv_combinado.csv
        rider_lv_combinado.csv
        shift_lv_combinado.csv
        transaction_lv_combinado.csv
        reassignment_lv_combinado.csv

--------------------------------------------------------------------------------
 CÓMO USARLO (solo la primera vez instalas la librería):
--------------------------------------------------------------------------------
    pip3 install pandas

 Y para ejecutarlo:
    python3 combinar_datos_fleet.py
================================================================================
"""

import os
import re
import sys
import glob

# ==============================================================================
#  CONFIGURACIÓN  —  edita SOLO esta sección
# ==============================================================================

# Carpeta con los datos descargados (la que generó el primer script).
INPUT_DIR = os.path.expanduser("~/Downloads/fleet_data")

# Carpeta donde se guardarán los ficheros combinados.
OUTPUT_DIR = os.path.expanduser("~/Downloads/fleet_data_combinado")

# ==============================================================================
#  A partir de aquí NO necesitas tocar nada.
# ==============================================================================

# Patrón para reconocer la fecha (AAAA-MM-DD) dentro de la ruta del fichero.
PATRON_FECHA = re.compile(r"(\d{4}-\d{2}-\d{2})")


def error_salir(mensaje):
    print("\n❌ ERROR: " + mensaje + "\n")
    sys.exit(1)


def main():
    # --- 1) Comprobaciones básicas -------------------------------------------
    if not os.path.isdir(INPUT_DIR):
        error_salir(
            "No encuentro la carpeta de datos:\n   " + INPUT_DIR +
            "\n\n   Ejecuta primero el script de descarga (extraer_datos_fleet.py)."
        )

    try:
        import pandas as pd
    except ImportError:
        error_salir(
            "Falta la librería 'pandas'.\n"
            "   Instálala ejecutando en la Terminal:\n\n"
            "      pip3 install pandas\n\n"
            "   y vuelve a lanzar este script."
        )

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # --- 2) Buscar todos los CSV y agruparlos por tipo -----------------------
    todos = glob.glob(os.path.join(INPUT_DIR, "**", "*.csv"), recursive=True)
    if not todos:
        error_salir("No he encontrado ningún .csv dentro de " + INPUT_DIR)

    # Agrupamos por nombre de fichero (tipo): rider_lv.csv, delivery_lv.csv, ...
    por_tipo = {}
    for ruta in todos:
        tipo = os.path.basename(ruta)          # p.ej. "rider_lv.csv"
        por_tipo.setdefault(tipo, []).append(ruta)

    print("Tipos de fichero encontrados:")
    for tipo, rutas in sorted(por_tipo.items()):
        print("   - {:<24} {} ficheros".format(tipo, len(rutas)))
    print()

    # --- 3) Combinar cada tipo -----------------------------------------------
    resumen = []
    for tipo, rutas in sorted(por_tipo.items()):
        print("Combinando '" + tipo + "' ...")
        trozos = []
        leidos = 0
        fallidos = 0

        for ruta in sorted(rutas):
            # Sacar la fecha de la ruta (AAAA-MM-DD)
            m = PATRON_FECHA.search(ruta)
            fecha = m.group(1) if m else ""
            try:
                df = pd.read_csv(ruta, dtype=str, keep_default_na=False)
            except Exception as e:
                # Reintento tolerante para ficheros con líneas problemáticas
                try:
                    df = pd.read_csv(ruta, dtype=str, keep_default_na=False,
                                     engine="python", on_bad_lines="skip")
                except Exception as e2:
                    print("   ⚠️  no pude leer {} -> {}".format(ruta, repr(e2)))
                    fallidos += 1
                    continue
            if df.empty:
                continue
            # Añadir la columna 'fecha' al principio
            df.insert(0, "fecha", fecha)
            trozos.append(df)
            leidos += 1

        if not trozos:
            print("   (sin datos para este tipo)\n")
            continue

        # Unir todo (une columnas aunque varíen entre días; rellena huecos)
        combinado = pd.concat(trozos, ignore_index=True, sort=False)
        combinado = combinado.sort_values("fecha", kind="stable")

        nombre_salida = tipo.replace(".csv", "_combinado.csv")
        salida = os.path.join(OUTPUT_DIR, nombre_salida)
        combinado.to_csv(salida, index=False)

        print("   ✅ {} filas, {} columnas -> {}".format(
            len(combinado), combinado.shape[1], nombre_salida))
        if fallidos:
            print("   (se saltaron {} fichero(s) ilegibles)".format(fallidos))
        print()

        resumen.append((nombre_salida, len(combinado), leidos))

    # --- 4) Resumen final -----------------------------------------------------
    print("=" * 60)
    print("  RESUMEN")
    print("=" * 60)
    for nombre, filas, ficheros in resumen:
        print("  {:<32} {:>8} filas  ({} días)".format(nombre, filas, ficheros))
    print("=" * 60)
    print("  Carpeta de salida: " + OUTPUT_DIR)
    print("=" * 60)
    print("\n✅ Listo. Ábrela con:\n   open \"" + OUTPUT_DIR + "\"\n")


if __name__ == "__main__":
    main()
