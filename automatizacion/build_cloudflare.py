"""Genera dist/ para Cloudflare Pages (límite 25 MiB por archivo).

- Copia el sitio tal cual (index.html, gra-mad-nom-alc/, sab/, mushdrink/leads.json, ...).
- mushdrink/index.html: cada pestaña del array DOCS pasa a su propio archivo
  mushdrink/_tabNN.html (iframe src en vez de srcdoc).
- Si una pestaña sigue superando LIMIT, sus constantes de datos más grandes
  (const X = <JSON>) se sacan a mushdrink/_tabNN_X.js y se cargan antes del script.
No modifica el repositorio: solo escribe en dist/.
Uso en Cloudflare Pages: build command `python3 automatizacion/build_cloudflare.py`, output `dist`.
"""
import json, os, re, shutil, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIST = os.path.join(ROOT, 'dist')
LIMIT = 20 * 1024 * 1024
SKIP = {'.git', '.github', 'dist', 'automatizacion', 'node_modules', '__pycache__'}


def copy_site():
    if os.path.exists(DIST):
        shutil.rmtree(DIST)
    os.makedirs(DIST)
    for name in os.listdir(ROOT):
        if name in SKIP or name.startswith('.'):
            continue
        src = os.path.join(ROOT, name)
        dst = os.path.join(DIST, name)
        if os.path.isdir(src):
            shutil.copytree(src, dst, ignore=shutil.ignore_patterns('.*', '__pycache__'))
        else:
            shutil.copy2(src, dst)


def externalize(doc, k, outdir):
    """Saca a .js las constantes JSON más grandes hasta que el doc quede bajo LIMIT."""
    dec = json.JSONDecoder()
    found = []
    for m in re.finditer(r'(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(?=[\[{"])', doc):
        try:
            _, end = dec.raw_decode(doc, m.end())
        except ValueError:
            continue
        if end - m.end() > 256 * 1024:
            found.append((end - m.end(), m.group(1), m.end(), end))
    found.sort(reverse=True)
    pre, cuts = [], []
    size = len(doc.encode())
    for n, name, s, e in found:
        if size <= LIMIT:
            break
        fn = f'_tab{k:02d}_{name}.js'
        with open(os.path.join(outdir, fn), 'w', encoding='utf-8') as f:
            f.write(f'window.__D_{name}=' + doc[s:e] + ';')
        cuts.append((s, e, f'window.__D_{name}'))
        pre.append(f'<script src="{fn}"></script>')
        size -= n
    for s, e, rep in sorted(cuts, reverse=True):
        doc = doc[:s] + rep + doc[e:]
    if pre:
        tag = '\n'.join(pre)
        m = re.search(r'<head[^>]*>', doc, re.I)
        doc = doc[:m.end()] + tag + doc[m.end():] if m else tag + doc
    return doc


def split_mushdrink():
    p = os.path.join(DIST, 'mushdrink', 'index.html')
    h = open(p, encoding='utf-8').read()
    i = h.index('const DOCS=') + len('const DOCS=')
    e = h.index('];\nconst stage', i) + 1
    docs = json.loads(h[i:e])
    outdir = os.path.dirname(p)
    names = []
    for k, d in enumerate(docs):
        if len(d.encode()) > LIMIT:
            d = externalize(d, k, outdir)
        fn = f'_tab{k:02d}.html'
        open(os.path.join(outdir, fn), 'w', encoding='utf-8').write(d)
        names.append(fn)
    h = h[:i] + json.dumps(names) + h[e:]
    h = h.replace("setTimeout(()=>{ f.srcdoc=doc; }, i===0?0:60);",
                  "setTimeout(()=>{ f.src=doc; }, i===0?0:60);")
    assert 'f.src=doc' in h, 'no se encontró el cargador de iframes'
    open(p, 'w', encoding='utf-8').write(h)


def check():
    big = []
    for dp, _, fs in os.walk(DIST):
        for f in fs:
            fp = os.path.join(dp, f)
            s = os.path.getsize(fp)
            if s > 25 * 1024 * 1024:
                big.append((fp, s))
    if big:
        for fp, s in big:
            print('DEMASIADO GRANDE', fp, round(s / 1e6, 1), 'MB')
        sys.exit(1)


if __name__ == '__main__':
    copy_site()
    split_mushdrink()
    check()
    tot = sum(os.path.getsize(os.path.join(dp, f)) for dp, _, fs in os.walk(DIST) for f in fs)
    n = sum(len(fs) for _, _, fs in os.walk(DIST))
    print(f'dist listo: {n} archivos, {tot/1e6:.1f} MB')
