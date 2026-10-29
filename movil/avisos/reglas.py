"""Qué se avisa, a quién y con qué texto. Lógica pura: sin base ni red, para poder probarla sola.

Tres avisos, según cómo avanza un pedido (los cambios los hace la PC o el reparto, directo en la base):
  nuevo       un vendedor cargó un pedido desde el celular        -> admin y superadmin (menos quien lo cargó)
  programado  el pedido quedó programado para su entrega          -> reparto
  entregado   el pedido se marcó como entregado                   -> admin, superadmin y el vendedor que lo cargó
"""
ROLES_ADMIN = ("admin", "superadmin")
EVENTOS = ("nuevo", "programado", "entregado")

# Cuánto avanzó un pedido. 'en camino' (entrega parcial) ya pasó por programado.
_AVANCE = {"pendiente": 0, "programado": 1, "en camino": 1.5, "entregado": 2}
_NIVEL_DEL_EVENTO = {"nuevo": 0, "programado": 1, "entregado": 2}

_MAX_TEXTO = 40


def decidir(estado, origen, hechos):
    """(a_enviar, a_silenciar) para un pedido, según su estado actual y los avisos que ya se registraron.

    A enviar: el aviso que corresponde al estado de AHORA. A silenciar: los avisos de pasos que el pedido ya
    superó sin que se enviaran (por ejemplo, el proceso estuvo apagado y el pedido pasó de pendiente a
    entregado): se anotan como hechos pero no se mandan, para no avisar tarde de algo ya viejo. Un estado
    desconocido no genera nada. 'nuevo' solo existe para los pedidos cargados desde el celular."""
    avance = _AVANCE.get((estado or "").strip().lower())
    if avance is None:
        return [], []
    a_enviar, a_silenciar = [], []
    for evento in EVENTOS:
        if evento in hechos or (evento == "nuevo" and origen != "movil"):
            continue
        nivel = _NIVEL_DEL_EVENTO[evento]
        if avance == nivel:
            a_enviar.append(evento)
        elif avance > nivel:
            a_silenciar.append(evento)
    return a_enviar, a_silenciar


def destinatarios(evento, creado_por):
    """(roles, usuarios, excluir): a quién se le avisa. `creado_por` es el username de quien cargó el pedido
    desde el celular (None si lo cargó la PC)."""
    if evento == "nuevo":
        return list(ROLES_ADMIN), [], [creado_por] if creado_por else []   # nadie se avisa de lo que acaba de hacer
    if evento == "programado":
        return ["reparto"], [], []
    if evento == "entregado":
        return list(ROLES_ADMIN), [creado_por] if creado_por else [], []
    raise ValueError(f"Aviso desconocido: {evento}")


def _corto(texto, largo=_MAX_TEXTO):
    texto = " ".join(str(texto or "").split())
    return texto if len(texto) <= largo else texto[: largo - 1].rstrip() + "…"


def mensaje(evento, pedido):
    """El contenido del aviso (viaja cifrado hasta el celular). `pedido`: id_pedido, cliente, vendedor,
    creado_por y fecha_entrega. Lo mínimo para saber de qué se trata sin abrir la app."""
    cliente = _corto(pedido.get("cliente")) or "Cliente sin nombre"
    if evento == "nuevo":
        titulo = "Pedido nuevo"
        quien = _corto(pedido.get("vendedor") or pedido.get("creado_por"))
        cuerpo = f"{cliente} · cargado por {quien}" if quien else cliente
    elif evento == "programado":
        titulo = "Pedido programado"
        fecha = pedido.get("fecha_entrega")
        cuerpo = f"{cliente} · entrega el {fecha.day}/{fecha.month}" if fecha else f"{cliente} · sin fecha de entrega"
    elif evento == "entregado":
        titulo = "Pedido entregado"
        cuerpo = cliente
    else:
        raise ValueError(f"Aviso desconocido: {evento}")
    return {
        "evento": evento,
        "id_pedido": pedido["id_pedido"],
        "titulo": titulo,
        "cuerpo": cuerpo,
        "etiqueta": f"pedido-{pedido['id_pedido']}-{evento}",   # el mismo aviso no se apila dos veces
    }
