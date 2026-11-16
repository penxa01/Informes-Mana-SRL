-- Observaciones del pedido: un texto libre y opcional que el vendedor escribe al cargarlo (por ejemplo "dejar en la
-- porteria" o "llamar antes de ir") y que se ve en la gestion del admin, en el reparto y en la PC.
-- Aditivo e idempotente: los pedidos que ya existen quedan con NULL (sin observaciones). El largo lo limita la app y la
-- API (movil/api/pedidos.py); la base no pone tope a proposito, para que la PC pueda cambiarlo sin migrar.

ALTER TABLE pedido ADD COLUMN IF NOT EXISTS observaciones text;
