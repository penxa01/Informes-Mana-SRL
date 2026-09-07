# Views / Beneficio — `src/Views/Beneficio/`

Módulo **Margen Beneficio**: análisis de rentabilidad por producto para un período/vendedor.

| Archivo | Clase | Rol |
|---|---|---|
| `margenBeneficio.py` | `margenBeneficio(QWidget)` | Ventana principal: tabla de productos con margen |
| `margenBeneficio.py` | `_CostoDelegate` | Editor de la columna "Costo Unit." en la tabla principal |
| `DetalleBeneficio.py` | `DetalleDialog(QDialog)` | Detalle venta por venta de un SKU (con cliente) |
| `DetalleBeneficio.py` | `_CostoDetalleDelegate` | Editor de "Costo Unit." en el detalle |
| `src/ui/widgets/indicadores.py` | `barra_porcentaje` | Mini "barra + valor" para la celda Margen % (color por umbral) |

---

> **Rediseño Tailwind (rama `style/beneficio-tailwind-look`)** — ambas ventanas se
> reescribieron según `prototypeExample/prototypeMargenBeneficio.html` y
> `prototypeDetalleBeneficio.html`:
> - **Índices de columna por constante** (`_C_*` en `margenBeneficio.py`, `_D_*` en
>   `DetalleBeneficio.py`). Ambas tablas ganaron una columna `#` al inicio, así que
>   **todo se corrió +1**. Si tocás el orden de columnas, cambiá SOLO la constante.
> - `margenBeneficio`: tarjeta de encabezado (título + badge de metadatos + buscador +
>   presets de margen `>25% / 20-25% / <20%`), tabla con header oscuro, columna
>   `Margen %` como barra (`barra_porcentaje`), tarjeta de resumen con pills + botón
>   verde "Exportar a Excel".
> - `DetalleDialog`: banner con KPIs (Unidades / Ventas / Beneficio / Margen %), toolbar
>   con búsqueda (cliente/cuenta/N° comp.) + filtro Tipo (FC/NC) que **oculta filas**
>   (`setRowHidden`, no rebuild — mantiene el índice `fila ↔ detalle_ventas`), barra de
>   totales consolidados al pie. Se quitó el botón "Imprimir Listado" del prototipo
>   (sería no-funcional).
> - Formato de moneda argentino en pantalla (`_money`: `$ 1.234,56`).
> - `barra_porcentaje` sanea `NaN`/`inf` (margen % con costo 0).
> - Test: `tests/verificar_beneficio_ui.py` (datos reales de fachist + catálogos).

> **UI integrada (F2b):** vive en `src/ui/paginas/margen.py` (`PaginaMargen`) con barra de
> filtro colapsable. `margenBeneficio` se refactorizó: `__init__` arma la UI vacía,
> `cargar(df_periodo_ventas)` la puebla (llamable N veces), catálogos (clientes + lista de
> precios + abmartic) se leen una sola vez vía `_asegurar_catalogos()`. El disparo viejo
> (`main_legacy.margenesBeneficio` + `DateRangeDialog`) sigue funcionando.

## Cómo se dispara — `main_legacy.margenesBeneficio()` (modelo viejo)

1. Diálogo `DateRangeDialog` (rango libre + vendedor; `pd.Timestamp`).
2. **Filtra `df_ventas`:**
   - `FECHA` entre `fecha_desde` y `fecha_hasta`
   - `MODELO` (como str) empieza con `L` (lubricantes)
   - opcional: `VENDNUMERO == vendedor_procesado`
   - `TC` ∈ (`FC`, `NC`, `ND`, `FE`)
3. `margenBeneficio(df_periodo_ventas=df_filtrado).show()`.

---

## Constructor `margenBeneficio.__init__(df_periodo_ventas=...)`

### Validaciones
- Si el DataFrame es `None`/vacío → warning + `close()`.
- **Columnas requeridas:** `FECHA`, `MODELO`, `U_VENDIDAS`, `TOTAVEN`. Si falta alguna → error + `close()`.
- **Columnas opcionales:** `CUENTA`, `NROEST`, `TC`, `NC`, `DESC`.
- `dropna(subset=["MODELO", "U_VENDIDAS", "TOTAVEN"])`.

### Cargas de datos
1. `cargar_clientes()` — **lee `{DBF_BASE_PATH}/ctaclien.DBF`** (`cp850`) →
   `self.clientes_dict = {CNUMERO(int→str): CNOMBRE}`.
2. Lista de precios — **lee `{EXCEL_PRECIOS_PATH}/Lista de precios Mana.xlsm`**, hoja
   `Lista De Precios`, `header=2` → `[SKU, Producto, "Precio Por envase"]`.
   Agrega `SKU_NORM` (`str.strip().str.upper()`). Si falla → precios en 0.
3. `cargar_abmartic()` — lee `{DBF_BASE_PATH}/abmartic.DBF` (`cp850`) → `self.abmartic_df`
   con `CODART_NORM`. Sirve para resolver `ARTIPROV`. (F2b: dejó de usar la ruta hardcodeada.)

---

## `margenesBeneficio(ventas)` — cálculo de márgenes

Por cada fila de venta:

| Cálculo | Fórmula |
|---|---|
| `precio_venta_unitario` | `TOTAVEN / U_VENDIDAS` |
| `precio_por_envase` (costo) | `obtener_precio_por_envase(SKU_NORM)` |
| `margen_unitario` | `precio_venta_unitario - precio_por_envase` |
| `margen_total` | `margen_unitario * U_VENDIDAS` |

Acumula por `SKU`: `Total Ventas` (Σ`TOTAVEN`), `Margen de beneficio` (Σ`margen_total`),
`Unidades Vendidas` (Σ`U_VENDIDAS`), `Costo` (primer `precio_por_envase`).

Guarda el **detalle línea por línea** en `self.detalles_por_sku[sku]` (fecha, cuenta, TC, NC,
unidades, total, precio unit., precio costo, margen unit.).

### Margen %
```
Margen % = Margen de beneficio / (Total Ventas - Margen de beneficio) * 100
```
Es decir **margen sobre costo** (no sobre venta). El denominador `Total Ventas - Margen` = costo total.

### `obtener_precio_por_envase(sku)` — búsqueda de costo (con caché)
1. Caché `self.cache_precios`.
2. Si `abmartic_df` está cargado: busca `CODART_NORM == sku`; si tiene `ARTIPROV`, **cambia el
   sku de búsqueda a `ARTIPROV`**.
3. Busca `SKU_NORM == sku` exacto en la lista de precios → `Precio Por envase`.
4. Si no, búsqueda parcial (`str.contains`).
5. Parsea el precio (soporta `"1.200,50"` y `"1200.50"`). Si no encuentra → `0` (y avisa por `print`).

### `obtener_nombre_producto(sku)`
1. Caché `self.cache_nombres_productos`.
2. Primero `DESC` de `periodoVentas` (por `MODELO == sku`).
3. Fallback: `Producto` de la lista de precios (exacto → parcial).
4. Último recurso: el propio `sku`.

---

## Interacción: costo editable y cascada

La columna **"Costo Unit." es editable** en ambas tablas (col `_C_COSTO` = 3 en la
principal, `_D_COSTO` = 9 en el detalle). Al confirmar (Enter):

### En la tabla principal — `on_costo_cambiado(fila, col=_C_COSTO)`
- `nuevo_margen = Total Ventas - nuevo_costo * Unidades Vendidas`
- `nuevo_pct = nuevo_margen / (Total Ventas - nuevo_margen) * 100`
- Actualiza `content_table` **y** `datos_originales` (para que el filtro no pierda el cambio).
- Propaga el nuevo costo a **todas** las líneas de `detalles_por_sku[sku]` (recalcula `MARGEN_UNITARIO`).
- Repinta solo las celdas afectadas (Costo, Margen $, Margen %) + estadísticas globales.

### En el detalle — `DetalleDialog._on_costo_cambiado(fila, col=_D_COSTO)`
- Edita **una línea** (`self.detalle_ventas[fila]` — dict **compartido por referencia** con el padre).
- `nuevo_margen_unit = PRECIO_UNITARIO - nuevo_costo`
- Recalcula celdas de la fila + stats del diálogo.
- Llama `on_costo_cambiado_cb` → `margenBeneficio._cascada_desde_detalle(sku)`:
  - `total_margen = Σ(MARGEN_UNITARIO * U_VENDIDAS)` de todas las líneas
  - `costo_ponderado = Σ(PRECIO_COSTO * U_VENDIDAS)`
  - `nuevo_costo_unit = costo_ponderado / total_unidades`
  - actualiza la fila del producto en la tabla principal + `datos_originales` + estadísticas.

> 🔗 La cascada es **bidireccional y por referencia compartida**. Si tocás la estructura de
> `detalles_por_sku` o el orden de columnas de cualquiera de las dos tablas, revisá los tres
> métodos: `on_costo_cambiado`, `_on_costo_cambiado`, `_cascada_desde_detalle`.

---

## Filtro y estadísticas

- `filtrar_tabla()` — busca en `SKU` o `Producto` (`contains`, lower). Trabaja sobre
  `self.datos_originales` (copia intacta post-cálculo).
- `actualizar_estadisticas()` — totales globales: Total Ventas, Total Margen,
  Margen Promedio (`total_margen / total_ventas * 100`), Productos mostrados.

---

## Exportar a Excel — `exportar_excel()`

`QFileDialog` → `margen_beneficio_{YYYYMMDD_HHMM}.xlsx` con **3 hojas** (`pd.ExcelWriter`, openpyxl):

| Hoja | Contenido |
|---|---|
| `Resumen` | SKU, Producto, Unidades Vendidas, Total Ventas, Margen de beneficio, Margen % |
| `Detalle_Completo` | Todas las líneas de `detalles_por_sku` + nombre de `CLIENTE` (desde `clientes_dict`) + `MARGEN_TOTAL` |
| `Estadisticas` | Totales, nº productos margen positivo/negativo, mejor/peor producto, clientes únicos |

`DetalleDialog.exportar_detalle()` — exporta **un solo SKU** a
`detalle_{SKU}_{YYYYMMDD_HHMM}.xlsx` (una hoja, con `CLIENTE` y `MARGEN_PORCENTUAL`).

---

## Archivos que toca

| Archivo | Modo |
|---|---|
| `{DBF_BASE_PATH}/fachist.DBF` | lee (vía `df_ventas`) |
| `{DBF_BASE_PATH}/ctaclien.DBF` | lee (nombres de cliente) |
| `d:/tiempo/vtiempoges/GESTION/MANA2014/abmartic.dbf` ⚠️ **hardcodeado** | lee (`ARTIPROV`) |
| `{EXCEL_PRECIOS_PATH}/Lista de precios Mana.xlsm` (hoja `Lista De Precios`) | lee (costos) |
| `margen_beneficio_*.xlsx` / `detalle_*.xlsx` (ruta elegida) | **escribe** |

---

## Bugs / deuda conocida

- El "costo" sale de la columna `Precio Por envase` de la lista de precios, **no** de un costo real
  de compra — es una aproximación que el usuario corrige a mano en la tabla.
- Margen % es sobre costo, no sobre venta — puede confundir a quien lea el informe.
- Búsqueda parcial de SKU (`str.contains`) puede matchear el producto equivocado.
