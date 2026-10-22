# Ventanas emergentes que se adaptan a la pantalla — `src/ui/ventanas.py`

## El problema

Varios diálogos traen tamaños pensados para un monitor grande y en pantallas chicas (notebook 1366×768 —unos
728 px útiles—, 1280×720, 1024×768) se salían: Reclamos `1020×760`, Detalle de Margen `1240×680` (y su contenido
pedía aún más ancho), Detalle de Pedido `1040×720`. Con la barra de título y los bordes el alto real es mayor
que el declarado.

## La solución: una sola, central

`ventanas.instalar(app)` (en `main.py`, una vez) instala un filtro de eventos que corrige **toda** `QDialog` la
primera vez que se muestra, incluidas las que se agreguen en el futuro. No hay que tocar cada ventana ni acordarse de
llamar nada.

Qué hace (`ajustar_ventana`):

1. **Achica** el tamaño y los mínimos hasta que entre, descontando un marco (barra de título + bordes, ≥ 16×40 px) y
   dejando un 4 % de aire (`FRACCION = 0.96`) contra la barra de tareas. Lo que ya entra no se toca.
2. Si el **contenido** en sí no entra (su `minimumSizeHint` supera el área útil) lo envuelve en un `QScrollArea`
   conservando el layout, grillas incluidas (`hacer_desplazable`: Qt permite pasarle el layout de un widget a otro).
3. La **centra** sobre su ventana madre (o la activa) y la mantiene dentro del área útil.
4. Usa el **monitor donde está el sistema** (el de la madre / ventana activa), no el principal.

Qué **no** toca: avisos tipo toast (`Qt.Tool`/sin marco), menús y popups, ventanas maximizadas, los cuadros nativos
(`QMessageBox`, `QFileDialog`, `QInputDialog`...) y las ventanas que ya se ajustaron (una sola vez: no pisa lo que el
usuario haga después).

Para ventanas principales: `ventanas.limitar_minimo(win, ancho, alto)` (lo usa `AppWindow`, cuyo mínimo ya no supera la
pantalla). Los avisos de Pedidos (`NotificationWidget`) se posicionan con `ventanas.area_disponible`.

## Trampa que costó encontrar

`windowFlags() & Qt.Tool` da **verdadero para cualquier `QDialog`**: los bits de `Qt.Dialog` están contenidos en los de
`Qt.Tool`. Hay que comparar el **tipo** (`win.windowType() == Qt.Tool`), no los bits.

## Probado

`tests/verificar_ventanas.py`: geometría pura (monitores de 1366×768, 1280×720, 1024×768, 800×600, grandes y a la
izquierda del principal con coordenadas negativas) y con Qt (achicar, tamaño fijo, centrar sobre la madre, scroll para
listas y grillas, lo que no hay que tocar). Además se abrieron las **12 ventanas reales** del sistema en esos 4 tamaños:
ninguna se sale.

El render sin pantalla (`QT_QPA_PLATFORM=offscreen`) usa una fuente de reserva más ancha: los `minimumSizeHint` que ahí
dan enormes (p. ej. 1776 px en el Detalle de Margen, por su barra de totales) sobreestiman lo real. Por eso el scroll es
una red de seguridad y no se rediseñó esa barra sin poder verla. `QMessageBox.show()` además se cae en esa plataforma
(sin este módulo también): no se prueba mostrándolo.
