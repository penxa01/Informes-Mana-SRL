// Pantalla "Panel" del admin: litros vendidos del mes, % premium y dinero recaudado de la semana
// (GET /panel). La API no calcula nada: entrega lo que dejó el proceso del servidor, así que carga
// al instante. Esta pantalla solo dibuja. La última respuesta se guarda en el teléfono para poder
// verla sin señal (con el aviso de desde cuándo son los datos); se borra al salir.
(() => {
  const pantalla = document.getElementById("pantalla-panel");
  const btnActualizar = document.getElementById("btn-actualizar-panel");
  const elActualizado = document.getElementById("panel-actualizado");
  const elError = document.getElementById("error-panel");
  const elAviso = document.getElementById("aviso-panel");
  const elContenido = document.getElementById("panel-contenido");
  const elFiltro = document.getElementById("panel-filtro");

  const CLAVE_CACHE = "panel";
  const INTERVALO_MS = 120000;
  const AZUL = "#2563eb";
  const AMBAR = "#f59e0b";
  const VERDE = "#059669";
  const VIOLETA = "#7c3aed";
  const GRIS = "#94a3b8";
  const LETRAS_DIA = ["L", "M", "M", "J", "V", "S", "D"];

  let cargando = false;
  let hayDatos = false;
  let ultimo = null; // { respuesta, sinConexion }: para redibujar al girar el teléfono

  const numero = (n, decimales = 0) =>
    n.toLocaleString("es-AR", { minimumFractionDigits: decimales, maximumFractionDigits: decimales });

  const hora = (iso) => new Date(iso).toLocaleTimeString("es-AR", { hour: "2-digit", minute: "2-digit" });

  function fechaCorta(iso) {
    const [a, m, d] = iso.split("-").map(Number);
    return new Date(a, m - 1, d);
  }

  // $ 89,8 M / $ 850 mil / $ 1.200
  function dinero(v) {
    if (Math.abs(v) >= 1e6) return `$ ${numero(v / 1e6, 1)} M`;
    if (Math.abs(v) >= 1e4) return `$ ${numero(v / 1e3, 0)} mil`;
    return `$ ${numero(v)}`;
  }

  // Chip de variación contra el período anterior. `puntos`: la diferencia se da en puntos (para porcentajes).
  function chipDelta(actual, anterior, textoContra, puntos = false) {
    const chip = document.createElement("span");
    chip.className = "chip-delta";
    if (!anterior) {
      chip.classList.add("neutro");
      chip.textContent = "sin dato anterior";
      return chip;
    }
    const dif = puntos ? actual - anterior : ((actual - anterior) / Math.abs(anterior)) * 100;
    if (Math.abs(dif) < 0.05) {
      chip.classList.add("neutro");
      chip.textContent = `= igual ${textoContra}`;
    } else {
      chip.classList.add(dif > 0 ? "sube" : "baja");
      chip.textContent = `${dif > 0 ? "▲" : "▼"} ${numero(Math.abs(dif), 1)}${puntos ? " pts" : " %"} ${textoContra}`;
    }
    return chip;
  }

  // Ancho real (en px) que va a tener un gráfico dentro de su tarjeta: así el SVG se dibuja a escala 1:1 y
  // las letras no crecen ni se achican según la pantalla. En escritorio la primera tarjeta ocupa todo el ancho
  // y las otras comparten la fila de a dos (ver .panel-grilla en estilos.css).
  function anchoGrafico(primera) {
    const total = elContenido.clientWidth || 320;
    const dosColumnas = window.matchMedia("(min-width: 720px)").matches;
    const columna = dosColumnas && !primera ? (total - 12) / 2 : total;
    return Math.max(240, Math.floor(columna - 34)); // el relleno (16 + 16) y el borde de la tarjeta
  }

  function tarjeta(titulo, subtitulo) {
    const t = document.createElement("section");
    t.className = "panel-tarjeta";
    const cab = document.createElement("header");
    const h = document.createElement("h3");
    h.textContent = titulo;
    cab.appendChild(h);
    if (subtitulo) {
      const s = document.createElement("span");
      s.textContent = subtitulo;
      cab.appendChild(s);
    }
    t.appendChild(cab);
    return t;
  }

  function cifra(valor, unidad) {
    const p = document.createElement("p");
    p.className = "panel-cifra";
    p.textContent = valor;
    if (unidad) {
      const u = document.createElement("small");
      u.textContent = ` ${unidad}`;
      p.appendChild(u);
    }
    return p;
  }

  function nota(texto) {
    const p = document.createElement("p");
    p.className = "panel-nota";
    p.textContent = texto;
    return p;
  }

  function leyenda(items) {
    const ul = document.createElement("ul");
    ul.className = "panel-leyenda";
    for (const [color, texto] of items) {
      const li = document.createElement("li");
      const punto = document.createElement("i");
      punto.style.background = color;
      li.append(punto, document.createTextNode(texto));
      ul.appendChild(li);
    }
    return ul;
  }

  // ── Qué productos se cuentan (Shell / Valvoline / Otros) ─────────────────────
  // Igual que los filtros del escritorio: litros y % premium se recalculan para lo elegido. El servidor
  // manda el desglose por proveedor, así que filtrar no necesita ninguna llamada. La elección queda
  // guardada en el teléfono (solo es una comodidad: si no se puede guardar, vuelve a "Todos").
  const PROVEEDORES = [["SHELL", "Shell"], ["VALVOLINE", "Valvoline"], ["OTROS", "Otros"]];
  const CLAVE_FILTRO = "panel_proveedores";
  const todosLosProveedores = () => new Set(PROVEEDORES.map(([clave]) => clave));
  let seleccion = leerSeleccionGuardada();

  function leerSeleccionGuardada() {
    try {
      const guardado = JSON.parse(localStorage.getItem(CLAVE_FILTRO) || "null");
      const validos = Array.isArray(guardado) ? guardado.filter((c) => PROVEEDORES.some(([k]) => k === c)) : [];
      if (validos.length) return new Set(validos);
    } catch (e) {
      // sin almacenamiento o valor roto: se empieza en "Todos"
    }
    return todosLosProveedores();
  }

  function guardarSeleccion() {
    try {
      localStorage.setItem(CLAVE_FILTRO, JSON.stringify([...seleccion]));
    } catch (e) {
      // no pasa nada
    }
  }

  const estanTodos = () => seleccion.size === PROVEEDORES.length;

  function alternarProveedor(clave) {
    if (estanTodos()) {
      seleccion = new Set([clave]); // el primer toque aísla ese proveedor
    } else if (seleccion.has(clave)) {
      seleccion.delete(clave);
      if (seleccion.size === 0) seleccion = todosLosProveedores(); // sin ninguno no hay nada que mostrar
    } else {
      seleccion.add(clave);
    }
    guardarSeleccion();
    redibujarConLoUltimo();
  }

  function dibujarFiltro(conDesglose) {
    elFiltro.hidden = !conDesglose;
    elFiltro.textContent = "";
    if (!conDesglose) return;
    const etiqueta = document.createElement("span");
    etiqueta.textContent = "Productos";
    elFiltro.appendChild(etiqueta);
    const chips = [["TODOS", "Todos", estanTodos()], ...PROVEEDORES.map(([c, n]) => [c, n, !estanTodos() && seleccion.has(c)])];
    for (const [clave, nombre, activo] of chips) {
      const b = document.createElement("button");
      b.type = "button";
      b.className = "chip-filtro";
      b.textContent = nombre;
      b.setAttribute("aria-pressed", String(activo));
      b.addEventListener("click", () => {
        if (clave === "TODOS") {
          seleccion = todosLosProveedores();
          guardarSeleccion();
          redibujarConLoUltimo();
        } else {
          alternarProveedor(clave);
        }
      });
      elFiltro.appendChild(b);
    }
  }

  const redondear2 = (n) => Math.round(n * 100) / 100;

  // Lo que muestran las tarjetas de litros y premium: los números del servidor, o, si se eligieron algunos
  // proveedores, la suma de esos. Si el servidor todavía manda el formato anterior (sin desglose), se
  // muestra todo y el filtro no aparece.
  function vistaLitros(datos) {
    const mes = datos.litros.mes;
    const ant = datos.litros.mes_anterior;
    if (!mes.por_proveedor || !ant.por_proveedor) {
      return {
        conDesglose: false, etiqueta: null, incluyeShell: true,
        litros: mes.litros, premium: mes.premium, pct: mes.pct_premium,
        litrosAnt: ant.litros, pctAnt: ant.pct_premium,
        porDia: mes.por_dia.map((d) => ({ fecha: d.fecha, litros: d.litros, premium: d.premium })),
      };
    }
    const claves = PROVEEDORES.map(([c]) => c).filter((c) => seleccion.has(c));
    const sumar = (porProveedor) =>
      claves.reduce((s, c) => ({ litros: s.litros + porProveedor[c].litros, premium: s.premium + porProveedor[c].premium }), { litros: 0, premium: 0 });
    const pct = (x) => (x.litros ? Math.round((x.premium / x.litros) * 1000) / 10 : 0);
    const actual = sumar(mes.por_proveedor);
    const anterior = sumar(ant.por_proveedor);
    return {
      conDesglose: true,
      etiqueta: estanTodos() ? null : claves.map((c) => PROVEEDORES.find(([k]) => k === c)[1]).join(" + "),
      incluyeShell: seleccion.has("SHELL"),
      litros: redondear2(actual.litros), premium: redondear2(actual.premium), pct: pct(actual),
      litrosAnt: redondear2(anterior.litros), pctAnt: pct(anterior),
      porDia: mes.por_dia.map((d) => {
        const dia = sumar(d.proveedores);
        return { fecha: d.fecha, litros: redondear2(dia.litros), premium: redondear2(dia.premium) };
      }),
    };
  }

  // ── Litros del mes ───────────────────────────────────────────────────────
  function tarjetaLitros(datos, vista) {
    const [desde, hasta] = [fechaCorta(datos.periodos.mes.desde), fechaCorta(datos.periodos.mes.hasta)];
    const nombreMes = desde.toLocaleDateString("es-AR", { month: "long" });
    const t = tarjeta("Litros vendidos", `${nombreMes} · al ${hasta.getDate()}${vista.etiqueta ? ` · ${vista.etiqueta}` : ""}`);
    t.appendChild(cifra(numero(vista.litros), "L"));
    const fila = document.createElement("div");
    fila.className = "panel-fila";
    const mesAnt = fechaCorta(datos.periodos.mes_anterior.desde).toLocaleDateString("es-AR", { month: "long" });
    fila.appendChild(chipDelta(vista.litros, vista.litrosAnt, `vs ${mesAnt} al ${fechaCorta(datos.periodos.mes_anterior.hasta).getDate()}`));
    t.appendChild(fila);

    // una columna por día del mes: lo premium abajo (ámbar) y el resto arriba (azul)
    const porFecha = new Map(vista.porDia.map((d) => [d.fecha, d]));
    const diasDelMes = new Date(desde.getFullYear(), desde.getMonth() + 1, 0).getDate();
    const datosGrafico = [];
    for (let dia = 1; dia <= diasDelMes; dia++) {
      const iso = `${desde.getFullYear()}-${String(desde.getMonth() + 1).padStart(2, "0")}-${String(dia).padStart(2, "0")}`;
      const d = porFecha.get(iso);
      const futuro = dia > hasta.getDate();
      const premium = d ? Math.max(0, d.premium) : 0;
      const resto = d ? Math.max(0, d.litros - d.premium) : 0;
      datosGrafico.push({
        etiqueta: dia === 1 || dia % 5 === 0 ? String(dia) : null,
        partes: [{ valor: premium, color: AMBAR }, { valor: resto, color: AZUL }],
        titulo: d ? `Día ${dia}: ${numero(d.litros)} L${vista.incluyeShell ? ` (${numero(d.premium)} premium)` : ""}` : `Día ${dia}: sin ventas`,
        tenue: futuro,
      });
    }
    t.appendChild(Graficos.barras({
      datos: datosGrafico,
      ancho: anchoGrafico(true),
      descripcion: `Litros vendidos por día en ${nombreMes}${vista.etiqueta ? ` (${vista.etiqueta})` : ""}; total ${numero(vista.litros)} litros`,
    }));
    t.appendChild(leyenda(vista.incluyeShell ? [[AMBAR, "Premium"], [AZUL, "Resto"]] : [[AZUL, "Litros"]]));
    return t;
  }

  // ── % Premium ────────────────────────────────────────────────────────────
  function tarjetaPremium(datos, vista) {
    const t = tarjeta("Premium", vista.etiqueta ? `sobre los litros de ${vista.etiqueta}` : "sobre el total de litros");
    const cuerpo = document.createElement("div");
    cuerpo.className = "panel-premium";
    cuerpo.appendChild(Graficos.anillo({
      porcentaje: vista.pct,
      color: AMBAR,
      texto: `${numero(vista.pct, 1)} %`,
      descripcion: `${numero(vista.pct, 1)} por ciento de los litros son premium`,
    }));
    const datosLado = document.createElement("div");
    const premium = document.createElement("p");
    premium.className = "panel-dato";
    const fuerte = document.createElement("strong");
    fuerte.textContent = `${numero(vista.premium)} L`;
    premium.append(fuerte, document.createTextNode(" premium"));
    const resto = document.createElement("p");
    resto.className = "panel-dato";
    const fuerte2 = document.createElement("strong");
    fuerte2.textContent = `${numero(vista.litros - vista.premium)} L`;
    resto.append(fuerte2, document.createTextNode(" resto"));
    const mesAnt = fechaCorta(datos.periodos.mes_anterior.desde).toLocaleDateString("es-AR", { month: "long" });
    datosLado.append(premium, resto);
    // Sin Shell no hay premium que comparar: el chip diría "sin dato anterior" y confundiría.
    if (vista.incluyeShell) datosLado.appendChild(chipDelta(vista.pct, vista.pctAnt, `vs ${mesAnt}`, true));
    cuerpo.appendChild(datosLado);
    t.appendChild(cuerpo);
    if (!vista.incluyeShell) t.appendChild(nota("Premium es solo de Shell: esta selección no lo incluye."));
    return t;
  }

  // ── Cómo se cobró lo recaudado (efectivo / transferencia / cheques) ───────
  // [clave del servidor, nombre, color, ¿se muestra aunque sea 0?]. Retenciones y Otros solo aparecen si hay algo:
  // "Otros" es lo que no se pudo clasificar y no tiene que quedar escondido.
  const MEDIOS_DE_COBRO = [
    ["efectivo", "Efectivo", VERDE, true],
    ["transferencia", "Transferencia", AZUL, true],
    ["cheques", "Cheques", VIOLETA, true],
    ["retenciones", "Retenciones", GRIS, false],
    ["otros", "Otros", AMBAR, false],
  ];

  function textoPorcentaje(valor, total) {
    if (!total || valor <= 0) return "0 %";
    const p = (valor / total) * 100;
    return p < 1 ? "<1 %" : `${Math.round(p)} %`;
  }

  function seccionDesglose(d) {
    const sec = document.createElement("div");
    sec.className = "panel-desglose";
    const titulo = document.createElement("h4");
    titulo.textContent = "Cómo se cobró";
    sec.appendChild(titulo);

    const filas = MEDIOS_DE_COBRO.filter(([clave, , , siempre]) => siempre || Math.abs(d[clave]) >= 0.005);
    sec.appendChild(Graficos.proporcion({
      partes: filas.map(([clave, , color]) => ({ valor: d[clave], color })),
      ancho: anchoGrafico(false),
      descripcion: `Cómo se cobró: ${filas.map(([clave, nombre]) => `${nombre} ${textoPorcentaje(d[clave], d.total)}`).join(", ")}`,
    }));

    const lista = document.createElement("ul");
    lista.className = "panel-desglose-lista";
    for (const [clave, nombre, color] of filas) {
      const li = document.createElement("li");
      const punto = document.createElement("i");
      punto.style.background = color;
      const etiqueta = document.createElement("span");
      etiqueta.textContent = nombre;
      const monto = document.createElement("strong");
      monto.textContent = dinero(d[clave]);
      monto.title = `$ ${numero(d[clave], 2)}`;
      const pct = document.createElement("small");
      pct.textContent = textoPorcentaje(d[clave], d.total);
      li.append(punto, etiqueta, monto, pct);
      lista.appendChild(li);
    }
    sec.appendChild(lista);

    // Control cruzado del servidor: si el desglose no coincide con el total, se dice en vez de esconderlo.
    if (Math.abs(d.diferencia || 0) >= 0.5) {
      const aviso = nota(`El desglose no coincide con el total (diferencia $ ${numero(d.diferencia)}). Conviene revisarlo.`);
      aviso.classList.add("alerta");
      sec.appendChild(aviso);
    }
    return sec;
  }

  // ── Recaudado de la semana ───────────────────────────────────────────────
  function tarjetaRecaudado(datos) {
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
        partes: [{ valor: monto, color: VERDE }],
        valorVisible: monto > 0 ? numero(monto / 1e6, 1) : null,
        titulo: futuro ? `${fmt(dia)}: todavía no` : `${fmt(dia)}: $ ${numero(monto)}`,
        tenue: futuro,
      };
    });
    t.appendChild(Graficos.barras({
      datos: datosGrafico,
      ancho: anchoGrafico(false),
      descripcion: `Recaudado por día de la semana, en millones de pesos; total ${dinero(sem.total)}`,
    }));
    t.appendChild(nota("Por día, en millones de $"));
    // Un servidor que todavía manda el formato anterior (sin desglose) simplemente no muestra esta parte.
    if (sem.desglose) t.appendChild(seccionDesglose(sem.desglose));
    return t;
  }

  function dibujar(respuesta, sinConexion) {
    ultimo = { respuesta, sinConexion };
    const { datos, calculado_en: calculadoEn, desactualizado, error, verificado_hace_seg: hace } = respuesta;
    elActualizado.textContent = `Datos de las ${hora(calculadoEn)}${new Date(calculadoEn).toDateString() === new Date().toDateString() ? "" : " del " + new Date(calculadoEn).toLocaleDateString("es-AR", { day: "numeric", month: "numeric" })}`;

    const avisos = [];
    if (sinConexion) avisos.push("Sin conexión: se ven los últimos datos guardados en el teléfono.");
    if (desactualizado) {
      const desde = new Date(Date.now() - hace * 1000).toISOString();
      avisos.push(`El cálculo del servidor no da señales desde las ${hora(desde)}: los números pueden estar desactualizados.`);
    }
    if (error) avisos.push("El último cálculo falló y se muestran los datos anteriores. Revisar el servidor.");
    elAviso.hidden = avisos.length === 0;
    elAviso.textContent = avisos.join(" ");

    const vista = vistaLitros(datos);
    dibujarFiltro(vista.conDesglose);
    elContenido.textContent = "";
    elContenido.append(tarjetaLitros(datos, vista), tarjetaPremium(datos, vista), tarjetaRecaudado(datos));
    hayDatos = true;
  }

  function redibujarConLoUltimo() {
    if (ultimo) dibujar(ultimo.respuesta, ultimo.sinConexion);
  }

  async function mostrarDesdeCache(sinConexion) {
    try {
      const copia = await MetaDB.leer(CLAVE_CACHE);
      if (copia && copia.usuario === Api.nombre()) {
        dibujar(copia.respuesta, sinConexion);
        return true;
      }
    } catch (e) {
      // sin copia: no pasa nada
    }
    return false;
  }

  async function cargar() {
    if (cargando) return;
    cargando = true;
    btnActualizar.disabled = true;
    btnActualizar.classList.add("girando");
    try {
      const respuesta = await Api.llamar("/panel");
      elError.hidden = true;
      dibujar(respuesta, false);
      MetaDB.guardar(CLAVE_CACHE, { usuario: Api.nombre(), respuesta }).catch(() => {});
    } catch (e) {
      if (typeof e.status === "number") {
        elError.textContent = e.message;
        elError.hidden = false;
      } else if (await mostrarDesdeCache(true)) {
        elError.hidden = true;
      } else {
        elError.textContent = "Sin conexión y todavía no hay datos guardados. Tocá ↻ para reintentar.";
        elError.hidden = false;
      }
    } finally {
      cargando = false;
      btnActualizar.disabled = false;
      btnActualizar.classList.remove("girando");
    }
  }

  function limpiar() {
    hayDatos = false;
    ultimo = null;
    elFiltro.hidden = true;
    elContenido.textContent = "";
    elActualizado.textContent = "";
    elAviso.hidden = true;
    elError.hidden = true;
  }

  const visible = () => !pantalla.hidden && !document.hidden;

  btnActualizar.addEventListener("click", cargar);
  document.addEventListener("mana:panel-mostrado", async () => {
    if (!hayDatos) await mostrarDesdeCache(false); // se ve algo al instante mientras llega lo nuevo
    cargar();
  });
  // Los números del negocio no quedan guardados en un teléfono que ya no está logueado.
  document.addEventListener("mana:sesion-cerrada", () => {
    limpiar();
    MetaDB.borrar(CLAVE_CACHE).catch(() => {});
  });
  let temporizadorGiro = null;
  window.addEventListener("resize", () => {
    clearTimeout(temporizadorGiro);
    temporizadorGiro = setTimeout(() => {
      if (visible() && ultimo) dibujar(ultimo.respuesta, ultimo.sinConexion);
    }, 200);
  });
  document.addEventListener("visibilitychange", () => {
    if (visible()) cargar();
  });
  window.addEventListener("online", () => {
    if (visible()) cargar();
  });
  setInterval(() => {
    if (visible()) cargar();
  }, INTERVALO_MS);
})();
