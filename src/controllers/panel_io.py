"""Lectura del panel de control que deja calculado el servidor (solo lectura).

El proceso `movil/panel/worker.py` (tarea `ManaPanelMovil`) calcula todo y lo guarda en Postgres; el celular lo lee por la
API y el escritorio lo lee directo de la base. Así las cifras son idénticas y esta PC no recalcula nada.
`movil/` queda fuera del .exe, por eso no se importa `movil.panel.almacen`: las dos consultas se repiten acá.

    general     `panel_resumen` (id = 1): litros del mes, % premium y recaudado de la semana.
    cobranzas   `panel_vendedor` (vendedor_id = 0): la cartera, lo cobrado por mes y todos los clientes de la empresa.
"""
from src.controllers import reclamos_db

#: Si pasan más de 15 minutos sin latido del proceso del servidor (revisa cada 5), los números pueden ser viejos.
SEGUNDOS_SIN_LATIDO = 15 * 60
#: Código de la fila con lo de toda la empresa en `panel_vendedor`.
CODIGO_EMPRESA = 0


class PanelNoDisponible(Exception):
    """Todavía no hay nada calculado (o el servidor no lo dejó)."""


def _estado(cur):
    cur.execute(
        "SELECT datos, calculado_en, error, "
        "EXTRACT(EPOCH FROM (clock_timestamp() - COALESCE(verificado_en, calculado_en, intento_en)))::int "
        "FROM panel_resumen WHERE id = 1"
    )
    fila = cur.fetchone()
    if fila is None or fila[0] is None:
        motivo = f" Último error: {fila[2]}" if fila and fila[2] else ""
        raise PanelNoDisponible("El panel todavía no se calculó en el servidor, probá en un momento." + motivo)
    return {"datos": fila[0], "calculado_en": fila[1], "error": fila[2], "verificado_hace_seg": fila[3]}


def _respuesta(datos, calculado_en, estado):
    return {
        "datos": datos,
        "calculado_en": calculado_en,
        "verificado_hace_seg": estado["verificado_hace_seg"],
        "desactualizado": estado["verificado_hace_seg"] > SEGUNDOS_SIN_LATIDO,
        "error": estado["error"],
    }


def leer_general(con):
    """{datos, calculado_en, verificado_hace_seg, desactualizado, error} del panel general."""
    with con.cursor() as cur:
        estado = _estado(cur)
    return _respuesta(estado["datos"], estado["calculado_en"], estado)


def leer_cobranzas(con):
    """Lo mismo, con los datos de cobranzas de TODA la empresa."""
    with con.cursor() as cur:
        estado = _estado(cur)
        cur.execute("SELECT datos, calculado_en FROM panel_vendedor WHERE vendedor_id = %s", (CODIGO_EMPRESA,))
        fila = cur.fetchone()
    if fila is None:
        raise PanelNoDisponible("Todavía no hay datos de cobranzas, probá en unos minutos.")
    return _respuesta(fila[0], fila[1], estado)


def leer(seccion):
    """Abre su propia conexión, lee la sección (`"general"` o `"cobranzas"`) y la cierra."""
    lectura = {"general": leer_general, "cobranzas": leer_cobranzas}[seccion]
    con = reclamos_db.conectar()
    try:
        return lectura(con)
    finally:
        con.close()
