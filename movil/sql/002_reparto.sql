-- Migración aditiva para el perfil de reparto: ubicación de Google Maps del cliente.
-- NULL hasta que alguien la cargue; el alta/actualización de clientes de la PC
-- (ImportThread) nombra sus columnas una por una y no la pisa.
-- El CHECK deja pasar solo enlaces http(s): el reparto la abre como enlace desde el
-- celular, y así nunca puede guardarse algo tipo `javascript:...`.
-- Idempotente: se puede aplicar más de una vez.

ALTER TABLE cliente ADD COLUMN IF NOT EXISTS ubicacion_maps text
    CHECK (ubicacion_maps IS NULL OR ubicacion_maps ~* '^https?://');

-- Coordenadas sacadas del enlace al guardarlo (la PC las calcula una sola vez): así
-- el mapita se dibuja sin resolver el enlace cada vez. Pueden quedar NULL si no se
-- las pudo leer del enlace; en ese caso solo se ofrece abrirlo en Maps.
ALTER TABLE cliente ADD COLUMN IF NOT EXISTS ubicacion_lat double precision
    CHECK (ubicacion_lat IS NULL OR ubicacion_lat BETWEEN -90 AND 90);
ALTER TABLE cliente ADD COLUMN IF NOT EXISTS ubicacion_lng double precision
    CHECK (ubicacion_lng IS NULL OR ubicacion_lng BETWEEN -180 AND 180);
