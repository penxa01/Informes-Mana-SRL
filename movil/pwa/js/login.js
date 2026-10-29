// Pantalla de login: envía usuario/clave, guarda el token y muestra la app.
// Si ya había una sesión guardada (el token dura 7 días), la saltea.
(() => {
  const form = document.getElementById("form-login");
  const inputUsername = document.getElementById("username");
  const inputClave = document.getElementById("clave");
  const elError = document.getElementById("error-login");
  const btn = form.querySelector('button[type="submit"]');

  const pantallaLogin = document.getElementById("pantalla-login");
  const pantallaApp = document.getElementById("pantalla-app");
  const nombreUsuario = document.getElementById("nombre-usuario");
  const btnSalir = document.getElementById("btn-salir");

  const pantallaReparto = document.getElementById("pantalla-reparto");
  const nombreReparto = document.getElementById("nombre-reparto");
  const btnSalirReparto = document.getElementById("btn-salir-reparto");

  const pantallaPanel = document.getElementById("pantalla-panel");
  const nombrePanel = document.getElementById("nombre-panel");
  const btnSalirPanel = document.getElementById("btn-salir-panel");

  // Cada perfil ve su pantalla: el reparto (marca entregas), el vendedor (carga pedidos) o el
  // admin, que ve todas con la barra de secciones (ver admin.js).
  function mostrarApp(nombre, rol) {
    pantallaLogin.hidden = true;
    nombreReparto.textContent = nombre;
    nombrePanel.textContent = nombre;
    if (rol === "reparto") {
      pantallaReparto.hidden = false;
      document.dispatchEvent(new CustomEvent("mana:reparto-iniciado"));
      return;
    }
    pantallaApp.hidden = false;
    nombreUsuario.textContent = nombre;
    document.dispatchEvent(new CustomEvent("mana:sesion-iniciada"));
    if (Api.esAdmin(rol)) document.dispatchEvent(new CustomEvent("mana:admin-iniciado"));
  }

  // Cuántas cosas quedaron guardadas en el teléfono sin enviar: pedidos y, para el reparto/admin,
  // entregas y ubicaciones.
  async function cantidadPorEnviar() {
    const pedidos = await Cola.cantidadPorEnviar();
    const reparto = Api.rol() === "reparto" || Api.esAdmin() ? await ColaReparto.cantidadPorEnviar() : 0;
    return pedidos + reparto;
  }

  function mostrarLogin() {
    pantallaApp.hidden = true;
    pantallaReparto.hidden = true;
    pantallaPanel.hidden = true;
    document.getElementById("pantalla-pedido").hidden = true;
    document.dispatchEvent(new CustomEvent("mana:sesion-cerrada"));
    pantallaLogin.hidden = false;
    inputClave.value = "";
  }

  form.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    elError.hidden = true;
    btn.disabled = true;
    btn.textContent = "Entrando...";
    try {
      const { token, nombre, rol } = await Api.login(inputUsername.value.trim(), inputClave.value);
      Api.guardarSesion(token, nombre, rol);
      mostrarApp(nombre, rol);
    } catch (e) {
      elError.textContent = e.message || "No se pudo iniciar sesión";
      elError.hidden = false;
    } finally {
      btn.disabled = false;
      btn.textContent = "Entrar";
    }
  });

  // Cualquier pantalla con su botón "Salir": si quedó algo sin enviar en el teléfono, se pregunta antes.
  async function salir() {
    const porEnviar = await cantidadPorEnviar();
    if (porEnviar > 0 && !confirm(`Tenés ${porEnviar} cosa(s) sin enviar (pedidos, entregas o ubicaciones). Se mandan cuando vuelvas a entrar. ¿Salir igual?`)) {
      return;
    }
    await Avisos.alSalir(); // antes de borrar la sesión: hace falta el token para dar de baja los avisos de este celular
    Api.borrarSesion();
    mostrarLogin();
  }
  btnSalir.addEventListener("click", salir);
  btnSalirReparto.addEventListener("click", salir);
  btnSalirPanel.addEventListener("click", salir);

  // El token venció (o lo revocaron, o le cambiaron el perfil): se vuelve al login.
  // Los pedidos de un vendedor sin enviar siguen guardados en el teléfono y salen
  // solos al volver a entrar.
  document.addEventListener("mana:sesion-vencida", (ev) => {
    const eraReparto = Api.rol() === "reparto";
    Api.borrarSesion();
    mostrarLogin();
    if (ev.detail && ev.detail.motivo === "permiso") {
      elError.textContent = "Tu perfil cambió. Volvé a entrar.";
    } else if (eraReparto) {
      elError.textContent = "Tu sesión venció. Volvé a entrar.";
    } else {
      elError.textContent = "Tu sesión venció. Volvé a entrar: los pedidos sin enviar se mandan solos.";
    }
    elError.hidden = false;
  });

  if (Api.token() && Api.nombre()) {
    mostrarApp(Api.nombre(), Api.rol());
  }

  if ("serviceWorker" in navigator) {
    navigator.serviceWorker.register("sw.js").catch(() => {});
  }
})();
