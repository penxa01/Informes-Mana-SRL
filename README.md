# Sistema de Gestión e Informes — Mana S.R.L.

Aplicación de escritorio para la gestión interna de Mana S.R.L., empresa distribuidora de lubricantes Shell y Valvoline. Permite generar informes de ventas, gestionar e-cheques, programar pedidos y actualizar precios, todo a partir de archivos DBF del sistema de gestión y planillas Excel.

- **Versión:** 1.5.10  
- **Autor:** Juan Ignacio Peña Seva  
- **Empresa:** Mana S.R.L.

---

## Stack tecnológico

| Capa | Tecnología |
|---|---|
| Interfaz de usuario | PyQt5 |
| Procesamiento de datos | Pandas, NumPy |
| Base de datos legacy | DBF (dBASE) vía `dbfread` / `dbf` |
| Base de datos relacional | PostgreSQL (psycopg2) |
| Archivos de entrada/salida | Excel (openpyxl) |
| Empaquetado | PyInstaller → `.exe` |

---

## Requisitos previos

- Python 3.10+
- PostgreSQL corriendo localmente (base de datos `pedidosMana`)
- Acceso a los archivos DBF en `d:/tiempo/vtiempoges/GESTION/`
- Archivos Excel de precios y templates en `d:/tiempo/`

### Dependencias Python (app desktop)

```
PyQt5
pandas
numpy
openpyxl
dbfread
dbf
psycopg2-binary
```

Instalación:

```bash
pip install PyQt5 pandas numpy openpyxl dbfread dbf psycopg2-binary
```

---

## Configuración

Copiar `.env.example` a `.env` y completar los valores según el entorno local:

```bash
cp .env.example .env
```

Variables principales:

```env
# PostgreSQL
DB_HOST=localhost
DB_PASSWORD=tu_password

# Rutas de datos
DBF_BASE_PATH=d:/tiempo/vtiempoges/GESTION/MANA2014
EXCEL_THALAMUS_PATH=d:/tiempo/Thalamus
EXCEL_PRECIOS_PATH=d:/tiempo/Lista de precios
OUTPUT_PATH=C:/tempdgr
```

> **Nota:** El `.env` nunca debe commitearse. Está excluido por `.gitignore`.

---

## Ejecutar la aplicación

```bash
python main.py
```

Al iniciar, la app carga en segundo plano el historial de ventas desde `fachist.DBF`. Los botones se habilitan una vez finalizada la carga.

---

## Módulos

### 1. Thalamus

Genera el archivo `Template_VENTA MANA {dd-mm}.xlsx` para el reporte diario de ventas hacia Thalamus (Shell).

- Selecciona una fecha mediante diálogo.
- Filtra facturas (`FC`), notas de crédito (`NC`) y factura electrónica (`FE`) del día seleccionado.
- Reemplaza códigos internos por el código de proveedor (`ARTIPROV`) cuando existe.
- Agrega precio s/IVA desde la lista de precios Excel.
- Verifica y actualiza automáticamente el archivo `Template_CLIENTE MANA.xlsx` si hay clientes nuevos (requiere seleccionar subsegmento manualmente).

### 2. Informe Litros

Genera un reporte de volumen vendido en litros para un rango de fechas y vendedor (opcional).

- Filtra por tipo de comprobante: `FC`, `NC`, `ND`, `FE`, `CR`.
- Muestra gráficos de evolución y tabla detallada por producto.
- Exporta a Excel.

### 3. Sell In

Reporte de compras (recepciones de mercadería) filtradas por `CODMOV = 'RI'` para un rango de fechas.

- Usa el mismo componente visual que Informe Litros pero sin gráficos.

### 4. Ventas Mensuales

Consolida los archivos `Template_VENTA MANA *.xlsx` de una carpeta en un único `Anexo_6_MES.xlsx`.

- El usuario selecciona la carpeta con los reportes diarios del mes.
- Cruza cada código de producto con `LITROS SHELL.xlsx` para obtener familia y litros equivalentes.
- Ordena por fecha y exporta.

### 5. Informe IIBB (Ingresos Brutos)

Genera el archivo de retenciones de Ingresos Brutos en formato `.txt` separado por tabulaciones, listo para importar en el sistema de ARCA/AFIP.

- Filtra `ivatemp.DBF` por mes/año y por puntos de venta `00002` y `00003`.
- Calcula la base imponible (83.33%) y el excedente (16.67%) de la retención.
- Guarda en `C:/tempdgr/salib {mes}-{año}.txt`.

### 6. E-Cheques

Gestión de cheques electrónicos registrados en el DBF correspondiente.

- Carga datos en hilo separado con barra de progreso.
- Abre ventana dedicada `EcheqWindow` con tabla y formulario.

### 7. Pedidos

Módulo para programar y gestionar pedidos de clientes.

- `VentanaProgramarPedido` conecta contra PostgreSQL (`pedidosMana`).
- Permite crear, editar y consultar pedidos por cliente y producto.

### 8. Margen Beneficio

Análisis de margen de ganancia para un rango de fechas y vendedor (opcional).

- Filtra comprobantes con modelo que empieza en `L` (lubricantes).
- Abre `margenBeneficio` con tabla y gráficos de rentabilidad.

### 9. Actualizar Precios

Actualiza los precios en los archivos `abmartic.DBF` de MANA2014 y HOREB25 a partir de las listas Excel.

- Lee `Lista de precios Mana.xlsm` (hoja *Lista De Precios*) y `Lista Valvoline.xlsx`.
- Escribe `PRECIO1` (s/IVA), `PRECIO7` (Gerardo), `PRECIO8` (Ecominera), `PRECIO9` (Luis Richarte).
- Corre en hilo separado con barra de progreso integrada.

---

## Flujo de datos general

```
fachist.DBF  ──► Pandas DataFrame (carga al inicio, hilo separado)
                       │
          ┌────────────┼────────────────────────┐
          ▼            ▼                        ▼
     Thalamus    Litros / Sell In          IIBB / Margen
          │            │                        │
          ▼            ▼                        ▼
    Excel export   Excel export           .txt export
```

```
abmartic.DBF  ◄──  Lista de precios Mana.xlsm
                   Lista Valvoline.xlsx
```

---

## Estructura del proyecto

```
App PyQt5 y Pandas/
├── main.py                        # Punto de entrada, ventana principal
├── .env                           # Variables de entorno (no commitear)
├── .gitignore
├── CompilarEjecutable.py          # Script de compilación con PyInstaller
├── ManaInformes.spec              # Spec de PyInstaller
│
├── src/
│   ├── controllers/
│   │   ├── controllerBD.py        # Conexión PostgreSQL + importación desde DBF
│   │   ├── ProgressBar.py         # Hilos de carga (ventas, e-cheques, precios)
│   │   ├── others.py              # Helpers: búsqueda de artículos, export Excel
│   │   ├── FechaDBF.py            # Diálogo selector de fecha
│   │   ├── RangeFechas.py         # Diálogo rango de fechas (con vendedor)
│   │   ├── rangeMY.py             # Diálogo rango mes/año (con vendedor)
│   │   └── MesAno.py              # Diálogo selector mes/año
│   │
│   ├── Views/
│   │   ├── Beneficio/             # Módulo Margen Beneficio
│   │   ├── Echeq/                 # Módulo E-Cheques
│   │   ├── Litros/                # Módulo Informe Litros y Sell In
│   │   └── Pedidos/               # Módulo Pedidos (desktop)
│   │
│   └── Distribuidora/             # Íconos y logos
```

---

## Compilar ejecutable (.exe)

```bash
python CompilarEjecutable.py
```

Genera `dist/ManaInformes.exe` (sin consola, con todos los assets embebidos).

Requiere PyInstaller instalado:

```bash
pip install pyinstaller
```

---

## Fuentes de datos externas requeridas

| Archivo / Ruta | Uso |
|---|---|
| `d:/tiempo/vtiempoges/GESTION/MANA2014/fachist.DBF` | Historial de ventas (fuente principal) |
| `d:/tiempo/vtiempoges/GESTION/MANA2014/abmartic.DBF` | Artículos Mana |
| `d:/tiempo/vtiempoges/GESTION/HOREB25/abmartic.DBF` | Artículos Horeb |
| `d:/tiempo/vtiempoges/GESTION/MANA2014/ctaclien.DBF` | Clientes |
| `d:/tiempo/vtiempoges/GESTION/MANA2014/ivatemp.DBF` | Retenciones IIBB |
| `d:/tiempo/vtiempoges/GESTION/MANA2014/stock.DBF` | Stock |
| `d:/tiempo/Thalamus/Template_VENTA MANA.xlsx` | Template base Thalamus |
| `d:/tiempo/Thalamus/Template_CLIENTE MANA.xlsx` | Registro de clientes Thalamus |
| `d:/tiempo/Thalamus/LITROS SHELL.xlsx` | Conversión unidades → litros |
| `d:/tiempo/Lista de precios/Lista de precios Mana.xlsm` | Lista de precios Shell |
| `d:/tiempo/Lista de precios/Lista Valvoline.xlsx` | Lista de precios Valvoline |
| `C:/tempdgr/` | Carpeta de salida para informes IIBB |
