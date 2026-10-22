# Rendimiento — lectura de archivos DBF

Investigación 2026-09-02 sobre el arranque lento de la app.

> **Estado (2026-09-02): pasos 1 y 2 IMPLEMENTADOS.** Ver
> [`src/controllers/dbf_io.py`](../src/controllers/dbf_io.py) y la sección
> "Implementación" al final. Resultado medido: arranque de **19,2 s → 0,6 s**
> (caché válida) o **4,6 s** (primera vez / DBF cambió), RAM **186 MB → 64 MB**.

## El problema medido

La app hace `pd.DataFrame(iter(DBF(ruta, encoding='latin1')))` para cargar los DBF grandes.
`dbfread` es Python puro: parsea **los 59 campos de cada registro** aunque la app use solo 12,
y devuelve un dict por fila; `pd.DataFrame` después materializa todo de nuevo.

### Archivos DBF y su peso

| Archivo | Tamaño | Registros | Usado por | Momento |
|---|---|---|---|---|
| `fachist.DBF` | **81 MB** | **151.969** | carga inicial (`LoadDataThread`) | **al abrir la app** |
| `ivatemp.DBF` | **71 MB** | ~similar | Informe IIBB | al generar IIBB |
| `abmartic.DBF` | 1,1 MB | 1.399 | Litros, Margen, Thalamus, Precios | al abrir cada ventana |
| `ctaclien.DBF` | 1,4 MB | — | Thalamus, IIBB, Margen | según módulo |
| `stock.DBF` | 121 KB | — | (solo `controllerBD.py`) | — |

**Solo `fachist.DBF` y `ivatemp.DBF` son el problema.** El resto se lee en < 1 s.

### Benchmark de `fachist.DBF` (81 MB, 152k filas, Python 3.9, máquina del dev)

| Método | Tiempo | RAM (DataFrame final) |
|---|---|---|
| **ACTUAL** — `pd.DataFrame(iter(DBF(...)))`, 59 columnas | **19,2 s** | **186 MB** (pico real ~2–3× por los dicts intermedios) |
| `dbfread` iterando sin construir DataFrame | 14,4 s | — |
| **DuckDB** `st_read` → pandas, 12 columnas | **5,1 s** | **58 MB** |
| DuckDB `st_read` → pandas, 59 columnas | 4,3 s | 144 MB |
| DuckDB con `WHERE fecha BETWEEN ... AND TC IN (...)` (pushdown) | 4,1 s | ~0 (solo las filas que matchean) |
| **Convertir DBF → Parquet** (una vez) | 4,3 s | archivo de **3 MB** |
| **Leer ese Parquet** (12 columnas) → pandas | **0,14 s** | 58 MB |

> Para archivos chicos (`abmartic`, `ctaclien`) DuckDB es **más lento** que `dbfread`
> (~0,7 s vs ~0,25 s) por el overhead de cargar la extensión + GDAL. **No migrar esos.**

---

## Opciones, de menor a mayor cambio

### A. Drop-in con DuckDB (recomendado como primer paso)

`duckdb` (con la extensión `spatial`, que trae su propio GDAL y lee `.dbf` directo) reemplaza
la lectura de los 2 DBF grandes. ~4× más rápido, ~3× menos RAM, **el DataFrame downstream es
el mismo**.

```python
# src/controllers/dbf_io.py  (helper nuevo)
import duckdb

def leer_dbf(ruta, columnas=None):
    con = duckdb.connect()
    con.execute("LOAD spatial;")               # INSTALL spatial una vez (o bundلeado en el .exe)
    cols = "*" if not columnas else ", ".join(f'"{c}"' for c in columnas)
    return con.execute(f"SELECT {cols} FROM st_read(?)", [ruta]).df()
```

Uso en `LoadDataThread`:
```python
COLS_VENTAS = ["FECHA","MODELO","U_VENDIDAS","TOTAVEN","TC","NC",
               "CUENTA","NROEST","LETRA","VENDNUMERO","CODMOV","DESC"]
df = leer_dbf(config.DBF_BASE_PATH + "/fachist.DBF", COLS_VENTAS)
```

**Ventaja extra:** DuckDB castea tipos solo — `FECHA` llega como `datetime64` (adiós a los
`pd.to_datetime(df['FECHA'])` repetidos en cada módulo).

**Cuidados al migrar (no es 100% drop-in):**
- `NC` llega como `int32`, no string. Revisar `str(row['NC']).zfill(8)` (Thalamus) y
  `str(row['NC']).split()[0].zfill(12)` (IIBB) — el `.split()` sobre un int no tiene sentido.
- `MODELO` llega como `object` (string) → `str.startswith('L')` sigue andando.
- `INSTALL spatial` baja la extensión de internet la primera vez. Para el `.exe`: pre-descargarla
  y setear `duckdb_extension_directory`, o bundlear.
- Requiere `duckdb` en `requirements.txt` y en los `--hidden-import` de `CompilarEjecutable.py`.

### B. Caché Parquet (recomendado como segundo paso — el que mata el problema)

En el arranque, comparar la **firma** del `fachist.DBF` (`size` + `mtime` + `n_reg`)
contra la guardada en `cache/fachist.parquet.meta`:
- si algo cambió → reconvertir (4-6 s, en el hilo de fondo)
- leer siempre del Parquet (**0,6 s**)

> ⚠️ Comparar solo `mtime` **no alcanza**: si el DBF se actualiza dejando un `mtime`
> igual o anterior al de la caché (copia que preserva timestamps, restore, reescritura
> in-place del sistema de gestión), la caché nunca se regenera y los informes muestran
> datos viejos. Por eso se usa también el tamaño y el nº de registros del header.

Startup de ~19 s → **~0,2 s** cuando el cache está fresco. El Parquet pesa 3 MB.
Mismo patrón para `ivatemp.DBF` (IIBB).

```python
def cargar_ventas(dbf_path, cache_path, columnas):
    import os, duckdb
    if not os.path.exists(cache_path) or os.path.getmtime(dbf_path) > os.path.getmtime(cache_path):
        con = duckdb.connect(); con.execute("LOAD spatial;")
        con.execute(f"COPY (SELECT * FROM st_read('{dbf_path}')) TO '{cache_path}' (FORMAT parquet)")
    return duckdb.connect().execute(
        f'SELECT {", ".join(chr(34)+c+chr(34) for c in columnas)} FROM \'{cache_path}\'').df()
```

### C. No cargar todo en RAM — query con `WHERE` (cambio de arquitectura)

Hoy `df_ventas` (152k × 59) vive en memoria toda la sesión y cada módulo lo filtra.
Con DuckDB/Parquet se puede empujar el filtro a la query: Thalamus pediría ~4.000 filas de un día
en vez de traer 152.000. Elimina el `df_ventas` global.
Es el mayor ahorro de RAM pero toca todos los módulos → proyecto aparte.

### D. Subir de Python 3.9 → 3.11 / 3.12

- **`polars` 1.x no soporta Python 3.9** (lo probamos: no instala). En 3.11 sí, y es 5–10× pandas
  en `groupby`/filtros, con modo lazy y menos RAM.
- El intérprete 3.11 es ~20–30 % más rápido que 3.9 en general.
- Habilita pandas con backend `pyarrow` (strings sin overhead de objetos Python).
- Recomendado independientemente de lo anterior.

---

## Librerías evaluadas

| Librería | Veredicto |
|---|---|
| `dbfread` (actual) | Python puro, sin proyección de columnas, sin pushdown. Bien para archivos chicos. |
| `dbf` (Ethan Furman) | Python puro, similar velocidad. Tiene `.query()` pero no acelera lecturas masivas. |
| `simpledbf` | Wrapper sobre pandas vía CSV troceado. No mejora nada. Desinstalado. |
| **`duckdb` + `spatial`** | **La opción. 4× más rápido, 3× menos RAM, tipos automáticos, SQL con pushdown.** |
| `polars` | Muy rápido pero **no en Python 3.9**. Evaluar tras subir de versión. |
| Parquet como caché | Complementa a DuckDB. Startup 19 s → 0,2 s. |

## Plan

1. ✅ **HECHO** — Helper `leer_dbf()` / `leer_dbf_cacheado()` con DuckDB.
2. ✅ **HECHO** — Caché Parquet con invalidación por firma del DBF (tamaño + mtime + nº de registros).
3. Pendiente — upgrade a Python 3.11+ (paso D).
4. Pendiente — evaluar eliminar el `df_ventas` global (paso C).

---

## Implementación (pasos 1 y 2)

### `src/controllers/dbf_io.py` (archivo nuevo)

| Función | Qué hace |
|---|---|
| `leer_dbf(ruta, columnas=None)` | Lee un DBF a `DataFrame` vía DuckDB (`st_read`). Proyección de columnas. Cae a `dbfread` si DuckDB/`spatial` no está. |
| `leer_dbf_cacheado(ruta_dbf, ruta_cache, columnas=None)` | Igual, pero convierte el DBF a Parquet la primera vez o si cambió, y después lee el Parquet. Guarda un `.parquet.meta` (JSON) con la **firma del DBF** = `{size, mtime, n_reg}` (nº de registros del header, bytes 4-7). Reconvierte si cualquiera difiere. **No basta el `mtime`:** al actualizar el DBF (copia, restore, reescritura del sistema de gestión) puede quedar igual o anterior al de la caché → serviría datos viejos. |
| `COLUMNAS_VENTAS` | Las 12 columnas de `fachist.DBF` (de 59) que usa la app. **Si un módulo necesita otra columna de `fachist`, agregala acá.** |
| `COLUMNAS_IVATEMP` | Las 7 columnas de `ivatemp.DBF` (de 98) que usa IIBB. |

**Capa de compatibilidad (`_emular_dbfread`)** — el `DataFrame` devuelto se normaliza
para comportarse como el de `dbfread` + pandas:
- campos de texto vacíos → `''` (no `NaN`), igual que `dbfread`.
- enteros nullable de DuckDB → `int64`/`float64` (como infiere pandas desde dicts).
- `FECHA` queda como `datetime64` (equivalente; ahorra los `pd.to_datetime` repetidos).

**`config.DBF_ENCODING`** (`cp850`, override por env `DBF_ENCODING`) — fuente única de
verdad del encoding de todos los DBF del proyecto.

**Encoding (corregido 2026-09-02):** los 4 DBF declaran **LDID `0x02` = codepage 850**
(MS-DOS Internacional) en el header. Antes se leían como `latin1`, lo que rompía
`Ñ` → `¥`, `°` → `ø`, `º` → `§` en ~100 descripciones de producto y ~45 nombres de
cliente / ~47 direcciones. Ahora **todo el código lee los DBF con `config.DBF_ENCODING`
(`cp850`)** — tanto `dbf_io` (GDAL `ENCODING=CP850` + fallback `dbfread`) como el resto
de call sites (`main.IIBB`/`verificaCliente`, `others.buscaArtic`, `margenBeneficio`,
`LitrosDBF`, `programarPedido.ImportThread`). Nada en el código hace *join* por texto,
así que el cambio solo mejora lo que se ve/exporta.

**Diferencia menor conocida:** GDAL recorta espacios a **ambos** lados de los campos
CHAR; `dbfread` solo a la derecha. Afecta ~77 filas de `DESC` en `fachist` (espacio a
la izquierda). Sin impacto: todos los consumidores de `DESC` hacen `.strip()`.

### Puntos de uso

| Dónde | Antes | Ahora |
|---|---|---|
| `ProgressBar.LoadDataThread.run()` | `pd.DataFrame(iter(DBF(fachist, encoding='latin1')))` | `dbf_io.leer_dbf_cacheado(fachist, cache, COLUMNAS_VENTAS)` |
| `main.IIBB()` — `ivatemp` | `pd.DataFrame(iter(DBF(ivatemp, encoding='latin1')))` | `dbf_io.leer_dbf(ivatemp, COLUMNAS_IVATEMP)` |

`config.py` — nueva constante `CACHE_PATH` (`{OUTPUT_PATH}/cache_dbf`, local a cada máquina).
`CompilarEjecutable.py` — agregado `duckdb` a `--hidden-import` y `--collect-all`.
`.gitignore` — ignora `cache_dbf/`, `*.parquet`.

### Resultados medidos (máquina del dev, `fachist.DBF` 81 MB / 152k filas)

| Escenario | Tiempo | RAM |
|---|---|---|
| Antes | 19,2 s | 186 MB |
| Primera vez / DBF cambió (DBF→Parquet + leer) | **4,6 s** | 64 MB |
| Arranque normal (Parquet fresco) | **0,6 s** | 64 MB |

### Fallback

Si DuckDB no se puede importar, o la extensión `spatial` no carga (sin internet la
primera vez en una máquina nueva), **ambas funciones caen automáticamente a
`dbfread`** — la app sigue funcionando, solo que sin la aceleración. Para el `.exe`
conviene pre-bundlear la extensión `spatial`.

### Cómo verificar tras tocar `dbf_io.py` o los filtros de ventas

Hay dos scripts de prueba (en el scratchpad de la sesión, no versionados). Reproducen:
comparación columna por columna contra `dbfread`, los filtros reales de cada módulo
(Thalamus / Sell In / Litros / Margen / IIBB) y el flujo de `LoadDataThread`. Si
cambiás algo acá, volvé a correrlos.
