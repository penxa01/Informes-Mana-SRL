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
            "INSERT INTO panel_resumen (id, datos, fuentes, calculado_en, intento_en, error) "
            "VALUES (1, %s::jsonb, %s::jsonb, now(), now(), NULL) "
            "ON CONFLICT (id) DO UPDATE SET datos = EXCLUDED.datos, fuentes = EXCLUDED.fuentes, "
            "calculado_en = now(), intento_en = now(), error = NULL",
            (json.dumps(datos), json.dumps(fuentes)),
        )


def guardar_error(con, mensaje):
    """Anota que el último intento falló; los datos anteriores (si los hay) quedan como estaban."""
    with con.cursor() as cur:
        cur.execute(
            "INSERT INTO panel_resumen (id, intento_en, error) VALUES (1, now(), %s) "
            "ON CONFLICT (id) DO UPDATE SET intento_en = now(), error = EXCLUDED.error",
            (mensaje,),
        )
