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
    finally:
        real.rollback()
        real.close()

print()
print("RESULTADO:", "TODO OK" if not fails else f"{len(fails)} FALLAS: {fails}")
sys.exit(1 if fails else 0)
