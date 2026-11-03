// Pantalla "Panel" del vendedor: SUS números (GET /panel/mio). La API le devuelve solo lo suyo y esta pantalla solo
// dibuja. Tiene dos secciones: Litros (los litros que vendió en el mes con las tarjetas de Shell, Valvoline y Otros,
// que además filtran, y el premium) y Cobranzas (cobranzas.js: lo que tiene en la calle, lo cobrado y la consulta de
// clientes). Pedir los datos, la copia para verlos sin señal y las tarjetas de litros son de panel-comun.js (las
// comparte con el panel del admin).
(() => {
  const { numero, anchoGrafico, nota } = PanelComun;
  const pestanas = [...document.querySelectorAll("#pantalla-panel-vendedor .panel-pestana")];
  let seccion = "litros";

  const filtro = PanelComun.filtroProveedores(() => pantalla.redibujar());
  const cobranzas = Cobranzas.crear(() => pantalla.redibujar());

  function elegirSeccion(nueva) {
    seccion = nueva;
    for (const b of pestanas) {
      const activa = b.dataset.seccion === nueva;
      b.classList.toggle("activa", activa);
      b.setAttribute("aria-selected", String(activa));
    }
    pantalla.redibujar();
  }

  // Una tarjeta por producto con los litros del mes. Tocarla deja solo ese producto en las tarjetas de abajo (y
  // volver a tocarla lo saca): es el mismo filtro que los chips del panel del admin.
  function tarjetasDeProductos(datos) {
    const porProveedor = datos.litros.mes.por_proveedor;
    if (!porProveedor) return null; // un servidor con el formato anterior no trae el desglose
    const caja = document.createElement("div");
    caja.className = "panel-proveedores";
    const fila = document.createElement("div");
    fila.className = "panel-proveedores-fila";
    fila.setAttribute("role", "group");
    fila.setAttribute("aria-label", "Litros del mes por producto");
    for (const [clave, nombre] of PanelComun.PROVEEDORES) {
      const b = document.createElement("button");
      b.type = "button";
      b.className = "tile-proveedor";
      b.setAttribute("aria-pressed", String(filtro.activo(clave)));
      const etiqueta = document.createElement("span");
      etiqueta.textContent = nombre;
      const litros = document.createElement("strong");
      litros.textContent = numero(porProveedor[clave].litros);
      const unidad = document.createElement("small");
      unidad.textContent = " L";
      litros.appendChild(unidad);
      b.append(etiqueta, litros);
      b.addEventListener("click", () => filtro.alternar(clave));
      fila.appendChild(b);
    }
    caja.appendChild(fila);
    caja.appendChild(nota(filtro.estanTodos() ? "Tocá un producto para ver solo ese." : "Tocá otro para sumarlo o el mismo para sacarlo."));
    return caja;
  }

  function dibujarLitros(datos, elContenido) {
    const vista = PanelComun.vistaLitros(datos, filtro);
    const tarjetas = tarjetasDeProductos(datos);
    if (tarjetas) elContenido.appendChild(tarjetas);
    elContenido.append(
      PanelComun.tarjetaLitros(datos, vista, anchoGrafico(elContenido, true)),
      PanelComun.tarjetaPremium(datos, vista),
    );
  }


  const pantalla = PanelComun.crearPantalla({
    ids: {
      pantalla: "pantalla-panel-vendedor", actualizar: "btn-actualizar-panel-vendedor", actualizado: "panel-vendedor-actualizado",
      error: "error-panel-vendedor", aviso: "aviso-panel-vendedor", contenido: "panel-vendedor-contenido",
    },
    ruta: "/panel/mio",
    claveCache: "panel_mio",
    evento: "mana:panel-vendedor-mostrado",
    firmaExtra: () => [seccion, filtro.firma(), cobranzas.firma()],
    dibujarContenido: (datos, elContenido) => (seccion === "cobranzas" ? cobranzas.dibujar : dibujarLitros)(datos, elContenido),
  });

  for (const b of pestanas) b.addEventListener("click", () => elegirSeccion(b.dataset.seccion));
  document.addEventListener("mana:sesion-cerrada", () => {
    cobranzas.limpiar();
    elegirSeccion("litros");
  });
})();
