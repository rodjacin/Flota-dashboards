"""Inserta/actualiza la pestaña "Leads delivery" (doc 16) de mushdrink/index.html
con la plantilla automatizacion/plantilla_leads_delivery.html y el respaldo de mushdrink/leads.json."""
import json,os
R=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
t=open(os.path.join(R,'automatizacion/plantilla_leads_delivery.html'),encoding='utf-8').read()
d=json.load(open(os.path.join(R,'mushdrink/leads.json'),encoding='utf-8'))
t=t.replace('__FALLBACK__',json.dumps(d,ensure_ascii=False,separators=(',',':')))
p=os.path.join(R,'mushdrink/index.html');h=open(p,encoding='utf-8').read()
i=h.index('const DOCS=')+len('const DOCS=');e=h.index('];\nconst stage',i)+1
docs=json.loads(h[i:e])
if len(docs)>16: docs[16]=t
else: docs.append(t)
h=h[:i]+json.dumps(docs,ensure_ascii=False).replace('</','<\\/')+h[e:]
if 'data-i="16"' not in h:
    h=h.replace('<button class="tab" data-i="15">Agrupación de pedidos</button>','<button class="tab" data-i="15">Agrupación de pedidos</button><button class="tab" data-i="16">Leads delivery</button>',1)
open(p,'w',encoding='utf-8').write(h)
print('Leads delivery:',len(d['leads']),'locales')
