"""Proceso del panel (movil/panel/worker.py + almacen.py + sql/003_panel.sql) contra la base real,
conectado como `movil_api` (con sus permisos reales) y dentro de una transacción que siempre se
revierte. El cálculo y la lectura de archivos se reemplazan por funciones falsas: lo que se prueba
acá es CUÁNDO recalcula, qué guarda y cómo se comporta ante un error. (El cálculo en sí está en
verificar_panel.py y verificar_panel_paridad.py.)

Correr desde la raíz:  python movil/tests/verificar_panel_worker.py
"""
import datetime as dt
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

fails = []


def check(name, cond, extra=""):
    print(("  OK  " if cond else " FAIL ") + name + (f"  {extra}" if extra else ""))
    if not cond:
        fails.append(name)


# La conexión real se abre ANTES de cualquier variable PEDIDOS_DB_* de prueba (mismos nombres que
# la app de escritorio).
try:
    from src.Views.Pedidos.programarPedido import _conexion
    real = _conexion()
except Exception as e:
    real = None
    print(f"  OMITIDO  no hay conexión a la base ({type(e).__name__}: {str(e)[:80]})")

from movil import migraciones
from movil.panel import almacen, worker

print("=== rutas y entorno ===")
r = worker.rutas_desde_entorno({})
check("por defecto busca en D:/tiempo, con la estructura del escritorio",
      r == (os.path.join("D:/tiempo", "vtiempoges", "GESTION", "MANA2014"), os.path.join("D:/tiempo", "Thalamus", "LITROS SHELL.xlsx")), r)
r = worker.rutas_desde_entorno({"PANEL_BASE_PATH": "E:/datos"})
check("PANEL_BASE_PATH la cambia", r[0].startswith("E:/datos") and r[1].startswith("E:/datos"), r)

print("=== firma ===")
from movil.panel import calculo
with tempfile.TemporaryDirectory() as tmp:
    for nombre in ("fachist.DBF", "abmartic.DBF", "ctacorr.DBF", "ctaclien.DBF", "plan_caj.DBF", "placaja.DBF"):
        open(os.path.join(tmp, nombre), "wb").write(b"x")
    excel = os.path.join(tmp, "LITROS SHELL.xlsx")
    open(excel, "wb").write(b"x")
    f1 = worker.firma_completa(tmp, excel)
    check("la firma trae los 6 archivos y la versión del cálculo",
          set(f1) == {"fachist", "abmartic", "ctacorr", "ctaclien", "plan_caj", "placaja", "clasificacion", "version_calculo"}
          and f1["version_calculo"] == calculo.VERSION, f1)
    open(os.path.join(tmp, "placaja.DBF"), "ab").write(b"mas datos")
    check("si cambia placaja (un cobro nuevo) la firma cambia y el panel se recalcula", worker.firma_completa(tmp, excel) != f1)
    open(os.path.join(tmp, "fachist.DBF"), "ab").write(b"mas datos")
    check("si un archivo crece, la firma cambia", worker.firma_completa(tmp, excel) != f1)
    check("y si no se toca nada, es estable", worker.firma_completa(tmp, excel) == worker.firma_completa(tmp, excel))

env_anterior = dict(os.environ)
try:
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["MOVIL_LOG_DIR"] = tmp
        for v in ("PEDIDOS_DB_HOST", "PEDIDOS_DB_NAME", "PEDIDOS_DB_USER", "PEDIDOS_DB_PASSWORD"):
            os.environ.pop(v, None)
        env_malo = os.path.join(tmp, "malo.env")
        with open(env_malo, "w", encoding="utf-8") as f:
            f.write("PEDIDOS_DB_HOST=localhost\n")
        os.environ["MOVIL_ENV_FILE"] = env_malo
        check("un .env al que le faltan variables -> código 2 (la tarea no arranca a ciegas)", worker.cargar_entorno() == 2)
        os.environ["MOVIL_ENV_FILE"] = os.path.join(tmp, "no_existe.env")
        check("un .env que no existe -> código 2", worker.cargar_entorno() == 2)
        env_bueno = os.path.join(tmp, "bueno.env")
        with open(env_bueno, "w", encoding="utf-8") as f:
            f.write("PEDIDOS_DB_HOST=h\nPEDIDOS_DB_NAME=n\nPEDIDOS_DB_USER=u\nPEDIDOS_DB_PASSWORD=p\n")
        os.environ["MOVIL_ENV_FILE"] = env_bueno
        check("un .env completo -> sigue (None) y deja el log en panel.log", worker.cargar_entorno() is None
              and os.path.exists(os.path.join(tmp, "panel.log")))
        import logging
        for h in list(logging.getLogger().handlers):   # suelta el archivo para poder borrar la carpeta temporal
            h.close()
            logging.getLogger().removeHandler(h)
finally:
    os.environ.clear()
    os.environ.update(env_anterior)

if real is not None:
    print("=== ciclos contra la base (transacción que se revierte, con el rol movil_api) ===")
    real.autocommit = False
    cur = real.cursor()
    import logging
    logging.disable(logging.CRITICAL)   # los errores de acá son a propósito: que no ensucien la salida

    class _ConSavepoint:
        """commit() y rollback() de `ciclo` actúan sobre un savepoint: nunca sobre la transacción
        entera (si no, el rollback de un error borraría también la tabla creada para la prueba)."""
        def __init__(self, real):
            self._real = real
            self._cur = real.cursor()
            self._cur.execute("SAVEPOINT sp_ciclo")

        def cursor(self):
            return self._real.cursor()

        def commit(self):
            self._cur.execute("RELEASE SAVEPOINT sp_ciclo")
            self._cur.execute("SAVEPOINT sp_ciclo")

        def rollback(self):
            self._cur.execute("ROLLBACK TO SAVEPOINT sp_ciclo")

    try:
        migraciones.aplicar(real)
        migraciones.asegurar_permisos(real)
        cur.execute("DELETE FROM panel_resumen")          # como postgres: parte de una tabla vacía
        cur.execute("SET LOCAL ROLE movil_api")           # todo lo que sigue, con los permisos reales
        con = _ConSavepoint(real)

        hoy = dt.date(2026, 10, 23)
        llamadas = []
        firma = {"fachist": [100, 1]}

        def calcular_ok():
            llamadas.append(1)
            return {"hoy": hoy.isoformat(), "litros": {"mes": {"litros": 123.45}}}

        def ciclo(dia=hoy, firma_actual=None, calcular=calcular_ok, leer_firma=None):
            return worker.ciclo(con, dia, leer_firma or (lambda: firma_actual or firma), calcular)

        check("la tabla vacía: no hay estado", almacen.leer_estado(con) is None)

        check("primer ciclo -> calculado", ciclo() == "calculado" and len(llamadas) == 1)
        e = almacen.leer_estado(con)
        check("guarda datos, firma y fecha, sin error", e["datos"]["litros"]["mes"]["litros"] == 123.45
              and e["fuentes"] == firma and e["calculado_en"] is not None and e["error"] is None, e)
        check("los datos vuelven de la base como diccionario (jsonb)", isinstance(e["datos"], dict))

        check("mismos archivos y mismo día -> sin_cambios, sin recalcular", ciclo() == "sin_cambios" and len(llamadas) == 1)
        cur.execute("RESET ROLE")
        cur.execute("UPDATE panel_resumen SET verificado_en = clock_timestamp() - interval '10 minutes'")
        cur.execute("SET LOCAL ROLE movil_api")
        con.commit()
        ciclo()
        cur.execute("SELECT clock_timestamp() - verificado_en < interval '5 seconds' FROM panel_resumen")
        check("un ciclo sin cambios deja el latido (así se nota si el proceso se cae)", cur.fetchone()[0] is True)
        check("cambió un archivo -> recalcula", ciclo(firma_actual={"fachist": [200, 2]}) == "calculado" and len(llamadas) == 2)
        check("la firma nueva queda guardada", almacen.leer_estado(con)["fuentes"] == {"fachist": [200, 2]})
        check("cambió el día (mismos archivos) -> recalcula, los períodos se corren",
              ciclo(dia=hoy + dt.timedelta(days=1), firma_actual={"fachist": [200, 2]},
                    calcular=lambda: calcular_ok() | {"hoy": (hoy + dt.timedelta(days=1)).isoformat()}) == "calculado"
              and len(llamadas) == 3)

        print("  -- errores --")
        datos_buenos = almacen.leer_estado(con)["datos"]

        def explota():
            raise OSError("no encuentro fachist.DBF")

        check("un cálculo que falla -> error", ciclo(firma_actual={"fachist": [300, 3]}, calcular=explota) == "error")
        e = almacen.leer_estado(con)
        check("se guarda el motivo", e["error"] is not None and "fachist.DBF" in e["error"], e["error"])
        check("los datos anteriores NO se pierden", e["datos"] == datos_buenos)
        check("con un error pendiente reintenta aunque los archivos no cambien",
              ciclo(firma_actual={"fachist": [300, 3]}) == "calculado" and almacen.leer_estado(con)["error"] is None)

        firmas = iter([{"a": 1}, {"a": 2}])   # el archivo cambió mientras se calculaba
        check("si un archivo cambia MIENTRAS se lee, no se guarda un resultado a medias",
              ciclo(leer_firma=lambda: next(firmas)) == "error")
        e = almacen.leer_estado(con)
        check("y lo explica", "cambiaron mientras se leían" in e["error"], e["error"])
        check("los datos de antes siguen", e["datos"]["litros"]["mes"]["litros"] == 123.45)

        def sin_archivo():
            raise FileNotFoundError("D:/tiempo/fachist.DBF")

        check("si ni siquiera se pueden mirar los archivos -> error guardado",
              ciclo(leer_firma=sin_archivo) == "error" and "FileNotFoundError" in almacen.leer_estado(con)["error"])

        print("  -- primer ciclo que falla (sin datos previos) --")
        cur.execute("RESET ROLE")
        cur.execute("DELETE FROM panel_resumen")
        cur.execute("SET LOCAL ROLE movil_api")
        con.commit()    # el DELETE queda "confirmado" para el rollback del ciclo (que solo deshace lo suyo)
        check("falla -> queda un error y datos vacíos", ciclo(calcular=explota) == "error"
              and almacen.leer_estado(con)["datos"] is None and almacen.leer_estado(con)["error"])
        check("y el siguiente ciclo, ya sano, lo cura", ciclo() == "calculado" and almacen.leer_estado(con)["datos"] is not None)

        print("  -- panel de los vendedores (se guarda en la misma transacción) --")
        cur.execute("RESET ROLE")
        cur.execute("DELETE FROM panel_vendedor")
        cur.execute("SET LOCAL ROLE movil_api")
        con.commit()
        periodos = {"mes": {"desde": "2026-10-01", "hasta": "2026-10-23"}}
        de_vendedores = {"hoy": hoy.isoformat(), "periodos": periodos, "vendedores": {"1": {"cartera": {"en_calle": 111.0}}, "4": {"cartera": {"en_calle": 444.0}}}}
        firma2 = {"fachist": [500, 5]}
        check("un ciclo que devuelve (panel general, panel de los vendedores) -> calculado",
              ciclo(firma_actual=firma2, calcular=lambda: (calcular_ok(), de_vendedores)) == "calculado")
        check("guarda una fila por vendedor, con la fecha y los períodos del cálculo",
              almacen.leer_vendedor(con, 1)["datos"] == {"hoy": hoy.isoformat(), "periodos": periodos, "cartera": {"en_calle": 111.0}}
              and almacen.leer_vendedor(con, 4)["datos"]["cartera"]["en_calle"] == 444.0)
        general = almacen.leer_estado(con)["datos"]
        check("el panel general (el del admin) NO lleva los datos de los vendedores", "vendedores" not in general and "cartera" not in str(general), general)

        de_vendedores_nuevo = {"hoy": hoy.isoformat(), "vendedores": {"1": {"cartera": {"en_calle": 222.0}}}}
        ciclo(firma_actual={"fachist": [600, 6]}, calcular=lambda: (calcular_ok(), de_vendedores_nuevo))
        check("el ciclo siguiente actualiza al vendedor 1 y borra al 4, que ya no aparece",
              almacen.leer_vendedor(con, 1)["datos"]["cartera"]["en_calle"] == 222.0 and almacen.leer_vendedor(con, 4) is None)

        roto = {"hoy": hoy.isoformat(), "vendedores": {"1": {"cartera": {"en_calle": object()}}}}   # no se puede guardar como JSON
        check("si falla guardar a los vendedores -> error",
              ciclo(firma_actual={"fachist": [700, 7]}, calcular=lambda: ({"hoy": hoy.isoformat(), "litros": {"mes": {"litros": 999.0}}}, roto)) == "error")
        e = almacen.leer_estado(con)
        check("no queda nada a medias: el panel general conserva los datos de antes (no los 999 L del ciclo fallido)",
              e["datos"]["litros"]["mes"]["litros"] == 123.45 and e["fuentes"] == {"fachist": [600, 6]}, e["datos"])
        check("el panel de los vendedores tampoco cambió, y el error queda anotado",
              almacen.leer_vendedor(con, 1)["datos"]["cartera"]["en_calle"] == 222.0 and "TypeError" in e["error"], e["error"])
        check("un cálculo que devuelve solo el panel general (sin vendedores) sigue funcionando y no toca las filas",
              ciclo(firma_actual={"fachist": [800, 8]}) == "calculado" and almacen.leer_vendedor(con, 1)["datos"]["cartera"]["en_calle"] == 222.0)

        print("  -- permisos de movil_api --")
        def permitido(sql):
            cur.execute("SAVEPOINT s_perm")
            try:
                cur.execute(sql)
                ok = True
            except Exception:
                ok = False
            cur.execute("ROLLBACK TO SAVEPOINT s_perm")
            return ok

        check("puede leer, insertar y actualizar la tabla del panel",
              permitido("SELECT * FROM panel_resumen") and permitido("UPDATE panel_resumen SET error = error"))
        check("NO puede borrar de la tabla del panel", not permitido("DELETE FROM panel_resumen"))
        check("puede leer, escribir y borrar filas del panel de los vendedores (borra la de quien ya no aparece)",
              permitido("SELECT * FROM panel_vendedor") and permitido("UPDATE panel_vendedor SET datos = datos WHERE false")
              and permitido("DELETE FROM panel_vendedor WHERE false"))
        check("NO puede crear una segunda fila (el CHECK id = 1)",
              not permitido("INSERT INTO panel_resumen (id) VALUES (2)"))
    finally:
        real.rollback()
        cur = real.cursor()
        cur.execute("SELECT to_regclass('panel_resumen')")
        # Si la tabla ya existía antes de la prueba (después del despliegue), sigue; si la creó la prueba, no queda.
        real.close()

print()
print("RESULTADO:", "TODO OK" if not fails else f"{len(fails)} FALLAS: {fails}")
sys.exit(1 if fails else 0)
