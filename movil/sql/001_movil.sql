-- Migración aditiva: permite que los pedidos creados desde el celular (movil/)
-- convivan con los de la PC, sin tocar su comportamiento. Columnas nuevas con
-- default o NULL: un INSERT de la PC (sin estas columnas) sigue andando igual.
-- Idempotente: se puede aplicar más de una vez (todo IF NOT EXISTS).

ALTER TABLE pedido ADD COLUMN IF NOT EXISTS origen text NOT NULL DEFAULT 'pc'
    CHECK (origen IN ('pc', 'movil'));

ALTER TABLE pedido ADD COLUMN IF NOT EXISTS uuid_cliente uuid;

CREATE UNIQUE INDEX IF NOT EXISTS ux_pedido_uuid_cliente
    ON pedido (uuid_cliente) WHERE uuid_cliente IS NOT NULL;

-- creado_por (ya existe, sin uso): la API guarda ahí el username del vendedor.
-- Los pedidos de la PC siguen con creado_por = NULL.
