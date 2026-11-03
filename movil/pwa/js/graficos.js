// Gráficos mínimos en SVG, sin librerías: barras (apiladas), una barra de proporciones y un anillo de porcentaje. Todo se
// arma con DOM (nunca con innerHTML) y cada barra lleva un <title> con su valor, que el celular
// muestra al mantener apretado.
const Graficos = (() => {
  const NS = "http://www.w3.org/2000/svg";
  const COLOR_TEXTO = "#566377";
  const COLOR_BASE = "#e3e8f3";

  function el(nombre, atributos = {}, texto = null) {
    const nodo = document.createElementNS(NS, nombre);
    for (const [clave, valor] of Object.entries(atributos)) nodo.setAttribute(clave, valor);
    if (texto !== null) nodo.textContent = texto;
    return nodo;
  }

  // Barras (de a una columna por dato, apiladas si el dato trae varias partes).
  //   datos: [{ etiqueta?, partes: [{ valor, color }], titulo?, valorVisible?, tenue? }]
  //   etiqueta       texto bajo la barra (si falta, no se escribe nada)
  //   valorVisible   texto sobre la barra (por ejemplo "27,7")
  //   tenue          el dato todavía no ocurrió (por ejemplo, un día futuro): se dibuja un puntito gris
  function barras({ datos, ancho = 320, alto = 120, descripcion = "" }) {
    const margenSup = 14;
    const margenInf = 16;
    const areaAlto = alto - margenSup - margenInf;
    const svg = el("svg", { viewBox: `0 0 ${ancho} ${alto}`, role: "img", "aria-label": descripcion, class: "grafico" });
    const y0 = margenSup + areaAlto;
    const maximo = Math.max(0, ...datos.map((d) => d.partes.reduce((s, p) => s + Math.max(0, p.valor), 0)));
    const hueco = ancho / datos.length;
    const grosor = Math.max(3, Math.min(34, hueco * 0.62));

    svg.appendChild(el("line", { x1: 0, x2: ancho, y1: y0, y2: y0, stroke: COLOR_BASE, "stroke-width": 1 }));
    datos.forEach((d, i) => {
      const x = i * hueco + (hueco - grosor) / 2;
      const grupo = el("g");
      if (d.titulo) grupo.appendChild(el("title", {}, d.titulo));
      let acumulado = 0;
      for (const p of d.partes) {
        const valor = Math.max(0, p.valor);
        if (valor <= 0 || maximo <= 0) continue;
        const h = Math.max(1, (valor / maximo) * areaAlto);
        grupo.appendChild(el("rect", { x, y: y0 - acumulado - h, width: grosor, height: h, rx: 3, fill: p.color, class: "barra", style: `--i:${i}` }));
        acumulado += h;
      }
      if (acumulado === 0) {
        grupo.appendChild(el("rect", { x, y: y0 - 2, width: grosor, height: 2, rx: 1, fill: COLOR_BASE, opacity: d.tenue ? 0.6 : 1 }));
      }
      if (d.valorVisible && acumulado > 0) {
        grupo.appendChild(el("text", { x: x + grosor / 2, y: y0 - acumulado - 4, "text-anchor": "middle", "font-size": 9, fill: COLOR_TEXTO }, d.valorVisible));
      }
      if (d.etiqueta) {
        grupo.appendChild(el("text", { x: x + grosor / 2, y: alto - 3, "text-anchor": "middle", "font-size": 10, fill: d.tenue ? "#cbd5e1" : COLOR_TEXTO }, d.etiqueta));
      }
      svg.appendChild(grupo);
    });
    return svg;
  }

  // Barra horizontal repartida en tramos (cómo se compone un total). Los tramos con valor 0 no se dibujan.
  //   partes: [{ valor, color }]
  let contadorRecortes = 0;
  function proporcion({ partes, ancho = 320, alto = 12, descripcion = "" }) {
    const svg = el("svg", { viewBox: `0 0 ${ancho} ${alto}`, role: "img", "aria-label": descripcion, class: "grafico grafico-proporcion" });
    const recorte = `recorte-proporcion-${++contadorRecortes}`;
    const defs = el("defs");
    const clip = el("clipPath", { id: recorte });
    clip.appendChild(el("rect", { x: 0, y: 0, width: ancho, height: alto, rx: alto / 2 }));
    defs.appendChild(clip);
    svg.appendChild(defs);
    const grupo = el("g", { "clip-path": `url(#${recorte})` });
    grupo.appendChild(el("rect", { x: 0, y: 0, width: ancho, height: alto, fill: COLOR_BASE }));
    const total = partes.reduce((s, p) => s + Math.max(0, p.valor), 0);
    if (total > 0) {
      let x = 0;
      for (const p of partes) {
        const valor = Math.max(0, p.valor);
        if (valor <= 0) continue;
        const w = (valor / total) * ancho;
        grupo.appendChild(el("rect", { x, y: 0, width: w, height: alto, fill: p.color }));
        if (x > 0) grupo.appendChild(el("rect", { x: x - 1, y: 0, width: 2, height: alto, fill: "#fff" })); // costura entre tramos
        x += w;
      }
    }
    svg.appendChild(grupo);
    return svg;
  }

  // Anillo con el porcentaje (0-100) del color dado y el resto en gris; `texto` va en el centro.
  function anillo({ porcentaje, color, texto, tamano = 112, descripcion = "" }) {
    const grosor = 12;
    const r = (tamano - grosor) / 2;
    const c = 2 * Math.PI * r;
    const lleno = (Math.max(0, Math.min(100, porcentaje)) / 100) * c;
    const centro = tamano / 2;
    const svg = el("svg", { viewBox: `0 0 ${tamano} ${tamano}`, width: tamano, height: tamano, role: "img", "aria-label": descripcion, class: "anillo" });
    svg.appendChild(el("circle", { cx: centro, cy: centro, r, fill: "none", stroke: COLOR_BASE, "stroke-width": grosor }));
    svg.appendChild(el("circle", {
      cx: centro, cy: centro, r, fill: "none", stroke: color, "stroke-width": grosor, "stroke-linecap": "round",
      "stroke-dasharray": `${lleno} ${c - lleno}`, transform: `rotate(-90 ${centro} ${centro})`,
      class: "anillo-valor", style: `--c:${c}`,
    }));
    svg.appendChild(el("text", { x: centro, y: centro + 6, "text-anchor": "middle", "font-size": 19, "font-weight": 700, fill: "#0f172a" }, texto));
    return svg;
  }

  return { barras, proporcion, anillo };
})();
