# Operaciones de compra y venta: alta, edicion, cancelacion y listado global.

from datetime import datetime, time
from decimal import Decimal, InvalidOperation

from django.utils import timezone
from django.shortcuts import get_object_or_404
from django.db import transaction
from django.db.models import F

from main.models import Producto, Operacion, DetalleOperacion, Pago, ProductoPorKg

from .cotizaciones import (get_cotizacion_cera_operculo, get_cotizacion_dolar_oficial,
                           get_cotizacion_miel_50mm)
from .productos import modificar_stock


def _procesar_item_granel(operacion, item, tipo_operacion):
    """
    Procesa una linea a granel (miel o cera en kilos) dentro de crear_operacion.
    El precio por kilo viene del item: la cotizacion del dia es solo el valor
    precargado en el front y el usuario puede negociarlo linea por linea.
    Debe llamarse dentro de transaction.atomic().
    """
    try:
        kilos = Decimal(str(item.get("cantidad", 0)))
        precio_unitario = Decimal(str(item.get("precio_unitario", 0)))
    except InvalidOperation:
        raise ValueError("La cantidad de kilos y el precio deben ser números válidos.")

    if kilos <= 0:
        raise ValueError("La cantidad de kilos debe ser mayor a 0.")
    if precio_unitario <= 0:
        raise ValueError("El precio por kilo debe ser mayor a 0.")

    cotizacion = get_object_or_404(ProductoPorKg, id=item.get("id_cotizacion"))

    if tipo_operacion == "venta":
        # Descuento condicional atomico, mismo patron que modificar_stock: el
        # chequeo de kilos disponibles y la resta ocurren en una sola sentencia,
        # asi dos ventas concurrentes no pueden sobrevender el mismo tambor
        filas = ProductoPorKg.objects.filter(
            id=cotizacion.id, cantidad__gte=kilos
        ).update(cantidad=F("cantidad") - kilos)

        if filas == 0:
            raise ValueError(
                f"No hay kilos suficientes de {cotizacion.articulo} a granel."
            )
    else:
        ProductoPorKg.objects.filter(id=cotizacion.id).update(
            cantidad=F("cantidad") + kilos
        )

    DetalleOperacion.objects.create(
        operacion=operacion,
        cotizacion=cotizacion,
        cantidad=kilos,
        precio_unitario=precio_unitario,
    )


def _parsear_fecha_operacion(fecha):
    """
    Convierte la fecha "YYYY-MM-DD" que manda el front en un datetime aware,
    o devuelve None si viene vacía o es la fecha de hoy (comportamiento normal).
    """
    if not fecha:
        return None

    try:
        fecha_date = datetime.strptime(str(fecha).strip(), "%Y-%m-%d").date()
    except (ValueError, TypeError):
        raise ValueError("La fecha de la operación no es válida.")

    if fecha_date == timezone.localdate():
        return None

    # Mediodía local para que la fecha no se corra de día al guardarse en UTC
    return timezone.make_aware(datetime.combine(fecha_date, time(12, 0)))


def _parsear_cotizaciones_historicas(datos):
    """
    Valida el dict {valor_dolar, valor_kilo_miel, valor_kilo_cera} que manda el
    front cuando la operación lleva fecha anterior a hoy (los valores de aquel
    día, cargados a mano en el modal). Devuelve Decimals o None si no vino nada.
    """
    if not datos:
        return None

    nombres = {
        "valor_kilo_miel": "la miel menor a 50 mm",
        "valor_dolar": "el dólar oficial",
        "valor_kilo_cera": "la cera opérculo",
    }
    resultado = {}
    for campo, nombre in nombres.items():
        try:
            valor = Decimal(str(datos.get(campo, "")).strip())
        except InvalidOperation:
            raise ValueError(f"El valor de {nombre} no es un número válido.")
        if valor < 1:
            raise ValueError(f"El valor de {nombre} debe ser de 1 o más.")
        resultado[campo] = valor
    return resultado


def _limpiar_observaciones(observaciones):
    """Normaliza la observación opcional de una operación: texto plano, sin
    espacios sobrantes, con tope de 250 caracteres (mismo límite que el modelo)."""
    texto = str(observaciones or "").strip()
    if len(texto) > 250:
        raise ValueError("La observación no puede superar los 250 caracteres.")
    return texto


def crear_operacion(cliente, items, metodo_pago, tipo_operacion, viaje=None, fecha=None,
                    cotizaciones_historicas=None, observaciones=None):
    # Fecha personalizada: permite cargar operaciones viejas. None = hoy.
    fecha_personalizada = _parsear_fecha_operacion(fecha)

    if fecha_personalizada:
        # Con fecha anterior a hoy las cotizaciones "de origen" las carga el
        # usuario en el modal (migración desde el sistema viejo) y son
        # obligatorias. Con fecha futura no hay valores conocibles: quedan
        # vacías en vez de guardar las de hoy como si fueran las de aquel día.
        historicas = _parsear_cotizaciones_historicas(cotizaciones_historicas)
        if historicas:
            valor_dolar = historicas["valor_dolar"]
            valor_miel = historicas["valor_kilo_miel"]
            valor_cera = historicas["valor_kilo_cera"]
        elif fecha_personalizada.date() < timezone.localdate():
            raise ValueError(
                "Para una operación con fecha anterior a hoy hay que cargar las "
                "cotizaciones de ese día (miel menor a 50 mm, dólar oficial y cera opérculo)."
            )
        else:
            valor_dolar = None
            valor_miel = None
            valor_cera = None
    else:
        # Obtenemos las cotizaciones actuales antes de la transacción
        cotizacion_dolar = get_cotizacion_dolar_oficial()
        if cotizacion_dolar:
            valor_dolar = cotizacion_dolar.get("venta")
        else:
            valor_dolar = None

        valor_miel = get_cotizacion_miel_50mm()
        valor_cera = get_cotizacion_cera_operculo()

    with transaction.atomic():
        # Creo la operación con las cotizaciones actuales
        operacion = Operacion.objects.create(
            cliente=cliente,
            viaje=viaje,
            tipo_operacion=tipo_operacion,
            fecha=fecha_personalizada or timezone.now(),
            valor_dolar=valor_dolar,
            valor_kilo_miel=valor_miel,
            valor_kilo_cera=valor_cera,
            observaciones=_limpiar_observaciones(observaciones),
        )

        _aplicar_items(operacion, items, tipo_operacion)

        # Si el pago es "contado", generamos automáticamente un pago usando el monto_total calculado.
        # El pago lleva la misma fecha que la operación (importa al cargar operaciones viejas)
        if metodo_pago.lower() == "contado":
            Pago.objects.create(
                operacion=operacion,
                fecha=operacion.fecha,
                monto=operacion.monto_total
            )

    return operacion


def _aplicar_items(operacion, items, tipo_operacion):
    """
    Crea los detalles de la operación aplicando el impacto de stock de cada
    ítem (productos envasados y líneas a granel). Debe llamarse dentro de
    transaction.atomic(). Compartido entre crear_operacion y editar_operacion.
    """
    for item in items:
        # Item a granel: viene con id_cotizacion en vez de id_producto y la
        # cantidad son kilos, por eso se parsea como Decimal (admite fracciones)
        id_cotizacion = item.get("id_cotizacion")
        if id_cotizacion:
            _procesar_item_granel(operacion, item, tipo_operacion)
            continue

        id_producto = item.get("id_producto")
        # Los productos envasados se venden por unidad entera: la columna de
        # stock es un entero, asi que la cantidad se mantiene como int
        cantidad = int(item.get("cantidad", 0))

        producto = get_object_or_404(Producto, id=id_producto, activo=True)

        if tipo_operacion == "venta":
            # El precio del producto se autocompleta en el front pero es
            # editable, así que se toma del ítem; si no viniera, se cae al
            # precio registrado del producto.
            precio_item = item.get("precio_unitario")
            if precio_item in (None, ""):
                precio_unitario = producto.precio
            else:
                precio_unitario = Decimal(str(precio_item))
            # Resto el stock y sumo a la cantidad vendida con un incremento
            # atómico a nivel BD (F()), evitando el lost update del patrón
            # refresh + save sobre una copia en memoria.
            modificar_stock(id_producto, -cantidad)
            Producto.objects.filter(id=id_producto).update(
                cantidad_vendida=F("cantidad_vendida") + cantidad
            )
        else:
            # En una compra, el precio viene en el ítem
            precio_unitario = Decimal(item.get("precio_unitario"))
            # Sumo el stock y sumo a la cantidad comprada de forma atómica
            modificar_stock(id_producto, cantidad)
            Producto.objects.filter(id=id_producto).update(
                cantidad_comprada=F("cantidad_comprada") + cantidad
            )

        # Creo el detalle vinculado a la operación
        DetalleOperacion.objects.create(
            operacion=operacion,
            producto=producto,
            cantidad=cantidad,
            precio_unitario=precio_unitario,
        )


def servicio_cancelar_operacion(id_operacion):
    with transaction.atomic():
        # Bloqueo la fila de la operación con select_for_update: una segunda
        # cancelación concurrente queda en espera aquí y, al desbloquearse tras
        # el commit de la primera, encontrará activa=False y saldrá por el guard.
        # Esto evita que el stock se revierta dos veces (TOCTOU sobre activa).
        operacion = get_object_or_404(
            Operacion.objects.select_for_update(), id=id_operacion
        )

        # Si ya está cancelada, no hacemos nada
        if not operacion.activa:
            return operacion

        detalles = DetalleOperacion.objects.filter(operacion=operacion)
        _revertir_stock_detalles(operacion, detalles)

        # Marcamos la operación como inactiva (cancelada)
        operacion.activa = False
        operacion.save(update_fields=["activa"])

    return operacion


def _revertir_stock_detalles(operacion, detalles):
    """
    Revierte el impacto de stock de los detalles dados según el tipo de
    operación. Debe llamarse dentro de transaction.atomic(). Compartido entre
    cancelar y editar una operación.
    """
    for detalle in detalles:
        # Lineas a granel: los kilos se revierten sobre la tabla de cotizaciones
        if detalle.cotizacion_id:
            if operacion.tipo_operacion == "venta":
                # Venta revertida: los kilos vuelven al deposito
                ProductoPorKg.objects.filter(id=detalle.cotizacion_id).update(
                    cantidad=F("cantidad") + detalle.cantidad
                )
            else:
                # Compra revertida: quito los kilos, con el mismo chequeo
                # condicional atomico para no dejar el stock negativo
                filas = ProductoPorKg.objects.filter(
                    id=detalle.cotizacion_id, cantidad__gte=detalle.cantidad
                ).update(cantidad=F("cantidad") - detalle.cantidad)

                if filas == 0:
                    raise ValueError(
                        "No se puede revertir la compra: los kilos a granel ya fueron vendidos."
                    )
            continue

        producto = detalle.producto

        if operacion.tipo_operacion == "venta":
            # Si era venta, devuelvo stock y resto de cantidad vendida de
            # forma atómica con F(). La reversión admite productos inactivos:
            # el historial puede referenciar productos ya dados de baja.
            modificar_stock(producto.id, detalle.cantidad, permitir_inactivos=True)
            Producto.objects.filter(id=producto.id).update(
                cantidad_vendida=F("cantidad_vendida") - detalle.cantidad
            )
        else:
            # Si era compra, quito stock y resto de cantidad comprada
            modificar_stock(producto.id, -detalle.cantidad, permitir_inactivos=True)
            Producto.objects.filter(id=producto.id).update(
                cantidad_comprada=F("cantidad_comprada") - detalle.cantidad
            )


def _validar_items_congelados(items, detalles_congelados):
    """
    Al editar una operación, los detalles de productos dados de baja
    (activo=False) están congelados: deben venir en el carrito exactamente
    como estaban (misma cantidad y mismo precio) y no se pueden quitar.

    Devuelve los ítems restantes (los que sí se procesan) y lanza ValueError
    si algún congelado falta en el carrito o llegó modificado.
    """
    congelados = {d.producto_id: d for d in detalles_congelados}
    restantes = []
    for item in items:
        # El front manda el id como string; se normaliza a int para matchear
        # contra producto_id
        try:
            id_producto = int(item.get("id_producto"))
        except (TypeError, ValueError):
            id_producto = None
        detalle = congelados.pop(id_producto, None) if id_producto else None
        if detalle is None:
            restantes.append(item)
            continue

        cantidad = Decimal(str(item.get("cantidad", 0)))
        precio_item = item.get("precio_unitario")
        precio = (
            detalle.precio_unitario
            if precio_item in (None, "")
            else Decimal(str(precio_item))
        )
        if cantidad != detalle.cantidad or precio != detalle.precio_unitario:
            raise ValueError(
                f'El producto "{detalle.producto.nombre}" fue dado de baja: '
                "no se puede modificar su cantidad ni su precio en la operación."
            )

    if congelados:
        nombres = ", ".join(d.producto.nombre for d in congelados.values())
        raise ValueError(
            "Estos productos fueron dados de baja y no se pueden quitar "
            f"de la operación: {nombres}."
        )

    return restantes


def editar_operacion(id_operacion, items, metodo_pago, fecha=None, cotizaciones_historicas=None,
                     observaciones=None):
    """
    Reemplaza los ítems de una operación activa por los nuevos (revirtiendo el
    stock viejo y aplicando el nuevo), y actualiza la fecha si cambió.

    Los detalles de productos dados de baja (activo=False) quedan congelados:
    no se revierten ni se reemplazan, y el carrito debe traerlos idénticos.

    Pagos: si la operación no tiene pagos, el métxdo es editable y "contado"
    genera el pago automático por el nuevo total. Si ya tiene pagos, el métxdo
    no se puede cambiar y los pagos se conservan; el único caso especial es el
    contado puro (un único pago que cubría el total), donde ese pago se ajusta
    al nuevo total para que la operación siga saldada.
    """
    # La fecha se parsea y las cotizaciones se consultan antes de la
    # transacción para no hacer llamadas externas dentro de ella
    fecha_date = None
    if fecha:
        try:
            fecha_date = datetime.strptime(str(fecha).strip(), "%Y-%m-%d").date()
        except (ValueError, TypeError):
            raise ValueError("La fecha de la operación no es válida.")

    cotizaciones_hoy = None
    if fecha_date == timezone.localdate():
        cotizacion_dolar = get_cotizacion_dolar_oficial()
        cotizaciones_hoy = {
            "valor_dolar": cotizacion_dolar.get("venta") if cotizacion_dolar else None,
            "valor_kilo_miel": get_cotizacion_miel_50mm(),
            "valor_kilo_cera": get_cotizacion_cera_operculo(),
        }

    # Valores de aquel día cargados a mano en el modal (fecha anterior a hoy)
    historicas = _parsear_cotizaciones_historicas(cotizaciones_historicas)

    with transaction.atomic():
        # Mismo bloqueo que al cancelar: evita ediciones/cancelaciones concurrentes
        operacion = get_object_or_404(
            Operacion.objects.select_for_update(), id=id_operacion
        )

        if not operacion.activa:
            raise ValueError("No se puede editar una operación cancelada.")

        # La observación se reemplaza siempre por la del formulario (el campo
        # llega precargado al editar, así que vacío significa borrarla)
        texto_observaciones = _limpiar_observaciones(observaciones)
        if texto_observaciones != operacion.observaciones:
            operacion.observaciones = texto_observaciones
            operacion.save(update_fields=["observaciones"])

        # Total anterior: se necesita para detectar el pago automático de contado
        monto_anterior = operacion.monto_total

        # 1) Separo los detalles congelados (productos dados de baja): su fila
        # y su stock no se tocan. El resto se revierte y se borra.
        detalles = DetalleOperacion.objects.filter(operacion=operacion).select_related("producto")
        detalles_congelados = [
            d for d in detalles if d.producto_id and not d.producto.activo
        ]

        # El carrito debe traer cada congelado exactamente igual (misma
        # cantidad y precio); devuelve los ítems que sí se procesan
        items_editables = _validar_items_congelados(items, detalles_congelados)

        detalles_editables = detalles.exclude(id__in=[d.id for d in detalles_congelados])
        _revertir_stock_detalles(operacion, detalles_editables)
        detalles_editables.delete()

        # 2) Aplico los ítems nuevos con las mismas validaciones que al crear
        _aplicar_items(operacion, items_editables, operacion.tipo_operacion)

        # 3) Fecha: solo si cambió respecto de la actual. Mismas reglas que al
        # crear: fecha de hoy lleva cotizaciones actuales; fecha anterior lleva
        # las históricas cargadas en el modal; fecha futura las vacía
        if fecha_date and fecha_date != timezone.localtime(operacion.fecha).date():
            if cotizaciones_hoy:
                operacion.fecha = timezone.now()
                operacion.valor_dolar = cotizaciones_hoy["valor_dolar"]
                operacion.valor_kilo_miel = cotizaciones_hoy["valor_kilo_miel"]
                operacion.valor_kilo_cera = cotizaciones_hoy["valor_kilo_cera"]
            else:
                if historicas:
                    operacion.valor_dolar = historicas["valor_dolar"]
                    operacion.valor_kilo_miel = historicas["valor_kilo_miel"]
                    operacion.valor_kilo_cera = historicas["valor_kilo_cera"]
                elif fecha_date < timezone.localdate():
                    raise ValueError(
                        "Para cambiar la operación a una fecha anterior a hoy hay que cargar las "
                        "cotizaciones de ese día (miel menor a 50 mm, dólar oficial y cera opérculo)."
                    )
                else:
                    operacion.valor_dolar = None
                    operacion.valor_kilo_miel = None
                    operacion.valor_kilo_cera = None
                # Mediodía local para que la fecha no se corra de día en UTC
                operacion.fecha = timezone.make_aware(datetime.combine(fecha_date, time(12, 0)))
            operacion.save(update_fields=["fecha", "valor_dolar", "valor_kilo_miel", "valor_kilo_cera"])

        # 4) Pagos según la regla de edición
        pagos = Pago.objects.filter(operacion=operacion)
        cantidad_pagos = pagos.count()
        monto_nuevo = operacion.monto_total

        if cantidad_pagos == 0:
            # Sin pagos: el métxdo es editable y contado salda la operación
            if (metodo_pago or "").lower() == "contado":
                Pago.objects.create(
                    operacion=operacion,
                    fecha=operacion.fecha,
                    monto=monto_nuevo,
                )
        elif cantidad_pagos == 1:
            # Contado puro: el único pago cubría el total anterior, lo ajusto
            # al nuevo total para que la operación siga saldada
            pago = pagos.first()
            if pago.monto == monto_anterior:
                pago.monto = monto_nuevo
                pago.save(update_fields=["monto"])

    return operacion


def obtener_operaciones_listado():
    """Queryset base del listado global de operaciones de compra/venta.

    Solo trae las operaciones activas (las canceladas quedan fuera), de la mas
    reciente a la mas vieja, con los totales ya anotados (con_totales) y las
    relaciones que lee la tabla precargadas, para no disparar una query por fila
    al iterar el listado.
    """
    return (
        Operacion.objects.filter(activa=True)
        .con_totales()
        .select_related("cliente")
        .prefetch_related("detalleoperacion_set__producto", "detalleoperacion_set__cotizacion")
        .order_by("-fecha", "-id")
    )
