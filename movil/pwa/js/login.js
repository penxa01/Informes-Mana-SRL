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

  function mostrarApp(nombre) {
    pantallaLogin.hidden = true;
    pantallaApp.hidden = false;
    nombreUsuario.textContent = nombre;
    document.dispatchEvent(new CustomEvent("mana:sesion-iniciada"));
  }

  function mostrarLogin() {
    pantallaApp.hidden = true;
    pantallaLogin.hidden = false;
    inputClave.value = "";
  }

  form.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    elError.hidden = true;
    btn.disabled = true;
    btn.textContent = "Entrando...";
    try {
      const { token, nombre } = await Api.login(inputUsername.value.trim(), inputClave.value);
      Api.guardarSesion(token, nombre);
      mostrarApp(nombre);
    } catch (e) {
      elError.textContent = e.message || "No se pudo iniciar sesión";
      elError.hidden = false;
    } finally {
      btn.disabled = false;
      btn.textContent = "Entrar";
    }
  });

  btnSalir.addEventListener("click", () => {
    Api.borrarSesion();
    mostrarLogin();
  });

  if (Api.token() && Api.nombre()) {
    mostrarApp(Api.nombre());
  }

  if ("serviceWorker" in navigator) {
    navigator.serviceWorker.register("sw.js").catch(() => {});
  }
})();
