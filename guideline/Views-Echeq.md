# Views / Echeq — `src/Views/Echeq/`

Módulo **E-Cheques**: consolida los Excel de cheques electrónicos exportados del banco,
permite filtrar, agregar registros a mano y guardar un archivo maestro.

| Archivo | Clase | Rol |
|---|---|---|
| `EcheqDBF.py` | `EcheqWindow(QWidget)` | Widget embebible con filtros y tabla; acciones en `self.acciones_toolbar` |
| `EcheqFormDBF.py` | `Form(QDialog)` | Formulario de alta manual (un `QLineEdit` por columna) — **queda modal** |
| `src/controllers/echeq_io.py` | — | Carga **cacheada por archivo** de los Excel (ver abajo) |
| `src/ui/paginas/echeques.py` | `PaginaEcheques(PaginaBase)` | Sección del `AppWindow`; carga lazy en `on_activar` |

> A pesar del sufijo `DBF`, este módulo **no toca ningún DBF**. Trabaja solo con Excel.
> **F2c:** `EcheqWindow` pasó de `QMainWindow` a `QWidget`. Toolbar → `acciones_toolbar`.
> **`style/echeques-tailwind-look`:** reescritura de la ventana con la estética del
> prototipo (`prototypeExample/prototypeEcheq.html`) + caché de carga + fix de datos.

---

## Cómo se dispara

- **UI integrada:** `PaginaEcheques.on_activar()` llama `EcheqWindow.cargar_datos_iniciales()`
  la primera vez. Corre en background (`EcheqLoadThread`), deshabilita las acciones de barra
  mientras carga y las rehabilita al terminar (`_on_datos_cargados`).
- **Legacy (`main_legacy.py`):** `manejadorEcheq()` lanza `EcheqLoadThread` y hace
  `EcheqWindow(df=df)`.

Ambos caminos pasan hoy por `echeq_io.cargar_echeqs_cacheado()`.

---

## Carga cacheada — `src/controllers/echeq_io.py`

`config.ECHEQ_PATH` acumula **cientos** de Excel (un lote de "novedades de cobros" por
export del banco). Cada cheque reaparece en muchos lotes a medida que cambia su `Estado`
(~400 archivos → ~20.000 filas crudas → ~1.500 cheques únicos). Releer todo con
`pd.read_excel` en cada apertura tardaba **~13 s**; además la versión vieja recalculaba el
set de duplicados desde cero por archivo (O(archivos²)).

`cargar_echeqs_cacheado(direc, ruta_cache)`:

1. Carga el estado previo: `ruta_cache` (pickle con el DataFrame combinado) +
   `ruta_cache + ".meta"` (JSON con la **firma** `{size, mtime}` de cada archivo ya
   procesado). Si **cualquiera** de los dos falla al leer → se descarta todo el caché
   (mejor releer de más que servir datos incompletos).
2. Recorre los archivos de `direc` ordenados por nombre; **saltea** los que tienen la
   misma firma en el manifest. Solo lee del disco los nuevos o modificados.
3. Si hubo cambios: `concat(cache + frames nuevos)` → `_deduplicar` →
   `drop_duplicates("Nro de Cheque", keep="last")` (los nombres llevan fecha, así que
   el último archivo tiene el estado más reciente) → reescribe pickle + meta.
4. Si no hubo cambios, devuelve el caché tal cual.

Timing real: **frío ~8 s / caliente ~0,07 s** (~400 archivos, 1.531 cheques).

> **Por qué pickle y no Parquet:** en este entorno no hay `pyarrow`/`fastparquet`, así que
> `pd.to_parquet` falla. `dbf_io.py` sí usa Parquet porque lo escribe DuckDB, no pandas.
> Pickle viene con pandas, preserva dtypes y no suma dependencias.

### `_leer_archivo(ruta, nombre)`

- Archivos cuyo nombre **empieza con `E`** (`Echeqs_sistema.xlsx`, export del propio
  sistema) → `read_excel(ruta)` (header fila 0). El resto (exports del banco) →
  `read_excel(ruta, header=1)`.
- Normaliza nombres de columna (`str.strip`), corrige el swap Pagador (abajo), y proyecta
  a las columnas de `echeq_io.COLUMNAS` que existan.

### `_corregir_pagador_swapeado(df)` — fix del swap Pagador Cuit / Nombre

Algunos exports traen el **nombre en la columna `Pagador Cuit`** y el **CUIT en
`Pagador Nombre Apellido/Razón Social`**. La corrección es **POR FILA**: para cada fila
cuyo `Pagador Cuit` contenga letras (`_tiene_letras`, que devuelve `False` en NaN), se
intercambian los dos valores de esa fila.

> **Por qué por fila y no por columna** (bug corregido en `style/echeques-tailwind-look`):
> la versión vieja hacía `if df["Pagador Cuit"].apply(tiene_letras).any(): rename(...)` —
> swap de columna entera. `Echeqs_sistema.xlsx` es un archivo **mixto** (461 filas
> swapeadas + 1.070 correctas); el `.any()` daba `True` y el rename rompía las 1.070 que
> estaban bien → 1.070/1.531 cheques mostraban el CUIT donde va el nombre. El swap por
> fila deja intactas las correctas. Es **auto-sanante**: al hacer "Guardar", `self.df` ya
> está corregido, así que el próximo `Echeqs_sistema.xlsx` sale limpio.

---

## `EcheqWindow` (`EcheqDBF.py`)

- `self.campos` — 6 campos filtrables/visibles:
  `["Nro de Cheque", "Echeq id", "Pagador Nombre Apellido/Razón Social", "Monto",
  "Fecha de Pago", "Fecha de Emisión"]`.
- `self.campos_tabla = self.campos + ["Estado"]` — 7 columnas de datos + `#` = 8.
- `self.df` arranca con las **45 columnas completas** de `echeq_io.COLUMNAS` (aunque
  la tabla solo muestre 7); "Guardar" exporta todas.
- `self.direc = config.ECHEQ_PATH` (ya **no** hardcodeado).

### Estructura visual (prototipo Tailwind)

- Acciones de barra (`self.acciones_toolbar`, íconos `qtawesome`):
  Nuevo (`fa5s.plus`, azul), Guardar (`fa5s.save`), Actualizar (`fa5s.sync-alt`),
  Limpiar Filtros (`fa5s.eraser`, rojo).
- Tarjeta **"Filtros de Búsqueda"** (`ui/widgets/tarjeta.crear_tarjeta`): grid de 2
  columnas, labels a la derecha, un `QLineEdit` por campo (filtra al tipear).
- Tarjeta **"Registros de E-Cheques"**: badge azul con el conteo (`1.531 registros`) +
  "Orden: Fecha de Pago DESC", tabla, y footer con **Total Mostrado / Promedio por
  Cheque / Suma Seleccionada** (pill azul, suma de las filas seleccionadas).
- Badges de `Estado` con color por valor (`_ESTADO_COLORES`): Activo (verde),
  Emitido Pendiente (ámbar), Cesión pendiente (azul), Rechazado (rojo).

### `mostrar_en_tabla(df)`

- Ordena por `Fecha de Pago` descendente (`_fecha_para_orden`, `errors="coerce"`).
- Formatea `Monto` a formato argentino (`_fmt_monto`: `$ 1.234.567,89`), fuente mono,
  alineado a la derecha, negrita.
- Fechas y `Nro de Cheque`/`Echeq id` en fuente mono.
- Al final llama `_actualizar_resumen(df_mostrar)` (total + promedio).

### `_actualizar_resumen(df_mostrar=None)`

- Con `df_mostrar` → recalcula Total Mostrado + Promedio.
- Sin argumento (lo llama `itemSelectionChanged`) → solo `_actualizar_suma_seleccionada()`
  (suma `_parse_monto` de la celda Monto de cada fila seleccionada).

### `aplicar_filtros()`

Un `QLineEdit` por campo visible; cada filtro con texto aplica
`df[col].astype(str).str.contains(texto, case=False, na=False)`. Sin filtros → todo.

### `guardar_archivo()`

`self.df.to_excel(config.ECHEQ_PATH/Echeqs_sistema.xlsx, index=False)` — sin diálogo,
guarda las 45 columnas. Ese archivo se vuelve a ingerir en la próxima carga (así
sobreviven las altas manuales).

### `openForm()`

`Form(self.df.columns)` → `QLineEdit` por columna → nueva fila → `pd.concat` →
`modified=True`. `hay_cambios_sin_guardar()` expone `self.modified` para que el
`AppWindow` pregunte al cerrar (F3).

---

## Archivos que toca

| Archivo | Modo |
|---|---|
| `config.ECHEQ_PATH/*.xls*` | lee (vía `echeq_io`, cacheado) |
| `config.CACHE_PATH/echeqs.pkl` + `.pkl.meta` | lee/escribe (caché) |
| `config.ECHEQ_PATH/Echeqs_sistema.xlsx` | **escribe** (Guardar) y lee (carga) |

---

## Tests

`tests/verificar_echeq_io.py` — correr desde la raíz con acceso a los Excel reales.
Cubre: carga fría/caliente, dedup, fix del swap por fila (incl. caso unitario de archivo
mixto), incorporación de archivo nuevo sin releer los viejos, reconstrucción total si
falta el `.pkl`.

---

## Bugs / deuda conocida

- Guardado sin `QFileDialog` — siempre `Echeqs_sistema.xlsx`.
- El botón "Actualizar" recarga desde disco (ahora vía caché) — no hace merge explícito
  con altas manuales no guardadas (pero `Echeqs_sistema.xlsx` las persiste si se guardó).
- `openForm` arma la fila con `columns=self.campos` (6) pero `Form` recibe las 45.
- El prompt "¿guardar antes de salir?" quedó pendiente para F3 (`hay_cambios_sin_guardar`).
