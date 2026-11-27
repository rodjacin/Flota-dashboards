#!/usr/bin/env python3
"""
Kometa Delivery Admin · descarga el informe «Reportes > Raw data» de un día operativo de MushDrink.

Hace lo mismo que el botón «Descargar Reporte» de https://mushdrinks-admin.nexus-software.es/#/admin-reports
(pestaña Raw data): inicia sesión con un usuario de la plataforma, pide el informe a la API de informes (v3, asíncrona),
espera a que esté listo en «Solicitudes» y lo descarga.

Credenciales (variables de entorno; en GitHub, Settings → Secrets and variables → Actions → secretos):
    KOMETA_EMAIL, KOMETA_PASSWORD   usuario de la plataforma (mejor uno dedicado, solo con acceso a informes)

Uso:
    python3 automatizacion/kometa_raw_data.py 2026-11-26 [--salida raw.csv] [--desde 07:00]
    python3 automatizacion/kometa_raw_data.py ayer
Ventana: del día D a las 07:00 al día D+1 a las 07:00 (hora de Madrid), la misma del panel.
"""
import argparse, json, os, sys, time, urllib.request, urllib.error
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

TZ = ZoneInfo('Europe/Madrid')
# Configuración pública de la web de administración (bundle main-es2015.*.js)
FIREBASE_API_KEY = 'AIzaSyDA9hyAb_g_kShZmPy6WGMBWK5RPdP2vCk'
ADMIN_ORIGIN = 'https://mushdrinks-admin.nexus-software.es'
API = 'https://europe-west2-mushdrink-delivery-platform.cloudfunctions.net/api_report/v3'
HQ = {'id': 'fkOJLzNsFkTEwV8Z3peH', 'name': 'Mushdrinks'}


def _req(url, data=None, headers=None, method=None, timeout=120):
    h = {'Content-Type': 'application/json', 'Origin': ADMIN_ORIGIN, 'Referer': ADMIN_ORIGIN + '/'}
    h.update(headers or {})
    body = json.dumps(data).encode() if data is not None else None
    req = urllib.request.Request(url, data=body, headers=h, method=method or ('POST' if body is not None else 'GET'))
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read(); ct = r.headers.get('content-type', '')
            return r.status, (json.loads(raw) if 'json' in ct else raw)
    except urllib.error.HTTPError as e:
        sys.exit(f'HTTP {e.code} en {url.split("?")[0]}: {e.read()[:400].decode(errors="replace")}')


def login():
    email, pwd = os.environ.get('KOMETA_EMAIL'), os.environ.get('KOMETA_PASSWORD')
    if not email or not pwd:
        sys.exit('Faltan KOMETA_EMAIL / KOMETA_PASSWORD.')
    _, j = _req(f'https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={FIREBASE_API_KEY}',
                {'email': email, 'password': pwd, 'returnSecureToken': True})
    return {'Authorization': 'Bearer ' + j['idToken'], 'X-User-Id': j['localId']}


def ventana(D, desde='07:00'):
    hh, mm = map(int, desde.split(':'))
    a = datetime.strptime(D, '%Y-%m-%d').replace(hour=hh, minute=mm, tzinfo=TZ)
    b = a + timedelta(days=1)
    return int(a.timestamp() * 1000), int(b.timestamp() * 1000)


def raw_data(D, salida, desde='07:00', espera_max=1800):
    auth = login()
    a, b = ventana(D, desde)
    body = {'report_title': f'Raw data {HQ["name"]} {D} (automático)', 'headquarter': HQ, 'areas': [],
            'start_date': a, 'end_date': b, 'statuses': ['delivered', 'undelivered'], 'report_format': 'raw_data',
            'include_cancelled': False, 'include_integrator_cancelled': False, 'show_duplicates': False,
            'delivery': {'mode': 'async'}}
    _, j = _req(API + '/report/raw-data', body, auth)
    job = j.get('jobId') or j.get('job_id')
    if not job:
        sys.exit(f'La API no devolvió un trabajo: {str(j)[:300]}')
    print(f'Raw data {D}: trabajo {job} en cola')
    t0 = time.time(); st = {}
    while time.time() - t0 < espera_max:
        time.sleep(20)
        _, st = _req(f'{API}/report/jobs/{job}', headers=auth, method='GET')
        s = st.get('status')
        if s == 'done': break
        if s == 'failed': sys.exit(f'El informe falló: {str(st)[:400]}')
    else:
        sys.exit('El informe no estuvo listo a tiempo.')
    url = st.get('downloadUrl')
    if not url or st.get('hasGcsPath'):
        _, d = _req(f'{API}/report/jobs/{job}/download-url', {}, auth)
        url = d.get('downloadUrl')
    with urllib.request.urlopen(url, timeout=300) as r:
        data = r.read()
    if data[:2] == b'PK':                       # si la API devuelve Excel, se guarda como el CSV de la web (';')
        import io, pandas as pd
        pd.read_excel(io.BytesIO(data), dtype=str).to_csv(salida, sep=';', index=False, encoding='utf-8-sig')
    else:
        open(salida, 'wb').write(data)
    print(f'Raw data {D}: {len(data) / 1e6:.1f} MB → {salida}')
    return salida


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('fecha', help="AAAA-MM-DD o 'ayer' (día operativo)")
    ap.add_argument('--salida', default='raw_data.csv')
    ap.add_argument('--desde', default='07:00', help='hora de corte del día operativo')
    a = ap.parse_args()
    D = a.fecha
    if D == 'ayer':
        now = datetime.now(TZ); D = (now - timedelta(days=1 if now.hour >= 7 else 2)).strftime('%Y-%m-%d')
    raw_data(D, a.salida, a.desde)
