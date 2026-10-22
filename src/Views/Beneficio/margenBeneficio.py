import PyQt5.QtWidgets as widget
import PyQt5.QtGui as Gui
import PyQt5.QtCore as Qt
import pandas as pd
from dbfread import DBF
from datetime import datetime
import os
from src.Views.Beneficio.DetalleBeneficio import DetalleDialog
from src.ui.widgets.indicadores import barra_porcentaje, color_margen
from src.controllers import config

# ── Índices de columna de la tabla principal ────────────────────────────────
_C_NUM, _C_SKU, _C_PROD, _C_COSTO, _C_VENTAS, _C_MARGEN, _C_PCT, _C_ACCION = range(8)

_ENCABEZADOS = ["#", "SKU", "Producto / Descripción", "Costo Unit.", "Total Ventas",
                "Margen $", "Margen %", "Acción"]

_TABLA_QSS = """
    QTableWidget {
        background-color: white;
        alternate-background-color: #f8fafc;
        selection-background-color: #dbeafe;
        selection-color: #1e293b;
        gridline-color: #eef2f7;
        border: none;
    }
    QTableWidget::item { padding: 4px 8px; border: none; }
    QHeaderView::section {
        background-color: #1e293b;
        color: #e2e8f0;
        padding: 7px 8px;
        border: none;
        border-right: 1px solid #334155;
        font-weight: 700;
        font-size: 10px;
    }
    QTableCornerButton::section { background-color: #1e293b; border: none; }
"""

_VERDE_BG, _VERDE_FG = Gui.QColor(209, 250, 229), Gui.QColor(6, 95, 70)
_ROJO_BG, _ROJO_FG = Gui.QColor(254, 226, 226), Gui.QColor(153, 27, 27)


def _money(v):
    try:
        s = f"{float(v):,.2f}"
    except (TypeError, ValueError):
        return "$ 0,00"
    return "$ " + s.replace(",", "@").replace(".", ",").replace("@", ".")


class _CostoDelegate(widget.QStyledItemDelegate):
    """Delegate exclusivo para la columna Costo: selecciona todo al abrir y valida número al confirmar."""

    def createEditor(self, parent, option, index):
        editor = widget.QLineEdit(parent)
        editor.setAlignment(Qt.Qt.AlignRight)
        return editor

    def setEditorData(self, editor, index):
        val = str(index.data(Qt.Qt.DisplayRole) or "0").replace("$", "").strip()
        # "1.234,56" -> "1234.56" ; "1234.56" -> "1234.56"
        if "," in val:
            val = val.replace(".", "").replace(",", ".")
        editor.setText(val)
        editor.selectAll()

    def setModelData(self, editor, model, index):
        texto = editor.text().strip()
        try:
            if ',' in texto and '.' in texto:
                texto = texto.replace('.', '').replace(',', '.')
            else:
                texto = texto.replace(',', '.')
            valor = float(texto)
            model.setData(index, f"{valor:.4f}", Qt.Qt.DisplayRole)
        except ValueError:
            pass  # Valor inválido: no actualizar, mantener el anterior


class margenBeneficio(widget.QWidget):
    """Análisis de margen. Embebible: se arma vacío y se puebla con ``cargar()``.

    Estética basada en prototypeExample/prototypeMargenBeneficio.html.
    Compatibilidad: ``margenBeneficio(df_periodo_ventas=...)`` (uso viejo,
    ``main_legacy``) carga y maximiza como antes.
    """

    COLS_REQUERIDAS = ["FECHA", "MODELO", "U_VENDIDAS", "TOTAVEN"]
    COLS_OPCIONALES = ["CUENTA", "NROEST", "TC", "NC", "DESC"]

    def __init__(self, parent=None, df_periodo_ventas=None):
        super().__init__(parent)
        self.index = 0
        self.TotalLts = 0
        self.TotalPremium = 0
        self.modified = False

        self.clientes_dict = {}
        self.cache_precios = {}
        self.cache_nombres_productos = {}
        self.cache_artiprov = {}

        self.precios = None
        self.abmartic_df = None
        self._catalogos_ok = False

        self.periodoVentas = None
        self.content_table = pd.DataFrame(columns=["SKU", "Producto", "Total Ventas", "Margen de beneficio", 'Detalle'])
        self.datos_originales = pd.DataFrame()
        self.detalles_por_sku = {}
        self._preset = None   # None | "alto" | "medio" | "bajo"

        self.setupUI()

        if df_periodo_ventas is not None:
            self.setWindowTitle("Margen de venta")
            self.setMinimumSize(900, 550)
            self.cargar(df_periodo_ventas)
            self.showMaximized()
            self.raise_()
            self.activateWindow()

    def _asegurar_catalogos(self):
        """Lee clientes + lista de precios + abmartic una sola vez."""
        if self._catalogos_ok:
            return
        self.cargar_clientes()
        try:
            self.precios = pd.read_excel(
                os.path.join(config.EXCEL_PRECIOS_PATH, 'Lista de precios Mana.xlsm'),
                sheet_name='Lista De Precios', header=2)
            self.precios = self.precios[["SKU", 'Producto', "Precio Por envase"]]
            self.precios = self.precios.dropna(subset=["SKU"])
            self.precios['SKU_NORM'] = self.precios['SKU'].astype(str).str.strip().str.upper()
        except Exception as e:
            widget.QMessageBox.warning(self, "Advertencia", f"No se pudo cargar la lista de precios: {e}\nSe usarán precios en 0.")
            self.precios = pd.DataFrame(columns=["SKU", 'Producto', "Precio Por envase", "SKU_NORM"])
        self.cargar_abmartic()
        self._catalogos_ok = True

    def cargar(self, df_periodo_ventas):
        """(Re)puebla el análisis con un período ya filtrado. Llamable N veces."""
        if df_periodo_ventas is None or df_periodo_ventas.empty:
            widget.QMessageBox.warning(self, "Sin datos", "No hay datos para procesar en el período seleccionado.")
            return
        if not all(c in df_periodo_ventas.columns for c in self.COLS_REQUERIDAS):
            widget.QMessageBox.critical(self, "Error", "Faltan columnas requeridas en los datos.")
            return
        disponibles = [c for c in self.COLS_REQUERIDAS + self.COLS_OPCIONALES if c in df_periodo_ventas.columns]
        pv = df_periodo_ventas[disponibles].copy()
        pv = pv.dropna(subset=["MODELO", "U_VENDIDAS", "TOTAVEN"])
        if pv.empty:
            widget.QMessageBox.warning(self, "Sin datos", "No hay datos válidos para procesar.")
            return

        self.periodoVentas = pv
        self._asegurar_catalogos()

        # limpiar estado de una corrida anterior
        self.cache_precios.clear()
        self.cache_nombres_productos.clear()
        self.cache_artiprov.clear()
        self.detalles_por_sku = {}
        self._preset = None
        self._marcar_preset_activo()
        self.search_input.clear()
        self.info_periodo.setText(
            f"Registros de ventas: {len(self.periodoVentas)}   •   Clientes cargados: {len(self.clientes_dict)}"
        )

        self.margenesBeneficio(self.periodoVentas)

    def cargar_clientes(self):
        """Cargar nombres de clientes desde archivo DBF"""
        try:
            ruta_clientes = os.path.join(config.DBF_BASE_PATH, 'ctaclien.DBF')
            clientes_df = None
            if os.path.exists(ruta_clientes):
                try:
                    clientes_df = pd.DataFrame(iter(DBF(ruta_clientes, encoding=config.DBF_ENCODING)))
                except Exception as e:
                    print(f"Error al cargar clientes: {e}")

            if clientes_df is not None and not clientes_df.empty:
                if 'CNUMERO' in clientes_df.columns and 'CNOMBRE' in clientes_df.columns:
                    for _, cliente in clientes_df.iterrows():
                        try:
                            cuenta = str(int(float(cliente['CNUMERO']))).strip()
                        except (ValueError, TypeError):
                            cuenta = str(cliente['CNUMERO']).strip()

                        nombre = str(cliente['CNOMBRE']).strip()
                        if cuenta and nombre and nombre.lower() != 'nan':
                            self.clientes_dict[cuenta] = nombre

                    print(f"Se cargaron {len(self.clientes_dict)} clientes")
                else:
                    print("No se encontraron las columnas CNUMERO y CNOMBRE en la base de clientes")
            else:
                print("No se pudo cargar la base de datos de clientes")

        except Exception as e:
            print(f"Error general al cargar clientes: {e}")
            widget.QMessageBox.warning(self, "Advertencia", f"No se pudieron cargar los nombres de clientes: {e}")

    def cargar_abmartic(self):
        """Cargar archivo abmartic.dbf una sola vez en memoria"""
        try:
            ruta_abmartic = os.path.join(config.DBF_BASE_PATH, 'abmartic.DBF')
            if os.path.exists(ruta_abmartic):
                try:
                    abmartic_dbf = DBF(ruta_abmartic, encoding=config.DBF_ENCODING)
                    self.abmartic_df = pd.DataFrame(iter(abmartic_dbf))
                    self.abmartic_df['CODART_NORM'] = self.abmartic_df['CODART'].astype(str).str.strip().str.upper()
                    print(f"abmartic.dbf cargado exitosamente con {len(self.abmartic_df)} registros")
                except Exception as e:
                    print(f"Error al cargar abmartic.dbf: {e}")
                    self.abmartic_df = None
            else:
                print(f"Archivo abmartic.dbf no encontrado en {ruta_abmartic}")
                self.abmartic_df = None
        except Exception as e:
            print(f"Error general al cargar abmartic.dbf: {e}")
            self.abmartic_df = None

    # ── construcción de UI ──────────────────────────────────────────────────
    def setupUI(self):
        self.configurar_estilo()

        layout = widget.QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        layout.addWidget(self._crear_tarjeta_encabezado())
        layout.addWidget(self._crear_tarjeta_tabla(), 1)
        layout.addWidget(self._crear_tarjeta_resumen())

    def configurar_estilo(self):
        self.setStyleSheet("""
            QWidget {
                background-color: #f1f5f9;
                color: #334155;
                font-family: 'Segoe UI', Arial, sans-serif;
            }
            QLabel#tarjetaTitulo { font-size: 11px; font-weight: 700; color: #334155; }
            QLineEdit {
                border: 1px solid #cbd5e1; border-radius: 5px;
                padding: 5px 8px; font-size: 11px; background-color: white;
                selection-background-color: #2563eb;
            }
            QLineEdit:focus { border: 1px solid #2563eb; }
        """)

    def _tarjeta(self):
        f = widget.QFrame()
        f.setObjectName("tarjeta")
        f.setStyleSheet("#tarjeta { background-color: white; border: 1px solid #e2e8f0; border-radius: 8px; }")
        return f

    def _crear_tarjeta_encabezado(self):
        tarjeta = self._tarjeta()
        lay = widget.QVBoxLayout(tarjeta)
        lay.setContentsMargins(14, 10, 14, 10)
        lay.setSpacing(8)

        # fila 1: título + badge de metadatos
        fila_top = widget.QHBoxLayout()
        fila_top.setSpacing(10)

        icono = widget.QLabel("📊")
        icono.setStyleSheet("font-size: 16px; background-color: #eff6ff; border: 1px solid #bfdbfe; border-radius: 6px; padding: 3px 6px;")
        fila_top.addWidget(icono, 0, Qt.Qt.AlignTop)

        col_tit = widget.QVBoxLayout()
        col_tit.setSpacing(1)
        titulo = widget.QLabel("Análisis de Margen de Beneficio")
        titulo.setStyleSheet("font-size: 15px; font-weight: 800; color: #0f172a;")
        sub = widget.QLabel("Rentabilidad individualizada por SKU, margen bruto y ratios porcentuales")
        sub.setStyleSheet("font-size: 11px; color: #64748b;")
        col_tit.addWidget(titulo)
        col_tit.addWidget(sub)
        fila_top.addLayout(col_tit)
        fila_top.addStretch(1)

        self.info_periodo = widget.QLabel("Elegí un período y generá el informe.")
        self.info_periodo.setStyleSheet(
            "font-size: 11px; color: #475569; background-color: #f8fafc;"
            " border: 1px solid #e2e8f0; border-radius: 6px; padding: 5px 10px;"
        )
        fila_top.addWidget(self.info_periodo, 0, Qt.Qt.AlignVCenter)
        lay.addLayout(fila_top)

        linea = widget.QFrame()
        linea.setFrameShape(widget.QFrame.HLine)
        linea.setStyleSheet("color: #f1f5f9; max-height: 1px;")
        lay.addWidget(linea)

        # fila 2: búsqueda + presets
        fila_busq = widget.QHBoxLayout()
        fila_busq.setSpacing(6)

        lbl_b = widget.QLabel("🔍  Buscar:")
        lbl_b.setStyleSheet("font-size: 11px; font-weight: 700; color: #475569;")
        fila_busq.addWidget(lbl_b)

        self.search_input = widget.QLineEdit()
        self.search_input.setPlaceholderText("SKU o nombre del producto (ej. SPIRAX, HELIX, L60…)")
        self.search_input.textChanged.connect(self.filtrar_tabla)
        fila_busq.addWidget(self.search_input, 1)

        btn_limpiar = widget.QPushButton("✖ Limpiar")
        btn_limpiar.setStyleSheet(
            "QPushButton { background-color: white; color: #475569; border: 1px solid #cbd5e1;"
            " border-radius: 5px; padding: 5px 10px; font-size: 11px; }"
            " QPushButton:hover { background-color: #f1f5f9; }"
        )
        btn_limpiar.clicked.connect(self.limpiar_busqueda)
        fila_busq.addWidget(btn_limpiar)

        sep = widget.QLabel("|")
        sep.setStyleSheet("color: #cbd5e1;")
        fila_busq.addWidget(sep)

        self._btns_preset = {}
        for clave, texto, base, activo in [
            ("alto", "Margen > 25%", ("#065f46", "#ecfdf5", "#a7f3d0"), ("#ffffff", "#059669", "#059669")),
            ("medio", "20% – 25%", ("#92400e", "#fffbeb", "#fde68a"), ("#ffffff", "#d97706", "#d97706")),
            ("bajo", "Bajo < 20%", ("#9f1239", "#fff1f2", "#fecdd3"), ("#ffffff", "#e11d48", "#e11d48")),
        ]:
            b = widget.QPushButton(texto)
            b.setCheckable(True)
            b.setProperty("_base", base)
            b.setProperty("_activo", activo)
            b.clicked.connect(lambda _=False, c=clave: self._toggle_preset(c))
            self._btns_preset[clave] = b
            fila_busq.addWidget(b)
        self._marcar_preset_activo()

        lay.addLayout(fila_busq)
        return tarjeta

    def _crear_tarjeta_tabla(self):
        tarjeta = self._tarjeta()
        lay = widget.QVBoxLayout(tarjeta)
        lay.setContentsMargins(1, 1, 1, 1)
        lay.setSpacing(0)

        self.tabla = widget.QTableWidget()
        self.tabla.setColumnCount(len(_ENCABEZADOS))
        self.tabla.setHorizontalHeaderLabels(_ENCABEZADOS)
        self.tabla.setStyleSheet(_TABLA_QSS)
        self.tabla.setAlternatingRowColors(True)
        self.tabla.setSelectionBehavior(widget.QAbstractItemView.SelectRows)
        self.tabla.verticalHeader().setVisible(False)
        self.tabla.verticalHeader().setDefaultSectionSize(28)
        self.tabla.horizontalHeader().setStretchLastSection(False)

        header = self.tabla.horizontalHeader()
        modos = {
            _C_NUM: (widget.QHeaderView.Fixed, 42),
            _C_SKU: (widget.QHeaderView.Interactive, 90),
            _C_PROD: (widget.QHeaderView.Stretch, None),
            _C_COSTO: (widget.QHeaderView.Interactive, 120),
            _C_VENTAS: (widget.QHeaderView.Interactive, 140),
            _C_MARGEN: (widget.QHeaderView.Interactive, 140),
            _C_PCT: (widget.QHeaderView.Interactive, 130),
            _C_ACCION: (widget.QHeaderView.Fixed, 70),
        }
        for col, (modo, ancho) in modos.items():
            header.setSectionResizeMode(col, modo)
            if ancho is not None:
                self.tabla.setColumnWidth(col, ancho)

        self.tabla.setEditTriggers(widget.QAbstractItemView.DoubleClicked)
        self.tabla.setItemDelegateForColumn(_C_COSTO, _CostoDelegate(self.tabla))
        self.tabla.cellChanged.connect(self.on_costo_cambiado)

        lay.addWidget(self.tabla)
        return tarjeta

    def _crear_tarjeta_resumen(self):
        tarjeta = self._tarjeta()
        lay = widget.QHBoxLayout(tarjeta)
        lay.setContentsMargins(10, 7, 10, 7)
        lay.setSpacing(8)

        self.label_total_ventas = self._pill("Total Ventas", "#0f172a", "#f8fafc", "#e2e8f0")
        self.label_total_margen = self._pill("Total Margen", "#047857", "#ecfdf5", "#a7f3d0")
        self.label_margen_promedio = self._pill("Margen Promedio", "#1d4ed8", "#eff6ff", "#bfdbfe")
        self.label_productos_mostrados = self._pill("Productos", "#334155", "#f8fafc", "#e2e8f0")
        for w in (self.label_total_ventas, self.label_total_margen,
                  self.label_margen_promedio, self.label_productos_mostrados):
            lay.addWidget(w[0])
        lay.addStretch(1)

        btn_exportar = widget.QPushButton("  Exportar a Excel")
        btn_exportar.setStyleSheet(
            "QPushButton { background-color: #107c41; color: white; border: none;"
            " border-radius: 6px; padding: 8px 18px; font-size: 12px; font-weight: 700; }"
            " QPushButton:hover { background-color: #0e6b37; }"
            " QPushButton:pressed { background-color: #0b5a2e; }"
        )
        btn_exportar.clicked.connect(self.exportar_excel)
        lay.addWidget(btn_exportar)
        return tarjeta

    def _pill(self, titulo, color_valor, bg, borde):
        cont = widget.QFrame()
        cont.setStyleSheet(f"QFrame {{ background-color: {bg}; border: 1px solid {borde}; border-radius: 5px; }}")
        h = widget.QHBoxLayout(cont)
        h.setContentsMargins(9, 4, 9, 4)
        h.setSpacing(5)
        t = widget.QLabel(f"{titulo.upper()}:")
        t.setStyleSheet("font-size: 9px; font-weight: 700; color: #64748b; background: transparent; border: none;")
        v = widget.QLabel("—")
        v.setStyleSheet(f"font-size: 12px; font-weight: 800; color: {color_valor}; background: transparent; border: none; font-family: Consolas;")
        h.addWidget(t)
        h.addWidget(v)
        return cont, v

    # ── presets de margen ───────────────────────────────────────────────────
    def _toggle_preset(self, clave):
        self._preset = None if self._preset == clave else clave
        self._marcar_preset_activo()
        self.filtrar_tabla()

    def _marcar_preset_activo(self):
        if not hasattr(self, "_btns_preset"):
            return
        for clave, b in self._btns_preset.items():
            activo = (self._preset == clave)
            b.setChecked(activo)
            fg, bg, borde = b.property("_activo" if activo else "_base")
            b.setStyleSheet(
                f"QPushButton {{ background-color: {bg}; color: {fg}; border: 1px solid {borde};"
                f" border-radius: 5px; padding: 4px 9px; font-size: 10px; font-weight: 700; }}"
            )

    def _mascara_preset(self, df):
        if self._preset is None or "Margen %" not in df.columns:
            return pd.Series(True, index=df.index)
        pct = df["Margen %"]
        if self._preset == "alto":
            return pct > 25
        if self._preset == "medio":
            return (pct >= 20) & (pct <= 25)
        return pct < 20

    # ── cálculo de márgenes ─────────────────────────────────────────────────
    def margenesBeneficio(self, ventas):
        """Procesa los datos de ventas y calcula márgenes de beneficio"""
        datos_acumulados = {}

        ventas_procesadas = ventas.copy()
        ventas_procesadas['MODELO_NORM'] = ventas_procesadas['MODELO'].astype(str).str.strip().str.upper()

        for index, venta in ventas_procesadas.iterrows():
            sku = str(venta['MODELO']).strip()
            sku_norm = venta['MODELO_NORM']

            try:
                total_venta = float(venta['TOTAVEN']) if pd.notna(venta['TOTAVEN']) else 0
                unidades = float(venta['U_VENDIDAS']) if pd.notna(venta['U_VENDIDAS']) else 0
            except (ValueError, TypeError):
                continue

            if unidades == 0:
                continue

            precio_por_envase = self.obtener_precio_por_envase(sku_norm)
            if precio_por_envase == 0:
                print(f"Precio por envase no encontrado para SKU: {sku}")
            precio_venta_unitario = total_venta / unidades
            margen_unitario = precio_venta_unitario - precio_por_envase
            margen_total = margen_unitario * unidades

            producto = self.obtener_nombre_producto(sku_norm)

            cuenta_raw = venta.get('CUENTA', 'N/A')
            try:
                cuenta_clean = str(int(float(cuenta_raw))) if cuenta_raw != 'N/A' else 'N/A'
            except (ValueError, TypeError):
                cuenta_clean = str(cuenta_raw)

            detalle_venta = {
                'FECHA': venta.get('FECHA', 'N/A'),
                'CUENTA': cuenta_clean,
                'TC': venta.get('TC', 'N/A'),
                'NC': venta.get('NC', 'N/A'),
                'U_VENDIDAS': unidades,
                'TOTAVEN': total_venta,
                'PRECIO_UNITARIO': precio_venta_unitario,
                'PRECIO_COSTO': precio_por_envase,
                'MARGEN_UNITARIO': margen_unitario
            }

            if sku in datos_acumulados:
                datos_acumulados[sku]['Total Ventas'] += total_venta
                datos_acumulados[sku]['Margen de beneficio'] += margen_total
                datos_acumulados[sku]['Unidades Vendidas'] += unidades
                self.detalles_por_sku[sku].append(detalle_venta)
            else:
                datos_acumulados[sku] = {
                    'SKU': sku,
                    'Producto': producto,
                    'Costo': precio_por_envase,
                    'Total Ventas': total_venta,
                    'Margen de beneficio': margen_total,
                    'Unidades Vendidas': unidades
                }
                self.detalles_por_sku[sku] = [detalle_venta]

        if datos_acumulados:
            self.content_table = pd.DataFrame(list(datos_acumulados.values()))
            self.content_table['Margen %'] = (
                (self.content_table['Margen de beneficio'] / (self.content_table['Total Ventas'] - self.content_table['Margen de beneficio'])) * 100
            ).round(2)
            self.datos_originales = self.content_table.copy()
            self.actualizar_tabla()
        else:
            self.content_table = pd.DataFrame()
            self.datos_originales = pd.DataFrame()
            widget.QMessageBox.information(self, "Sin datos", "No hay datos válidos para mostrar en el período seleccionado.")

    def filtrar_tabla(self):
        """Filtra la tabla por texto de búsqueda + preset de margen."""
        if self.datos_originales.empty:
            return
        base = self.datos_originales
        texto = self.search_input.text().strip().lower()
        if texto:
            mask = (
                base['SKU'].astype(str).str.lower().str.contains(texto, na=False) |
                base['Producto'].astype(str).str.lower().str.contains(texto, na=False)
            )
        else:
            mask = pd.Series(True, index=base.index)
        mask &= self._mascara_preset(base)
        self.content_table = base[mask].copy()
        self.actualizar_tabla()

    def limpiar_busqueda(self):
        """Limpia búsqueda y preset, muestra todo."""
        self.search_input.clear()
        self._preset = None
        self._marcar_preset_activo()
        self.content_table = self.datos_originales.copy()
        self.actualizar_tabla()

    def obtener_precio_por_envase(self, sku):
        """Busca el precio por envase del SKU en la lista de precios"""
        if self.precios.empty:
            return 0

        sku_limpio = str(sku).strip().upper()

        if sku_limpio in self.cache_precios:
            return self.cache_precios[sku_limpio]

        if self.abmartic_df is not None and sku_limpio not in self.cache_artiprov:
            codart_rows = self.abmartic_df[self.abmartic_df['CODART_NORM'] == sku_limpio]
            if not codart_rows.empty:
                artiprov = codart_rows.iloc[0].get('ARTIPROV', '')
                if pd.notna(artiprov) and str(artiprov).strip():
                    sku_limpio = str(artiprov).strip().upper()
            self.cache_artiprov[sku_limpio] = True

        precio_row = self.precios[self.precios['SKU_NORM'] == sku_limpio]
        if not precio_row.empty:
            return self._parsear_precio(precio_row.iloc[0]['Precio Por envase'], sku_limpio)

        precio_row = self.precios[self.precios['SKU_NORM'].str.contains(sku_limpio, case=False, na=False)]
        if not precio_row.empty:
            return self._parsear_precio(precio_row.iloc[0]['Precio Por envase'], sku_limpio)

        self.cache_precios[sku_limpio] = 0
        return 0

    def _parsear_precio(self, precio, sku_limpio):
        try:
            if isinstance(precio, str):
                precio_limpio = ''.join(c for c in precio if c.isdigit() or c in '.,').replace(',', '.')
                resultado = float(precio_limpio) if precio_limpio else 0
            else:
                resultado = float(precio) if pd.notna(precio) else 0
        except (ValueError, TypeError):
            resultado = 0
        self.cache_precios[sku_limpio] = resultado
        return resultado

    def obtener_nombre_producto(self, sku):
        """Obtiene el nombre del producto desde la columna DESC de periodoVentas"""
        sku_limpio = str(sku).strip().upper()

        if sku_limpio in self.cache_nombres_productos:
            return self.cache_nombres_productos[sku_limpio]

        if 'DESC' in self.periodoVentas.columns:
            producto_rows = self.periodoVentas[
                self.periodoVentas['MODELO'].astype(str).str.strip().str.upper() == sku_limpio
            ]
            if not producto_rows.empty:
                desc = producto_rows.iloc[0]['DESC']
                if pd.notna(desc) and str(desc).strip():
                    resultado = str(desc).strip()
                    self.cache_nombres_productos[sku_limpio] = resultado
                    return resultado

        if not self.precios.empty:
            producto_row = self.precios[self.precios['SKU_NORM'] == sku_limpio]
            if not producto_row.empty:
                nombre = producto_row.iloc[0]['Producto']
                if pd.notna(nombre) and str(nombre).strip():
                    resultado = str(nombre).strip()
                    self.cache_nombres_productos[sku_limpio] = resultado
                    return resultado

            producto_row = self.precios[self.precios['SKU_NORM'].str.contains(sku_limpio, case=False, na=False)]
            if not producto_row.empty:
                nombre = producto_row.iloc[0]['Producto']
                if pd.notna(nombre) and str(nombre).strip():
                    resultado = str(nombre).strip()
                    self.cache_nombres_productos[sku_limpio] = resultado
                    return resultado

        self.cache_nombres_productos[sku_limpio] = str(sku)
        return str(sku)

    def _make_item_readonly(self, text, alignment=None, font=None, bg=None, fg=None):
        item = widget.QTableWidgetItem(text)
        item.setFlags(item.flags() & ~Qt.Qt.ItemIsEditable)
        if alignment:
            item.setTextAlignment(alignment)
        if font:
            item.setFont(font)
        if bg:
            item.setBackground(bg)
        if fg:
            item.setForeground(fg)
        return item

    # ── pintado de tabla ────────────────────────────────────────────────────
    def actualizar_tabla(self):
        """Actualiza la tabla con los datos calculados"""
        self.tabla.blockSignals(True)
        try:
            self.tabla.setRowCount(len(self.content_table))
            if self.content_table.empty:
                self.actualizar_estadisticas()
                return

            font_mono = Gui.QFont("Consolas", 8)
            font_mono_bold = Gui.QFont("Consolas", 8, Gui.QFont.Bold)
            font_normal = Gui.QFont("Segoe UI", 8)
            font_sku = Gui.QFont("Consolas", 9, Gui.QFont.Bold)
            aln_right = Qt.Qt.AlignRight | Qt.Qt.AlignVCenter

            for i, (_, row) in enumerate(self.content_table.iterrows()):
                self.tabla.setRowHeight(i, 28)

                num = self._make_item_readonly(str(i + 1), alignment=Qt.Qt.AlignCenter, font=font_mono, fg=Gui.QColor("#94a3b8"))
                self.tabla.setItem(i, _C_NUM, num)

                self.tabla.setItem(i, _C_SKU, self._make_item_readonly(str(row['SKU']), font=font_sku, fg=Gui.QColor("#0f172a")))
                self.tabla.setItem(i, _C_PROD, self._make_item_readonly(str(row['Producto']), font=font_normal))

                costo = row.get('Costo', 0)
                costo_item = widget.QTableWidgetItem(f"{costo:.4f}")
                costo_item.setTextAlignment(aln_right)
                costo_item.setFont(font_mono_bold)
                costo_item.setBackground(Gui.QColor(255, 251, 235))
                costo_item.setForeground(Gui.QColor(120, 90, 0))
                costo_item.setToolTip("Doble clic para editar el costo unitario. Enter para confirmar.")
                self.tabla.setItem(i, _C_COSTO, costo_item)

                self.tabla.setItem(i, _C_VENTAS, self._make_item_readonly(
                    _money(row['Total Ventas']), alignment=aln_right, font=font_mono))

                self._pintar_margen(i, row['Margen de beneficio'], row['Margen %'])

                btn_detalle = widget.QPushButton("Ver")
                btn_detalle.setStyleSheet(
                    "QPushButton { background-color: #2563eb; color: white; border: none;"
                    " border-radius: 4px; padding: 3px 10px; font-size: 10px; font-weight: 700; }"
                    " QPushButton:hover { background-color: #1d4ed8; }"
                )
                btn_detalle.clicked.connect(lambda checked, sku=row['SKU']: self.mostrar_detalle(sku))
                cont = widget.QWidget()
                cont.setStyleSheet("background: transparent;")
                cl = widget.QHBoxLayout(cont)
                cl.setContentsMargins(4, 2, 4, 2)
                cl.addWidget(btn_detalle)
                self.tabla.setCellWidget(i, _C_ACCION, cont)
        finally:
            self.tabla.blockSignals(False)

        self.actualizar_estadisticas()

    def _pintar_margen(self, fila, margen, pct):
        font_mono_bold = Gui.QFont("Consolas", 8, Gui.QFont.Bold)
        aln_right = Qt.Qt.AlignRight | Qt.Qt.AlignVCenter
        bg, fg = (_VERDE_BG, _VERDE_FG) if margen >= 0 else (_ROJO_BG, _ROJO_FG)
        self.tabla.setItem(fila, _C_MARGEN, self._make_item_readonly(
            _money(margen), alignment=aln_right, font=font_mono_bold, bg=bg, fg=fg))
        self.tabla.setCellWidget(fila, _C_PCT, barra_porcentaje(pct))

    def actualizar_estadisticas(self):
        """Actualiza los pills de estadísticas globales"""
        if self.content_table.empty:
            for _, v in [self.label_total_ventas, self.label_total_margen,
                         self.label_margen_promedio, self.label_productos_mostrados]:
                v.setText("—")
            self.label_productos_mostrados[1].setText("0")
            return
        total_ventas = self.content_table['Total Ventas'].sum()
        total_margen = self.content_table['Margen de beneficio'].sum()
        costo = total_ventas - total_margen
        margen_promedio = (total_margen / costo * 100) if costo > 0 else 0
        self.label_total_ventas[1].setText(_money(total_ventas))
        self.label_total_margen[1].setText(_money(total_margen))
        self.label_margen_promedio[1].setText(f"{margen_promedio:.2f}%".replace(".", ","))
        self.label_productos_mostrados[1].setText(str(len(self.content_table)))

    def on_costo_cambiado(self, fila, columna):
        """Recalcula el margen cuando el usuario edita el costo unitario (señal cellChanged)"""
        if columna != _C_COSTO:
            return

        costo_item = self.tabla.item(fila, _C_COSTO)
        if costo_item is None:
            return
        try:
            nuevo_costo = float(costo_item.text().strip())
        except ValueError:
            return

        sku_item = self.tabla.item(fila, _C_SKU)
        if sku_item is None:
            return
        sku = sku_item.text()

        mask = self.content_table['SKU'].astype(str) == sku
        if not mask.any():
            return

        idx = self.content_table.index[mask][0]
        total_ventas = float(self.content_table.loc[idx, 'Total Ventas'])
        unidades = float(self.content_table.loc[idx, 'Unidades Vendidas'])

        nuevo_margen = total_ventas - nuevo_costo * unidades
        costo_total = total_ventas - nuevo_margen
        nuevo_pct = (nuevo_margen / costo_total * 100) if costo_total != 0 else 0

        self.content_table.loc[idx, 'Costo'] = nuevo_costo
        self.content_table.loc[idx, 'Margen de beneficio'] = nuevo_margen
        self.content_table.loc[idx, 'Margen %'] = round(nuevo_pct, 2)

        if hasattr(self, 'datos_originales') and not self.datos_originales.empty:
            orig_mask = self.datos_originales['SKU'].astype(str) == sku
            if orig_mask.any():
                orig_idx = self.datos_originales.index[orig_mask][0]
                self.datos_originales.loc[orig_idx, 'Costo'] = nuevo_costo
                self.datos_originales.loc[orig_idx, 'Margen de beneficio'] = nuevo_margen
                self.datos_originales.loc[orig_idx, 'Margen %'] = round(nuevo_pct, 2)

        if sku in self.detalles_por_sku:
            for detalle in self.detalles_por_sku[sku]:
                precio_venta = detalle.get('PRECIO_UNITARIO', 0)
                detalle['PRECIO_COSTO'] = nuevo_costo
                detalle['MARGEN_UNITARIO'] = precio_venta - nuevo_costo

        self.tabla.blockSignals(True)
        try:
            costo_item.setText(f"{nuevo_costo:.4f}")
            costo_item.setBackground(Gui.QColor(255, 251, 235))
            costo_item.setForeground(Gui.QColor(120, 90, 0))
            self._pintar_margen(fila, nuevo_margen, nuevo_pct)
        finally:
            self.tabla.blockSignals(False)

        self.actualizar_estadisticas()

    def mostrar_detalle(self, sku):
        """Muestra el detalle de ventas para un SKU específico"""
        if sku in self.detalles_por_sku:
            producto = self.obtener_nombre_producto(sku)
            detalle_dialog = DetalleDialog(
                sku, producto, self.detalles_por_sku[sku], self.clientes_dict, self,
                on_costo_cambiado_cb=lambda: self._cascada_desde_detalle(sku)
            )
            detalle_dialog.exec_()

    def _cascada_desde_detalle(self, sku):
        """Recalcula los totales del SKU en la tabla principal usando los costos del detalle."""
        if sku not in self.detalles_por_sku:
            return

        detalles = self.detalles_por_sku[sku]
        total_margen = sum(d['MARGEN_UNITARIO'] * d['U_VENDIDAS'] for d in detalles)
        total_unidades = sum(d['U_VENDIDAS'] for d in detalles)
        costo_ponderado = sum(d['PRECIO_COSTO'] * d['U_VENDIDAS'] for d in detalles)
        nuevo_costo_unit = costo_ponderado / total_unidades if total_unidades > 0 else 0
        nuevo_pct = (total_margen / costo_ponderado * 100) if costo_ponderado != 0 else 0

        mask = self.content_table['SKU'].astype(str) == str(sku)
        if not mask.any():
            return
        idx = self.content_table.index[mask][0]
        self.content_table.loc[idx, 'Costo'] = nuevo_costo_unit
        self.content_table.loc[idx, 'Margen de beneficio'] = total_margen
        self.content_table.loc[idx, 'Margen %'] = round(nuevo_pct, 2)

        if hasattr(self, 'datos_originales') and not self.datos_originales.empty:
            orig_mask = self.datos_originales['SKU'].astype(str) == str(sku)
            if orig_mask.any():
                orig_idx = self.datos_originales.index[orig_mask][0]
                self.datos_originales.loc[orig_idx, 'Costo'] = nuevo_costo_unit
                self.datos_originales.loc[orig_idx, 'Margen de beneficio'] = total_margen
                self.datos_originales.loc[orig_idx, 'Margen %'] = round(nuevo_pct, 2)

        for row_idx in range(self.tabla.rowCount()):
            sku_item = self.tabla.item(row_idx, _C_SKU)
            if sku_item and sku_item.text() == str(sku):
                self.tabla.blockSignals(True)
                try:
                    costo_item = self.tabla.item(row_idx, _C_COSTO)
                    if costo_item:
                        costo_item.setText(f"{nuevo_costo_unit:.4f}")
                    self._pintar_margen(row_idx, total_margen, nuevo_pct)
                finally:
                    self.tabla.blockSignals(False)
                break

        self.actualizar_estadisticas()

    def exportar_excel(self):
        """Exporta los resultados a un archivo Excel"""
        if self.content_table.empty:
            widget.QMessageBox.warning(self, "Sin datos", "No hay datos para exportar.")
            return

        ruta_archivo, _ = widget.QFileDialog.getSaveFileName(
            self, "Exportar Margen de Beneficio",
            f"margen_beneficio_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
            "Archivos Excel (*.xlsx)"
        )

        if ruta_archivo:
            try:
                with pd.ExcelWriter(ruta_archivo, engine='openpyxl') as writer:
                    df_resumen = self.content_table.copy()
                    df_resumen = df_resumen[['SKU', 'Producto', 'Unidades Vendidas', 'Total Ventas', 'Margen de beneficio', 'Margen %']]
                    df_resumen.to_excel(writer, sheet_name='Resumen', index=False)

                    detalles_completos = []
                    for sku, detalles in self.detalles_por_sku.items():
                        producto = self.obtener_nombre_producto(sku)
                        for detalle in detalles:
                            detalle_completo = detalle.copy()
                            detalle_completo['SKU'] = sku
                            detalle_completo['Producto'] = producto
                            cuenta = str(detalle.get('CUENTA', 'N/A'))
                            detalle_completo['CLIENTE'] = self.clientes_dict.get(cuenta, cuenta)
                            detalle_completo['MARGEN_TOTAL'] = detalle_completo['MARGEN_UNITARIO'] * detalle_completo['U_VENDIDAS']
                            detalles_completos.append(detalle_completo)

                    if detalles_completos:
                        df_detalles = pd.DataFrame(detalles_completos)
                        columnas_orden = ['SKU', 'Producto', 'FECHA', 'CLIENTE', 'CUENTA', 'TC', 'NC',
                                          'U_VENDIDAS', 'TOTAVEN', 'PRECIO_UNITARIO', 'PRECIO_COSTO',
                                          'MARGEN_UNITARIO', 'MARGEN_TOTAL']
                        columnas_existentes = [col for col in columnas_orden if col in df_detalles.columns]
                        df_detalles = df_detalles[columnas_existentes]
                        df_detalles.to_excel(writer, sheet_name='Detalle_Completo', index=False)

                    total_ventas = self.content_table['Total Ventas'].sum()
                    total_margen = self.content_table['Margen de beneficio'].sum()
                    margen_promedio = (total_margen / total_ventas * 100) if total_ventas > 0 else 0
                    productos_con_margen_positivo = len(self.content_table[self.content_table['Margen de beneficio'] > 0])
                    productos_con_margen_negativo = len(self.content_table[self.content_table['Margen de beneficio'] < 0])

                    estadisticas = {
                        'Métrica': [
                            'Total de Productos', 'Productos con Margen Positivo', 'Productos con Margen Negativo',
                            'Total Ventas ($)', 'Total Margen ($)', 'Margen Promedio (%)',
                            'Mejor Producto (Margen $)', 'Peor Producto (Margen $)', 'Clientes Únicos Cargados'
                        ],
                        'Valor': [
                            len(self.content_table), productos_con_margen_positivo, productos_con_margen_negativo,
                            f"${total_ventas:,.2f}", f"${total_margen:,.2f}", f"{margen_promedio:.2f}%",
                            self.content_table.loc[self.content_table['Margen de beneficio'].idxmax(), 'SKU'] if not self.content_table.empty else 'N/A',
                            self.content_table.loc[self.content_table['Margen de beneficio'].idxmin(), 'SKU'] if not self.content_table.empty else 'N/A',
                            len(self.clientes_dict)
                        ]
                    }
                    pd.DataFrame(estadisticas).to_excel(writer, sheet_name='Estadisticas', index=False)

                widget.QMessageBox.information(self, "Éxito", f"Archivo exportado correctamente:\n{ruta_archivo}")

            except Exception as e:
                widget.QMessageBox.critical(self, "Error", f"Error al exportar: {e}")
