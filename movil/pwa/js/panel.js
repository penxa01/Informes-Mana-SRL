// Pantalla "Panel" del admin: litros vendidos del mes, % premium y dinero recaudado de la semana
// (GET /panel). La API no calcula nada: entrega lo que dejó el proceso del servidor, así que carga
// al instante. Esta pantalla solo dibuja. Pedir los datos, la copia para verlos sin señal, los avisos y las
// tarjetas de litros y premium son de panel-comun.js (las comparte con el panel del vendedor); acá quedan el
// filtro de productos en chips y el recaudado de la semana con cómo se cobró.
(() => {
  const { colores, numero, dinero, fechaCorta, chipDelta, anchoGrafico, tarjeta, cifra, nota } = PanelComun;
  // (cómo se cobró lo recaudado, el gráfico de proporciones y su lista, es de panel-comun.js: lo usa también el vendedor)
  const LETRAS_DIA = ["L", "M", "M", "J", "V", "S", "D"];
  const elFiltro = document.getElementById("panel-filtro");

  const filtro = PanelComun.filtroProveedores(() => pantalla.redibujar());

  function dibujarFiltro(conDesglose) {
    elFiltro.hidden = !conDesglose;
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
    evento: "mana:panel-mostrado",
    firmaExtra: filtro.firma,
    alLimpiar: () => { elFiltro.hidden = true; },
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
})();
