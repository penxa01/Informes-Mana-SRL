-- Panel de control: una sola fila con el ultimo resultado calculado (litros del mes, % premium,
-- recaudado de la semana). La calcula un proceso del servidor (movil/panel/worker.py) y la API
-- solo la lee, asi el celular recibe el panel al instante sin leer los archivos del sistema.
-- Aditivo e idempotente: se puede aplicar mas de una vez.

CREATE TABLE IF NOT EXISTS panel_resumen (
    id           smallint PRIMARY KEY DEFAULT 1 CHECK (id = 1),   -- una sola fila
    datos        jsonb,          -- el panel; NULL hasta el primer calculo exitoso
    fuentes      jsonb,          -- tamano y fecha de los archivos usados: si no cambiaron, no se recalcula
    calculado_en timestamptz,    -- cuando se calculo `datos` por ultima vez
    intento_en   timestamptz NOT NULL DEFAULT now(),   -- ultimo intento, haya salido bien o mal
    error        text,           -- motivo del ultimo intento fallido (NULL si salio bien)
    verificado_en timestamptz    -- ultima vez que el proceso reviso (aunque no hubiera nada que recalcular):
                                 -- si pasa mucho tiempo, el proceso del servidor esta caido
);

-- Para la tabla que ya existia antes de agregar el latido (idempotente).
ALTER TABLE panel_resumen ADD COLUMN IF NOT EXISTS verificado_en timestamptz;
