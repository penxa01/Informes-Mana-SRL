"""Mapa de clientes, ubicación del reparto y sesión única de la cuenta de reparto contra la base real
(movil/api/db.py: `clientes_con_ubicacion`, `guardar_posicion_reparto`, `posiciones_reparto`, `fijar_sesion` y
`sesion_vigente`), conectado como `movil_api` (con sus permisos reales) y dentro de una transacción que siempre se
revierte. Si la base no responde, se omite y se avisa.

Correr desde la raíz:  python movil/tests/verificar_mapa_db.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

fails = []


def check(name, cond, extra=""):
    print(("  OK  " if cond else " FAIL ") + name + (f"  {extra}" if extra else ""))
    if not cond:
        fails.append(name)


# La conexión real se abre ANTES de fijar las variables de prueba (mismos nombres PEDIDOS_DB_* que la app de
# escritorio; ver guideline/Movil.md).
print("=== mapa y sesión única (transacción que se revierte, con el rol movil_api) ===")
try:
    from src.Views.Pedidos.programarPedido import _conexion
    con = _conexion()
except Exception as e:
    con = None
    print(f"  OMITIDO  no hay conexión a la base ({type(e).__name__}: {str(e)[:80]})")

os.environ.setdefault("PEDIDOS_DB_HOST", "localhost")
os.environ.setdefault("PEDIDOS_DB_NAME", "no_existe")
os.environ.setdefault("PEDIDOS_DB_USER", "movil_api")
os.environ.setdefault("PEDIDOS_DB_PASSWORD", "x")
os.environ.setdefault("MOVIL_JWT_SECRET", "clave-de-prueba")

from movil import migraciones, usuarios
from movil.api import db

if con is not None:
    con.autocommit = False
    cur = con.cursor()
    try:
        migraciones.aplicar(con)
        migraciones.asegurar_permisos(con)   # no depende de cómo haya quedado el servidor

        def permitido(sql):
            cur.execute("SAVEPOINT s_permiso")
            try:
                cur.execute(sql)
                ok = True
            except Exception:
                ok = False
            cur.execute("ROLLBACK TO SAVEPOINT s_permiso")
            return ok

        # Un cliente de prueba (dos, en realidad) con la ubicación cargada, y una cuenta de reparto de prueba.
        cur.execute("SELECT id_cliente FROM cliente ORDER BY id_cliente LIMIT 3")
        c1, c2, c3 = (r[0] for r in cur.fetchall())
        cur.execute("UPDATE cliente SET nombre = 'CLIENTE MAPA UNO', direccion = 'Calle 1', localidad = 'SAN JUAN', "
                    "ubicacion_lat = -31.5375, ubicacion_lng = -68.5364 WHERE id_cliente = %s", (c1,))
        cur.execute("UPDATE cliente SET ubicacion_lat = NULL, ubicacion_lng = NULL, ubicacion_maps = NULL WHERE id_cliente = %s", (c2,))
        cur.execute("UPDATE cliente SET ubicacion_lat = -31.5, ubicacion_lng = NULL WHERE id_cliente = %s", (c3,))   # incompleta
        usuarios.crear_usuario(con, "reparto_mapa_tmp", "clave-de-prueba", "Reparto de prueba", "reparto")
        usuarios.crear_usuario(con, "reparto_mapa_tmp2", "clave-de-prueba", "Otro reparto", "reparto")

        cur.execute("SET LOCAL ROLE movil_api")

        print("  -- clientes en el mapa --")
        lista = db.clientes_con_ubicacion(con)
        ids = [c["id"] for c in lista]
        uno = next((c for c in lista if c["id"] == c1), None)
        check("incluye al cliente con ubicación", uno is not None)
        check("trae nombre, dirección, localidad y coordenadas",
              uno == {"id": c1, "nombre": "CLIENTE MAPA UNO", "direccion": "Calle 1", "localidad": "SAN JUAN", "lat": -31.5375, "lng": -68.5364}, uno)
        check("NO incluye al que no tiene ubicación ni al que la tiene a medias (solo latitud)", c2 not in ids and c3 not in ids)
        check("solo lo básico: sin teléfono ni CUIT", all(set(c) == {"id", "nombre", "direccion", "localidad", "lat", "lng"} for c in lista))

        print("  -- posición del reparto --")
        check("sin posiciones guardadas de esa cuenta: no aparece", "reparto_mapa_tmp" not in [p["usuario"] for p in db.posiciones_reparto(con)])
        db.guardar_posicion_reparto(con, "reparto_mapa_tmp", -31.52, -68.53, 12.5)
        p = next(p for p in db.posiciones_reparto(con) if p["usuario"] == "reparto_mapa_tmp")
        check("guarda y devuelve la posición, con el nombre de la persona y hace cuánto llegó",
              (p["nombre"], p["lat"], p["lng"], p["precision_m"]) == ("Reparto de prueba", -31.52, -68.53, 12.5) and 0 <= p["hace_seg"] <= 5, p)
        db.guardar_posicion_reparto(con, "reparto_mapa_tmp", -31.6, -68.6, None)
        filas = [p for p in db.posiciones_reparto(con) if p["usuario"] == "reparto_mapa_tmp"]
        check("mandar otra vez la PISA (una sola fila por cuenta, sin historial)", len(filas) == 1 and (filas[0]["lat"], filas[0]["lng"], filas[0]["precision_m"]) == (-31.6, -68.6, None), filas)
        cur.execute("RESET ROLE")
        cur.execute("UPDATE ubicacion_reparto SET actualizado_en = now() - interval '20 minutes' WHERE username = 'reparto_mapa_tmp'")
        cur.execute("SET LOCAL ROLE movil_api")
        check("una posición de hace más de 15 minutos NO se muestra (el celular dejó de mandarla)",
              "reparto_mapa_tmp" not in [p["usuario"] for p in db.posiciones_reparto(con)])
        db.guardar_posicion_reparto(con, "reparto_mapa_tmp", -31.5, -68.5, None)
        check("al volver a mandar, vuelve a aparecer", "reparto_mapa_tmp" in [p["usuario"] for p in db.posiciones_reparto(con)])
        check("una latitud imposible la rechaza la base (CHECK)", not permitido("INSERT INTO ubicacion_reparto (username, lat, lng) VALUES ('x', 95, 0)"))

        print("  -- una sola sesión para la cuenta de reparto --")
        check("sin sesión anotada, un token sin identificador vale (los de antes de esto)", db.sesion_vigente(con, "reparto_mapa_tmp", None) is True)
        check("y uno con identificador no", db.sesion_vigente(con, "reparto_mapa_tmp", "abc") is False)
        db.fijar_sesion(con, "reparto_mapa_tmp", "sesion-celular-1")
        check("con la sesión anotada, el token de ESA sesión vale", db.sesion_vigente(con, "reparto_mapa_tmp", "sesion-celular-1") is True)
        check("y uno sin identificador (token viejo) deja de valer", db.sesion_vigente(con, "reparto_mapa_tmp", None) is False)
        db.fijar_sesion(con, "reparto_mapa_tmp", "sesion-celular-2")
        check("al iniciar sesión en otro celular, el primero deja de valer", db.sesion_vigente(con, "reparto_mapa_tmp", "sesion-celular-1") is False)
        check("y el nuevo vale", db.sesion_vigente(con, "reparto_mapa_tmp", "sesion-celular-2") is True)
        check("la sesión de una cuenta no afecta a otra", db.sesion_vigente(con, "reparto_mapa_tmp2", None) is True
              and db.sesion_vigente(con, "reparto_mapa_tmp2", "sesion-celular-2") is False)
        check("un usuario que no existe nunca tiene sesión vigente", db.sesion_vigente(con, "no_existe_zzz", None) is False)

        print("  -- permisos de movil_api --")
        check("puede anotar la sesión (solo esa columna de usuario)", permitido("UPDATE usuario SET sesion_id = 'x' WHERE username = 'reparto_mapa_tmp'"))
        check("NO puede cambiar el rol, el estado ni la clave de un usuario",
              not permitido("UPDATE usuario SET rol = 'superadmin' WHERE username = 'reparto_mapa_tmp'")
              and not permitido("UPDATE usuario SET activo = true WHERE username = 'reparto_mapa_tmp'")
              and not permitido("UPDATE usuario SET password_hash = 'x' WHERE username = 'reparto_mapa_tmp'"))
        check("NO puede borrar posiciones ni crear la tabla de nuevo (no hace falta: la pisa)",
              not permitido("DELETE FROM ubicacion_reparto WHERE false") and not permitido("DROP TABLE ubicacion_reparto"))
    finally:
        con.rollback()
        cur = con.cursor()
        cur.execute("SELECT count(*) FROM usuario WHERE username IN ('reparto_mapa_tmp', 'reparto_mapa_tmp2')")
        check("rollback: los usuarios de prueba no quedaron en la base real", cur.fetchone()[0] == 0)
        con.close()

print()
print("RESULTADO:", "TODO OK" if not fails else f"{len(fails)} FALLAS: {fails}")
sys.exit(1 if fails else 0)
