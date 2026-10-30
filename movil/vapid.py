"""Claves VAPID de los avisos (push): el par de claves con el que el servidor se identifica ante el
servicio de push de Google/Apple. Se generan UNA sola vez por servidor:

    python <ruta>\\movil\\vapid.py --contacto mailto:alguien@ejemplo.com

Se puede correr desde cualquier carpeta (con la ruta completa) o, parado en la carpeta que CONTIENE `movil\\`,
con `python movil\\vapid.py ...`. Escribe en el `movil\\.env` que tiene al lado (`--env` solo hace falta para otro):
  MOVIL_VAPID_PUBLICA    la que usa la API (la baja el navegador para suscribirse)
  MOVIL_VAPID_PRIVADA    la que usa el proceso notificador para firmar los avisos. SECRETA: no va al chat ni al repo
  MOVIL_VAPID_CONTACTO   un contacto del servidor (mailto: o https://), que viaja en cada aviso hacia Google/Apple

Si ya hay claves en el `.env` se niega a generar otras: cambiarlas deja sin efecto todas las suscripciones
(cada celular tendría que volver a activar los avisos).

Sin dependencias: la curva P-256 (la que exige VAPID) se calcula con enteros de Python. En la máquina de
desarrollo `cryptography` no carga (su parte en Rust falla con `DLL load failed`) y generar un par de claves
no justifica depender de ella. Los tests lo verifican con el vector de prueba de la RFC 6979.
"""
import argparse
import base64
import os
import secrets
import sys

# El `.env` de la API, al lado de este archivo: así el comando anda desde cualquier carpeta.
RUTA_ENV_POR_DEFECTO = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")

# Curva P-256 (NIST / secp256r1): y^2 = x^3 - 3x + b  (mod p)
_P = 0xFFFFFFFF00000001000000000000000000000000FFFFFFFFFFFFFFFFFFFFFFFF
_N = 0xFFFFFFFF00000000FFFFFFFFFFFFFFFFBCE6FAADA7179E84F3B9CAC2FC632551   # orden del punto generador
_B = 0x5AC635D8AA3A93E7B3EBBD55769886BC651D06B0CC53B0F63BCE3C3E27D2604B
_G = (0x6B17D1F2E12C4247F8BCE6E563A440F277037D812DEB33A0F4A13945D898C296,
      0x4FE342E2FE1A7F9B8EE7EB4A7C0F9E162BCE33576B315ECECBB6406837BF51F5)


def _suma(p, q):
    """Suma de dos puntos de la curva (None = el punto en el infinito)."""
    if p is None:
        return q
    if q is None:
        return p
    x1, y1 = p
    x2, y2 = q
    if x1 == x2:
        if (y1 + y2) % _P == 0:
            return None
        pendiente = (3 * x1 * x1 - 3) * pow(2 * y1, -1, _P) % _P
    else:
        pendiente = (y2 - y1) * pow(x2 - x1, -1, _P) % _P
    x3 = (pendiente * pendiente - x1 - x2) % _P
    return x3, (pendiente * (x1 - x3) - y1) % _P


def _multiplicar(k, punto):
    """k * punto, por duplicación y suma (alcanza para derivar una clave una sola vez)."""
    resultado = None
    while k:
        if k & 1:
            resultado = _suma(resultado, punto)
        punto = _suma(punto, punto)
        k >>= 1
    return resultado


def _en_la_curva(punto):
    x, y = punto
    return (y * y - (x * x * x - 3 * x + _B)) % _P == 0


def _b64url(crudo):
    return base64.urlsafe_b64encode(crudo).rstrip(b"=").decode("ascii")


def _desde_b64url(texto):
    return base64.urlsafe_b64decode(texto + "=" * (-len(texto) % 4))


def _publica_de_escalar(d):
    x, y = _multiplicar(d, _G)
    return b"\x04" + x.to_bytes(32, "big") + y.to_bytes(32, "big")


def generar():
    """(publica, privada) en base64url: la pública es el punto sin comprimir (65 bytes) y la privada el
    escalar de 32 bytes, que es el formato que esperan el navegador y `pywebpush`."""
    while True:
        d = int.from_bytes(secrets.token_bytes(32), "big")
        if 1 <= d < _N:
            break
    return _b64url(_publica_de_escalar(d)), _b64url(d.to_bytes(32, "big"))


def publica_de(privada):
    """La clave pública que le corresponde a una privada (para comprobar que el par del `.env` es coherente)."""
    crudo = _desde_b64url(privada)
    d = int.from_bytes(crudo, "big")
    if len(crudo) != 32 or not 1 <= d < _N:
        raise ValueError("La clave privada no es válida")
    return _b64url(_publica_de_escalar(d))


def contacto_valido(contacto):
    return isinstance(contacto, str) and ((contacto.startswith("mailto:") and "@" in contacto) or contacto.startswith("https://"))


def main(argv=None):
    ap = argparse.ArgumentParser(description="Genera las claves VAPID de los avisos y las agrega al .env")
    ap.add_argument("--contacto", required=True, help="mailto:alguien@ejemplo.com o https://... (viaja en cada aviso)")
    ap.add_argument("--env", default=RUTA_ENV_POR_DEFECTO, help="ruta del .env donde agregarlas (por defecto, el movil\\.env de al lado)")
    args = ap.parse_args(argv)

    if not contacto_valido(args.contacto):
        print("El contacto tiene que empezar con mailto: (y llevar un correo) o con https://", file=sys.stderr)
        return 2
    try:
        with open(args.env, encoding="utf-8") as f:
            actual = f.read()
    except FileNotFoundError:
        actual = ""
    if "MOVIL_VAPID_PRIVADA" in actual:
        print(f"{args.env} ya tiene claves VAPID: no se generan otras (los celulares tendrían que volver a suscribirse).",
              file=sys.stderr)
        return 1

    publica, privada = generar()
    separador = "" if not actual or actual.endswith("\n") else "\n"
    with open(args.env, "a", encoding="utf-8", newline="") as f:
        f.write(f"{separador}\n# Avisos (push). La privada es SECRETA.\n"
                f"MOVIL_VAPID_PUBLICA={publica}\nMOVIL_VAPID_PRIVADA={privada}\nMOVIL_VAPID_CONTACTO={args.contacto}\n")
    print(f"Claves agregadas a {args.env}. Reiniciar la API para que ofrezca los avisos.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
