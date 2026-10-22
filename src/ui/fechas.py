"""Parseo tolerante de fechas escritas a mano en los filtros de las secciones.

Acepta `dd/mm` o `dd/mm/aaaa` (también `-` o `.` como separador, año de 2
dígitos, espacios y una barra de más). Ante algo que no se puede interpretar
tira `ValueError` con un mensaje para mostrar al usuario (no el crudo de
Python)."""
import datetime as dt


def parsear_fecha(txt, *, fin=False):
    """`txt` -> `datetime`. `fin=True` fija la hora en 23:59:59 (para el extremo
    superior de un rango), si no en 00:00:00."""
    normal = str(txt).strip().replace("-", "/").replace(".", "/")
    partes = [p.strip() for p in normal.split("/") if p.strip()]
    hoy = dt.date.today()
    try:
        if len(partes) == 2:
            d, m, y = int(partes[0]), int(partes[1]), hoy.year
        elif len(partes) == 3:
            d, m, y = int(partes[0]), int(partes[1]), int(partes[2])
            if y < 100:
                y += 2000
        else:
            raise ValueError
        fecha = dt.date(y, m, d)
    except ValueError:
        raise ValueError(
            f"Fecha inválida: «{str(txt).strip()}». Usá el formato dd/mm o dd/mm/aaaa "
            "(por ejemplo 01/07 o 01/07/2025)."
        )
    hora = dt.time(23, 59, 59) if fin else dt.time(0, 0, 0)
    return dt.datetime.combine(fecha, hora)
