-- Panel de cada vendedor: una fila por codigo de vendedor con SUS numeros (litros, cartera, cobrado por mes y
-- sus clientes con el detalle de facturas). La calcula el mismo proceso del servidor que arma el panel general
-- (movil/panel/worker.py) y la API solo lee la fila del vendedor que pregunta (GET /panel/mio): el codigo sale
-- del usuario que inicio sesion (usuario.vendedor_id), nunca de lo que mande el celular.
-- Va aparte de panel_resumen a proposito: GET /panel (admin) devuelve esa fila entera y no tiene que arrastrar
-- los datos de todos los vendedores.
-- Aditivo e idempotente: se puede aplicar mas de una vez.

CREATE TABLE IF NOT EXISTS panel_vendedor (
    vendedor_id  integer PRIMARY KEY,                    -- codigo del vendedor: ctaclien.VENDEDOR = usuario.vendedor_id
    datos        jsonb NOT NULL,                         -- el panel de ese vendedor (movil/panel/vendedores.py)
    calculado_en timestamptz NOT NULL DEFAULT clock_timestamp()
);
