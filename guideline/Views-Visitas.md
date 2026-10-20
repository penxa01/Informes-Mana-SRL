# Views / Visitas — `src/Views/Visitas/`

Sección **Visitas**: registro de las visitas que cargan los vendedores por un formulario de Google.
Pestaña simple: filtros (que se pueden ocultar) y una tabla.

| Archivo | Rol |
|---|---|
| `src/controllers/visitas_io.py` | Lógica **pura** (sin Qt): lectura de la hoja, limpieza, filtros, resumen, atajos de fecha |
| `src/Views/Visitas/VisitasWindow.py` | Ventana: filtros plegables, tabla, resumen y botón de actualizar |
| `src/ui/paginas/visitas.py` | `PaginaVisitas` (lee la planilla al abrir la pestaña; relee si pasaron > 2 min) |
| `src/ui/widgets/item_ordenable.py` | Celda que ordena por una clave tipada (fecha real, no el texto) |

Test: `tests/verificar_visitas.py`. Atajo: `Ctrl+6` (Otros pasó a `Ctrl+7`).

---

## De dónde salen los datos

**Una sola hoja de Google Sheets, leída en vivo**: la hoja `Respuestas de formulario 1` (donde cae el
formulario) de la planilla `VISITAS_SHEET_ID` (`config.py`; override por `.env`: `VISITAS_SHEET_ID`,
`VISITAS_HOJA`). Decisión del usuario:

- **No se descarga ningún archivo ni se guarda copia** (ni caché en disco): cada lectura va a Google
  y vive solo en memoria. Sin internet no hay datos nuevos; si ya había leído, la pantalla conserva lo
  que tenía y avisa.
- **No se unifican las hojas mensuales** (`Visitas Agosto/Septiembre/Octubre 2026`): el usuario las
  integra a mano en la hoja del formulario.
- La planilla tiene que seguir compartida como **"cualquier persona con el enlace"**. Si se hace privada
  la app lo explica (Google responde con una página de login, no con datos).

Se lee por el endpoint `gviz` en JSON (`.../gviz/tq?tqx=out:json&headers=1&sheet=<hoja>`), ~7 KB, ~0,6 s.
Quirks reales de ese endpoint (cubiertos por el test):

- Las **fechas** llegan como `Date(2026,9,15,9,21,17)` con el **mes contado desde 0** (9 = octubre).
- Si el **nombre de la hoja no existe**, Google devuelve igual **la primera hoja**, sin avisar. Por eso
  se validan las columnas (Fecha, Vendedor, Cliente): una hoja equivocada da un error claro.

## Formato de los datos

Columnas de la hoja del formulario: `Marca temporal`, `Vendedor`, `Nombre de Cliente`, `Cliente nuevo`,
`Compro`, `Observacion` (las hojas mensuales las llaman `FECHA`, `VENDEDOR`, `NOMBRE CLIENTE`... y se
aceptan los dos juegos de nombres). Se normalizan a `FECHA, VENDEDOR, CLIENTE, NUEVO, COMPRO, OBSERVACION`.

Limpieza (datos cargados a mano): espacios de más fuera; `Si`/`Sí` → `Sí`; `Cliente nuevo` vacío queda
vacío (no se inventa); filas sin fecha o con fecha ilegible, fuera; **copias exactas** de una fila
(un bloque pegado dos veces, ya pasó en la hoja de Septiembre) se descartan y se cuenta cuántas; las
**visitas repetidas al mismo cliente el mismo día a distinta hora son legítimas** y se conservan.

Los **clientes son texto libre**: no están ligados a CTACLIEN (hay variantes: `Giantino`/`Gigantino`),
por eso el filtro es "contiene", sin acentos ni mayúsculas.

## Pantalla

- **Filtros** (tarjeta plegable; el encabezado resume lo aplicado — `Hoy · Jose Banco · cliente «gil»` —,
  la cantidad de visitas y el botón de actualizar, así que sigue a la vista con el panel oculto): cliente,
  vendedor, **desde / hasta** y atajos **Hoy · Ayer · 7 días · Mes**. Un rango al revés se corrige solo.
- Por defecto muestra **hoy**; si hoy no hay visitas, el último día con datos.
- **Tabla**: Fecha, Hora, Vendedor, Cliente, Nuevo, Compró, Observación; ordenable por cualquier columna
  (por la clave real, no el texto); más reciente arriba.
- **Pie**: `N visitas · M compraron (x%) · K clientes nuevos · J clientes distintos` y de dónde/cuándo
  se leyó (`Planilla de Google · leída a las 10:23`). Sin resultados sugiere la última fecha con visitas.
- Errores: relectura **automática** fallida → solo un aviso en el pie; **manual** o primera lectura →
  cartel con el motivo.
