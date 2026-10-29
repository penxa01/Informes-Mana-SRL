"""Los avisos en el service worker (movil/pwa/sw.js): cómo se muestra un aviso (`push`) y qué pasa al tocarlo
(`notificationclick`). El navegador integrado no deja registrar un service worker, así que se prueba con Node:
se carga sw.js con un `self` simulado y se le disparan los eventos. Si no hay Node instalado, se omite y se avisa.

Correr desde la raíz:  python movil/tests/verificar_sw_avisos.py
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

SW = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "pwa", "sw.js")
fails = []


def check(name, cond, extra=""):
    print(("  OK  " if cond else " FAIL ") + name + (f"  {extra}" if extra else ""))
    if not cond:
        fails.append(name)


JS = r"""
const fs = require("fs");
const src = fs.readFileSync(process.argv[2], "utf8");
const manejadores = {};
let ventanas = [], abiertas = [], mostradas = [];
const falso = {
  addEventListener: (tipo, fn) => { manejadores[tipo] = fn; },
  registration: { showNotification: (titulo, opciones) => { mostradas.push({ titulo, opciones }); return Promise.resolve(); } },
  location: { origin: "https://app.test" },
  clients: { matchAll: async () => ventanas, openWindow: async (url) => { abiertas.push(url); }, claim() {} },
  skipWaiting() {},
};
const cachesFalso = { match: async () => ({ desdeElCache: true }), open: async () => ({ addAll: async () => {} }), keys: async () => [], delete: async () => true };
new Function("self", "caches", "Request", "fetch", src)(falso, cachesFalso, class {}, () => {});

const resultado = {};
const esperas = [];
function evento(extra) { return { waitUntil: (p) => esperas.push(p), ...extra }; }
async function disparar(tipo, extra) { esperas.length = 0; const ev = evento(extra); manejadores[tipo](ev); await Promise.all(esperas); return ev; }

(async () => {
  // push con un aviso completo
  await disparar("push", { data: { json: () => ({ evento: "nuevo", id_pedido: 7, titulo: "Pedido nuevo", cuerpo: "ACME · cargado por Jose", etiqueta: "pedido-7-nuevo" }) } });
  resultado.completo = mostradas[0];
  // sin contenido, con contenido que no es JSON, con tipos raros y con un evento inventado
  mostradas = [];
  await disparar("push", {});
  await disparar("push", { data: { json: () => { throw new Error("no es JSON"); } } });
  await disparar("push", { data: { json: () => ({ titulo: 123, cuerpo: { x: 1 }, etiqueta: 5, evento: "inventado" }) } });
  resultado.genericos = mostradas;
  // tocar el aviso con la app abierta (de este origen y de otro)
  let cerrada = 0, enfocada = 0, mensajes = [];
  const aviso = { close: () => { cerrada++; }, data: { evento: "entregado" } };
  ventanas = [{ url: "https://otro.test/", postMessage() {}, focus: async () => { enfocada += 100; } },
              { url: "https://app.test/", postMessage: (m) => mensajes.push(m), focus: async () => { enfocada++; } }];
  await disparar("notificationclick", { notification: aviso });
  resultado.conVentana = { cerrada, enfocada, mensajes, abiertas: [...abiertas] };
  // sin la app abierta: se abre (con el aviso en la dirección, o sin nada si no había)
  ventanas = [{ url: "https://otro.test/", postMessage() {}, focus: async () => {} }];
  await disparar("notificationclick", { notification: { close() {}, data: { evento: "programado" } } });
  await disparar("notificationclick", { notification: { close() {}, data: {} } });
  await disparar("notificationclick", { notification: { close() {}, data: { evento: "x&y=1" } } });
  resultado.sinVentana = abiertas;
  // la API de avisos no se sirve nunca desde el caché del service worker
  const respuestas = [];
  const prueba = (ruta) => { manejadores.fetch({ request: { url: "https://app.test" + ruta, mode: "cors" }, respondWith: (p) => respuestas.push([ruta, true]) }); };
  prueba("/push/clave"); prueba("/push/suscribir"); prueba("/js/avisos.js");
  resultado.fetch = respuestas;
  console.log(JSON.stringify(resultado));
})();
"""

print("=== avisos en el service worker (con Node) ===")
node = shutil.which("node")
if node is None:
    print("  OMITIDO  Node no está instalado: no se puede simular el service worker")
else:
    with tempfile.TemporaryDirectory() as tmp:
        ruta_js = os.path.join(tmp, "prueba_sw.js")
        with open(ruta_js, "w", encoding="utf-8") as f:
            f.write(JS)
        proc = subprocess.run([node, ruta_js, SW], capture_output=True, text=True, encoding="utf-8", timeout=60)
    if proc.returncode != 0:
        check("el service worker carga y los eventos corren sin errores", False, proc.stderr[-300:])
    else:
        r = json.loads(proc.stdout.strip().splitlines()[-1])
        check("el service worker carga y los eventos corren sin errores", True)

        c = r["completo"]
        check("un aviso se muestra con su título y su texto", (c["titulo"], c["opciones"]["body"]) == ("Pedido nuevo", "ACME · cargado por Jose"), c)
        o = c["opciones"]
        check("con el ícono de la app, la silueta para la barra de estado de Android, y en castellano",
              (o["icon"], o["badge"], o["lang"]) == ("/icons/icon-192.png", "/icons/badge-96.png", "es"), o)
        check("el mismo aviso no se apila dos veces (etiqueta)", o["tag"] == "pedido-7-nuevo")
        check("guarda solo el tipo de aviso para saber a dónde ir al tocarlo", o["data"] == {"evento": "nuevo"}, o["data"])

        g = r["genericos"]
        check("un aviso sin contenido o con contenido que no se puede leer se muestra igual, con el título de la app",
              len(g) == 3 and all(x["titulo"] == "Mana Pedidos" for x in g), [x["titulo"] for x in g])
        check("con tipos raros o un tipo de aviso inventado no rompe y no guarda nada raro",
              g[2]["opciones"]["body"] == "" and g[2]["opciones"]["data"] == {"evento": ""} and g[2]["opciones"].get("tag") is None, g[2])

        v = r["conVentana"]
        check("al tocar el aviso se cierra", v["cerrada"] == 1)
        check("con la app abierta se la trae al frente (la del mismo origen, no otra) y no se abre otra ventana",
              v["enfocada"] == 1 and v["abiertas"] == [], v)
        check("y se le dice qué aviso fue (un admin cae en la pestaña que corresponde)", v["mensajes"] == [{"tipo": "aviso-tocado", "evento": "entregado"}], v["mensajes"])
        check("con la app cerrada se abre con el aviso en la dirección; sin aviso, la raíz; y el texto raro se escapa",
              r["sinVentana"] == ["/?aviso=programado", "/", "/?aviso=x%26y%3D1"], r["sinVentana"])
        check("la API de avisos (/push) nunca se sirve desde el caché; los archivos de la app sí",
              r["fetch"] == [["/js/avisos.js", True]], r["fetch"])

print()
print("RESULTADO:", "TODO OK" if not fails else f"{len(fails)} FALLAS: {fails}")
sys.exit(1 if fails else 0)
