-- Avisos (notificaciones push) a los celulares: pedido nuevo de un vendedor, pedido programado y
-- pedido entregado. Dos tablas nuevas, solo del celular: no se toca ninguna tabla del sistema.
-- Aditivo e idempotente: se puede aplicar mas de una vez.

-- Un renglon por celular/navegador que acepto recibir avisos. `endpoint` identifica al dispositivo en el
-- servicio de push de Google/Apple; `p256dh` y `auth` son las claves con las que se cifra el contenido
-- (no son secretas frente al servidor: son las que el propio telefono entrego al suscribirse).
CREATE TABLE IF NOT EXISTS push_suscripcion (
    id         bigserial PRIMARY KEY,
    usuario_id integer NOT NULL REFERENCES usuario (id) ON DELETE CASCADE,
    endpoint   text NOT NULL UNIQUE,
    p256dh     text NOT NULL,
    auth       text NOT NULL,
    creado_en  timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS push_suscripcion_usuario_idx ON push_suscripcion (usuario_id);

-- Avisos que ya se enviaron (o que no correspondia enviar), por pedido y tipo: asi el proceso que mira la
-- tabla `pedido` no repite un aviso ni, al instalarse, manda uno por cada pedido que ya existia.
CREATE TABLE IF NOT EXISTS notificacion_enviada (
    evento     text NOT NULL CHECK (evento IN ('nuevo', 'programado', 'entregado')),
    id_pedido  integer NOT NULL,
    enviado_en timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (evento, id_pedido)
);
