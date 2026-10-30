# Mana Pedidos móvil

Los vendedores cargan pedidos desde el celular, en la calle, y esos pedidos aparecen solos en el sistema de
escritorio. Solo **crea pedidos** (nada de cuentas corrientes ni de consultar pedidos ajenos).

```
celular (PWA instalada) --HTTPS por Tailscale--> API FastAPI (127.0.0.1:8000) --> PostgreSQL pedidosMana
```

- **PWA** (`pwa/`): HTML/CSS/JS puro, sin compilar. La sirve la propia API (mismo origen, sin CORS). Funciona
  sin conexión: el catálogo vive en el celular (IndexedDB) y los pedidos se guardan ahí hasta enviarse.
- **API** (`api/`): FastAPI. `POST /auth/login`, `GET /catalogo`, `POST /pedidos` (vendedores), `GET /reparto/pedidos` y
  `POST /reparto/pedidos/{id}/entregar` (reparto), `GET /panel` (admin), `GET /health`.
- **Fuera del `.exe`**: esta carpeta nunca entra al compilable (`CompilarEjecutable.py` solo empaqueta `main.py` y
  `src/`). Tiene su propio `requirements.txt` y no importa nada de `src/` (arrastraría PyQt).
- Diseño, decisiones y bitácora de cada tarea: `guideline/Movil.md`.

## Carpetas

| Ruta | Qué es |
|---|---|
| `claves.py` | Administración: ver usuarios y asignarles clave (ver Usuarios y seguridad) |
| `migrar.py` | Aplica en la base los cambios de `sql/` y deja los permisos de `movil_api` (ver Actualizar) |
| `vapid.py` | Genera una sola vez las claves de los avisos (ver Avisos) |
| `run.py` | Lanzador: lee `.env`, escribe logs, arranca la API. Lo usa la tarea de Windows y sirve a mano |
| `api/` | La API (`app.py`, `auth.py`, `deps.py`, `db.py`, `pedidos.py`, `routers/`) |
| `pwa/` | La app del celular (`index.html`, `js/`, `css/`, `sw.js`, `manifest.webmanifest`). Pantalla de vendedor y pantalla de reparto, según el perfil |
| `sql/001_movil.sql` ... `004_notificaciones.sql`, `migraciones.py` | Cambios a la base (aditivos) y rol `movil_api` |
| `panel/` | Cálculo del panel de control (litros, % premium, recaudado) y el proceso `worker.py` que lo guarda en la base |
| `avisos/` | El proceso que manda los avisos (notificaciones push) a los celulares |
| `deploy/` | Instalar / desinstalar las tareas de Windows (API, panel y avisos) |
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

## Panel de control (proceso aparte, una sola vez)

El panel (litros vendidos del mes, % premium y dinero recaudado de la semana) lo calcula un **segundo proceso** del
servidor que lee los archivos del sistema de gestión (`D:\tiempo`), así la API y el celular no los leen nunca. Se
instala después de la API, con el mismo `.env`:

1. Librerías, con el mismo Python que usa la tarea: `python -m pip install -r movil\requirements-panel.txt`.
2. PowerShell **como administrador**, desde la ruta local del servidor:
   `powershell -ExecutionPolicy Bypass -File <ruta local>\movil\deploy\instalar_panel.ps1`
   (con `-SoloVerificar` solo revisa los requisitos). Registra la tarea `ManaPanelMovil`, la arranca y espera el
   primer cálculo (puede tardar un minuto).
3. Si el sistema de gestión no está en `D:\tiempo`, agregar `PANEL_BASE_PATH=<carpeta>` al `.env`.

Cada 5 minutos (`PANEL_INTERVALO_SEG`) mira si los archivos cambiaron y recién ahí recalcula. Log: `movil\logs\panel.log`.
La API lo lee con `GET /panel` y lo ve el admin en la pestaña Panel; si el proceso deja de dar señales por más de 15 minutos, la app lo avisa.
La semana va siempre del lunes a hoy; el mes, del 1 a hoy; cada cifra se compara con el período anterior hasta el mismo día.
El recaudado trae además su desglose (efectivo, transferencia, cheques, retenciones y otros), que sale de `plan_caj.DBF` y
`placaja.DBF` (misma carpeta que los demás DBF); si el proceso no las encuentra no calcula nada y lo informa en el log.

## Avisos (notificaciones push)

Con la app en segundo plano, los celulares avisan de un **pedido nuevo de un vendedor** (a admin y superadmin), un
**pedido programado** (al reparto) y un **pedido entregado** (a admin, superadmin y al vendedor que lo cargó). Cada
persona activa los avisos en su celular tocando la campana del encabezado de la app. Detalle del diseño en
`guideline/Movil.md` (Fase 4). La primera vez se instala así, **en este orden**:

1. **Base de datos** (crea las tablas de los avisos y da los permisos; pide la clave del `postgres`; se puede correr
   desde cualquier PC que vea la base). Primero mirar qué falta y después aplicar:
   ```powershell
   python movil\migrar.py --host DESKTOP-R8E4V7S --solo-verificar
   ```
   ```powershell
   python movil\migrar.py --host DESKTOP-R8E4V7S
   ```
2. **Copiar** `movil\` al servidor (ver Actualizar, paso 1).
3. **Librerías** en el servidor, con el mismo Python que usa la tarea (`pywebpush` usa `cryptography`; si dice
   `DLL load failed`, instalar el *Visual C++ Redistributable x64* de Microsoft y reintentar):
   ```powershell
   python -m pip install -r movil\requirements-avisos.txt
   ```
4. **Claves** (UNA sola vez, en el servidor). El contacto viaja en cada aviso hacia Google/Apple: elegir un correo a
   propósito. Si ya hay claves en el `.env` el comando no las cambia (hacerlo dejaría sin efecto todas las suscripciones).
   Escribe en el `movil\.env` que tiene al lado y anda desde cualquier carpeta con la ruta completa (o parado en la
   carpeta que **contiene** `movil\`, que es donde se ve la subcarpeta `movil`):
   ```powershell
   python movil\vapid.py --contacto mailto:CORREO-ELEGIDO
   ```
5. **Reiniciar la API** para que ofrezca los avisos (ver Actualizar, paso 2) y comprobar que `/health` dice `"reiniciar": false`.
6. **Instalar el proceso** (PowerShell **como administrador**, desde la ruta local del servidor; con `-SoloVerificar` solo
   revisa los requisitos). La primera vez anota como ya avisado todo lo que existe, para no mandar un aviso por cada
   pedido viejo:
   ```powershell
   powershell -ExecutionPolicy Bypass -File <ruta local>\movil\deploy\instalar_avisos.ps1
   ```
7. **Celulares**: cerrar la app del todo y volver a abrirla; aparece la campana. Tocarla y aceptar el permiso. En iPhone
   solo funciona con la app agregada a la pantalla de inicio (iOS 16.4 o más).

Log: `movil\logs\avisos.log` (nunca escribe las direcciones de los celulares ni las claves). Reiniciar el proceso:
`Stop-ScheduledTask -TaskName ManaAvisosMovil; Start-ScheduledTask -TaskName ManaAvisosMovil`. Los avisos llegan al
celular por los servidores de Google/Apple (el contenido viaja cifrado) y no necesitan Tailscale; tocar el aviso para abrir
la app sí lo necesita.

## Operación

- **Logs**: `movil\logs\api.log` (rota solo, 1 MB x 5).
- **Estado**: `Get-ScheduledTaskInfo -TaskName ManaPedidosMovil` (mirar `LastTaskResult`).
- **Reiniciar la API** (PowerShell como administrador, en el servidor):
  `Stop-ScheduledTask -TaskName ManaPedidosMovil; Start-ScheduledTask -TaskName ManaPedidosMovil`
  y comprobar `https://<servidor>/health`.
- **Quitar**: `deploy\desinstalar_servicio.ps1` (y `tailscale serve reset` para sacar el HTTPS).

## Actualizar (cuando hay cambios en `movil/`)

Los comandos de abajo son **los que se usan siempre**. Están escritos sin variables ni guiones bajos a propósito:
un comando con `$_` perdió el guion bajo al pegarse en PowerShell (quedó `$`, nombre de tarea vacío) y la tarea
nunca se reinició, aunque el error parecía de otra cosa. Se pegan tal cual.

1. **Copiar** desde la PC de desarrollo (raíz del repo). No pisa el `.env` del servidor ni los logs:
   ```powershell
   robocopy movil Z:\AppInforme\movil /E /XD __pycache__ logs tests /XF .env
   ```
2. **Reiniciar las tareas del servidor solo si cambió Python** (`api\`, `panel\`, `avisos\`, `run.py`, `migraciones.py`). Si
   **solo** cambió la app (`pwa\`: HTML, CSS, JS, imágenes) **no hace falta**: la API lee esos archivos del disco en
   cada pedido. Si cambió `requirements.txt`, `requirements-panel.txt` o `requirements-avisos.txt`, antes instalar las librerías (ver
   "Despliegue", "Panel de control" y "Avisos"). Si apareció un archivo nuevo en `movil\sql\`, antes aplicar los cambios a la
   base (ver Avisos, paso 1: `python movil\migrar.py --host DESKTOP-R8E4V7S`). En el **servidor**, PowerShell **como administrador**
   (con los avisos instalados son tres tareas; **antes de instalarlos, `ManaAvisosMovil` no existe** y ese pedazo da un error inofensivo):
   ```powershell
   Stop-ScheduledTask -TaskName ManaPedidosMovil; Stop-ScheduledTask -TaskName ManaPanelMovil; Stop-ScheduledTask -TaskName ManaAvisosMovil
   ```
   Esperar unos 5 segundos y:
   ```powershell
   Start-ScheduledTask -TaskName ManaPedidosMovil; Start-ScheduledTask -TaskName ManaPanelMovil; Start-ScheduledTask -TaskName ManaAvisosMovil
   ```
   Para confirmar que están corriendo (tienen que decir `Running`):
   ```powershell
   Get-ScheduledTask -TaskName ManaPedidosMovil, ManaPanelMovil, ManaAvisosMovil | Select-Object TaskName, State
   ```
3. **Comprobar que el servidor ya tiene lo nuevo**: abrir `https://<servidor>/sw.js` en el navegador; la primera
   constante, `CACHE_NAME` (`mana-pedidos-vN`), tiene que ser la versión nueva. Y `https://<servidor>/health` tiene que
   decir `"reiniciar": false`: si dice `true`, se copiaron archivos de Python pero la API sigue corriendo el código viejo
   (la app se actualiza sola al copiar, la API no): reiniciar la tarea. (Si `/health` no trae el campo `reiniciar`, la API
   es de antes de que existiera: reiniciarla igual.)
4. **Si cambió el cálculo del panel**: a los 30-60 segundos del reinicio, desde la carpeta que contiene `movil\`, el
   final del log tiene que decir `Ciclo: calculado`:
   ```powershell
   Get-Content .\movil\logs\panel.log -Tail 30
   ```
5. **Celulares**: cerrar la app **del todo** (deslizarla en apps recientes) y volver a abrirla; si sigue la versión
   vieja, repetirlo una vez más. El teléfono baja la versión nueva en segundo plano al abrir y la muestra en el
   siguiente arranque: una PWA instalada no se actualiza sola mientras está abierta. Si cambió el perfil (rol) de
   alguien, tiene que salir y volver a entrar.

**Regla para quien toque la PWA**: cada cambio en `pwa\` tiene que subir `CACHE_NAME` en `pwa\sw.js` (v6 → v7...) y,
si se agrega un archivo, sumarlo a la lista `CASCARON`. Sin eso los celulares no detectan que hay una versión nueva
(el navegador solo actualiza el service worker si `sw.js` cambió byte a byte).

## Usuarios y seguridad

- Se usa la tabla `usuario` que ya existía (clave en bcrypt): `romulo`, `miguel`, `jose`, `diego`, `matias`, `martin`
  (vendedores) y `admin`. Maxi, Angeles y Julieta no tienen usuario.
- **Claves**: nadie conoce las originales. Hoy solo `jose` y `matias` tienen una clave de prueba puesta a propósito.
  Para asignarles las reales a los demás: `claves.py` (siguiente punto).
- **Claves** (`claves.py`): `python movil/claves.py --host DESKTOP-R8E4V7S vendedores` pide una clave nueva por cada vendedor activo (Enter = saltear); `fijar <usuario>...` para algunos; `listar` para ver usuarios y estado; `rol <usuario> <rol>` para cambiar un rol (el usuario tiene que salir y volver a entrar en la app para ver su pantalla nueva); `crear <usuario> --nombre N --rol R` para dar de alta uno nuevo. Las claves se escriben sin mostrarse (nunca van por argumentos ni por chat), mínimo 8 caracteres, y quedan en bcrypt. Pide la clave del usuario `postgres` del servidor (o la variable `PEDIDOS_ADMIN_PASSWORD`): `movil_api` no puede modificar `usuario`. En el servidor alcanza con `--host localhost`. Las sesiones ya abiertas siguen valiendo hasta que venzan (7 días): para cortar un acceso al instante, `activo = false`.
- **Perfiles** (`usuario.rol`, se lee de la base en cada petición): `vendedor` carga pedidos; `reparto` solo ve y marca
  entregas (y guarda ubicaciones de clientes); `admin` ve todo (pestañas Pedidos, Reparto y Panel abajo); `superadmin` hace todo lo del admin y tendrá más control sobre la app. Cambiar el rol de alguien o darlo
  de baja le surte efecto al instante, aunque conserve su token.
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

Un solo servidor (si la PC se apaga no hay API; la cola del celular lo cubre guardando los pedidos; el reparto también guarda entregas y ubicaciones sin señal). No se pueden
eliminar pedidos desde el celular. El precio unitario se guarda en 0, igual que en el alta de la PC.
