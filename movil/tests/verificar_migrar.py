"""Herramienta de migraciones (movil/migrar.py) contra la base real, dentro de una transacción que siempre se
revierte (Postgres tiene DDL transaccional): no deja nada en la base. Si la base no responde, se omite y se avisa.

Correr desde la raíz:  python movil/tests/verificar_migrar.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

fails = []


def check(name, cond, extra=""):
    print(("  OK  " if cond else " FAIL ") + name + (f"  {extra}" if extra else ""))
    if not cond:
        fails.append(name)


print("=== migrar.py (transacción que se revierte) ===")
try:
    from src.Views.Pedidos.programarPedido import _conexion
    real = _conexion()
except Exception as e:
    real = None
    print(f"  OMITIDO  no hay conexión a la base ({type(e).__name__}: {str(e)[:80]})")

from movil import migrar


class _SinCommit:
    """La conexión real, pero con commit() y rollback() de mentira: `ejecutar` los llama y no tienen que
    cerrar la transacción de la prueba (se revierte al final, a propósito)."""

    def __init__(self, conexion):
        self._real = conexion
        self.commits = 0
        self.rollbacks = 0

    def cursor(self):
        return self._real.cursor()

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


if real is not None:
    real.autocommit = False
    try:
        con = _SinCommit(real)
        salida = []
        inicial = migrar.faltantes(con)

        # Se parte de una base SIN lo de los avisos (si ya está aplicado en el servidor, se quita en esta transacción).
        cur = real.cursor()
        cur.execute("DROP TABLE IF EXISTS push_suscripcion, notificacion_enviada")
        falta = migrar.faltantes(con)
        check("detecta que faltan las tablas de los avisos", any("004" in f for f in falta), falta)
        check("y solo eso (lo demás ya está en el servidor)", all("004" in f for f in falta), falta)

        codigo = migrar.ejecutar(con, True, salida.append)
        check("--solo-verificar con algo pendiente -> código 1, lo dice y no cambia nada",
              codigo == 1 and any("004" in l for l in salida) and con.commits == 0 and migrar.faltantes(con) == falta, salida)

        salida.clear()
        codigo = migrar.ejecutar(con, False, salida.append)
        check("aplicar -> código 0, hace commit y deja la base al día", codigo == 0 and con.commits == 1 and migrar.faltantes(con) == [], salida)

        salida.clear()
        codigo = migrar.ejecutar(con, True, salida.append)
        check("--solo-verificar con todo aplicado -> código 0", codigo == 0 and "al día" in salida[-1], salida)

        con.commits = 0
        salida.clear()
        codigo = migrar.ejecutar(con, False, salida.append)
        check("aplicar de nuevo no rompe (idempotente) y avisa que ya estaba", codigo == 0 and con.commits == 1
              and any("Ya estaba todo aplicado" in l for l in salida), salida)

        # Un fallo en la mitad no deja nada: se simula con una migración que explota.
        original = migrar.migraciones.aplicar
        migrar.migraciones.aplicar = lambda c: (_ for _ in ()).throw(RuntimeError("falla simulada"))
        con.commits = 0
        salida.clear()
        codigo = migrar.ejecutar(con, False, salida.append)
        migrar.migraciones.aplicar = original
        check("si falla, no hace commit, hace rollback y lo dice (código 1)",
              codigo == 1 and con.commits == 0 and con.rollbacks >= 1 and any("No se guardó nada" in l for l in salida), salida)
    finally:
        real.rollback()
        cur = real.cursor()
        cur.execute("SELECT to_regclass('push_suscripcion') IS NOT NULL")
        existe_ahora = cur.fetchone()[0]
        real.close()
        check("rollback: la base real quedó como estaba (no se aplicó ni se quitó nada)",
              existe_ahora == (not any("004" in f for f in inicial)), f"antes faltaba: {inicial}")

print()
print("RESULTADO:", "TODO OK" if not fails else f"{len(fails)} FALLAS: {fails}")
sys.exit(1 if fails else 0)
