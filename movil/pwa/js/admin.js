// Barra de secciones del perfil admin: abajo, siempre a mano. Pedidos = su pantalla de gestión (gestion.js: lo
// pendiente, lo entregado, el detalle de cada pedido y "Agregar pedido"), Reparto = las entregas y Panel = el panel
// de control; acá solo se decide cuál se muestra. Para los demás perfiles la barra no existe.
(() => {
  const nav = document.getElementById("nav-admin");
  const botones = [...nav.querySelectorAll(".nav-admin-boton")];
  const pantallas = {
    pedidos: document.getElementById("pantalla-gestion"),
    reparto: document.getElementById("pantalla-reparto"),
    panel: document.getElementById("pantalla-panel"),
  };
  const pantallaPedido = document.getElementById("pantalla-pedido");
  // La pantalla del vendedor (lista de clientes) no es de ninguna sección del admin: "Agregar pedido" le presta sus
  // piezas a la de gestión, y login.js la deja visible para todos los perfiles que no son reparto. Acá se oculta.
  const pantallaVendedor = document.getElementById("pantalla-app");

  let repartoAbierto = false; // la primera vez se "inicia" el reparto; después alcanza con refrescarlo

  function mostrar(seccion) {
    for (const [nombre, el] of Object.entries(pantallas)) el.hidden = nombre !== seccion;
    pantallaVendedor.hidden = true;
    pantallaPedido.hidden = true; // si había un pedido a medio cargar, se vuelve a la gestión
    for (const b of botones) {
      const activo = b.dataset.seccion === seccion;
      b.classList.toggle("activo", activo);
      b.setAttribute("aria-current", activo ? "page" : "false");
    }
    if (seccion === "reparto") {
      document.dispatchEvent(new CustomEvent(repartoAbierto ? "mana:reparto-mostrado" : "mana:reparto-iniciado"));
      repartoAbierto = true;
    }
    if (seccion === "pedidos") document.dispatchEvent(new CustomEvent("mana:gestion-mostrada"));
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
