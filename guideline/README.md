# Guideline — Lógica de negocio por módulo

Documentación de referencia para modificar la app **sin romper la lógica del sistema**.
Cada archivo describe: qué hace el módulo, cómo se dispara, el paso a paso de negocio,
y **todos los archivos/recursos externos que toca** (DBF, Excel, PostgreSQL, `.env`).

> Convertí fechas relativas a absolutas al leer esto: última actualización **2026-09-02**.

## Índice

| Archivo | Cubre |
|---|---|
| [MainWindow.md](MainWindow.md) | Punto de entrada, carga inicial de ventas, y los módulos que viven en `main.py`: **Thalamus**, **Ventas Mensuales**, **Informe IIBB**, **Actualizar Precios** |
| [controllers.md](controllers.md) | `src/controllers/`: `config.py`, `ProgressBar.py` (hilos), `others.py` (export Excel), `controllerBD.py`, y los 4 diálogos de fecha/período |
| [Views-Litros.md](Views-Litros.md) | `src/Views/Litros/`: **Informe Litros** y **Sell In** (`ReportLts`) |
| [Views-Beneficio.md](Views-Beneficio.md) | `src/Views/Beneficio/`: **Margen Beneficio** (`margenBeneficio` + `DetalleDialog`) |
| [Views-Echeq.md](Views-Echeq.md) | `src/Views/Echeq/`: **E-Cheques** (`EcheqWindow` + `Form`) |
| [Views-Pedidos.md](Views-Pedidos.md) | `src/Views/Pedidos/`: **Pedidos** (PostgreSQL `pedidosMana`) |
| [Views-CuentasCorrientes.md](Views-CuentasCorrientes.md) | `src/Views/CuentasCorrientes/`: **Cuentas Corrientes** (deuda por cliente, saldo neto), **reclamos** con aviso por WhatsApp y **actualización de la base de ventas** (F5 / cada 15 min) |
| [Views-Visitas.md](Views-Visitas.md) | `src/Views/Visitas/`: **Visitas** de los vendedores, leídas en vivo de la hoja `Respuestas de formulario 1` de Google Sheets (sin descargas ni copias) |
| [UI-ventanas-pantalla.md](UI-ventanas-pantalla.md) | `src/ui/ventanas.py`: toda ventana emergente se achica / centra / recibe scroll para entrar en el monitor donde está el sistema (un filtro central, sin tocar cada diálogo) |
| [Build-32bits.md](Build-32bits.md) | Por qué el `.exe` de 64 bits no corre en Windows de 32 bits, cómo decidir si hace falta y cómo compilar la versión de 32 bits (`requirements-win32.txt`, sin DuckDB) |
| [rendimiento-dbf.md](rendimiento-dbf.md) | Arranque lento: benchmarks de lectura DBF, el helper `dbf_io.py` (DuckDB + caché Parquet) y cómo verificarlo con `tests/verificar_*.py` |
| [propuesta-ui-integrada.md](propuesta-ui-integrada.md) | **PLANTEO** (no implementado): pasar de 9 ventanas separadas a una ventana única con navbar de 5 secciones |

---

## Arquitectura de datos (global)

### Fuente principal: `fachist.DBF` (historial de ventas)

Se carga **una sola vez al arrancar** en un hilo (`LoadDataThread`) a un `DataFrame`
llamado `self.df_ventas` dentro de `MainWindow`. Los botones quedan deshabilitados
hasta que termina la carga (`on_data_loaded`).

Ruta: `{DBF_BASE_PATH}/fachist.DBF`. Desde 2026-09-02 se lee vía
`src/controllers/dbf_io.py` (DuckDB + caché Parquet en `{CACHE_PATH}`, solo las 12
columnas que usa la app). Ver [rendimiento-dbf.md](rendimiento-dbf.md).

**Encoding:** todos los `.DBF` son **codepage 850** (LDID `0x02` en el header). Se leen
con `config.DBF_ENCODING` (`cp850`). Antes se leían como `latin1` — eso rompía `Ñ`, `°`, `º`.

**Todos los informes de ventas (Thalamus, Litros, Sell In, Margen, IIBB indirectamente)
filtran este mismo DataFrame.** No se vuelve a leer el DBF salvo para datos de artículos/clientes.

#### Columnas de `fachist.DBF` usadas en la app

| Columna | Significado | Dónde se usa |
|---|---|---|
| `FECHA` | Fecha del comprobante | Todos los filtros por período |
| `MODELO` | Código interno de artículo (SKU) | Merge con `abmartic`, filtros por familia |
| `U_VENDIDAS` | Unidades vendidas | Litros, Margen, Thalamus (`Quantity`) |
| `TOTAVEN` | Total vendido ($) de la línea | Margen Beneficio |
| `TC` | Tipo de comprobante | Filtros (ver abajo) |
| `NC` | Número de comprobante | Thalamus (`Transaction ID`), IIBB |
| `CUENTA` | Nº de cliente (systemid) | Thalamus, IIBB, Margen |
| `NROEST` | Punto de venta / establecimiento | Thalamus (`Transaction ID`), IIBB (`00002`/`00003`) |
| `LETRA` | Letra del comprobante (A/B/C) | Thalamus (`Transaction ID`) |
| `VENDNUMERO` | Nº de vendedor | Filtro por vendedor (Litros, Margen) |
| `CODMOV` | Código de movimiento | Sell In filtra `CODMOV == 'RI'` (recepción) |
| `DESC` | Descripción del artículo | Margen (nombre de producto) |

#### Tipos de comprobante (`TC`)

| Código | Significado |
|---|---|
| `FC` | Factura |
| `NC` | Nota de crédito |
| `ND` | Nota de débito |
| `FE` | Factura electrónica |
| `CR` | Comprobante de recepción / remito |

Cada módulo arma su lista de `TC` según lo que necesita (esto es **intencional**, no un bug):

| Módulo | `TC` incluidos | Por qué |
|---|---|---|
| **Thalamus** | `FC, NC, FE, CR` | Solo interesa lo que **salió o se devolvió**. La `ND` no cambia lo despachado. |
| **Informe Litros / Sell In** | `FC, NC, ND, FE, CR` | La `ND` puede **modificar el stock** y por lo tanto los litros calculados. |
| **Margen Beneficio** | `FC, NC, ND, FE` | Se necesita el **importe ajustado** (`ND` = devolución de producto o anulación de una `NC`). |

> Si agregás un `TC` nuevo, decidí módulo por módulo con este criterio; no lo repliques a ciegas.

#### Convención de artículos

- `MODELO` que empieza con `L` → **lubricante** (Shell). Thalamus exige además `^L\d` (regex).
- `ARTIPROV` en `abmartic.DBF` = código del proveedor. Cuando existe, **reemplaza** al código interno
  en los reportes hacia terceros (Thalamus, precios).
- Clasificación de proveedor en Litros: `L...` → SHELL, `^\d{2}[A-Za-z]{2}\d{3}$` → VALVOLINE, resto → OTROS.

### Otras fuentes

| Recurso | Tipo | Módulos |
|---|---|---|
| `{DBF_BASE_PATH}/abmartic.DBF` | DBF | Litros, Margen, Thalamus, Precios (artículos, `CODMEDIDA`, `ARTIPROV`, `PRECIO1/7/8/9`) |
| `{DBF_HOREB_PATH}/abmartic.DBF` | DBF | Actualizar Precios (destino de la copia) |
| `{DBF_BASE_PATH}/ctaclien.DBF` | DBF | Thalamus, IIBB, Margen, Pedidos (clientes) |
| `{DBF_BASE_PATH}/ivatemp.DBF` | DBF | IIBB (retenciones) |
| `{DBF_BASE_PATH}/stock.DBF` | DBF | `controllerBD.py` (script suelto) |
| `{EXCEL_PRECIOS_PATH}/Lista de precios Mana.xlsm` | Excel (hoja `Lista De Precios`, header=2) | Thalamus, Margen, Precios |
| `{EXCEL_PRECIOS_PATH}/Lista Valvoline.xlsx` | Excel (hoja `Lista`, header=1) | Precios |
| `{EXCEL_THALAMUS_PATH}/Template_VENTA MANA.xlsx` | Excel plantilla | Thalamus (base de salida) |
| `{EXCEL_THALAMUS_PATH}/Template_CLIENTE MANA.xlsx` | Excel | Thalamus (registro de clientes) |
| `{EXCEL_LITROS_PATH}` = `{_b}/Thalamus/LITROS SHELL.xlsx` (hoja `GENERAL`) | Excel | Litros (clasificación), Ventas Mensuales (familia/litros) |
| `{ECHEQ_PATH}` = `{_b}/E-cheqs/` | Carpeta de Excel | E-Cheques |
| `{OUTPUT_PATH}` = `C:/tempdgr` | Carpeta de salida | IIBB |
| `{CACHE_PATH}` = `{OUTPUT_PATH}/cache_dbf` | Caché Parquet local de `fachist.DBF` | arranque (`dbf_io`) |
| PostgreSQL `pedidosMana` | Base relacional | Pedidos |

Todas las rutas salen de `src/controllers/config.py` (ver [controllers.md](controllers.md)),
que autodetecta entorno local (`d:/tiempo`) vs. remoto (`Z:`).

> ⚠️ **Deuda conocida:** varios módulos ignoran `config` y hardcodean rutas
> (`margenBeneficio.cargar_abmartic`, `EcheqWindow.direc`, `ImportThread.ruta_dbf`).
> Están marcados en cada archivo.

---

## Cómo usar esta carpeta al modificar

1. Antes de tocar un módulo, leé su `.md` y confirmá **qué archivos externos lee/escribe**.
2. Si cambiás un filtro de `TC`, `MODELO` o fechas, revisá la sección "Convención de artículos"
   arriba y los otros módulos que comparten `df_ventas`.
3. Si cambiás nombres de columnas esperadas de un DBF/Excel, buscá la columna en **todos** los `.md`.
4. Actualizá el `.md` correspondiente en el mismo commit que el cambio de código.

---

## Limpieza de código muerto — 2026-09-02

Eliminado (código no referenciado por ninguna ruta de ejecución):

| Archivo | Removido |
|---|---|
| `main.py` | `formatIIBB()`, `guardar_contenido()`, `seleccionar_archivo()`, `actualizar_precios()` (versión vieja O(n·m), reemplazada por `ActualizarPreciosThread`), `import dbf` |
| `src/controllers/others.py` | `format_thalamus()` |
| `src/controllers/MesAno.py` | `import sys`, `QApplication` (no usados) |
| `src/Views/Beneficio/DetalleBeneficio.py` | `from dbfread import DBF` (no usado) |

Pendiente de decisión: `src/controllers/controllerBD.py` (script CLI standalone, esquema obsoleto).
