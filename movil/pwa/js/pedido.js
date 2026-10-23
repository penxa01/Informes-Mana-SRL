// Pantalla de pedido: elegís productos del catálogo (ya sincronizado por
// catalogo.js/db.js, funciona offline) y los mandás con POST /pedidos. Las
// validaciones de cantidad son las mismas que en el servidor (movil/api/pedidos.py):
// esto es solo para avisar antes de enviar, el servidor vuelve a validar todo.
(() => {
  const CANTIDAD_MIN = 1;
  const CANTIDAD_MAX = 9999;

  const pantallaApp = document.getElementById("pantalla-app");
  const pantallaPedido = document.getElementById("pantalla-pedido");
  const nombreCliente = document.getElementById("cliente-pedido");
  const btnVolver = document.getElementById("btn-volver-pedido");

  const inputBuscarProducto = document.getElementById("buscar-producto");
  const listaProductos = document.getElementById("lista-productos");
  const elCarrito = document.getElementById("carrito");
  const elCarritoVacio = document.getElementById("carrito-vacio");
  const elError = document.getElementById("error-pedido");
  const elMensajeOk = document.getElementById("mensaje-pedido-ok");
  const btnConfirmar = document.getElementById("btn-confirmar-pedido");

  let clienteActual = null;
  let productosCache = [];
  const carrito = new Map(); // id_producto -> { id, nombre, cantidad }

  function fechaHoyLocal() {
    const d = new Date();
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
  }

  function ocultarMensajes() {
    elError.hidden = true;
    elMensajeOk.hidden = true;
  }

  function renderProductos(filtro) {
    const texto = filtro.trim().toLowerCase();
    const filtrados = texto ? productosCache.filter((p) => (p.nombre || "").toLowerCase().includes(texto)) : [];

    listaProductos.textContent = "";
    if (!texto) return;
    if (filtrados.length === 0) {
      const li = document.createElement("li");
      li.className = "sin-resultados";
      li.textContent = "Sin resultados";
      listaProductos.appendChild(li);
      return;
    }
    for (const p of filtrados.slice(0, 20)) {
      const li = document.createElement("li");
      li.className = "item-producto item-tocable";
      li.tabIndex = 0;
      li.setAttribute("role", "button");
      li.textContent = p.nombre || p.id;
      li.addEventListener("click", () => agregarProducto(p));
      listaProductos.appendChild(li);
    }
  }

  function agregarProducto(producto) {
    const linea = carrito.get(producto.id);
    if (linea) {
      linea.cantidad = Math.min(linea.cantidad + 1, CANTIDAD_MAX);
    } else {
      carrito.set(producto.id, { id: producto.id, nombre: producto.nombre || producto.id, cantidad: 1 });
    }
    ocultarMensajes();
    renderCarrito();
    inputBuscarProducto.value = "";
    listaProductos.textContent = "";
  }

  function cambiarCantidad(id, delta) {
    const linea = carrito.get(id);
    if (!linea) return;
    linea.cantidad = Math.min(CANTIDAD_MAX, Math.max(CANTIDAD_MIN, linea.cantidad + delta));
    renderCarrito();
  }

  function quitarLinea(id) {
    carrito.delete(id);
    renderCarrito();
  }

  function renderCarrito() {
    elCarrito.textContent = "";
    elCarritoVacio.hidden = carrito.size > 0;
    btnConfirmar.disabled = carrito.size === 0;

    for (const linea of carrito.values()) {
      const li = document.createElement("li");
      li.className = "item-carrito";

      const nombre = document.createElement("span");
      nombre.className = "item-carrito-nombre";
      nombre.textContent = linea.nombre;

      const controles = document.createElement("div");
      controles.className = "controles-cantidad";

      const btnMenos = document.createElement("button");
      btnMenos.type = "button";
      btnMenos.className = "boton-cantidad";
      btnMenos.textContent = "−";
      btnMenos.addEventListener("click", () => cambiarCantidad(linea.id, -1));

      const cantidad = document.createElement("span");
      cantidad.className = "cantidad";
      cantidad.textContent = linea.cantidad;

      const btnMas = document.createElement("button");
      btnMas.type = "button";
      btnMas.className = "boton-cantidad";
      btnMas.textContent = "+";
      btnMas.addEventListener("click", () => cambiarCantidad(linea.id, 1));

      const btnQuitar = document.createElement("button");
      btnQuitar.type = "button";
      btnQuitar.className = "boton-quitar";
      btnQuitar.textContent = "×";
      btnQuitar.setAttribute("aria-label", `Quitar ${linea.nombre}`);
      btnQuitar.addEventListener("click", () => quitarLinea(linea.id));

      controles.append(btnMenos, cantidad, btnMas, btnQuitar);
      li.append(nombre, controles);
      elCarrito.appendChild(li);
    }
  }

  async function abrirPedido(cliente) {
    clienteActual = cliente;
    carrito.clear();
    ocultarMensajes();
    nombreCliente.textContent = cliente.nombre || `Cliente ${cliente.id}`;
    inputBuscarProducto.value = "";
    listaProductos.textContent = "";
    renderCarrito();
    productosCache = await CatalogoDB.productos();

    pantallaApp.hidden = true;
    pantallaPedido.hidden = false;
    inputBuscarProducto.focus();
  }

  function volverAClientes() {
    if (carrito.size > 0 && !confirm("Tenés productos cargados sin enviar. ¿Salir igual?")) {
      return;
    }
    pantallaPedido.hidden = true;
    pantallaApp.hidden = false;
  }

  // Confirmar = guardar el pedido en el teléfono (cola) y después intentar
  // enviarlo. Con señal sale al instante; sin señal queda guardado y se manda
  // solo cuando vuelva la conexión (ver cola.js). El carrito solo se vacía una
  // vez que el pedido quedó guardado: si falla el guardado local no se pierde.
  async function confirmarPedido() {
    if (carrito.size === 0 || !clienteActual) return;
    ocultarMensajes();
    btnConfirmar.disabled = true;
    btnConfirmar.textContent = "Guardando...";

    try {
      const pedido = await Cola.encolar({
        id_cliente: clienteActual.id,
        cliente_nombre: clienteActual.nombre,
        fecha_pedido: fechaHoyLocal(),
        lineas: Array.from(carrito.values()).map((l) => ({ id_producto: l.id, cantidad: l.cantidad })),
      });
      carrito.clear();
      renderCarrito();

      await Cola.sincronizar();
      const estado = await Cola.obtener(pedido.uuid);
      if (estado && estado.estado === "enviado") {
        elMensajeOk.textContent = "Pedido enviado.";
        elMensajeOk.hidden = false;
      } else if (estado && estado.estado === "rechazado") {
        elError.textContent = `El servidor no aceptó el pedido: ${estado.error}`;
        elError.hidden = false;
      } else {
        elMensajeOk.textContent = "Pedido guardado. Se envía solo apenas haya conexión.";
        elMensajeOk.hidden = false;
      }
    } catch (e) {
      elError.textContent = "No se pudo guardar el pedido en el teléfono. Probá de nuevo.";
      elError.hidden = false;
    } finally {
      btnConfirmar.disabled = carrito.size === 0;
      btnConfirmar.textContent = "Confirmar pedido";
    }
  }

  inputBuscarProducto.addEventListener("input", () => renderProductos(inputBuscarProducto.value));
  btnVolver.addEventListener("click", volverAClientes);
  btnConfirmar.addEventListener("click", confirmarPedido);

  document.addEventListener("mana:cliente-elegido", (ev) => abrirPedido(ev.detail));
})();
