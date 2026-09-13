"""
Opciones de los modales selectores y etiquetas de los chips de filtro de las
pantallas de viajes y operaciones.
"""

import re

from main.models import (Producto, Cliente, ProductoPorKg, Empleado, Vehiculo, DetalleViaje,
                         DetalleViajeCereal, DestinoViajeReparto)


def opciones_empleados_filtro():
    # Items para el modal selector_entidad del chip "Empleado" (filtro de las vistas de
    # viaje). Lista los empleados activos, el mismo universo que el alta de un viaje.
    items = []
    for empleado in Empleado.objects.filter(activo=True).order_by("nombre", "apellido"):
        nombre = f"{empleado.nombre} {empleado.apellido}".strip()
        items.append({
            "id": empleado.id,
            "principal": nombre,
            "busqueda": nombre.lower(),
        })
    return items


def opciones_vehiculos_filtro():
    # Items para el modal del chip "Vehiculo". La patente viaja como linea secundaria y
    # tambien entra en la busqueda por texto del modal.
    items = []
    for vehiculo in Vehiculo.objects.filter(activo=True).order_by("nombre"):
        items.append({
            "id": vehiculo.id,
            "principal": vehiculo.nombre,
            "secundario": vehiculo.patente,
            "busqueda": f"{vehiculo.nombre} {vehiculo.patente}".lower(),
        })
    return items


def _opciones_destinos_texto(valores):
    # Arma los items del modal de destino a partir de una lista de strings (los destinos
    # de miel/cera y de cereal se escriben a mano, no salen de un catalogo). El propio
    # texto es el id que viaja al filtrar.
    items = []
    for destino in valores:
        if not destino:
            continue
        items.append({
            "id": destino,
            "principal": destino,
            "busqueda": destino.lower(),
        })
    return items


def opciones_destinos_viaje():
    valores = (DetalleViaje.objects.filter(viaje__activo=True)
               .values_list("destino", flat=True).distinct().order_by("destino"))
    return _opciones_destinos_texto(valores)


def opciones_destinos_cereal():
    valores = (DetalleViajeCereal.objects.filter(viaje_cereal__activo=True)
               .values_list("destino", flat=True).distinct().order_by("destino"))
    return _opciones_destinos_texto(valores)


def opciones_destinos_reparto_filtro():
    # El destino de un reparto sale del catalogo de localidades, asi que el modal lista
    # las localidades activas y filtra por su id (no por texto libre).
    items = []
    for destino in DestinoViajeReparto.objects.filter(activo=True).order_by("localidad_destino"):
        items.append({
            "id": destino.id,
            "principal": destino.localidad_destino,
            "busqueda": destino.localidad_destino.lower(),
        })
    return items


def nombre_empleado_filtro(id_empleado):
    # Etiqueta del chip cuando el filtro por empleado esta aplicado. Resuelve el nombre
    # aunque el empleado ya no este activo, para no dejar el chip sin texto.
    if not id_empleado:
        return ""
    empleado = Empleado.objects.filter(id=id_empleado).first()
    return f"{empleado.nombre} {empleado.apellido}".strip() if empleado else ""


def nombre_vehiculo_filtro(id_vehiculo):
    if not id_vehiculo:
        return ""
    vehiculo = Vehiculo.objects.filter(id=id_vehiculo).first()
    return vehiculo.nombre if vehiculo else ""


def nombre_destino_reparto_filtro(id_destino):
    if not id_destino:
        return ""
    destino = DestinoViajeReparto.objects.filter(id=id_destino).first()
    return destino.localidad_destino if destino else ""


def opciones_productos_operaciones():
    """Items para el modal selector_entidad del chip "Producto" del listado.

    Ofrece solo lo que realmente aparece en alguna operacion activa, asi el filtro
    nunca lista un producto que no daria resultados. Cada linea de operacion apunta
    a un producto de catalogo o a un articulo a granel (nunca a los dos), por eso el
    id viaja como token: "p<id>" para el producto y "g<id>" para el articulo a granel,
    el mismo esquema que usa el filtro de Deudas.
    """
    items = []
    productos = (Producto.objects.filter(detalleoperacion__operacion__activa=True)
                 .distinct().order_by("nombre"))
    for producto in productos:
        items.append({
            "id": f"p{producto.id}",
            "principal": producto.nombre,
            "busqueda": producto.nombre.lower(),
        })
    granel = (ProductoPorKg.objects.filter(detalleoperacion__operacion__activa=True)
              .distinct().order_by("articulo"))
    for cotizacion in granel:
        nombre = f"{cotizacion.articulo} (por {cotizacion.abreviatura})"
        items.append({
            "id": f"g{cotizacion.id}",
            "principal": nombre,
            "busqueda": nombre.lower(),
        })
    items.sort(key=lambda i: i["principal"].lower())
    return items


def nombre_producto_operaciones_filtro(token):
    """Etiqueta del chip cuando el filtro por producto esta aplicado.

    El token distingue producto de catalogo ("p<id>") de articulo a granel
    ("g<id>"); resuelve el nombre aunque el articulo ya no aparezca en las opciones,
    para no dejar el chip sin texto. Un token mal formado devuelve cadena vacia.
    """
    if not re.fullmatch(r"[pg]\d+", token or ""):
        return ""
    ident = token[1:]
    if token[0] == "p":
        producto = Producto.objects.filter(id=ident).first()
        return producto.nombre if producto else ""
    cotizacion = ProductoPorKg.objects.filter(id=ident).first()
    return f"{cotizacion.articulo} (por {cotizacion.abreviatura})" if cotizacion else ""


def opciones_clientes_operaciones():
    """Items para el modal selector_entidad del chip "Cliente" del listado.

    Ofrece solo los clientes que aparecen en alguna operacion activa, asi el filtro
    nunca lista un cliente que no daria resultados. El id viaja tal cual (numerico),
    a diferencia del filtro de producto que necesita un token con prefijo.
    """
    clientes = (Cliente.objects.filter(operacion__activa=True)
                .distinct().order_by("nombre", "apellido"))
    items = []
    for cliente in clientes:
        nombre = f"{cliente.nombre} {cliente.apellido or ''}".strip()
        items.append({
            "id": str(cliente.id),
            "principal": nombre,
            "busqueda": nombre.lower(),
        })
    items.sort(key=lambda i: i["principal"].lower())
    return items


def nombre_cliente_operaciones_filtro(id_cliente):
    """Etiqueta del chip cuando el filtro por cliente esta aplicado.

    Resuelve el nombre aunque el cliente ya no aparezca en las opciones (por ej. si
    quedo sin operaciones activas), para no dejar el chip sin texto. Un id no
    numerico o inexistente devuelve cadena vacia.
    """
    if not (id_cliente or "").isdigit():
        return ""
    cliente = Cliente.objects.filter(id=id_cliente).first()
    return f"{cliente.nombre} {cliente.apellido or ''}".strip() if cliente else ""


def incluir_asignado(opciones, asignado):
    """
    Devuelve las opciones de un <select> incluyendo el registro actualmente asignado,
    aunque este inactivo (y por lo tanto ausente del queryset de activos). Asi, al editar
    un viaje cuyo empleado, vehiculo o cliente fue dado de baja, su valor sigue
    preseleccionado en vez de obligar a elegir otro.
    """
    opciones = list(opciones)
    if asignado and asignado not in opciones:
        opciones.append(asignado)
    return opciones
