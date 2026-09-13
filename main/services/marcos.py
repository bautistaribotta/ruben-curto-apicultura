# Marcos: recepcion, procesamiento y entrega de marcos de los clientes.

from django.shortcuts import get_object_or_404

from main.models import Cliente, OperacionMarco

from .comunes import _entero_opcional, _fecha_obligatoria, _parsear_dia


# ==========================================================================
#  MARCOS (recepcion, procesamiento y entrega)
# ==========================================================================

# Tope de marcos por tanda. No lo impone la base (el PositiveIntegerField llega
# mucho mas arriba): es un limite de sentido comun para que un cero de mas en el
# teclado no entre como una tanda de un millon de marcos.
MAX_MARCOS = 100000


def _validar_marco(id_cliente, cantidad, estado, fecha_recepcion, fecha_entrega):
    """Limpia y valida una operacion de marcos.

    Devuelve (cliente, cantidad, estado, recepcion, entrega) ya normalizados. La
    entrega es lo unico opcional: mientras esta vacia, la tanda sigue en el galpon.
    Se aceptan fechas pasadas sin restriccion porque el sistema arranca con anios
    de tandas viejas para cargar.
    """
    # El id lo escribe el autocompletado al elegir de la lista: si viene vacio es
    # que se tipeo un nombre sin elegir a nadie, y eso se avisa como corresponde.
    if not str(id_cliente or "").isdigit():
        raise ValueError("Elegí el cliente de la lista.")
    cliente = get_object_or_404(Cliente, id=id_cliente, activo=True)

    cantidad = _entero_opcional(cantidad, "La cantidad de marcos", MAX_MARCOS)
    if not cantidad:
        raise ValueError("La cantidad de marcos es obligatoria y tiene que ser mayor a cero.")

    estado = (estado or "").strip()
    if estado not in dict(OperacionMarco.ESTADOS):
        raise ValueError("Elegí el estado en el que llegaron los marcos.")

    recepcion = _fecha_obligatoria(fecha_recepcion, "La fecha de recepción")
    entrega = _parsear_dia(fecha_entrega, "La fecha de entrega")
    if entrega and entrega < recepcion:
        raise ValueError("La entrega no puede ser anterior a la recepción.")

    return cliente, cantidad, estado, recepcion, entrega


def obtener_marcos():
    """Operaciones de marcos vigentes, de la mas nueva a la mas vieja.

    Trae el cliente en la misma query: el listado lo muestra en cada fila.
    """
    return (OperacionMarco.objects.filter(activa=True)
            .select_related("cliente"))


def obtener_datos_marco(id_marco):
    """Datos de una operacion para rellenar el slide-over de edicion (JSON)."""
    try:
        marco = OperacionMarco.objects.select_related("cliente").get(id=id_marco, activa=True)
    except OperacionMarco.DoesNotExist:
        return None

    return {
        "id": marco.id,
        "id_cliente": marco.cliente_id,
        "cliente": f"{marco.cliente.nombre} {marco.cliente.apellido or ''}".strip(),
        "cantidad": marco.cantidad,
        "estado": marco.estado,
        "fecha_recepcion": marco.fecha_recepcion.isoformat(),
        "fecha_entrega": marco.fecha_entrega.isoformat() if marco.fecha_entrega else "",
    }


def crear_marco(id_cliente, cantidad, estado, fecha_recepcion, fecha_entrega=None):
    cliente, cantidad, estado, recepcion, entrega = _validar_marco(
        id_cliente, cantidad, estado, fecha_recepcion, fecha_entrega
    )
    return OperacionMarco.objects.create(
        cliente=cliente, cantidad=cantidad, estado=estado,
        fecha_recepcion=recepcion, fecha_entrega=entrega,
    )


def editar_marco(id_marco, id_cliente, cantidad, estado, fecha_recepcion, fecha_entrega=None):
    marco = get_object_or_404(OperacionMarco, id=id_marco, activa=True)
    (marco.cliente, marco.cantidad, marco.estado,
     marco.fecha_recepcion, marco.fecha_entrega) = _validar_marco(
        id_cliente, cantidad, estado, fecha_recepcion, fecha_entrega
    )
    marco.save()
    return marco


def eliminar_marco(id_marco):
    # Baja logica, como en el resto del sistema: la tanda sale de los listados
    # pero no se pierde el historial del cliente
    marco = get_object_or_404(OperacionMarco, id=id_marco)
    marco.activa = False
    marco.save()
    return marco


def opciones_clientes_marcos():
    """Items para el modal selector_entidad del chip "Cliente" del listado.

    Ofrece solo los clientes que tienen alguna tanda vigente, asi el filtro nunca
    lista un cliente que no daria resultados.
    """
    clientes = (Cliente.objects.filter(operaciones_marcos__activa=True)
                .distinct().order_by("nombre", "apellido"))
    items = []
    for cliente in clientes:
        nombre = f"{cliente.nombre} {cliente.apellido or ''}".strip()
        items.append({"id": str(cliente.id), "principal": nombre, "busqueda": nombre.lower()})
    items.sort(key=lambda i: i["principal"].lower())
    return items


def nombre_cliente_marcos_filtro(id_cliente):
    """Etiqueta del chip cuando el filtro por cliente esta aplicado.

    Resuelve el nombre aunque el cliente ya no tenga tandas vigentes, para no
    dejar el chip sin texto. Un id no numerico o inexistente devuelve vacio.
    """
    if not (id_cliente or "").isdigit():
        return ""
    cliente = Cliente.objects.filter(id=id_cliente).first()
    return f"{cliente.nombre} {cliente.apellido or ''}".strip() if cliente else ""
