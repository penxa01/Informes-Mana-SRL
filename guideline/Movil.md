# Móvil — toma de pedidos desde el celular (`movil/`)

**Estado: diseño aprobado, Tareas 0 a 11 hechas, Tarea 12 (prueba de campo) pendiente.** Tareas 0 a 9 confirmadas en
el celular real; la 10 (cola offline) probada de punta a punta en el navegador contra la base real, **falta
probarla en el celular con modo avión real**; la 11 (arranque automático) está lista y probada en la PC de
desarrollo, **falta instalarla en el servidor y hacer la prueba de reinicio real** (ver `movil/README.md`, sección
"Despliegue en el servidor"). **Gotcha de PWA instalada:** al actualizar `movil/pwa/` la app instalada sigue
mostrando la versión vieja hasta cerrarla del todo (no solo "atrás") y reabrirla.
Última actualización: 2026-10-23.

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
> - Todavía **no existe** una herramienta para asignar claves reales a los vendedores (solo `jose`/`matias` tienen
>   clave de prueba): pendiente antes de la prueba de campo.

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
- [x] **11. Servicio de Windows** y documentación final. Hecho (23/10/2026), ver nota arriba: tarea programada + `run.py` + `README.md`. **Falta la prueba real en el servidor** (instalarla con `deploy\instalar_servicio.ps1` como administrador, reiniciar el equipo y comprobar que `/health` responde sin iniciar sesión).
- [ ] **12. Prueba de campo** con un vendedor durante una jornada.
