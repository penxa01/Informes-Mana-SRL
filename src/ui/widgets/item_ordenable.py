"""Celda de tabla que ordena por una clave tipada (fecha, número, texto) y no por el texto
visible. Sin esto Qt compara "31/05/2026" < "03/12/2025" como strings y la fecha nunca
queda bien ordenada.

    item = ItemOrdenable("17/10/2026")
    item.setData(core.Qt.UserRole, datetime(2026, 10, 17))
"""
import PyQt5.QtCore as core
import PyQt5.QtWidgets as widget


class ItemOrdenable(widget.QTableWidgetItem):
    def __lt__(self, other):
        a = self.data(core.Qt.UserRole)
        b = other.data(core.Qt.UserRole) if isinstance(other, widget.QTableWidgetItem) else None
        if a is None or b is None:
            return super().__lt__(other)
        try:
            return bool(a < b)
        except TypeError:
            return str(a) < str(b)
