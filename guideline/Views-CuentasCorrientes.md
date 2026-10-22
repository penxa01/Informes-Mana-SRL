# Views / CuentasCorrientes — `src/Views/CuentasCorrientes/`

Sección **Cuentas Corrientes**: deuda pendiente por cliente, detalle de facturas y
**seguimiento de reclamos** con aviso por WhatsApp al vendedor. Reemplaza al script suelto
`FiltradoDeudasCtaCtes.py`.

| Archivo | Rol |
|---|---|
| `src/controllers/cuentas_corrientes_io.py` | Lógica **pura** (sin Qt): deudores, detalle, filtros, KPIs, saldos a favor |
| `src/Views/CuentasCorrientes/CuentasCorrientesWindow.py` | Panel: KPIs, filtros plegables, grilla, botón Reclamos |
| `src/Views/CuentasCorrientes/DetalleCuenta.py` | Diálogo con las facturas pendientes de un cliente (doble clic) |
| `src/Views/CuentasCorrientes/Reclamos.py` | Modal: alta de reclamo + tabla de reclamos activos |
| `src/controllers/reclamos_db.py` | Tablas de reclamos en PostgreSQL (sin `commit` propio: lo hace quien llama) |
| `src/controllers/whatsapp.py` | Mensaje al vendedor y enlace `wa.me` |
| `src/controllers/vendedores.py` | Código → nombre de vendedor (**duplicada** en 4 lugares del repo) |
| `src/ui/paginas/cuentas_corrientes.py` | `PaginaCuentasCorrientes` (carga lazy en `on_activar`) |

Tests: `tests/verificar_cuentas_corrientes.py`, `verificar_reclamos.py`, `verificar_whatsapp.py`.

---

## Fuentes de datos

`ctacorr.dbf` (movimientos) y `ctaclien.dbf` (clientes), por `dbf_io.leer_dbf_cacheado` (Parquet
en `CACHE_PATH`). Carga en un hilo (`_CargaThread`) la primera vez que se abre la sección.

## Reglas de negocio (importan: el script original las tenía mal)

- **Saldo = `SALDO` nativo** de las facturas `FA/FC/FE` con saldo > 0,01. **No** se recalcula
  `Total − Recibos − NC`: el script original ignoraba los comprobantes `CR` aplicados a una
  factura y daba por impagas facturas ya canceladas (ej. FE A-3-94 de la cuenta 482).
- **No se suma el `SALDO` de recibos / NC / CR**: tienen un saldo propio que duplicaría la deuda.
- `fecha_desde` filtra por **fecha de emisión** (inclusive). Es un campo del panel (default 01/01/2024).
- **Mora**: se mide desde la **emisión** de la factura (los datos no traen plazo de pago).
  `> 30` días = Mora, `> 60` = Mora crítica (`DIAS_MORA`, `DIAS_CRITICA`). Por **factura**, no por cliente.
- El detalle de un cliente suma **exactamente** lo que muestra la grilla (comparten `_facturas_con_saldo`).
- Una fila por comprobante, **sin agrupar**: en `ctacorr` hay facturas duplicadas por error del
  sistema de gestión (FC A-3-8808, cuenta 1727) y el mismo número en dos cuentas
  (FC A-3-9127). La clave de una factura es `(cuenta, clase, nro_est, nc)`.

### Saldo total = neto

`KPI saldo total = suma de la tabla (saldo_bruto) + saldos a favor (a_favor)`.

- **Saldo contable** de una cuenta = suma de `TOTALL` de `TC_CONTABLES` (FA CH FC ND FE BE SI RC NC CR CC),
  de toda la historia (no depende de `fecha_desde`).
- Las cuentas con saldo contable **negativo** (crédito a favor del cliente) que **no** están en la tabla
  bajan el total pero **no se listan**. Las que sí están (tienen una factura pendiente) no se descuentan
  de nuevo.
- Los % de mora/crítica van contra el **bruto**; el pie "Saldo mostrado" suma solo lo listado.
- ⚠️ Medido el 16/10/2026: el efecto es de ~−0,04 % (−$440 mil en 69 cuentas). Contra el saldo contable
  neto de todas las cuentas (~$1.128,6 M) el KPI sigue ~$19 M arriba: lo explican en parte los
  recibos/NC **sin factura asociada** (~−$9,8 M) y las ND/CH/BE (la tabla solo cuenta facturas).
  Si hace falta que coincida con el sistema de gestión, el KPI debería ser el saldo contable neto.

---

## Panel (`CuentasCorrientesWindow`)

- 3 KPIs: saldo total (neto), en mora (> 30 d), mora crítica (> 60 d).
- **Filtros plegables** (`crear_tarjeta_colapsable`): arrancan plegados; el encabezado resume lo
  aplicado (`Desde 01/01/2024 · filtros: cliente, saldo mínimo`) y los resultados. Campos: cliente/cuenta,
  saldo mínimo (`1.500.000,50`), antigüedad, **facturas desde**. Cambiar la fecha recalcula sin releer DBF.
- Grilla: `#`, Cliente, Saldo, Factura más vieja con saldo, Antigüedad, Estado. Doble clic o
  "Ver detalle" → `DetalleCuentaDialog`.
- Botón naranja **Reclamos** → modal.

---

## Reclamos

### Base de datos (PostgreSQL de Pedidos, tablas nuevas)

| Tabla | Contenido |
|---|---|
| `reclamo` | cuenta, cliente, teléfono, vendedor (código y nombre), `estado`, `creado_por`, fechas. **Snapshot**: no cambia si después se edita el cliente |
| `reclamo_factura` | facturas del reclamo con total y saldo **al momento de reclamar** |
| `contacto_whatsapp` | nombre, teléfono, `codigo_vendedor` (= `ctaclien.VENDEDOR` = `usuario.vendedor_id`), `es_remitente` (uno solo: Martin) |

`reclamos_db.asegurar_esquema(con)` es **idempotente** y se ejecuta al abrir el modal: crea las tablas,
**migra** el `CHECK` del estado si la tabla es anterior a `NO CONTACTADO` (sin tocar reclamos
existentes) y carga los contactos con `ON CONFLICT DO NOTHING` (un número editado en la base no se pisa).

La conexión es `programarPedido._conexion()` (host por `config.DB_HOST`, ver [controllers.md](controllers.md)).
Los tests de base corren **dentro de una transacción que se revierte** (Postgres tiene DDL transaccional).

### Estados

`NO CONTACTADO` (inicial) → `SIN RESPUESTA` → `CONTACTADO` → `PENDIENTE DE O/P` → `RESUELTO`.
Los resueltos se ocultan salvo "Mostrar resueltos", y sus facturas vuelven a poder reclamarse.
**Una factura no puede estar en dos reclamos activos.**

### Alta

- Cliente: **todos** los de CTACLIEN (~2.100), etiqueta `NOMBRE (cuenta)` porque hay nombres repetidos.
- Vendedor: se asigna solo según `ctaclien.VENDEDOR`; si el código no figura en la lista
  (la cuenta 818 tiene el 7) hay que elegirlo a mano.
- Teléfono: de `ctaclien.TELEFONO` (texto libre); si falta se ingresa a mano. Es obligatorio.
- Facturas: las pendientes del cliente desde la fecha del panel; las ya reclamadas salen bloqueadas.

### Aviso por WhatsApp

Botón verde por reclamo → abre `https://wa.me/549<número del vendedor>?text=<mensaje>`. El mensaje
lleva cliente, cuenta y teléfono, las facturas (comprobante, fecha, importe), el rango de fechas, el
total y el recordatorio de avisar por ese medio al contactar al cliente (máx. 25 facturas listadas; el
total incluye todas).

- **No es un envío automático**: sale desde la cuenta de WhatsApp abierta en la PC (la de Martin) y quien
  usa la app toca *Enviar*. La app **no puede saber** si el mensaje salió.
- Si el vendedor no tiene número en `contacto_whatsapp` avisa y no abre nada.
- Diego Calderón (vendedor 5) comparte línea con Maxi (mismo número, confirmado).

### Alertas: reclamos sin novedades

Un reclamo **activo** (no RESUELTO) que lleva **7 días o más sin actualizar su estado** genera una alerta
(`reclamos_db.sin_novedades`; umbral configurable con `RECLAMOS_ALERTA_DIAS` en el `.env`, 1–365). Los días se
cuentan desde la **última actualización** (`fecha_actualizacion`: la creación cuenta como una; cambiar el estado la
reinicia) y los calcula la base (`now()`), no el reloj de cada PC.

- **Barra de estado**: botón naranja `N reclamos sin novedades` (oculto si no hay ninguno; el tooltip lista los más
  viejos). Clic → abre Cuentas Corrientes y el modal de reclamos (espera a que terminen de cargar los datos).
- **Aviso emergente** (el mismo toast de Pedidos), **solo de los reclamos que todavía no se avisaron** en la sesión:
  no se repite cada 30 minutos. Si un reclamo sale de la alerta y vuelve a vencer, se avisa de nuevo.
- **Modal**: columna `Sin novedades` (`hoy`, `hace 9 días`); con alerta la celda se resalta en ámbar.
- **✓ Revisado** (en esa celda): reinicia el plazo **sin cambiar el estado** (`renovar_reclamo`). Sin esto, un reclamo
  que seguirá en `SIN RESPUESTA` alarmaría para siempre. No se puede revisar uno resuelto.
- **Quién chequea**: `src/ui/alertas_reclamos.py` (`MonitorReclamos`): a los 8 s de arrancar y luego cada 30 min, en un
  hilo con una conexión corta. Un fallo (base caída, tabla todavía inexistente) se ignora en silencio: queda el último
  resultado bueno. Crear / cambiar de estado / revisar un reclamo dispara un chequeo inmediato por
  `src/ui/eventos.py` (`bus.reclamos_modificados`).

---

## Actualización de la base de ventas

Aplica a toda sección que usa `df_ventas` (Litros, Margen, Otros). Lógica en `src/controllers/ventas_io.py`.

- `QTimer` en `AppWindow` cada **15 min** (`VENTAS_ACTUALIZAR_MIN`, 1–240) y botón / **F5**.
- Solo relee `fachist.DBF` si cambió su **firma** (tamaño + fecha + nº de registros). Sin cambios no se
  rehace ningún informe. Verificación y lectura en `LoadDataThread(firma_previa)`, fuera del hilo de UI.
- Red caída: se conservan los datos anteriores (el automático avisa en la barra de estado, el manual con un cartel).
- Litros, si ya generó un informe, lo rehace con **los mismos filtros con que se generó** (no los de los
  combos actuales), y si el usuario está en otra sección espera a `on_activar`.
- Litros y Margen traen un botón cuadrado junto a *Generar* (`tiene_boton_actualizar = True`: el AppWindow
  no les agrega la franja de comandos); Otros usa la franja. La barra de estado muestra la última verificación.
- El panel de gráficos de Litros se oculta desde la cabecera de la tabla; la preferencia se recuerda.
