"""Guarda y lee el panel calculado en la tabla `panel_resumen` (una sola fila, id = 1).
No hace commit: lo decide quien llama."""
import json


def leer_estado(con):
    """El estado guardado o None si todavía no hay fila:
    {datos, fuentes, calculado_en, intento_en, error}."""
    with con.cursor() as cur:
        cur.execute("SELECT datos, fuentes, calculado_en, intento_en, error FROM panel_resumen WHERE id = 1")
        fila = cur.fetchone()
    if fila is None:
        return None
    return {"datos": fila[0], "fuentes": fila[1], "calculado_en": fila[2], "intento_en": fila[3], "error": fila[4]}


def guardar_resultado(con, datos, fuentes):
    with con.cursor() as cur:
        cur.execute(
            "INSERT INTO panel_resumen (id, datos, fuentes, calculado_en, intento_en, error, verificado_en) "
            "VALUES (1, %s::jsonb, %s::jsonb, clock_timestamp(), clock_timestamp(), NULL, clock_timestamp()) "
            "ON CONFLICT (id) DO UPDATE SET datos = EXCLUDED.datos, fuentes = EXCLUDED.fuentes, "
            "calculado_en = clock_timestamp(), intento_en = clock_timestamp(), error = NULL, "
            "verificado_en = clock_timestamp()",
            (json.dumps(datos), json.dumps(fuentes)),
        )


def guardar_error(con, mensaje):
    """Anota que el último intento falló; los datos anteriores (si los hay) quedan como estaban."""
    with con.cursor() as cur:
        cur.execute(
            "INSERT INTO panel_resumen (id, intento_en, error, verificado_en) "
            "VALUES (1, clock_timestamp(), %s, clock_timestamp()) "
            "ON CONFLICT (id) DO UPDATE SET intento_en = clock_timestamp(), error = EXCLUDED.error, "
            "verificado_en = clock_timestamp()",
            (mensaje,),
        )


def marcar_verificado(con):
    """Latido: el proceso revisó y no había nada nuevo. Sin esto, un proceso caído y uno que
    simplemente no tiene datos nuevos se verían igual desde la API."""
    with con.cursor() as cur:
        cur.execute("UPDATE panel_resumen SET verificado_en = clock_timestamp() WHERE id = 1")


def leer_para_api(con):
    """Lo que la API le entrega al celular, o None si todavía no hay fila:
    {datos, calculado_en, error, verificado_hace_seg}. `verificado_hace_seg` lo mide la base
    (no el reloj de quien pregunta), contra la última revisión del proceso."""
    with con.cursor() as cur:
        cur.execute(
            "SELECT datos, calculado_en, error, "
            "EXTRACT(EPOCH FROM (clock_timestamp() - COALESCE(verificado_en, calculado_en, intento_en)))::int "
            "FROM panel_resumen WHERE id = 1"
        )
        fila = cur.fetchone()
    if fila is None:
        return None
    return {"datos": fila[0], "calculado_en": fila[1], "error": fila[2], "verificado_hace_seg": fila[3]}
