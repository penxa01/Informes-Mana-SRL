# Views / Pedidos — `src/Views/Pedidos/programarPedido.py`

Módulo **Pedidos**: alta, seguimiento y entrega (parcial/total) de pedidos de clientes.
Es el **único módulo que usa PostgreSQL** (base `pedidosMana`), no DBF como fuente viva.

Archivo único (~2000 líneas). Clases:

| Clase | Rol |
|---|---|
| `VentanaProgramarPedido(QWidget)` | Panel principal: "Pendientes" y "Entregados (7 días)". Embebido en `src/ui/paginas/pedidos.py` (`PaginaPedidos`) |
| `DialogoNuevoPedido(QDialog)` | Alta de pedido (cliente + productos) |
| `VentanaDetallePedido(QDialog)` | Detalle de un pedido + acciones de entrega |
| `VentanaHistorialCompleto(QDialog)` | Listado completo con filtro |
| `DatabaseSyncManager(QObject)` | Polling cada 8 s + notificaciones toast |
| `ImportThread(QThread)` | Importa clientes/productos desde DBF a PostgreSQL |
| `NotificationWidget` / `NotificationManager` | Toasts animados esquina superior derecha |

Se abre con `main.pedidosCaller()` → `VentanaProgramarPedido().show()` (sin diálogo previo,
no depende de `df_ventas`).

---

## Conexión a la base

**`obtener_conexion()` está duplicado en 6 clases**, idéntico:

```python
ip = socket.gethostbyname("DESKTOP-R8E4V7S")   # ⚠️ hostname hardcodeado
psycopg2.connect(host=ip, database="pedidosMana",
                 user="postgres", password="manapedidos2025")  # ⚠️ credenciales en código
```

> 🔧 Al refactorizar: **una sola** función de conexión que lea de `config.DB_HOST` / `config.DB_NAME`
> / `config.DB_USER` / `config.DB_PASSWORD` (ya existen en `config.py`, hoy sin usar).

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
    fecha_entrega   date NULL
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
4. Por cada fila de la tabla: `INSERT INTO DetallePedido (id_pedido, id_producto, cantidad, precio_unitario)`
   con `precio_unitario = 0.00` (**siempre 0** — "Precio 0 por ahora").
5. `commit`, emite `pedido_creado(id_pedido)`, `sync_manager.force_refresh()`.
- Combos de cliente/producto se llenan con `SELECT id_cliente, nombre FROM Cliente ORDER BY nombre`
  y `SELECT id_producto, nombre FROM Producto ORDER BY nombre` (con filtro por texto en memoria).

### Programar entrega — `VentanaDetallePedido.programar_entrega()`
`UPDATE Pedido SET estado_pedido = 'programado', fecha_entrega = %s WHERE id_pedido = %s`.

### En camino — `marcar_en_camino()`
`UPDATE Pedido SET estado_pedido = 'en camino' WHERE id_pedido = %s`.

### Entrega parcial — `realizar_entrega_parcial()`
1. Por cada producto con cantidad a entregar > 0:
   `UPDATE DetallePedido SET cantidad_entregada = cantidad_entregada + %s WHERE id_pedido = %s AND id_producto = %s`.
2. `SELECT COUNT(*) FROM DetallePedido WHERE id_pedido = %s AND cantidad_entregada < cantidad`.
3. Si el count es 0 (todo entregado):
   `UPDATE Pedido SET estado_pedido = 'entregado', fecha_entrega = %s` (fecha = hoy).
4. Recarga las 3 tablas del detalle, emite `pedido_updated`, `force_refresh`.

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

- Barra de estado con indicador de sync animado.
- Barra de herramientas: Nuevo pedido, Importar DBF, Forzar actualización, Ver historial completo.
- Dos paneles (`crear_panel_pendientes` / `crear_panel_entregados`):
  - Pendientes: `SELECT p.id_pedido, c.nombre, p.fecha_pedido, p.fecha_entrega, p.estado_pedido
    FROM Pedido p JOIN Cliente c ... WHERE estado_pedido IN ('pendiente','programado','en camino')`.
  - Entregados: mismos campos, `estado_pedido = 'entregado' AND fecha_entrega >= CURRENT_DATE - INTERVAL '7 days'`.
- Doble clic en una fila → `VentanaDetallePedido(id_pedido, sync_manager=...)`.
- Se suscribe a las señales de `DatabaseSyncManager` para refrescar automáticamente.

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

- **Credenciales y hostname hardcodeados** en 6 copias de `obtener_conexion()`.
- `config.DB_*` existe y no se usa (el módulo ya importa `config`, solo para `DBF_ENCODING`).
- `precio_unitario` siempre `0.00` → no hay valorización de pedidos.
- `stock_disponible` se crea pero se importa siempre en `0`.
- `estado_entrega` en `DetallePedido` se lee (`cargar_productos_pedido`) pero nunca se escribe.
- Polling cada 8 s con conexión nueva cada vez — costo de red/BD constante mientras la ventana está abierta.
- `except:` desnudos en los `ALTER TABLE` (≈líneas 414, 471).
- `ImportThread` duplica la intención de `controllerBD.py` con **otro esquema** (ver [controllers.md](controllers.md)).
