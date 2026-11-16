// El celular de la cuenta de reparto le manda su posición a la oficina (POST /mapa/mi-ubicacion) para que aparezca en la
// tarjeta "Mapa de clientes". Solo el perfil de reparto lo hace.
//
// Es a propósito simple y transparente:
//   - Solo mientras la app está abierta y en pantalla: una web instalada no puede seguir al celular en segundo plano
//     (sobre todo en iPhone), y es lo justo para el reparto: si cierra la app, deja de compartir.
//   - Una vez cada 20 segundos (y apenas se vuelve a la app), con el GPS del teléfono.
//   - Un aviso fijo en la pantalla dice que la oficina ve la ubicación, y si algo impide mandarla (permiso de ubicación
//     negado, sin GPS, sin señal) lo dice en rojo.
//   - No se guarda historial: el servidor se queda solo con la última posición y no la muestra si es vieja.
//   - Sin cola: una posición vieja no sirve, así que sin señal simplemente se manda la próxima.
// Si la cuenta inicia sesión en otro celular, este recibe 401 en la próxima vuelta (una sola sesión por cuenta de
// reparto) y la app vuelve al login: el seguimiento se corta con la sesión.
(() => {
  const aviso = document.getElementById("aviso-seguimiento");
  const INTERVALO_MS = 20000;
  const MENSAJE_OK = "La oficina ve tu ubicación mientras tengas la app abierta.";

  let activo = false;
  let enCurso = false;
  let temporizador = null;

  function mostrar(texto, problema) {
    aviso.textContent = texto;
    aviso.classList.toggle("aviso-seguimiento-problema", Boolean(problema));
    aviso.hidden = false;
  }

  function mensajeDeGps(e) {
    if (e.sinGps) return "Este teléfono no permite obtener la ubicación: la oficina no te ve en el mapa.";
    if (e.code === 1) return "No estás compartiendo tu ubicación. Habilitala para esta app en los ajustes del teléfono.";
    if (e.code === 2) return "No se pudo determinar tu ubicación. Probá a cielo abierto y con el GPS activado.";
    if (e.code === 3) return "Tu ubicación tardó demasiado: se reintenta sola.";
    return "No se pudo obtener tu ubicación.";
  }

  function posicion() {
    return new Promise((ok, mal) => {
      if (!("geolocation" in navigator)) {
        mal({ sinGps: true });
        return;
      }
      navigator.geolocation.getCurrentPosition(ok, mal, { enableHighAccuracy: true, timeout: 15000, maximumAge: 10000 });
    });
  }

  async function enviar() {
    if (!activo || enCurso || document.hidden) return;
    enCurso = true;
    try {
      let pos;
      try {
        pos = await posicion();
      } catch (e) {
        if (activo) mostrar(mensajeDeGps(e), true);
        return;
      }
      await Api.llamar("/mapa/mi-ubicacion", {
        method: "POST",
        body: JSON.stringify({ lat: pos.coords.latitude, lng: pos.coords.longitude, precision_m: Math.round(pos.coords.accuracy) }),
      });
      if (activo) mostrar(MENSAJE_OK, false);
    } catch (e) {
      // Un 401/403 ya sacó a la persona al login (api.js): `detener` corta esto. Sin señal: se reintenta en la próxima vuelta.
      if (activo && typeof e.status !== "number") mostrar("Sin señal: tu ubicación no llegó a la oficina. Se reintenta sola.", true);
    } finally {
      enCurso = false;
    }
  }

  function iniciar() {
    if (Api.rol() !== "reparto") return;
    detener();
    activo = true;
    mostrar("Activando tu ubicación…", false);
    enviar();
    temporizador = setInterval(enviar, INTERVALO_MS);
  }

  function detener() {
    activo = false;
    clearInterval(temporizador);
    temporizador = null;
    aviso.hidden = true;
  }

  document.addEventListener("mana:reparto-iniciado", iniciar);
  document.addEventListener("mana:sesion-cerrada", detener);
  document.addEventListener("mana:sesion-vencida", detener);
  // Al volver a la app (estaba en otra o con la pantalla apagada) se manda de inmediato: la última posición ya es vieja.
  document.addEventListener("visibilitychange", () => {
    if (!document.hidden) enviar();
  });
})();
