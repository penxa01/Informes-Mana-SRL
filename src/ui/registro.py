"""Registro de secciones. El orden de `PAGINAS` = el orden del navbar.

Agregar una sección = agregar un `PageDef` acá + escribir su clase de página.
El `AppWindow` no se toca.
"""
from dataclasses import dataclass
from typing import Callable, Type

from src.ui.paginas.base import PaginaBase
from src.ui.paginas.echeques import PaginaEcheques
from src.ui.paginas.litros import PaginaLitros
from src.ui.paginas.margen import PaginaMargen
from src.ui.paginas.otros import PaginaOtros
from src.ui.paginas.pedidos import PaginaPedidos


@dataclass(frozen=True)
class PageDef:
    id: str
    titulo: str
    icono: str                       # nombre de archivo en src/Distribuidora/
    factory: Type[PaginaBase]        # se instancia como factory(app)
    atajo: str = ""                  # p. ej. "Ctrl+1"


PAGINAS = [
    PageDef("litros",   "Litros",     "gotas.png",   PaginaLitros,   "Ctrl+1"),
    PageDef("pedidos",  "Pedidos",    "pedidos.png", PaginaPedidos,  "Ctrl+2"),
    PageDef("echeques", "E-Cheques",  "echeq.png",   PaginaEcheques, "Ctrl+3"),
    PageDef("margen",   "Margen",     "margen.png",  PaginaMargen,   "Ctrl+4"),
    PageDef("otros",    "Otros",      "informe.png", PaginaOtros,    "Ctrl+5"),
]
