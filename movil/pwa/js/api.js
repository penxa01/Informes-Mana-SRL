// Cliente HTTP mínimo para la API móvil. Mismo origen que la PWA (la sirve
// el propio FastAPI, ver movil/api/app.py): rutas relativas, sin CORS.
const Api = (() => {
  const TOKEN_KEY = "movil_token";
  const NOMBRE_KEY = "movil_nombre";

  function token() {
    return localStorage.getItem(TOKEN_KEY);
  }

  function nombre() {
    return localStorage.getItem(NOMBRE_KEY);
  }

  function guardarSesion(tok, nom) {
    localStorage.setItem(TOKEN_KEY, tok);
    localStorage.setItem(NOMBRE_KEY, nom);
  }

  function borrarSesion() {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(NOMBRE_KEY);
  }

  async function llamar(ruta, opciones = {}) {
    const headers = { "Content-Type": "application/json", ...(opciones.headers || {}) };
    const t = token();
    if (t) headers.Authorization = `Bearer ${t}`;

    const res = await fetch(ruta, { ...opciones, headers });
    let cuerpo = null;
    try {
      cuerpo = await res.json();
    } catch (e) {
      // sin cuerpo JSON (ej. 204)
    }

    if (!res.ok) {
      const mensaje = (cuerpo && cuerpo.detail) || `Error ${res.status}`;
      throw new Error(mensaje);
    }
    return cuerpo;
  }

  function login(username, clave) {
    return llamar("/auth/login", { method: "POST", body: JSON.stringify({ username, clave }) });
  }

  return { token, nombre, guardarSesion, borrarSesion, llamar, login };
})();
