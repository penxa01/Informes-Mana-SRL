# Mana Pedidos móvil

Los vendedores cargan pedidos desde el celular, en la calle, y esos pedidos aparecen solos en el sistema de
escritorio. Solo **crea pedidos** (nada de cuentas corrientes ni de consultar pedidos ajenos).

```
celular (PWA instalada) --HTTPS por Tailscale--> API FastAPI (127.0.0.1:8000) --> PostgreSQL pedidosMana
```

- **PWA** (`pwa/`): HTML/CSS/JS puro, sin compilar. La sirve la propia API (mismo origen, sin CORS). Funciona
  sin conexión: el catálogo vive en el celular (IndexedDB) y los pedidos se guardan ahí hasta enviarse.
- **API** (`api/`): FastAPI. `POST /auth/login`, `GET /catalogo`, `POST /pedidos`, `GET /health`.
- **Fuera del `.exe`**: esta carpeta nunca entra al compilable (`CompilarEjecutable.py` solo empaqueta `main.py` y
  `src/`). Tiene su propio `requirements.txt` y no importa nada de `src/` (arrastraría PyQt).
- Diseño, decisiones y bitácora de cada tarea: `guideline/Movil.md`.

## Carpetas

| Ruta | Qué es |
|---|---|
| `run.py` | Lanzador: lee `.env`, escribe logs, arranca la API. Lo usa la tarea de Windows y sirve a mano |
| `api/` | La API (`app.py`, `auth.py`, `deps.py`, `db.py`, `pedidos.py`, `routers/`) |
| `pwa/` | La app del celular (`index.html`, `js/`, `css/`, `sw.js`, `manifest.webmanifest`) |
| `sql/001_movil.sql`, `migraciones.py` | Cambios a la base (aditivos) y rol `movil_api` |
| `deploy/` | Instalar / desinstalar la tarea de Windows |
| `tests/` | `verificar_*.py` |
| `env.example` | Modelo del `.env` |

## Configuración (`movil/.env`)

Copiar `env.example` a `.env` (no se versiona: tiene claves). Formato `CLAVE=valor`, sin comentarios a mitad de línea.

| Variable | Valor |
|---|---|
| `PEDIDOS_DB_HOST` | Servidor de la base (`localhost` si corre en el servidor) |
| `PEDIDOS_DB_NAME` | `pedidosMana` |
| `PEDIDOS_DB_USER` | `movil_api` (rol de permisos mínimos, **no** `postgres`) |
| `PEDIDOS_DB_PASSWORD` | Clave del rol `movil_api` |
| `MOVIL_JWT_SECRET` | Cadena larga al azar para firmar sesiones. Si se cambia, todos tienen que volver a loguearse |
| `MOVIL_HOST` / `MOVIL_PORT` | Opcionales: `127.0.0.1` / `8000` |

`run.py` carga el `.env` **solo dentro de su proceso**: así `PEDIDOS_DB_*` no se pisa con la app de escritorio, que usa
los mismos nombres. Por defecto escucha solo en `127.0.0.1`; la expone por HTTPS `tailscale serve`.

## Arranque manual (desarrollo)

```bash
pip install -r movil/requirements.txt
python movil/run.py
```

Abrir `http://127.0.0.1:8000/`. Logs en `movil/logs/api.log`.

## Tests

Desde la raíz del repo: `python movil/tests/verificar_<algo>.py` (cada uno termina en `TODO OK` o lista las fallas).
Los que tocan la base real corren dentro de una transacción que se revierte; son de **desarrollo** (usan el entorno
completo del repo), no se corren en el servidor.

## Despliegue en el servidor (una sola vez)

La carpeta se despliega **dentro de la carpeta del sistema de escritorio** (la que los demás ven como `Z:\AppInforme`).
Ojo: una tarea de Windows no ve las unidades de red (`Z:`), por eso el instalador se corre desde la **ruta local** del
servidor (la carpeta que se comparte como `Z:`) y se niega a seguir si detecta una unidad de red.

1. **Copiar** `movil\` a esa carpeta (sin `tests`, `logs` ni `__pycache__`):
   ```
   robocopy movil Z:\AppInforme\movil /E /XD __pycache__ logs tests /XF .env
   ```
2. **Crear `movil\.env` en el servidor** (a partir de `env.example`, con `PEDIDOS_DB_HOST=localhost` y la clave del rol
   `movil_api`). No viaja con el `robocopy` a propósito.
3. **Python y librerías en el servidor** (con el mismo Python que va a usar la tarea):
   ```
   python -m pip install -r movil\requirements.txt
   ```
   `bcrypt` está fijado en `3.2.2`: las versiones 4.x/5.x usan Rust y no cargan en estas PCs.
4. **Tailscale en el servidor**: instalarlo, loguearse con la misma cuenta y tener activado "HTTPS Certificates"
   (admin console de Tailscale > DNS).
5. **Instalar la tarea** (PowerShell **como administrador**, desde la ruta local del servidor):
   ```
   powershell -ExecutionPolicy Bypass -File <ruta local>\movil\deploy\instalar_servicio.ps1 -ConfigurarTailscale
   ```
   Revisa los requisitos, restringe `movil\.env` a Administradores y SYSTEM (la carpeta se comparte con la red de la
   oficina), registra la tarea `ManaPedidosMovil` (arranca al encender, corre como SYSTEM, se reinicia sola si se cae),
   la arranca y comprueba `/health`. Con `-SoloVerificar` solo revisa; con `-Python <ruta>` se indica el intérprete.
6. **Probar el reinicio**: reiniciar el servidor y, sin iniciar sesión ni abrir nada, abrir
   `https://<nombre-del-servidor>.<tu-tailnet>.ts.net/health` desde un celular: tiene que dar `{"api":"ok","db":"ok"}`.

## Operación

- **Logs**: `movil\logs\api.log` (rota solo, 1 MB x 5).
- **Estado**: `Get-ScheduledTaskInfo -TaskName ManaPedidosMovil` (mirar `LastTaskResult`).
- **Reiniciar la API** (PowerShell como administrador, en el servidor):
  `Stop-ScheduledTask -TaskName ManaPedidosMovil; Start-ScheduledTask -TaskName ManaPedidosMovil`
  y comprobar `https://<servidor>/health`.
- **Quitar**: `deploy\desinstalar_servicio.ps1` (y `tailscale serve reset` para sacar el HTTPS).

## Actualizar (cuando hay cambios en `movil/`)

1. **Copiar** desde la PC de desarrollo (raíz del repo). No pisa el `.env` del servidor ni los logs:
   ```
   robocopy movil Z:\AppInforme\movil /E /XD __pycache__ logs tests /XF .env
   ```
2. **Reiniciar la API solo si cambió Python** (`api\`, `run.py`, `migraciones.py`). Si además cambió
   `requirements.txt`, antes `python -m pip install -r <ruta local>\movil\requirements.txt`. Si **solo** cambió la PWA
   (`pwa\`: HTML, CSS, JS, imágenes) **no hace falta reiniciar**: la API lee esos archivos del disco en cada pedido.
3. **Comprobar que el servidor ya tiene lo nuevo**: abrir `https://<servidor>/sw.js` en el navegador; la primera
   constante, `CACHE_NAME` (`mana-pedidos-vN`), tiene que ser la versión nueva.
4. **Celulares**: cerrar la app **del todo** (deslizarla en apps recientes) y volver a abrirla; si sigue la versión
   vieja, repetirlo una vez más. El teléfono baja la versión nueva en segundo plano al abrir y la muestra en el
   siguiente arranque: una PWA instalada no se actualiza sola mientras está abierta.

**Regla para quien toque la PWA**: cada cambio en `pwa\` tiene que subir `CACHE_NAME` en `pwa\sw.js` (v6 → v7...) y,
si se agrega un archivo, sumarlo a la lista `CASCARON`. Sin eso los celulares no detectan que hay una versión nueva
(el navegador solo actualiza el service worker si `sw.js` cambió byte a byte).

## Usuarios y seguridad

- Se usa la tabla `usuario` que ya existía (clave en bcrypt): `romulo`, `miguel`, `jose`, `diego`, `matias`, `martin`
  (vendedores) y `admin`. Maxi, Angeles y Julieta no tienen usuario.
- **Claves**: nadie conoce las originales. Hoy solo `jose` y `matias` tienen una clave de prueba puesta a propósito.
  Falta una herramienta para asignarles claves reales a los demás (pendiente).
- **Dar de baja a un vendedor**: `UPDATE usuario SET activo = false WHERE username = '...'` le corta el acceso **al
  instante** (se chequea en cada petición, no solo en el login). Para un celular perdido, además sacarlo de Tailscale.
- Todos los clientes y productos se descargan al celular (solo nombre, CUIT y localidad; nunca teléfono, dirección,
  stock ni saldos). El rol `movil_api` solo puede leer clientes/productos, insertar pedidos y leer 5 columnas de `usuario`.
- Tras 5 claves incorrectas el usuario se bloquea 15 minutos; ese contador vive en memoria y se reinicia con la tarea.
- La sesión dura 7 días: tiene que sobrevivir un fin de semana sin señal. Vencida, la app vuelve al login y los
  pedidos guardados se envían solos al volver a entrar.

## Problemas frecuentes

| Síntoma | Causa y salida |
|---|---|
| `/health` dice `db: error: OperationalError` | Revisar `PEDIDOS_DB_*`. El nombre de máquina de Windows se resuelve con `gethostbyname` (psycopg2 no lo hace solo): ya está contemplado en `api/db.py` |
| El celular muestra la pantalla vieja | Cerrar la app del todo y reabrirla |
| Los clientes "desaparecen" al arrastrar sin conexión | Ya corregido (se desactivó el gesto de recarga); si pasa, es la versión vieja de la app |
| `Demasiados intentos fallidos` | Esperar 15 minutos o reiniciar la tarea |
| La tarea no arranca tras reiniciar | `Get-ScheduledTaskInfo`, luego `logs\api.log`. Causa típica: librerías instaladas solo para un usuario (`pip --user`) y no para el Python que usa SYSTEM |
| El instalador dice "unidad de red" | Correrlo desde la ruta local del servidor, no desde `Z:` |

## Límites conocidos

Un solo servidor (si la PC se apaga no hay API; la cola del celular lo cubre guardando los pedidos). No se pueden
eliminar pedidos desde el celular. El precio unitario se guarda en 0, igual que en el alta de la PC.
