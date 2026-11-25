# -*- coding: utf-8 -*-
"""
MushDrink · datos por pedido para el análisis «Stacking: el rider prioriza agrupar sobre el tiempo»
(pestaña «Agrupación de pedidos», variable STK).

Por cada pedido entregado del día operativo se guarda: rider, segundo de Aceptado, de En camino y de Entregado
(desde las 07:00 del día operativo), si superó 45 min y el nº de pedido. La agrupación (ventana de aceptación y diferencia de
En camino) se calcula en la página, con umbrales editables (por defecto <3 min y >7 min).

Uso suelto (rellenar un día desde un CSV ya convertido a «Pedidos en Curso»):
    python3 automatizacion/mushdrink_stacking.py 2026-11-24 pedidos.csv [mushdrink/index.html]
Desde mushdrink_dia.py se llama a stk_set(docs, D, w) en cada actualización diaria.
"""
import sys, os, re, json
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
J = lambda v: json.dumps(v, ensure_ascii=False, separators=(',', ':'))
F = 6                                   # campos por pedido: rider, aceptado, en camino, >45, nº pedido, entregado
INIT = {"riders": [], "dates": [], "D": {}}


def stk_day(w, D, riders):
    """w = pedidos ya preparados (prep() de mushdrink_dia): t_cre, pac, t_ong, tp, Repartidor, rc, id."""
    t0 = pd.Timestamp(D) + pd.Timedelta(hours=7)
    x = w[w.Repartidor.notna()].copy()
    x['acc'] = x.t_cre + pd.to_timedelta(x.pac, unit='s')
    x = x[x.acc.notna() & x.t_ong.notna()]
    RI = {r: i for i, r in enumerate(riders)}
    out = {}
    for c, y in x.sort_values('acc').groupby('rc'):
        L = []
        for _, o in y.iterrows():
            r = o.Repartidor
            if r not in RI: RI[r] = len(riders); riders.append(r)
            L += [RI[r], int((o.acc - t0).total_seconds()), int((o.t_ong - t0).total_seconds()),
                  int(o.tp > 2700), int(o.id) if pd.notna(o.id) else 0, int((o.t_del - t0).total_seconds())]
        out[str(int(c))] = L
    return out


def stk_set(docs, D, w, k=15):
    d = docs[k]
    m = re.search(r'const STK\s*=\s*', d)
    if m:
        v, e = json.JSONDecoder().raw_decode(d[m.end():])
    else:
        v, e = json.loads(J(INIT)), None
    v['D'][D] = stk_day(w, D, v['riders'])
    ds = re.search(r'const DS\s*=\s*', docs[3])
    if ds:                                   # nombre y marca de los restaurantes que no están en AGR (p. ej. 13826)
        R = json.JSONDecoder().raw_decode(docs[3][ds.end():])[0]['restaurants']
        v['names'] = {str(r['code']): r['name'] for r in R}
        v['brand'] = {str(r['code']): ('PLK' if 'plk' in r['name'].lower() else 'BK') for r in R}
        v['owner'] = {str(r['code']): r.get('owner') or '' for r in R}
    if D not in v['dates']: v['dates'].append(D); v['dates'].sort()
    if m:
        docs[k] = d[:m.end()] + J(v) + d[m.end() + e:]
    else:
        a = d.index('const AGR')
        docs[k] = d[:a] + 'const STK = ' + J(v) + ';\n' + d[a:]
    return sum(len(L) // F for L in v['D'][D].values())


def pin_set(docs, D, w, k=15):
    """Tiempo de comprobación de recogida (PIN: desde que se pide el código hasta que el rider lo introduce) por pedido,
    variable PIN de la pestaña: {dates, D: {fecha: {código: [rider, segundos, …]}}} con los índices de rider de STK.
    Solo si los pedidos traen la columna T_Comprob (export de Torre de Control con «T. COMPROBACIÓN DE RECOGIDA»)."""
    if 'T_Comprob' not in w.columns or w.T_Comprob.notna().sum() == 0:
        return 0
    d = docs[k]
    ms = re.search(r'const STK\s*=\s*', d); stk, es = json.JSONDecoder().raw_decode(d[ms.end():])
    RI = {r: i for i, r in enumerate(stk['riders'])}
    x = w[w.Repartidor.notna() & w.T_Comprob.notna()]
    out = {}
    for c, y in x.groupby('rc'):
        L = []
        for _, o in y.iterrows():
            r = o.Repartidor
            if r not in RI: RI[r] = len(stk['riders']); stk['riders'].append(r)
            L += [RI[r], int(round(o.T_Comprob * 60))]
        out[str(int(c))] = L
    d = d[:ms.end()] + J(stk) + d[ms.end() + es:]
    m = re.search(r'const PIN\s*=\s*', d)
    if m:
        v, e = json.JSONDecoder().raw_decode(d[m.end():])
    else:
        v, e = {"dates": [], "D": {}}, None
    v['D'][D] = out
    if D not in v['dates']: v['dates'].append(D); v['dates'].sort()
    if m:
        d = d[:m.end()] + J(v) + d[m.end() + e:]
    else:
        a = d.index('const AGR')
        d = d[:a] + 'const PIN = ' + J(v) + ';\n' + d[a:]
    docs[k] = d
    return sum(len(L) // 2 for L in out.values())


if __name__ == '__main__':
    sys.path.insert(0, HERE)
    import mushdrink_dia as M
    D, csv = sys.argv[1], sys.argv[2]
    P = sys.argv[3] if len(sys.argv) > 3 else os.path.join(HERE, '..', 'mushdrink', 'index.html')
    db = pd.read_csv(csv)
    raw = M.normaliza_curso(db) if 'Fec.solicitado' in db.columns else M.normaliza(db)
    t0 = pd.Timestamp(D) + pd.Timedelta(hours=7)
    raw = raw[(raw.t_cre >= t0) & (raw.t_cre < t0 + pd.Timedelta(days=1)) & raw.Estado.isin(['Entregado', 'No Localizable'])]
    w = M.prep(raw)
    h = open(P, encoding='utf-8').read()
    i = h.index('const DOCS=') + len('const DOCS=')
    docs, e = json.JSONDecoder().raw_decode(h[i:])
    n = stk_set(docs, D, w)
    print(f'PIN {D}: {pin_set(docs, D, w)} pedidos con tiempo de comprobación de recogida')
    open(P, 'w', encoding='utf-8').write(h[:i] + json.dumps(docs, ensure_ascii=False).replace('</', '<\\/') + h[i + e:])
    print(f'Stacking {D}: {n} pedidos con Aceptado y En camino')
