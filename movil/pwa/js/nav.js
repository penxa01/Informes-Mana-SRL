// Barra de secciones: abajo, siempre a mano, para los perfiles que tienen más de una pantalla.
//   admin      Pedidos (gestion.js) | Reparto (reparto.js) | Panel (panel.js)
//   vendedor   Pedidos (su lista de clientes, la de siempre) | Panel (panel-vendedor.js)
// Acá solo se decide cuál se muestra. El reparto tiene una sola pantalla y no lleva barra. La barra se esconde mientras
// se carga un pedido (pantalla-pedido): ahí se sale con "← Volver", que avisa si quedan productos sin enviar.
(() => {
  const nav = document.getElementById("nav-secciones");
  const pantallaPedido = document.getElementById("pantalla-pedido");
  // La lista de clientes del vendedor es la sección "Pedidos" del vendedor; en el admin no es de ninguna sección:
  // "Agregar pedido" le presta sus piezas a la de gestión, y login.js la deja visible para todos los perfiles que no
  // son reparto. Acá se oculta.
  const pantallaClientes = document.getElementById("pantalla-app");

  // evento(primeraVez): lo que se avisa al mostrar la sección, para que cargue lo suyo (null = nada).
  const SECCIONES = {
    admin: [
      { id: "pedidos", nombre: "Pedidos", pantalla: "pantalla-gestion", evento: () => "mana:gestion-mostrada" },
      { id: "reparto", nombre: "Reparto", pantalla: "pantalla-reparto", evento: (primeraVez) => (primeraVez ? "mana:reparto-iniciado" : "mana:reparto-mostrado") },
      { id: "panel", nombre: "Panel", pantalla: "pantalla-panel", evento: () => "mana:panel-mostrado" },
    ],
    vendedor: [
      { id: "pedidos", nombre: "Pedidos", pantalla: "pantalla-app", evento: () => null },
      { id: "panel", nombre: "Panel", pantalla: "pantalla-panel-vendedor", evento: () => "mana:panel-vendedor-mostrado" },
    ],
  };

  let perfil = null; // "admin", "vendedor" o null (sin sesión o sin barra)
  let yaMostradas = new Set();

  const secciones = () => (perfil ? SECCIONES[perfil] : []);

  function actualizarVisibilidad() {
    const visible = perfil !== null && pantallaPedido.hidden;
    nav.hidden = !visible;
    document.body.classList.toggle("con-nav", visible);
  }

  function mostrar(id) {
    for (const s of secciones()) document.getElementById(s.pantalla).hidden = s.id !== id;
    if (perfil === "admin") pantallaClientes.hidden = true;
    pantallaPedido.hidden = true; // si había un pedido a medio cargar, se vuelve a la sección
    for (const b of nav.querySelectorAll(".nav-secciones-boton")) {
      const activo = b.dataset.seccion === id;
      b.classList.toggle("activo", activo);
      b.setAttribute("aria-current", activo ? "page" : "false");
    }
    const seccion = secciones().find((s) => s.id === id);
    const evento = seccion && seccion.evento(!yaMostradas.has(id));
    yaMostradas.add(id);
    if (evento) document.dispatchEvent(new CustomEvent(evento));
  }

  function iniciar(nuevoPerfil) {
    perfil = nuevoPerfil;
    yaMostradas = new Set();
    nav.textContent = "";
    for (const s of secciones()) {
      const b = document.createElement("button");
      b.type = "button";
      b.className = "nav-secciones-boton";
      b.dataset.seccion = s.id;
      b.textContent = s.nombre;
      b.addEventListener("click", () => mostrar(s.id));
      nav.appendChild(b);
    }
    actualizarVisibilidad();
    mostrar("pedidos");
  }

  // La barra aparece y desaparece con la pantalla de carga de un pedido.
  new MutationObserver(actualizarVisibilidad).observe(pantallaPedido, { attributes: true, attributeFilter: ["hidden"] });

  document.addEventListener("mana:admin-iniciado", () => iniciar("admin"));
  document.addEventListener("mana:vendedor-iniciado", () => iniciar("vendedor"));

  // Otro script (los avisos, avisos.js) pide ir a una sección, por ejemplo al tocar un aviso de entrega.
  document.addEventListener("mana:ir-a-seccion", (ev) => {
    if (secciones().some((s) => s.id === ev.detail)) mostrar(ev.detail);
  });

  document.addEventListener("mana:sesion-cerrada", () => {
    perfil = null;
    actualizarVisibilidad();
  });
})();
