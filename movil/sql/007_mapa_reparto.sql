-- Mapa de clientes y ubicacion del reparto (tarjeta "Mapa de clientes" de la pantalla Pedidos), y una sola sesion
-- para la cuenta de reparto.
--
--  * ubicacion_reparto: la ULTIMA posicion que mando el celular de la cuenta de reparto (una fila por usuario, sin
--    historial: se pisa en cada envio). La API solo la muestra si es reciente (ver movil/api/db.py).
--  * usuario.sesion_id: identificador de la sesion activa de la cuenta de reparto. Se genera al iniciar sesion, viaja
--    dentro del token, y si alguien inicia sesion en otro celular el anterior deja de valer (movil/api/deps.py).
--    Los demas perfiles no lo usan (queda NULL).
-- Aditivo e idempotente: se puede aplicar mas de una vez.

ALTER TABLE usuario ADD COLUMN IF NOT EXISTS sesion_id text;

CREATE TABLE IF NOT EXISTS ubicacion_reparto (
    username        text PRIMARY KEY,                                   -- usuario.username de la cuenta de reparto
    lat             double precision NOT NULL CHECK (lat BETWEEN -90 AND 90),
    lng             double precision NOT NULL CHECK (lng BETWEEN -180 AND 180),
    precision_m     real,                                               -- precision del GPS, en metros (puede faltar)
    actualizado_en  timestamptz NOT NULL DEFAULT now()
);
