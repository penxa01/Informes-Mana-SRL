# Inicio (panel de control) en el escritorio

> **Actualización 06/11/2026:** la sección se llama **Inicio** (`Ctrl+1`, primera del navbar) y absorbió a **Litros** y
> **Cuentas Corrientes**, que ya no existen como secciones. Tiene tres pestañas:
> - **General** y **Cobranzas**: lo de abajo (datos del servidor).
> - **Desglose de litros** (`ui/paginas/panel_litros.py`, `VistaLitros`): el informe de la vieja sección Litros con sus
>   filtros (período, vendedor, Ventas / Sell In, proveedor, premium) y el comparativo con el año anterior. Necesita
>   `df_ventas`: Inicio lo recibe por `recibe_ventas` y solo esa pestaña muestra «Cargando…».
> - **Reclamos**: el botón ámbar de Cobranzas (y «Reclamar» en el detalle de un cliente) abre el modal de siempre vía
>   `ui/reclamos_acceso.py` (`AccesoReclamos`: carga ctacorr/ctaclien al primer uso y los reusa 10 min). La alerta de la
>   barra de estado lleva a Inicio → Cobranzas. Se borró `CuentasCorrientesWindow` / `DetalleCuenta` (la grilla por mora,
>   los filtros de saldo mínimo y antigüedad y el KPI neto ya no tienen pantalla; la lógica sigue en `cuentas_corrientes_io`).
> - Sin título «Inicio»: la fila de pestañas lleva a la derecha «Datos de las…» y el ↻. El Desglose de litros **no tiene panel de
>   gráficos** (`ReportLts(graficos=False)`; el código de gráficos sigue en `LitrosDBF.py` sin usarse en Inicio).
> - Atajos: Inicio `Ctrl+1`, Pedidos 2, E-Cheques 3, Margen 4, Visitas 5, Otros 6.
> - Estética común: fondo `#f4f6fb` (`QWidget#pagina`), azul de marca `#2640dc`, `TarjetaPintada` (`widgets/tarjeta.py`) para
>   las tarjetas de todas las secciones, encabezados de tabla claros y Otros armado con tarjetas.

Réplica del panel de la app móvil (`movil/pwa/js/panel*.js`, `cobranzas.js`, `graficos.js`) como una sección más del
navbar. Misma información, mismo orden, mismo aspecto (tarjetas, gráficos con animación de entrada, chips).

## Decisiones

- **Los datos NO se recalculan en el escritorio.** El proceso del servidor (`movil/panel/worker.py`, tarea `ManaPanelMovil`)
  ya deja todo calculado en Postgres (`panel_resumen` id=1 = general; `panel_vendedor` vendedor_id=0 = cobranzas de la
  empresa). El escritorio solo **lee** esas dos filas con la conexión de Pedidos (`reclamos_db.conectar()`). Resultado:
  las cifras son idénticas a las del celular (paridad por construcción) y no hay una segunda copia de la lógica.
- `movil/` queda fuera del `.exe`: el escritorio **no importa** `movil.panel`. Las dos consultas SELECT se repiten en
  `src/controllers/panel_io.py` (son de una línea cada una).
- Vista de admin (toda la empresa). El escritorio no tiene login por rol: es la PC de la oficina.
- Gráficos con `QPainter` (sin matplotlib): permiten la animación de entrada y el tooltip por barra como en el celular.
- Lógica pura (formatos, filtro Shell/Valvoline/Otros, `vista_litros`, deltas) en `src/controllers/panel_vista.py`, sin
  Qt, con test propio.

## Fases

| # | Qué | Archivos |
|---|-----|----------|
| F1 | Lectura de datos + lógica de vista (con tests) | `controllers/panel_io.py`, `controllers/panel_vista.py`, `tests/verificar_panel_vista.py` |
| F2 | Gráficos animados: barras apiladas, anillo, barra de proporciones | `ui/widgets/graficos.py` |
| F3 | Página Panel → General: filtro de productos, Litros, Premium, Recaudado (+ cómo se cobró) | `ui/paginas/panel.py` |
| F4 | Pestaña Cobranzas: cartera, cobrado por mes, consulta de clientes y detalle de facturas | `ui/paginas/panel_cobranzas.py` |
| F5 | Registro en el navbar (`Ctrl+7`, Otros pasa a `Ctrl+8`), QSS, verificación visual | `ui/registro.py`, `ui/estilos.qss` |

## Estado (06/11/2026)

F1 a F5 hechas. Tests: `tests/verificar_panel_vista.py` (lógica, sin Qt), `tests/verificar_panel_ui.py` (página con datos
falsos, offscreen). Verificado contra la base real: la página arma General y Cobranzas con los números del servidor.

## Cosas no obvias

- **Slots con `lambda` en señales de una animación hija = cierre de la app.** Una `QVariantAnimation` hija de un widget puede
  emitir al destruirse el padre; un `lambda` no se desconecta y llama a un objeto ya liberado (access violation). Usar
  siempre métodos del propio QObject como slot (`CifraAnimada._al_cambiar`, señales del hilo en `PaginaPanel`).
- Qt no redondea una esquina si `border-radius` supera la mitad del alto: los chips usan `min-height` fijo y un radio menor.
- Un `setStyleSheet("background: transparent;")` sin selector en un contenedor pisa los estilos del `.qss` de todos sus hijos.
- La sombra de `TarjetaPanel` se pinta a mano (no `QGraphicsDropShadowEffect`) para no re-renderizar la tarjeta en cada
  cuadro de las animaciones de adentro.
- La flechita de los `QComboBox` sale de un PNG que `recursos.leer_estilos()` genera en la carpeta temporal (`@CHEVRON@`).

## Comportamiento

- Carga en un hilo; refresco automático cada 2 min y botón ↻ (igual que el celular). Si falla, se siguen mostrando los
  últimos datos y se avisa.
- Avisos: «Datos de las HH:MM», servidor sin latido hace más de 15 min, último cálculo con error.
- Las tarjetas solo se vuelven a armar si los datos cambiaron (así los gráficos animan al aparecer, no en cada refresco).
