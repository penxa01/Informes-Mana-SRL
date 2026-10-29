// Barra de secciones del perfil admin: abajo, siempre a mano. El admin ve las mismas pantallas
// que el resto (Pedidos = la carga de pedidos del vendedor, Reparto = las entregas) y el Panel de
// control; acá solo se decide cuál se muestra. Para los demás perfiles la barra no existe.
(() => {
  const nav = document.getElementById("nav-admin");
  const botones = [...nav.querySelectorAll(".nav-admin-boton")];
  const pantallas = {
    pedidos: document.getElementById("pantalla-app"),
    reparto: document.getElementById("pantalla-reparto"),
    panel: document.getElementById("pantalla-panel"),
  };
  const pantallaPedido = document.getElementById("pantalla-pedido");

  let repartoAbierto = false; // la primera vez se "inicia" el reparto; después alcanza con refrescarlo

  function mostrar(seccion) {
    for (const [nombre, el] of Object.entries(pantallas)) el.hidden = nombre !== seccion;
    pantallaPedido.hidden = true; // si había un pedido a medio cargar, se vuelve a la lista de clientes
    for (const b of botones) {
      const activo = b.dataset.seccion === seccion;
      b.classList.toggle("activo", activo);
      b.setAttribute("aria-current", activo ? "page" : "false");
    }
    if (seccion === "reparto") {
      document.dispatchEvent(new CustomEvent(repartoAbierto ? "mana:reparto-mostrado" : "mana:reparto-iniciado"));
      repartoAbierto = true;
    }
    if (seccion === "panel") document.dispatchEvent(new CustomEvent("mana:panel-mostrado"));
  }

  for (const b of botones) b.addEventListener("click", () => mostrar(b.dataset.seccion));

  document.addEventListener("mana:admin-iniciado", () => {
    repartoAbierto = false;
    nav.hidden = false;
    document.body.classList.add("con-nav");
    mostrar("pedidos");
  });

  // Otro script (los avisos, avisos.js) pide ir a una sección, por ejemplo al tocar un aviso de entrega.
  document.addEventListener("mana:ir-a-seccion", (ev) => {
    if (!nav.hidden && pantallas[ev.detail]) mostrar(ev.detail);
  });

  document.addEventListener("mana:sesion-cerrada", () => {
    nav.hidden = true;
    document.body.classList.remove("con-nav");
  });
})();
