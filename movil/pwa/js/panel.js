// Pantalla "Panel" del admin: litros vendidos del mes, % premium y dinero recaudado de la semana
// (GET /panel). La API no calcula nada: entrega lo que dejó el proceso del servidor, así que carga
// al instante. Esta pantalla solo dibuja. Pedir los datos, la copia para verlos sin señal, los avisos y las
// tarjetas de litros y premium son de panel-comun.js (las comparte con el panel del vendedor); acá quedan el
// filtro de productos en chips y el recaudado de la semana con cómo se cobró.
// Tiene dos pestañas: General (lo de arriba) y Cobranzas: la cartera, lo cobrado por mes y la consulta de TODOS los
// clientes de la empresa, de todos los vendedores (GET /panel/cobranzas, dibujado por cobranzas.js). El vendedor ve esa
// misma sección pero solo con sus clientes (panel-vendedor.js).
(() => {
  const { colores, numero, dinero, fechaCorta, chipDelta, anchoGrafico, tarjeta, cifra, nota } = PanelComun;
  // (cómo se cobró lo recaudado, el gráfico de proporciones y su lista, es de panel-comun.js: lo usa también el vendedor)
  const LETRAS_DIA = ["L", "M", "M", "J", "V", "S", "D"];
  const elFiltro = document.getElementById("panel-filtro");
  const elGeneral = document.getElementById("panel-contenido");
  const elCobranzas = document.getElementById("panel-cobranzas-contenido");
  const pestanas = [...document.querySelectorAll("#panel-pestanas-admin .panel-pestana")];
  let seccion = "general"; // "general" o "cobranzas"
  let filtroVisible = false;

  const filtro = PanelComun.filtroProveedores(() => pantalla.redibujar());

  function dibujarFiltro(conDesglose) {
    filtroVisible = conDesglose;
    elFiltro.hidden = !conDesglose || seccion !== "general";
    elFiltro.textContent = "";
    if (!conDesglose) return;
    const etiqueta = document.createElement("span");
    etiqueta.textContent = "Productos";
    elFiltro.appendChild(etiqueta);
    const chips = [["TODOS", "Todos", filtro.estanTodos()], ...PanelComun.PROVEEDORES.map(([c, n]) => [c, n, filtro.activo(c)])];
    for (const [clave, nombre, activo] of chips) {
      const b = document.createElement("button");
      b.type = "button";
      b.className = "chip-filtro";
      b.textContent = nombre;
      b.setAttribute("aria-pressed", String(activo));
      b.addEventListener("click", () => (clave === "TODOS" ? filtro.todos() : filtro.alternar(clave)));
      elFiltro.appendChild(b);
    }
  }

  // ── Recaudado de la semana ───────────────────────────────────────────────
  function tarjetaRecaudado(datos, elContenido) {
    const sem = datos.recaudado.semana;
    const ant = datos.recaudado.semana_anterior;
    const lunes = fechaCorta(datos.periodos.semana.desde);
    const hoy = fechaCorta(datos.periodos.semana.hasta);
    const fmt = (d) => d.toLocaleDateString("es-AR", { weekday: "short", day: "numeric" }).replace(".", "");
    const t = tarjeta("Recaudado", `${fmt(lunes)} al ${fmt(hoy)}`);
    t.appendChild(cifra(dinero(sem.total)));
    t.appendChild(nota(`$ ${numero(sem.total)} · ${sem.recibos} ${sem.recibos === 1 ? "recibo" : "recibos"}`));
    const fila = document.createElement("div");
    fila.className = "panel-fila";
    fila.appendChild(chipDelta(sem.total, ant.total, "vs semana anterior al mismo día"));
    t.appendChild(fila);

    const porFecha = new Map(sem.por_dia.map((d) => [d.fecha, d.monto]));
    const datosGrafico = LETRAS_DIA.map((letra, i) => {
      const dia = new Date(lunes.getFullYear(), lunes.getMonth(), lunes.getDate() + i);
      const iso = `${dia.getFullYear()}-${String(dia.getMonth() + 1).padStart(2, "0")}-${String(dia.getDate()).padStart(2, "0")}`;
      const monto = porFecha.get(iso) || 0;
      const futuro = dia > hoy;
      return {
        etiqueta: letra,
        partes: [{ valor: monto, color: colores.verde }],
        valorVisible: monto > 0 ? numero(monto / 1e6, 1) : null,
        titulo: futuro ? `${fmt(dia)}: todavía no` : `${fmt(dia)}: $ ${numero(monto)}`,
        tenue: futuro,
      };
    });
    t.appendChild(Graficos.barras({
      datos: datosGrafico,
      ancho: anchoGrafico(elContenido, false),
      descripcion: `Recaudado por día de la semana, en millones de pesos; total ${dinero(sem.total)}`,
    }));
    t.appendChild(nota("Por día, en millones de $"));
    // Un servidor que todavía manda el formato anterior (sin desglose) simplemente no muestra esta parte.
    if (sem.desglose) t.appendChild(PanelComun.seccionDesglose(sem.desglose, anchoGrafico(elContenido, false)));
    return t;
  }

  const pantalla = PanelComun.crearPantalla({
    ids: {
      pantalla: "pantalla-panel", actualizar: "btn-actualizar-panel", actualizado: "panel-actualizado",
      error: "error-panel", aviso: "aviso-panel", contenido: "panel-contenido",
    },
    ruta: "/panel",
    claveCache: "panel",
    evento: "mana:panel-general-mostrado",
    activa: () => seccion === "general",
    firmaExtra: filtro.firma,
    alLimpiar: () => {
      filtroVisible = false;
      elFiltro.hidden = true;
    },
    dibujarContenido(datos, elContenido) {
      const vista = PanelComun.vistaLitros(datos, filtro);
      dibujarFiltro(vista.conDesglose);
      elContenido.append(
        PanelComun.tarjetaLitros(datos, vista, anchoGrafico(elContenido, true)),
        PanelComun.tarjetaPremium(datos, vista),
        tarjetaRecaudado(datos, elContenido),
      );
    },
  });

  // ── Cobranzas de toda la empresa ──────────────────────────────────────────
  const cobranzas = Cobranzas.crear(() => deLaEmpresa.redibujar(), { nombreCartera: () => "todos los clientes", todos: true });
  const deLaEmpresa = PanelComun.crearPantalla({
    ids: {
      pantalla: "pantalla-panel", actualizar: "btn-actualizar-panel", actualizado: "panel-actualizado",
      error: "error-panel", aviso: "aviso-panel", contenido: "panel-cobranzas-contenido",
    },
    ruta: "/panel/cobranzas",
    claveCache: "panel_cobranzas",
    evento: "mana:panel-cobranzas-mostrado",
    activa: () => seccion === "cobranzas",
    firmaExtra: cobranzas.firma,
    dibujarContenido: cobranzas.dibujar,
  });

  // Muestra la pestaña (sin pedir nada) y, aparte, avisa para que cargue lo suyo.
  function aplicarSeccion(nueva) {
    seccion = nueva;
    for (const b of pestanas) {
      const activa = b.dataset.seccion === nueva;
      b.classList.toggle("activa", activa);
      b.setAttribute("aria-selected", String(activa));
    }
    elGeneral.hidden = nueva !== "general";
    elCobranzas.hidden = nueva !== "cobranzas";
    elFiltro.hidden = !filtroVisible || nueva !== "general";
  }

  const avisarSeccion = () =>
    document.dispatchEvent(new CustomEvent(seccion === "general" ? "mana:panel-general-mostrado" : "mana:panel-cobranzas-mostrado"));

  for (const b of pestanas) {
    b.addEventListener("click", () => {
      aplicarSeccion(b.dataset.seccion);
      avisarSeccion();
    });
  }

  // La barra de secciones (nav.js) avisa que se mostró el panel: se carga la pestaña que está a la vista.
  document.addEventListener("mana:panel-mostrado", avisarSeccion);

  document.addEventListener("mana:sesion-cerrada", () => {
    cobranzas.limpiar();
    aplicarSeccion("general");
  });
})();
