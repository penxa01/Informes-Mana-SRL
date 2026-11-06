"""Panel → Cobranzas: la cartera de toda la empresa, lo cobrado por mes y la consulta de clientes con el detalle de
sus facturas. Es la sección «Cobranzas» del celular (`movil/pwa/js/cobranzas.js`) con los datos de todos los
clientes (los que arma el servidor para `GET /panel/cobranzas`).
"""
import json

import PyQt5.QtCore as core
import PyQt5.QtGui as gui
import PyQt5.QtWidgets as widget

try:
    import qtawesome as qta
except ImportError:
    qta = None

from src.controllers import panel_vista as pv
from src.ui.widgets.panel_piezas import CifraAnimada, TarjetaPanel, etiqueta, nota, seccion_desglose, vaciar

_VERDE_FONDO = "#e7f4ec"
_VERDE_BORDE = "#bfe0cc"
_ROJO = "#b42332"
_NOMBRE_CARTERA = "todos los clientes"


def boton_reclamos(texto="Reclamos"):
    """Botón ámbar que abre el modal de reclamos (el mismo color que la alerta de la barra de estado)."""
    b = widget.QPushButton(f" {texto}")
    b.setObjectName("btnReclamos")
    b.setCursor(core.Qt.PointingHandCursor)
    if qta is not None:
        b.setIcon(qta.icon("fa5s.gavel", color="#d97706"))
    return b


def _tile(etiq, valor, aclaracion=None, grande=False, fondo="#ffffff", borde="#eef1f8", tono=None):
    """Una cifra de la cartera: etiqueta chica, valor grande (cuenta hasta su valor) y una aclaración."""
    t = TarjetaPanel("", fondo=fondo, borde=borde)
    t.cuerpo.setSpacing(3)
    nombre = "tileValorGrande" if grande else "tileValor"
    lbl = etiqueta(etiq, "tileEtiqueta")
    t.agregar(lbl)
    if isinstance(valor, str):                      # ya viene formateado (el %)
        cifra = etiqueta(valor, nombre)
    else:
        cifra = CifraAnimada(valor, pv.pesos, nombre=nombre)
    t.agregar(cifra)
    aclar = etiqueta(aclaracion or " ", "tileAclaracion")
    t.agregar(aclar)
    if tono:
        for w in (lbl, cifra, aclar):
            w.setProperty("tono", tono)
    return t


class VistaCobranzas(widget.QWidget):
    #: se pide abrir el modal de reclamos (con la cuenta a preseleccionar, o None)
    reclamos_solicitado = core.pyqtSignal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._datos = None
        self._mes = None
        self._firmas = {"cartera": None, "cobrado": None}

        lay = widget.QVBoxLayout(self)
        lay.setContentsMargins(0, 4, 0, 0)
        lay.setSpacing(14)
        self._cartera = widget.QWidget()
        self._cartera.setLayout(widget.QVBoxLayout())
        self._cartera.layout().setContentsMargins(0, 0, 0, 0)
        self._cobrado = widget.QWidget()
        self._cobrado.setLayout(widget.QVBoxLayout())
        self._cobrado.layout().setContentsMargins(0, 0, 0, 0)
        barra = widget.QHBoxLayout()
        barra.addStretch(1)
        btn = boton_reclamos()
        btn.setToolTip("Alta y seguimiento de reclamos de cobranza (aviso por WhatsApp al vendedor)")
        btn.clicked.connect(lambda: self.reclamos_solicitado.emit(None))
        barra.addWidget(btn)
        lay.addLayout(barra)
        lay.addWidget(self._cartera)
        lay.addWidget(self._cobrado)
        lay.addWidget(self._armar_consulta())
        lay.addStretch(1)

    # ── el panel entrega datos nuevos ────────────────────────────────────────
    def actualizar(self, datos):
        """Vuelve a armar solo lo que cambió: así los números no cuentan de nuevo en cada refresco y quien está
        escribiendo en el buscador no pierde el foco."""
        self._datos = datos
        firma = json.dumps(datos["cartera"], sort_keys=True)
        if firma != self._firmas["cartera"]:
            self._firmas["cartera"] = firma
            self._dibujar_cartera()
        firma = json.dumps([datos["cobrado"], datos["hoy"]], sort_keys=True)
        if firma != self._firmas["cobrado"]:
            self._firmas["cobrado"] = firma
            self._dibujar_cobrado()
        self._llenar_lista()

    # ── lo que tiene en la calle ─────────────────────────────────────────────
    def _dibujar_cartera(self):
        c = self._datos["cartera"]
        lay = self._cartera.layout()
        vaciar(lay)
        lay.addWidget(etiqueta(f"Resumen de la cartera: {_NOMBRE_CARTERA}", "panelH3"))
        grilla = widget.QGridLayout()
        grilla.setSpacing(6)
        for col in range(3):
            grilla.setColumnStretch(col, 1)
        calle = (f"{pv.plural(c['facturas'], 'factura', 'facturas')} de {pv.plural(c['clientes_con_deuda'], 'cliente', 'clientes')}"
                 if c["facturas"] else "Nada pendiente")
        grilla.addWidget(_tile("Dinero en calle", c["en_calle"], calle, grande=True), 0, 0)
        grilla.addWidget(_tile("Vencido", c["vencido"], fondo=_ROJO, borde=_ROJO, tono="vencido", grande=True), 0, 1)
        grilla.addWidget(_tile("% vencido del total en calle", f"{pv.numero(c['pct_vencido'], 1)} %", fondo="#fdeeee",
                               borde="#f7d4d6", tono="rosa", grande=True), 0, 2)
        grilla.addWidget(_tile("Por vencer", c["por_vencer"], "en los próximos 7 días"), 1, 0)
        grilla.addWidget(_tile("Al día", c["al_dia"], "vence más adelante"), 1, 1)
        grilla.addWidget(_tile("A favor", c["a_favor"], "saldo a favor de clientes"), 1, 2)
        lay.addLayout(grilla)

    # ── cobrado en el mes ────────────────────────────────────────────────────
    def _dibujar_cobrado(self):
        datos = self._datos
        meses = sorted(datos["cobrado"], reverse=True)
        if self._mes not in meses:
            self._mes = meses[0]
        d = datos["cobrado"][self._mes]
        lay = self._cobrado.layout()
        vaciar(lay)

        t = TarjetaPanel("Cobrado en el mes", fondo=_VERDE_FONDO, borde=_VERDE_BORDE)
        t.lbl_titulo.setStyleSheet("color: #0b5132;")
        fila = widget.QHBoxLayout()
        fila.setSpacing(10)
        fila.addWidget(etiqueta("Mes", "cobradoTexto"))
        combo = widget.QComboBox()
        combo.setMinimumWidth(190)
        for clave in meses:
            combo.addItem(pv.nombre_mes(clave).capitalize(), clave)
        combo.setCurrentIndex(meses.index(self._mes))
        combo.currentIndexChanged.connect(lambda _i, c=combo: self._elegir_mes(c.currentData()))
        fila.addWidget(combo)
        fila.addStretch(1)
        t.agregar(fila)
        t.agregar(CifraAnimada(d["total"], pv.pesos, nombre="cobradoTotal"))
        t.agregar(etiqueta(f"Cartera: {_NOMBRE_CARTERA}", "cobradoTexto"))
        if d["total"] > 0:
            t.agregar(seccion_desglose(d, color_borde=_VERDE_BORDE))
        t.agregar(etiqueta(f"Mes: {pv.nombre_mes(self._mes)} · {pv.plural(d['recibos'], 'recibo', 'recibos')} · "
                           f"Datos al {pv.fecha_larga(datos['hoy'])}", "cobradoPie"))
        lay.addWidget(t)

    def _elegir_mes(self, clave):
        if clave and clave != self._mes:
            self._mes = clave
            self._firmas["cobrado"] = None
            # se rearma después de que el combo termine de cerrarse
            core.QTimer.singleShot(0, self._dibujar_cobrado)

    # ── consultar un cliente ─────────────────────────────────────────────────
    def _armar_consulta(self):
        t = TarjetaPanel("Consultar un cliente")
        self._buscar = widget.QLineEdit()
        self._buscar.setPlaceholderText("Buscar cliente por nombre o número")
        self._buscar.setClearButtonEnabled(True)
        self._buscar.setMinimumHeight(36)
        self._buscar.textChanged.connect(lambda _t: self._llenar_lista())
        t.agregar(self._buscar)
        self._resumen = etiqueta("", "consultaResumen")
        self._resumen.setWordWrap(True)
        t.agregar(self._resumen)

        self._tabla = widget.QTableWidget(0, 3)
        self._tabla.setObjectName("tablaClientes")
        self._tabla.horizontalHeader().setVisible(False)
        self._tabla.verticalHeader().setVisible(False)
        self._tabla.horizontalHeader().setSectionResizeMode(0, widget.QHeaderView.Stretch)
        self._tabla.horizontalHeader().setSectionResizeMode(1, widget.QHeaderView.ResizeToContents)
        self._tabla.horizontalHeader().setSectionResizeMode(2, widget.QHeaderView.ResizeToContents)
        self._tabla.verticalHeader().setDefaultSectionSize(40)
        self._tabla.setEditTriggers(widget.QAbstractItemView.NoEditTriggers)
        self._tabla.setSelectionBehavior(widget.QAbstractItemView.SelectRows)
        self._tabla.setSelectionMode(widget.QAbstractItemView.SingleSelection)
        self._tabla.setShowGrid(False)
        self._tabla.setMouseTracking(True)
        self._tabla.setCursor(core.Qt.PointingHandCursor)
        self._tabla.setMinimumHeight(380)
        self._tabla.cellClicked.connect(self._abrir_detalle)
        t.agregar(self._tabla)
        return t

    def _llenar_lista(self):
        if self._datos is None:
            return
        clientes, resumen = pv.filtrar_clientes(self._datos, self._buscar.text(), todos=True)
        self._resumen.setText(resumen)
        self._clientes = clientes
        tabla = self._tabla
        tabla.setUpdatesEnabled(False)
        tabla.clearContents()
        tabla.setRowCount(len(clientes))
        fuente = gui.QFont()
        fuente.setBold(True)
        for fila, c in enumerate(clientes):
            nombre = widget.QTableWidgetItem(c["nombre"])
            nombre.setFont(fuente)
            detalle = widget.QTableWidgetItem(pv.texto_de_saldo(c))
            detalle.setForeground(gui.QColor("#566377"))
            a_favor = c["saldo"] < 0
            saldo = widget.QTableWidgetItem(f"{pv.pesos(-c['saldo'])} a favor" if a_favor else pv.pesos(c["saldo"]))
            saldo.setFont(fuente)
            saldo.setTextAlignment(core.Qt.AlignRight | core.Qt.AlignVCenter)
            if c["vencido"] > 0:
                saldo.setForeground(gui.QColor(_ROJO))
            elif a_favor:
                saldo.setForeground(gui.QColor("#047857"))
            for col, item in enumerate((nombre, detalle, saldo)):
                tabla.setItem(fila, col, item)
        tabla.setUpdatesEnabled(True)

    def _abrir_detalle(self, fila, _columna):
        if 0 <= fila < len(self._clientes):
            DetalleCliente(self._clientes[fila], self._datos["hoy"], self.window(),
                           al_reclamar=self.reclamos_solicitado.emit).exec_()

    def limpiar(self):
        self._buscar.clear()


# ── el detalle de un cliente: sus facturas ───────────────────────────────────
class DetalleCliente(widget.QDialog):
    def __init__(self, c, hoy, parent=None, al_reclamar=None):
        super().__init__(parent)
        self.setWindowTitle(c["nombre"])
        self.setMinimumSize(540, 560)
        self.setStyleSheet("QDialog { background-color: #ffffff; }")
        lay = widget.QVBoxLayout(self)
        lay.setContentsMargins(24, 20, 24, 18)
        lay.setSpacing(10)

        cab = widget.QHBoxLayout()
        titulos = widget.QVBoxLayout()
        titulos.setSpacing(0)
        nombre = etiqueta(c["nombre"], "detalleTitulo")
        nombre.setWordWrap(True)
        titulos.addWidget(nombre)
        titulos.addWidget(etiqueta(f"Cliente {c['cuenta']}", "detalleMeta"))
        cab.addLayout(titulos, 1)
        if al_reclamar is not None:
            reclamar = boton_reclamos("Reclamar")
            reclamar.setToolTip("Abre el alta de reclamos con este cliente elegido")
            # se abre después de cerrar este detalle, no encima
            reclamar.clicked.connect(lambda: (self.accept(), core.QTimer.singleShot(0, lambda: al_reclamar(c["cuenta"]))))
            cab.addWidget(reclamar, 0, core.Qt.AlignTop)
        cerrar = widget.QPushButton("Cerrar")
        cerrar.setObjectName("btnGenerar")
        cerrar.setCursor(core.Qt.PointingHandCursor)
        cerrar.clicked.connect(self.accept)
        cab.addWidget(cerrar, 0, core.Qt.AlignTop)
        lay.addLayout(cab)

        resumen = widget.QFrame()
        resumen.setObjectName("detalleResumen")
        r = widget.QVBoxLayout(resumen)
        r.setContentsMargins(14, 6, 14, 6)
        r.setSpacing(0)
        a_favor = c["saldo"] < 0
        filas = [("A favor" if a_favor else "Saldo", pv.pesos(abs(c["saldo"])), "favor" if a_favor else None),
                 ("Vencido", pv.pesos(c["vencido"]), "alerta" if c["vencido"] > 0 else None),
                 ("Facturas", str(len(c["facturas"])), None)]
        for i, (nom, valor, tono) in enumerate(filas):
            fila = widget.QHBoxLayout()
            fila.setContentsMargins(0, 8, 0, 8)
            fila.addWidget(etiqueta(nom, "detalleFilaEtiqueta"))
            fila.addStretch(1)
            v = etiqueta(valor, "detalleFilaValor")
            if tono:
                v.setProperty("tono", tono)
            fila.addWidget(v)
            r.addLayout(fila)
            if i < len(filas) - 1:
                sep = widget.QFrame()
                sep.setFixedHeight(1)
                sep.setStyleSheet("background-color: #e3e8f3;")
                r.addWidget(sep)
        lay.addWidget(resumen)

        if not c["facturas"]:
            lay.addWidget(nota("Este cliente tiene saldo a favor y ninguna factura pendiente." if a_favor
                               else "Este cliente no debe ninguna factura."))
            lay.addStretch(1)
        else:
            scroll = widget.QScrollArea()
            scroll.setObjectName("panelScroll")
            scroll.setWidgetResizable(True)
            scroll.setFrameShape(widget.QFrame.NoFrame)
            cont = widget.QWidget()
            fl = widget.QVBoxLayout(cont)
            fl.setContentsMargins(0, 0, 6, 0)
            fl.setSpacing(0)
            for f in c["facturas"]:
                fl.addWidget(self._fila_factura(f, hoy))
            fl.addStretch(1)
            scroll.setWidget(cont)
            lay.addWidget(scroll, 1)
        lay.addWidget(nota(f"Datos al {pv.fecha_larga(hoy)}."))

        # entra con un fundido corto
        self.setWindowOpacity(0.0)
        self._fundido = core.QPropertyAnimation(self, b"windowOpacity", self)
        self._fundido.setDuration(160)
        self._fundido.setStartValue(0.0)
        self._fundido.setEndValue(1.0)

    def showEvent(self, evento):
        super().showEvent(evento)
        self._fundido.start()

    @staticmethod
    def _fila_factura(f, hoy):
        clase, texto = pv.estado_factura(f["vencimiento"], hoy)
        fila = widget.QFrame()
        fila.setObjectName("facturaFila")
        fila.setStyleSheet("QFrame#facturaFila { border-top: 1px solid #eef1f8; }")
        lay = widget.QHBoxLayout(fila)
        lay.setContentsMargins(0, 10, 0, 10)
        izq = widget.QVBoxLayout()
        izq.setSpacing(3)
        izq.addWidget(etiqueta(f["comprobante"], "facturaComprobante"))
        izq.addWidget(etiqueta(f"Emitida {pv.fecha_larga(f['emision'])} · vence {pv.fecha_larga(f['vencimiento'])}", "facturaFechas"))
        chip = etiqueta(texto, "facturaEstado")
        chip.setProperty("estado", clase)
        chip.setSizePolicy(widget.QSizePolicy.Maximum, widget.QSizePolicy.Fixed)
        fila_chip = widget.QHBoxLayout()
        fila_chip.addWidget(chip)
        fila_chip.addStretch(1)
        izq.addLayout(fila_chip)
        lay.addLayout(izq, 1)
        der = widget.QVBoxLayout()
        der.setSpacing(2)
        monto = etiqueta(pv.pesos_exactos(f["saldo"]), "facturaMonto")
        monto.setAlignment(core.Qt.AlignRight)
        der.addWidget(monto)
        if f["total"] - f["saldo"] > 0.005:          # pagó una parte
            de = etiqueta(f"de {pv.pesos_exactos(f['total'])}", "facturaFechas")
            de.setAlignment(core.Qt.AlignRight)
            der.addWidget(de)
        der.addStretch(1)
        lay.addLayout(der)
        return fila
