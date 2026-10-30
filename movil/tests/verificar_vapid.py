"""Claves VAPID de los avisos (movil/vapid.py): formato, coherencia del par y el comando que las
agrega al .env (una sola vez). No toca la base ni el .env real: todo en una carpeta temporal.

Correr desde la raíz:  python movil/tests/verificar_vapid.py
"""
import base64
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from movil import vapid

fails = []


def check(name, cond, extra=""):
    print(("  OK  " if cond else " FAIL ") + name + (f"  {extra}" if extra else ""))
    if not cond:
        fails.append(name)


def crudo(texto):
    return base64.urlsafe_b64decode(texto + "=" * (-len(texto) % 4))


print("=== claves ===")
publica, privada = vapid.generar()
check("la pública es un punto P-256 sin comprimir (65 bytes, empieza con 0x04)", len(crudo(publica)) == 65 and crudo(publica)[0] == 4, len(crudo(publica)))
check("la privada es un escalar de 32 bytes", len(crudo(privada)) == 32)
check("van en base64url sin relleno (lo que espera el navegador)", "=" not in publica + privada and "+" not in publica + privada and "/" not in publica + privada)
check("la pública sale de la privada (el par es coherente)", vapid.publica_de(privada) == publica)
otra_publica, otra_privada = vapid.generar()
check("cada vez se generan claves distintas", (otra_publica, otra_privada) != (publica, privada))

print("=== la matemática de la curva P-256 (sin librerías) ===")
# Vector de prueba de la RFC 6979, apéndice A.2.5 (P-256): una privada conocida y su pública publicada.
d_rfc = 0xC9AFA9D845BA75166B5C215767B1D6934E50C3DB36E89B127B8A622B120F6721
esperada = (bytes([4]) + bytes.fromhex("60FED4BA255A9D31C961EB74C6356D68C049B8923B61FA6CE669622E60F29FB6")
            + bytes.fromhex("7903FE1008B8BC99A41AE9E95628BC64F2F1B20C2D7E9F5177A3C294D4462299"))
check("coincide con el vector de la RFC 6979 (privada conocida -> pública publicada)",
      vapid._publica_de_escalar(d_rfc) == esperada)
check("n * G es el punto en el infinito (el orden de la curva es el correcto)", vapid._multiplicar(vapid._N, vapid._G) is None)
check("(n + 1) * G es G (la suma de puntos es coherente)", vapid._multiplicar(vapid._N + 1, vapid._G) == vapid._G)
punto = (int.from_bytes(crudo(publica)[1:33], "big"), int.from_bytes(crudo(publica)[33:], "big"))
check("la pública generada está sobre la curva", vapid._en_la_curva(punto))
def rechaza(privada_mala):
    try:
        vapid.publica_de(privada_mala)
        return False
    except ValueError:
        return True


check("una privada de largo equivocado o que no es base64 se rechaza",
      rechaza("no-es-una-clave") and rechaza(base64.urlsafe_b64encode(bytes(31) + b"\x01").decode().rstrip("=")[:-2])
      and rechaza("") and rechaza("!!!"))
check("una privada fuera de rango (cero o el orden de la curva) se rechaza",
      rechaza(base64.urlsafe_b64encode(bytes(32)).decode()) and rechaza(base64.urlsafe_b64encode(vapid._N.to_bytes(32, "big")).decode()))
try:
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    clave = ec.derive_private_key(int.from_bytes(crudo(privada), "big"), ec.SECP256R1())
    check("contra `cryptography`: da la misma pública",
          crudo(publica) == clave.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint))
except Exception as e:   # en la máquina de desarrollo su parte en Rust no carga (DLL load failed)
    print(f"  OMITIDO  comparación con cryptography ({type(e).__name__}); queda el vector de la RFC")

print("=== contacto ===")
check("acepta mailto: con correo y https://", vapid.contacto_valido("mailto:a@b.com") and vapid.contacto_valido("https://mana.example"))
check("rechaza lo demás", not any(vapid.contacto_valido(c) for c in ("a@b.com", "mailto:sin-arroba", "http://inseguro", "", None)))

print("=== comando: agrega las claves al .env una sola vez ===")
with tempfile.TemporaryDirectory() as tmp:
    env = os.path.join(tmp, ".env")
    with open(env, "w", encoding="utf-8") as f:
        f.write("PEDIDOS_DB_HOST=servidor\nMOVIL_JWT_SECRET=secreto")   # sin salto de línea final, a propósito
    check("sin contacto válido no escribe nada", vapid.main(["--contacto", "cualquiera", "--env", env]) == 2
          and open(env, encoding="utf-8").read() == "PEDIDOS_DB_HOST=servidor\nMOVIL_JWT_SECRET=secreto")
    check("con contacto válido las agrega", vapid.main(["--contacto", "mailto:avisos@ejemplo.com", "--env", env]) == 0)
    texto = open(env, encoding="utf-8").read()
    lineas = dict(l.split("=", 1) for l in texto.splitlines() if "=" in l and not l.startswith("#"))
    check("no pisa lo que ya había", lineas["PEDIDOS_DB_HOST"] == "servidor" and lineas["MOVIL_JWT_SECRET"] == "secreto")
    check("quedan las tres variables, con un par coherente",
          vapid.publica_de(lineas["MOVIL_VAPID_PRIVADA"]) == lineas["MOVIL_VAPID_PUBLICA"]
          and lineas["MOVIL_VAPID_CONTACTO"] == "mailto:avisos@ejemplo.com")
    check("una segunda vez se niega a cambiar las claves (invalidaría todas las suscripciones)",
          vapid.main(["--contacto", "mailto:avisos@ejemplo.com", "--env", env]) == 1 and open(env, encoding="utf-8").read() == texto)
    check("por defecto escribe en el movil/.env que tiene al lado (anda desde cualquier carpeta)",
          vapid.RUTA_ENV_POR_DEFECTO == os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))
    por_defecto = os.path.join(tmp, "por_defecto.env")
    original = vapid.RUTA_ENV_POR_DEFECTO
    vapid.RUTA_ENV_POR_DEFECTO = por_defecto   # que la prueba no toque el .env real
    try:
        sin_env = vapid.main(["--contacto", "mailto:avisos@ejemplo.com"])
    finally:
        vapid.RUTA_ENV_POR_DEFECTO = original
    check("sin --env usa ese por defecto", sin_env == 0 and "MOVIL_VAPID_PRIVADA=" in open(por_defecto, encoding="utf-8").read())
    import subprocess
    desde_otra_carpeta = os.path.join(tmp, "desde_otra_carpeta.env")
    proc = subprocess.run([sys.executable, vapid.__file__, "--contacto", "mailto:avisos@ejemplo.com", "--env", desde_otra_carpeta],
                          cwd=tmp, capture_output=True, text=True, timeout=60)
    check("como script (python ...\\movil\\vapid.py) anda desde una carpeta cualquiera, sin ser paquete ('No module named movil' no puede pasar)",
          proc.returncode == 0 and "MOVIL_VAPID_PUBLICA=" in open(desde_otra_carpeta, encoding="utf-8").read(), proc.stderr[-200:])
    inexistente = os.path.join(tmp, "nuevo.env")
    check("si el .env no existe lo crea", vapid.main(["--contacto", "https://mana.example", "--env", inexistente]) == 0
          and "MOVIL_VAPID_PRIVADA=" in open(inexistente, encoding="utf-8").read())

print()
print("RESULTADO:", "TODO OK" if not fails else f"{len(fails)} FALLAS: {fails}")
sys.exit(1 if fails else 0)
