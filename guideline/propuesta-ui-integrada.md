# Propuesta — UI integrada (ventana única, estilo Office)

> **Estado: DECISIONES CERRADAS. Implementación por fases en la rama `feat/ui-integrada`.**
>
> **Punto de retorno:** tag `checkpoint-pre-ui` (commit `f27248a`) = estado con el modelo
> viejo de 9 ventanas, ya con DuckDB/caché/encoding. `main` se queda ahí hasta que la
> UI nueva esté completa y aprobada.
> - Volver al estado viejo: `git checkout main` (o `git checkout checkpoint-pre-ui`).
> - Descartar todo lo de UI: `git branch -D feat/ui-integrada`.
> - Cada fase (F1..F3) es un commit en la rama → se puede volver a cualquier fase intermedia.

## Decisiones (cerradas 2026-09-02)

| # | Decisión |
|---|---|
| 1 | Diálogos de drill-down / creación (`DetalleDialog`, `DialogoNuevoPedido`, `VentanaDetallePedido`, `VentanaHistorialCompleto`, `Form`) → **quedan modales**. |
| 2 | Navbar: **toolbar de secciones + `QStackedWidget` manejados por un registro de páginas**, más una **franja de comandos contextual** debajo del navbar (cada página aporta sus acciones). Es lo más escalable: agregar una sección = 1 entrada en el registro + 1 clase de página. Ver "Navbar escalable" abajo. |
| 3 | Pedidos: el `DatabaseSyncManager` (polling + toasts) queda **siempre activo en background**, estés en la pestaña que estés. Intervalo `2 s → 8 s`. |
| 4 | Reorganizar a **`src/ui/`** (aprobado). |
| 5 | Filtro de Litros / Margen: **barra arriba, colapsable**. |

## Objetivo

Reemplazar el modelo actual (ventana principal con grilla de 9 botones, cada uno abre
una **ventana nueva**) por **una sola ventana** con una **navbar superior** de secciones
y un área de contenido que cambia según la sección activa.

### Navbar (5 secciones)

```
┌─────────────────────────────────────────────────────────────────────────┐
│  💧 LITROS   │  📋 PEDIDOS   │  🧾 E-CHEQUES   │  📊 MARGEN   │  ⚙ OTROS  │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│                         área de contenido                               │
│                       (cambia según sección)                            │
│                                                                         │
├─────────────────────────────────────────────────────────────────────────┤
│  entorno: LOCAL   │   ventas: 153.176 filas · 2014→2026   │   v1.6.x    │
└─────────────────────────────────────────────────────────────────────────┘
```

- **SELL IN** se integra dentro de **LITROS** como un modo (`Ventas` / `Sell In`) — es el
  mismo informe con otro filtro (`CODMOV = 'RI'`, sin filtro de `TC`, sin gráficos).
- **OTROS** agrupa las funcionalidades que hoy no abren ventana propia: Thalamus,
  Ventas Mensuales, Informe IIBB, Actualizar Precios.

---

## Arquitectura técnica

```
QMainWindow (AppWindow)
├── QToolBar  "navbar"      ── QToolButton por sección (QActionGroup exclusivo, checkable)
├── QToolBar  "comandos"    ── acciones de la página activa (Nuevo / Guardar / …); oculta si la página no aporta ninguna
├── QStackedWidget (central)
│     ├── PaginaLitros(QWidget)     (incluye Sell In)
│     ├── PaginaPedidos(QWidget)
│     ├── PaginaEcheques(QWidget)
│     ├── PaginaMargen(QWidget)
│     └── PaginaOtros(QWidget)
└── QStatusBar (compartida)
```

### Navbar escalable — registro de páginas

`AppWindow` **no** cablea cada página a mano. Hay un registro:

```python
# src/ui/registro.py
PAGINAS = [
    PageDef(id="litros",   titulo="Litros",   icono="gotas.png",   factory=PaginaLitros,   necesita_ventas=True),
    PageDef(id="pedidos",  titulo="Pedidos",  icono="pedidos.png", factory=PaginaPedidos,  necesita_ventas=False),
    PageDef(id="echeques", titulo="E-Cheques",icono="echeq.png",   factory=PaginaEcheques, necesita_ventas=False),
    PageDef(id="margen",   titulo="Margen",   icono="margen.png",  factory=PaginaMargen,   necesita_ventas=True),
    PageDef(id="otros",    titulo="Otros",    icono="informe.png", factory=PaginaOtros,    necesita_ventas=True),
]
```

`AppWindow` itera `PAGINAS`: por cada una crea el `QToolButton` del navbar y agrega
`factory(self)` al stack. **Agregar una sección nueva = una línea en `PAGINAS` + la clase
de página.** Cero cambios en `AppWindow`.

### Contrato de página (`src/ui/paginas/base.py` → `PaginaBase(QWidget)`)

| Método | Cuándo | Default |
|---|---|---|
| `__init__(self, app)` | al construir el stack (una vez) | arma la UI |
| `on_activar(self)` | cada vez que la pestaña se vuelve visible | no-op (override para lazy load / refresh) |
| `on_ventas_listas(self, df)` | cuando `LoadDataThread` termina | no-op |
| `acciones_barra(self)` | al activar la página → puebla la toolbar "comandos" | `[]` (sin franja de comandos) |

`app` (el `AppWindow`) expone: `app.df_ventas`, `app.status` (status bar), `app.recurso(nombre)`
(wrapper de `resource_path`), y señales de carga.

### Carga de `df_ventas`

Igual que hoy: `ProgressBar.LoadDataThread` (DuckDB + caché Parquet) al iniciar, resultado
en `AppWindow.df_ventas`. Las páginas con `necesita_ventas=True` muestran un overlay
"Cargando base de ventas…" hasta `on_ventas_listas`. Pedidos y E-Cheques arrancan usables
de una (no dependen de `df_ventas`).

---

## Detalle por sección

### LITROS (+ Sell In)

**Hoy:** `main.reporteLitros` / `main.sellIn` abren `DateYearRangeDialog` (modal),
filtran `df_ventas`, y hacen `ReportLts(...).show()` (`QWidget`, `showMaximized()`).

**Propuesta:**
- **Barra de filtro arriba** (reemplaza el diálogo modal):
  `Modo: (•) Ventas ( ) Sell In` · `Desde [MM/AAAA▾]` · `Hasta [MM/AAAA▾]` (+ opción
  manual `dd/mm`) · `Vendedor [TODOS▾]` (off en Sell In) · `[ Generar ]`
- Debajo: el contenido actual de `ReportLts` (splitter tabla | gráficos). En Sell In se
  ocultan los gráficos.
- **Refactor `ReportLts`:** separar `__init__` (arma la UI una vez) de
  `cargar(df_filtrado, con_graficos)` (puebla; llamable N veces).
- La lógica de armado del `df_filtrado` (hoy en `main.reporteLitros` / `main.sellIn`,
  incluida la conversión manual/desplegable de fechas) se mueve a la página.

### MARGEN BENEFICIO

**Hoy:** `main.margenesBeneficio` → `DateRangeDialog` (modal) → `margenBeneficio(...).show()`.

**Propuesta:**
- Barra de filtro arriba: `Desde [dd/mm/aaaa]` · `Hasta [dd/mm/aaaa]` · `Vendedor [TODOS▾]` · `[ Generar ]`.
- Debajo: contenido de `margenBeneficio` (tabla editable + stats + exportar).
- Mismo refactor `__init__` / `cargar(df_filtrado)`.
- `DetalleDialog` (botón "Ver" por fila): **queda modal** (drill-down puntual). Alternativa: panel deslizante.

### E-CHEQUES

**Hoy:** `EcheqWindow(QMainWindow)` con toolbar propia + statusbar propia + `setStyleSheet` propio.

**Propuesta:**
- `QMainWindow` → `PaginaEcheques(PaginaBase)`.
- Toolbar propia (Nuevo / Guardar / Actualizar / Limpiar filtros) → `acciones_barra()`
  (aparecen en la franja de comandos contextual del `AppWindow`).
- `statusBar` propia → la status bar compartida (`app.status`).
- **Carga lazy:** `on_activar()` la primera vez lanza `EcheqLoadThread` con overlay.
  No se carga al iniciar la app.
- `Form` (alta manual) → **queda modal**.
- Su `setStyleSheet` gigante → se funde en el stylesheet global.

### PEDIDOS

**Hoy:** `VentanaProgramarPedido(QDialog)` con 2 paneles + toolbar + `DatabaseSyncManager`
(QTimer cada 2 s + toasts).

**Propuesta:**
- `QDialog` → `PaginaPedidos(PaginaBase)`. Los 2 paneles (Pendientes / Entregados) quedan igual.
- Toolbar (Nuevo pedido / Importar DBF / Forzar actualización / Historial) → `acciones_barra()`.
- `DatabaseSyncManager`:
  - **Siempre activo en background** (notificaciones estés en la pestaña que estés).
    Se instancia en `AppWindow`, no en la página. Intervalo `2 s → 8 s`.
  - Los `NotificationWidget` (toasts) son ventanas frameless flotantes en la esquina →
    **quedan como están** (son overlays).
- `DialogoNuevoPedido`, `VentanaDetallePedido`, `VentanaHistorialCompleto` → **quedan modales**.
- Si PostgreSQL no conecta, la página muestra un aviso en vez de romper.

### OTROS

**Hoy:** cada botón → diálogo (`Fecha` / `MesAnioDialog` / selector de carpeta) → trabajo → `QMessageBox`.

**Propuesta:** un panel con 4 secciones (tarjetas o colapsables), cada una un mini-formulario inline:

| Sección | Campos inline | Acción | Resultado |
|---|---|---|---|
| **Thalamus** | Fecha (`dd` / `dd/mm` / `dd/mm/aaaa`) | `[ Generar ]` | mensaje + "Abrir carpeta" |
| **Ventas Mensuales** | `[ Elegir carpeta ]` (muestra ruta) | `[ Consolidar ]` | archivo `Anexo_6_MES.xlsx` |
| **Informe IIBB** | Mes `[▾]` · Año `[____]` · Jurisdicción `[▾]` | `[ Generar ]` | total inline + `.txt` |
| **Actualizar Precios** | (texto explicativo) | `[ Actualizar MANA + HOREB ]` | barra de progreso inline |

- Los `QMessageBox` de error/confirmación quedan.
- Los diálogos de campos (`Fecha`, `MesAnioDialog`) se inlinean (extraer los widgets,
  tirar el wrapper `QDialog`) o quedan modales en v1 (OTROS es secundario).

---

## Concerns transversales

1. **Estilos.** Hoy hay 4 `setStyleSheet` gigantes con reglas que se pisan
   (`QPushButton`, `QTableWidget`, …). → **un** stylesheet global (`src/ui/estilos.qss`),
   cargado en `AppWindow`. Cleanup real.
2. **`df_ventas`.** Vive en `AppWindow`, se pasa por **referencia** a las páginas que lo
   usan. Bloquear solo esas pestañas mientras carga, no toda la app.
3. **Ciclo de vida.** Páginas armadas una vez (o lazy en el primer `on_activar`).
   Re-generar un informe = `pagina.cargar(nuevo_df)`, **no** reconstruir el widget.
4. **`QMainWindow`→`QWidget` (Echeq) y `QDialog`→`QWidget` (Pedidos).** Auditar
   `self.statusBar()`, `self.addToolBar()`, `self.menuBar()`, `self.setCentralWidget()`,
   `exec_()`, `accept()/reject()`, `closeEvent`.
5. **Tamaño.** La ventana arranca maximizada; se eliminan los `showMaximized()` por módulo.
6. **Atajos.** `Ctrl+1..5` cambian de sección. Recordar última pestaña (opcional).

---

## Reorganización de archivos (propuesta)

```
main.py                       # mínimo: QApplication + AppWindow + exec
src/ui/
├── app_window.py             # QMainWindow: navbar + toolbar comandos + stack + statusbar + carga df_ventas + sync Pedidos
├── registro.py               # PageDef + lista PAGINAS (el orden = el orden del navbar)
├── estilos.qss               # stylesheet global unificado
├── widgets/
│   ├── overlay_carga.py      # overlay "Cargando…" reutilizable
│   └── barra_filtro.py       # barra colapsable de filtro (base para Litros / Margen)
└── paginas/
    ├── base.py               # PaginaBase(QWidget): contrato (on_activar / on_ventas_listas / acciones_barra)
    ├── litros.py             # PaginaLitros  (absorbe ReportLts + filtro inline + Sell In)
    ├── margen.py             # PaginaMargen  (absorbe margenBeneficio + filtro inline)
    ├── echeques.py           # PaginaEcheques (ex EcheqWindow)
    ├── pedidos.py            # PaginaPedidos  (ex VentanaProgramarPedido)
    └── otros.py              # PaginaOtros   (Thalamus / Mensual / IIBB / Precios)
src/controllers/…             # sin cambios (config, dbf_io, ProgressBar, others, diálogos)
src/Views/…                   # se va vaciando; sus clases migran a src/ui/paginas/
main_legacy.py                # copia del main.py viejo (modelo de 9 ventanas), borrada en F3
```

---

## Migración por fases

Cada fase = 1 commit; **la app funciona en cada punto**.

Rama: **`feat/ui-integrada`** (`main` congelado en `checkpoint-pre-ui`). Cada fase = 1 commit.

| Fase | Qué | Esfuerzo |
|---|---|---|
| **F0** | ✅ Checkpoint (`checkpoint-pre-ui` / `f27248a`) + rama `feat/ui-integrada`. | — |
| **F1** | ✅ Cascarón: `AppWindow` (navbar por registro + toolbar comandos + stack + statusbar), `PaginaBase`, 5 placeholders, carga de `df_ventas`, `main_legacy.py`. | bajo |
| **F2a** | ✅ **Litros** (+ Sell In). `ReportLts` refactorizado (`__init__` sin datos + `cargar(df, df_ventas, graficos)`); barra de filtro colapsable inline (`BarraColapsable`) con modo Ventas/Sell In, período MM/AAAA + manual, vendedor. La lógica de `main_legacy.reporteLitros`/`sellIn` vive ahora en `PaginaLitros._generar()`. | medio |
| **F2b** | ✅ **Margen**. `margenBeneficio` refactorizado (`__init__` + `cargar(df)`, catálogos lazy una vez). `PaginaMargen` con barra de filtro inline (Desde/Hasta `dd/mm/aaaa` + vendedor). `DetalleDialog` sigue modal. De paso: `cargar_abmartic` usa `config.DBF_BASE_PATH` (ya no ruta hardcodeada). | medio |
| **F2c** | ✅ **E-Cheques**. `EcheqWindow` pasó de `QMainWindow` a `QWidget` embebible (toolbar → `self.acciones_toolbar` → franja de comandos; statusbar → fila propia al pie; `self.direc` y el guardado → `config.ECHEQ_PATH`). `PaginaEcheques` hace carga lazy en `on_activar`. `main_legacy` monta el widget en un shell `QMainWindow`. | bajo-medio |
| **F2d** | ✅ **Pedidos**. `VentanaProgramarPedido` de `QDialog` a `QWidget` embebible; `sync_manager` opcional (lo crea el `AppWindow`, siempre activo, intervalo 2 s → 8 s). Toolbar → `acciones_toolbar` → franja de comandos. `DialogoNuevoPedido` / `VentanaDetallePedido` / `VentanaHistorialCompleto` siguen modales. | medio |
| **F2e** | ✅ **Otros**. `PaginaOtros` con 4 tarjetas (Thalamus / Ventas Mensuales / IIBB / Actualizar Precios). Campos inline (fecha, mes/año, carpeta). La lógica se portó desde `main_legacy` (`self.df_ventas` → `self.app.df_ventas`). `selectSubsec` (subsegmento de cliente nuevo, Thalamus) sigue modal. | medio |
| **F3** | Pulido: `estilos.qss` unificado, atajos `Ctrl+1..5` (ya en el registro), recordar última pestaña, chequeo "cambios sin guardar" al cerrar, borrar `main_legacy.py` y `src/Views/` vacío. Merge a `main`. | bajo |

---

## Estética visual (rediseño Tailwind, rama `style/litros-tailwind-look`)

El usuario provee prototipos HTML/Tailwind (`prototypeExample/`) sección por sección para
guiar el rediseño visual. Se van integrando de a uno, en ramas separadas de `feat/ui-integrada`.

- **No se migra de librería.** QSS cubre gradientes, `border-radius`, `:hover`/`:checked`; lo único
  que falta (`box-shadow`) se resuelve con `QGraphicsDropShadowEffect` por widget. Migrar a un
  stack web (NiceGUI/pywebview/Flet) implicaría re-cablear QThreads/DuckDB/PostgreSQL por una
  mejora puramente estética — no vale la pena.
- **Nueva dependencia: `qtawesome`** (íconos vectoriales Font Awesome, coloreables por código).
  Reemplaza los PNG fijos del navbar solo para íconos que cambian de color según estado
  (activo/inactivo). `PageDef.icono_fa` en `src/ui/registro.py`; fallback a PNG si no está instalado.
  **Falta agregar a `requirements.txt`** si se crea uno (hoy el proyecto no tiene manifiesto de deps).
  PyInstaller: `--collect-all=qtawesome` en `CompilarEjecutable.py` (bundlea las fuentes .ttf).
- **Paleta**: navbar slate-800/900 con pill azul (`#2563eb`) activo; contenido sobre slate-100;
  tarjetas blancas `border #e2e8f0` + `border-radius 8px` + sombra suave.
- **Widget compartido `src/ui/widgets/tarjeta.py`**: `crear_tarjeta(titulo, extra, icono)` →
  `(frame, cuerpo_layout)` (tarjeta blanca con encabezado + separador) y `aplicar_sombra(w)`.
  Lo usan Litros y E-Cheques; centraliza el look de tarjeta.
- **[x] Litros** — filtros en tarjeta, tabla con badges de color por Proveedor/Premium, KPIs
  "Total Litros"/"Total Premium" como tarjetas con gradiente (antes eran `QLineEdit` de solo lectura),
  panel de análisis y gráfico comparativo en tarjetas separadas.
- **[x] E-Cheques** (rama `style/echeques-tailwind-look`, sobre `style/litros-tailwind-look`) —
  reescritura de `EcheqWindow` con `prototypeEcheq.html`: toolbar de acciones con íconos
  `qtawesome` (Nuevo azul primario + Guardar/Actualizar/Limpiar), tarjeta "Filtros de Búsqueda"
  (grid 2 col, labels a la derecha), tarjeta "Registros de E-Cheques" con badge de conteo +
  footer Total/Promedio/Suma Seleccionada. Reglas genéricas de `QTableWidget`/`QHeaderView`
  agregadas a `estilos.qss` (para secciones sin stylesheet propio).
  - **Rendimiento**: nueva capa `src/controllers/echeq_io.py` — caché por archivo
    (pickle + manifest de firmas). La carga pasó de ~13 s (releer ~400 Excel siempre) a
    ~0,07 s en caliente. `EcheqLoadThread` delega ahí; `EcheqWindow` la corre en background.
  - **Bug de datos corregido**: el swap `Pagador Cuit` ↔ `Pagador Nombre...` era por columna
    (`.any()` + `rename`), y rompía archivos mixtos (`Echeqs_sistema.xlsx`: 461 filas
    swapeadas + 1.070 correctas → el rename daba vuelta las 1.070 buenas). Ahora es **por
    fila**. Ver [Views-Echeq.md](Views-Echeq.md).
- **Pendiente**: Pedidos, Margen, Otros — cada uno espera su propio prototipo del usuario.
- **Bug de paso, corregido**: la columna "Descripción" de la tabla de Litros quedaba colapsada a
  ~20px porque `QHeaderView.ResizeToContents` mide el ancho del *header* (no solo la celda) — con
  headers largos ("Unidades Vendidas") las demás columnas se comían todo el espacio. Se cambió a
  `Interactive` con anchos fijos iniciales, dejando `Stretch` solo en Descripción.

---

## Rollback

- **Volver al modelo viejo (9 ventanas):** `git checkout main` — `main` está congelado en
  `checkpoint-pre-ui` hasta que la UI nueva se apruebe.
- **Volver a una fase intermedia:** `git checkout <hash de la fase>` en la rama.
- **Tirar todo el trabajo de UI:** `git branch -D feat/ui-integrada` (con `main` limpio).
- El tag `checkpoint-pre-ui` no se mueve nunca.
