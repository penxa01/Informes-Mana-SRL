// Cliente HTTP mínimo para la API móvil. Mismo origen que la PWA (la sirve
// el propio FastAPI, ver movil/api/app.py): rutas relativas, sin CORS.
const Api = (() => {
  const TOKEN_KEY = "movil_token";
  const NOMBRE_KEY = "movil_nombre";
  const ROL_KEY = "movil_rol";

  function token() {
    return localStorage.getItem(TOKEN_KEY);
  }

  function nombre() {
    return localStorage.getItem(NOMBRE_KEY);
  }

  // Las sesiones guardadas antes de que existieran los perfiles no tienen rol:
  // eran todas de vendedores.
  function rol() {
    return localStorage.getItem(ROL_KEY) || "vendedor";
  }

  // admin y superadmin ven todas las pantallas (la barra de secciones de admin.js).
  function esAdmin(rolUsuario = rol()) {
    return rolUsuario === "admin" || rolUsuario === "superadmin";
  }

  function guardarSesion(tok, nom, rolUsuario) {
    localStorage.setItem(TOKEN_KEY, tok);
    localStorage.setItem(NOMBRE_KEY, nom);
    localStorage.setItem(ROL_KEY, rolUsuario || "vendedor");
  }

  function borrarSesion() {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(NOMBRE_KEY);
    localStorage.removeItem(ROL_KEY);
  }

  const TIMEOUT_MS = 20000;

  // FastAPI devuelve `detail` como texto (nuestros errores) o como lista de
  // objetos (validación de Pydantic, 422): en ese caso juntamos los `msg`.
  function mensajeDeError(cuerpo, status) {
    const detalle = cuerpo && cuerpo.detail;
    if (typeof detalle === "string") return detalle;
    if (Array.isArray(detalle)) return detalle.map((d) => d.msg).join("; ");
    return `Error ${status}`;
  }

  async function llamar(ruta, opciones = {}) {
    const headers = { "Content-Type": "application/json", ...(opciones.headers || {}) };
    const t = token();
    if (t) headers.Authorization = `Bearer ${t}`;

    // Sin timeout, una red "colgada" (señal mala) deja el fetch esperando para
    // siempre y traba la cola de envíos. Un timeout se trata igual que "sin red".
    const control = new AbortController();
    const reloj = setTimeout(() => control.abort(), TIMEOUT_MS);
    let res;
    try {
      res = await fetch(ruta, { ...opciones, headers, signal: control.signal });
    } catch (e) {
      throw e.name === "AbortError" ? new TypeError("Tiempo de espera agotado") : e;
    } finally {
      clearTimeout(reloj);
    }

    let cuerpo = null;
    try {
      cuerpo = await res.json();
    } catch (e) {
      // sin cuerpo JSON (ej. 204)
    }

    if (!res.ok) {
      // 401 fuera del login = el token venció: la app vuelve a la pantalla de
      // login (los pedidos sin enviar quedan guardados y se mandan al volver).
      // 403 = el servidor ya no le reconoce permiso para esto (le cambiaron el
      // perfil): también se vuelve al login para que entre con la pantalla que le toca.
      if ((res.status === 401 || res.status === 403) && ruta !== "/auth/login") {
        document.dispatchEvent(
          new CustomEvent("mana:sesion-vencida", { detail: { motivo: res.status === 403 ? "permiso" : "sesion" } })
        );
      }
      const error = new Error(mensajeDeError(cuerpo, res.status));
      error.status = res.status;
      throw error;
    }
    return cuerpo;
  }

  function login(username, clave) {
    return llamar("/auth/login", { method: "POST", body: JSON.stringify({ username, clave }) });
  }

  return { token, nombre, rol, esAdmin, guardarSesion, borrarSesion, llamar, login };
})();
