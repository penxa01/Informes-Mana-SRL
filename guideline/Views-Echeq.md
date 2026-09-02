# Views / Echeq — `src/Views/Echeq/`

Módulo **E-Cheques**: consolida los Excel de cheques electrónicos exportados del banco,
permite filtrar, agregar registros a mano y guardar un archivo maestro.

| Archivo | Clase | Rol |
|---|---|---|
| `EcheqDBF.py` | `EcheqWindow(QWidget)` | Widget embebible con filtros y tabla; acciones en `self.acciones_toolbar` |
| `EcheqFormDBF.py` | `Form(QDialog)` | Formulario de alta manual (un `QLineEdit` por columna) — **queda modal** |
| `src/ui/paginas/echeques.py` | `PaginaEcheques(PaginaBase)` | Sección del `AppWindow`; carga lazy en `on_activar` |

> A pesar del sufijo `DBF`, este módulo **no toca ningún DBF**. Trabaja solo con Excel.
> **F2c:** `EcheqWindow` pasó de `QMainWindow` a `QWidget`. Toolbar → `acciones_toolbar`
> (franja de comandos del `AppWindow`). Status bar propia al pie. Rutas: `config.ECHEQ_PATH`
> (antes `d:/tiempo/E-cheqs` hardcodeado, incluido el guardado a `Echeqs_sistema.xlsx`).

---

## Cómo se dispara — `main.manejadorEcheq()`

1. Muestra el panel de carga de `MainWindow` ("Cargando E-Cheques..."), deshabilita botones.
2. Lanza `ProgressBar.EcheqLoadThread` (hilo).
   - **Lee todos los `.xlsx` de `config.ECHEQ_PATH`** (`{_b}/E-cheqs/`).
   - Archivos cuyo nombre **empieza con `E`** → `read_excel(path)`; el resto → `read_excel(path, header=1)`.
   - Normaliza columnas, filtra a las 44 de `EcheqLoadThread.COLUMNAS`, concatena.
   - `drop_duplicates(subset=['Nro de Cheque'], keep='last')`.
3. `on_echeq_loaded(df)` → oculta panel, rehabilita botones, `EcheqWindow(df=df).show()`.

---

## `EcheqWindow.__init__(df=None)`

- Estado: `self.direc = 'd:/tiempo/E-cheqs'` ⚠️ **HARDCODEADO** (no usa `config.ECHEQ_PATH`).
- `self.campos` = columnas visibles:
  `["Nro de Cheque", "Echeq id", "Pagador Nombre Apellido/Razón Social", "Monto",
  "Fecha de Pago", "Fecha de Emisión"]`
- `self.df` arranca con las **44 columnas completas** (aunque solo se muestran 6).
- Si viene `df` (del hilo) → lo usa y `modified=True`.
- Si no → `cargar_datos_iniciales()` lee de `self.direc` con `InfoProgressBarWindow`
  (misma lógica que `EcheqLoadThread` pero en el hilo de UI, con `processEvents`).

---

## Lógica de negocio

### `addEcheqFile(excel)` — incorporar un Excel
1. Si la columna `Pagador Cuit` **contiene letras** en algún valor (`tiene_letras`), asume que
   las columnas `Pagador Cuit` y `Pagador Nombre Apellido/Razón Social` **vienen invertidas** y
   las intercambia.
2. Dedup contra los `Nro de Cheque` ya cargados (set en memoria).
3. Filas sin `Nro de Cheque` (NaN) → se descartan.
4. `pd.concat` de las filas nuevas.

### `aplicar_filtros()` — filtros por campo
- Un `QLineEdit` por cada uno de los 6 campos visibles.
- Cada filtro con texto aplica `df[col].astype(str).str.contains(texto, case=False, na=False)`.
- Sin filtros → muestra todo.

### `mostrar_en_tabla(df)` — pintado
- Actualiza contador de registros en el título y la status bar.
- **Colorea la columna `Monto`** (índice 3): `> 100.000` → rojo claro; `> 50.000` → amarillo claro.
- `except:` desnudo si el monto no parsea.

### `openForm()` — alta manual
- Abre `Form(self.df.columns)` — genera un `QLineEdit` por columna (grilla de 2).
- Al aceptar: `obtener_datos()` → dict → nueva fila → `pd.concat` → `modified=True`.
  > Nota: `Form` recibe **todas** las columnas del `df` (44), no solo las 6 visibles.
  > Pero `openForm` construye la fila con `columns=self.campos` (6) — posible descuadre.

### `guardar_archivo()` — persistencia
- **Escribe SIEMPRE en `d:/tiempo/E-cheqs/Echeqs_sistema.xlsx`** ⚠️ **HARDCODEADO**, sin diálogo.
- `self.df.to_excel(ruta, index=False)` — guarda las 44 columnas.

### `closeEvent(event)`
- Si `modified`: pregunta "¿Guardar antes de salir?" (Yes/No/Cancel).

---

## `Form` (`EcheqFormDBF.py`)

Diálogo genérico: recibe una lista de `campos`, crea un `QLineEdit` por campo en grilla de 2
columnas, botones Guardar/Cancelar. `obtener_datos()` devuelve `{campo: texto}`.

---

## Archivos que toca

| Archivo | Modo |
|---|---|
| `config.ECHEQ_PATH` (`{_b}/E-cheqs/*.xlsx`) | lee (vía `EcheqLoadThread`) |
| `d:/tiempo/E-cheqs/*.xlsx` ⚠️ **hardcodeado** | lee (vía `cargar_datos_iniciales`) |
| `d:/tiempo/E-cheqs/Echeqs_sistema.xlsx` ⚠️ **hardcodeado** | **escribe** |

---

## Bugs / deuda conocida

- Guardado sin `QFileDialog` — siempre escribe `Echeqs_sistema.xlsx` en `config.ECHEQ_PATH`.
- El botón "Actualizar" (`cargar_datos_iniciales`) **no** hace merge con lo ya cargado: recarga
  desde disco y puede perder altas manuales no guardadas.
- `openForm` arma la fila con 6 columnas pero `Form` pide 44.
- `except:` desnudo en `mostrar_en_tabla`.
- El prompt "¿guardar antes de salir?" (ex `closeEvent`) se perdió al pasar a `QWidget`.
  `hay_cambios_sin_guardar()` queda listo para que el `AppWindow` lo chequee al cerrar (F3).
