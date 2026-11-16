// Piezas que comparten las dos pantallas de panel: la del admin (panel.js, GET /panel: todo el negocio) y la del
// vendedor (panel-vendedor.js, GET /panel/mio: solo lo suyo). Acá están los formatos de números, las tarjetas de
// litros y de premium, el filtro de productos (Shell / Valvoline / Otros) y la mecánica de cada pantalla: pedir los
// datos, guardar la última respuesta en el teléfono para verla sin señal (se borra al salir), avisar si están
// viejos y volver a dibujar solo cuando algo cambió. Cada pantalla pone lo suyo: qué tarjetas arma.
const PanelComun = (() => {
  // Los colores de las series salen de las variables de estilos.css (una sola fuente de verdad).
  const estilo = getComputedStyle(document.documentElement);
  const color = (variable, respaldo) => estilo.getPropertyValue(variable).trim() || respaldo;
  const colores = {
    azul: color("--azul", "#2640dc"),
    ambar: color("--ambar", "#f59e0b"),
    verde: color("--verde", "#059669"),
    violeta: color("--violeta", "#7c3aed"),
    gris: color("--gris", "#94a3b8"),
  };

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
  function anchoGrafico(contenedor, primera) {
    const total = contenedor.clientWidth || 320;
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
    for (const [colorItem, texto] of items) {
      const li = document.createElement("li");
      const punto = document.createElement("i");
      punto.style.background = colorItem;
      li.append(punto, document.createTextNode(texto));
      ul.appendChild(li);
    }
    return ul;
  }

  // ── Cómo se cobró lo recaudado (efectivo / transferencia / cheques) ───────
  // [clave del servidor, nombre, color, ¿se muestra aunque sea 0?]. Retenciones y Otros solo aparecen si hay algo:
  // "Otros" es lo que no se pudo clasificar y no tiene que quedar escondido.
  const MEDIOS_DE_COBRO = [
    ["efectivo", "Efectivo", colores.verde, true],
    ["transferencia", "Transferencia", colores.azul, true],
    ["cheques", "Cheques", colores.violeta, true],
    ["retenciones", "Retenciones", colores.gris, false],
    ["otros", "Otros", colores.ambar, false],
  ];

  function textoPorcentaje(valor, total) {
    if (!total || valor <= 0) return "0 %";
    const p = (valor / total) * 100;
    return p < 1 ? "<1 %" : `${Math.round(p)} %`;
  }

  // `d` es el desglose de un período ({total, efectivo, transferencia, cheques, retenciones, otros, diferencia?}) y
  // `ancho` el ancho del gráfico (ver anchoGrafico).
  function seccionDesglose(d, ancho) {
    const sec = document.createElement("div");
    sec.className = "panel-desglose";
    const titulo = document.createElement("h4");
    titulo.textContent = "Cómo se cobró";
    sec.appendChild(titulo);

    const filas = MEDIOS_DE_COBRO.filter(([clave, , , siempre]) => siempre || Math.abs(d[clave]) >= 0.005);
    sec.appendChild(Graficos.proporcion({
      partes: filas.map(([clave, , colorFila]) => ({ valor: d[clave], color: colorFila })),
      ancho,
      descripcion: `Cómo se cobró: ${filas.map(([clave, nombre]) => `${nombre} ${textoPorcentaje(d[clave], d.total)}`).join(", ")}`,
    }));

    const lista = document.createElement("ul");
    lista.className = "panel-desglose-lista";
    for (const [clave, nombre, colorFila] of filas) {
      const li = document.createElement("li");
      const punto = document.createElement("i");
      punto.style.background = colorFila;
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

  // ── Qué productos se cuentan (Shell / Valvoline / Otros) ─────────────────────
  // Igual que los filtros del escritorio: litros y % premium se recalculan para lo elegido. El servidor
  // manda el desglose por proveedor, así que filtrar no necesita ninguna llamada. La elección queda
  // guardada en el teléfono (solo es una comodidad: si no se puede guardar, vuelve a "Todos").
  const PROVEEDORES = [["SHELL", "Shell"], ["VALVOLINE", "Valvoline"], ["OTROS", "Otros"]];
  const CLAVE_FILTRO = "panel_proveedores";

  // `alCambiar` se llama cuando el usuario cambia la selección (la pantalla se vuelve a dibujar).
  function filtroProveedores(alCambiar) {
    const todos = () => new Set(PROVEEDORES.map(([clave]) => clave));
    let seleccion = leerGuardada();

    function leerGuardada() {
      try {
        const guardado = JSON.parse(localStorage.getItem(CLAVE_FILTRO) || "null");
        const validos = Array.isArray(guardado) ? guardado.filter((c) => PROVEEDORES.some(([k]) => k === c)) : [];
        if (validos.length) return new Set(validos);
      } catch (e) {
        // sin almacenamiento o valor roto: se empieza en "Todos"
      }
      return todos();
    }

    function guardar() {
      try {
        localStorage.setItem(CLAVE_FILTRO, JSON.stringify([...seleccion]));
      } catch (e) {
        // no pasa nada
      }
    }

    const estanTodos = () => seleccion.size === PROVEEDORES.length;

    function cambiado() {
      guardar();
      alCambiar();
    }

    return {
      seleccion: () => seleccion,
      estanTodos,
      // La clave está en lo elegido y NO están todos (con todos elegidos nada se ve "apretado").
      activo: (clave) => !estanTodos() && seleccion.has(clave),
      // Lo elegido, como texto estable: sirve para saber si hay que volver a dibujar.
      firma: () => [...seleccion].sort().join(","),
      alternar(clave) {
        if (estanTodos()) {
          seleccion = new Set([clave]); // el primer toque aísla ese proveedor
        } else if (seleccion.has(clave)) {
          seleccion.delete(clave);
          if (seleccion.size === 0) seleccion = todos(); // sin ninguno no hay nada que mostrar
        } else {
          seleccion.add(clave);
        }
        cambiado();
      },
      todos() {
        seleccion = todos();
        cambiado();
      },
    };
  }

  const redondear2 = (n) => Math.round(n * 100) / 100;

  // Lo que muestran las tarjetas de litros y premium: los números del servidor, o, si se eligieron algunos
  // proveedores, la suma de esos. Si el servidor todavía manda el formato anterior (sin desglose), se
  // muestra todo y el filtro no aparece.
  function vistaLitros(datos, filtro) {
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
    const seleccion = filtro.seleccion();
    const claves = PROVEEDORES.map(([c]) => c).filter((c) => seleccion.has(c));
    const sumar = (porProveedor) =>
      claves.reduce((s, c) => ({ litros: s.litros + porProveedor[c].litros, premium: s.premium + porProveedor[c].premium }), { litros: 0, premium: 0 });
    const pct = (x) => (x.litros ? Math.round((x.premium / x.litros) * 1000) / 10 : 0);
    const actual = sumar(mes.por_proveedor);
    const anterior = sumar(ant.por_proveedor);
    return {
      conDesglose: true,
      etiqueta: filtro.estanTodos() ? null : claves.map((c) => PROVEEDORES.find(([k]) => k === c)[1]).join(" + "),
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
  function tarjetaLitros(datos, vista, ancho) {
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
        partes: [{ valor: premium, color: colores.ambar }, { valor: resto, color: colores.azul }],
        titulo: d ? `Día ${dia}: ${numero(d.litros)} L${vista.incluyeShell ? ` (${numero(d.premium)} premium)` : ""}` : `Día ${dia}: sin ventas`,
        tenue: futuro,
      });
    }
    t.appendChild(Graficos.barras({
      datos: datosGrafico,
      ancho,
      descripcion: `Litros vendidos por día en ${nombreMes}${vista.etiqueta ? ` (${vista.etiqueta})` : ""}; total ${numero(vista.litros)} litros`,
    }));
    t.appendChild(leyenda(vista.incluyeShell ? [[colores.ambar, "Premium"], [colores.azul, "Resto"]] : [[colores.azul, "Litros"]]));
    return t;
  }

  // ── % Premium ────────────────────────────────────────────────────────────
  function tarjetaPremium(datos, vista) {
    const t = tarjeta("Premium", vista.etiqueta ? `sobre los litros de ${vista.etiqueta}` : "sobre el total de litros");
    const cuerpo = document.createElement("div");
    cuerpo.className = "panel-premium";
    cuerpo.appendChild(Graficos.anillo({
      porcentaje: vista.pct,
      color: colores.ambar,
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

  // ── La pantalla: pedir, guardar para verla sin señal, avisar y dibujar solo si cambió algo ──
  // ids: ids de los elementos de la pantalla (pantalla, actualizar, actualizado, error, aviso, contenido).
  // ruta / claveCache: de dónde salen los datos y con qué clave se guarda la copia en el teléfono.
  // evento: lo que avisa que la pantalla se mostró (la barra de secciones, nav.js).
  // dibujarContenido(datos, contenedor): arma las tarjetas dentro de `contenedor` (que llega vacío).
  // firmaExtra(): lo que, además de los datos y del ancho, hace que haya que volver a dibujar (el filtro, la sección).
  // alLimpiar(): para lo que la pantalla tenga fuera del contenedor.
  // activa(): si hay dos de estas en la misma pantalla (las pestañas del panel del admin), solo la que está a la vista
  // pide datos; la otra espera a que se la muestre.
  function crearPantalla({ ids, ruta, claveCache, evento, dibujarContenido, firmaExtra = () => "", alLimpiar = () => {}, activa = () => true }) {
    const pantalla = document.getElementById(ids.pantalla);
    const btnActualizar = document.getElementById(ids.actualizar);
    const elActualizado = document.getElementById(ids.actualizado);
    const elError = document.getElementById(ids.error);
    const elAviso = document.getElementById(ids.aviso);
    const elContenido = document.getElementById(ids.contenido);

    const INTERVALO_MS = 120000;
    let cargando = false;
    let hayDatos = false;
    let ultimo = null; // { respuesta, sinConexion }: para redibujar al girar el teléfono
    let firmaVista = ""; // lo que muestran las tarjetas ahora (ver dibujar)

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

      // Las tarjetas se vuelven a armar solo si cambió algo (datos, filtro o ancho): así los gráficos se
      // animan al aparecer y no se repiten cada vez que llegan los mismos números.
      // La firma se toma después de dibujar: dibujar puede fijar cosas que forman parte de ella (por ejemplo el mes
      // elegido por defecto), y si no, el refresco siguiente lo volvería a armar sin que haya cambiado nada.
      const firma = () => JSON.stringify([datos, firmaExtra(), elContenido.clientWidth]);
      if (firma() !== firmaVista) {
        elContenido.textContent = "";
        dibujarContenido(datos, elContenido);
        firmaVista = firma();
      }
      hayDatos = true;
    }

    function redibujar() {
      if (ultimo) dibujar(ultimo.respuesta, ultimo.sinConexion);
    }

    async function mostrarDesdeCache(sinConexion) {
      try {
        const copia = await MetaDB.leer(claveCache);
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
        const respuesta = await Api.llamar(ruta);
        elError.hidden = true;
        dibujar(respuesta, false);
        MetaDB.guardar(claveCache, { usuario: Api.nombre(), respuesta }).catch(() => {});
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
      firmaVista = "";
      alLimpiar();
      elContenido.textContent = "";
      elActualizado.textContent = "";
      elAviso.hidden = true;
      elError.hidden = true;
    }

    const visible = () => !pantalla.hidden && !document.hidden && activa();

    btnActualizar.addEventListener("click", () => {
      if (activa()) cargar();
    });
    document.addEventListener(evento, async () => {
      if (!activa()) return;
      if (!hayDatos) await mostrarDesdeCache(false); // se ve algo al instante mientras llega lo nuevo
      else redibujar(); // los textos de arriba (hora de los datos, avisos) son de la pestaña que se acaba de mostrar
      cargar();
    });
    // Los números del negocio no quedan guardados en un teléfono que ya no está logueado.
    document.addEventListener("mana:sesion-cerrada", () => {
      limpiar();
      MetaDB.borrar(claveCache).catch(() => {});
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

    return { redibujar };
  }

  return {
    colores, numero, hora, fechaCorta, dinero, chipDelta, anchoGrafico, tarjeta, cifra, nota, leyenda,
    seccionDesglose, PROVEEDORES, filtroProveedores, vistaLitros, tarjetaLitros, tarjetaPremium, crearPantalla,
  };
})();
