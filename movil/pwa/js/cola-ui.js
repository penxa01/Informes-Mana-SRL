// Panel "estado de envíos" de la pantalla de clientes: una línea de resumen
// (X por enviar · Y enviados) que se despliega en la lista de pedidos con el
// estado de cada uno. Solo dibuja lo que dice Cola (cola.js).
(() => {
  const panel = document.getElementById("panel-cola");
  const btnResumen = document.getElementById("btn-resumen-cola");
  const lista = document.getElementById("lista-cola");

  const ETIQUETAS = { pendiente: "Por enviar", enviado: "Enviado", rechazado: "Rechazado" };
  let abierta = false;

  function plural(n, singular, pluralTxt) {
    return `${n} ${n === 1 ? singular : pluralTxt}`;
  }

  function formatearFecha(iso) {
    return new Date(iso).toLocaleString("es-AR", { dateStyle: "short", timeStyle: "short" });
  }

  function crearItem(p) {
    const li = document.createElement("li");
    li.className = "item-cola";

    const fila = document.createElement("div");
    fila.className = "item-cola-fila";
    const cliente = document.createElement("strong");
    cliente.textContent = p.cliente_nombre || `Cliente ${p.id_cliente}`;
    const pastilla = document.createElement("span");
    pastilla.className = `pastilla pastilla-${p.estado}`;
    pastilla.textContent = ETIQUETAS[p.estado] || p.estado;
    fila.append(cliente, pastilla);

    const detalle = document.createElement("small");
    const partes = [plural(p.lineas.length, "producto", "productos"), formatearFecha(p.creado_en)];
    if (p.estado === "enviado" && p.id_pedido) partes.push(`pedido #${p.id_pedido}`);
    detalle.textContent = partes.join(" · ");

    li.append(fila, detalle);

    if (p.estado === "rechazado" && p.error) {
      const error = document.createElement("p");
      error.className = "error-cola";
      error.textContent = p.error;
      li.appendChild(error);
    }

    if (p.estado !== "enviado") {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "boton-descartar";
      btn.textContent = "Descartar";
      btn.addEventListener("click", async () => {
        if (confirm(`¿Descartar el pedido de ${cliente.textContent}? No se va a enviar.`)) {
          await Cola.descartar(p.uuid);
        }
      });
      li.appendChild(btn);
    }
    return li;
  }

  async function render() {
    const pedidos = (await Cola.listar()).reverse(); // el más nuevo primero
    panel.hidden = pedidos.length === 0;
    if (pedidos.length === 0) return;

    const cuantos = (estado) => pedidos.filter((p) => p.estado === estado).length;
    const resumen = [];
    if (cuantos("pendiente")) resumen.push(`${cuantos("pendiente")} por enviar`);
    if (cuantos("rechazado")) resumen.push(plural(cuantos("rechazado"), "rechazado", "rechazados"));
    if (cuantos("enviado")) resumen.push(plural(cuantos("enviado"), "enviado", "enviados"));
    btnResumen.textContent = resumen.join(" · ");
    btnResumen.dataset.estado = cuantos("rechazado") ? "rechazado" : cuantos("pendiente") ? "pendiente" : "enviado";
    btnResumen.setAttribute("aria-expanded", String(abierta));

    lista.hidden = !abierta;
    lista.textContent = "";
    for (const p of pedidos) lista.appendChild(crearItem(p));
  }

  btnResumen.addEventListener("click", () => {
    abierta = !abierta;
    render();
  });

  document.addEventListener("mana:cola-cambio", render);
  document.addEventListener("mana:sesion-iniciada", render);
})();
