"""Sección LITROS — informe de litros vendidos + modo Sell In (recepciones)."""
import calendar
import datetime as dt

import PyQt5.QtCore as core
import PyQt5.QtWidgets as widget

from src.Views.Litros.LitrosDBF import ReportLts
from src.ui.paginas.base import PaginaBase
from src.ui.widgets.barra_colapsable import BarraColapsable

_VENDEDORES = {
    "1": "ROMULO SANCHEZ", "3": "MIGUEL ORTUÑO", "4": "JOSE BANCO",
    "5": "DIEGO CALDERON", "6": "MATIAS BARATA", "9": "MARTIN MOYA",
}
# Tipos de comprobante que cuentan para el Informe Litros (incluye ND: afecta stock).
_TC_LITROS = ["FC", "NC", "ND", "FE", "CR"]


class PaginaLitros(PaginaBase):
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

        self._reporte = ReportLts()          # vacío; se puebla con cargar()
        raiz.addWidget(self._reporte, 1)

        self._set_habilitado(False)

    # ── filtro inline ────────────────────────────────────────────────────────
    def _armar_filtro(self, lay):
        # modo: toggle tipo pill (Ventas / Sell In)
        self._modo_ventas = widget.QRadioButton("Ventas")
        self._modo_sellin = widget.QRadioButton("Sell In")
        self._modo_ventas.setObjectName("pillToggle")
        self._modo_sellin.setObjectName("pillToggle")
        self._modo_ventas.setChecked(True)
        grupo = widget.QButtonGroup(self)
        grupo.addButton(self._modo_ventas)
        grupo.addButton(self._modo_sellin)
        self._modo_sellin.toggled.connect(self._on_modo)
        caja_modo = widget.QFrame()
        caja_modo.setObjectName("cajaModo")
        caja_modo.setStyleSheet(
            "#cajaModo { background-color: #e2e8f0; border-radius: 7px; }"
        )
        fila_modo = widget.QHBoxLayout(caja_modo)
        fila_modo.setContentsMargins(2, 2, 2, 2)
        fila_modo.setSpacing(0)
        fila_modo.addWidget(self._modo_ventas)
        fila_modo.addWidget(self._modo_sellin)
        lay.addWidget(caja_modo, 0, core.Qt.AlignBottom)

        lay.addWidget(self._sep())

        # desde / hasta
        self._desde, self._desde_manual = self._selector_periodo()
        self._hasta, self._hasta_manual = self._selector_periodo()
        lay.addLayout(self._col("Desde", self._desde, self._desde_manual))
        lay.addLayout(self._col("Hasta", self._hasta, self._hasta_manual))

        # vendedor
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

    def _selector_periodo(self):
        combo = widget.QComboBox()
        hoy = dt.date.today()
        cursor = dt.date(hoy.year - 2, hoy.month, 1)
        opciones = []
        while cursor <= hoy:
            opciones.append((cursor.strftime("%m/%Y"), cursor))
            cursor = dt.date(cursor.year + (cursor.month == 12), (cursor.month % 12) + 1, 1)
        for texto, fecha in reversed(opciones):
            combo.addItem(texto, fecha)
        combo.addItem("MANUAL", "manual")

        manual = widget.QLineEdit()
        manual.setPlaceholderText("dd/mm")
        manual.setMaximumWidth(70)
        manual.setVisible(False)
        combo.currentTextChanged.connect(lambda t, e=manual: e.setVisible(t == "MANUAL"))
        return combo, manual

    def _col(self, etiqueta, *widgets):
        v = widget.QVBoxLayout()
        v.setSpacing(2)
        lbl = widget.QLabel(etiqueta)
        lbl.setStyleSheet("font-size: 10px; font-weight: 600; color: #64748b;")
        v.addWidget(lbl)
        fila = widget.QHBoxLayout()
        fila.setSpacing(4)
        for w in widgets:
            fila.addWidget(w)
        v.addLayout(fila)
        return v

    def _sep(self):
        s = widget.QFrame()
        s.setFrameShape(widget.QFrame.VLine)
        s.setStyleSheet("color: #cbd5e1;")
        s.setFixedHeight(24)
        return s

    def _on_modo(self, sellin):
        self._vendedor.setEnabled(not sellin)

    # ── ciclo de vida ────────────────────────────────────────────────────────
    def on_ventas_listas(self, df):
        self._df_ventas = df
        self._set_habilitado(True)

    def _set_habilitado(self, ok):
        self._btn.setEnabled(ok)

    # ── generar ─────────────────────────────────────────────────────────────
    def _rango_extremo(self, combo, manual, *, fin):
        if combo.currentText() == "MANUAL":
            txt = manual.text().strip()
            if not txt:
                raise ValueError("Ingresá la fecha manual (dd/mm).")
            partes = txt.split("/")
            hoy = dt.date.today()
            if len(partes) == 2:
                d, m = int(partes[0]), int(partes[1]); y = hoy.year
            elif len(partes) == 3:
                d, m, y = int(partes[0]), int(partes[1]), int(partes[2])
            else:
                raise ValueError("Formato de fecha inválido. Usá dd/mm o dd/mm/aaaa.")
            base = dt.date(y, m, d)
            return dt.datetime(y, m, d, 23, 59, 59) if fin else dt.datetime(y, m, d, 0, 0, 0)
        base = combo.currentData()  # date(y, m, 1)
        if fin:
            ultimo = calendar.monthrange(base.year, base.month)[1]
            return dt.datetime(base.year, base.month, ultimo, 23, 59, 59)
        return dt.datetime(base.year, base.month, 1, 0, 0, 0)

    def _generar(self):
        if self._df_ventas is None:
            return
        try:
            fecha_desde = self._rango_extremo(self._desde, self._desde_manual, fin=False)
            fecha_hasta = self._rango_extremo(self._hasta, self._hasta_manual, fin=True)
            if fecha_desde > fecha_hasta:
                raise ValueError("La fecha 'Desde' no puede ser mayor que 'Hasta'.")

            df = self._df_ventas
            f = (df["FECHA"] >= fecha_desde) & (df["FECHA"] <= fecha_hasta)

            if self._modo_sellin.isChecked():
                df_f = df[f & df["MODELO"].astype(str).str.startswith("L") & (df["CODMOV"] == "RI")]
                self._reporte.cargar(df_f, df, graficos=False)
            else:
                f &= df["TC"].isin(_TC_LITROS)
                vend = self._vendedor.currentData()
                if vend is not None:
                    f &= (df["VENDNUMERO"] == vend)
                self._reporte.cargar(df[f], df, graficos=True)

            self._barra.set_colapsada(True)
        except ValueError as e:
            widget.QMessageBox.warning(self, "Filtro", str(e))
        except Exception as e:  # noqa: BLE001 — mostrar cualquier error del informe
            widget.QMessageBox.critical(self, "Error al generar el informe", str(e))
