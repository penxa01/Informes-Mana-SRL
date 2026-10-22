// Sincroniza el catálogo al entrar y arma el buscador de clientes. Funciona
// sin conexión (modo avión): si falla el fetch, muestra lo último guardado
// en IndexedDB en vez de dejar la pantalla vacía o tirar un error.
(() => {
  const inputBuscar = document.getElementById("buscar-cliente");
  const listaClientes = document.getElementById("lista-clientes");
  const estadoCatalogo = document.getElementById("estado-catalogo");

  let clientesCache = [];

  function formatearFecha(iso) {
    if (!iso) return "nunca";
    return new Date(iso).toLocaleString("es-AR", { dateStyle: "short", timeStyle: "short" });
  }

  function renderLista(filtro) {
    const texto = filtro.trim().toLowerCase();
    const filtrados = texto
      ? clientesCache.filter(
          (c) => (c.nombre || "").toLowerCase().includes(texto) || (c.cuit || "").includes(texto)
        )
      : clientesCache.slice(0, 20);

    listaClientes.textContent = "";
    if (texto && filtrados.length === 0) {
      const li = document.createElement("li");
      li.className = "sin-resultados";
      li.textContent = "Sin resultados";
      listaClientes.appendChild(li);
      return;
    }
    for (const c of filtrados) {
      const li = document.createElement("li");
      li.className = "item-cliente";

      const nombre = document.createElement("strong");
      nombre.textContent = c.nombre || "(sin nombre)";

      const detalle = document.createElement("span");
      detalle.textContent = [c.localidad, c.cuit].filter(Boolean).join(" · ");

      li.append(nombre, detalle);
      listaClientes.appendChild(li);
    }
  }

  async function cargarDesdeCache() {
    clientesCache = await CatalogoDB.clientes();
    const sinc = await CatalogoDB.sincronizadoEn();
    estadoCatalogo.textContent = clientesCache.length
      ? `${clientesCache.length} clientes · actualizado ${formatearFecha(sinc)}`
      : "Todavía no hay catálogo descargado (hace falta conexión la primera vez)";
    renderLista(inputBuscar.value);
  }

  async function sincronizar() {
    try {
      const { version, clientes, productos } = await Api.llamar("/catalogo");
      await CatalogoDB.guardarCatalogo(version, clientes, productos);
    } catch (e) {
      // Sin conexión o la API no respondió: seguimos con lo que ya había
      // guardado en IndexedDB, no es un error para el vendedor en la calle.
    }
    await cargarDesdeCache();
  }

  inputBuscar.addEventListener("input", () => renderLista(inputBuscar.value));

  document.addEventListener("mana:sesion-iniciada", sincronizar);
})();
