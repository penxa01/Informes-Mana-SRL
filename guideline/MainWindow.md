# MainWindow — `main.py`

Punto de entrada de la app. Contiene la ventana principal (grilla de 9 botones), la
**carga inicial de ventas**, y la lógica completa de 4 módulos: **Thalamus**, **Ventas
Mensuales**, **Informe IIBB** y **Actualizar Precios**. Los otros 5 botones solo abren
ventanas de `src/Views/` (ver sus `.md`).

Clase: `MainWindow(QMainWindow)`. Se instancia en `if __name__ == "__main__"`.

---

## Arranque y carga inicial

1. `setupUI()` arma header (logo `src/Distribuidora/Logo Mana SRL.jpg`), grilla 3×3 de botones
   y el panel de carga. Todos los botones arrancan **deshabilitados**.
2. `getStyleSheet()` — CSS inline (≈120 líneas).
3. `load_data()` lanza `ProgressBar.LoadDataThread` (hilo).
   - **Lee:** `{DBF_BASE_PATH}/fachist.DBF` vía `dbf_io.leer_dbf_cacheado` (DuckDB +
     caché Parquet, solo 12 columnas). `self.df_ventas` queda con esas 12. Ver
     [rendimiento-dbf.md](rendimiento-dbf.md).
   - Al terminar emite `data_loaded(df)` → `on_data_loaded(df)`:
     - `self.df_ventas = df`
     - oculta el panel de carga, habilita botones, foco en Thalamus.

`resource_path(rel)` resuelve assets tanto en dev como dentro del `.exe` de PyInstaller
(usa `sys._MEIPASS`).

### Botones y sus funciones

| Botón | Método | Módulo |
|---|---|---|
| Thalamus | `informeThalamus2` | acá |
| Informe Litros | `reporteLitros` | [Views-Litros.md](Views-Litros.md) |
| Sell In | `sellIn` | [Views-Litros.md](Views-Litros.md) |
| Ventas Mensuales | `reporteMensual` | acá |
| Informe IIBB | `IIBB` | acá |
| E-Cheques | `manejadorEcheq` | [Views-Echeq.md](Views-Echeq.md) |
| Pedidos | `pedidosCaller` | [Views-Pedidos.md](Views-Pedidos.md) |
| Margen Beneficio | `margenesBeneficio` | [Views-Beneficio.md](Views-Beneficio.md) |
| Actualizar Precios | `actualizar_precios_mana_horeb` | acá |

---

## 1. Thalamus — `informeThalamus2()`

Genera el reporte diario de ventas de lubricantes para cargar en el sistema Thalamus (Shell).

### Disparador
Diálogo `Fecha` (texto: `dd`, `dd/mm` o `dd/mm/yyyy`; completa con la fecha de hoy).

### Lógica de negocio
1. **Filtra `df_ventas`:**
   - `FECHA` == fecha seleccionada
   - `MODELO` matchea regex `^L\d` (lubricante)
   - `CUENTA` no nula
   - `TC` ∈ (`FC`, `NC`, `FE`, `CR`)
2. `buscaArtic(df_filtrado)` (`others.py`) → **lee `{DBF_BASE_PATH}/ABMARTIC.DBF`** (`cp850`),
   filtra `CODART ∈ MODELO` → `SKUArticDS` con columnas `CODART`, `ARTIPROV`.
3. `getCodigosCorrectos(MODELO, SKUArticDS)` → reemplaza cada `MODELO` por su `ARTIPROV`
   cuando existe (no vacío / no NaN).
4. `addPrice(MODELO, SKUArticDS)` → **lee `{EXCEL_PRECIOS_PATH}/Lista de precios Mana.xlsm`**,
   hoja `Lista De Precios`, `header=2`. Usa columnas `SKU`, `Producto`, `Precio Por envase`,
   `Informe  s/IVA` (ojo: **dos espacios** en "Informe  s/IVA"). Arma dict `SKU → Informe s/IVA`
   y busca por el código corregido (ARTIPROV si aplica). Si no encuentra → precio 0.
5. Construye el `DataFrame` de salida:
   | Columna salida | Origen |
   |---|---|
   | `Systemid` | `CUENTA` (int) |
   | `Sale Date` | `FECHA` → `%Y/%m/%d` |
   | `Transaction ID` | `"{TC} {LETRA} {NROEST} {NC.zfill(8)}"` |
   | `Code` | código corregido (ARTIPROV o MODELO) |
   | `Quantity` | `U_VENDIDAS` (int) |
   | `Description 1` | `F` si `TC==FC`, `NC` si `TC==NC`, sino `''` |
   | `Amount` | precio s/IVA × (implícito por fila), `round(...,2)` |
6. `verificaCliente(Systemid)` — actualización del padrón de clientes (ver abajo).
7. **Salida Excel:**
   - Base: `{EXCEL_THALAMUS_PATH}/Template_VENTA MANA.xlsx` (debe existir, sino aborta con warning).
   - Borra filas 2..max, agrega las filas nuevas, formatea columna B como `yyyy/mm/dd;@`.
   - Guarda como `{EXCEL_THALAMUS_PATH}/Template_VENTA MANA {dd-mm}.xlsx`.
   - `PermissionError` → avisa que el archivo está abierto.

### `verificaCliente(numero_clientes)` — subrutina
- **Lee** `{EXCEL_THALAMUS_PATH}/Template_CLIENTE MANA.xlsx` (columna `Systemid`).
- **Lee** `{DBF_BASE_PATH}/ctaclien.DBF` (`cp850`).
- Clientes en la venta que **no están** en el template → arma filas nuevas con datos de `ctaclien`:
  - `FiscalID` = `CUIT` sin guiones; `FiscalName`/`Name` = `CNOMBRE`
  - `Address.*` desde `CPROVIN`, `CDIREC`, `CCP`, `CLOCAL`
  - `address.stateId` desde dict `codigos_prov` (provincia argentina → id `3557`–`3580`)
  - `Vendedor` desde dict `cod_vendedor` (`1`→ROMULO SANCHEZ, `3`→MIGUEL ORTUnO, `4`→JOSE BANCO,
    `5`→DIEGO CALDERON, `6`→MATIAS BARATA, `9`→MARTIN MOYA)
  - `subsegmento` → **diálogo manual** `selectSubsec(id, nombre)`: combo con ~30 subsegmentos
    (AGRO, MINERÍA, TRANSPORTE, NAVAL, LUBRICENTRO, ...). Si se cancela devuelve `None`.
- Guarda vía `others.format_CLIENTE(documento, ruta, cant)` — reescribe el Template con anchos
  de columna `A`–`Q` fijos y avisa cuántos clientes se agregaron.

### Archivos que toca Thalamus
| Archivo | Modo |
|---|---|
| `{DBF_BASE_PATH}/fachist.DBF` | lee (vía `df_ventas`) |
| `{DBF_BASE_PATH}/ABMARTIC.DBF` | lee |
| `{DBF_BASE_PATH}/ctaclien.DBF` | lee |
| `{EXCEL_PRECIOS_PATH}/Lista de precios Mana.xlsm` | lee |
| `{EXCEL_THALAMUS_PATH}/Template_VENTA MANA.xlsx` | lee (base) |
| `{EXCEL_THALAMUS_PATH}/Template_VENTA MANA {dd-mm}.xlsx` | **escribe** |
| `{EXCEL_THALAMUS_PATH}/Template_CLIENTE MANA.xlsx` | lee + **escribe** (si hay clientes nuevos) |

---

## 2. Ventas Mensuales — `reporteMensual()`

Consolida los reportes diarios de Thalamus de un mes en un único `Anexo_6_MES.xlsx`.

### Disparador
`seleccionar_carpeta()` → `QFileDialog` de carpeta. El usuario elige la carpeta con los
`Template_VENTA MANA *.xlsx` del mes.

### Lógica de negocio
1. Arma cabeceras fijas (`DISTRIBUIDOR`, fila de columnas).
2. **Lee** `config.EXCEL_LITROS_PATH` (`{_b}/Thalamus/LITROS SHELL.xlsx`), hoja `GENERAL` → `df_art`
   (columnas `articulo`, `Artiprov`, `desc`, `codmedida`).
3. Por cada archivo de la carpeta que **empiece con `Template`**:
   - Lee el Excel diario.
   - Por cada venta: busca el artículo por `articulo == Code` **o** `Artiprov == Code`.
     - Si no encuentra → `QMessageBox` informando el código faltante y sigue.
     - `Familia`: `get_familia(art)` → primera palabra de `desc` si está en
       `[Helix, Rimula, Gadus, Omala, Tellus, Advance, Corena, Coolant, Diala, Raizen,
       Spirax, Refrigeration, Tonna, Turbo]`, sino `'Otro'`.
     - `Litros`: `get_litros(art, cantidad)` = `art['codmedida'] * cantidad`.
     - Fila: `Fecha` (`Sale Date` → `%Y/%m/%d`), `Comprobante` (`Transaction ID`),
       `Codigo de producto` (`Code`), `Familia`, `Litros`.
4. `df_mensual.sort_values(by='Dia / Periodo')` — **nota:** no reasigna (`inplace` falta), el sort no tiene efecto.
5. `QFileDialog.getSaveFileName` (default `Anexo_6_MES.xlsx`) → `others.generar_archivo_excel(df, ruta)`:
   - Título `DISTRIBUIDOR` merge `A1:D1`, encabezados `Dia / Periodo / SKU / Familia / Litros`
     (rojo `ED1C24` sobre amarillo `FFD500`), anchos `[20, 25, 15, 10]`.
   - Borra 2 filas dummy y guarda.

### Archivos que toca
| Archivo | Modo |
|---|---|
| `{_b}/Thalamus/LITROS SHELL.xlsx` (hoja `GENERAL`) | lee |
| Carpeta elegida / `Template_*.xlsx` | lee (varios) |
| `Anexo_6_MES.xlsx` (ruta elegida por el usuario) | **escribe** |

---

## 3. Informe IIBB — `IIBB()`

Genera el `.txt` de retenciones de Ingresos Brutos para importar en ARCA/AFIP.

### Disparador
Diálogo `MesAnioDialog`: combo mes (nombre → número), input año (texto), combo jurisdicción
(`San Juan`→1, `Mendoza`→3).
> ⚠️ La jurisdicción se captura pero **no se usa** en el filtro actual (el filtro usa
> `NROEST ∈ ('00002', '00003')` hardcodeado).

### Lógica de negocio
1. **Lee** `{DBF_BASE_PATH}/ctaclien.DBF` (`dbfread`, `cp850`) y
   `{DBF_BASE_PATH}/ivatemp.DBF` (~71 MB) vía `dbf_io.leer_dbf(..., COLUMNAS_IVATEMP)`.
2. `ivatemp['FECHA']` → `datetime` (`errors='coerce'`).
3. **Filtra `ivatemp`:** `FECHA.month == mes`, `FECHA.year == anio`, `NROEST ∈ ('00002', '00003')`.
4. Por cada fila con `PERCE_1 != 0`:
   - `nc` = `str(NC).split()[0].zfill(12)`
   - `perce_1_83` = `round(PERCE_1 * 0.83333327, 2)` — base imponible (~83,33 %)
   - `perce_1_16` = `round(PERCE_1 * 0.1666667, 2)` — excedente (~16,67 %)
   - `TC`: `FC → FA`, `NC → CA`
   - Busca cliente en `ctaclien` por `CNUMERO == CUENTA`:
     - `CNOMBRE`, `INGBRUT` (`"000-000000-0"` si viene vacío), `CUIT` sin guiones, `CDIREC`
   - Fila de salida (11 campos, en orden):
     `CNOMBRE, CUIT, CDIREC, INGBRUT, FECHA(%d/%m/%Y), TC, NC, NETO, 3.00, PERCE_1_83, PERCE_1_16`
   - `total_ingresos_brutos += PERCE_1`
5. **Escribe** `{OUTPUT_PATH}/salib {mes}-{anio}.txt` — `to_csv(sep='\t', header=False, index=False)`.
6. Muestra dos `QMessageBox`: confirmación de guardado + resumen (total $ y cantidad de comprobantes).

### Archivos que toca
| Archivo | Modo |
|---|---|
| `{DBF_BASE_PATH}/ctaclien.DBF` | lee |
| `{DBF_BASE_PATH}/ivatemp.DBF` | lee |
| `{OUTPUT_PATH}/salib {mes}-{anio}.txt` | **escribe** |

---

## 4. Actualizar Precios — `actualizar_precios_mana_horeb()`

Actualiza los precios en `abmartic.DBF` de MANA y replica el archivo a HOREB.

### Disparador
Botón directo (sin diálogo). Muestra el panel de carga, deshabilita botones y lanza
`ProgressBar.ActualizarPreciosThread` (hilo). Ver detalle del hilo en [controllers.md](controllers.md).

### Lógica de negocio (dentro del hilo)
1. **Lee** `{EXCEL_PRECIOS_PATH}/Lista de precios Mana.xlsm` (hoja `Lista De Precios`, `header=2`)
   y `{EXCEL_PRECIOS_PATH}/Lista Valvoline.xlsx` (hoja `Lista`, `header=1`).
2. Arma dict `updates` por `SKU` (salteando la primera fila = subcabecera):
   - **Mana:**
     - `PRECIO1` = `round(Precio de venta s/IVA, 2)` — s/IVA
     - `PRECIO7` = `round(Lista Gerardo / 1.21, 2)` — Gerardo (quita IVA)
     - `PRECIO8` = `round(Lista Ecominera S/IVA, 2)` — Ecominera / industria
     - `PRECIO9` = `round(Lista Luis Richarte / 1.21, 2)` — Luis Richarte (quita IVA)
   - **Valvoline** (itera después, **sobrescribe** `PRECIO1`/`PRECIO7` si el SKU coincide):
     - `PRECIO1` = `round(PRECIO S/IVA, 2)`
     - `PRECIO7` = `round(LISTA GERARDO, 2)`
3. Abre `{DBF_BASE_PATH}/abmartic.DBF` en `READ_WRITE`. **Pasada única** O(n+m):
   por cada artículo, matchea `CODART` o `ARTIPROV` contra `updates` y hace `setattr` de los campos.
4. `shutil.copy2({DBF_BASE_PATH}/abmartic.DBF, {DBF_HOREB_PATH}/abmartic.DBF)` — **copia el DBF
   completo de MANA sobre el de HOREB** (no fusiona; HOREB queda idéntico a MANA).
5. Señales: `progress_actualizado(str)` → texto del panel; `finalizado(bool, str)` → `QMessageBox`.

> El módulo actualiza **dos empresas distintas** (MANA y HOREB) que corren en el mismo sistema
> de gestión pero con bases de datos separadas — de ahí la copia MANA→HOREB. Comportamiento correcto.

### Archivos que toca
| Archivo | Modo |
|---|---|
| `{EXCEL_PRECIOS_PATH}/Lista de precios Mana.xlsm` | lee |
| `{EXCEL_PRECIOS_PATH}/Lista Valvoline.xlsx` | lee |
| `{DBF_BASE_PATH}/abmartic.DBF` | lee + **escribe** |
| `{DBF_HOREB_PATH}/abmartic.DBF` | **sobrescribe** (copia) |

---

## Otros métodos de `MainWindow`

| Método | Uso |
|---|---|
| `keyPressEvent` | Enter/Return activa el botón que tiene foco |
| `get_familia` / `get_litros` | Helpers de Ventas Mensuales |
| `seleccionar_carpeta` | `QFileDialog` de carpeta (Ventas Mensuales) |

---

## Bugs / deuda conocida en `main.py`

- **`reporteLitros()` (≈línea 946):** indentación incorrecta — el `if dateRange.exec_() == Accepted:`
  solo envuelve una línea. Si el usuario cancela el diálogo, igual abre `ReportLts`. `sellIn()` lo hace bien.
- `import PyQt5.QtCore as Qt` **y** `as core` en el mismo archivo (ambos se usan; consolidar a uno).
- `crear_botones_principales`: la variable de loop `for config in botones_config:` **shadowea** el
  módulo `config` importado. Funciona porque no se usa el módulo ahí, pero es frágil.
- ~14 `print()` de debug.
- Diccionarios `cod_vendedor` / `codigos_prov` / `subsegmentos` / `familias` hardcodeados inline.
