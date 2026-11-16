# Views / Pedidos — `src/Views/Pedidos/programarPedido.py`

Módulo **Pedidos**: alta, seguimiento y entrega (parcial/total) de pedidos de clientes.
Es el **único módulo que usa PostgreSQL** (base `pedidosMana`), no DBF como fuente viva.

Archivo único (~2100 líneas). Clases:

| Clase | Rol |
|---|---|
| `VentanaProgramarPedido(QWidget)` | Panel principal: barra de sync + KPIs + "Pendientes" y "Entregados (7 días)". Embebido en `src/ui/paginas/pedidos.py` (`PaginaPedidos`) |
| `DialogoNuevoPedido(QDialog)` | Alta de pedido (cliente + productos) |
| `VentanaDetallePedido(QDialog)` | Detalle de un pedido + acciones de entrega |
| `VentanaHistorialCompleto(QDialog)` | Listado completo con filtro |
| `DatabaseSyncManager(QObject)` | Polling cada 8 s + notificaciones toast |
| `ImportThread(QThread)` | Importa clientes/productos desde DBF a PostgreSQL |
| `NotificationWidget` / `NotificationManager` | Toasts animados esquina superior derecha |

Helpers a nivel de módulo (rama `style/pedidos-tailwind-look`): `_conexion()`,
`_pill_estado(estado)`, `_celda_cliente(nombre, sub)`, `_centrar(w)`,
`_QSS_DIALOGO_PEDIDO`, mapa `_ESTADO_PILL`.

Se abre con `main.pedidosCaller()` → `VentanaProgramarPedido().show()` (sin diálogo previo,
no depende de `df_ventas`).

---

## Conexión a la base

**`_conexion()` — función única de módulo** (antes `obtener_conexion()` estaba
duplicado idéntico en 6 clases; ahora cada uno delega en ella).

```python
_PEDIDOS_DB_HOST     = os.getenv("PEDIDOS_DB_HOST",     "DESKTOP-R8E4V7S")
_PEDIDOS_DB_NAME     = os.getenv("PEDIDOS_DB_NAME",     "pedidosMana")
_PEDIDOS_DB_USER     = os.getenv("PEDIDOS_DB_USER",     "postgres")
_PEDIDOS_DB_PASSWORD = os.getenv("PEDIDOS_DB_PASSWORD", "manapedidos2025")
# psycopg2.connect(host=gethostbyname(HOST), ..., connect_timeout=6)
```

> ⚠️ **NO usa `config.DB_*`**: eso apunta a un postgres **local** (`localhost` / pw
> `011201`) que pertenece a `controllerDialogos.py` / `controllerBD.py`, otra base.
> La de Pedidos es la remota `DESKTOP-R8E4V7S`. Se agregó `connect_timeout=6` para
> que la UI no se cuelgue si la BD no responde, y override por variable de entorno.

---

## Esquema de base (inferido de las queries)

```
Cliente(
    id_cliente      PK,
    nombre,
    direccion,
    telefono,
    cuit            VARCHAR(15),   -- agregada por ImportThread (ADD COLUMN IF NOT EXISTS)
    localidad       VARCHAR(100),  -- idem
    tasacero        VARCHAR(1)     -- idem
)

Producto(
    id_producto        PK,
    nombre,
    stock_disponible   INTEGER DEFAULT 0   -- agregada por ImportThread
)

Pedido(
    id_pedido       PK (serial),
    id_cliente      FK -> Cliente,
    fecha_pedido    date,
    estado_pedido   text,     -- 'pendiente' | 'programado' | 'en camino' | 'entregado'
    fecha_entrega   date NULL,
    observaciones   text NULL        -- texto libre y opcional (tope 500 caracteres, lo limita la app); lo agrega
                                     -- movil/migrar.py (sql/006). Si la base todavía no la tiene, la PC trabaja
                                     -- como siempre (`_observaciones_disponibles`)
)

DetallePedido(
    id_detalle           PK (serial),
    id_pedido            FK -> Pedido,
    id_producto          FK -> Producto,
    cantidad             int,
    cantidad_entregada   int DEFAULT 0,
    precio_unitario      numeric,   -- hoy siempre 0.00
    estado_entrega       text GENERATED ALWAYS AS (
                             CASE WHEN cantidad_entregada = 0        THEN 'pendiente'
                                  WHEN cantidad_entregada >= cantidad THEN 'completa'
                                  ELSE 'parcial' END) STORED
)
```

> ⚠️ **`estado_entrega` es una columna GENERADA**: se recalcula sola desde
> `cantidad_entregada`. No se puede INSERT/UPDATE (tira `GeneratedAlways`).

### Trigger `trg_actualizar_estado_pedido`

`AFTER UPDATE OF cantidad_entregada ON DetallePedido` → función `actualizar_estado_pedido()`:
si ninguna línea del pedido tiene `cantidad_entregada < cantidad`, hace
`UPDATE Pedido SET estado_pedido = 'entregado'`. O sea el pase a 'entregado' está
**doblemente asegurado** (trigger + el UPDATE explícito del código). El trigger NO toca
`fecha_entrega`.

### Estados del pedido

| Estado | Cómo se llega | Panel donde aparece |
|---|---|---|
| `pendiente` | al crear el pedido | Pendientes |
| `pendiente` (otra vez) | entrega parcial que deja algo sin entregar (`fecha_entrega` vuelve a NULL) | Pendientes |
| `programado` | `programar_entrega()` + `fecha_entrega` | Pendientes |
| `en camino` | `marcar_en_camino()` | Pendientes |
| `entregado` | entrega parcial que completa todo, o entrega completa | Entregados |

El panel "Pendientes" muestra `estado_pedido IN ('pendiente', 'programado', 'en camino')`.
El panel "Entregados" muestra `estado_pedido = 'entregado' AND fecha_entrega >= CURRENT_DATE - INTERVAL '7 days'`.

---

## `DatabaseSyncManager` — sincronización y notificaciones

> **F2d:** lo instancia el `AppWindow` una sola vez y **queda siempre activo** (notificaciones
> aunque estés en otra sección). `PaginaPedidos` recibe esa instancia. Uso legacy: si
> `VentanaProgramarPedido(sync_manager=None)` se crea uno propio.

- `QTimer` cada **8000 ms** → `check_for_changes()`.
- Query de pendientes + query de entregados (última semana). Calcula `md5(str(resultado))`.
- Si el hash cambió respecto al anterior → emite señal (`pedidos_pendientes_changed` /
  `pedidos_entregados_changed`) y, si **no** fue un cambio local, llama a
  `detectar_cambios_*` para disparar toasts:
  - pedido nuevo → toast "🆕 Nuevo Pedido"
  - cambio de estado → toast "📝 Estado Actualizado: X → Y"
  - fecha de entrega asignada → toast "📅 Entrega Programada"
  - pedido que salió de pendientes → toast "✅ Pedido Completado"
  - nuevo entregado → toast "🚚 Entrega Completada"
- **`marcar_cambio_local()`**: cada acción de escritura del propio usuario llama esto antes de
  ejecutar; pone `cambios_locales = True` (se resetea solo a los 5 s o tras el próximo check)
  para **no auto-notificarse**.
- `force_refresh()` (se llama después de cada escritura local): pone `cambios_locales = True`,
  blanquea los hashes, hace `check_for_changes()` para regrabar el baseline, y **emite
  explícitamente** `pedidos_pendientes_changed` + `pedidos_entregados_changed` para recargar
  los paneles.
  > 🐞 **Bug corregido** (`checkpoint-pre-fixes-echeq-pedidos`): antes solo blanqueaba los
  > hashes + `check_for_changes()`. Con el hash en `""` ese método entra por la rama
  > "primer arranque": **guarda el hash y no emite nada**. Resultado: los paneles no se
  > recargaban tras una acción local (un pedido entregado seguía en "Pendientes" hasta
  > reiniciar la app). Los dos `emit()` explícitos son el fix.

> ⚠️ El polling abre una conexión nueva cada 8 s. Si la BD no responde, `print(error)` y sigue.

---

## Flujos de negocio

### Alta — `DialogoNuevoPedido.crear_pedido()`
1. Valida cliente seleccionado y al menos un producto.
2. `sync_manager.marcar_cambio_local()`.
3. `INSERT INTO Pedido (id_cliente, fecha_pedido, estado_pedido) VALUES (%s, %s, 'pendiente') RETURNING id_pedido`.
   Con **observaciones** (cuadro "Observaciones (opcional)" del diálogo, `QPlainTextEdit`, tope `OBSERVACIONES_MAX` = 500) y
   si la base ya tiene la columna, el INSERT lleva también `observaciones`; en blanco se guarda NULL. Si la base todavía no
   tiene la columna el pedido se crea igual y un aviso dice que las observaciones no se guardaron. En el **detalle** del
   pedido (`VentanaDetallePedido`) aparece una tarjeta "Observaciones" solo si las tiene, y en las **grillas** de pendientes y
   entregados el subtítulo de la celda Cliente las resume ("Obs.: …") y el mouse encima las muestra enteras. Los pedidos que
   cargan los vendedores desde el celular traen las suyas. Test: `tests/verificar_pedido_observaciones.py`.
4. Por cada fila de la tabla: `INSERT INTO DetallePedido (id_pedido, id_producto, cantidad, precio_unitario)`
   con `precio_unitario = 0.00` (**siempre 0** — "Precio 0 por ahora").
5. `commit`, emite `pedido_creado(id_pedido)`, `sync_manager.force_refresh()`.
- Combos: `SELECT id_cliente, nombre, cuit FROM Cliente` (el `currentData` del combo de
  cliente es una **tupla `(id, cuit)`** — el CUIT se muestra bajo el selector) y
  `SELECT id_producto, nombre FROM Producto` (`currentData` = tupla `(id, nombre)`).
  Filtro por texto en memoria.
- **`_quitar_fila_producto()`** (antes `eliminar_producto(fila)`): identifica la fila por
  `self.sender()` (el botón), no por un índice capturado en el lambda — el viejo se
  desincronizaba al borrar filas del medio. Renumera la columna `#` y recalcula el
  resumen ("Líneas activas / Total bultos").

### Agregar productos a un pedido existente — `VentanaDetallePedido.agregar_producto()`
Barra "Buscar producto para agregar" sobre la grilla de productos (visible mientras el pedido **no** esté
`entregado`; se revalida contra la base al agregar). Si el producto ya está en el pedido **suma** la cantidad a
esa línea (`UPDATE DetallePedido SET cantidad = cantidad + %s`); si no, `INSERT` con `precio_unitario = 0`.
Recarga detalle, productos y entrega parcial, emite `pedido_updated` y llama a `force_refresh()`.
Test: `tests/verificar_pedido_agregar.py` (transacción revertida).

### Quitar un artículo del pedido — `VentanaDetallePedido.quitar_producto()`
Cada fila de "Productos del Pedido" lleva una **✕** (columna 7; no aparece si el pedido está `entregado`). La regla vive en
dos funciones de módulo, las mismas reglas que el celular (`movil/api/db.py`, `quitar_linea`):
- `_motivo_no_quitable(n_lineas, entregada)`: **no el único artículo** (un pedido vacío no tiene sentido: se elimina el
  pedido) y **no uno del que ya se entregó algo** (se perdería el registro de lo entregado). En esos casos la ✕ queda
  apagada y el mouse encima explica por qué.
- `_quitar_linea_pedido(cur, id_pedido, id_detalle)`: `SELECT … FOR UPDATE` del pedido y sus líneas, `DELETE FROM DetallePedido
  WHERE id_detalle = %s AND id_pedido = %s` y, si lo que queda ya estaba todo entregado, `UPDATE Pedido SET estado_pedido =
  'entregado', fecha_entrega = hoy` (el trigger `actualizar_estado_pedido` solo corre al ACTUALIZAR `cantidad_entregada`, no al
  borrar una línea, así que se hace a mano). Devuelve `quitada | completo | ya_no_estaba | no_existe | ya_entregado |
  entregada_en_parte | es_la_unica`; no hace commit.
`quitar_producto()` identifica el botón con `sender()` y la propiedad `id_detalle` (no con lambda), pregunta, aplica, avisa si
no se pudo y recarga las 3 tablas, emite `pedido_updated` y llama a `force_refresh()`. `cargar_productos_pedido` ahora trae
también `dp.id_detalle`.
Test: `tests/verificar_pedido_quitar_articulo.py` (transacción revertida).

### Programar entrega — `VentanaDetallePedido.programar_entrega()`
`UPDATE Pedido SET estado_pedido = 'programado', fecha_entrega = %s WHERE id_pedido = %s`.
La grilla del panel se refresca sola: `_fila_pedido` saca el chip "Sin programar" (`removeCellWidget`) cuando la
fila ya tiene fecha, porque un `cellWidget` tapa al item y, al reusar filas, el chip viejo seguía visible.

### En camino — `marcar_en_camino()`
`UPDATE Pedido SET estado_pedido = 'en camino' WHERE id_pedido = %s`.

### Entrega parcial — `realizar_entrega_parcial()`
1. Por cada producto con cantidad a entregar > 0:
   `UPDATE DetallePedido SET cantidad_entregada = cantidad_entregada + %s WHERE id_pedido = %s AND id_producto = %s`.
2. `SELECT COUNT(*) FROM DetallePedido WHERE id_pedido = %s AND cantidad_entregada < cantidad`.
3. Si el count es 0 (todo entregado):
   `UPDATE Pedido SET estado_pedido = 'entregado', fecha_entrega = %s` (fecha = hoy).
   Si queda algo por entregar **y se entregó algo ahora**: `UPDATE Pedido SET estado_pedido = 'pendiente', fecha_entrega = NULL`
   — el pedido **vuelve a Pendiente** con los productos que faltan (hay que programarlo de nuevo); es la misma regla que el
   celular (`movil/api/db.py`, `entrega_parcial`). Si no se entregó nada, el pedido queda como estaba.
4. Recarga las 3 tablas del detalle, emite `pedido_updated`, `force_refresh`.
Test: `tests/verificar_pedido_entrega_parcial.py` (transacción revertida).

### Entrega completa — `realizar_entrega_completa()`
Confirma con el usuario, luego:
`UPDATE DetallePedido SET cantidad_entregada = cantidad WHERE id_pedido = %s`
+ `UPDATE Pedido SET estado_pedido = 'entregado', fecha_entrega = %s` (hoy).

> 🐞 **Fix** (`checkpoint-pre-fixes-echeq-pedidos`): antes era
> `fecha_entrega = COALESCE(fecha_entrega, hoy)`. Si el pedido estaba `programado`
> para una fecha > 7 días atrás, la entrega conservaba esa fecha vieja y el panel
> "Entregados (última semana)" lo filtraba → el pedido desaparecía de ambos paneles.
> Ahora `fecha_entrega` = la fecha real de entrega (hoy).

### Eliminar — `eliminar_pedido()`
Confirma, luego `DELETE FROM DetallePedido WHERE id_pedido = %s` y `DELETE FROM Pedido WHERE id_pedido = %s`
(en ese orden por la FK). Emite `pedido_deleted`.

### Importar desde DBF — `ImportThread.importar_datos()`
- `self.ruta_dbf = "D:\\tiempo\\vtiempoges\\GESTION\\MANA2014"` ⚠️ **HARDCODEADO** (no usa `config`).
- **Clientes** (`ctaclien.dbf`, `config.DBF_ENCODING` = `cp850`):
  - `ALTER TABLE Cliente ADD COLUMN IF NOT EXISTS` (`cuit`, `localidad`, `tasacero`) — envuelto en `try/except:` desnudo.
  - `INSERT ... ON CONFLICT (id_cliente) DO UPDATE SET ...` (UPSERT) con
    `CNUMERO, CNOMBRE, dirección (CDIREC + LOCALIDAD), TELEFONO, CUIT, LOCALIDAD, TASACERO`.
  - Progreso 0–50 %.
- **Productos** (`abmartic.dbf`, `config.DBF_ENCODING` = `cp850`):
  - `ALTER TABLE Producto ADD COLUMN IF NOT EXISTS stock_disponible INTEGER DEFAULT 0`.
  - `INSERT ... ON CONFLICT (id_producto) DO UPDATE SET nombre = EXCLUDED.nombre` con
    `CODART, DESC, 0` (stock siempre 0 — **no se importa stock real**).
  - Progreso 50–100 %.
- Señales: `progress(int)`, `status(str)`, `finished(bool, str)`.

---

## `VentanaProgramarPedido` — ventana principal

Estética rediseñada según `prototypeExample/prototypePedidos.html` (light Tailwind,
igual que el resto de la app — los prototipos de los diálogos venían oscuros pero se
unificaron a claro).

- **Barra de sync** (`crear_barra_estado`): pill verde con punto animado + "Sincronizando
  cada 8 s" + reloj `HH:MM:SS`.
- **Barra de herramientas** (`self.acciones_toolbar`, franja del `AppWindow`): Nuevo pedido,
  Importar DBF, Actualizar.
- **KPIs** (`crear_kpis` / `_actualizar_kpis`): Pendientes · Entregados (semana) ·
  Entregados (histórico) · Tiempo prom. despacho (`AVG(fecha_entrega - fecha_pedido)` en
  días sobre los entregados). Se recalculan tras cada recarga de panel.
- **Dos paneles** en un `QSplitter` vertical (`_tarjeta_panel` = card blanca con cabecera
  punto+título+badge):
  - Pendientes: `SELECT p.id_pedido, c.nombre, c.cuit, p.fecha_pedido, p.fecha_entrega,
    p.estado_pedido ... WHERE estado_pedido IN ('pendiente','programado','en camino')`.
  - Entregados: mismos campos, `estado_pedido='entregado' AND fecha_entrega >= CURRENT_DATE
    - INTERVAL '7 days'`, `ORDER BY p.fecha_entrega DESC`.
  - `_fila_pedido()` pinta: ID (chip mono azul), Cliente (`_celda_cliente`: avatar con
    inicial + nombre + CUIT), fechas mono, "Sin programar" como chip ámbar, Estado como
    `_pill_estado` (color por estado), botón "Ver".
- Botón "Ver" → `VentanaDetallePedido(id_pedido, sync_manager=...)`.
- Se suscribe a las señales de `DatabaseSyncManager` para refrescar automáticamente.

## `VentanaDetallePedido` — según `prototypeDetallePedido.html`

Header con pill de estado + 4 KPIs (Cliente/Fecha Pedido/Estado/Fecha Entrega) + barra
"Programar Entrega" + card "Productos del Pedido" (tabla 8 col: `#` / SKU / Descripción /
Solicitado / Entregado / A Entregar / Estado-pill / ✕ quitar artículo) + card "Entrega Parcial" (SKU /
Descripción / Pendiente / spinbox) + footer (Entrega Parcial · Entrega Completa · Eliminar
· Cerrar). `cargar_datos_pedido` ahora trae `c.cuit`. La tabla de productos es display-only salvo la ✕
(las acciones de entrega leen `tabla_entrega_parcial`, col 0 = SKU / col 3 = spinbox — sin cambios).

## `DialogoNuevoPedido` — según `prototypeNuevoPedido.html`

Chip "Borrador" + card "Información del Pedido" (buscador + combo cliente + CUIT + fecha) +
card "Productos" (buscador + combo + cantidad + Agregar; tabla 5 col `#`/ID/Descripción/
Cantidad/✕; footer "Líneas activas / Total bultos") + footer (Cancelar · Crear Pedido).

---

## Archivos / recursos que toca

| Recurso | Modo |
|---|---|
| PostgreSQL `pedidosMana` (host `DESKTOP-R8E4V7S`) | lee + escribe (todas las operaciones) |
| `D:\tiempo\vtiempoges\GESTION\MANA2014\ctaclien.dbf` ⚠️ hardcodeado | lee (solo al importar) |
| `D:\tiempo\vtiempoges\GESTION\MANA2014\abmartic.dbf` ⚠️ hardcodeado | lee (solo al importar) |

**No genera archivos Excel ni de texto.** Todo persiste en la base.

---

## Bugs / deuda conocida

- ~~Credenciales y hostname hardcodeados en 6 copias~~ → unificado en `_conexion()`
  (aún con default hardcodeado, pero un solo lugar + override por env + timeout).
- `config.DB_*` NO sirve para este módulo (es de otra base, `controllerDialogos`).
- `precio_unitario` siempre `0.00` → no hay valorización de pedidos.
- `stock_disponible` se crea pero se importa siempre en `0`.
- `estado_entrega` en `DetallePedido` es **GENERATED ALWAYS** (se recalcula sola).
- Polling cada 8 s con conexión nueva cada vez — costo de red/BD constante mientras la ventana está abierta.
- `except:` desnudos en los `ALTER TABLE` (≈líneas 414, 471).
- `ImportThread` duplica la intención de `controllerBD.py` con **otro esquema** (ver [controllers.md](controllers.md)).
