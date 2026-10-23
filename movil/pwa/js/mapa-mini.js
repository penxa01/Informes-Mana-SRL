// Mapita reducido de un punto (lat, lng), armado con teselas de OpenStreetMap: sin
// librerías ni claves. Una grilla de 3x3 teselas se acomoda de modo que el punto
// quede en el centro del recuadro; el recuadro recorta lo que sobra. Es un enlace:
// al tocarlo abre `destino` (el enlace de Google Maps del cliente).
// La atribución a OpenStreetMap es obligatoria por su licencia.
const MapaMini = (() => {
  const ZOOM = 16;
  const TESELA = 256;

  function crear(lat, lng, destino) {
    const n = 2 ** ZOOM;
    const latRad = (Math.max(-85, Math.min(85, lat)) * Math.PI) / 180;
    const x = ((lng + 180) / 360) * n;
    const y = ((1 - Math.asinh(Math.tan(latRad)) / Math.PI) / 2) * n;
    const tx0 = Math.floor(x);
    const ty0 = Math.floor(y);
    // Posición del punto dentro de la grilla (que arranca una tesela antes en cada eje).
    const px = TESELA + (x - tx0) * TESELA;
    const py = TESELA + (y - ty0) * TESELA;

    const enlace = document.createElement("a");
    enlace.className = "mapa-mini";
    enlace.href = destino;
    enlace.target = "_blank";
    enlace.rel = "noopener noreferrer";
    enlace.setAttribute("aria-label", "Abrir la ubicación en Google Maps");

    const lienzo = document.createElement("div");
    lienzo.className = "mapa-lienzo";
    lienzo.style.left = `calc(50% - ${px}px)`;
    lienzo.style.top = `calc(50% - ${py}px)`;
    for (let dy = -1; dy <= 1; dy++) {
      for (let dx = -1; dx <= 1; dx++) {
        const img = document.createElement("img");
        img.alt = "";
        img.width = TESELA;
        img.height = TESELA;
        img.loading = "lazy";
        img.decoding = "async";
        img.draggable = false;
        const ty = ty0 + dy;
        if (ty >= 0 && ty < n) {
          img.src = `https://tile.openstreetmap.org/${ZOOM}/${(((tx0 + dx) % n) + n) % n}/${ty}.png`;
        }
        lienzo.appendChild(img);
      }
    }

    const atribucion = document.createElement("span");
    atribucion.className = "mapa-atribucion";
    atribucion.textContent = "© OpenStreetMap";

    enlace.append(lienzo, atribucion);
    return enlace;
  }

  return { crear };
})();
