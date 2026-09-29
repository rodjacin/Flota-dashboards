#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
================================================================================
 Extraer datos del bucket de GCP: dhub-glovo-es-external-fleet-mushdrink
================================================================================

Descarga los ficheros del bucket a una carpeta local de tu Mac, conservando la
estructura por fecha (2026-08-05/, 2026-08-06/, ...). Puede reanudarse si se
corta: no vuelve a bajar lo que ya tienes.

--------------------------------------------------------------------------------
 CÓMO USARLO (solo la primera vez instalas la librería):
--------------------------------------------------------------------------------
    pip3 install google-cloud-storage

 Y para ejecutarlo:
    python3 extraer_datos_fleet.py

--------------------------------------------------------------------------------
 SEGURIDAD: este script LEE tu fichero de credenciales desde tu disco local.
 No lo comparte con nadie. Mantén el JSON solo en tu ordenador.
================================================================================
"""

import os
import sys

# ==============================================================================
#  CONFIGURACIÓN  —  edita SOLO esta sección
# ==============================================================================

# Ruta a tu fichero de credenciales (el JSON que guardaste en Descargas).
CREDENTIALS_PATH = os.path.expanduser("~/.gcp/gcp_mushdrink.json")

# Nombre del bucket (no lo cambies salvo que te digan otro).
BUCKET_NAME = "dhub-glovo-es-external-fleet-mushdrink"

# Carpeta local donde se guardarán los datos.
OUTPUT_DIR = os.path.expanduser("~/Downloads/fleet_data")

# --- Filtros opcionales -------------------------------------------------------

# Rango de fechas a descargar (formato "AAAA-MM-DD"). Pon None para no filtrar.
# Ejemplo: DATE_FROM = "2026-08-01"  y  DATE_TO = "2026-08-27"
DATE_FROM = None
DATE_TO = None

# Descargar solo ciertos tipos de fichero. Lista vacía [] = todos.
# Opciones: "delivery_lv.csv", "rider_lv.csv", "shift_lv.csv",
#           "transaction_lv.csv", "reassignment_lv.csv"
ONLY_FILES = []

# Si un fichero ya existe en local con el mismo tamaño, saltarlo (reanudar).
SKIP_EXISTING = True

# ==============================================================================
#  A partir de aquí NO necesitas tocar nada.
# ==============================================================================


def error_salir(mensaje):
    """Imprime un mensaje de error claro y termina el programa."""
    print("\n❌ ERROR: " + mensaje + "\n")
    sys.exit(1)


def main():
    # --- 1) Comprobar que existe el fichero de credenciales -------------------
    if not os.path.isfile(CREDENTIALS_PATH):
        error_salir(
            "No encuentro el fichero de credenciales en:\n   " + CREDENTIALS_PATH +
            "\n\n   Revisa la variable CREDENTIALS_PATH arriba en el script y que "
            "la ruta sea correcta.\n   (Recuerda: en este Mac tu usuario es la carpeta "
            "dentro de /Users/)."
        )

    # --- 2) Importar la librería de Google Cloud Storage ----------------------
    try:
        from google.cloud import storage
    except ImportError:
        error_salir(
            "Falta la librería 'google-cloud-storage'.\n"
            "   Instálala ejecutando en la Terminal:\n\n"
            "      pip3 install google-cloud-storage\n\n"
            "   y vuelve a lanzar este script."
        )

    # --- 3) Conectar con el bucket usando tus credenciales --------------------
    print("Conectando con Google Cloud Storage...")
    try:
        client = storage.Client.from_service_account_json(CREDENTIALS_PATH)
        bucket = client.bucket(BUCKET_NAME)
    except Exception as e:
        error_salir("No se pudo conectar. Detalle técnico:\n   " + repr(e))

    # --- 4) Listar los objetos del bucket -------------------------------------
    print("Listando objetos del bucket '" + BUCKET_NAME + "'...")
    try:
        todos = list(client.list_blobs(BUCKET_NAME))
    except Exception as e:
        error_salir(
            "No se pudieron listar los objetos. Puede ser un problema de permisos "
            "(403) o de nombre de bucket (404).\n   Detalle técnico:\n   " + repr(e)
        )

    # --- 5) Aplicar filtros (fecha / tipo de fichero) -------------------------
    seleccionados = []
    for blob in todos:
        nombre = blob.name

        # Ignorar "carpetas" (marcadores que terminan en /)
        if nombre.endswith("/"):
            continue

        # La fecha es el primer tramo de la ruta: "2026-08-05/rider_lv.csv"
        partes = nombre.split("/")
        fecha = partes[0] if len(partes) > 1 else ""

        # Filtro por rango de fechas (comparación de texto AAAA-MM-DD funciona bien)
        if DATE_FROM is not None and fecha < DATE_FROM:
            continue
        if DATE_TO is not None and fecha > DATE_TO:
            continue

        # Filtro por tipo de fichero
        if ONLY_FILES:
            basename = partes[-1]
            if basename not in ONLY_FILES:
                continue

        seleccionados.append(blob)

    total = len(seleccionados)
    if total == 0:
        print("\n⚠️  No hay objetos que cumplan los filtros indicados. Revisa "
              "DATE_FROM / DATE_TO / ONLY_FILES.\n")
        return

    print("Se van a procesar " + str(total) + " ficheros.\n")

    # --- 6) Descargar ---------------------------------------------------------
    descargados = 0
    saltados = 0
    bytes_bajados = 0

    for i, blob in enumerate(seleccionados, start=1):
        # Ruta local = carpeta de salida + ruta del objeto (mantiene estructura)
        destino = os.path.join(OUTPUT_DIR, blob.name)
        os.makedirs(os.path.dirname(destino), exist_ok=True)

        # Reanudar: si ya existe con el mismo tamaño, saltar
        if SKIP_EXISTING and os.path.isfile(destino):
            try:
                if blob.size is not None and os.path.getsize(destino) == blob.size:
                    saltados += 1
                    print("[{}/{}] ya existe, saltando: {}".format(i, total, blob.name))
                    continue
            except OSError:
                pass  # si falla la comprobación, simplemente lo re-descargamos

        # Descargar
        try:
            blob.download_to_filename(destino)
            descargados += 1
            if blob.size:
                bytes_bajados += blob.size
            print("[{}/{}] descargado: {}".format(i, total, blob.name))
        except Exception as e:
            print("[{}/{}] ⚠️  fallo al descargar {} -> {}".format(
                i, total, blob.name, repr(e)))

    # --- 7) Resumen final -----------------------------------------------------
    mb = bytes_bajados / (1024 * 1024)
    print("\n" + "=" * 60)
    print("  RESUMEN")
    print("=" * 60)
    print("  Descargados nuevos : " + str(descargados))
    print("  Ya existían        : " + str(saltados))
    print("  Total procesados   : " + str(total))
    print("  Tamaño descargado  : {:.1f} MB".format(mb))
    print("  Carpeta de salida  : " + OUTPUT_DIR)
    print("=" * 60)
    print("\n✅ Listo. Puedes abrir la carpeta con:\n   open \"" + OUTPUT_DIR + "\"\n")


if __name__ == "__main__":
    main()
