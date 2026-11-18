# -*- coding: utf-8 -*-
"""
MushDrink · asigna (o cambia) el coordinador de uno o varios restaurantes en todas las pestañas de mushdrink/index.html.

Uso:
    python3 automatizacion/mushdrink_coordinador.py "Manuel Bueno" 16611="PLK Alfahuir" 34383="BK Jávea Arenal"
    python3 automatizacion/mushdrink_coordinador.py Bokko 14376            # restaurante ya conocido: basta el código
    python3 automatizacion/mushdrink_coordinador.py "" 20605               # quitar el coordinador

Toca: RS.owners/names/brand (Resumen), DS.restaurants y DS.meta.owners (Operativa), SIM.owner, KM/EC/PR/AGR.coord,
PE/AG.owner y A.R (Alerta agregadores). Si el restaurante no existía en una tabla de nombres, lo añade.
"""
import sys, os, re, json

HERE = os.path.dirname(os.path.abspath(__file__))
HTML = os.path.join(HERE, '..', 'mushdrink', 'index.html')


def main():
    if len(sys.argv) < 3: sys.exit(__doc__)
    owner = sys.argv[1]
    rests = {}
    for a in sys.argv[2:]:
        code, _, name = a.partition('=')
        rests[code.strip()] = name.strip() or None

    html = open(HTML, encoding='utf-8').read()
    i0 = html.index('const DOCS=') + len('const DOCS=')
    docs, e0 = json.JSONDecoder().raw_decode(html[i0:])

    def setv(k, name, fn):
        d = docs[k]; m = re.search(r'(?:const|let|var)\s+' + name + r'\s*=\s*', d)
        if not m: return False
        v, e = json.JSONDecoder().raw_decode(d[m.end():]); fn(v)
        docs[k] = d[:m.end()] + json.dumps(v, ensure_ascii=False, separators=(',', ':')) + d[m.end() + e:]
        return True

    def find(name):
        return [k for k, d in enumerate(docs) if re.search(r'(?:const|let|var)\s+' + name + r'\s*=\s*\{', d)]

    known = {}
    def f_rs(v):
        for c, n in rests.items():
            n = n or v['names'].get(c) or c; known[c] = n
            v['owners'][c] = owner; v['names'].setdefault(c, n)
            if 'brand' in v: v['brand'].setdefault(c, 'PLK' if 'plk' in n.lower() else 'BK')
    for k in find('RS'): setv(k, 'RS', f_rs)

    def f_ds(v):
        R = {str(r['code']): r for r in v['restaurants']}
        for c in rests:
            if c in R: R[c]['owner'] = owner
            else: v['restaurants'].append({'code': int(c), 'name': known.get(c, c), 'owner': owner, 'teo': None, 'teoDays': None, 'peak': 20, 'zona': ''})
        v['restaurants'].sort(key=lambda r: r['code'])
        if owner and owner not in v['meta']['owners']: v['meta']['owners'] = sorted(v['meta']['owners'] + [owner], key=str.lower)
        for lst in [x for x in v.values() if isinstance(x, list)]:
            for r in lst:
                if isinstance(r, dict) and str(r.get('code')) in rests and 'owner' in r: r['owner'] = owner
    for k in find('DS'): setv(k, 'DS', f_ds)

    for var, key in [('SIM', 'owner'), ('KM', 'coord'), ('EC', 'coord'), ('PR', 'coord'), ('PE', 'owner'), ('AG', 'owner'), ('AGR', 'coord')]:
        def f(v, key=key):
            if key not in v: return
            for c in rests: v[key][c] = owner
            if 'names' in v:
                for c in rests: v['names'].setdefault(c, known.get(c, c))
            if 'brand' in v:
                for c in rests: v['brand'].setdefault(c, 'PLK' if 'plk' in known.get(c, '').lower() else 'BK')
        for k in find(var): setv(k, var, f)

    def f_al(v):
        if not isinstance(v.get('R'), dict): return
        for c in rests:
            if c in v['R']: v['R'][c]['o'] = owner
            else: v['R'][c] = {'n': known.get(c) or c, 'z': '', 'o': owner}
            if v['R'][c].get('n') in (None, '', c) and known.get(c): v['R'][c]['n'] = known[c]
    for k in find('A'):
        if '"o":"' in docs[k]: setv(k, 'A', f_al)

    # resto de listas con objetos {"code":C,...,"owner":"..."} (p. ej. capacidad en Operativa)
    own_js = json.dumps(owner, ensure_ascii=False)
    for k, d in enumerate(docs):
        for c in rests:
            d = re.sub(r'(\{"code":' + c + r',(?:"[^"]+":(?:"[^"]*"|[^,{}\[\]]*),)*?"owner":)"[^"]*"', lambda m: m.group(1) + own_js, d)
        docs[k] = d
    body = '[' + ',\n'.join(json.dumps(d, ensure_ascii=False).replace('</', '<\\/') for d in docs) + ']'   # un documento por línea
    out = html[:i0] + body + html[i0 + e0:]
    open(HTML, 'w', encoding='utf-8').write(out)
    print(f'{owner}: ' + ', '.join(f'{c} {known.get(c, "")}' for c in rests))


if __name__ == '__main__':
    main()
