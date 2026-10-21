# Build para Windows de 32 bits

## Por qué hace falta

El `.exe` que genera PyInstaller tiene **la misma arquitectura que el Python que lo compila**. Compilado con
Python de 64 bits (lo normal) **no arranca en un Windows de 32 bits**, esté donde esté el archivo (copiado
local o ejecutado desde `Z:`: se ejecuta siempre en la PC de quien lo abre). El síntoma es un cartel de
Windows tipo "la versión de este archivo no es compatible con la versión de Windows… busque una versión
compatible". No es un error del programa.

**Antes de compilar en 32 bits, revisar si hace falta.** En la PC de destino:

```
wmic cpu get AddressWidth
```

- **64** → el procesador es de 64 bits y alcanza con **reinstalar Windows 10 de 64 bits**: sirve el build
  de siempre, sin mantener dos versiones (y se aprovecha toda la RAM; en 32 bits el techo es 4 GB).
- **32** → el procesador es de 32 bits: compilar este build, o usar Escritorio Remoto (`mstsc`) contra una PC
  de 64 bits (el host debe ser Windows Pro y admite una sola sesión a la vez).

## Cómo compilar

Hace falta un **Python de 32 bits** (se instala al lado del de 64; no lo pisa) en la PC donde se compila:

```
py -3.9-32 -m venv venv32
venv32\Scripts\activate
pip install -r requirements-win32.txt
python CompilarEjecutable.py
```

Al arrancar, el script imprime los bits del Python (`Python 3.9.x de 32 bits -> el .exe será de 32 bits`) y si
DuckDB está o no. Verificar ahí antes de esperar a que termine. **No compilar desde `ManaInformes.spec`**: se
generó con DuckDB y se regenera cada vez que corre `CompilarEjecutable.py`.

## Qué cambia respecto del build de 64 bits

Probado en un entorno con las **mismas versiones** (pandas 2.0.3, numpy 1.26.4, matplotlib 3.7.5, **sin DuckDB**)
corriendo toda la batería de `tests/verificar_*.py` y con datos reales:

| | 64 bits | 32 bits |
|---|---|---|
| pandas / matplotlib | 2.3.x / 3.9.x | **2.0.3 / 3.7.5** (las últimas con versión de 32 bits) |
| DuckDB | sí | **no existe** (solo 0.9.2, sin la extensión `spatial`) |
| Lectura de DBF | DuckDB + caché Parquet | `dbfread` (automático: `dbf_io` ya tiene el plan B) |
| Arranque (carga de ventas) | ~0,6 s con caché | **~15–30 s en cada arranque** (mientras carga, las demás pestañas se pueden usar) |
| Cuentas Corrientes / Informe IIBB | rápido | ~10 s / ~20–30 s |
| E-Cheques, Pedidos, Visitas, Margen, Litros | igual | igual (mismos resultados) |
| Memoria | — | pico ~290 MB al cargar todo (el tope de 32 bits es ~2 GB: sin riesgo) |

Los tests que dependen de DuckDB o de su caché Parquet (`verificar_dbf_io.py` y la comprobación "2da carga < 3 s"
de `verificar_integracion_dbf.py`) **fallan a propósito** en este entorno: miden justamente lo que no existe.

## Trampas

- **`xlrd` es obligatorio**: 287 de los 289 archivos de E-Cheques son `.xls`. Si falta, `echeq_io` ignora esos
  archivos **en silencio** (sin error) y la pantalla muestra menos cheques. Está en `requirements-win32.txt` y
  `CompilarEjecutable.py` lo declara como `--hidden-import`.
- pandas 2.0.3 **exige numpy 1.x**: no instalar numpy 2.
- La caché de E-Cheques (`C:\tempdgr\cache_dbf\echeqs.pkl`) es un pickle de pandas: una versión más nueva lee
  el de una más vieja, no al revés. Si una PC con pandas viejo comparte caché con otra con pandas nuevo, se
  releerá de más (no es fatal).
- Mejora posible (no implementada): una caché `pickle` de los DBF dentro de `dbf_io` bajaría el arranque de
  32 bits de ~15–30 s a ~1 s, sin depender de DuckDB.
