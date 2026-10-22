# Views / Litros — `src/Views/Litros/LitrosDBF.py`

Cubre **dos** modos del mismo widget `ReportLts`:

- **Informe Litros** — con gráficos comparativos.
- **Sell In** — misma tabla, panel de gráficos oculto (`graficos=False`).

> **UI integrada (F2a):** ambos modos viven en `src/ui/paginas/litros.py` (`PaginaLitros`),
> con una barra de filtro colapsable arriba. `ReportLts` se refactorizó: `__init__()` arma
> la UI vacía y `cargar(df_periodo_ventas, df_ventas, graficos)` la puebla (llamable N
> veces). El disparo viejo (`main_legacy.reporteLitros` / `sellIn` + `DateYearRangeDialog`
> modal) sigue funcionando por compatibilidad (`ReportLts(df, ...)` → carga + `showMaximized`).

Archivo único: `LitrosDBF.py` (~1400 líneas). Clases: `ReportLts(QWidget)`,
`InteractiveCanvas(FigureCanvasQTAgg)`, más el helper `_codmedida_a_litros` y el mapa
`_CODMEDIDA_LITROS`.

---

## Cómo se dispara

### Informe Litros — `main.reporteLitros()`
1. Diálogo `DateYearRangeDialog` (combos MM/YYYY + manual + vendedor).
2. `main.py` calcula `fecha_desde` / `fecha_hasta` (día 1 / último día del mes, o día exacto si manual).
3. **Filtra `df_ventas`:**
   - `FECHA` entre `fecha_desde` y `fecha_hasta`
   - opcional: `VENDNUMERO == vendedor_procesado`
   - `TC` ∈ (`FC`, `NC`, `ND`, `FE`, `CR`) — (con `CR` duplicado en el código; sin efecto)
4. `ReportLts(df_filtrado, df_ventas=self.df_ventas, graficos=True)`.

### Sell In — `main.sellIn()`
1. Diálogo `DateYearRangeDialog(enable_seller=False)`.
2. `main.py` calcula el rango de fechas igual que arriba.
3. **Filtra `df_ventas`:**
   - `FECHA` entre `fecha_desde` y `fecha_hasta`
   - `MODELO` empieza con `L`
   - `CODMOV == 'RI'` (recepción de mercadería — compras)
4. `ReportLts(df_filtrado, df_ventas=self.df_ventas, graficos=False)`.

> ⚠️ Sell In **no** filtra por `TC`; Informe Litros **no** filtra por `MODELO startswith L`
> (solo por `TC`). Son criterios de negocio distintos a propósito.

---

## Constructor `ReportLts.__init__(df_periodo_ventas, df_ventas=None, graficos=True)`

- `self.periodoVentas` = `df_periodo_ventas[["FECHA", "TC", "MODELO", "U_VENDIDAS"]]` (ya filtrado).
- `self.df_ventas_completo` = `df_ventas` — DataFrame completo, solo para la comparación año anterior.
- **Lee `{DBF_BASE_PATH}/abmartic.DBF`** (`cp850`) → `self.bdArt` = `[CODART, DESC, CODMEDIDA]`.
- **Lee `config.EXCEL_LITROS_PATH`** (`LITROS SHELL.xlsx`), hoja `GENERAL` → `self.Clasificacion` =
  `[articulo, Clasificacion, Artiprov]`.
- Arma UI (con splitter tabla|gráficos si `graficos=True`, si no solo tabla).
- `LoadContent()` → ordena por código → `actualizar_totales()` → `showContent()`.

---

## `LoadContent()` — cálculo central

1. `merge` de `periodoVentas` con `bdArt` por `MODELO == CODART` (**inner** → descarta ventas
   sin artículo en `abmartic`).
2. `litros_u` = `_codmedida_a_litros(CODMEDIDA)` por fila.
3. `litros` = `U_VENDIDAS * litros_u`, redondeado a 2.
4. `Proveedor` = `_clasificar_proveedor(MODELO)`:
   - empieza con `L` (case-insensitive) → `SHELL`
   - regex `^\d{2}[A-Za-z]{2}\d{3}$` → `VALVOLINE`
   - resto → `OTROS`
5. `Premium`: dict de `Clasificacion` indexado por `articulo` **y** por `Artiprov`
   (`cls.get(MODELO, "-")`), pero **solo si `Proveedor == SHELL`**; si no, `"-"`.
6. `groupby("MODELO")` → agrega: `Descripcion` (first), `Unidades Vendidas` (sum),
   `Litros` (sum), `Proveedor` (first), `Premium` (first).
7. `self.content_table` = `[Codigo de Producto, Descripcion, Unidades Vendidas, Litros, Proveedor, Premium]`.
8. Totales:
   - `self.TotalLts` = suma de `Litros`
   - `self.TotalPremium` = suma de `Litros` donde `Premium == "Premium"`

### `_codmedida_a_litros(codmedida)` — conversión de unidades
- Normaliza (`strip().lower()`) y busca en `_CODMEDIDA_LITROS` (dict explícito de ~80 entradas):
  litros directos, galones (`1 gl`→3.785), cc/ml (`500 c`→0.5), onzas, kg (1 kg = 1 L),
  gramos (`500 g`→0.5), libras (`35 lb`→15.876). Unidades sin equivalencia (`kit`, `2 tn`,
  criques) → `0.0`.
- **Fallback:** si no está en el dict, extrae el primer número con regex `^(\d+(\.\d+)?)` y lo
  usa como litros. Si no hay número → `0.0`.

> 🔧 **Cuando aparezcan `CODMEDIDA` nuevos en `abmartic`:** agregarlos al dict `_CODMEDIDA_LITROS`.
> El fallback numérico cubre solo códigos que ya vienen expresados en litros.

---

## Filtros de la tabla (`aplicar_filtro`)

- Texto por `Descripcion` (`contains`, case-insensitive).
- Checkboxes `SHELL` / `VALVOLINE` / `OTROS` (por `Proveedor`).
- Checkbox "Solo productos Premium (Shell)" → `Premium == "Premium"`.
- Recalcula `TotalLts` y `TotalPremium` sobre el subconjunto filtrado y refresca los labels.

`showContent(df)` pinta la `QTableWidget` con formato: unidades/litros alineados a la derecha
en verde, colores por proveedor (`SHELL` naranja, `VALVOLINE` azul, `OTROS` gris), Premium en dorado.

---

## Panel de gráficos (solo `graficos=True`)

Usa `matplotlib` embebido en `InteractiveCanvas` (con tooltips vía `mplcursors` si está
instalado, si no fallback manual).

### `generar_histograma_comparativo()`
- `dias_diferencia = (fecha_max - fecha_min).days`
  - `<= 31` → gráfico **diario** (`generar_histograma_diario_comparativo`)
  - `> 31` → gráfico **mensual** (`generar_histograma_mensual_comparativo`)
- Cada uno compara **año actual vs. año anterior**:
  - `obtener_datos_anio_anterior*` filtra `self.df_ventas_completo` en el mismo rango −1 año,
    con `TC` ∈ (`FC`, `NC`, `ND`, `FE`, `CR`), y suma `+1 año` a las fechas para superponer en el eje.

### Selección de productos
- `lista_productos` (checkboxes) con búsqueda.
- `actualizar_grafico_productos_seleccionados()`:
  - sin selección → histograma general
  - con selección → `generar_histograma_suma_productos()` (suma de litros de los productos tildados,
    litros/unidad calculado desde `content_table`: `Litros / Unidades Vendidas`).
- Clic en una fila de la tabla (`on_producto_seleccionado`) togglea el checkbox correspondiente.

---

## Archivos que toca

| Archivo | Modo |
|---|---|
| `{DBF_BASE_PATH}/fachist.DBF` | lee (vía `df_ventas` de `MainWindow`) |
| `{DBF_BASE_PATH}/abmartic.DBF` | lee (`CODART`, `DESC`, `CODMEDIDA`) |
| `config.EXCEL_LITROS_PATH` (`{_b}/Thalamus/LITROS SHELL.xlsx`, hoja `GENERAL`) | lee |

**No escribe nada.** El README histórico menciona "Exporta a Excel" pero **esa función no
existe en el código actual** de `ReportLts`.

---

## Bugs / deuda conocida

- Sin exportación a Excel (contradice el README).
- `merge` inner en `LoadContent`: ventas de artículos ausentes en `abmartic` desaparecen del informe
  sin aviso.
- `generar_histograma_suma_productos` tiene bloques de configuración de ejes **duplicados**
  (≈líneas 907–937).
- `except:` desnudo en `on_hover_mplcursors` (≈línea 183).
- `_clasificar_proveedor` para VALVOLINE depende de un formato de código rígido; códigos que
  no matchean el regex caen en `OTROS`.
