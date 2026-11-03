"""GET /panel (movil/api/routers/panel.py): quién puede verlo, qué devuelve y cómo avisa cuando el
proceso del servidor no da señales de vida.

Parte 1 (sin base): cableado HTTP con `almacen.leer_para_api` reemplazado.
Parte 2 (base real): `almacen.leer_para_api` y el latido, conectado como `movil_api`, dentro de una
transacción que siempre se revierte.

Correr desde la raíz:  python movil/tests/verificar_panel_api.py
"""
import datetime as dt
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

fails = []


def check(name, cond, extra=""):
    print(("  OK  " if cond else " FAIL ") + name + (f"  {extra}" if extra else ""))
    if not cond:
        fails.append(name)


# La conexión real se abre ANTES de fijar las variables de prueba (mismos nombres PEDIDOS_DB_* que el escritorio).
try:
    from src.Views.Pedidos.programarPedido import _conexion
    real = _conexion()
except Exception as e:
    real = None
    print(f"  OMITIDO  no hay conexión a la base ({type(e).__name__}: {str(e)[:80]})")

os.environ.setdefault("PEDIDOS_DB_HOST", "localhost")
os.environ.setdefault("PEDIDOS_DB_NAME", "no_existe")
os.environ.setdefault("PEDIDOS_DB_USER", "movil_api")
os.environ.setdefault("PEDIDOS_DB_PASSWORD", "x")
os.environ.setdefault("MOVIL_JWT_SECRET", "clave-de-prueba")

from fastapi.testclient import TestClient

from movil import migraciones
from movil.api import auth, db
from movil.api.app import app
from movil.panel import almacen


class _Con:
    def close(self): pass
    def commit(self): pass


print("=== 1. HTTP ===")
db.conexion = lambda: _Con()
DATOS = {"hoy": "2026-10-23", "litros": {"mes": {"litros": 55915.27, "premium": 16325.0, "pct_premium": 29.2, "por_dia": []}},
         "recaudado": {"semana": {"total": 89818223.02, "recibos": 85, "por_dia": []}}}
AHORA = dt.datetime(2026, 10, 24, 9, 0, tzinfo=dt.timezone.utc)
estado = {"datos": DATOS, "calculado_en": AHORA, "error": None, "verificado_hace_seg": 60}
almacen.leer_para_api = lambda con: estado

client = TestClient(app)
cab = {"Authorization": f"Bearer {auth.crear_token('alguien')}"}
for rol, esperado in (("admin", 200), ("superadmin", 200), ("vendedor", 403), ("reparto", 403), (None, 401)):
    db.rol_activo = lambda con, username, rol=rol: rol
    check(f"rol {rol}: GET /panel -> {esperado}", client.get("/panel", headers=cab).status_code == esperado)
check("sin token -> 401", client.get("/panel").status_code == 401)

db.rol_activo = lambda con, username: "admin"
r = client.get("/panel", headers=cab)
cuerpo = r.json()
check("devuelve los datos tal cual los dejó el proceso", cuerpo["datos"] == DATOS)
check("con la fecha del cálculo, la antigüedad y sin error", cuerpo["calculado_en"].startswith("2026-10-24T09:00") and cuerpo["verificado_hace_seg"] == 60 and cuerpo["error"] is None, cuerpo)
check("al día -> desactualizado = false", cuerpo["desactualizado"] is False)

estado = {**estado, "verificado_hace_seg": 20 * 60}
check("20 minutos sin latido -> desactualizado = true (el proceso del servidor no responde)",
      client.get("/panel", headers=cab).json()["desactualizado"] is True)
estado = {**estado, "verificado_hace_seg": 10 * 60}
check("10 minutos todavía es normal (el proceso revisa cada 5)", client.get("/panel", headers=cab).json()["desactualizado"] is False)

estado = {**estado, "verificado_hace_seg": 30, "error": "OSError: no encuentro fachist.DBF"}
c = client.get("/panel", headers=cab).json()
check("si el último intento falló: los datos de antes + el motivo", c["datos"] == DATOS and "fachist" in c["error"], c["error"])

almacen.leer_para_api = lambda con: None
r = client.get("/panel", headers=cab)
check("sin fila todavía -> 503 con el motivo, no un error crudo", r.status_code == 503 and "todavía no se calculó" in r.json()["detail"], r.text)
almacen.leer_para_api = lambda con: {"datos": None, "calculado_en": None, "error": "FileNotFoundError: x", "verificado_hace_seg": 5}
r = client.get("/panel", headers=cab)
check("fila sin datos (el primer cálculo falló) -> 503 y muestra el error", r.status_code == 503 and "FileNotFoundError" in r.json()["detail"], r.text)

print("=== 1b. GET /panel/mio: cada vendedor ve SOLO lo suyo ===")
vendedor_id_de_real = db.vendedor_id_de
leer_vendedor_real = almacen.leer_vendedor
leer_empresa_real = almacen.leer_empresa
ROLES = {"ana": "vendedor", "beto": "vendedor", "sin_codigo": "vendedor", "cero": "vendedor", "mili": "admin", "diego": "admin",
         "super": "superadmin", "rep": "reparto", "baja": None}
CODIGOS = {"ana": 1, "beto": 4, "sin_codigo": None, "cero": 0, "mili": 3, "diego": 5, "super": None, "rep": None}
EMPRESA = {"hoy": "2026-10-23", "cartera": {"en_calle": 1110.0}, "clientes": [
    {"cuenta": 10, "nombre": "CLIENTE DE ANA", "saldo": 111.0, "facturas": []},
    {"cuenta": 40, "nombre": "CLIENTE DE BETO", "saldo": 444.0, "facturas": []},
    {"cuenta": 50, "nombre": "CLIENTE DE DIEGO", "saldo": 555.0, "facturas": []}]}
BLOQUES = {
    5: {"hoy": "2026-10-23", "cartera": {"en_calle": 555.0}, "clientes": [{"cuenta": 50, "nombre": "CLIENTE DE DIEGO", "saldo": 555.0, "facturas": []}]},
    1: {"hoy": "2026-10-23", "cartera": {"en_calle": 111.0}, "clientes": [{"cuenta": 10, "nombre": "CLIENTE DE ANA", "saldo": 111.0, "facturas": []}]},
    4: {"hoy": "2026-10-23", "cartera": {"en_calle": 444.0}, "clientes": [{"cuenta": 40, "nombre": "CLIENTE DE BETO", "saldo": 444.0, "facturas": []}]},
}
pedidos_de_codigo = []


def leer_vendedor_falso(con, codigo):
    pedidos_de_codigo.append(codigo)
    return {"datos": BLOQUES[codigo], "calculado_en": AHORA} if codigo in BLOQUES else None


db.rol_activo = lambda con, username: ROLES[username]
db.vendedor_id_de = lambda con, username: CODIGOS.get(username)
almacen.leer_vendedor = leer_vendedor_falso
almacen.leer_para_api = lambda con: {"datos": DATOS, "calculado_en": AHORA, "error": None, "verificado_hace_seg": 60}


def con_token(usuario):
    return {"Authorization": f"Bearer {auth.crear_token(usuario)}"}


r = client.get("/panel/mio", headers=con_token("ana"))
check("un vendedor recibe su panel (200) con lo suyo", r.status_code == 200 and r.json()["datos"] == BLOQUES[1], r.text[:200])
check("y con la fecha del cálculo, la antigüedad y si está desactualizado",
      r.json()["calculado_en"].startswith("2026-10-24T09:00") and r.json()["verificado_hace_seg"] == 60 and r.json()["desactualizado"] is False, r.json())
check("en la respuesta no hay nada de otro vendedor ni de la empresa",
      "BETO" not in r.text and "444" not in r.text and "recaudado" not in r.text and "litros" not in r.text, r.text[:200])
r = client.get("/panel/mio", headers=con_token("beto"))
check("el otro vendedor recibe el suyo y no el de ana", r.json()["datos"] == BLOQUES[4] and "ANA" not in r.text)
pedidos_de_codigo.clear()
for trampa in ("?vendedor=4", "?vendedor_id=4", "?codigo=4", "?usuario=beto", "?id=4"):
    r = client.get("/panel/mio" + trampa, headers=con_token("ana"))
    check(f"pedir /panel/mio{trampa} con el token de ana sigue dando el de ana", r.status_code == 200 and r.json()["datos"] == BLOQUES[1] and "BETO" not in r.text)
r = client.get("/panel/mio", headers={**con_token("ana"), "X-Vendedor": "4", "X-Vendedor-Id": "4"})
check("un encabezado inventado tampoco cambia de quién es el panel", r.json()["datos"] == BLOQUES[1])
check("la base siempre se consultó con el código de ana (1), nunca con otro", set(pedidos_de_codigo) == {1}, pedidos_de_codigo)
check("no existe ninguna ruta para pedir el panel de un código o de otro usuario",
      all(client.get(ruta, headers=con_token("ana")).status_code in (404, 405) for ruta in ("/panel/mio/4", "/panel/4", "/panel/vendedor/4", "/panel/vendedores", "/panel/mio/beto")))
check("el panel general sigue siendo solo de admin: ana no lo ve", client.get("/panel", headers=con_token("ana")).status_code == 403)

# /panel/mio es solo del vendedor: el admin y el superadmin ven las cobranzas de toda la empresa en /panel/cobranzas (aunque
# tengan código de vendedor, como diego) y el reparto no ve números: 403. El vendedor sin código recibe 404 y no 403: la
# app deslogueaba a quien recibía un 403 (cree que le cambiaron el perfil).
for usuario, esperado in (("diego", 403), ("mili", 403), ("super", 403), ("rep", 403), ("sin_codigo", 404), ("cero", 404), ("baja", 401)):
    check(f"{usuario} ({ROLES[usuario]}, código {CODIGOS.get(usuario)}): GET /panel/mio -> {esperado}",
          client.get("/panel/mio", headers=con_token(usuario)).status_code == esperado)
r = client.get("/panel/mio", headers=con_token("sin_codigo"))
check("el vendedor sin código de vendedor recibe un mensaje claro", "código de vendedor" in r.json()["detail"], r.text)
check("sin token -> 401", client.get("/panel/mio").status_code == 401)
check("token inválido -> 401", client.get("/panel/mio", headers={"Authorization": "Bearer cualquiera"}).status_code == 401)

almacen.leer_vendedor = lambda con, codigo: None
r = client.get("/panel/mio", headers=con_token("ana"))
check("vendedor todavía sin fila -> 404 con un mensaje, no un error crudo", r.status_code == 404 and "Todavía no hay datos" in r.json()["detail"], r.text)
almacen.leer_vendedor = leer_vendedor_falso

print("=== 1c. GET /panel/cobranzas: el admin y el superadmin ven TODOS los clientes; el vendedor, no ===")
pedidos_empresa = []
almacen.leer_empresa = lambda con: (pedidos_empresa.append(1), {"datos": EMPRESA, "calculado_en": AHORA})[1]
almacen.leer_para_api = lambda con: {"datos": DATOS, "calculado_en": AHORA, "error": None, "verificado_hace_seg": 60}
for usuario, esperado in (("diego", 200), ("mili", 200), ("super", 200), ("ana", 403), ("beto", 403), ("rep", 403), ("sin_codigo", 403), ("baja", 401)):
    check(f"{usuario} ({ROLES[usuario]}): GET /panel/cobranzas -> {esperado}", client.get("/panel/cobranzas", headers=con_token(usuario)).status_code == esperado)
check("sin token -> 401", client.get("/panel/cobranzas").status_code == 401)
r = client.get("/panel/cobranzas", headers=con_token("diego"))
check("un admin recibe los clientes de todos los vendedores", r.json()["datos"] == EMPRESA and "ANA" in r.text and "BETO" in r.text and "DIEGO" in r.text, r.text[:150])
check("con la fecha del cálculo, la antigüedad y si está desactualizado",
      r.json()["calculado_en"].startswith("2026-10-24T09:00") and r.json()["verificado_hace_seg"] == 60 and r.json()["desactualizado"] is False, r.json())
check("y un superadmin recibe lo mismo", client.get("/panel/cobranzas", headers=con_token("super")).json()["datos"] == EMPRESA)
pedidos_empresa.clear()
client.get("/panel/cobranzas", headers=con_token("ana"))
client.get("/panel/cobranzas?vendedor=1", headers=con_token("ana"))
check("a un vendedor ni siquiera se le consulta la fila de la empresa", pedidos_empresa == [], pedidos_empresa)
check("el panel de un vendedor no trae los clientes de otros", "BETO" not in client.get("/panel/mio", headers=con_token("ana")).text)
almacen.leer_empresa = lambda con: None
r = client.get("/panel/cobranzas", headers=con_token("diego"))
check("sin fila de la empresa todavía -> 404 con un mensaje, no un error crudo", r.status_code == 404 and "Todavía no hay datos" in r.json()["detail"], r.text)
almacen.leer_para_api = lambda con: None
check("panel sin calcular todavía -> 503", client.get("/panel/cobranzas", headers=con_token("diego")).status_code == 503)
almacen.leer_empresa = leer_empresa_real

almacen.leer_para_api = lambda con: None
r = client.get("/panel/mio", headers=con_token("ana"))
check("panel sin calcular todavía -> 503 con el motivo", r.status_code == 503 and "todavía no se calculó" in r.json()["detail"], r.text)
almacen.leer_para_api = lambda con: {"datos": DATOS, "calculado_en": AHORA, "error": "OSError: se cayó la red", "verificado_hace_seg": 20 * 60}
r = client.get("/panel/mio", headers=con_token("ana"))
check("con el proceso del servidor sin señales de vida: los datos de antes, desactualizado y el motivo",
      r.json()["datos"] == BLOQUES[1] and r.json()["desactualizado"] is True and "se cayó la red" in r.json()["error"], r.json())
db.vendedor_id_de = vendedor_id_de_real
almacen.leer_vendedor = leer_vendedor_real

if real is not None:
    print("=== 2. base real (con los permisos de movil_api; transacción que se revierte) ===")
    import importlib
    importlib.reload(almacen)   # las funciones reales, no las de arriba
    real.autocommit = False
    cur = real.cursor()
    try:
        migraciones.aplicar(real)
        migraciones.asegurar_permisos(real)
        cur.execute("DELETE FROM panel_resumen")
        cur.execute("SET LOCAL ROLE movil_api")

        check("sin fila: leer_para_api -> None", almacen.leer_para_api(real) is None)
        almacen.guardar_resultado(real, DATOS, {"fachist": [1, 2]})
        e = almacen.leer_para_api(real)
        check("tras guardar: devuelve datos, fecha y error vacío", e["datos"] == DATOS and e["calculado_en"] is not None and e["error"] is None, e)
        check("verificado_hace_seg recién guardado ~ 0", 0 <= e["verificado_hace_seg"] <= 5, e["verificado_hace_seg"])

        # Se "envejece" el latido como lo haría un proceso caído (como postgres, que sí puede tocar cualquier cosa)
        cur.execute("RESET ROLE")
        cur.execute("UPDATE panel_resumen SET verificado_en = clock_timestamp() - interval '20 minutes'")
        cur.execute("SET LOCAL ROLE movil_api")
        viejo = almacen.leer_para_api(real)["verificado_hace_seg"]
        check("con el último latido de hace 20 minutos, la base lo mide (~1200 s)", 1190 <= viejo <= 1215, viejo)
        almacen.marcar_verificado(real)
        check("un latido nuevo lo pone otra vez al día", almacen.leer_para_api(real)["verificado_hace_seg"] <= 5)

        almacen.guardar_error(real, "OSError: se cayó la red")
        e = almacen.leer_para_api(real)
        check("un error se guarda sin perder los datos anteriores", e["datos"] == DATOS and "se cayó la red" in e["error"], e)
        cur.execute("RESET ROLE")
        cur.execute("UPDATE panel_resumen SET verificado_en = NULL")
        cur.execute("SET LOCAL ROLE movil_api")
        check("una fila sin latido registrado se mide contra el cálculo (no falla)", almacen.leer_para_api(real)["verificado_hace_seg"] is not None)

        print("  -- panel de cada vendedor --")
        cur.execute("RESET ROLE")
        cur.execute("DELETE FROM panel_vendedor")           # como postgres: parte de una tabla vacía
        cur.execute("SET LOCAL ROLE movil_api")
        check("sin filas: leer_vendedor -> None", almacen.leer_vendedor(real, 1) is None)
        almacen.guardar_vendedores(real, {"hoy": "2026-10-23", "vendedores": {"1": {"cartera": {"en_calle": 111.0}, "clientes": [{"nombre": "DE ANA"}]},
                                                                                "4": {"cartera": {"en_calle": 444.0}, "clientes": [{"nombre": "DE BETO"}]}}})
        a, b = almacen.leer_vendedor(real, 1), almacen.leer_vendedor(real, 4)
        check("cada vendedor lee SU fila, con la fecha del cálculo agregada", a["datos"] == {"hoy": "2026-10-23", "cartera": {"en_calle": 111.0}, "clientes": [{"nombre": "DE ANA"}]}
              and b["datos"]["cartera"]["en_calle"] == 444.0 and a["calculado_en"] is not None, (a, b))
        check("leer el 1 no trae nada del 4", "BETO" not in str(a) and "444" not in str(a))
        check("un código sin fila -> None", almacen.leer_vendedor(real, 7) is None)
        almacen.guardar_vendedores(real, {"hoy": "2026-10-24", "vendedores": {"1": {"cartera": {"en_calle": 222.0}, "clientes": []}}})
        check("guardar de nuevo actualiza la fila del vendedor", almacen.leer_vendedor(real, 1)["datos"]["cartera"]["en_calle"] == 222.0
              and almacen.leer_vendedor(real, 1)["datos"]["hoy"] == "2026-10-24")
        check("y borra la fila del vendedor que ya no aparece", almacen.leer_vendedor(real, 4) is None)
        almacen.guardar_vendedores(real, {"hoy": "2026-10-25", "vendedores": {}})
        check("sin vendedores se borran todas las filas", almacen.leer_vendedor(real, 1) is None)
        # La empresa entera (todos los clientes): una fila aparte que solo lee el admin, nunca un vendedor.
        almacen.guardar_vendedores(real, {"hoy": "2026-10-23", "vendedores": {"1": {"cartera": {"en_calle": 111.0}, "clientes": [{"nombre": "DE ANA"}]},
                                                                                "0": {"cartera": {"en_calle": 999.0}, "clientes": [{"nombre": "VENDEDOR CERO"}]}},
                                          "empresa": {"cartera": {"en_calle": 1110.0}, "clientes": [{"nombre": "DE TODOS"}]}})
        e = almacen.leer_empresa(real)
        check("la fila de la empresa se guarda y se lee, con la fecha del cálculo", e["datos"] == {"hoy": "2026-10-23", "cartera": {"en_calle": 1110.0}, "clientes": [{"nombre": "DE TODOS"}]}, e)
        check("un vendedor con código 0 no se guarda (0 es la empresa) y nadie lee la fila de la empresa como si fuera de un vendedor",
              "VENDEDOR CERO" not in str(e) and almacen.leer_vendedor(real, 0) is None and almacen.leer_vendedor(real, -1) is None)
        check("la fila de un vendedor no trae nada de la empresa", "DE TODOS" not in str(almacen.leer_vendedor(real, 1)) and almacen.leer_vendedor(real, 1)["datos"]["cartera"]["en_calle"] == 111.0)
        almacen.guardar_vendedores(real, {"hoy": "2026-10-24", "vendedores": {"1": {"cartera": {"en_calle": 222.0}, "clientes": []}}})
        check("si ya no viene la empresa, su fila se borra", almacen.leer_empresa(real) is None and almacen.leer_vendedor(real, 1)["datos"]["cartera"]["en_calle"] == 222.0)
        try:
            almacen.leer_vendedor(real, "1; DROP TABLE panel_vendedor")
            check("un código que no es número se rechaza antes de llegar a la base", False)
        except ValueError:
            check("un código que no es número se rechaza antes de llegar a la base", True)

        # De quién es cada panel: el código sale del usuario en la base (datos reales, solo lectura).
        for usuario, esperado in (("romulo", 1), ("jose", 4), ("matias", 6), ("reparto", None), ("admin", None), ("no_existe_xyz", None)):
            check(f"vendedor_id_de('{usuario}') = {esperado} (leído de la base como movil_api)", db.vendedor_id_de(real, usuario) == esperado, db.vendedor_id_de(real, usuario))
    finally:
        real.rollback()
        real.close()

print()
print("RESULTADO:", "TODO OK" if not fails else f"{len(fails)} FALLAS: {fails}")
sys.exit(1 if fails else 0)
