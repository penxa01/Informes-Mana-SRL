"""Reclamos de deuda de clientes, en la base PostgreSQL de Pedidos (tablas nuevas).

* ``reclamo``          — un reclamo: cliente, teléfono, vendedor y estado.
* ``reclamo_factura``  — las facturas incluidas en cada reclamo (con su saldo al
  momento de reclamar).

Cliente, vendedor y teléfono se guardan como **snapshot** (nombre incluido): el
reclamo no cambia si después se edita el cliente en el sistema de gestión.

Todas las funciones reciben una conexión ya abierta y **no hacen commit**: quien
llama decide (la UI commitea; los tests revierten).
"""
import pandas as pd

# NO CONTACTADO: el reclamo se creó y el vendedor todavía no se contactó con el cliente.
# SIN RESPUESTA: ya se lo contactó y no contesta.
ESTADOS = ("NO CONTACTADO", "SIN RESPUESTA", "CONTACTADO", "PENDIENTE DE O/P", "RESUELTO")
ESTADO_INICIAL = ESTADOS[0]
ESTADO_FINAL = "RESUELTO"
_CHECK_ESTADOS = ", ".join(f"'{e}'" for e in ESTADOS)

_ESQUEMA = f"""
CREATE TABLE IF NOT EXISTS reclamo (
    id_reclamo          SERIAL PRIMARY KEY,
    cuenta              INTEGER      NOT NULL,
    cliente_nombre      VARCHAR(120) NOT NULL,
    telefono            VARCHAR(60),
    vendedor_codigo     INTEGER      NOT NULL,
    vendedor_nombre     VARCHAR(80)  NOT NULL,
    estado              VARCHAR(20)  NOT NULL DEFAULT '{ESTADO_INICIAL}'
                        CONSTRAINT reclamo_estado_check CHECK (estado IN ({_CHECK_ESTADOS})),
    creado_por          VARCHAR(60),
    fecha_creacion      TIMESTAMP    NOT NULL DEFAULT now(),
    fecha_actualizacion TIMESTAMP    NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS reclamo_factura (
    id_reclamo_factura SERIAL PRIMARY KEY,
    id_reclamo         INTEGER       NOT NULL REFERENCES reclamo(id_reclamo) ON DELETE CASCADE,
    tc                 VARCHAR(2)    NOT NULL,
    clase              VARCHAR(1)    NOT NULL,
    nro_est            INTEGER       NOT NULL,
    nc                 BIGINT        NOT NULL,
    fecha_emision      DATE          NOT NULL,
    total              NUMERIC(14,2) NOT NULL,
    saldo              NUMERIC(14,2) NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_reclamo_factura_clave ON reclamo_factura (clase, nro_est, nc);
CREATE INDEX IF NOT EXISTS idx_reclamo_estado ON reclamo (estado);

-- Números de WhatsApp. ``codigo_vendedor`` = ctaclien.VENDEDOR = usuario.vendedor_id
-- (NULL para quien no es vendedor del sistema). ``es_remitente``: la línea desde la
-- que se envían los mensajes (una sola).
CREATE TABLE IF NOT EXISTS contacto_whatsapp (
    id_contacto     SERIAL PRIMARY KEY,
    nombre          VARCHAR(60) NOT NULL UNIQUE,
    telefono        VARCHAR(20) NOT NULL,
    codigo_vendedor INTEGER UNIQUE,
    es_remitente    BOOLEAN NOT NULL DEFAULT FALSE
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_contacto_remitente ON contacto_whatsapp (es_remitente) WHERE es_remitente;
"""

# Carga inicial. ON CONFLICT DO NOTHING: si después se edita un número en la base,
# volver a abrir la app no lo pisa. Diego (vendedor 5) usa la misma línea que Maxi
# (confirmado por el usuario), por eso el número se repite.
_CONTACTOS_INICIALES = (
    ("Martin", "2645048307", 9, True),
    ("Miguel", "2646600437", 3, False),
    ("Maxi", "2645047459", None, False),
    ("Angeles", "2645060925", None, False),
    ("Julieta", "2644174385", None, False),
    ("Jose", "2645044432", 4, False),
    ("Matias", "2644437285", 6, False),
    ("Romulo", "2645043510", 1, False),
    ("Diego", "2645047459", 5, False),
)


def conectar():
    """Conexión a la base de Pedidos (``_conexion`` del módulo Pedidos: es la
    base real, NO la de ``config.DB_*``). Import diferido: ese módulo es pesado."""
    from src.Views.Pedidos.programarPedido import _conexion
    return _conexion()


def asegurar_esquema(con):
    """Crea las tablas si no existen y carga los contactos iniciales (idempotente)."""
    with con.cursor() as cur:
        cur.execute(_ESQUEMA)
        _migrar_estados(cur)
        for nombre, telefono, codigo, remitente in _CONTACTOS_INICIALES:
            cur.execute(
                "INSERT INTO contacto_whatsapp (nombre, telefono, codigo_vendedor, es_remitente) "
                "VALUES (%s, %s, %s, %s) ON CONFLICT DO NOTHING",
                (nombre, telefono, codigo, remitente),
            )


def _migrar_estados(cur):
    """Tablas creadas antes de existir NO CONTACTADO: les cambia el CHECK y el valor
    por defecto del estado. No toca los reclamos existentes. Solo actúa si hace falta
    (cambiar un CHECK bloquea la tabla un instante y varias PCs abren la app a la vez)."""
    cur.execute(
        "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
        "WHERE conrelid = 'reclamo'::regclass AND conname = 'reclamo_estado_check'"
    )
    fila = cur.fetchone()
    if fila is not None and ESTADO_INICIAL in fila[0]:
        return
    cur.execute("ALTER TABLE reclamo DROP CONSTRAINT IF EXISTS reclamo_estado_check")
    cur.execute(f"ALTER TABLE reclamo ADD CONSTRAINT reclamo_estado_check CHECK (estado IN ({_CHECK_ESTADOS}))")
    cur.execute(f"ALTER TABLE reclamo ALTER COLUMN estado SET DEFAULT '{ESTADO_INICIAL}'")


def telefono_vendedor(con, codigo):
    """Número de WhatsApp del vendedor con ese código, o ``None`` si no hay."""
    if codigo is None:
        return None
    with con.cursor() as cur:
        cur.execute("SELECT telefono FROM contacto_whatsapp WHERE codigo_vendedor = %s", (codigo,))
        fila = cur.fetchone()
    return fila[0] if fila else None


def telefono_remitente(con):
    """Número desde el que se envían los mensajes (hoy el de Martin), o ``None``."""
    with con.cursor() as cur:
        cur.execute("SELECT telefono FROM contacto_whatsapp WHERE es_remitente")
        fila = cur.fetchone()
    return fila[0] if fila else None


def texto_comprobante(tc, clase, nro_est, nc):
    """'FC A 0003-00008808'."""
    return f"{tc} {clase} {int(nro_est):04d}-{int(nc):08d}"


# ── validaciones (sin base) ──────────────────────────────────────────────────
def validar_estado(estado):
    if estado not in ESTADOS:
        raise ValueError(f"Estado inválido: «{estado}». Valores permitidos: {', '.join(ESTADOS)}.")


def validar_reclamo(cliente, telefono, vendedor_codigo, vendedor_nombre, facturas):
    if not str(cliente or "").strip():
        raise ValueError("Falta seleccionar el cliente.")
    if not facturas:
        raise ValueError("Seleccioná al menos una factura a reclamar.")
    if vendedor_codigo is None or not str(vendedor_nombre or "").strip():
        raise ValueError("Falta seleccionar el vendedor al que corresponde el reclamo.")
    if not str(telefono or "").strip():
        raise ValueError("Falta el teléfono del cliente: no figura en CTACLIEN, ingresalo a mano.")


# ── consultas ────────────────────────────────────────────────────────────────
def facturas_reclamadas(con):
    """``{(cuenta, clase, nro_est, nc): id_reclamo}`` de las facturas que están en
    un reclamo **activo** (no RESUELTO)."""
    with con.cursor() as cur:
        cur.execute(
            "SELECT r.cuenta, f.clase, f.nro_est, f.nc, r.id_reclamo "
            "FROM reclamo_factura f JOIN reclamo r ON r.id_reclamo = f.id_reclamo "
            "WHERE r.estado <> %s",
            (ESTADO_FINAL,),
        )
        return {(c, cl, ne, nc): rid for c, cl, ne, nc, rid in cur.fetchall()}


def listar_reclamos(con, incluir_resueltos=False):
    """Reclamos, el más nuevo primero. Por defecto solo los activos."""
    with con.cursor() as cur:
        cur.execute(
            """
            SELECT r.id_reclamo, r.cuenta, r.cliente_nombre, r.telefono, r.vendedor_nombre,
                   r.vendedor_codigo, r.estado, r.fecha_creacion, r.fecha_actualizacion,
                   floor(extract(epoch FROM (now() - r.fecha_actualizacion)) / 86400)::int,
                   COUNT(f.id_reclamo_factura),
                   COALESCE(SUM(f.saldo), 0),
                   COALESCE(string_agg(
                       f.tc || ' ' || f.clase || ' ' || lpad(f.nro_est::text, 4, '0') || '-' ||
                       lpad(f.nc::text, 8, '0'), ', ' ORDER BY f.fecha_emision, f.nc), '')
            FROM reclamo r LEFT JOIN reclamo_factura f ON f.id_reclamo = r.id_reclamo
            WHERE %s OR r.estado <> %s
            GROUP BY r.id_reclamo
            ORDER BY r.fecha_creacion DESC, r.id_reclamo DESC
            """,
            (bool(incluir_resueltos), ESTADO_FINAL),
        )
        filas = cur.fetchall()
    df = pd.DataFrame(filas, columns=[
        "id_reclamo", "cuenta", "cliente", "telefono", "vendedor", "vendedor_codigo", "estado", "creado",
        "actualizado", "dias_sin_novedad", "n_facturas", "saldo", "comprobantes",
    ])
    df["saldo"] = df["saldo"].astype(float)
    df["n_facturas"] = df["n_facturas"].astype(int)
    df["dias_sin_novedad"] = df["dias_sin_novedad"].astype(int)
    return df


# ── alertas: reclamos que llevan mucho sin actualizarse ──────────────────────
#: Días sin actualizar el estado a partir de los cuales un reclamo activo genera una alerta.
#: Se mide desde la ÚLTIMA actualización (la creación cuenta como una).
DIAS_SIN_NOVEDADES = 7
_DIAS_ALERTA_MAX = 365


def dias_de_alerta(valor=None):
    """Umbral de la alerta en días. ``valor`` viene de ``RECLAMOS_ALERTA_DIAS``; si falta
    o es absurdo, 7."""
    try:
        dias = int(str(valor).strip())
    except (TypeError, ValueError):
        return DIAS_SIN_NOVEDADES
    return dias if 1 <= dias <= _DIAS_ALERTA_MAX else DIAS_SIN_NOVEDADES


def sin_novedades(reclamos, dias=None):
    """Reclamos **activos** que llevan ``dias`` o más sin actualizar su estado, el más
    antiguo primero. Un reclamo RESUELTO no alerta nunca, por viejo que sea.

    :param reclamos: DataFrame de :func:`listar_reclamos` (usa ``estado`` y ``dias_sin_novedad``).
    """
    dias = DIAS_SIN_NOVEDADES if dias is None else dias
    mascara = (reclamos["estado"] != ESTADO_FINAL) & (reclamos["dias_sin_novedad"] >= dias)
    return reclamos[mascara].sort_values("dias_sin_novedad", ascending=False, kind="stable").reset_index(drop=True)


def reclamos_sin_novedades(con, dias=None):
    """Consulta los reclamos activos y devuelve los que llevan ``dias`` o más sin novedades."""
    return sin_novedades(listar_reclamos(con), dias)


def _dias_txt(n):
    return "1 día" if n == 1 else f"{n} días"


def texto_alerta(vencidos, dias=None):
    """``(título, mensaje)`` para avisar de los reclamos de ``vencidos`` (salida de
    :func:`sin_novedades`), o ``None`` si no hay ninguno."""
    if vencidos.empty:
        return None
    dias = DIAS_SIN_NOVEDADES if dias is None else dias
    peor = vencidos.loc[vencidos["dias_sin_novedad"].idxmax()]
    if len(vencidos) == 1:
        return ("Reclamo sin novedades",
                f"El reclamo #{peor['id_reclamo']} de {peor['cliente']} lleva "
                f"{_dias_txt(int(peor['dias_sin_novedad']))} sin actualizar su estado.")
    return ("Reclamos sin novedades",
            f"{len(vencidos)} reclamos llevan {dias} o más días sin actualizar su estado. "
            f"El más antiguo: {peor['cliente']} (#{peor['id_reclamo']}), {_dias_txt(int(peor['dias_sin_novedad']))}.")


# ── escritura ────────────────────────────────────────────────────────────────
def crear_reclamo(con, *, cuenta, cliente, telefono, vendedor_codigo, vendedor_nombre,
                  facturas, creado_por=""):
    """Crea un reclamo en estado SIN RESPUESTA y devuelve su id.

    :param facturas: lista de dicts con ``tc, clase, nro_est, nc, fecha_emision,
        total, saldo``. Una factura no puede estar en dos reclamos activos.
    """
    validar_reclamo(cliente, telefono, vendedor_codigo, vendedor_nombre, facturas)

    en_reclamo = facturas_reclamadas(con)
    for f in facturas:
        clave = (cuenta, f["clase"], int(f["nro_est"]), int(f["nc"]))
        if clave in en_reclamo:
            raise ValueError(
                f"La factura {texto_comprobante(f['tc'], f['clase'], f['nro_est'], f['nc'])} "
                f"ya está en el reclamo activo #{en_reclamo[clave]}."
            )

    with con.cursor() as cur:
        cur.execute(
            "INSERT INTO reclamo (cuenta, cliente_nombre, telefono, vendedor_codigo, vendedor_nombre, estado, creado_por) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id_reclamo",
            (cuenta, str(cliente).strip(), str(telefono).strip(), vendedor_codigo,
             str(vendedor_nombre).strip(), ESTADO_INICIAL, creado_por or None),
        )
        id_reclamo = cur.fetchone()[0]
        for f in facturas:
            cur.execute(
                "INSERT INTO reclamo_factura (id_reclamo, tc, clase, nro_est, nc, fecha_emision, total, saldo) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                (id_reclamo, f["tc"], f["clase"], int(f["nro_est"]), int(f["nc"]),
                 f["fecha_emision"], round(float(f["total"]), 2), round(float(f["saldo"]), 2)),
            )
    return id_reclamo


def facturas_de_reclamo(con, id_reclamo):
    """Facturas de un reclamo (con el saldo del momento de reclamar), la más vieja primero."""
    with con.cursor() as cur:
        cur.execute(
            "SELECT tc, clase, nro_est, nc, fecha_emision, total, saldo FROM reclamo_factura "
            "WHERE id_reclamo = %s ORDER BY fecha_emision, nc",
            (id_reclamo,),
        )
        filas = cur.fetchall()
    return pd.DataFrame(
        [(texto_comprobante(tc, cl, ne, nc), pd.Timestamp(fe), float(tot), float(sal))
         for tc, cl, ne, nc, fe, tot, sal in filas],
        columns=["comprobante", "fecha_emision", "total", "saldo"],
    )


def renovar_reclamo(con, id_reclamo):
    """Marca el reclamo como **revisado hoy**: reinicia el plazo de la alerta SIN cambiar su
    estado (p. ej. se llamó al cliente, sigue sin responder). Un reclamo resuelto no se renueva."""
    with con.cursor() as cur:
        cur.execute("SELECT estado FROM reclamo WHERE id_reclamo = %s", (id_reclamo,))
        fila = cur.fetchone()
        if fila is None:
            raise ValueError(f"No existe el reclamo #{id_reclamo}.")
        if fila[0] == ESTADO_FINAL:
            raise ValueError(f"El reclamo #{id_reclamo} ya está resuelto.")
        cur.execute("UPDATE reclamo SET fecha_actualizacion = now() WHERE id_reclamo = %s", (id_reclamo,))


def cambiar_estado(con, id_reclamo, estado):
    validar_estado(estado)
    with con.cursor() as cur:
        cur.execute(
            "UPDATE reclamo SET estado = %s, fecha_actualizacion = now() WHERE id_reclamo = %s",
            (estado, id_reclamo),
        )
        if cur.rowcount == 0:
            raise ValueError(f"No existe el reclamo #{id_reclamo}.")
