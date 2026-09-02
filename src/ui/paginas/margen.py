"""Sección MARGEN BENEFICIO — rentabilidad por producto para un período/vendedor."""
import datetime as dt

import PyQt5.QtCore as core
import PyQt5.QtWidgets as widget

from src.Views.Beneficio.margenBeneficio import margenBeneficio
from src.ui.paginas.base import PaginaBase
from src.ui.paginas.litros import _VENDEDORES
from src.ui.widgets.barra_colapsable import BarraColapsable

# Margen necesita el importe ajustado -> incluye ND (devolución / anulación de NC).
_TC_MARGEN = ["FC", "NC", "ND", "FE"]


class PaginaMargen(PaginaBase):
    necesita_ventas = True

    def __init__(self, app):
        super().__init__(app)
        self._df_ventas = None

        raiz = widget.QVBoxLayout(self)
        raiz.setContentsMargins(0, 0, 0, 0)
        raiz.setSpacing(0)

        self._barra = BarraColapsable("Filtros")
        self._armar_filtro(self._barra.cuerpo_layout())
        raiz.addWidget(self._barra)

        self._analisis = margenBeneficio()   # vacío; se puebla con cargar()
        raiz.addWidget(self._analisis, 1)

        self._btn.setEnabled(False)

    def _armar_filtro(self, lay):
        self._desde = widget.QLineEdit()
        self._desde.setPlaceholderText("dd/mm o dd/mm/aaaa")
        self._desde.setMaximumWidth(150)
        self._hasta = widget.QLineEdit()
        self._hasta.setPlaceholderText("dd/mm o dd/mm/aaaa")
        self._hasta.setMaximumWidth(150)
        lay.addLayout(self._col("Desde", self._desde))
        lay.addLayout(self._col("Hasta", self._hasta))

        self._vendedor = widget.QComboBox()
        self._vendedor.addItem("TODOS", None)
        for num, nombre in _VENDEDORES.items():
            self._vendedor.addItem(nombre, int(num))
        lay.addLayout(self._col("Vendedor", self._vendedor))

        lay.addStretch(1)

        self._btn = widget.QPushButton("Generar")
        self._btn.setObjectName("btnGenerar")
        self._btn.setMinimumWidth(110)
        self._btn.clicked.connect(self._generar)
        lay.addWidget(self._btn, 0, core.Qt.AlignBottom)

    def _col(self, etiqueta, *widgets):
        v = widget.QVBoxLayout()
        v.setSpacing(2)
        lbl = widget.QLabel(etiqueta)
        lbl.setStyleSheet("font-size: 11px; color: #6c757d;")
        v.addWidget(lbl)
        fila = widget.QHBoxLayout()
        fila.setSpacing(4)
        for w in widgets:
            fila.addWidget(w)
        v.addLayout(fila)
        return v

    # ── ciclo de vida ────────────────────────────────────────────────────────
    def on_ventas_listas(self, df):
        self._df_ventas = df
        self._btn.setEnabled(True)

    # ── generar ─────────────────────────────────────────────────────────────
    def _parse_fecha(self, txt, *, fin):
        partes = txt.strip().split("/")
        hoy = dt.date.today()
        if len(partes) == 2:
            d, m, y = int(partes[0]), int(partes[1]), hoy.year
        elif len(partes) == 3:
            d, m, y = int(partes[0]), int(partes[1]), int(partes[2])
        else:
            raise ValueError("Formato de fecha inválido. Usá dd/mm o dd/mm/aaaa.")
        return dt.datetime(y, m, d, 23, 59, 59) if fin else dt.datetime(y, m, d, 0, 0, 0)

    def _generar(self):
        if self._df_ventas is None:
            return
        try:
            fd = self._parse_fecha(self._desde.text(), fin=False)
            fh = self._parse_fecha(self._hasta.text(), fin=True)
            if fd > fh:
                raise ValueError("La fecha 'Desde' no puede ser mayor que 'Hasta'.")
        except ValueError as e:
            widget.QMessageBox.warning(self, "Filtro", str(e))
            return

        df = self._df_ventas
        mask = (
            (df["FECHA"] >= fd) & (df["FECHA"] <= fh)
            & df["MODELO"].astype(str).str.startswith("L")
            & df["TC"].isin(_TC_MARGEN)
        )
        vend = self._vendedor.currentData()
        if vend is not None:
            mask &= (df["VENDNUMERO"] == vend)

        self._analisis.cargar(df[mask])
        self._barra.set_colapsada(True)
