# Móvil — toma de pedidos desde el celular (`movil/`)

**Estado: diseño aprobado, Tareas 0 a 11 hechas, Tarea 12 (prueba de campo) pendiente.** Tareas 0 a 9 confirmadas en
el celular real; la 10 (cola offline) probada de punta a punta en el navegador contra la base real, **falta
probarla en el celular con modo avión real**; la 11 (arranque automático) **ya está instalada y corriendo en
el servidor** (`https://desktop-r8e4v7s.tail5a20aa.ts.net/`, confirmado por el usuario el 23/10/2026; `/health` → ok/ok
verificado desde Penxita). La API de Penxita se apagó; las PWA instaladas desde la URL vieja hay que reinstalarlas
desde la nueva (el almacenamiento del celular es por origen). **Gotcha de PWA instalada:** al actualizar `movil/pwa/` la app instalada sigue
mostrando la versión vieja hasta cerrarla del todo (no solo "atrás") y reabrirla.
Última actualización: 2026-10-23.

> **Logo en el login (23/10/2026) y cómo se actualiza la PWA en producción:** el login ahora muestra el logo de
> Mana (`pwa/icons/logo-mana.png`, 480x120, generado desde `Distribuidora/Logo Mana comprimido.png`: el
> `Logo_Mana.png` pedido es de 139x34 px y se vería pixelado en celulares 2x/3x; es el mismo logo en alta
> resolución). Responsive: `width: min(100%, 220px); height: auto`, probado en 320, 375 y 768 px. Reemplazó al
> ícono chico de pedidos dentro de la tarjeta (ese ícono sigue siendo el de la pantalla de inicio).
> Procedimiento de actualización (detalle en `movil/README.md`, sección "Actualizar"): `robocopy` de `movil\` al
> servidor sin pisar `.env`; reiniciar la tarea **solo si cambió Python** (la PWA se lee del disco en cada pedido);
> en los celulares cerrar la app del todo y reabrirla. **Regla:** todo cambio en `pwa/` sube `CACHE_NAME` en
> `sw.js` (hoy `v6`) y suma los archivos nuevos a `CASCARON`. Además `sw.js` ahora instala con
> `cache: "reload"`: el servidor no manda `Cache-Control` y sin eso el navegador podía dar por "frescas" varias
> horas las copias viejas y el service worker nuevo guardaba archivos viejos.

> **Tarea 11 (23/10/2026):** arranque automático en el servidor + documentación final (`movil/README.md`).
> - **Tarea programada de Windows** en vez de un servicio clásico (decisión mía, sin instalar nada extra: ni
>   `pywin32` ni NSSM): disparador "al iniciar el equipo", cuenta SYSTEM (sube sin que nadie inicie sesión),
>   reinicio automático cada minuto si se cae, **sin límite de tiempo** (el default de Windows la mataría a los 3
>   días). `deploy/instalar_servicio.ps1` (con `-SoloVerificar`, `-ConfigurarTailscale`, `-Python`) y
>   `deploy/desinstalar_servicio.ps1`. Son ASCII a propósito (PowerShell 5.1 lee mal los acentos sin BOM).
> - **`movil/run.py`**: lanzador que lee `movil/.env` solo dentro de su proceso (pisa a las variables del sistema:
>   **resuelve el riesgo anotado en la Tarea 4** de que `PEDIDOS_DB_*` se mezcle con la app de escritorio) y escribe
>   `movil/logs/api.log` (rota solo). Sale con código 2 y deja el motivo en el log si falta el `.env` o variables.
> - **La API ahora escucha solo en `127.0.0.1`** (antes `0.0.0.0` a mano): `tailscale serve` la proxea por HTTPS, no
>   hace falta abrirla a la red local de la oficina.
> - **Una tarea de Windows no ve unidades de red (`Z:`)**: el instalador se niega a correr desde una (detecta
>   `DriveType = 4`, probado con la `Z:` real) y pide la ruta local del servidor.
> - **`movil\.env` se restringe a Administradores y SYSTEM** al instalar (`icacls` por SID, sirve en Windows en
>   español): tiene la clave de la base y el secreto de los tokens, y la carpeta se comparte con la red de la oficina.
> - **Corregido un faltante de seguridad** (lo encontré al redactar el README): el plan decía que `usuario.activo` "se
>   chequea en cada pedido", pero solo se chequeaba en el login: un vendedor dado de baja seguía operando hasta que
>   venciera su token (7 días). Ahora `deps.usuario_actual` consulta `db.usuario_activo` en cada petición (token
>   primero, base después; una sola conexión por petición). Cubierto en `verificar_login_api.py` (mock) y
>   `verificar_catalogo.py` (base real, `UPDATE` revertido con rollback).
> - Pruebas: `verificar_run.py` (parser del `.env`, errores de configuración, arranque real en puerto libre, que
>   **no** escucha en la red local, log). El registro real de la tarea necesita consola de administrador y reinicio
>   del equipo: **no se pudo probar acá**, lo hace el usuario en el servidor.
> - Herramienta para asignar claves reales a los vendedores: `movil/claves.py` (hecha el 24/10/2026, ver `README.md`).
>   Hasta que se corra, solo `jose`/`matias` tienen clave de prueba.

> **Tarea 10 (23/10/2026):** el pedido ahora se guarda **primero en el teléfono** y después se envía.
> - `js/db.js`: IndexedDB pasa a la versión 2 (store nuevo `cola`, el catálogo se conserva). Base compartida
>   `BaseLocal` + `CatalogoDB` + `ColaDB`.
> - `js/cola.js` (`Cola`): estados `pendiente` (se reintenta solo) / `enviado` (guarda `id_pedido`) / `rechazado`
>   (el servidor dijo 4xx: no se reintenta, el vendedor lo descarta). Dispara el envío al confirmar, al volver la
>   conexión (`online`), al abrir la app, al volver a primer plano y cada 30 s. Un solo ciclo a la vez (si llega
>   un pedido mientras se envía, se hace otra vuelta). Reintentar **no duplica**: el `uuid` lo genera el teléfono
>   y el servidor ya era idempotente por `uuid`. Solo 4xx "de verdad" rechaza; red, timeout, 401, 408, 429, 5xx y
>   errores inesperados dejan el pedido pendiente. Los enviados se purgan a los 3 días.
> - `js/cola-ui.js`: panel "X por enviar · Y rechazados · Z enviados" arriba de la lista de clientes; se despliega
>   con el estado de cada pedido (pastilla, `pedido #id`, motivo del rechazo) y botón "Descartar" (pendientes y
>   rechazados; un enviado ya no se puede deshacer desde el celular).
> - `js/api.js`: errores con `.status`, **timeout de 20 s** (una red colgada no traba la cola; se trata como "sin
>   red"), mensaje legible para los 422 de Pydantic (antes salía `[object Object]`) y evento
>   `mana:sesion-vencida` ante un 401 fuera del login. `login.js` lo escucha: vuelve al login con aviso, y los
>   pedidos guardados salen solos al volver a entrar. "Salir" con pedidos sin enviar pide confirmación.
> - Los pedidos se filtran por vendedor (`vendedor` = nombre de la sesión): en un teléfono compartido el pedido de
>   uno no sale bajo la sesión del otro.
> - Backend: **sin cambios** (la idempotencia de la Tarea 5 ya cubría esto).
>
> **Prueba contra la base real (en el navegador, con `fetch` roto para simular modo avión):** sin conexión →
> `pendiente` → vuelve la red → `enviado` solo; **respuesta perdida** (el servidor guarda pero el teléfono no se
> entera) → reintento → **1 sola fila y 1 sola línea de detalle por `uuid`** (verificado en Postgres); producto
> inexistente → `rechazado` con su motivo; token inválido → login con aviso, el pedido queda guardado y al
> volver a entrar se manda; flujo completo por la pantalla de pedido. Los pedidos de prueba (229, 230, 232, 233)
> se borraron de la base; los 3 pedidos `movil` de `jose` que siguen son de las pruebas del usuario desde el
> celular (no tocar). Nota: el reintento de un pedido ya guardado consume un número de secuencia
> (`ON CONFLICT DO NOTHING`), por eso los `id_pedido` pueden saltear números; es inofensivo.

> **Tarea 9 (22/10/2026):** `movil/pwa/js/pedido.js` — tercera pantalla (`#pantalla-pedido`), se abre tocando un
> cliente de la lista (evento `mana:cliente-elegido`, lo dispara `catalogo.js`). Buscador de producto sobre el
> catálogo ya sincronizado (IndexedDB, `db.js`), carrito con stepper de cantidad (1-9999, mismos límites que
> `movil/api/pedidos.py`) y botón quitar, `POST /pedidos` con `uuid` generado por `crypto.randomUUID()` y
> `fecha_pedido` en fecha local (no `toISOString()`, que es UTC y puede correrse de día cerca de medianoche). Si
> falla el envío, el carrito **no se vacía** (el vendedor no pierde lo que cargó) y se distingue un error de red
> (mensaje claro en español) de un error de validación del servidor (que ya trae su propio mensaje). "Volver" con
> el carrito lleno pide confirmación antes de descartarlo.
>
> **Probado de punta a punta en el navegador contra el servidor real**: elegí un cliente real, busqué y agregué un
> producto real, mandé el pedido — se creó de verdad (`id_pedido=216`, `origen='movil'`, `creado_por='jose'`) y lo
> borré enseguida de la base (mismo criterio que las pruebas anteriores: no dejar basura en producción). También
> probé el camino de error (sin conexión simulada): el carrito se mantiene y el mensaje es claro.

> **Bug reportado por el usuario probando en su celular (22/10/2026), confirmado arreglado:** con los datos/wifi
> apagados, "arrastrar para actualizar" hacía que los clientes "desaparecieran". Causa: ese gesto dispara una
> recarga completa de la página (no una acción de la app), y offline esa recarga podía fallar y mostrar la
> pantalla de error del navegador en vez de la app. Corregido con `overscroll-behavior-y: contain` (desactiva el
> gesto nativo) + `sw.js` cae al cascarón cacheado si falla una navegación sin red. El usuario lo volvió a probar
> en el celular real y confirmó que ya anda.
>
> De paso, hasta ahora el test `verificar_catalogo.py` tenía la cantidad de clientes hardcodeada (2.104) y la base
> real ya tiene más (creció a 2.107 en el uso normal del negocio entre la Tarea 4 y ahora): se cambió a comparar
> contra un `COUNT(*)` en vivo en la misma corrida, no un número fijo — un test así siempre iba a quedar viejo.

> **Tarea 8 (22/10/2026):** `movil/pwa/js/db.js` (IndexedDB: stores `clientes`, `productos`, `meta` con versión y
> fecha de sincronización) + `js/catalogo.js` (sincroniza contra `GET /catalogo` al loguearse — evento
> `mana:sesion-iniciada` que dispara `login.js` — y arma el buscador por nombre/CUIT). Si el fetch falla, sigue
> mostrando lo último guardado en IndexedDB en vez de romper: probado simulando `fetch` roto en el navegador (no
> hay forma de forzar modo avión real desde esta sesión), 2.104 clientes y el buscador siguieron andando. Corregí
> en el momento un riesgo de XSS que me marcó el hook de seguridad: armaba las filas con `innerHTML` + texto
> interpolado; lo cambié a `textContent`/DOM seguro antes de commitear.

> **Despliegue real hecho (22/10/2026), confirmado por el usuario:** se aplicó la migración de la Tarea 1 de verdad
> sobre `DESKTOP-R8E4V7S` (ya no es solo código: existen `pedido.origen`, `pedido.uuid_cliente` y el rol `movil_api`
> en el servidor real) y se le puso una clave de prueba conocida a `jose` (`<clave-privada>`) porque nadie sabía ninguna
> clave real de la tabla `usuario` (son hashes bcrypt, nadie las anotó). `movil/.env` quedó con las credenciales
> reales (gitignored). **Bug encontrado al probar con la base real:** `movil/api/db.py::conexion()` no resolvía el
> hostname con `socket.gethostbyname()` como sí hace `programarPedido.py::_conexion()` — psycopg2 no resuelve
> `DESKTOP-R8E4V7S` directo en esta red y tiraba un `OperationalError` sin mensaje. Ya corregido, replicando el
> mismo patrón.

> **Tarea 7 (22/10/2026):** PWA mínima en `movil/pwa/` (manifest, service worker, pantalla de login), servida por el
> propio FastAPI con `StaticFiles` montado al final de `app.py` (mismo origen que la API, sin CORS; `aiofiles` no
> hizo falta). Ícono generado desde `Distribuidora/pedidos.png` (ya existía y es temáticamente el correcto) con
> Pillow, 192/512px con fondo claro y padding para zona segura "maskable". **Dos bugs encontrados probando en vivo
> en el navegador** (ver [[feedback-frontend-minimalista]] y la memoria del proyecto): (1) `.pantalla[hidden]`
> faltaba — `.pantalla{display:flex}` empataba en especificidad con `[hidden]` del navegador y ganaba por orden de
> carga, las dos pantallas (login y app) quedaban visibles a la vez; (2) con la base caída, `/auth/login` tiraba un
> 500 crudo — se agregó `deps.conexion_actual()` (dependencia con `yield`, 503 prolijo) y se usa en los tres routers
> (`auth`, `catalogo`, `pedidos`) en vez de que cada uno abra/cierre la conexión a mano.

> **Tarea 6 hecha (22/10/2026), probada en Penxita (no en `DESKTOP-R8E4V7S`, el servidor real; se repite ahí al
> desplegar):** HTTPS Certificates activado en el admin console del tailnet, API levantada con
> `uvicorn movil.api.app:app --host 0.0.0.0 --port 8000` y variables de entorno de prueba (`movil/.env`, gitignored).
> **El comando real para expuesto por HTTPS fue `tailscale serve --bg http://127.0.0.1:8000`**, no
> `tailscale serve https / <target>` (sintaxis vieja/de otra versión). Confirmado desde el celular por HTTPS:
> `{"api":"ok","db":"error: OperationalError"}` (el error de base es esperado, son credenciales de prueba).

> **Fix a la migración de la Tarea 1 (encontrado recién al usarla en la Tarea 5):** el índice único de
> `uuid_cliente` es parcial (`WHERE uuid_cliente IS NOT NULL`). El `INSERT ... ON CONFLICT (uuid_cliente)` de
> `crear_pedido` tiene que repetir ese `WHERE` para que Postgres pueda inferir el índice arbiter, sin él tira
> `InvalidColumnReference`. El test de la Tarea 1 no lo detectó porque nunca hace un `INSERT` real con conflicto;
> el de la Tarea 5 sí. Ya corregido en `movil/api/db.py`.

> **Riesgo de despliegue (anotado en la Tarea 4, RESUELTO en la Tarea 11):** `movil/api/config.py` lee las mismas
> `PEDIDOS_DB_*` que `programarPedido.py` (a propósito). Si alguna vez las variables se ponían a nivel de
> sistema/usuario, una pisaba a la otra. Ahora `movil/run.py` carga el `.env` solo dentro de su proceso y **pisa**
> las del sistema, así que no se mezclan.

> **Frontend (PWA, Tareas 7-9):** minimalista, estético y responsive por defecto, sin que haga falta pedirlo —
> mismo criterio que el resto de la app (ver `prototypeExample/` y el estilo Tailwind/slate-blue ya establecido).

> **Gotcha de esta máquina:** ningún paquete de Python con extensión en Rust carga (`bcrypt>=4`, `cryptography`,
> por lo tanto tampoco `pyjwt`): `ImportError: DLL load failed`. Se resolvió con `bcrypt==3.2.2` (cffi) y un JWT
> HS256 escrito a mano con `hmac`/`hashlib` (`movil/api/auth.py`), sin `pyjwt` ni `cryptography`. Detalle en la
> memoria `gotchas-maquina-dev`.

> **Para retomar el trabajo (p. ej. desde la app de Claude):** leé este archivo entero, hacé la próxima tarea sin
> marcar del plan y tildala al terminar. Una tarea por sesión. Reglas del usuario: sin `Co-Authored-By` en los
> commits (conventional commits), **no compilar** después de cambios, respuestas cortas, y toda prueba que escriba en
> Postgres va **dentro de una transacción que se revierte** (la base del servidor es la real).

## Objetivo

Que los vendedores **carguen pedidos desde el celular, en la calle**, y que esos pedidos aparezcan en el sistema de
escritorio. Solo eso: **crear pedidos**. Nada de cuentas corrientes, ventas ni consulta de pedidos ajenos.

## Decisiones tomadas (por el usuario)

| Tema | Decisión |
|---|---|
| Alcance | Solo crear pedidos |
| Formato | **PWA** (web app instalable), JS puro, sin framework ni paso de compilación |
| Red | Los vendedores cargan en la calle (datos móviles o WiFi que no es del local) → **Tailscale** (VPN, una app en cada celular). La API escucha solo en la interfaz de Tailscale; nada público en internet |
| Servidor | El de siempre (`DESKTOP-R8E4V7S`, PC local). Está prendido en horario de trabajo: aceptado |
| Clientes visibles | **Todos** (cualquier vendedor puede cubrir a otro). No hace falta traer el vendedor a `Cliente` |
| Ubicación en el repo | Dentro de este repo, carpeta `movil/` aparte, **fuera del `.exe`**, con su propio `requirements.txt` |
| Offline | Obligatorio: el pedido se guarda en el celular y se envía al reconectar, sin duplicar |

## Tarea 0 — hallazgos en la base real (solo lectura, 22/10/2026)

PostgreSQL 17.5, base `pedidosMana`. 2.104 clientes, 1.425 productos, 91 pedidos (88 entregados).

1. **Ya existe la tabla `usuario`**: `id, username (único), password_hash, nombre, rol, vendedor_id, activo, creado_en`.
   Tiene 7 filas: `admin` (rol admin) y 6 vendedores (romulo→1, miguel→3, jose→4, diego→5, matias→6, martin→9).
   El hash es **bcrypt** (`$2a$10$…`, 60 caracteres). **Nada del repo la usa**: alguien la creó para otro fin.
   → Se **reutiliza** para el login; **no** se crea `usuario_movil`. Maxi, Angeles y Julieta no tienen usuario.
2. **`Pedido.creado_por VARCHAR` ya existe**, sin uso (los 91 pedidos lo tienen `NULL`).
   → Se usa para guardar quién tomó el pedido; **no** se agrega `tomado_por`.
3. `DetallePedido.id_producto` es **`VARCHAR`** (códigos como `01VA133`, hasta 14 caracteres), no entero.
   `Cliente.id_cliente` sí es entero.
4. Restricciones que la API debe respetar: `cantidad > 0`; `estado_pedido` ∈ {pendiente, programado, en camino,
   entregado}; `Pedido.id_cliente` y `DetallePedido.id_producto` con `ON DELETE RESTRICT`;
   `DetallePedido.id_pedido` con `ON DELETE CASCADE`; `estado_entrega` es columna GENERADA (no se escribe).
5. Hay una vista `vista_pedidos_completa` (junta pedido, cliente y totales): no se rompe por columnas nuevas.
6. Solo hay dos roles en el servidor, `postgres` y `mana`, **ambos superusuario**.
   → La API **no** debe conectarse como superusuario: una API expuesta a la red con ese rol, si la comprometen,
   da control total de la base. Se crea el rol `movil_api` con permisos mínimos (ver Tarea 1).
7. Trigger único: `trg_actualizar_estado_pedido` (sobre `UPDATE` de `DetallePedido`). Los `INSERT` de la API no lo disparan.

## Estructura de carpetas

```
movil/                         ← NO entra en el .exe, dependencias propias
├── README.md                  cómo levantarlo, desplegarlo y operarlo (documentación final)
├── run.py                     lanzador: lee .env, logs a movil/logs/api.log, escucha en 127.0.0.1
├── requirements.txt           fastapi, uvicorn, psycopg2-binary, bcrypt==3.2.2, httpx (sin pyjwt, ver gotcha arriba)
├── env.example                 (el sandbox bloquea nombres .env*; copiar a mano a .env)
├── api/
│   ├── app.py                 FastAPI: arma la app y registra routers
│   ├── config.py              lee PEDIDOS_DB_* (mismas variables que Pedidos) + secreto del token
│   ├── db.py                  conexión a Postgres (rol movil_api)
│   ├── auth.py                verificación bcrypt, token firmado con vencimiento, límite de intentos
│   ├── schemas.py             validación de entrada
│   └── routers/               auth.py · catalogo.py · pedidos.py
├── sql/001_movil.sql          migración idempotente (se puede aplicar dos veces)
├── tests/                     estilo tests/verificar_*.py, con rollback
├── pwa/                       JS puro, servida por StaticFiles desde la propia API (mismo origen)
│   ├── index.html · manifest.webmanifest · sw.js
│   ├── css/estilos.css        paleta slate/blue, la misma que src/ui/estilos.qss
│   ├── icons/                 icon-192.png · icon-512.png (generados desde Distribuidora/pedidos.png)
│   └── js/                    api.js · db.js · cola.js · cola-ui.js · catalogo.js · pedido.js · login.js
└── deploy/                    instalar_servicio.ps1 · desinstalar_servicio.ps1 (tarea programada de Windows)
                               (no se creó tools/: la migración y el rol van por migraciones.py)
```

- **No importar nada de `src/`**: arrastra PyQt. La API tiene su propio acceso a la base.
- La carpeta no entra en el `.exe` (`CompilarEjecutable.py` solo empaqueta `main.py` y `src/`).

## Cambios a la base (`sql/001_movil.sql`, todo aditivo)

La PC sigue funcionando igual: las columnas nuevas tienen valor por defecto o aceptan `NULL`.

```sql
ALTER TABLE Pedido ADD COLUMN IF NOT EXISTS origen text NOT NULL DEFAULT 'pc'
    CHECK (origen IN ('pc', 'movil'));
ALTER TABLE Pedido ADD COLUMN IF NOT EXISTS uuid_cliente uuid;
CREATE UNIQUE INDEX IF NOT EXISTS ux_pedido_uuid_cliente ON Pedido (uuid_cliente) WHERE uuid_cliente IS NOT NULL;
-- creado_por (ya existe): la API guarda ahí el username del vendedor; los pedidos de la PC siguen en NULL.

-- Rol de la API, sin superusuario (la clave se define al aplicarlo, no se versiona):
--   CREATE ROLE movil_api LOGIN PASSWORD '...';
--   GRANT SELECT ON Cliente, Producto TO movil_api;
--   GRANT SELECT (id, username, password_hash, nombre, activo) ON usuario TO movil_api;
--   GRANT SELECT, INSERT ON Pedido, DetallePedido TO movil_api;
--   GRANT USAGE ON SEQUENCE pedido_id_pedido_seq, detallepedido_id_detalle_seq TO movil_api;
```

- **Login**: `usuario.username` + clave contra `password_hash` (bcrypt). Debe estar `activo`. El vendedor usa la misma
  clave que ya tiene en esa tabla. El token firmado dura 7 días (la cola offline tiene que sobrevivir un fin de semana).
- **Revocar a alguien**: `UPDATE usuario SET activo = false` (se chequea en cada pedido) y sacar el celular de Tailscale.
- **Límite de intentos**: en memoria de la API (sin tocar `usuario`). Se reinicia con el servicio. Si hace falta algo
  persistente, se agregan columnas nulas a `usuario` más adelante.
- **Anti-duplicados**: `uuid_cliente` lo genera el celular. `INSERT … ON CONFLICT (uuid_cliente) DO NOTHING` y se devuelve
  el pedido ya existente.

## Endpoints

| Ruta | Función |
|---|---|
| `POST /auth/login` | `username` y clave → token |
| `GET /catalogo` | clientes `{id, nombre, cuit, localidad}`, productos `{id, nombre}` y una versión. **Sin teléfono, dirección ni saldos** |
| `POST /pedidos` | `{uuid, id_cliente, fecha_pedido, lineas:[{id_producto, cantidad}]}`. Idempotente |
| `GET /health` | prueba de conexión |

Validaciones de `POST /pedidos` (las mismas que la PC): cliente y productos existentes, `1 ≤ cantidad ≤ 9999`, líneas
repetidas se suman, máximo ~100 líneas, `precio_unitario = 0` (igual que hoy), estado inicial `pendiente`,
`origen = 'movil'`, `creado_por = username`.

## Cómo lo ve la PC

Nada que cambiar: `DatabaseSyncManager` revisa la base cada 8 s y al detectar un pedido nuevo muestra el aviso
"Nuevo Pedido" y recarga la lista. Mejora opcional futura: mostrar quién lo tomó (`creado_por`) en el aviso.

## Riesgos

- **HTTPS**: el service worker y la instalación de la PWA exigen HTTPS en el celular. Se resuelve con certificados de
  Tailscale (`tailscale serve`), pero **hay que probarlo con un celular real antes de escribir la pantalla** (Tarea 6).
- **Cartera completa en cada celular** (todos los clientes): por eso el catálogo lleva solo nombre, CUIT y localidad, y
  se vence a los pocos días. Un celular perdido se corta quitándolo de Tailscale.
- **Servidor = PC de escritorio**: si se apaga no hay servicio; la cola offline lo cubre en parte.
- La clave de la base está escrita por defecto en `programarPedido.py` (repo): conviene sacarla a `.env`.
- Maxi, Angeles y Julieta no tienen usuario: si van a cargar pedidos hay que darles uno en `usuario`.

## Plan de trabajo

Una tarea por sesión. Marcar al terminar.

- [x] **0. Esquema real del servidor** (solo lectura): hecho, ver hallazgos arriba.
- [x] **1. `sql/001_movil.sql` + rol `movil_api`.** Hecho (22/10/2026): `movil/sql/001_movil.sql` (DDL aditivo) + `movil/migraciones.py` (`aplicar(con)`, `asegurar_rol(con, password)`, sin commit — igual que `reclamos_db.py`). Test `movil/tests/verificar_migracion.py`, 16 checks OK dentro de una transacción revertida.
- [x] **2. Esqueleto de la API** + `/health` + `config.py` + `requirements.txt`. Hecho (22/10/2026): `movil/api/app.py` (FastAPI + `/health`, separa estado de la API del estado de la base), `movil/api/config.py` (variables de entorno obligatorias, sin defaults inseguros), `movil/api/db.py` (conexión con el rol `movil_api`), `movil/requirements.txt`, `movil/env.example` (sandbox bloquea archivos `.env*`: se documenta con ese nombre, copiar a `.env` a mano). Test `movil/tests/verificar_api.py` con `TestClient`, 4 checks OK.
- [x] **3. Login:** bcrypt contra `usuario`, token con vencimiento, límite de intentos. Hecho (22/10/2026): `movil/api/auth.py` (bcrypt + JWT HS256 a mano, sin `pyjwt` — ver gotcha arriba), `movil/api/schemas.py`, `movil/api/routers/auth.py` (`POST /auth/login`), `buscar_usuario` en `db.py`. Tests `verificar_auth.py` (lógica, 17 checks) y `verificar_login_api.py` (cableado HTTP, 6 checks), todo OK.
- [x] **4. `GET /catalogo`.** Hecho (22/10/2026): `db.catalogo(con)` (cliente: id/nombre/cuit/localidad; producto: id/nombre — ninguno expone teléfono/dirección/stock), `version` = sha256 del contenido (para que el celular sepa si cambió sin re-bajar todo), `movil/api/deps.py` (`usuario_actual`: exige `Authorization: Bearer`, lo usan todas las rutas salvo login/health), `routers/catalogo.py`. Test `movil/tests/verificar_catalogo.py`: 11 checks, contra la base real (2.104/1.425 confirmados, solo lectura) + wiring HTTP con datos falsos.
- [x] **5. `POST /pedidos` idempotente.** Hecho (22/10/2026): `movil/api/pedidos.py` (valida/suma líneas), `db.crear_pedido`/`cliente_existe`/`productos_inexistentes`, `routers/pedidos.py`. Idempotencia por `uuid_cliente` con `INSERT ... ON CONFLICT ... DO NOTHING` (ver el fix al índice parcial arriba). Tests `verificar_pedidos_logica.py` (11 checks, sin base), `verificar_pedidos_api.py` (17 checks contra la base real dentro de una transacción revertida — nuevo, repetido, producto inexistente, y que `check_for_changes` de la PC lo ve) y `verificar_pedidos_http.py` (7 checks de cableado HTTP). Todo OK.
- [x] **6. Prueba de HTTPS con Tailscale:** `/health` abierto desde un celular real. Hecho (22/10/2026) en Penxita (ver nota arriba). `tailscale serve --bg http://127.0.0.1:8000`, no `tailscale serve https / <target>`.
- [x] **7. PWA base:** manifest, service worker, pantalla de login. Hecho e instalada en el celular real (22/10/2026), confirmado por el usuario.
- [x] **8. Catálogo en IndexedDB + buscador de cliente sin conexión.** Hecho y confirmado en modo avión real en el celular (22/10/2026).
- [x] **9. Pantalla de pedido:** productos, cantidades, validaciones. Hecho y confirmado en el celular real (22/10/2026), ver nota arriba (hizo falta cerrar y reabrir la app instalada para ver la versión nueva).
- [x] **10. Cola offline + sincronización + estado de cada envío.** Hecho (23/10/2026), ver nota arriba. Probado en navegador contra la base real (llega una sola vez, incluso con la respuesta perdida); falta repetirlo en el celular con modo avión real.
- [x] **11. Servicio de Windows** y documentación final. Hecho (23/10/2026), ver nota arriba: tarea programada + `run.py` + `README.md`. Instalada por el usuario en el servidor con `deploy\instalar_servicio.ps1` y funcionando (23/10/2026).
- [ ] **12. Prueba de campo** con un vendedor durante una jornada.


---

## Fase 2 — Usuario de reparto (23/10/2026)

Un perfil único `reparto` (usuario `reparto`) que ve los pedidos ya programados y los marca como entregados, desde la misma PWA. Supuestos: se usa desde el celular (PWA), la entrega es **completa** (la parcial sigue en la PC) y ve pedidos en estado `programado` y `en camino`.

- [x] **R1. Base y permisos.** `movil/migraciones.py::asegurar_permisos` (nuevo: `movil_api` lee `usuario.rol` y puede UPDATE solo `pedido.estado_pedido/fecha_entrega` y `detallepedido.cantidad_entregada`; nada de DELETE ni cambiar cliente/cantidad) y `movil/usuarios.py::crear_usuario` (bcrypt). Tests: `verificar_migracion.py` (ampliado) y `verificar_usuarios.py`. **Aplicado en la base real (23/10/2026)** en una sola transacción: usuario `reparto` (clave `<clave-privada>`, rol `reparto`, sin vendedor), permisos nuevos de `movil_api` y la columna `cliente.ubicacion_maps` (`sql/002_reparto.sql`: texto, NULL por defecto, CHECK que solo deja pasar `http(s)://`; el ImportThread de la PC no la pisa porque nombra sus columnas). Ojo: hasta desplegar R2, la API vieja no distingue roles y `reparto` podría entrar como si fuera vendedor.
- [x] **R2. API: roles.** Hecho (23/10/2026, **todavía sin desplegar en el servidor**). `db.rol_activo` (rol leído de la base en cada petición, igual que `activo`: un cambio de rol o una baja surte efecto al instante con el mismo token) y `deps.exigir_rol(*roles)` (401 = baja/sin token, 403 = perfil sin permiso). `deps.vendedor_actual` (vendedor + admin) protege `GET /catalogo` y `POST /pedidos`; `usuario_actual` desapareció. `POST /auth/login` ahora devuelve `rol`. Tests: `verificar_roles.py` (matriz de roles por HTTP + `rol_activo` contra la base real con los permisos de `movil_api`); se actualizaron `verificar_login_api/catalogo/pedidos_http`. Efecto hasta R4: un `reparto` que entre a la app actual ve la pantalla de vendedor y recibe 403 al sincronizar el catálogo.
- [x] **R3. API: reparto.** Hecho (23/10/2026, sin desplegar): `movil/api/routers/reparto.py` + `db.pedidos_para_reparto` / `db.marcar_entregado`, solo rol `reparto` (`deps.reparto_actual`). `GET /reparto/pedidos`: programados y en camino ordenados por fecha de entrega (sin fecha al final), con líneas (cantidad/entregada) y datos del cliente. `POST /reparto/pedidos/{id}/entregar`: entrega COMPLETA como "Entrega Completa" de la PC (líneas = cantidad, estado 'entregado', fecha_entrega = HOY, no la programada); idempotente (ya entregado -> 200 con `ya_estaba=true`), 404 si no existe, 409 si todavía está 'pendiente'; la fila se bloquea (`FOR UPDATE`) para que dos celulares no se pisen y todo va en una transacción. Tests: `verificar_reparto_http.py` y `verificar_reparto_db.py` (base real como `movil_api`, transacción revertida; incluye que la PC lo ve en "Entregados (última semana)"). No se guarda quién entregó (no hay columna; se puede agregar). Descripción original:  `GET /reparto/pedidos` (programados y en camino, con sus líneas, y del cliente: dirección, teléfono y `ubicacion_maps`; decisión del usuario 23/10/2026: el reparto SÍ ve dirección y teléfono, solo de los pedidos de su lista) y `POST /reparto/pedidos/{id}/entregar` (idempotente: si ya está entregado devuelve OK).
- [x] **R4. PWA: pantalla de reparto.** Hecho (23/10/2026, sin desplegar; `CACHE_NAME` = `mana-pedidos-v8`). El login guarda el `rol` (`Api.rol()`; las sesiones viejas sin rol cuentan como vendedor) y `login.js` muestra la pantalla que corresponde. `pantalla-reparto`: tarjetas agrupadas por día de entrega (Atrasadas / Hoy / Mañana / días siguientes / Sin fecha) con cliente, estado, dirección, mapita (`js/mapa-mini.js`: grilla 3x3 de teselas de OpenStreetMap, el punto al centro, tocarlo abre el enlace de Maps; atribución obligatoria), "Cómo llegar" (enlace cargado > coordenadas; SIN búsqueda por dirección: las del sistema viejo son imprecisas y Maps mostraba cualquier lugar. Sin ubicación cargada dice "Sin ubicación cargada", v8), "Llamar" (`tel:`), productos desplegables y "Marcar entregado" con confirmación (`js/reparto.js`). Se actualiza al abrir la app, al volver la conexión, cada 60 s y con ↻; no redibuja si la lista no cambió. Un 403 (le cambiaron el perfil) lleva al login con el aviso "Tu perfil cambió". Necesita conexión (ver R5). Probado en el navegador contra un servidor de prueba con datos en memoria (la API real con la base reemplazada): login, lista, mapa, entrega y 403; vendedor sin cambios. Test nuevo `verificar_pwa.py` (todo archivo de la app está en `CASCARON`, ids del HTML). Confirmado en celulares reales (24/10/2026), ver R4c.
- [x] **R4b. Ubicación del cliente en el escritorio.** Hecho (23/10/2026). Se guarda en el cliente (`cliente.ubicacion_maps` + `ubicacion_lat/lng`, aplicado en la base real): se carga una vez y vale para todos sus pedidos. En el detalle del pedido hay una tarjeta "Ubicación" (`src/Views/Pedidos/mapa_ubicacion.py`): con enlace muestra un mapita (teselas de OpenStreetMap, en un hilo, con caché en `%LOCALAPPDATA%\ManaInformes\teselas`; la licencia exige la atribución, que se dibuja sobre el mapa) y al tocarlo abre el enlace en Google Maps; "Cambiar" permite pegar otro enlace o vaciarlo; sin enlace invita a cargarlo. Las coordenadas se leen del enlace al guardarlo (`src/controllers/ubicacion_maps.py`; los enlaces cortos `maps.app.goo.gl` se resuelven siguiendo la redirección). Si no se pueden leer, se guarda igual el enlace y la tarjeta ofrece solo abrirlo. Test: `tests/verificar_ubicacion_maps.py` (sin internet). Para la PWA de reparto (R3/R4): el API devuelve enlace + lat/lng y la app muestra un mapa embebido y el botón "Cómo llegar".
- [x] **R4c. El reparto carga la ubicación con su GPS.** Hecho (23/10/2026, sin desplegar; `CACHE_NAME` = `mana-pedidos-v9`). En cada tarjeta sin ubicación, "Guardar mi ubicación actual" (`navigator.geolocation`, exige HTTPS: ya lo da Tailscale): confirma "¿Estás en el lugar de X?", avisa si la precisión es peor que 50 m y manda `POST /reparto/clientes/{id}/ubicacion` {lat, lng}. La API (`db.guardar_ubicacion_cliente`) guarda coordenadas redondeadas a 6 decimales y un enlace de Maps de ese punto (`db.enlace_maps`; la PC lo lee y dibuja su mapita), solo si el cliente tiene una entrega pendiente (404 si no) y NUNCA pisa una ubicación ya cargada (409; si la de la oficina está mal, se corrige desde la PC con "Cambiar"). Permiso nuevo aplicado en la base real: `GRANT UPDATE (ubicacion_maps, ubicacion_lat, ubicacion_lng) ON cliente TO movil_api` (nada más de `cliente`). Tests: `verificar_reparto_http/db.py`, `verificar_migracion.py`; probado en el navegador con GPS simulado (confirmaciones, precisión baja, guardado, permiso denegado). **Confirmado por el usuario en celulares reales (24/10/2026): el mapa, "Cómo llegar" y la carga con GPS funcionan bien.**
- [x] **R5. Reparto sin señal.** Hecho (24/10/2026, sin desplegar; `CACHE_NAME` = `mana-pedidos-v10`). Las entregas y las ubicaciones del reparto pasan SIEMPRE por una cola local (`js/cola-reparto.js`, IndexedDB v3, store `cola_reparto`): se guardan primero en el teléfono y se mandan en orden al volver la señal (evento `online`, al abrir/volver a la app y cada 30 s). Estados pendiente / enviado / rechazado, igual que la cola de pedidos; reintentar es seguro (entregar un pedido ya entregado responde OK; una ubicación que ya estaba cargada, 409, se da por resuelta). Sin señal la tarjeta muestra "Por enviar", una nota y "Deshacer"; la ubicación guardada se ve ya en el mapa. La última lista se guarda en el teléfono (`MetaDB`, clave `reparto_lista`, por usuario) y se ve al abrir la app sin señal con el aviso "Sin conexión · lista de las HH:MM"; se borra al tocar Salir (no al vencer la sesión). Al salir con acciones sin enviar se pide confirmación. Servidor: la ubicación se acepta también para clientes con una entrega de los últimos 3 días (si llega después de sincronizar la entrega). Probado en el navegador contra el servidor de prueba cortando la red desde la página (guardar, reabrir sin señal, volver la señal, rechazo 409 y descarte); falta probarlo en un celular real con modo avión.
- [ ] **R6. Pruebas, docs y despliegue.** Tests de roles (un vendedor no entrega, reparto no crea pedidos), subir `CACHE_NAME`, README, actualizar el servidor.

---

## Fase 3 — Rol admin y panel de control (24/10/2026)

El admin ve en el celular todas las pantallas (Pedidos = la carga de pedidos de siempre, Reparto) y una pestaña **Panel** con: litros vendidos en el mes, % premium y dinero recaudado en la semana.

- [x] **P1. Admin con pestañas Pedidos | Reparto.** Hecho (24/10/2026, sin desplegar; `CACHE_NAME` = `mana-pedidos-v11`). `deps.reparto_actual` ahora admite `reparto` y `admin` (el admin también puede marcar entregas y guardar ubicaciones; si se lo quiere solo-lectura, se cambia ahí). PWA: barra de secciones fija abajo (`js/admin.js`, solo para admin), la sesión admin arranca en Pedidos; al pasar a Reparto se inicia/refresca esa pantalla; al salir se pide confirmación si hay pedidos, entregas o ubicaciones sin enviar. El usuario `admin` ya existe en la base pero **no tiene clave conocida**: asignarla con `claves.py fijar admin`. Probado en el navegador con el servidor de prueba (login, cambio de pestaña, salir).
- [x] **P1b. Rol `superadmin` y quiénes son admin.** Hecho (24/10/2026, sin desplegar; `CACHE_NAME` = `mana-pedidos-v12`). Decisión del usuario: **admin** serán Miguel, Martin y Diego/Maxi (siguen pudiendo cargar pedidos: el admin hace todo lo del vendedor); **superadmin** será Juan (usuario nuevo): todo lo del admin y "más control sobre la app" (qué más: a definir; candidato natural, gestionar usuarios desde la app). API: `deps.ROLES_ADMIN = (admin, superadmin)`; `vendedor_actual` y `reparto_actual` los admiten; la PWA muestra la barra de secciones con `Api.esAdmin()`. Herramienta `claves.py`: `rol <usuario> <rol>` y `crear <usuario> --nombre N --rol R` (pide la clave por consola). Los roles se asignan corriendo esos comandos en el servidor (no se tocó la base real). Pendiente de confirmar: quién es "Maxi/Diego" (hay usuario `diego`; Maxi no tiene usuario).
- [x] **P2. Cálculo de los datos del panel.** Hecho (24/10/2026, sin desplegar): paquete `movil/panel/` (`litros.py`, `recaudado.py`, `lectura.py`, `calculo.py`; pandas + dbfread + openpyxl, ver `requirements-panel.txt`; sin Qt). El mapa de medidas y las reglas de litros son una COPIA de `LitrosDBF.py` (el `.exe` y `movil/` no se pueden importar entre sí): `tests/verificar_panel_paridad.py` falla si difieren. **Verificado contra el escritorio con datos reales el 24/10/2026: coincide al centavo** — litros del mes 55.910,27 L, premium 16.320 L (29,2 %), idéntico a `ReportLts`; recaudado de la semana $89.818.223,02 en 85 recibos, idéntico al cálculo con los datos de Cuentas Corrientes (y ningún recibo con importe positivo). Cada cifra trae su comparación con el período anterior hasta el mismo día (mes anterior; semana anterior) y series por día para gráficos. Leer `fachist.DBF` (80 MB) con dbfread tarda ~30 s por la red (menos en el servidor, que lo tiene local): por eso P3 solo recalcula si los archivos cambiaron. Tests: `movil/tests/verificar_panel.py` (datos inventados, rápido). Definiciones: **litros del mes** = misma lógica del informe de Litros (ventas `TC` en FC/NC/ND/FE/CR, litros por unidad desde `abmartic.CODMEDIDA`); **% premium** = litros Premium (Shell, según `LITROS SHELL.xlsx`) / litros totales, como el KPI "Total Premium" del escritorio; **recaudado de la semana** = suma de los recibos (`ctacorr`, `TC = RC`, importes negativos: se toma el valor absoluto) con fecha en la semana (medido el 24/10: ~$89,8 M lun-vie esta semana, entre $52 M y $90 M las anteriores). **Semana = siempre desde el lunes de la semana correspondiente** (decisión del usuario, 24/10/2026): por defecto la semana en curso, lunes a hoy; se compara con la semana anterior hasta el mismo día.
- [x] **P3. Que el servidor los calcule solo.** Hecho (24/10/2026; el código está listo, **falta instalarlo en el servidor**). `movil/panel/worker.py`: proceso aparte (tarea programada `ManaPanelMovil`, instalador `deploy/instalar_panel.ps1`) que cada `PANEL_INTERVALO_SEG` (300 s) mira tamaño y fecha de `fachist/abmartic/ctacorr/LITROS SHELL.xlsx` y recalcula SOLO si cambiaron o cambió el día; guarda el resultado en la tabla `panel_resumen` (una sola fila, `sql/003_panel.sql`, **ya creada en la base real**, vacía; `movil_api` puede SELECT/INSERT/UPDATE, no DELETE). Si los archivos cambian mientras se leen, no guarda un resultado a medias; si el cálculo falla, los datos anteriores quedan y el error se guarda en la fila (la API lo va a informar) y el ciclo siguiente reintenta. Corrida real de prueba (descartada, por la red desde Penxita): 41 s, JSON de ~2 KB; el segundo ciclo da `sin_cambios`. Dependencias en el servidor: `pip install -r movil\requirements-panel.txt` (pandas, dbfread, openpyxl). Opcionales del `.env`: `PANEL_BASE_PATH` (por defecto `D:/tiempo`) y `PANEL_INTERVALO_SEG`. Log: `movil\logs\panel.log`. Tests: `verificar_panel_worker.py` (cuándo recalcula, errores, permisos como `movil_api`).
- [x] **P4. API `GET /panel`.** Hecho (24/10/2026, sin desplegar). Solo `admin` y `superadmin` (`deps.panel_actual`). No calcula nada: entrega lo que dejó el proceso del servidor (`almacen.leer_para_api`): `datos`, `calculado_en`, `verificado_hace_seg`, `desactualizado` y `error`. Se agregó un **latido**: el proceso anota `panel_resumen.verificado_en` en cada ciclo (aunque no haya nada que recalcular) y la API marca `desactualizado` si pasan más de 15 minutos sin latido (el proceso revisa cada 5): si la tarea del servidor se cae, el celular lo avisa en vez de mostrar números viejos sin decir nada. Columna ya aplicada en la base real (la fila que dejó el proceso del servidor tiene `verificado_en` vacío hasta que se actualice a esta versión; la API mide contra `calculado_en` mientras tanto). 503 con el motivo si todavía no hay datos. Tests: `verificar_panel_api.py`.
- [x] **P5. Pestaña Panel en la app.** Hecho (24/10/2026, sin desplegar; `CACHE_NAME` = `mana-pedidos-v13`). Tercera pestaña de la barra del admin (Pedidos | Reparto | Panel; `js/panel.js` + `js/graficos.js`, SVG armado con DOM, sin librerías). Tres tarjetas: **Litros vendidos** (cifra del mes, variación contra el mes anterior hasta el mismo día, barras por día del mes con lo premium apilado), **Premium** (anillo con el %, litros premium y resto, variación en puntos) y **Recaudado** (cifra de la semana, recibos, variación contra la semana anterior al mismo día, barras de lunes a domingo en millones). Los gráficos se dibujan al ancho real de su tarjeta (una columna en el celular, dos en pantallas anchas) y se redibujan al girar. Avisa si el proceso del servidor no da señales, si el último cálculo falló, o si no hay conexión (en ese caso muestra la última respuesta guardada en el teléfono, que se borra al salir: son números del negocio). `/reparto` y `/panel` se agregaron a las rutas que el service worker no toca. Probado en el navegador con el servidor de prueba y los DATOS REALES del panel (55.915 L, 29,2 %, $ 89,8 M en 85 recibos): celular, pantalla ancha, aviso de proceso caído, sin conexión y 503. Falta verlo en un celular real.
- [ ] **P6. Despliegue y documentación.**

- [x] **P7. Filtro de productos en el panel (Shell / Valvoline / Otros / Todos).** Hecho (24/10/2026, sin desplegar; `CACHE_NAME` = `mana-pedidos-v14`). Pedido del usuario: poder marcar productos de Shell, Valvoline, Otros o todos, como los checkboxes del escritorio. El cálculo (`movil/panel/litros.py`) ahora guarda el desglose por proveedor del mes, del mes anterior y de **cada día** (`por_proveedor`, `proveedores`), y `calculo.VERSION = 2` entra en la firma del proceso del servidor (`worker.firma_completa`): al actualizar el programa se recalcula solo aunque los archivos del sistema no hayan cambiado. En la app, botones **Todos | Shell | Valvoline | Otros** (`js/panel.js`): el primer toque aísla ese proveedor, los siguientes suman o quitan, y sin ninguno vuelve a Todos; la elección queda guardada en el teléfono. Afecta a las tarjetas de Litros (cifra, variación contra el mes anterior, barras por día) y de Premium (que se recalcula sobre lo elegido: sin Shell dice que el premium es solo de Shell). El recaudado no se filtra. Todo se recalcula en el teléfono con el desglose: no hay llamadas nuevas. Si el servidor todavía manda el formato anterior (sin desglose), el filtro no aparece y se ve todo. Verificado contra el escritorio con datos reales: Shell 46.488 L (16.333 premium), Valvoline 2.871 L, Otros 6.564,27 L, idénticos a la tabla del informe de Litros (`tests/verificar_panel_paridad.py`). Probado en el navegador: selección individual, combinada, vacía, persistencia al recargar y una sola fila de botones en pantalla angosta.

- [x] **P8. Desglose del recaudado semanal (efectivo / transferencia / cheques).** Hecho (29/10/2026, sin desplegar; `CACHE_NAME` = `mana-pedidos-v15`, `calculo.VERSION = 3`). En la app, la tarjeta Recaudado trae al pie "Cómo se cobró" (`js/panel.js::seccionDesglose`, `Graficos.proporcion` en `js/graficos.js`): barra de proporciones + una fila por medio (efectivo, transferencia, cheques; retenciones y otros solo si no son cero) con monto y porcentaje, y un aviso ámbar si `diferencia` no es 0. Un servidor con el formato anterior (sin desglose) simplemente no muestra esa parte. Probado en el navegador con los datos reales del cálculo (servidor de prueba en memoria): celular de 375 px, 1000 px, con "otros" y diferencia, y sin desglose. Análisis previo (solo lectura, datos reales, 9 semanas y 957 recibos): `plan_caj.DBF` es la cabecera de cada comprobante con una columna por medio de pago (`EFECTIVO`, `CHEQUES`, `BANCO`, `RETENCION`, `TARJETAS`...) y `placaja.DBF` los movimientos de caja, cuyo campo `CAJA` vale `CAJA` (efectivo real) o `TRANSF` (transferencia); se ligan por `placaja.NCASOCIADO = plan_caj.NC` (recibos: `TM='I'`, `DETALLE='RECIBO DE CLIENTES'`). Reglas (`panel/recaudado.py::desglose`): efectivo = `placaja` `CAJA`; transferencia = `placaja` `TRANSF` + `plan_caj.BANCO` (confirmado por el usuario que `BANCO` es una transferencia); cheques = `CHEQUES`; retenciones = `RETENCION`; **otros** = lo que falta hasta `TOTALL` (tarjetas, o un recibo que no se pudo ligar), visible y aparte para no esconder diferencias. Verificado: `EFECTIVO` de `plan_caj` = `CAJA` + `TRANSF` de `placaja` en el 100 % de los recibos desde 2023, y la suma semanal de `TOTALL` de `plan_caj` es igual al centavo a la de `ctacorr` (la que el panel ya mostraba). Por eso cada semana trae `desglose.diferencia` (control cruzado `ctacorr` − `plan_caj`; si no es 0, algo no cuadra). **Gotchas:** (1) en la historia vieja (2018-2022) los números de recibo se repiten y el cruce falla, así que el cruce se hace solo dentro del período, y si un número aparece dos veces en el período el cobro se asigna a uno solo; (2) `placaja.DBF` trae fechas y números vacíos como bytes nulos y `dbfread` los rechaza: `lectura.leer_dbf(..., tolerante=True)`; (3) `plan_caj` y `placaja` entran a la firma del proceso del servidor (si no están, el cálculo falla y lo informa); (4) hay 143 recibos anulados en la historia, ninguno en el último año: no se filtran, si aparecieran la `diferencia` lo mostraría. Pruebas: `movil/tests/verificar_panel.py` (datos inventados) y `tests/verificar_panel_paridad.py` sección 4 (semana cerrada 19-25/10/2026: $95.868.623,02 = efectivo $10.474.725,58 + transferencia $28.812.816,31 + cheques $55.812.436,87 + retenciones $768.644,26).

## Fase 4: avisos (notificaciones push) a los celulares

Pedido del usuario (29/10/2026): con la app en segundo plano, avisar de tres cosas. Destinatarios confirmados: **pedido nuevo de un vendedor** (`origen='movil'`) -> admin y superadmin; **pedido programado** -> reparto; **pedido entregado** -> admin, superadmin y el vendedor que lo cargó (`pedido.creado_por` guarda su `username`). Web Push (VAPID): es la única forma confiable de avisar con la app cerrada. Los avisos pasan por los servidores de Google/Apple (el contenido va cifrado); el celular los recibe sin Tailscale, pero abrir la app sí lo necesita; en iPhone solo anda con la app instalada en la pantalla de inicio (iOS 16.4 o más). Los cambios de estado los hace la PC directo en Postgres y `pedido` no tiene triggers ni fecha de cambio de estado: un proceso nuevo del servidor (`ManaNotificadorMovil`) mira la tabla cada ~20 s y compara contra lo ya avisado.

- [x] **N1. Tablas y permisos.** Hecho (29/10/2026, sin aplicar en la base real). `sql/004_notificaciones.sql`: `push_suscripcion` (un renglón por celular: `endpoint` único, claves `p256dh`/`auth`, clave foránea a `usuario` con borrado en cascada) y `notificacion_enviada` (clave `(evento, id_pedido)`, evento = nuevo/programado/entregado: evita repetir avisos y que al instalarse mande uno por cada pedido existente). `migraciones.asegurar_permisos`: `movil_api` puede leer/insertar/actualizar/**borrar** suscripciones (única tabla con DELETE: es un dato propio de la app) y solo leer/insertar `notificacion_enviada`. Prueba en `tests/verificar_migracion.py` (transacción que se revierte). Para aplicarla en producción: `migraciones.aplicar` + `asegurar_permisos`, como en las fases anteriores.
- [x] **N2. Claves VAPID y endpoints.** Hecho (29/10/2026, sin desplegar). `GET /push/clave` (la clave pública VAPID; 503 si el servidor no tiene avisos configurados, así la app no ofrece el botón), `POST /push/suscribir` y `POST /push/baja` (`routers/push.py`; los usan todos los perfiles, `deps.avisos_actual`). La suscripción es idempotente (la app la manda al abrir), si el mismo celular entra con otro usuario pasa a ese usuario y cada usuario conserva como mucho 10 dispositivos. **Seguridad:** el `endpoint` lo manda el celular y después el servidor le hace un POST: solo se acepta https de los servicios de push conocidos (`fcm.googleapis.com`, `*.push.services.mozilla.com`, `*.push.apple.com`, `*.notify.windows.com`, sin usuario ni puerto raro, máx. 1024 caracteres); si no, cualquier usuario podría hacer que el servidor le pegue a una dirección de la red interna (SSRF). Las claves de la suscripción se validan (p256dh = punto P-256 de 65 bytes, auth = 16 bytes). Las claves VAPID se generan una sola vez con `python movil\vapid.py --contacto mailto:...` (`movil/vapid.py`): agrega `MOVIL_VAPID_PUBLICA/PRIVADA/CONTACTO` al `.env` y se niega a generar otras si ya hay (cambiarlas invalida todas las suscripciones). **Sin dependencias:** la curva P-256 está hecha con enteros de Python (verificada con el vector de la RFC 6979) porque en la máquina de desarrollo `cryptography` no carga (`import cryptography` anda pero su parte en Rust falla con `DLL load failed`; ojo, una comprobación solo de `import cryptography` engaña). Esto compromete N3: `pywebpush` necesita `cryptography`, así que hay que probar en el servidor si carga; si no, alternativa con `pycryptodome` (extensión en C) + firma ES256 propia. El contacto (correo o URL) viaja en cada aviso hacia Google/Apple: usar un correo/URL elegido a propósito. Pruebas: `verificar_push_http.py`, `verificar_push_db.py` (como `movil_api`, transacción que se revierte) y `verificar_vapid.py`. Pendiente para N4: agregar `/push` a `RUTAS_API` de `sw.js`.
- [x] **N3. Proceso notificador.** Hecho (29/10/2026, sin desplegar). Paquete `movil/avisos/`: `reglas.py` (lógica pura: qué se avisa, a quién, con qué texto), `almacen.py` (SQL), `envio.py` (Web Push con `pywebpush`, importado recién al crear el emisor) y `worker.py` (tarea `ManaAvisosMovil`, `python -m movil.avisos.worker`, `deploy/instalar_avisos.ps1`, `requirements-avisos.txt`, log `movil/logs/avisos.log`). Mira `pedido` cada 20 s (`AVISOS_INTERVALO_SEG`) y compara contra `notificacion_enviada`. **Reglas:** el aviso que corresponde es el del estado de AHORA; los pasos que el pedido ya superó sin avisarse (proceso apagado, o la PC lo pasó directo a entregado) se anotan como hechos pero NO se mandan (no avisar tarde de algo viejo); 'en camino' ya pasó por programado; un estado desconocido no genera nada; 'nuevo' solo para `origen='movil'`; quien cargó el pedido no recibe el aviso de pedido nuevo; no se avisa a usuarios dados de baja. **Entrega:** si no hay nadie suscripto el aviso se da por resuelto (si no, quien active los avisos mañana recibiría de golpe todo lo anterior); si a alguno le llega, resuelto; si TODOS fallan por motivos pasajeros se reintenta, y a la 5ª vez se rinde; 404/410 del servicio de push borra la suscripción (también un destino que no sea de un servicio conocido). **Siembra:** al arrancar con `notificacion_enviada` vacía anota como hecho todo lo existente (`--sembrar` fuerza). El contenido del aviso es mínimo (tipo, número de pedido, cliente, quién lo cargó o la fecha de entrega) y viaja cifrado. El proceso no arranca (código 2) si falta el `.env`, las claves VAPID (o la pública no corresponde a la privada) o `pywebpush`. Pruebas: `verificar_avisos_reglas.py` (reglas, configuración, envío con `pywebpush` simulado, arranque), `verificar_avisos_db.py` (ciclo completo contra la base real como `movil_api`, transacción que se revierte, envío simulado: 14 escenarios). **No se pudo probar con `pywebpush` real** (no carga en la PC de desarrollo): el instalador lo comprueba en el servidor y avisa qué hacer si falla (suele ser el Visual C++ Redistributable).
- [x] **N4. Service worker.** Hecho (29/10/2026, sin desplegar; `CACHE_NAME` = `mana-pedidos-v17`). `sw.js`: el evento `push` muestra el aviso SIEMPRE (el navegador lo exige) con título, texto, ícono de la app, la silueta monocromo `icons/badge-96.png` (la gota de la marca, para la barra de estado de Android: un ícono a color se ve como un cuadrado blanco) y `tag` (el mismo aviso no se apila dos veces); un aviso ilegible o con tipos raros se muestra igual con el título genérico, y solo se guarda el tipo de aviso (`nuevo|programado|entregado`). `notificationclick` cierra el aviso y, si la app está abierta, la trae al frente y le manda `{tipo:'aviso-tocado', evento}`; si no, la abre con `/?aviso=<evento>`. `/push` agregado a `RUTAS_API` (la API nunca se sirve desde el caché). Prueba en Node (`tests/verificar_sw_avisos.py`: carga `sw.js` con un `self` simulado; se omite si no hay Node), porque el navegador integrado no deja registrar un service worker.
- [x] **N5. Campana de avisos en la app.** Hecho (29/10/2026, sin desplegar). `js/avisos.js` + `css/avisos.css` (archivo aparte) + una campana en el encabezado de las 3 pantallas (`.boton-avisos`) y un mensaje breve (`#toast-avisos`). Estados: activo (campana llena), inactivo (con raya), bloqueado (ámbar, permiso denegado en el navegador). **Activar** exige un toque: pide el permiso, se suscribe con la clave de `GET /push/clave` y manda la suscripción a `POST /push/suscribir`; **desactivar** da de baja en el servidor y en el celular. La elección se guarda por usuario (`movil_avisos:<nombre>`: un mismo celular lo pueden usar varias personas) y, mientras el usuario los quiera, se renueva la suscripción en silencio cada vez que abre la app (cubre que el servidor la haya perdido). **Al salir** se da de baja este celular (mejor esfuerzo, máximo 3 s, directo con `fetch` para que un token vencido no dispare el aviso de sesión vencida), así el siguiente usuario del celular no recibe los avisos del anterior. La campana no aparece si el servidor no tiene avisos configurados (503) ni si el navegador no los soporta; en iPhone sin instalar la app aparece y explica que hay que agregarla a la pantalla de inicio. Si el servicio de push nunca termina de prepararse (`serviceWorker.ready`) hay un tope de 8 s para que la campana no quede ocupada para siempre. Un admin que toca un aviso de programado/entregado cae en Reparto (`mana:ir-a-seccion`, escuchado por `admin.js`). Probado en el navegador con la API real y la base reemplazada (sin permisos ni service worker reales: simulados en la página): alta, baja, bloqueado, 503, salir (baja) y volver a entrar (alta silenciosa), reparto y admin, ancho de celular; falta probarlo en un celular real (permiso, aviso con la app cerrada, tocar el aviso).
- [x] **N6. Pruebas, documentación y despliegue.** Hecho en el código (29/10/2026); **el despliegue lo corre el usuario** (nada se aplicó en la base real ni en el servidor). Hueco que se cerró: hasta ahora las migraciones a la base real las aplicaba yo con scripts sueltos; ahora hay `movil/migrar.py` (`--solo-verificar` muestra qué falta, sin cambiar nada; sin la opción aplica `migraciones.aplicar` + `asegurar_permisos` en UNA transacción: si algo falla no queda nada a medias; pide la clave del `postgres` por consola o `PEDIDOS_ADMIN_PASSWORD`), con test `verificar_migrar.py` (transacción que se revierte; si las tablas de los avisos ya existen las quita DENTRO de esa transacción, con un bloqueo breve, y se revierte). Estado de la base real verificado en solo lectura el 29/10/2026: solo faltaban las tablas de los avisos (004); 001 a 003 ya estaban. `README.md` quedó con el orden de instalación de los avisos (sección "Avisos") y la sección "Actualizar" con las tres tareas (`ManaPedidosMovil`, `ManaPanelMovil`, `ManaAvisosMovil`). **Orden del despliegue de esta tanda** (incluye lo anterior que todavía no estaba en el servidor: desglose del recaudado, el rediseño de la app y los avisos): (1) `python movil\migrar.py --host DESKTOP-R8E4V7S` desde cualquier PC; (2) `robocopy` al servidor; (3) en el servidor `pip install -r movil\requirements-avisos.txt` y comprobar que `pywebpush` carga (lo que no se pudo probar en la PC de desarrollo: si dice `DLL load failed`, instalar el Visual C++ Redistributable x64); (4) `python movil\vapid.py --contacto mailto:<elegido>`; (5) reiniciar la API y el panel (el panel recalcula solo por `calculo.VERSION = 3`); (6) `instalar_avisos.ps1` como administrador; (7) celulares: cerrar y reabrir la app, tocar la campana. Corrección del 29/10/2026: el comando original (`python -m movil.vapid`) falló en el servidor con `No module named 'movil'` porque hay que correrlo parado en la carpeta que CONTIENE `movil\`; ahora es `python movil\vapid.py --contacto mailto:...` y escribe en el `movil\.env` que tiene al lado, así anda desde cualquier carpeta. **Prueba de campo pendiente con un celular real:** permiso, aviso con la app cerrada, tocar el aviso, y que un pedido cargado desde otro celular llegue a los admin.

