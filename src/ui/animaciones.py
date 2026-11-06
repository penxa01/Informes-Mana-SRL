"""Animaciones compartidas de la UI.

Ninguna usa ``QGraphicsEffect`` sobre widgets de contenido: las tarjetas ya llevan
``QGraphicsDropShadowEffect`` y un widget admite un solo efecto. El fundido entre
secciones se hace con una captura del widget anterior (un QLabel descartable, que sí
puede llevar el efecto de opacidad).
"""
import PyQt5.QtCore as core
import PyQt5.QtWidgets as widget

_SIN_LIMITE = 16777215   # QWIDGETSIZE_MAX


def cambiar_con_fundido(stack, idx, duracion=180):
    """``stack.setCurrentIndex(idx)`` con un fundido cruzado desde la página anterior."""
    actual = stack.currentWidget()
    if actual is None or stack.currentIndex() == idx or not stack.isVisible():
        stack.setCurrentIndex(idx)
        return

    viejo = getattr(stack, "_velo_fundido", None)
    if viejo is not None:
        viejo.deleteLater()

    foto = actual.grab()
    stack.setCurrentIndex(idx)

    velo = widget.QLabel(stack)
    velo.setPixmap(foto)
    velo.setGeometry(stack.rect())
    velo.setAttribute(core.Qt.WA_TransparentForMouseEvents, True)
    efecto = widget.QGraphicsOpacityEffect(velo)
    velo.setGraphicsEffect(efecto)
    velo.show()
    velo.raise_()
    stack._velo_fundido = velo

    anim = core.QPropertyAnimation(efecto, b"opacity", velo)
    anim.setDuration(duracion)
    anim.setStartValue(1.0)
    anim.setEndValue(0.0)
    anim.setEasingCurve(core.QEasingCurve.OutCubic)

    def _fin():
        if getattr(stack, "_velo_fundido", None) is velo:
            stack._velo_fundido = None
        velo.deleteLater()

    anim.finished.connect(_fin)
    anim.start()


def desplegar(contenido, visible, animar=True, duracion=170):
    """Muestra u oculta ``contenido`` animando su alto máximo.

    Sin ``animar`` (o con el widget todavía sin mostrar) es un ``setVisible`` directo.
    """
    previa = getattr(contenido, "_anim_desplegar", None)
    if previa is not None:
        previa.stop()

    padre = contenido.parentWidget()
    if not animar or padre is None or not padre.isVisible():
        contenido.setMaximumHeight(_SIN_LIMITE)
        contenido.setVisible(visible)
        return

    anim = core.QPropertyAnimation(contenido, b"maximumHeight", contenido)
    anim.setDuration(duracion)
    anim.setEasingCurve(core.QEasingCurve.InOutCubic)
    contenido._anim_desplegar = anim

    if visible:
        contenido.setMaximumHeight(0)
        contenido.setVisible(True)
        anim.setStartValue(0)
        anim.setEndValue(max(contenido.sizeHint().height(), 1))
        anim.finished.connect(lambda: contenido.setMaximumHeight(_SIN_LIMITE))
    else:
        anim.setStartValue(contenido.height())
        anim.setEndValue(0)

        def _fin():
            contenido.setVisible(False)
            contenido.setMaximumHeight(_SIN_LIMITE)

        anim.finished.connect(_fin)
    anim.start()
