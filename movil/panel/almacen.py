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


# La fila con lo de TODA la empresa (todos los clientes y todo lo cobrado: la ve el admin) vive en la misma tabla con este
# código. Ningún vendedor puede tenerlo: `leer_vendedor` no lo devuelve nunca y `guardar_vendedores` no guarda un vendedor
# con este código (o menor).
CODIGO_EMPRESA = 0


def guardar_vendedores(con, de_vendedores):
    """Guarda el panel de cada vendedor (lo que devuelve `vendedores.calcular`) en `panel_vendedor`, una fila por
    código, la de la empresa entera (si viene) con `CODIGO_EMPRESA`, y borra las filas que ya no aparecen. Cada fila
    lleva la fecha del cálculo (`hoy`) y los períodos que se muestran (`periodos`, si vienen) junto a sus datos y nada más."""
    comunes = {clave: de_vendedores[clave] for clave in ("hoy", "periodos") if clave in de_vendedores}
    filas = [(int(codigo), bloque) for codigo, bloque in de_vendedores["vendedores"].items() if int(codigo) > CODIGO_EMPRESA]
    if de_vendedores.get("empresa") is not None:
        filas.append((CODIGO_EMPRESA, de_vendedores["empresa"]))
    with con.cursor() as cur:
        for codigo, bloque in filas:
            cur.execute(
                "INSERT INTO panel_vendedor (vendedor_id, datos, calculado_en) VALUES (%s, %s::jsonb, clock_timestamp()) "
                "ON CONFLICT (vendedor_id) DO UPDATE SET datos = EXCLUDED.datos, calculado_en = clock_timestamp()",
                (codigo, json.dumps({**comunes, **bloque})),
            )
        cur.execute("DELETE FROM panel_vendedor WHERE NOT (vendedor_id = ANY(%s::int[]))", ([codigo for codigo, _ in filas],))


def _leer_fila(con, codigo):
    with con.cursor() as cur:
        cur.execute("SELECT datos, calculado_en FROM panel_vendedor WHERE vendedor_id = %s", (int(codigo),))
        fila = cur.fetchone()
    return None if fila is None else {"datos": fila[0], "calculado_en": fila[1]}


def leer_vendedor(con, codigo):
    """El panel de UN vendedor: {datos, calculado_en}, o None si todavía no hay fila con ese código. Es la forma de
    leer lo de un vendedor desde la API: la consulta filtra por el código y nunca devuelve más de una fila. Un código
    que no es de vendedor (0 o negativo) no devuelve nada: la fila de la empresa no se lee por acá."""
    return None if int(codigo) <= CODIGO_EMPRESA else _leer_fila(con, codigo)


def leer_empresa(con):
    """El panel de la empresa entera (todos los clientes y todo lo cobrado): {datos, calculado_en} o None. Solo para
    el admin y el superadmin (ver `routers/panel.py`)."""
    return _leer_fila(con, CODIGO_EMPRESA)


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
