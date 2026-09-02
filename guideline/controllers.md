# Controllers — `src/controllers/`

Infraestructura compartida: configuración de entorno, hilos de trabajo, helpers de
exportación a Excel y los diálogos de selección de fecha/período.

| Archivo | Rol |
|---|---|
| `config.py` | Autodetección de entorno + todas las rutas y credenciales |
| `dbf_io.py` | Lectura eficiente de DBF (DuckDB + caché Parquet) — ver [rendimiento-dbf.md](rendimiento-dbf.md) |
| `ProgressBar.py` | Hilos (`QThread`) para operaciones bloqueantes + diálogo de progreso |
| `others.py` | Generación/formato de archivos Excel + `buscaArtic` |
| `controllerBD.py` | Script CLI standalone de importación DBF → PostgreSQL (**no lo usa la app**) |
| `FechaDBF.py` | Diálogo `Fecha` (día único) |
| `RangeFechas.py` | Diálogo `DateRangeDialog` (rango libre + vendedor) |
| `rangeMY.py` | Diálogo `DateYearRangeDialog` (combos MM/YYYY + manual + vendedor) |
| `MesAno.py` | Diálogo `MesAnioDialog` (mes + año + jurisdicción) |

---

## `config.py`

Módulo de configuración. Se importa como `from src.controllers import config`.

### Localización del `.env`
- App compilada (`sys.frozen`): `.env` junto al `.exe`.
- Desarrollo: `.env` en la raíz del proyecto (`parents[2]` desde `config.py`).
- Se carga con `python-dotenv` (`load_dotenv`).

### Autodetección de entorno
Prioridad:
1. **Local** — si existe `BASE_PATH_LOCAL` (default `d:/tiempo`) → `_BASE = d:/tiempo`, `DB_HOST = DB_HOST_LOCAL` (default `localhost`).
2. **Remoto** — si existe `BASE_PATH_REMOTE` (default `Z:`) → `_BASE = Z:`, `DB_HOST = DB_HOST_REMOTE` (default `DESKTOP-R8E4V7S`).
3. **Fallback** — usa local sin garantía de recursos.

### Rutas derivadas (`_b = Path(_BASE)`)

| Constante | Valor | Usado por |
|---|---|---|
| `DBF_BASE_PATH` | `{_b}/vtiempoges/GESTION/MANA2014` | casi todos |
| `DBF_HOREB_PATH` | `{_b}/vtiempoges/GESTION/HOREB25` | Actualizar Precios |
| `EXCEL_THALAMUS_PATH` | `{_b}/Thalamus` | Thalamus |
| `EXCEL_PRECIOS_PATH` | `{_b}/Lista de precios` | Thalamus, Margen, Precios |
| `EXCEL_LITROS_PATH` | `{_b}/Thalamus/LITROS SHELL.xlsx` | Litros, Ventas Mensuales |
| `ECHEQ_PATH` | `{_b}/E-cheqs` | E-Cheques (vía `EcheqLoadThread`) |
| `OUTPUT_PATH` | env `OUTPUT_PATH` (default `C:/tempdgr`) — **local, no depende del base remoto** | IIBB |
| `CACHE_PATH` | env `CACHE_PATH` (default `{OUTPUT_PATH}/cache_dbf`) — **local** | caché Parquet de `dbf_io` |

### Credenciales BD
`DB_NAME` (`pedidosMana`), `DB_USER` (`postgres`), `DB_PASSWORD` (env, default `""`).
`DB_HOST` se resuelve arriba.

### `DBF_ENCODING`
`config.DBF_ENCODING` (`cp850`, override por env `DBF_ENCODING`) — encoding de **todos**
los `.DBF`. El header declara LDID `0x02` = codepage 850. **Fuente única de verdad:**
si tocás la lectura de un DBF, usá `config.DBF_ENCODING`, no un literal.

> ⚠️ **`config.DB_*` está definido pero casi nadie lo usa.** `programarPedido.py` y
> `controllerBD.py` hardcodean host/usuario/password en cada `obtener_conexion()`.
> Al migrar Pedidos, esta es la fuente de verdad a la que hay que apuntar.

---

## `ProgressBar.py`

### `InfoProgressBarWindow(QDialog)`
Diálogo simple con `QLabel` + `QProgressBar`. Métodos `actualizar_progreso(valor)` y
`actualizar_mensaje(msg)`. Lo usa `EcheqWindow.cargar_datos_iniciales`.

### `LoadDataThread(QThread)` — carga inicial de ventas
- Señal: `data_loaded(pd.DataFrame)`.
- `run()`: lee `{DBF_BASE_PATH}/fachist.DBF` vía `dbf_io.leer_dbf_cacheado(...)` con
  caché Parquet en `{CACHE_PATH}/fachist.parquet` y proyección a `dbf_io.COLUMNAS_VENTAS`
  (12 de 59 columnas) → `DataFrame` → emite.
- Lo lanza `MainWindow.load_data()` al arrancar. Arranque: ~0,6 s con caché fresca
  (antes ~19 s). Ver [rendimiento-dbf.md](rendimiento-dbf.md).

### `ActualizarPreciosThread(QThread)` — módulo Actualizar Precios
- Constructor: `ruta_mana`, `ruta_horeb`, `excel_precios_path`, `excel_valvoline_path`.
- Señales: `progress_actualizado(str)`, `finalizado(bool, str)`.
- `run()`:
  1. Lee ambos Excel de precios.
  2. `_actualizar_precios_dbf(ruta_mana, ...)` — arma dict `updates` (Mana + Valvoline) y hace
     **una sola pasada** por el DBF en `READ_WRITE` (O(n+m)). Fórmulas de precio: ver
     [MainWindow.md](MainWindow.md) → Actualizar Precios.
  3. `shutil.copy2(ruta_mana, ruta_horeb)` — replica el DBF a HOREB.
  4. Emite `finalizado(True/False, mensaje)`.
- **Archivos:** lee `Lista de precios Mana.xlsm` + `Lista Valvoline.xlsx`; lee/escribe
  `{DBF_BASE_PATH}/abmartic.DBF`; sobrescribe `{DBF_HOREB_PATH}/abmartic.DBF`.

### `EcheqLoadThread(QThread)` — módulo E-Cheques
- Señal: `completado(pd.DataFrame)`.
- `run()`:
  1. Directorio = `config.ECHEQ_PATH`. Si no existe → emite DataFrame vacío con `COLUMNAS`.
  2. Por cada archivo del directorio:
     - Si el nombre **empieza con `E`** → `pd.read_excel(path)`.
     - Si no → `pd.read_excel(path, header=1)` (salta fila de título).
     - Normaliza nombres de columna (`.str.strip()`), se queda con las columnas de `COLUMNAS` (44 nombres).
  3. `pd.concat` de todos los frames.
  4. Si hay columna `Nro de Cheque` → `drop_duplicates(subset=['Nro de Cheque'], keep='last')`.
  5. Emite el DataFrame.
- `COLUMNAS` — lista fija de 44 nombres del export estándar de e-cheques (incluye `Unnamed: 1`,
  `Unnamed: 37` del formato original).

---

## `others.py`

Helpers de exportación a Excel con `openpyxl`. Cada función muestra su propio `QMessageBox`
de éxito/`PermissionError`.

### `generar_archivo_excel(df, ruta_salida)` — Ventas Mensuales
- Crea libro nuevo. Título `DISTRIBUIDOR` merge `A1:D1` (bold 14, centrado).
- Encabezados `["Dia / Periodo", "SKU", "Familia", "Litros"]` — fuente roja `ED1C24`,
  relleno amarillo `FFD500`.
- Vuelca el `df` (formatea col 0 a `%Y/%m/%d` si es fecha/string).
- Anchos `[20, 25, 15, 10]`. Borra 2 filas dummy (`ws.delete_rows(3)` ×2).
- Guarda en `ruta_salida`.

### `format_CLIENTE(df, ruta_salida, cant)` — Thalamus
- Quita columnas `Unnamed:*`.
- `df.to_excel(ruta_salida)` y luego reabre con `openpyxl` para fijar anchos de columna
  `A`–`Q` (dict `anchos_columnas` con valores tipo `54.14`, `13.0`, ...).
- Mensaje: "Se agregaron {cant} clientes".

### `buscaArtic(df)` — Thalamus
- **Lee `{DBF_BASE_PATH}/ABMARTIC.DBF`** (`load=True`, `config.DBF_ENCODING` = `cp850`) → DataFrame.
- Filtra `CODART ∈ df['MODELO']`.
- Devuelve el DataFrame filtrado (se usa para resolver `ARTIPROV` y precios).

---

## `controllerBD.py` — script standalone (⚠️ no lo usa la app)

CLI que corre con `python -m src.controllers.controllerBD` y pregunta `c`/`p`.

- `obtener_conexion()` — **`password="011201"` hardcodeado**, host `localhost`, db `pedidosMana`.
- `importar_clientes_desde_dbf()` — lee `d:/tiempo/vtiempoges/GESTION/MANA2014/ctaclien.dbf`
  (ruta hardcodeada), `INSERT INTO cliente (id_cliente, nombre, direccion, telefono)`.
- `importar_productos_desde_dbf()` — lee `abmartic.dbf`, para cada producto llama
  `busca_stock(id)` (que reabre `stock.dbf` entero — O(n·m)), `INSERT INTO producto`.
- `busca_stock(id_producto)` — recorre `stock.dbf` buscando `ARTICULO == id`.

> **Divergencia importante:** este script usa tablas `cliente` / `producto` en minúscula y
> columnas distintas a las de `programarPedido.py` (`Cliente` / `Producto` con `ON CONFLICT`).
> Es una versión vieja del importador. **La versión viva es `ImportThread` en
> [Views-Pedidos.md](Views-Pedidos.md).** No tomarlo como referencia del esquema real.

---

## Diálogos de fecha / período

### `Fecha` (`FechaDBF.py`) — día único → Thalamus
- Un `QLineEdit`. Acepta `dd`, `dd/mm` o `dd/mm/yyyy`; completa mes/año con hoy.
- Valida con `datetime.strptime(fecha, "%d/%m/%Y")`. Deja `input_fecha.text()` **normalizado**
  a `dd/mm/yyyy` (el caller lo relee).
- No expone atributos procesados: el caller hace `dialogo.input_fecha.text()`.

### `DateRangeDialog` (`RangeFechas.py`) — rango libre + vendedor → Margen Beneficio
- Dos `QLineEdit` (`dd/mm` o `dd/mm/yyyy`) + combo vendedor.
- `enable_seller=True` por defecto.
- `completar_fecha(str)`: 2 partes → asume **año actual**; 3 partes → año explícito.
- Valida `desde <= hasta`.
- **Expone tras `Accepted`:**
  - `fecha_desde_procesada`, `fecha_hasta_procesada` → `pd.Timestamp`
  - `vendedor_procesado` → `int` (nº de vendedor) o `None` si eligió "TODOS"
- `vendedor_mapping` = `{1: ROMULO SANCHEZ, 3: MIGUEL ORTUÑO, 4: JOSE BANCO, 5: DIEGO CALDERON,
  6: MATIAS BARATA, 9: MARTIN MOYA}`.

### `DateYearRangeDialog` (`rangeMY.py`) — combos MM/YYYY + manual + vendedor → Litros / Sell In
- Combo "Desde" y "Hasta" con meses `MM/YYYY` desde **hace 2 años** hasta hoy (orden inverso),
  más una opción `MANUAL` que muestra un `QLineEdit` `dd/mm`.
- Combo vendedor (igual mapping que arriba). `enable_seller=False` en Sell In.
- **Expone tras `Accepted`:**
  - `fecha_desde_procesada`, `fecha_hasta_procesada` → `datetime.date`
    (si es del combo, es el **día 1** del mes; si es manual, el día exacto vía `completar_fecha`)
  - `fecha_desde_manual_seleccionada`, `fecha_hasta_manual_seleccionada` → `bool`
  - `vendedor_procesado` → `int` o `None`
- **El caller (`main.py`) convierte:**
  - manual → `datetime(año, mes, día, 0/23:59:59)`
  - combo → `datetime(año, mes, 1)` (desde) / `datetime(año, mes, último_día, 23:59:59)` (hasta,
    con `calendar.monthrange`)

### `MesAnioDialog` (`MesAno.py`) — mes + año + jurisdicción → IIBB
- Combo mes (`Enero`..`Diciembre` → 1..12), `QLineEdit` año (valida `.isdigit()`),
  combo jurisdicción (`San Juan`→1, `Mendoza`→3).
- **Expone tras `Accepted`:**
  - `mes_seleccionado` → `int`
  - `anio_seleccionado` → `int`
  - `jurisdiccion_seleccionada` → `int` (1 o 3)
  - `jurisdiccion_nombre` → `str`
- ⚠️ IIBB **no consume** `jurisdiccion_*` todavía (usa `NROEST` hardcodeado).

### Duplicación
`vendedor_mapping` está definido idéntico en `RangeFechas.py` y `rangeMY.py`, y una tercera
copia (`cod_vendedor`, con "ORTUnO" en vez de "ORTUÑO") en `main.verificaCliente`.
`completar_fecha` está duplicado tal cual entre los dos diálogos de rango.
