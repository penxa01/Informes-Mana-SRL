// Sección "Cobranzas" del panel del vendedor. Dibuja lo que el servidor calculó para ese vendedor (GET /panel/mio):
//   datos.cartera   lo que tiene en la calle: vencido, por vencer (próximos 7 días), al día y lo que quedó a favor
//   datos.cobrado   lo cobrado a sus clientes en cada uno de los últimos 12 meses, con cómo se pagó
//   datos.clientes  sus clientes con el saldo y el detalle de las facturas que deben (para "Consultar")
// "Cobrado" es lo cobrado a SUS clientes: el sistema no guarda quién cobró físicamente (ver guideline/Movil.md, Plan A).
// Acá solo se dibuja; los números vienen hechos y los clientes son solo los del vendedor.
const Cobranzas = (() => {
  const { numero, fechaCorta, anchoGrafico } = PanelComun;
  const DIA_MS = 86400000;
  const MAXIMO_RESULTADOS = 40;

  const pesos = (v) => `$ ${numero(v)}`;
  const pesosExactos = (v) => `$ ${numero(v, 2)}`;
  const plural = (n, uno, varios) => `${n} ${n === 1 ? uno : varios}`;
  const fechaLarga = (iso) => iso.split("-").reverse().join("/");
  const nombreMes = (clave) => {
    const [a, m] = clave.split("-").map(Number);
    return new Date(a, m - 1, 1).toLocaleDateString("es-AR", { month: "long", year: "numeric" });
  };
  const sinAcentos = (texto) => texto.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();

  function el(tag, clase, texto) {
    const nodo = document.createElement(tag);
    if (clase) nodo.className = clase;
    if (texto !== undefined) nodo.textContent = texto;
    return nodo;
  }

  // `redibujar` vuelve a armar la sección (cuando cambia el mes elegido).
  function crear(redibujar) {
    let mesElegido = null;
    let busqueda = "";
    const hoja = document.getElementById("detalle-cuenta");

    // ── Lo que tiene en la calle ───────────────────────────────────────────
    function dato(clase, etiqueta, valor, aclaracion) {
      const t = el("div", `cartera-dato cartera-${clase}`);
      t.append(el("span", "cartera-etiqueta", etiqueta), el("strong", "cartera-valor", valor));
      if (aclaracion) t.appendChild(el("small", "cartera-aclaracion", aclaracion));
      return t;
    }

    function bloqueCartera(datos) {
      const c = datos.cartera;
      const sec = el("section", "cobranzas-bloque");
      sec.appendChild(el("h3", "cobranzas-titulo", `Resumen de la cartera: ${Api.nombre() || ""}`));
      const grilla = el("div", "cartera-grilla");
      grilla.append(
        dato("calle", "Dinero en calle", pesos(c.en_calle), c.facturas ? `${plural(c.facturas, "factura", "facturas")} de ${plural(c.clientes_con_deuda, "cliente", "clientes")}` : "Nada pendiente"),
        dato("vencido", "Vencido", pesos(c.vencido)),
        dato("pct", "% vencido del total en calle", `${numero(c.pct_vencido, 1)} %`),
        dato("por-vencer", "Por vencer", pesos(c.por_vencer), "en los próximos 7 días"),
        dato("al-dia", "Al día", pesos(c.al_dia), "vence más adelante"),
        dato("favor", "A favor", pesos(c.a_favor), "saldo a favor de clientes"),
      );
      sec.appendChild(grilla);
      return sec;
    }

    // ── Cobrado en el mes ──────────────────────────────────────────────────
    function bloqueCobrado(datos, contenedor) {
      const meses = Object.keys(datos.cobrado).sort().reverse();
      if (!meses.includes(mesElegido)) mesElegido = meses[0];
      const d = datos.cobrado[mesElegido];

      const sec = el("section", "cobranzas-bloque cobrado");
      sec.appendChild(el("h3", "cobranzas-titulo", "Cobrado en el mes"));
      const fila = el("label", "cobrado-mes", "Mes");
      const selector = document.createElement("select");
      for (const clave of meses) {
        const o = document.createElement("option");
        o.value = clave;
        o.textContent = nombreMes(clave);
        o.selected = clave === mesElegido;
        selector.appendChild(o);
      }
      selector.addEventListener("change", () => {
        mesElegido = selector.value;
        redibujar();
      });
      fila.appendChild(selector);
      sec.append(fila, el("p", "cobrado-total", pesos(d.total)));
      sec.appendChild(el("p", "cobrado-cartera", `Cartera: ${Api.nombre() || ""}`));
      if (d.total > 0) sec.appendChild(PanelComun.seccionDesglose(d, anchoGrafico(contenedor, true)));
      sec.appendChild(el("p", "cobrado-pie", `Mes: ${nombreMes(mesElegido)} · ${plural(d.recibos, "recibo", "recibos")} · Datos al ${fechaLarga(datos.hoy)}`));
      return sec;
    }

    // ── Consultar: el saldo de cada cliente y sus facturas ─────────────────
    function textoDeSaldo(c) {
      if (c.facturas.length) return c.vencido > 0 ? `${plural(c.facturas.length, "factura", "facturas")} · ${pesos(c.vencido)} vencido` : plural(c.facturas.length, "factura", "facturas");
      return c.saldo < 0 ? "Saldo a favor del cliente" : "Sin deuda";
    }

    function filaDeCliente(datos, c) {
      const li = el("li");
      const b = el("button", "cliente-fila");
      b.type = "button";
      b.append(el("span", "cliente-nombre", c.nombre), el("span", "cliente-detalle", textoDeSaldo(c)));
      const saldo = el("strong", `cliente-saldo${c.vencido > 0 ? " con-vencido" : ""}${c.saldo < 0 ? " a-favor" : ""}`, c.saldo < 0 ? `${pesos(-c.saldo)} a favor` : pesos(c.saldo));
      b.appendChild(saldo);
      b.addEventListener("click", () => abrirDetalle(datos, c));
      li.appendChild(b);
      return li;
    }

    function dibujarLista(datos, lista, resumen) {
      const q = sinAcentos(busqueda.trim());
      let clientes;
      if (!q) {
        clientes = datos.clientes.filter((c) => c.facturas.length || c.saldo !== 0); // con deuda o a favor
        resumen.textContent = clientes.length ? `${plural(datos.cartera.clientes_con_deuda, "cliente con deuda", "clientes con deuda")}. Buscá por nombre o número para ver a cualquiera de tus clientes.` : "No tenés clientes con deuda. Buscá por nombre o número para consultar a cualquiera.";
      } else {
        clientes = datos.clientes.filter((c) => sinAcentos(c.nombre).includes(q) || String(c.cuenta).includes(q));
        resumen.textContent = clientes.length === 0 ? "No hay clientes tuyos con ese nombre o número."
          : clientes.length > MAXIMO_RESULTADOS ? `Mostrando ${MAXIMO_RESULTADOS} de ${clientes.length}: escribí más para acotar.` : plural(clientes.length, "cliente", "clientes");
      }
      lista.textContent = "";
      for (const c of clientes.slice(0, q ? MAXIMO_RESULTADOS : clientes.length)) lista.appendChild(filaDeCliente(datos, c));
    }

    function bloqueConsultar(datos) {
      const sec = el("section", "cobranzas-bloque consultar");
      sec.appendChild(el("h3", "cobranzas-titulo", "Consultar un cliente"));
      const campo = el("input", "consultar-buscar");
      campo.type = "search";
      campo.placeholder = "Buscar cliente por nombre o número";
      campo.autocomplete = "off";
      campo.value = busqueda;
      campo.setAttribute("aria-label", "Buscar cliente por nombre o número");
      const resumen = el("p", "consultar-resumen");
      const lista = el("ul", "consultar-lista");
      campo.addEventListener("input", () => {
        busqueda = campo.value;
        dibujarLista(datos, lista, resumen); // solo la lista: así el campo no pierde el foco mientras se escribe
      });
      sec.append(campo, resumen, lista);
      dibujarLista(datos, lista, resumen);
      return sec;
    }

    // ── El detalle de un cliente: sus facturas ─────────────────────────────
    // Estado de una factura según los días que faltan para su vencimiento, contados desde el día de los datos (no del
    // teléfono): coincide con cómo el servidor armó vencido / por vencer / al día.
    function estadoDeFactura(f, hoyIso) {
      const dias = Math.round((fechaCorta(f.vencimiento) - fechaCorta(hoyIso)) / DIA_MS);
      if (dias < 0) return ["vencida", `Vencida hace ${plural(-dias, "día", "días")}`];
      if (dias === 0) return ["por-vencer", "Vence hoy"];
      if (dias === 1) return ["por-vencer", "Vence mañana"];
      if (dias <= 7) return ["por-vencer", `Vence en ${dias} días`];
      return ["al-dia", "Al día"];
    }

    function abrirDetalle(datos, c) {
      hoja.textContent = "";
      const cab = el("header", "hoja-cabecera");
      const titulo = el("h3", "hoja-titulo", c.nombre);
      titulo.id = "titulo-cuenta";
      hoja.setAttribute("aria-labelledby", "titulo-cuenta");
      const cerrar = el("button", "boton-link hoja-cerrar", "Cerrar");
      cerrar.type = "button";
      cerrar.addEventListener("click", cerrarDetalle);
      cab.append(titulo, cerrar);
      hoja.append(cab, el("div", "hoja-meta", `Cliente ${c.cuenta}`));

      const resumen = el("div", "cuenta-resumen");
      const celda = (etiqueta, valor, clase) => {
        const d = el("div", clase);
        d.append(el("span", null, etiqueta), el("strong", null, valor));
        return d;
      };
      resumen.append(
        celda(c.saldo < 0 ? "A favor" : "Saldo", pesos(Math.abs(c.saldo)), c.saldo < 0 ? "cuenta-favor" : ""),
        celda("Vencido", pesos(c.vencido), c.vencido > 0 ? "cuenta-vencido" : ""),
        celda("Facturas", String(c.facturas.length), ""),
      );
      hoja.appendChild(resumen);

      if (c.facturas.length === 0) {
        hoja.appendChild(el("p", "hoja-nota", c.saldo < 0 ? "Este cliente tiene saldo a favor y ninguna factura pendiente." : "Este cliente no debe ninguna factura."));
      } else {
        const lista = el("ul", "factura-lista");
        for (const f of c.facturas) {
          const [clase, texto] = estadoDeFactura(f, datos.hoy);
          const li = el("li", "factura-fila");
          const izquierda = el("div", "factura-datos");
          izquierda.append(
            el("strong", "factura-comprobante", f.comprobante),
            el("span", "factura-fechas", `Emitida ${fechaLarga(f.emision)} · vence ${fechaLarga(f.vencimiento)}`),
            el("span", `factura-estado factura-${clase}`, texto),
          );
          const derecha = el("div", "factura-monto");
          derecha.appendChild(el("strong", null, pesosExactos(f.saldo)));
          if (f.total - f.saldo > 0.005) derecha.appendChild(el("small", null, `de ${pesosExactos(f.total)}`)); // pagó una parte
          li.append(izquierda, derecha);
          lista.appendChild(li);
        }
        hoja.appendChild(lista);
      }
      hoja.appendChild(el("p", "hoja-nota", `Datos al ${fechaLarga(datos.hoy)}.`));
      if (!hoja.open) hoja.showModal();
    }

    function cerrarDetalle() {
      if (hoja.open) hoja.close();
    }

    function dibujar(datos, contenedor) {
      contenedor.append(bloqueCartera(datos), bloqueCobrado(datos, contenedor), bloqueConsultar(datos));
    }

    // Al salir no queda nada de este vendedor en el teléfono: ni el mes elegido, ni lo buscado, ni la hoja abierta.
    function limpiar() {
      mesElegido = null;
      busqueda = "";
      cerrarDetalle();
      hoja.textContent = "";
    }

    return { dibujar, limpiar, firma: () => mesElegido };
  }

  return { crear };
})();
