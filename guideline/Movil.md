# Móvil — toma de pedidos desde el celular (`movil/`)

**Estado: diseño aprobado, Tarea 0 hecha, Tarea 1 pendiente.** Todavía no existe la carpeta `movil/`.
Última actualización: 2026-10-22.

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
├── README.md                  cómo levantarlo y probarlo
├── requirements.txt           fastapi, uvicorn, psycopg2-binary, bcrypt, pyjwt
├── .env.example
├── api/
│   ├── app.py                 FastAPI: arma la app y registra routers
│   ├── config.py              lee PEDIDOS_DB_* (mismas variables que Pedidos) + secreto del token
│   ├── db.py                  conexión a Postgres (rol movil_api)
│   ├── auth.py                verificación bcrypt, token firmado con vencimiento, límite de intentos
│   ├── schemas.py             validación de entrada
│   └── routers/               auth.py · catalogo.py · pedidos.py
├── sql/001_movil.sql          migración idempotente (se puede aplicar dos veces)
├── tests/                     estilo tests/verificar_*.py, con rollback
├── pwa/                       JS puro
│   ├── index.html · manifest.webmanifest · sw.js
│   └── js/                    db.js (IndexedDB) · api.js · cola.js · login.js · pedido.js
├── deploy/                    servicio de Windows, pasos de Tailscale
└── tools/                     utilidades de consola (alta de rol, prueba de login)
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
- [ ] **1. `sql/001_movil.sql` + rol `movil_api`.** Prueba: aplicar dos veces dentro de una transacción revertida; un `INSERT` de la PC (sin las columnas nuevas) sigue andando; `movil_api` no puede leer `password_hash` de otro modo ni escribir en `Cliente`.
- [ ] **2. Esqueleto de la API** + `/health` + `config.py` + `requirements.txt`. Prueba: `TestClient`.
- [ ] **3. Login:** bcrypt contra `usuario`, token con vencimiento, límite de intentos. Prueba: clave mala, usuario inactivo, token vencido, bloqueo.
- [ ] **4. `GET /catalogo`.** Prueba: cantidades (2.104 / 1.425) y que no salgan teléfono ni dirección.
- [ ] **5. `POST /pedidos` idempotente.** Prueba: nuevo, repetido, producto inexistente, cantidad inválida; y que la consulta de `check_for_changes` de la PC lo vea.
- [ ] **6. Prueba de HTTPS con Tailscale:** `/health` abierto desde un celular real. (La hace el usuario, se lo guía.)
- [ ] **7. PWA base:** manifest, service worker, pantalla de login. Prueba: instalarla en el celular.
- [ ] **8. Catálogo en IndexedDB + buscador de cliente sin conexión.** Prueba: modo avión.
- [ ] **9. Pantalla de pedido:** productos, cantidades, validaciones. Prueba: cargar un pedido a mano.
- [ ] **10. Cola offline + sincronización + estado de cada envío.** Prueba: cargar en modo avión, reconectar, que llegue una sola vez.
- [ ] **11. Servicio de Windows** y documentación final. Prueba: reiniciar el servidor y comprobar que sube solo.
- [ ] **12. Prueba de campo** con un vendedor durante una jornada.
