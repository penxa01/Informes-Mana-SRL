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

  const CLAVE_CACHE = "panel";
  const INTERVALO_MS = 120000;
  const AZUL = "#2563eb";
  const AMBAR = "#f59e0b";
  const VERDE = "#059669";
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

  // ── Litros del mes ───────────────────────────────────────────────────────
  function tarjetaLitros(datos) {
    const mes = datos.litros.mes;
    const ant = datos.litros.mes_anterior;
    const [desde, hasta] = [fechaCorta(datos.periodos.mes.desde), fechaCorta(datos.periodos.mes.hasta)];
    const nombreMes = desde.toLocaleDateString("es-AR", { month: "long" });
    const t = tarjeta("Litros vendidos", `${nombreMes} · al ${hasta.getDate()}`);
    t.appendChild(cifra(numero(mes.litros), "L"));
    const fila = document.createElement("div");
    fila.className = "panel-fila";
    const mesAnt = fechaCorta(datos.periodos.mes_anterior.desde).toLocaleDateString("es-AR", { month: "long" });
    fila.appendChild(chipDelta(mes.litros, ant.litros, `vs ${mesAnt} al ${fechaCorta(datos.periodos.mes_anterior.hasta).getDate()}`));
    t.appendChild(fila);

    // una columna por día del mes: lo premium abajo (ámbar) y el resto arriba (azul)
    const porFecha = new Map(mes.por_dia.map((d) => [d.fecha, d]));
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
        titulo: d ? `Día ${dia}: ${numero(d.litros)} L (${numero(d.premium)} premium)` : `Día ${dia}: sin ventas`,
        tenue: futuro,
      });
    }
    t.appendChild(Graficos.barras({
      datos: datosGrafico,
      ancho: anchoGrafico(true),
      descripcion: `Litros vendidos por día en ${nombreMes}; total ${numero(mes.litros)} litros`,
    }));
    t.appendChild(leyenda([[AMBAR, "Premium"], [AZUL, "Resto"]]));
    return t;
  }

  // ── % Premium ────────────────────────────────────────────────────────────
  function tarjetaPremium(datos) {
    const mes = datos.litros.mes;
    const ant = datos.litros.mes_anterior;
    const t = tarjeta("Premium", "sobre el total de litros");
    const cuerpo = document.createElement("div");
    cuerpo.className = "panel-premium";
    cuerpo.appendChild(Graficos.anillo({
      porcentaje: mes.pct_premium,
      color: AMBAR,
      texto: `${numero(mes.pct_premium, 1)} %`,
      descripcion: `${numero(mes.pct_premium, 1)} por ciento de los litros son premium`,
    }));
    const datosLado = document.createElement("div");
    const premium = document.createElement("p");
    premium.className = "panel-dato";
    const fuerte = document.createElement("strong");
    fuerte.textContent = `${numero(mes.premium)} L`;
    premium.append(fuerte, document.createTextNode(" premium"));
    const resto = document.createElement("p");
    resto.className = "panel-dato";
    const fuerte2 = document.createElement("strong");
    fuerte2.textContent = `${numero(mes.litros - mes.premium)} L`;
    resto.append(fuerte2, document.createTextNode(" resto"));
    const mesAnt = fechaCorta(datos.periodos.mes_anterior.desde).toLocaleDateString("es-AR", { month: "long" });
    datosLado.append(premium, resto, chipDelta(mes.pct_premium, ant.pct_premium, `vs ${mesAnt}`, true));
    cuerpo.appendChild(datosLado);
    t.appendChild(cuerpo);
    return t;
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

    elContenido.textContent = "";
    elContenido.append(tarjetaLitros(datos), tarjetaPremium(datos), tarjetaRecaudado(datos));
    hayDatos = true;
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
