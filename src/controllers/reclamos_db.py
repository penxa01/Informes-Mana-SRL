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

ESTADOS = ("SIN RESPUESTA", "CONTACTADO", "PENDIENTE DE O/P", "RESUELTO")
ESTADO_INICIAL = ESTADOS[0]
ESTADO_FINAL = "RESUELTO"

_ESQUEMA = f"""
CREATE TABLE IF NOT EXISTS reclamo (
    id_reclamo          SERIAL PRIMARY KEY,
    cuenta              INTEGER      NOT NULL,
    cliente_nombre      VARCHAR(120) NOT NULL,
    telefono            VARCHAR(60),
    vendedor_codigo     INTEGER      NOT NULL,
    vendedor_nombre     VARCHAR(80)  NOT NULL,
    estado              VARCHAR(20)  NOT NULL DEFAULT '{ESTADO_INICIAL}'
                        CHECK (estado IN ({", ".join(f"'{e}'" for e in ESTADOS)})),
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
# volver a abrir la app no lo pisa. Diego Calderon (vendedor 5) no tiene número.
_CONTACTOS_INICIALES = (
    ("Martin", "2645048307", 9, True),
    ("Miguel", "2646600437", 3, False),
    ("Maxi", "2645047459", None, False),
    ("Angeles", "2645060925", None, False),
    ("Julieta", "2644174385", None, False),
    ("Jose", "2645044432", 4, False),
    ("Matias", "2644437285", 6, False),
    ("Romulo", "2645043510", 1, False),
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
        for nombre, telefono, codigo, remitente in _CONTACTOS_INICIALES:
            cur.execute(
                "INSERT INTO contacto_whatsapp (nombre, telefono, codigo_vendedor, es_remitente) "
                "VALUES (%s, %s, %s, %s) ON CONFLICT DO NOTHING",
                (nombre, telefono, codigo, remitente),
            )


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
                   r.estado, r.fecha_creacion,
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
        "id_reclamo", "cuenta", "cliente", "telefono", "vendedor", "estado", "creado",
        "n_facturas", "saldo", "comprobantes",
    ])
    df["saldo"] = df["saldo"].astype(float)
    df["n_facturas"] = df["n_facturas"].astype(int)
    return df


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
            "INSERT INTO reclamo (cuenta, cliente_nombre, telefono, vendedor_codigo, vendedor_nombre, creado_por) "
            "VALUES (%s, %s, %s, %s, %s, %s) RETURNING id_reclamo",
            (cuenta, str(cliente).strip(), str(telefono).strip(), vendedor_codigo,
             str(vendedor_nombre).strip(), creado_por or None),
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


def cambiar_estado(con, id_reclamo, estado):
    validar_estado(estado)
    with con.cursor() as cur:
        cur.execute(
            "UPDATE reclamo SET estado = %s, fecha_actualizacion = now() WHERE id_reclamo = %s",
            (estado, id_reclamo),
        )
        if cur.rowcount == 0:
            raise ValueError(f"No existe el reclamo #{id_reclamo}.")
