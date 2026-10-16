"""Reclamos de deuda: reglas de negocio y persistencia (src/controllers/reclamos_db.py).

Las pruebas de base corren **dentro de una transacción que siempre se revierte**
(Postgres tiene DDL transaccional): no crean tablas ni filas en la base real de
Pedidos. Si la base no responde, esa parte se omite y se avisa.

Correr desde la raíz:  python tests/verificar_reclamos.py
"""
import datetime as dt
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.controllers import reclamos_db as rdb
from src.controllers.cuentas_corrientes_io import datos_cliente, opciones_clientes
from src.controllers.vendedores import VENDEDORES, nombre_vendedor

fails = []


def check(name, cond, extra=""):
    print(("  OK  " if cond else " FAIL ") + name + (f"  {extra}" if extra else ""))
    if not cond:
        fails.append(name)


def lanza(fn, *args, **kw):
    try:
        fn(*args, **kw)
    except ValueError as e:
        return str(e)
    return None


def factura(nc=100, clase="A", nro_est=3, tc="FC", saldo=500.0, total=800.0, fecha=dt.date(2026, 3, 1)):
    return {"tc": tc, "clase": clase, "nro_est": nro_est, "nc": nc,
            "fecha_emision": fecha, "total": total, "saldo": saldo}


print("=== vendedores ===")
check("hay 6 vendedores", len(VENDEDORES) == 6, str(VENDEDORES))
check("nombre por código int", nombre_vendedor(3) == "MIGUEL ORTUÑO", str(nombre_vendedor(3)))
check("nombre por código str con espacios", nombre_vendedor(" 9 ") == "MARTIN MOYA")
check("código desconocido -> None", nombre_vendedor(99) is None and nombre_vendedor(None) is None)

print("=== datos del cliente desde ctaclien ===")
clientes = pd.DataFrame({
    "CNUMERO": [1, 2, 3, 4],
    "CNOMBRE": ["A", "B", "C", "D"],
    "TELEFONO": ["  0261-4231234 ", "", None, "155-111"],
    "VENDEDOR": ["3", 4.0, None, " 9 "],
})
d = datos_cliente(clientes, 1)
check("teléfono sin espacios sobrantes", d["telefono"] == "0261-4231234", repr(d["telefono"]))
check("vendedor str -> int", d["vendedor_codigo"] == 3)
check("teléfono vacío -> ''", datos_cliente(clientes, 2)["telefono"] == "")
check("vendedor float -> int", datos_cliente(clientes, 2)["vendedor_codigo"] == 4)
check("teléfono None -> ''", datos_cliente(clientes, 3)["telefono"] == "")
check("vendedor None -> None", datos_cliente(clientes, 3)["vendedor_codigo"] is None)
check("vendedor con espacios", datos_cliente(clientes, 4)["vendedor_codigo"] == 9)
check("cuenta inexistente -> vacío", datos_cliente(clientes, 99) == {"telefono": "", "vendedor_codigo": None})
check("sin columnas TELEFONO/VENDEDOR no rompe",
      datos_cliente(clientes[["CNUMERO", "CNOMBRE"]], 1) == {"telefono": "", "vendedor_codigo": None})

print("=== clientes elegibles: TODOS los de ctaclien ===")
todos = pd.DataFrame({
    "CNUMERO": [30, 10, 20, 40, 50],
    "CNOMBRE": ["  zeta SA ", "ALFA SRL", "ALFA SRL", None, "beta"],
})
op = opciones_clientes(todos)
check("incluye a todos los clientes", len(op) == 5, str(len(op)))
check("ordenado por nombre sin distinguir mayúsculas, desempata por cuenta",
      [c for _, c in op] == [10, 20, 50, 40, 30], str([c for _, c in op]))   # ALFA, ALFA, beta, SIN NOMBRE, zeta
etiquetas = [e for e, _ in op]
check("homónimos distinguibles (la etiqueta lleva la cuenta)", len(set(etiquetas)) == 5 and "ALFA SRL (10)" in etiquetas,
      str(etiquetas))
check("nombre sin espacios sobrantes", "zeta SA (30)" in etiquetas)
check("nombre vacío no rompe", any(c == 40 and e.endswith("(40)") for e, c in op))
check("cuentas como int de Python", all(type(c) is int for _, c in op))
check("sin clientes -> lista vacía", opciones_clientes(todos.iloc[0:0]) == [])

print("=== validación (sin base) ===")
ok = dict(cliente="DREAM SRL", telefono="155", vendedor_codigo=3, vendedor_nombre="MIGUEL ORTUÑO",
          facturas=[factura()])
check("reclamo válido no lanza", lanza(rdb.validar_reclamo, **ok) is None)
check("sin facturas", "factura" in (lanza(rdb.validar_reclamo, **{**ok, "facturas": []}) or ""))
check("sin teléfono", "teléfono" in (lanza(rdb.validar_reclamo, **{**ok, "telefono": "   "}) or "").lower())
check("sin cliente", "cliente" in (lanza(rdb.validar_reclamo, **{**ok, "cliente": ""}) or "").lower())
check("sin vendedor", "vendedor" in (lanza(rdb.validar_reclamo, **{**ok, "vendedor_codigo": None}) or "").lower())
check("estado inválido", "estado" in (lanza(rdb.validar_estado, "INVENTADO") or "").lower())
check("estados válidos", all(lanza(rdb.validar_estado, e) is None for e in rdb.ESTADOS))
check("los 5 estados, en orden",
      rdb.ESTADOS == ("NO CONTACTADO", "SIN RESPUESTA", "CONTACTADO", "PENDIENTE DE O/P", "RESUELTO"), str(rdb.ESTADOS))
check("un reclamo nuevo arranca NO CONTACTADO", rdb.ESTADO_INICIAL == "NO CONTACTADO")

print("=== persistencia (transacción que se revierte) ===")
con = None
try:
    con = rdb.conectar()
except Exception as e:  # base caída / sin red: se omite esta sección
    print(f"  OMITIDO  no hay conexión a la base ({type(e).__name__}: {str(e)[:80]})")

if con is not None:
    con.autocommit = False
    cur = con.cursor()
    try:
        cur.execute("select to_regclass('public.reclamo') is not null")
        existian = cur.fetchone()[0]

        rdb.asegurar_esquema(con)
        rdb.asegurar_esquema(con)
        check("asegurar_esquema es idempotente", True)

        print("  -- migración del estado NO CONTACTADO sobre una tabla con el CHECK viejo --")
        viejos = "'SIN RESPUESTA','CONTACTADO','PENDIENTE DE O/P','RESUELTO'"
        cur.execute("ALTER TABLE reclamo DROP CONSTRAINT IF EXISTS reclamo_estado_check")
        cur.execute(f"ALTER TABLE reclamo ADD CONSTRAINT reclamo_estado_check CHECK (estado IN ({viejos}))")
        cur.execute("ALTER TABLE reclamo ALTER COLUMN estado SET DEFAULT 'SIN RESPUESTA'")
        cur.execute("INSERT INTO reclamo (cuenta, cliente_nombre, telefono, vendedor_codigo, vendedor_nombre, estado) "
                    "VALUES (99, 'VIEJO', '1', 3, 'X', 'SIN RESPUESTA') RETURNING id_reclamo")
        id_viejo = cur.fetchone()[0]
        cur.execute("SAVEPOINT viejo")
        try:
            cur.execute("INSERT INTO reclamo (cuenta, cliente_nombre, vendedor_codigo, vendedor_nombre, estado) "
                        "VALUES (98, 'N', 3, 'X', 'NO CONTACTADO')")
            rechazaba = False
        except Exception:
            rechazaba = True
        cur.execute("ROLLBACK TO SAVEPOINT viejo")
        check("(precondición) el esquema viejo rechaza NO CONTACTADO", rechazaba)

        rdb.asegurar_esquema(con)
        cur.execute("INSERT INTO reclamo (cuenta, cliente_nombre, vendedor_codigo, vendedor_nombre, estado) "
                    "VALUES (98, 'N', 3, 'X', 'NO CONTACTADO') RETURNING id_reclamo")
        check("tras migrar acepta NO CONTACTADO", cur.fetchone()[0] > 0)
        cur.execute("SELECT estado FROM reclamo WHERE id_reclamo = %s", (id_viejo,))
        check("los reclamos existentes conservan su estado", cur.fetchone()[0] == "SIN RESPUESTA")
        cur.execute("INSERT INTO reclamo (cuenta, cliente_nombre, vendedor_codigo, vendedor_nombre) "
                    "VALUES (97, 'D', 3, 'X') RETURNING estado")
        check("el estado por defecto de la tabla pasó a NO CONTACTADO", cur.fetchone()[0] == "NO CONTACTADO")
        cur.execute("SAVEPOINT malo")
        try:
            cur.execute("INSERT INTO reclamo (cuenta, cliente_nombre, vendedor_codigo, vendedor_nombre, estado) "
                        "VALUES (96, 'M', 3, 'X', 'INVENTADO')")
            rechaza_basura = False
        except Exception:
            rechaza_basura = True
        cur.execute("ROLLBACK TO SAVEPOINT malo")
        check("sigue rechazando estados inventados", rechaza_basura)
        rdb.asegurar_esquema(con)
        check("migrar dos veces no rompe", True)

        id1 = rdb.crear_reclamo(con, cuenta=7, cliente="DREAM SRL", telefono="155", vendedor_codigo=3,
                                vendedor_nombre="MIGUEL ORTUÑO", creado_por="test",
                                facturas=[factura(nc=100, saldo=500.0), factura(nc=101, saldo=250.5)])
        check("crear devuelve un id", isinstance(id1, int) and id1 > 0, str(id1))

        df = rdb.listar_reclamos(con)
        fila = df[df["id_reclamo"] == id1].iloc[0]
        check("estado inicial NO CONTACTADO", fila["estado"] == "NO CONTACTADO", fila["estado"])
        check("devuelve el código de vendedor (para avisarle por WhatsApp)", fila["vendedor_codigo"] == 3)
        fd = rdb.facturas_de_reclamo(con, id1)
        check("facturas del reclamo: 2, con comprobante, fecha, total y saldo",
              len(fd) == 2 and list(fd.columns) == ["comprobante", "fecha_emision", "total", "saldo"], str(list(fd.columns)))
        check("comprobante formateado", list(fd["comprobante"]) == ["FC A 0003-00000100", "FC A 0003-00000101"])
        check("saldos al momento de reclamar", list(fd["saldo"]) == [500.0, 250.5], str(list(fd["saldo"])))
        check("reclamo sin facturas / inexistente -> vacío", rdb.facturas_de_reclamo(con, 999999).empty)
        check("cuenta de facturas", fila["n_facturas"] == 2)
        check("saldo suma de las facturas", fila["saldo"] == 750.5, str(fila["saldo"]))
        check("snapshot de cliente/teléfono/vendedor",
              (fila["cliente"], fila["telefono"], fila["vendedor"]) == ("DREAM SRL", "155", "MIGUEL ORTUÑO"))
        check("lista los comprobantes", "FC A 0003-00000100" in fila["comprobantes"], fila["comprobantes"])

        claves = rdb.facturas_reclamadas(con)
        check("claves de facturas en reclamo activo", claves.get((7, "A", 3, 100)) == id1, str(list(claves)[:2]))

        msg = lanza(rdb.crear_reclamo, con, cuenta=7, cliente="DREAM SRL", telefono="155", vendedor_codigo=3,
                    vendedor_nombre="X", facturas=[factura(nc=100)])
        check("no se reclama dos veces la misma factura", msg is not None and "ya está" in msg, str(msg))
        check("misma clave en OTRA cuenta no choca",
              (lanza(rdb.crear_reclamo, con, cuenta=8, cliente="OTRO", telefono="1", vendedor_codigo=3,
                     vendedor_nombre="X", facturas=[factura(nc=100)]) is None))

        rdb.cambiar_estado(con, id1, "CONTACTADO")
        check("cambiar estado", rdb.listar_reclamos(con).set_index("id_reclamo").loc[id1, "estado"] == "CONTACTADO")
        check("estado inválido no toca la base", lanza(rdb.cambiar_estado, con, id1, "XXX") is not None)
        check("reclamo inexistente", lanza(rdb.cambiar_estado, con, 999999, "CONTACTADO") is not None)

        rdb.cambiar_estado(con, id1, "RESUELTO")
        check("resueltos ocultos por defecto", id1 not in set(rdb.listar_reclamos(con)["id_reclamo"]))
        check("resueltos visibles si se piden",
              id1 in set(rdb.listar_reclamos(con, incluir_resueltos=True)["id_reclamo"]))
        check("factura de reclamo resuelto se puede volver a reclamar", (7, "A", 3, 100) not in rdb.facturas_reclamadas(con))
        print("  -- contactos de WhatsApp --")
        # Diego (5) comparte línea con Maxi (confirmado por el usuario): mismo número, a propósito.
        esperados = {9: "2645048307", 3: "2646600437", 4: "2645044432", 6: "2644437285", 1: "2645043510",
                     5: "2645047459"}
        for codigo, tel in esperados.items():
            check(f"teléfono del vendedor {codigo} ({nombre_vendedor(codigo)})",
                  rdb.telefono_vendedor(con, codigo) == tel, str(rdb.telefono_vendedor(con, codigo)))
        cur.execute("select nombre from contacto_whatsapp where telefono = '2645047459' order by nombre")
        check("Diego y Maxi comparten el mismo número", [r[0] for r in cur.fetchall()] == ["Diego", "Maxi"])
        check("código inexistente / None -> None",
              rdb.telefono_vendedor(con, 999) is None and rdb.telefono_vendedor(con, None) is None)
        check("el remitente es el número de Martin", rdb.telefono_remitente(con) == "2645048307",
              str(rdb.telefono_remitente(con)))
        cur.execute("select count(*), count(codigo_vendedor), count(*) filter (where es_remitente) "
                    "from contacto_whatsapp")
        total, con_codigo, remitentes = cur.fetchone()
        check("9 contactos cargados (6 con código de vendedor)", (total, con_codigo) == (9, 6), f"{total}/{con_codigo}")
        check("un solo remitente", remitentes == 1)
        cur.execute("select nombre, telefono from contacto_whatsapp where codigo_vendedor is null order by nombre")
        check("Maxi, Angeles y Julieta sin código de vendedor",
              cur.fetchall() == [("Angeles", "2645060925"), ("Julieta", "2644174385"), ("Maxi", "2645047459")])
        cur.execute("update contacto_whatsapp set telefono = '2640000000' where nombre = 'Miguel'")
        rdb.asegurar_esquema(con)
        cur.execute("select count(*) from contacto_whatsapp")
        check("re-ejecutar el esquema no duplica contactos", cur.fetchone()[0] == 9)
        check("re-ejecutar el esquema no pisa un número editado", rdb.telefono_vendedor(con, 3) == "2640000000")
        cur.execute("savepoint s")
        try:
            cur.execute("update contacto_whatsapp set es_remitente = true where nombre = 'Miguel'")
            check("no admite dos remitentes", False)
        except Exception:
            check("no admite dos remitentes", True)
        cur.execute("rollback to savepoint s")
        check("la estructura de tablas existe", True)
    finally:
        con.rollback()
        cur.execute("select to_regclass('public.reclamo') is not null")
        despues = cur.fetchone()[0]
        con.close()
    check("rollback: no quedaron tablas nuevas en la base real", despues == existian,
          f"existían={existian} después={despues}")

print()
print("RESULTADO:", "TODO OK" if not fails else f"{len(fails)} FALLAS: {fails}")
sys.exit(1 if fails else 0)
