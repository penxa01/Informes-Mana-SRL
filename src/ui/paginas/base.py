"""Contrato común de las páginas del `AppWindow`.

Ver `guideline/propuesta-ui-integrada.md` → "Contrato de página".
Las páginas concretas overridean solo lo que necesitan.
"""
import PyQt5.QtWidgets as widget


class PaginaBase(widget.QWidget):
    #: Si True, el AppWindow tapa la página con un overlay "Cargando…" hasta que
    #: `df_ventas` está listo y entonces llama a `on_ventas_listas(df)`.
    necesita_ventas = False
    #: Si True, la página trae su propio botón de "Actualizar ventas" (junto a Generar) y
    #: el AppWindow NO le agrega la franja de comandos de arriba (una fila entera de menos).
    tiene_boton_actualizar = False

    def __init__(self, app):
        super().__init__()
        #: referencia al AppWindow — expone `df_ventas`, `status`, `recurso(nombre)`.
        self.app = app

    # ── hooks opcionales ─────────────────────────────────────────────────────
    def on_activar(self):
        """Se llama cada vez que la página pasa a ser la visible del stack."""

    def on_ventas_listas(self, df):
        """Se llama cuando la carga de `fachist` termina (solo si `necesita_ventas`)."""

    def acciones_barra(self):
        """Lista de `QAction` para la franja de comandos contextual del AppWindow.

        `[]` (default) → esa franja queda oculta para esta página.
        """
        return []
