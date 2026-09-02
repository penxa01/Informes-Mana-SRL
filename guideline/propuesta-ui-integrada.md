# Propuesta — UI integrada (ventana única, estilo Office)

> **Estado: PLANTEO. No implementado.** Documento de trabajo para pulir antes de proceder.

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
├── QToolBar (navbar)  ── 5 QToolButton exclusivos (QActionGroup, checkables)
├── QStackedWidget (central)
│     ├── PaginaLitros(QWidget)     idx 0   (incluye Sell In)
│     ├── PaginaPedidos(QWidget)    idx 1
│     ├── PaginaEcheques(QWidget)   idx 2
│     ├── PaginaMargen(QWidget)     idx 3
│     └── PaginaOtros(QWidget)      idx 4
└── QStatusBar (compartida)
```

- Botón de navbar `.toggled` → `stack.setCurrentIndex(i)` + `pagina.on_activar()`.
- **Contrato de página** (cada `PaginaXxx` implementa lo que necesite):
  - `__init__(self, app)` — arma la UI **una sola vez**. `app` da acceso a `df_ventas`,
    status bar, `config`, etc.
  - `on_activar(self)` — al hacerse visible la pestaña (carga lazy / refresh). Opcional.
  - `on_ventas_listas(self, df)` — cuando `LoadDataThread` termina. Opcional.
- `df_ventas` se carga al inicio (igual que hoy, `ProgressBar.LoadDataThread` con caché
  Parquet) y vive en `AppWindow.df_ventas`. Solo Litros / Margen / Otros→Thalamus
  dependen de él → solo esas páginas muestran overlay "Cargando ventas…"; Pedidos y
  E-Cheques arrancan usables de una.

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
- `QMainWindow` → `QWidget`.
- Toolbar (Nuevo / Guardar / Actualizar / Limpiar filtros) → **fila de botones** arriba de la página.
- `statusBar` propia → labels en la página o la status bar compartida.
- **Carga lazy:** al abrir la pestaña por primera vez (`on_activar`), lanza
  `EcheqLoadThread` con overlay. No se carga al iniciar la app.
- `Form` (alta manual) → **queda modal**.
- Su `setStyleSheet` gigante → se funde en el stylesheet global.

### PEDIDOS

**Hoy:** `VentanaProgramarPedido(QDialog)` con 2 paneles + toolbar + `DatabaseSyncManager`
(QTimer cada 2 s + toasts).

**Propuesta:**
- `QDialog` → `QWidget`. Los 2 paneles (Pendientes / Entregados) quedan igual.
- Toolbar (Nuevo pedido / Importar DBF / Forzar actualización / Historial) → fila de botones arriba.
- `DatabaseSyncManager`:
  - **A decidir:** polling siempre (notificaciones en background estés donde estés) vs.
    solo con la pestaña activa. Recomendado: **siempre**, subiendo el intervalo `2 s → 8-10 s`.
  - Los `NotificationWidget` (toasts) son ventanas frameless flotantes en la esquina →
    **quedan como están** (son overlays, no parte del layout).
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
main.py                       # ~15 líneas: QApplication + AppWindow + exec
src/ui/
├── app_window.py             # QMainWindow + navbar + stack + statusbar + carga df_ventas
├── estilos.qss               # stylesheet global unificado
└── paginas/
    ├── litros.py             # PaginaLitros  (absorbe ReportLts + filtro inline + Sell In)
    ├── margen.py             # PaginaMargen  (absorbe margenBeneficio + filtro inline)
    ├── echeques.py           # PaginaEcheques (ex EcheqWindow)
    ├── pedidos.py            # PaginaPedidos  (ex VentanaProgramarPedido)
    └── otros.py              # PaginaOtros   (Thalamus / Mensual / IIBB / Precios)
src/controllers/…             # sin cambios (config, dbf_io, ProgressBar, others, diálogos)
```

`src/Views/` se va vaciando a medida que sus clases migran a `src/ui/paginas/`.

---

## Migración por fases

Cada fase = 1 commit; **la app funciona en cada punto**.

| Fase | Qué | Esfuerzo |
|---|---|---|
| **F0** | Checkpoint del estado actual (este commit). | — |
| **F1** | Cascarón: `AppWindow` con navbar + stack + 5 páginas placeholder + carga de `df_ventas`. Abre, cambia de pestaña, nada más anda. Se conserva `main.py` viejo como `main_legacy.py`. | bajo |
| **F2a** | **Litros** (+ Sell In). La más valiosa; ejercita los patrones difíciles (df_ventas, gráficos, re-generar). | medio |
| **F2b** | **Margen** (mismo patrón que Litros). | medio |
| **F2c** | **E-Cheques** (`QMainWindow`→`QWidget`, carga lazy). | bajo-medio |
| **F2d** | **Pedidos** (`QDialog`→`QWidget`, alcance del timer, 3 sub-diálogos, PostgreSQL). | medio |
| **F2e** | **Otros** (4 mini-forms, inline de campos). | medio |
| **F3** | Pulido: stylesheet unificado, status bar compartida, atajos, borrar `main_legacy.py` y `src/Views` vacío. | bajo |

---

## Preguntas para cerrar el planteo (antes de F1)

1. **Modales de drill-down / creación** (`DetalleDialog`, `DialogoNuevoPedido`,
   `VentanaDetallePedido`, `VentanaHistorialCompleto`, `Form` de alta de e-cheque):
   ¿está OK que queden como **modales**? (Leo el pedido "no ventanas nuevas por
   funcionalidad" como las 5 secciones, no cada popup.)
2. **Navbar:** ¿**pestañas simples** ahora (tipo navegador / VS Code) y dejamos una
   franja de comandos contextual estilo ribbon para después? ¿O ribbon completo desde el arranque?
3. **Pedidos:** el polling de notificaciones, ¿**siempre activo** en background
   (subiendo a 8-10 s) o solo con la pestaña abierta?
4. ¿OK reorganizar a `src/ui/` como arriba?
5. **Filtro de Litros / Margen:** ¿barra arriba (colapsable) o panel a la izquierda?
   (Recomiendo barra arriba.)
