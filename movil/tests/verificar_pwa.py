"""Coherencia de la PWA (movil/pwa/), sin navegador:
- todo script/estilo/ícono que usa `index.html` está en la lista `CASCARON` de `sw.js` (si falta,
  la app no abre sin señal) y todo lo de esa lista existe en disco;
- todo `getElementById` de los scripts apunta a un id que existe en `index.html`;
- `CACHE_NAME` tiene el formato `mana-pedidos-vN` (hay que subir N con cada cambio en `pwa/`).

Correr desde la raíz:  python movil/tests/verificar_pwa.py
"""
import os
import re
import sys

PWA = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "pwa")
fails = []


def check(name, cond, extra=""):
    print(("  OK  " if cond else " FAIL ") + name + (f"  {extra}" if extra else ""))
    if not cond:
        fails.append(name)


def leer(ruta):
    with open(os.path.join(PWA, ruta), encoding="utf-8") as f:
        return f.read()


html = leer("index.html")
sw = leer("sw.js")

print("=== service worker ===")
m = re.search(r'const CACHE_NAME = "(mana-pedidos-v\d+)";', sw)
check("CACHE_NAME con formato mana-pedidos-vN", m is not None)
cascaron = re.findall(r'^\s*"(/[^"]*)",?\s*$', sw[sw.index("CASCARON"):sw.index("];", sw.index("CASCARON"))], re.M)
check("la lista CASCARON se pudo leer", len(cascaron) > 5, len(cascaron))

usados = re.findall(r'(?:src|href)="([^"]+)"', html)
locales = ["/" + u.lstrip("/") for u in usados if not re.match(r"^(https?:|#|mailto:|tel:)", u)]
for ruta in locales:
    check(f"{ruta} (usado por index.html) está en CASCARON", ruta in cascaron)
for ruta in cascaron:
    if ruta == "/":
        continue
    check(f"{ruta} existe en disco", os.path.exists(os.path.join(PWA, ruta.lstrip("/"))))

print("=== ids de los scripts ===")
ids_html = set(re.findall(r'\bid="([^"]+)"', html))
for ruta in sorted(os.listdir(os.path.join(PWA, "js"))):
    if not ruta.endswith(".js"):
        continue
    pedidos = set(re.findall(r'getElementById\("([^"]+)"\)', leer(os.path.join("js", ruta))))
    faltan = sorted(pedidos - ids_html)
    check(f"js/{ruta}: todos sus getElementById existen en el HTML", not faltan, faltan)

print()
print("RESULTADO:", "TODO OK" if not fails else f"{len(fails)} FALLAS: {fails}")
sys.exit(1 if fails else 0)
