# -*- coding: utf-8 -*-
"""
MushDrink · añade (o rehace) UN día operativo (07:00 → 06:59) en todas las pestañas de mushdrink/index.html.

Fuente de pedidos (una de las dos):
  · API de Grafana (automático): variables de entorno GRAFANA_URL y GRAFANA_TOKEN (cuenta de servicio con
    permiso de lectura del datasource PostgreSQL de MushDrink). Lee mushdrinks.raw_pickups con todas las horas de
    estado, incluida ordered_at = «Solicitado por el cliente» de Kometa.
  · --pedidos fichero.csv: la misma consulta exportada a CSV (columnas de SQL_PEDIDOS, horas en epoch).

Agregadores (opcional): --resumen «Resumen pedidos-12.xls» «Resumen pedidos-11.xls» ... (del más reciente al más
antiguo: ante Ids repetidos se queda el primero, igual que en las actualizaciones anteriores).

Uso:
    python3 automatizacion/mushdrink_dia.py 2026-11-09                       # API
    python3 automatizacion/mushdrink_dia.py 2026-11-09 --pedidos p.csv --resumen r12.xls r11.xls
    python3 automatizacion/mushdrink_dia.py ayer                             # día operativo de ayer (Madrid)
Después recalcula los tramos 20-23 h de «Repartidores · SLA» (mushdrink_sla_tramos.py).

Reglas (comprobadas contra el 08/11 ya publicado):
  · Pedidos del día = entregados (Entregado + No Localizable) creados entre las 07:00 y las 06:59.
  · Tiempo de pedido = de «Solicitado por el cliente» a entregado; >45 min = >2700 s.
  · Hora del pedido = hora de solicitud del cliente (salvo donde se indica entrega / salida / creación).
"""
import sys, os, re, json, argparse, collections, subprocess
from datetime import datetime, timedelta
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ALIAS = {99954: 13826}          # PLK Plaza Ayuntamiento Valencia: código de Grafana → código del panel
DS_UID = 'efaxfjprp5eyoa'       # datasource PostgreSQL de Grafana MushDrink
HQ = 'fkOJLzNsFkTEwV8Z3peH'     # Matriz MushDrink
SQL_PEDIDOS = """select rz.name zona, rs.store_name tienda, rp.search_id sid, rp.order_code_ab oc, rp.status st,
 rp.undeliverable_reason ur, ru.name rider, ri.name integ, rp.created_at c, rp.ordered_at o, rp.assigned_at asg,
 rp.accepted_at acc, rp.instore_at ins, rp.ongoing_at ong, rp.arrived_at arr, rp.delivered_at del, rp.cancelled_at can,
 rp.total_distance dist
from mushdrinks.raw_pickups rp left join mushdrinks.raw_integrators ri on rp.integrator_id=ri.id
left join mushdrinks.raw_stores rs on rp.store_id=rs.id left join mushdrinks.raw_users ru on rp.driver_id=ru.id
left join mushdrinks.raw_zones rz on rp.zone_id=rz.id
where rp.headquarter_id='{hq}' and rs.is_deleted=false and rp.created_at>={a} and rp.created_at<{b}"""
TIPOS = ['MushDrink', 'Catcher', 'Glovo', 'UberDirect', 'Uber 3P', 'Otras flotas', 'Sin repartidor']


# ----------------------------------------------------------------------------- datos
def ventana(date):
    a = pd.Timestamp(date + ' 07:00', tz='Europe/Madrid')
    return int(a.timestamp()), int((a + pd.Timedelta(days=1)).timestamp())


def pedidos_api(date):
    import urllib.request
    url, tok = os.environ.get('GRAFANA_URL'), os.environ.get('GRAFANA_TOKEN')
    if not url or not tok:
        sys.exit('Faltan GRAFANA_URL / GRAFANA_TOKEN (o usa --pedidos).')
    a, b = ventana(date)
    body = {'queries': [{'refId': 'A', 'datasource': {'type': 'grafana-postgresql-datasource', 'uid': DS_UID},
                         'rawSql': SQL_PEDIDOS.format(hq=HQ, a=a, b=b), 'format': 'table'}], 'from': 'now-24h', 'to': 'now'}
    req = urllib.request.Request(url.rstrip('/') + '/api/ds/query', data=json.dumps(body).encode(),
                                 headers={'Content-Type': 'application/json', 'Authorization': 'Bearer ' + tok})
    j = json.load(urllib.request.urlopen(req, timeout=120))
    f = j['results']['A']['frames'][0]
    names = [x['name'] for x in f['schema']['fields']]
    return pd.DataFrame(dict(zip(names, f['data']['values'])))


def normaliza(db):
    """Filas de raw_pickups → mismas columnas que el CSV «Pedidos en Curso» + t_sol."""
    db = db.copy()
    for k in ['c', 'o', 'asg', 'acc', 'ins', 'ong', 'arr', 'del', 'can']:
        db[k] = pd.to_numeric(db.get(k), errors='coerce')
    ts = lambda s: pd.to_datetime(s, unit='s', utc=True).dt.tz_convert('Europe/Madrid').dt.tz_localize(None)
    est = db.st.map({'delivered': 'Entregado', 'undelivered': 'No Entregado', 'cancel': 'Cancelado'}).fillna(db.st)
    est = est.where(~((db.st == 'delivered') & (db.ur == 'DELIVERED_UNLOCATABLE')), 'No Localizable')
    pend = (db.can.fillna(db.asg).fillna(db.acc) - db.c)
    df = pd.DataFrame({'Zona': db.zona, 'Tienda': db.tienda, 'ID Servicio': db.sid, 'Cód.Pedido': db.oc, 'Estado': est,
                       'Repartidor': db.rider, 'Integrador': db.integ, 'Distancia': db.dist,
                       'T.Pendiente': pend / 60, 'T_Acept': (db.ins - db.acc) / 60, 'T_enTienda': (db.ong - db.ins) / 60,
                       'T_Camino': (db.arr - db.ong) / 60, 'T_Llegó': (db['del'] - db.arr) / 60,
                       'T_Entreg': (db['del'] - db.c) / 60})
    df['t_cre'] = ts(db.c).dt.floor('s')
    df['t_sol'] = ts(db.o).dt.floor('s')
    df['code'] = df.Tienda.str.split().str[0].astype(int)
    df['rc'] = df.code.replace(ALIAS)
    df['id'] = pd.to_numeric(df['Cód.Pedido'], errors='coerce')
    return df


def prep(w):
    w = w[w.Estado.isin(['Entregado', 'No Localizable']) & w.T_Entreg.notna()].copy()
    w['t_del'] = w.t_cre + pd.to_timedelta(w.T_Entreg, unit='m')
    w['tp'] = (w.t_del - w.t_sol).dt.total_seconds()
    w['sol'] = (w.t_cre - w.t_sol).dt.total_seconds()
    w['rep'] = (w.T_Camino.fillna(0) + w['T_Llegó'].fillna(0)) * 60
    w['tie'] = (w.T_Acept.fillna(0) + w.T_enTienda.fillna(0)) * 60
    w['pac'] = w.T_Entreg * 60 - w.tie - w.rep
    w['t_ong'] = w.t_del - pd.to_timedelta(w.rep, unit='s')
    return w[w.t_sol.notna()]


# ----------------------------------------------------------------------------- cálculos por bloque
def ds_rows(w, date, REST):
    dt = pd.Timestamp(date); dow = dt.dayofweek; week = int(dt.isocalendar().week)
    teo = {r['code']: r.get('teoDays') for r in REST}
    out = []
    for c, x in w.groupby('rc'):
        g = x.groupby(x.t_cre.dt.hour).size(); hh = g[g == g.max()].index[-1]
        sh = x.t_sol.dt.hour; dh = x.t_del.dt.hour; m23 = (dh >= 20) & (dh < 23)
        td = teo.get(int(c)); late = int((x.tp > 2700).sum()); n = len(x)
        out.append({"code": int(c), "date": date, "week": week, "dow": int(dow), "orders": n, "late45": late, "lateSum": late,
                    "recepSum": 0, "recepN": 0, "recepGt2": 0, "cocSum": 0, "cocN": 0, "cocGt18": 0,
                    "repSum": int(round(x.rep.sum())), "repN": n, "repGt20": int((x.rep > 1200).sum()),
                    "riders": sorted(x.Repartidor.dropna().unique().tolist()),
                    "realPeak": int(x[x.t_cre.dt.hour == hh].Repartidor.nunique()),
                    "teoDate": (td[dow] if td else None), "forecast": None, "fcPeak": None,
                    "actPeakVol": int(((sh >= 19) & (sh < 23)).sum()),
                    "t2023": [int(x[m23].Repartidor.nunique()), int(m23.sum())], "k": 1,
                    "solSum": int(round(x.sol.sum())), "solN": n, "penSum": 0, "penN": n,
                    "pacSum": int(round(x.pac.sum())), "pacN": n, "tieSum": int(round(x.tie.sum())), "tieN": n,
                    "tpSum": int(round(x.tp.sum())), "tpN": n})
    return out


def multi(w):
    out = []
    for (r, h), x in w.groupby([w.Repartidor, w.t_del.dt.hour]):
        g = x.groupby('rc').size()
        if len(g) >= 2:
            out.append([r, int(h), [[int(c), int(n)] for c, n in sorted(g.items(), key=lambda t: (-t[1], t[0]))]])
    return out


def htavg(x):
    out = []
    for h, y in x.groupby(x.t_sol.dt.hour): out += [int(h), len(y), int(round(y.tp.sum())), int((y.tp > 2700).sum())]
    return out


def hhdata(x):
    out = []
    for sl, y in x.groupby((x.t_sol.dt.hour * 60 + x.t_sol.dt.minute) // 30):
        n = len(y); r = y.rep
        out += [int(sl), n, 0, 0, 0, 0, 0, n, int((r < 900).sum()), int((r > 1200).sum())]
    return out


def wrap_slot(t):
    h = t.dt.hour; h = h.where(h >= 7, h + 24)
    return (h * 60 + t.dt.minute) // 30


def ec_h(allx, RIDX):
    allx = allx[allx.Estado.isin(['Entregado', 'No Localizable', 'No Entregado'])].copy()
    allx['rep'] = (allx.T_Camino.fillna(0) + allx['T_Llegó'].fillna(0)) * 60
    out = []
    for h, y in allx.groupby(allx.t_cre.dt.hour):
        v = y[(y.Estado != 'No Entregado') & (y.rep <= 7200)]
        out.append([int(h), len(y), int((y.Estado == 'No Entregado').sum()), len(v), int(round((v.rep / 6).sum())),
                    int((v.rep > 1200).sum()), [RIDX[r] for r in sorted(set(y.Repartidor.dropna())) if r in RIDX]])
    return out


def agrupa(x, gap=120):
    """Salidas (En camino) del mismo rider y restaurante con <2 min respecto a la primera del grupo."""
    groups = []
    for _, y in x.sort_values('t_ong').groupby(['Repartidor', 'rc']):
        cur = []; t0 = None
        for _, o in y.iterrows():
            if cur and (o.t_ong - t0).total_seconds() < gap: cur.append(o)
            else:
                if cur: groups.append(cur)
                cur = [o]; t0 = o.t_ong
        if cur: groups.append(cur)
    C = collections.defaultdict(lambda: [0, 0])
    for g in groups:
        k = (g[0].t_ong.hour, min(len(g), 4)); C[k][0] += 1; C[k][1] += sum(1 for o in g if o.tp > 2700)
    return C


def tipo(r):
    if not isinstance(r, str) or not r.strip(): return 6
    s = r.lower()
    if 'mushdrink' in s or s.startswith('mud'): return 0
    if 'catcher' in s: return 1
    if 'motorista glovo' in s: return 2
    if 'uber direct' in s: return 3
    if 'motorista uber' in s: return 4
    return 5


# ----------------------------------------------------------------------------- html
def J(v): return json.dumps(v, ensure_ascii=False, separators=(',', ':'))


def getv(d, name):
    m = re.search(r'(?:const|let|var)\s+' + name + r'\s*=\s*', d)
    return json.JSONDecoder().raw_decode(d[m.end():])[0]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('fecha', help="AAAA-MM-DD o 'ayer'")
    ap.add_argument('--pedidos', help='CSV con la consulta SQL_PEDIDOS (si no, API de Grafana)')
    ap.add_argument('--resumen', nargs='*', default=[], help='«Resumen pedidos» .xls, del más reciente al más antiguo')
    ap.add_argument('--html', default=os.path.join(HERE, '..', 'mushdrink', 'index.html'))
    a = ap.parse_args()
    D = a.fecha
    if D == 'ayer':
        now = pd.Timestamp.now(tz='Europe/Madrid')
        D = (now - pd.Timedelta(days=1 if now.hour >= 7 else 2)).strftime('%Y-%m-%d')
    dt = pd.Timestamp(D); WK = int(dt.isocalendar().week); DOW = int(dt.dayofweek); DM = dt.strftime('%d/%m')
    GEN = pd.Timestamp.now(tz='Europe/Madrid').strftime('%Y-%m-%d')

    db = pd.read_csv(a.pedidos) if a.pedidos else pedidos_api(D)
    raw = normaliza(db)
    t0 = dt + pd.Timedelta(hours=7)
    raw = raw[(raw.t_cre >= t0) & (raw.t_cre < t0 + pd.Timedelta(days=1))]
    w = prep(raw)
    if not len(w): sys.exit(f'Sin pedidos entregados para {D}.')
    codes = sorted(w.rc.unique()); by = {c: w[w.rc == c] for c in codes}
    print(f'{D}: {len(w)} pedidos entregados en {len(codes)} restaurantes · {(w.tp > 2700).mean() * 100:.1f}% >45 min')

    html = open(a.html, encoding='utf-8').read()
    i0 = html.index('const DOCS=') + len('const DOCS=')
    docs, e0 = json.JSONDecoder().raw_decode(html[i0:])

    def setv(k, name, fn):
        d = docs[k]; m = re.search(r'(?:const|let|var)\s+' + name + r'\s*=\s*', d)
        v, e = json.JSONDecoder().raw_decode(d[m.end():])
        docs[k] = d[:m.end()] + J(fn(v)) + d[m.end() + e:]

    def add_date(lst):
        if D not in lst: lst.append(D); lst.sort()
        return lst

    # doc3 · Operativa restaurantes
    DSv = getv(docs[3], 'DS'); NAME = {r['code']: r['name'] for r in DSv['restaurants']}
    ROWS = sorted(ds_rows(w, D, DSv['restaurants']), key=lambda r: r['code'])
    def f_ds(v):
        add_date(v['meta']['dates'])
        if WK not in v['meta']['weeks']: v['meta']['weeks'].append(WK)
        v['rows'] = [r for r in v['rows'] if r['date'] != D] + ROWS
        return v
    setv(3, 'DS', f_ds)
    def f_avhd(v):
        out = {}
        for c in codes:
            L = []
            for _, o in by[c].sort_values('t_cre').iterrows():
                ca = None if pd.isna(o.T_Acept) or pd.isna(o.T_enTienda) else [int(round(o.T_Acept * 60)), int(round(o.T_enTienda * 60))]
                L.append([int(o.id) if pd.notna(o.id) else None, o.t_sol.strftime('%Y-%m-%d %H:%M:%S'),
                          o.t_cre.strftime('%Y-%m-%d %H:%M:%S'), int(round(o.sol)), ca, int(round(o.tp)), int(round(o.pac))])
            out[str(c)] = L
        v[D] = out
        return v
    setv(3, 'AVHD', f_avhd)
    def f_hh(v):
        for c in codes: v['H'].setdefault(str(c), {})[D] = hhdata(by[c])
        v['dow'][D] = DOW; return v
    setv(3, 'HHDATA', f_hh)
    def f_ht(v):
        for c in codes: v['H'].setdefault(str(c), {})[D] = htavg(by[c])
        v['dow'][D] = DOW; add_date(v['dates']); return v
    setv(3, 'HTAVG', f_ht)

    # doc0 · Resumen
    def f_rs(v):
        add_date(v['dates']); v['week'][D] = WK; v['dow'][D] = DOW
        v['d3'][D] = [[r['code'], r['orders'], r['late45'], len(r['riders']), r['realPeak'], r['actPeakVol'], r['fcPeak'],
                       r['t2023'][0], r['t2023'][1], r['repSum'], r['repN']] for r in ROWS]
        L = {}
        for c in codes:
            x = by[c]; x = x[(x.tp > 2700) & (x.tie <= 7200)]
            if len(x): L[str(c)] = [len(x), int((x.tie > 720).sum())]
        v['l45ac'][D] = L; v['multi'][D] = multi(w)
        R, P = {}, {}
        for c in codes:
            x = by[c]
            R[str(c)] = [len(x), int(round(x.tp.sum())), int((x.tp > 2700).sum())]
            P[str(c)] = {r: [len(y), int(round(y.tp.sum())), int((y.tp > 2700).sum())] for r, y in x.groupby('Repartidor')}
        v['perf'][D] = {'R': R, 'P': P}; v['generated'] = GEN
        return v
    setv(0, 'RS', f_rs)

    # doc1 · Repartidores · SLA (ventana 19-23 h por hora de solicitud)
    KNOWN = set(getv(docs[2], 'AGG')['riders'])
    def f_data(v):
        ya = any(p[2] == DM and p[0] == WK for s in v['series'].values() for p in s)   # re-ejecución: no sumar dos veces
        m = (w.t_sol.dt.hour >= 19) & (w.t_sol.dt.hour < 23); x = w[m].assign(nm=w[m].rc.map(NAME))
        to = tl = 0; tsum = 0.0
        for nm, y in x.groupby('nm'):
            if nm not in v['series']: continue
            s = v['series'][nm]; s[:] = [p for p in s if not (p[2] == DM and p[0] == WK)]
            o, l = len(y), int((y.tp > 2700).sum())
            s.append([WK, DOW, DM, int(y.Repartidor.nunique()), o, l, round(y.tp.mean() / 60, 1)])
            if not ya:
                ad = v['allDays'][nm]
                ad['avg'] = round((ad['avg'] * ad['orders'] + y.tp.sum() / 60) / (ad['orders'] + o), 1)
                ad['orders'] += o; ad['o45'] += l; ad['drivers'] += len(set(y.Repartidor.dropna()) - KNOWN)
            to += o; tl += l; tsum += y.tp.sum() / 60
        if not ya:
            ov = v['overall']; ov['avg'] = round((ov['avg'] * ov['orders'] + tsum) / (ov['orders'] + to), 1)
            ov['orders'] += to; ov['o45'] += tl; ov['drivers'] += len(set(x.Repartidor.dropna()) - KNOWN)
        for k in (v['meta']['weeks'], v['weeks']):
            if WK not in k: k.append(WK)
        if pd.Timestamp(D) >= pd.to_datetime(v['meta']['date_max'], dayfirst=True):
            v['meta']['date_max'] = dt.strftime('%d/%m/%Y')
        return v
    setv(1, 'DATA', f_data)

    # doc2 · Pedidos por rider · 15 min
    def f_agg(v):
        RI = {r: i for i, r in enumerate(v['riders'])}
        for r in sorted(set(w.Repartidor.dropna())):
            if r not in RI: RI[r] = len(v['riders']); v['riders'].append(r)
        for c in codes:
            x = by[c]; v['names'].setdefault(str(c), NAME.get(c, str(c)))
            g = x.assign(s=(x.t_sol.dt.hour * 60 + x.t_sol.dt.minute) // 15).groupby(['s', 'Repartidor']).size()
            v['data'][f'{c}|{D}'] = [z for (sl, r), n in g.items() for z in (RI[r], int(sl), int(n))]
        return v
    setv(2, 'AGG', f_agg)
    def f_sl(v):
        for c in codes:
            x = by[c]; fl = []
            for sl, y in x.groupby((x.t_sol.dt.hour * 60 + x.t_sol.dt.minute) // 30):
                fl += [int(sl), len(y), 0, 0, 0, 0, 0, 0, len(y), int(round(y.rep.sum())), int((y.rep > 1200).sum()), int((y.tp > 2700).sum())]
            v[f'{c}|{D}'] = fl
        return v
    setv(2, 'SL30', f_sl)

    # doc4 · Entregados ilocalizables
    def f_il(v):
        add_date(v['dates']); v['week'][D] = WK
        RT = {r: int(n) for r, n in w.groupby('Repartidor').size().items()}
        v['RT'][D] = RT; v['OC'][D] = {str(c): len(by[c]) for c in codes}
        v['D'][D] = {str(c): [[r, int(n), RT.get(r, 0)] for r, n in y.groupby('Repartidor').size().items()]
                     for c, y in w[w.Estado == 'No Localizable'].groupby('rc')}
        v['generated'] = GEN; return v
    setv(4, 'IL', f_il)

    # doc5 · Simulador (salidas reales de cocina)
    def f_sim(v):
        add_date(v['dates']); v['dow'][D] = DOW; v['week'][D] = WK
        v['R'][D] = {str(c): [z for s, n in wrap_slot(by[c].t_ong).value_counts().sort_index().items() for z in (int(s), int(n))] for c in codes}
        v['generated'] = GEN; return v
    setv(5, 'SIM', f_sim)

    # doc6 · Pedidos por repartidor
    def f_pr(v):
        add_date(v['dates']); v['dow'][D] = DOW; v['week'][D] = WK; R = {}
        for c in codes:
            x = by[c]; m = (x.t_del.dt.hour >= 20) & (x.t_del.dt.hour < 23)
            fl = [len(x), int(x.Repartidor.nunique()), int(m.sum()), int(x[m].Repartidor.nunique())]
            for sl, y in x.groupby(wrap_slot(x.t_del)): fl += [int(sl), len(y), int(y.Repartidor.nunique())]
            R[str(c)] = fl
        v['R'][D] = R; v['generated'] = GEN; return v
    setv(6, 'PR', f_pr)

    # doc8 · Grafana / Kometa tiempos por estado (décimas de minuto)
    def f_km(v):
        add_date(v['dates']); v['dow'][D] = DOW; v['week'][D] = WK
        v['R'][D] = {str(c): [len(by[c]), int(round(by[c].pac.mean() / 6)), int(round(by[c].T_Acept.fillna(0).mean() * 10)),
                              int(round(by[c].T_enTienda.fillna(0).mean() * 10))] for c in codes}
        v['generated'] = GEN; return v
    setv(8, 'KM', f_km)

    # doc9 · Nº pedidos/hora
    def f_ec(v):
        add_date(v['dates']); v['dow'][D] = DOW; v['week'][D] = WK
        RI = {r: i for i, r in enumerate(v['riders'])}
        for r in sorted(set(raw.Repartidor.dropna())):
            if r not in RI: RI[r] = len(v['riders']); v['riders'].append(r)
        for c in codes:
            x = by[c]
            v['X'].setdefault(str(c), {})[D] = [len(x), int(round(x.sol.sum())), len(x), int(round(x.tie.sum())), len(x), int(round((x.pac / 6).sum()))]
            v['L45'].setdefault(str(c), {})[D] = [len(x), int((x.tp > 2700).sum())]
            v['H'].setdefault(str(c), {})[D] = ec_h(raw[raw.rc == c], RI)
            v['names'].setdefault(str(c), NAME.get(c, str(c)))
        v['generated'] = GEN; return v
    setv(9, 'EC', f_ec)

    # doc10 · Horas valle (hora de entrega)
    def f_hv(v):
        add_date(v['dates']); v['dow'][D] = DOW
        RI = {r: 950000 + i for i, r in enumerate(sorted(set(w.Repartidor.dropna())))}
        for c in codes:
            x = by[c]
            v['H'].setdefault(str(c), {})[D] = [[int(h), len(y), sorted(RI[r] for r in set(y.Repartidor.dropna()))]
                                                 for h, y in x.groupby(x.t_del.dt.hour)]
        v['generated'] = GEN; return v
    setv(10, 'PR', f_hv)

    # doc12 · Agregadores
    if a.resumen:
        fr = [pd.read_excel(f, header=0, dtype=str) for f in a.resumen]
        rdf = pd.concat(fr, ignore_index=True)
        rdf = rdf[rdf['Código'].notna() & rdf.Confirmado.notna()].copy()
        rdf['t'] = pd.to_datetime(rdf.Confirmado, format='%d/%m/%Y %H:%M:%S', errors='coerce')
        x = rdf[(rdf.t >= t0) & (rdf.t < t0 + pd.Timedelta(days=1))]
        x = x[~x['Fallo de Entrega'].fillna('').str.startswith('Cancelado')].drop_duplicates('Id')
        x = x.assign(code=x['Código'].astype(int).astype(str), tp=x.Repartidor.map(tipo), h=x.t.dt.hour)
        hk = lambda h: h + 24 if h < 7 else h
        def f_ag(v):
            out = {}
            for c, y in x.groupby('code'):
                g = y.groupby(['tp', 'h']).size()
                out[c] = [z for (tp, h), n in sorted(g.items(), key=lambda t: (hk(t[0][1]), t[0][0])) for z in (int(tp), int(h), int(n))]
                if c not in v['names']:
                    v['names'][c] = y.Restaurante.iloc[0]; v['brand'][c] = 'PLK' if 'plk' in y.Restaurante.iloc[0].lower() else 'BK'
                    v['owner'][c] = ''; v['zona'][c] = ''
            v['D'][D] = out; add_date(v['dates']); v['generated'] = GEN
            print(f'Agregadores: {len(x)} pedidos en {len(out)} restaurantes')
            return v
        setv(12, 'AG', f_ag)
    else:
        print('Agregadores: sin «Resumen pedidos», no se toca.')


    # Recepción / cocina por franja de 30 min (pestaña «Pedidos por rider · 15 min» y franjas de Operativa), desde los Resumen
    if a.resumen:
        rr = rdf[~rdf['Fallo de Entrega'].fillna('').str.startswith('Cancelado')].drop_duplicates('Id')
        rr = rr[rr.Repartidor.map(tipo) == 0]
        rr = rr[(rr.t >= t0) & (rr.t < t0 + pd.Timedelta(days=1))].copy()
        sec = lambda s: pd.to_timedelta(s, errors='coerce').dt.total_seconds()
        rr['rec'] = sec(rr['Tiempo en recepción']); rr['coc'] = sec(rr['Tiempo en producción'])
        rr['code'] = rr['Código'].astype(int).replace(ALIAS); rr['s'] = (rr.t.dt.hour * 60 + rr.t.dt.minute) // 30
        G = {}
        for (c, s_), y in rr.groupby(['code', 's']):
            rc = y[y.rec.notna()]; cc = y[y.coc.notna()]
            G[(c, s_)] = [len(rc), int(round(rc.rec.sum())), int((rc.rec > 120).sum()), int((rc.rec <= 120).sum()),
                          len(cc), int(round(cc.coc.sum())), int((cc.coc > 1080).sum()), int((cc.coc < 720).sum()),
                          int(((y.rec.fillna(0) + y.coc) > 2700).sum())]
        def f_sl2(v):
            for k, arr in v.items():
                c, dd = k.split('|')
                if dd != D: continue
                for j in range(0, len(arr), 12):
                    g = G.get((int(c), arr[j]))
                    if g: arr[j + 2:j + 8] = [g[0], g[1], g[2], g[4], g[5], g[6]]
            return v
        setv(2, 'SL30', f_sl2)
        def f_x45(v):
            for k in [k for k in v if k.endswith('|' + D)]: del v[k]
            for (c, s_), g in G.items():
                if g[8]: v.setdefault(f'{c}|{D}', []).extend([int(s_), g[8]])
            return v
        setv(2, 'X45', f_x45)
        def f_hh2(v):
            for c, dd in v['H'].items():
                arr = dd.get(D)
                if not arr: continue
                for j in range(0, len(arr), 10):
                    g = G.get((int(c), arr[j]))
                    if g: arr[j + 2:j + 7] = [g[0], g[3], g[4], g[7], g[6]]
            return v
        setv(3, 'HHDATA', f_hh2)

    # doc7 · Mapa (% >45 por restaurante y día)
    d7 = docs[7]; m7 = re.search(r'const D=(?=\{"coords")', d7)
    v7, e7 = json.JSONDecoder().raw_decode(d7[m7.end():]); L = v7['L']
    if D not in L['dates']:
        L['dates'].append(D); idx = len(L['dates']) - 1
        for r in ROWS: L['R'].setdefault(str(r['code']), []).extend([idx, r['orders'], r['late45']])
    docs[7] = d7[:m7.end()] + J(v7) + d7[m7.end() + e7:]

    # doc15 · Agrupación de pedidos
    def f_agr(v):
        add_date(v['dates']); v['dow'][D] = DOW; v['week'][D] = WK
        hk = lambda h: h + 24 if h < 7 else h; R = {}
        for c in codes:
            C = agrupa(by[c])
            R[str(c)] = [z for (h, s), (n, l) in sorted(C.items(), key=lambda t: (hk(t[0][0]), t[0][1])) for z in (int(h), int(s), int(n), int(l))]
        v['R'][D] = R; v['generated'] = GEN; return v
    setv(15, 'AGR', f_agr)

    out = html[:i0] + json.dumps(docs, ensure_ascii=False).replace('</', '<\\/') + html[i0 + e0:]
    out = re.sub(r'<span class="updated">actualizado [0-9-]+</span>', f'<span class="updated">actualizado {GEN}</span>', out)
    open(a.html, 'w', encoding='utf-8').write(out)
    subprocess.run([sys.executable, os.path.join(HERE, 'mushdrink_sla_tramos.py'), a.html], check=True)


if __name__ == '__main__':
    main()
