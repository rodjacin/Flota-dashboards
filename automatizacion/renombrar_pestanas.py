# -*- coding: utf-8 -*-
"""Último paso: cambia los textos visibles de pestañas en los dashboards ya generados.
Los demás scripts siguen usando «Delivery Race» como ancla interna; aquí solo se cambia lo que se ve.
Uso: python3 renombrar_pestanas.py <index.html> [...]"""
import sys
CAMBIOS = [('aria-pressed="false">Delivery Race</button>', 'aria-pressed="false">Tendencias</button>'),
           ('aria-pressed="true">Delivery Race</button>', 'aria-pressed="true">Tendencias</button>'),
           ('Delivery Race · Tendencia por rider</h1>', 'Tendencias por rider</h1>'),
           ('Delivery Race · Score de performance</h1>', 'Tendencias · Score de performance</h1>')]
for p in sys.argv[1:]:
    h = open(p, encoding="utf-8").read(); n = 0
    for a, b in CAMBIOS:
        n += h.count(a); h = h.replace(a, b)
    open(p, "w", encoding="utf-8").write(h)
    print(f"renombrar_pestanas: {p} · {n} cambios")
