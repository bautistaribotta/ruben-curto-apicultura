import re
from datetime import datetime, time
import requests
from django.utils import timezone
from decimal import Decimal, InvalidOperation

from django.shortcuts import get_object_or_404
from django.http import Http404
from django.db import transaction
from django.db.models import Sum, F, Value, Count, Q, Subquery, OuterRef
from django.db.models.functions import Coalesce
from django.core.cache import cache
from .models import (Producto, Cliente, Operacion, DetalleOperacion, Pago, Cotizaciones, Chofer, Vehiculo, Viaje,
                     DetalleViaje, Gasto, ViajeCereal, DetalleViajeCereal, GastoViajeCereal,
                     ViajeReparto, DetalleViajeReparto, GastoViajeReparto)


def _aplicar_estado_pago(viaje, pagado):
    """Sincroniza el estado de cobro de un viaje con su fecha de pago.

    Lo usan por igual los viajes de reparto y los de cereal: ambos tienen los
    campos 'pagado' y 'fecha_pago'. Reglas:
    - pasa de impago a pagado -> sella el momento del cobro
    - ya estaba pagado        -> conserva la fecha original, no la refresca
    - vuelve a impago         -> limpia la fecha, para no mostrar una que ya no aplica

    No guarda: deja el objeto listo y que lo persista quien lo llamo.
    """
    pagado = bool(pagado)
    if pagado and not viaje.pagado:
        viaje.fecha_pago = timezone.now()
    elif not pagado:
        viaje.fecha_pago = None
    viaje.pagado = pagado
    return viaje


# --- Validadores REGEX ---
REGEX_TEXTO_BASICO = re.compile(r"^[a-zA-ZÁÉÍÓÚáéíóúñÑ\s]+$")
REGEX_TEXTO_NUMEROS = re.compile(r"^[a-zA-ZÁÉÍÓÚáéíóúñÑ\s\d]+$")
REGEX_PATENTE = re.compile(r"^[A-Z0-9]{6,7}$")
# El codigo de trazabilidad de granos (CTG) admite hasta 15 digitos, solo numeros
REGEX_CTG = re.compile(r"^[0-9]{1,15}$")


def nuevo_producto(nombre, categoria=None, precio=None, cantidad=None):
    nuevo_producto = Producto.objects.create(
        nombre=nombre, categoria=categoria, precio=precio, cantidad=cantidad
    )
    return nuevo_producto


def obtener_datos_producto(id_producto):
    try:
        # Busco el producto asegurándome de que esté activo en el inventario
        producto = Producto.objects.get(id=id_producto, activo=True)

        # Estructuro la información en un diccionario limpio para que la API JSON lo consuma fácilmente
        return {
            "id": producto.id,
            "nombre": producto.nombre,
            "categoria": producto.categoria,
            "precio": str(
                producto.precio
            ),  # Convierto el Decimal a string para evitar errores de serialización JSON
            "cantidad": str(producto.cantidad),
        }
    except Producto.DoesNotExist:
        # Si el producto no existe o está inactivo, devuelvo None
        return None


def modificar_stock(id_producto, cantidad, permitir_inactivos=False):
    """
    Modifica el stock de un producto sumando o restando según el valor de 'cantidad'.
    - cantidad > 0 → suma stock (ingreso de mercadería, devolución, etc.)
    - cantidad < 0 → resta stock (venta, egreso, etc.)

    Con permitir_inactivos=True también opera sobre productos dados de baja
    (activo=False): lo usan las reversiones de stock al cancelar o editar una
    operación, porque el historial puede referenciar productos ya eliminados.

    Retorna el producto actualizado o lanza ValueError si el stock quedaría negativo.
    """
    filtro_base = {"id": id_producto}
    if not permitir_inactivos:
        filtro_base["activo"] = True

    # Verifico existencia para mantener el comportamiento 404 ante productos
    # inexistentes o inactivos
    if not Producto.objects.filter(**filtro_base).exists():
        raise Http404("Producto no encontrado")

    if cantidad < 0:
        # UPDATE condicional atómico: el chequeo de stock (WHERE cantidad__gte)
        # y el descuento (SET cantidad = cantidad + n) ocurren en UNA sola
        # sentencia SQL. No hay ventana entre verificar y escribir, por lo que
        # se elimina el read-modify-write que permitía lost updates y sobreventa.
        filas = Producto.objects.filter(
            **filtro_base, cantidad__gte=abs(cantidad)
        ).update(cantidad=F("cantidad") + cantidad)

        if filas == 0:
            # 0 filas afectadas significa que no había stock suficiente
            raise ValueError("No se puede quitar más stock del existente.")
    else:
        # Ingreso de stock: incremento atómico sin lectura previa
        Producto.objects.filter(**filtro_base).update(
            cantidad=F("cantidad") + cantidad
        )

    return Producto.objects.get(id=id_producto)


def editar_producto(id_producto, nombre, categoria, precio, activo):
    # El stock NO se modifica al editar: se gestiona solo en el alta y con el modal
    # de agregar/quitar (UPDATE atomico). Asi evito el lost update de pisar 'cantidad'
    # con un valor del form leido al abrir la pantalla, descartando una venta o compra
    # concurrente que haya movido el stock entremedio.
    producto = get_object_or_404(Producto, id=id_producto)

    producto.nombre = nombre
    producto.categoria = categoria
    producto.precio = precio
    producto.activo = activo

    producto.save()
    return producto


def eliminar_producto(id_producto):
    producto = get_object_or_404(Producto, id=id_producto)

    # En lugar de borrarlo de la base de datos, lo marco como inactivo
    # para no perder el historial de ventas en las otras tablas
    producto.activo = False
    producto.save()
    return producto


def nuevo_cliente(nombre, apellido=None, telefono=None, localidad=None, direccion=None, factura_produccion=False, cuit=None):
    nuevo_cliente = Cliente.objects.create(
        nombre=nombre,
        apellido=apellido,
        telefono=telefono,
        localidad=localidad,
        direccion=direccion,
        factura_produccion=factura_produccion,
        cuit=cuit,
    )
    return nuevo_cliente


def obtener_datos_cliente(id_cliente):
    try:
        # Busco al cliente asegurándome de que esté activo para no exponer datos de registros "eliminados"
        cliente = Cliente.objects.get(id=id_cliente, activo=True)

        # Estructuro la información en un diccionario para que sea fácil de consumir,
        # ya sea para una respuesta JSON o para cualquier otra lógica interna del sistema
        return {
            "id": cliente.id,
            "nombre": cliente.nombre,
            "apellido": cliente.apellido,
            "telefono": cliente.telefono,
            "localidad": cliente.localidad,
            "direccion": cliente.direccion,
            "factura": cliente.factura_produccion,
            "cuit": cliente.cuit,
        }
    except Cliente.DoesNotExist:
        return None


def editar_cliente(id_cliente, nombre, apellido, telefono, localidad, direccion, factura_produccion, cuit, activo):
    cliente = get_object_or_404(Cliente, id=id_cliente)

    cliente.nombre = nombre
    cliente.apellido = apellido
    cliente.telefono = telefono
    cliente.localidad = localidad
    cliente.direccion = direccion
    cliente.factura_produccion = factura_produccion
    cliente.cuit = cuit
    cliente.activo = activo

    cliente.save()
    return cliente


def eliminar_cliente(id_cliente):
    cliente = get_object_or_404(Cliente, id=id_cliente)
    cliente.activo = False

    cliente.save()
    return cliente


def filtro_tokens(q, *campos):
    """
    Arma un Q para buscar por varias palabras sobre uno o más campos: cada
    palabra del texto tiene que aparecer (icontains) en alguno de los campos, y
    todas las palabras tienen que estar presentes. Así "cera laminada" encuentra
    "Cera Estampada Laminada" y el orden no importa. Una sola palabra se comporta
    como un icontains común. Sin palabras devuelve un Q() vacío (no filtra nada).
    """
    filtro = Q()
    for palabra in (q or "").split():
        por_palabra = Q()
        for campo in campos:
            por_palabra |= Q(**{f"{campo}__icontains": palabra})
        filtro &= por_palabra
    return filtro


def filtro_nombre_apellido(q, prefijo=""):
    """
    Caso particular de filtro_tokens para nombre + apellido: "carola diaz"
    encuentra a Carola Diaz aunque sean columnas separadas y sin importar el
    orden. 'prefijo' permite reutilizarlo sobre relaciones, por ejemplo
    "cliente__" o "chofer__".
    """
    return filtro_tokens(q, f"{prefijo}nombre", f"{prefijo}apellido")


def buscar_clientes(q, limite=10):
    """
    Busqueda acotada de clientes activos para el autocompletado del select de cliente
    (viajes de cereal). Limito los resultados para no serializar miles de filas en cada
    tecla; devuelvo una lista de dicts {id, texto} lista para el JSON del front.
    """
    q = (q or "").strip()
    if not q:
        return []

    clientes = Cliente.objects.filter(activo=True)
    if q.isdigit():
        clientes = clientes.filter(id=q)
    else:
        clientes = clientes.filter(filtro_nombre_apellido(q))

    clientes = clientes.order_by("nombre", "apellido")[:limite]
    return [
        {"id": c.id, "texto": f"{c.nombre} {c.apellido or ''}".strip()}
        for c in clientes
    ]


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

    cotizacion = get_object_or_404(Cotizaciones, id=item.get("id_cotizacion"))

    if tipo_operacion == "venta":
        # Descuento condicional atomico, mismo patron que modificar_stock: el
        # chequeo de kilos disponibles y la resta ocurren en una sola sentencia,
        # asi dos ventas concurrentes no pueden sobrevender el mismo tambor
        filas = Cotizaciones.objects.filter(
            id=cotizacion.id, cantidad__gte=kilos
        ).update(cantidad=F("cantidad") - kilos)

        if filas == 0:
            raise ValueError(
                f"No hay kilos suficientes de {cotizacion.articulo} a granel."
            )
    else:
        Cotizaciones.objects.filter(id=cotizacion.id).update(
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
        "valor_kilo_miel": "la miel 50mm",
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
                "cotizaciones de ese día (miel 50mm, dólar oficial y cera opérculo)."
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
                Cotizaciones.objects.filter(id=detalle.cotizacion_id).update(
                    cantidad=F("cantidad") + detalle.cantidad
                )
            else:
                # Compra revertida: quito los kilos, con el mismo chequeo
                # condicional atomico para no dejar el stock negativo
                filas = Cotizaciones.objects.filter(
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

    Pagos: si la operación no tiene pagos, el método es editable y "contado"
    genera el pago automático por el nuevo total. Si ya tiene pagos, el método
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
                        "cotizaciones de ese día (miel 50mm, dólar oficial y cera opérculo)."
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
            # Sin pagos: el método es editable y contado salda la operación
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


def _iniciales(nombre, apellido=None):
    # Siempre dos letras: inicial de nombre + inicial de apellido.
    # Sin apellido, uso las dos primeras letras del nombre.
    nombre = (nombre or "").strip()
    apellido = (apellido or "").strip()
    if apellido:
        return (nombre[:1] + apellido[:1]).upper()
    return nombre[:2].upper()


def obtener_listado_deudores(q="", tipo="", desde=None, hasta=None):
    # Si la API del dolar falla, la equivalencia queda en None (la fila muestra "-"
    # y no aporta al total), igual que miel y cera. Antes caia a 1 y la columna
    # "hoy" terminaba mostrando los pesos como si fueran dolares.
    dolar_actual_data = get_cotizacion_dolar_oficial()
    venta_dolar = dolar_actual_data.get("venta")
    try:
        dolar_actual = Decimal(str(venta_dolar)) if venta_dolar else None
    except InvalidOperation:
        dolar_actual = None

    miel_actual_data = get_cotizacion_miel_50mm()
    try:
        miel_actual = Decimal(str(miel_actual_data)) if miel_actual_data else None
    except ValueError:
        miel_actual = None

    # La equivalencia en cera usa siempre la cotizacion actual de "Cera Operculo"
    cera_actual_data = get_cotizacion_cera_operculo()
    try:
        cera_actual = Decimal(str(cera_actual_data)) if cera_actual_data else None
    except ValueError:
        cera_actual = None

    # Filtramos operaciones activas donde el total pagado es menor al monto total.
    # Como 'monto_total' ahora es una @property (no un campo de BD), lo recreo en la query.
    # Uso subqueries (no JOINs directos) para sumar detalles y pagos por separado y así
    # evitar el "fan-out" que multiplicaría los montos al combinar dos agregaciones.
    from django.db.models import DecimalField, OuterRef, Subquery
    monto_detalles = (
        DetalleOperacion.objects.filter(operacion=OuterRef('pk'))
        .values('operacion')
        .annotate(total=Sum(F('cantidad') * F('precio_unitario')))
        .values('total')
    )
    monto_pagos = (
        Pago.objects.filter(operacion=OuterRef('pk'))
        .values('operacion')
        .annotate(total=Sum('monto'))
        .values('total')
    )
    operaciones_adeudadas = (
        Operacion.objects.filter(activa=True)
        .annotate(
            monto_calculado=Coalesce(Subquery(monto_detalles, output_field=DecimalField()), Value(0), output_field=DecimalField()),
            pagado=Coalesce(Subquery(monto_pagos, output_field=DecimalField()), Value(0), output_field=DecimalField())
        )
        .filter(monto_calculado__gt=F('pagado'))
        .select_related('cliente')
        .order_by('-fecha')
    )

    # Filtro por tipo de deuda: "cobros" son ventas impagas (el cliente nos debe) y
    # "pagos" son compras impagas (nosotros le debemos al proveedor).
    if tipo == "cobros":
        operaciones_adeudadas = operaciones_adeudadas.filter(tipo_operacion="venta")
    elif tipo == "pagos":
        operaciones_adeudadas = operaciones_adeudadas.filter(tipo_operacion="compra")

    # Filtro por fecha de la operacion. 'fecha' es un DateTimeField, asi que en vez
    # del lookup __date (que en MySQL usa CONVERT_TZ para pasar de UTC a la zona
    # local antes de extraer la fecha, y devuelve NULL -> descarta todo- si el
    # servidor no tiene cargadas las tablas de zona horaria) comparo contra los
    # limites del dia como datetimes aware: el inicio del dia 'desde' y el fin del
    # dia 'hasta', en la zona horaria local. El caso "un solo dia" llega como
    # desde == hasta, asi que no necesita rama aparte.
    if desde:
        inicio = timezone.make_aware(datetime.combine(desde, time.min))
        operaciones_adeudadas = operaciones_adeudadas.filter(fecha__gte=inicio)
    if hasta:
        fin = timezone.make_aware(datetime.combine(hasta, time.max))
        operaciones_adeudadas = operaciones_adeudadas.filter(fecha__lte=fin)

    if q:
        if q.isdigit():
            operaciones_adeudadas = operaciones_adeudadas.filter(id__icontains=q)
        else:
            operaciones_adeudadas = operaciones_adeudadas.filter(
                filtro_nombre_apellido(q, "cliente__")
            )

    hoy = timezone.localdate()

    lista_deudores = []
    for operacion in operaciones_adeudadas:
        # La deuda es igual al monto total - los pagos registrados en esa operacion
        deuda_pesos = operacion.monto_calculado - operacion.pagado

        # Antigüedad de la deuda en días (la fecha puede ser date o datetime)
        fecha_op = operacion.fecha
        if isinstance(fecha_op, datetime):
            fecha_op = fecha_op.date()
        dias = (hoy - fecha_op).days

        # Cálculos del dólar
        valor_dolar_historico = operacion.valor_dolar if operacion.valor_dolar else None

        # Usamos división porque el total está en pesos (Pesos / Valor Dólar = Dólares)
        deuda_dolar_historico = (deuda_pesos / valor_dolar_historico) if valor_dolar_historico else None
        deuda_dolar_actual = (deuda_pesos / dolar_actual) if dolar_actual else None

        # Cálculos de la Miel
        valor_miel_historico = operacion.valor_kilo_miel if operacion.valor_kilo_miel else None

        kg_miel_historico = (deuda_pesos / valor_miel_historico) if valor_miel_historico else None
        kg_miel_actual = (deuda_pesos / miel_actual) if miel_actual else None

        # Cálculos de la cera: misma metodologia que la miel, equivalencia a la
        # cotizacion de hoy y a la guardada al crear la operacion (origen)
        valor_cera_historico = operacion.valor_kilo_cera if operacion.valor_kilo_cera else None

        kg_cera_historico = (deuda_pesos / valor_cera_historico) if valor_cera_historico else None
        kg_cera_actual = (deuda_pesos / cera_actual) if cera_actual else None

        lista_deudores.append({
            "id": operacion.id,
            # Tipo de operacion para diferenciar en la tabla: una venta impaga es una
            # deuda "a cobrar" (el cliente nos debe) y una compra impaga es "a pagar"
            # (nosotros le debemos al proveedor).
            "tipo_operacion": operacion.tipo_operacion,
            "cliente": f"{operacion.cliente.nombre} {operacion.cliente.apellido or ''}".strip(),
            "iniciales": _iniciales(operacion.cliente.nombre, operacion.cliente.apellido),
            "fecha": operacion.fecha,
            "dias": dias,
            "deuda_pesos": deuda_pesos,
            "deuda_dolar_historico": round(deuda_dolar_historico, 2) if deuda_dolar_historico else None,
            "deuda_dolar_actual": round(deuda_dolar_actual, 2) if deuda_dolar_actual else None,
            "kg_miel_historico": round(kg_miel_historico, 2) if kg_miel_historico else None,
            "kg_miel_actual": round(kg_miel_actual, 2) if kg_miel_actual else None,
            "kg_cera_historico": round(kg_cera_historico, 2) if kg_cera_historico else None,
            "kg_cera_actual": round(kg_cera_actual, 2) if kg_cera_actual else None
        })

    return lista_deudores


def get_cotizacion_dolar_oficial():
    cotizacion = cache.get("cotizacion_oficial")
    if cotizacion:
        return cotizacion

    url_dolar_oficial = "https://dolarapi.com/v1/dolares/oficial"

    # cache.add() es atómico (set-if-not-exists): solo un worker gana el lock y
    # consulta la API externa. El resto evita el cache stampede (varios workers
    # golpeando la API a la vez cuando expira la clave).
    if not cache.add("cotizacion_oficial_lock", "1", 10):
        # No gané el lock: devuelvo lo que haya en cache o un fallback neutro
        return cache.get("cotizacion_oficial") or {"compra": None, "venta": None}

    try:
        # timeout para no bloquear el worker si la API externa cuelga
        respuesta = requests.get(url_dolar_oficial, verify=True, timeout=5)
        respuesta.raise_for_status()
        datos = respuesta.json()
        resultado = {"compra": datos.get("compra"), "venta": datos.get("venta")}
        cache.set("cotizacion_oficial", resultado, 3600)  # Cache por 1 hora
        return resultado
    except requests.RequestException:
        return {"compra": None, "venta": None}
    finally:
        cache.delete("cotizacion_oficial_lock")


def get_cotizaciones():
    """
    Obtiene todas las cotizaciones guardadas en la base de datos.
    Retorna un diccionario con el formato {articulo_sanitizado: {"monto": x, "cantidad": y}}
    donde los caracteres especiales se reemplazan para facilitar su uso en templates.
    La cantidad son los kilos disponibles a granel de ese articulo.
    """
    articulos_esperados = ["Miel 34mm", "Miel 50mm", "Miel +50mm", "Cera Operculo", "Cera Recupero"]
    cotizaciones_db = {c.articulo: c for c in Cotizaciones.objects.all()}

    resultado = {}
    for art in articulos_esperados:
        # Sanitizar la clave para que sea un identificador válido en Django Templates
        clave = art.replace(" ", "_").replace("+", "plus")
        cotizacion = cotizaciones_db.get(art)
        resultado[clave] = {
            "monto": cotizacion.monto if cotizacion else 0,
            "cantidad": cotizacion.cantidad if cotizacion else 0,
        }

    return resultado


def get_articulos_granel():
    """
    Devuelve los articulos de cotizaciones en el orden semantico del tablero
    (mieles por calibre y despues ceras), para el panel "A granel" de las
    pantallas de venta y compra. Los articulos sin fila en la BD se omiten.
    """
    orden = ["Miel 34mm", "Miel 50mm", "Miel +50mm", "Cera Operculo", "Cera Recupero"]
    articulos = {c.articulo: c for c in Cotizaciones.objects.all()}
    return [articulos[art] for art in orden if art in articulos]


def get_total_kilos_granel():
    """
    Suma los kilos a granel por familia de articulo para mostrar el total
    de cada grupo (Miel / Cera) en la cabecera del tablero de inicio.
    """
    totales = {}
    for grupo in ("Miel", "Cera"):
        resultado = Cotizaciones.objects.filter(articulo__startswith=grupo).aggregate(
            total=Sum("cantidad")
        )["total"]
        totales[grupo.lower()] = resultado if resultado is not None else 0
    return totales


def actualizar_cotizacion(articulo, monto):
    """
    Actualiza o crea una cotización en la base de datos.
    """
    cotizacion, created = Cotizaciones.objects.update_or_create(
        articulo=articulo,
        defaults={"monto": monto}
    )
    return cotizacion


def get_cotizacion_miel_50mm():
    """
    Obtiene la cotización de la miel. Se toma 'Miel 50mm' como referencia por defecto.
    """
    try:
        miel = Cotizaciones.objects.get(articulo="Miel 50mm")
        return miel.monto
    except Cotizaciones.DoesNotExist:
        return 1.00


def get_cotizacion_cera_operculo():
    """
    Obtiene la cotización de la cera. Se toma 'Cera Operculo' como referencia.
    Devuelve None si no existe para que quien la use muestre un guion en vez
    de calcular una equivalencia sin sentido.
    """
    try:
        cera = Cotizaciones.objects.get(articulo="Cera Operculo")
        return cera.monto
    except Cotizaciones.DoesNotExist:
        return None


def crear_chofer(nombre, apellido):
    # Aplico limpieza de espacios
    nombre = nombre.strip()
    apellido = apellido.strip()

    # Valido la longitud y formato del nombre
    if not (3 <= len(nombre) <= 25) or not REGEX_TEXTO_BASICO.match(nombre):
        raise ValueError("El nombre debe tener entre 3 y 25 letras, sin números ni símbolos.")

    # Valido la longitud y formato del apellido
    if not (3 <= len(apellido) <= 25) or not REGEX_TEXTO_BASICO.match(apellido):
        raise ValueError("El apellido debe tener entre 3 y 25 letras, sin números ni símbolos.")

    nuevo_chofer = Chofer.objects.create(
        nombre=nombre,
        apellido=apellido
    )
    return nuevo_chofer


def editar_chofer(id_chofer, nombre, apellido, activo):
    chofer = get_object_or_404(Chofer, id=id_chofer)

    # Aplico limpieza de espacios
    nombre = nombre.strip()
    apellido = apellido.strip()

    # Valido la longitud y formato del nombre
    if not (3 <= len(nombre) <= 25) or not REGEX_TEXTO_BASICO.match(nombre):
        raise ValueError("El nombre debe tener entre 3 y 25 letras, sin números ni símbolos.")

    # Valido la longitud y formato del apellido
    if not (3 <= len(apellido) <= 25) or not REGEX_TEXTO_BASICO.match(apellido):
        raise ValueError("El apellido debe tener entre 3 y 25 letras, sin números ni símbolos.")

    chofer.nombre = nombre
    chofer.apellido = apellido
    chofer.activo = activo

    chofer.save()
    return chofer


def eliminar_chofer(id_chofer):
    chofer = get_object_or_404(Chofer, id=id_chofer)
    chofer.activo = False
    chofer.save()
    return chofer


def crear_vehiculo(nombre, patente):
    # Aplico limpieza de espacios y fuerzo la patente a mayúsculas
    nombre = nombre.strip()
    patente = patente.strip().upper()

    # Valido la longitud y formato del nombre del vehículo
    if not (3 <= len(nombre) <= 25) or not REGEX_TEXTO_NUMEROS.match(nombre):
        raise ValueError("El nombre del vehículo debe tener entre 3 y 25 caracteres (solo letras y números).")

    # Valido la longitud y formato de la patente
    if not patente or not REGEX_PATENTE.match(patente):
        raise ValueError("La patente debe tener 6 o 7 caracteres alfanuméricos sin espacios.")

    nuevo_vehiculo = Vehiculo.objects.create(
        nombre=nombre,
        patente=patente
    )
    return nuevo_vehiculo


def editar_vehiculo(id_vehiculo, nombre, patente, activo):
    vehiculo = get_object_or_404(Vehiculo, id=id_vehiculo)

    # Aplico limpieza de espacios y fuerzo la patente a mayúsculas
    nombre = nombre.strip()
    patente = patente.strip().upper()

    # Valido la longitud y formato del nombre del vehículo
    if not (3 <= len(nombre) <= 25) or not REGEX_TEXTO_NUMEROS.match(nombre):
        raise ValueError("El nombre del vehículo debe tener entre 3 y 25 caracteres (solo letras y números).")

    # Valido la longitud y formato de la patente
    if not patente or not REGEX_PATENTE.match(patente):
        raise ValueError("La patente debe tener 6 o 7 caracteres alfanuméricos sin espacios.")

    vehiculo.nombre = nombre
    vehiculo.patente = patente
    vehiculo.activo = activo

    vehiculo.save()
    return vehiculo


def eliminar_vehiculo(id_vehiculo):
    vehiculo = get_object_or_404(Vehiculo, id=id_vehiculo)
    vehiculo.activo = False
    vehiculo.save()
    return vehiculo


def _validar_viaje(id_chofer, id_vehiculo, destinos, inicio_caja, fecha_inicio, fecha_vuelta):
    """
    Centraliza las validaciones de un viaje comun (crear y editar comparten las
    mismas reglas). Devuelve una tupla con los valores ya limpios y convertidos
    (caja_val, destinos_limpios), o lanza ValueError ante el primer dato invalido.
    """
    # 1. El chofer debe existir en la base de datos
    if not Chofer.objects.filter(id=id_chofer).exists():
        raise ValueError("El chofer seleccionado no existe en el sistema.")

    # 2. El vehiculo debe existir en la base de datos
    if not Vehiculo.objects.filter(id=id_vehiculo).exists():
        raise ValueError("El vehículo seleccionado no existe en el sistema.")

    # 3. Destinos: al menos uno, cada uno alfanumerico de 3 a 30 caracteres
    if not destinos:
        raise ValueError("Debe ingresar al menos un destino.")

    destinos_limpios = []
    for d in destinos:
        d_limpio = d.strip()
        if not (3 <= len(d_limpio) <= 30) or not REGEX_TEXTO_NUMEROS.match(d_limpio):
            raise ValueError(f"El destino '{d}' es inválido (debe tener entre 3 y 30 caracteres alfanuméricos).")
        destinos_limpios.append(d_limpio)

    # 4. Inicio de caja: entero no negativo dentro del limite de la BD
    try:
        caja_val = int(inicio_caja)
        if caja_val < 0 or caja_val > 2147483647:
            raise ValueError()
    except (ValueError, TypeError):
        raise ValueError("El monto de inicio de caja debe ser un número entero positivo y no superar el límite permitido de la BD.")

    # 5. Fechas: inicio obligatoria, vuelta opcional, ambas con formato YYYY-MM-DD
    try:
        datetime.strptime(fecha_inicio, "%Y-%m-%d")
        if fecha_vuelta:
            datetime.strptime(fecha_vuelta, "%Y-%m-%d")
    except (ValueError, TypeError):
        raise ValueError("Las fechas deben tener el formato válido YYYY-MM-DD.")

    return caja_val, destinos_limpios


def crear_viaje(id_chofer, id_vehiculo, destinos, inicio_caja, fecha_inicio, fecha_vuelta=None):
    """
    Crea un viaje (maestro) y sus destinos asociados (detalle) usando una transacción atómica.
    'destinos' debe ser una lista de strings. Ejemplo: ["Buenos Aires", "Rosario"].
    """
    caja_val, destinos_limpios = _validar_viaje(
        id_chofer, id_vehiculo, destinos, inicio_caja, fecha_inicio, fecha_vuelta
    )

    with transaction.atomic():
        # Creamos el viaje (Tabla Maestra)
        nuevo_viaje = Viaje.objects.create(
            chofer_id=id_chofer,
            vehiculo_id=id_vehiculo,
            inicio_caja=caja_val,
            fecha_inicio=fecha_inicio,
            fecha_vuelta=fecha_vuelta
        )

        # Iteramos sobre la lista de destinos limpios para crear el Detalle
        for destino_nombre in destinos_limpios:
            DetalleViaje.objects.create(
                viaje=nuevo_viaje,
                destino=destino_nombre
            )

    return nuevo_viaje


def obtener_choferes_activos():
    # Anoto _num_viajes (viajes activos) para que la property total_viajes no
    # dispare una query por cada chofer en el listado de flota. Sumo los tres
    # tipos de viaje. Uso distinct=True en cada Count porque los tres LEFT JOIN
    # generan fan-out y sin el distinct los conteos se multiplicarian entre si.
    return (
        Chofer.objects.filter(activo=True)
        .annotate(_num_viajes=(
            Count("viaje", filter=Q(viaje__activo=True), distinct=True)
            + Count("viajereparto", filter=Q(viajereparto__activo=True), distinct=True)
            + Count("viajecereal", filter=Q(viajecereal__activo=True), distinct=True)
        ))
        .order_by('nombre')
    )


def obtener_vehiculos_activos():
    return (
        Vehiculo.objects.filter(activo=True)
        .annotate(_num_viajes=(
            Count("viaje", filter=Q(viaje__activo=True), distinct=True)
            + Count("viajereparto", filter=Q(viajereparto__activo=True), distinct=True)
            + Count("viajecereal", filter=Q(viajecereal__activo=True), distinct=True)
        ))
        .order_by('nombre')
    )


def incluir_asignado(opciones, asignado):
    """
    Devuelve las opciones de un <select> incluyendo el registro actualmente asignado,
    aunque este inactivo (y por lo tanto ausente del queryset de activos). Asi, al editar
    un viaje cuyo chofer, vehiculo o cliente fue dado de baja, su valor sigue
    preseleccionado en vez de obligar a elegir otro.
    """
    opciones = list(opciones)
    if asignado and asignado not in opciones:
        opciones.append(asignado)
    return opciones


def obtener_viajes():
    return Viaje.objects.filter(activo=True).select_related('chofer', 'vehiculo').prefetch_related('destinos').order_by('-fecha_inicio')


def obtener_datos_viaje(id_viaje):
    # Trae un viaje comun activo con sus relaciones listas para la vista de informacion.
    # Mismo patron que obtener_datos_viaje_cereal / _reparto: la vista no toca el ORM directo.
    return get_object_or_404(
        Viaje.objects.select_related("chofer", "vehiculo").prefetch_related("destinos", "detalle_gastos"),
        id=id_viaje,
        activo=True,
    )


def editar_viaje(id_viaje, id_chofer, id_vehiculo, destinos, inicio_caja, fecha_inicio, fecha_vuelta):
    caja_val, destinos_limpios = _validar_viaje(
        id_chofer, id_vehiculo, destinos, inicio_caja, fecha_inicio, fecha_vuelta
    )

    with transaction.atomic():
        viaje = get_object_or_404(Viaje, id=id_viaje)

        viaje.chofer_id = id_chofer
        viaje.vehiculo_id = id_vehiculo
        viaje.inicio_caja = caja_val
        viaje.fecha_inicio = fecha_inicio
        viaje.fecha_vuelta = fecha_vuelta if fecha_vuelta else None
        viaje.save()

        # Eliminar destinos anteriores y crear nuevos
        viaje.destinos.all().delete()
        for destino_nombre in destinos_limpios:
            DetalleViaje.objects.create(
                viaje=viaje,
                destino=destino_nombre
            )

    return viaje


def eliminar_viaje(id_viaje):
    viaje = get_object_or_404(Viaje, id=id_viaje)
    viaje.activo = False
    viaje.save()
    return viaje


def crear_gasto(id_viaje, tipo_gasto, monto):
    viaje = get_object_or_404(Viaje, id=id_viaje)

    # Validamos que el tipo de gasto sea correcto
    tipos_validos = dict(Gasto.TIPO_GASTOS).keys()
    if tipo_gasto not in tipos_validos:
        raise ValueError(f"El tipo de gasto '{tipo_gasto}' no es válido.")

    # Validamos el monto
    try:
        monto_val = int(monto)
        if monto_val <= 0:
            raise ValueError()
    except (ValueError, TypeError):
        raise ValueError("El monto debe ser un número entero positivo mayor a 0.")

    nuevo_gasto = Gasto.objects.create(
        viaje=viaje,
        gasto=tipo_gasto,
        monto=monto_val
    )
    return nuevo_gasto


# --- Viajes de cereales ---

def _validar_viaje_cereal(id_cliente, id_chofer, id_vehiculo, tipo_cereal, codigo_trazabilidad,
                          toneladas, precio_tonelada, porcentaje_chofer, fecha_viaje_cereal, destinos):
    """
    Centraliza las validaciones de un viaje de cereal (crear y editar comparten las
    mismas reglas). Devuelve una tupla con los valores ya limpios y convertidos,
    listos para persistir, o lanza ValueError ante el primer dato invalido.
    """
    # 1. El cliente es opcional (el modelo permite null). Si se informa, debe existir y estar activo.
    if id_cliente and not Cliente.objects.filter(id=id_cliente, activo=True).exists():
        raise ValueError("El cliente seleccionado no existe en el sistema.")

    # 2. El chofer debe existir en la base de datos
    if not Chofer.objects.filter(id=id_chofer).exists():
        raise ValueError("El chofer seleccionado no existe en el sistema.")

    # 3. El vehiculo debe existir en la base de datos
    if not Vehiculo.objects.filter(id=id_vehiculo).exists():
        raise ValueError("El vehiculo seleccionado no existe en el sistema.")

    # 4. El tipo de cereal es obligatorio y debe ser una de las opciones validas
    tipos_validos = dict(ViajeCereal.cereales).keys()
    if tipo_cereal not in tipos_validos:
        raise ValueError("Debe seleccionar un tipo de cereal valido.")

    # 5. Codigo de trazabilidad (CTG): obligatorio, solo numeros, hasta 15 digitos
    #    (conservando ceros a la izquierda al ser texto)
    codigo_limpio = (codigo_trazabilidad or "").strip()
    if not REGEX_CTG.match(codigo_limpio):
        raise ValueError("El codigo de trazabilidad debe ser numerico y tener hasta 15 digitos.")

    # 6. Toneladas: numero positivo con hasta dos decimales, dentro del limite de la BD.
    #    Acepto coma o punto como separador decimal (la coma es lo habitual en es-AR).
    try:
        toneladas_val = Decimal(str(toneladas).strip().replace(",", "."))
    except (InvalidOperation, TypeError, AttributeError):
        raise ValueError("Las toneladas deben ser un numero valido (hasta 2 decimales).")

    if toneladas_val <= 0:
        raise ValueError("Las toneladas deben ser un numero positivo.")

    # No mas de dos decimales: si al redondear a 2 el valor cambia, tenia mas precision
    toneladas_cuant = toneladas_val.quantize(Decimal("0.01"))
    if toneladas_cuant != toneladas_val:
        raise ValueError("Las toneladas admiten como maximo 2 decimales.")

    # max_digits=10 con 2 decimales => parte entera de hasta 8 digitos
    if toneladas_cuant >= Decimal("100000000"):
        raise ValueError("El valor de toneladas es demasiado grande.")

    # Normalizo a 2 decimales para que "5,5" se guarde como 5.50
    toneladas_val = toneladas_cuant

    # 7. Precio por tonelada: entero positivo dentro del limite de la BD
    try:
        precio_val = int(precio_tonelada)
        if precio_val <= 0 or precio_val > 2147483647:
            raise ValueError()
    except (ValueError, TypeError):
        raise ValueError("El precio por tonelada debe ser un numero entero positivo.")

    # 8. Porcentaje del chofer: opcional. Si no se carga queda en 0; si viene, debe ser 1 a 100
    if porcentaje_chofer in (None, ""):
        porcentaje_val = 0
    else:
        try:
            porcentaje_val = int(porcentaje_chofer)
            if porcentaje_val < 1 or porcentaje_val > 100:
                raise ValueError()
        except (ValueError, TypeError):
            raise ValueError("El porcentaje del chofer debe ser un numero entero entre 1 y 100.")

    # 9. Fecha del viaje: obligatoria y con formato YYYY-MM-DD
    try:
        datetime.strptime(fecha_viaje_cereal, "%Y-%m-%d")
    except (ValueError, TypeError):
        raise ValueError("La fecha del viaje debe tener el formato valido YYYY-MM-DD.")

    # 10. Destinos: al menos uno, cada uno alfanumerico de 3 a 30 caracteres
    if not destinos:
        raise ValueError("Debe ingresar al menos un destino.")

    destinos_limpios = []
    for d in destinos:
        d_limpio = d.strip()
        if not (3 <= len(d_limpio) <= 30) or not REGEX_TEXTO_NUMEROS.match(d_limpio):
            raise ValueError(f"El destino '{d}' es invalido (debe tener entre 3 y 30 caracteres alfanumericos).")
        destinos_limpios.append(d_limpio)

    return codigo_limpio, toneladas_val, precio_val, porcentaje_val, destinos_limpios


def crear_viaje_cereal(id_cliente, id_chofer, id_vehiculo, tipo_cereal, codigo_trazabilidad,
                       toneladas, precio_tonelada, porcentaje_chofer, fecha_viaje_cereal, destinos,
                       pagado=False):
    """
    Crea un viaje de cereal (maestro) y sus destinos asociados (detalle) en una
    transaccion atomica. 'destinos' es una lista de strings.

    'pagado' es el cobro del flete: la empresa no acepta pagos parciales, asi que
    alcanza con el booleano (o esta cobrado o no lo esta). Por defecto nace impago.
    """
    codigo, toneladas_val, precio_val, porcentaje_val, destinos_limpios = _validar_viaje_cereal(
        id_cliente, id_chofer, id_vehiculo, tipo_cereal, codigo_trazabilidad,
        toneladas, precio_tonelada, porcentaje_chofer, fecha_viaje_cereal, destinos
    )

    with transaction.atomic():
        nuevo_viaje_cereal = ViajeCereal.objects.create(
            cliente_id=id_cliente or None,
            chofer_id=id_chofer,
            vehiculo_id=id_vehiculo,
            tipo_cereal=tipo_cereal,
            codigo_trazabilidad_granos=codigo,
            toneladas=toneladas_val,
            precio_tonelada=precio_val,
            porcentaje_chofer=porcentaje_val,
            fecha_viaje_cereal=fecha_viaje_cereal,
            pagado=bool(pagado),
            # Si nace cobrado, el momento del cobro es el del alta
            fecha_pago=timezone.now() if pagado else None,
        )

        for destino_nombre in destinos_limpios:
            DetalleViajeCereal.objects.create(
                viaje_cereal=nuevo_viaje_cereal,
                destino=destino_nombre
            )

    return nuevo_viaje_cereal


def obtener_viajes_cereales():
    # Solo los viajes activos (borrado logico), con relaciones precargadas para evitar el N+1
    return (
        ViajeCereal.objects.filter(activo=True)
        .select_related("cliente", "chofer", "vehiculo")
        .prefetch_related("destinos")
        .order_by("-fecha_viaje_cereal")
    )


def obtener_resumen_cereal(viajes):
    """Totales para las tarjetas de resumen de la vista de viajes de cereal.

    'viajes' es el listado ya filtrado (texto, fecha), de modo que las tarjetas
    reflejan los mismos filtros que la tabla. Se calcula sobre todo ese conjunto,
    no solo la pagina visible.

    Total   = suma de (toneladas * precio_tonelada) de cada viaje (total_bruto).
    Gastos  = suma de los gastos de cada viaje MAS el pago al chofer de cada uno.
    Ganancia = (total + 21%) - gastos.

    El pago al chofer no es un aggregate plano: depende del subtotal por viaje
    (bruto - gastos de ese viaje) con un tope en 0 (si los gastos superan al
    bruto el chofer no aporta plata). Por eso anoto los gastos de cada viaje con
    UNA sola subconsulta correlacionada y recorro el resultado en Python: es una
    unica query y evita el N+1 (no dispara un aggregate por viaje como haria la
    property total_gastos del modelo).

    Re-scopeo por pk: 'viajes' puede venir con un JOIN a los destinos y
    .distinct() (filtro por texto), que duplicaria filas al recorrerlas. Filtrar
    por pk__in parte de una base limpia con una fila por viaje.
    """
    gastos_por_viaje = Subquery(
        GastoViajeCereal.objects
        .filter(viaje_cereal=OuterRef("pk"))
        .values("viaje_cereal")
        .annotate(total=Sum("monto"))
        .values("total")
    )
    viajes = (
        ViajeCereal.objects.filter(pk__in=viajes.values("pk"))
        .annotate(
            _bruto=F("toneladas") * F("precio_tonelada"),
            _gastos=Coalesce(gastos_por_viaje, Value(0)),
        )
        .values("_bruto", "_gastos", "porcentaje_chofer")
    )

    total = Decimal(0)
    gastos = Decimal(0)
    for v in viajes:
        bruto = v["_bruto"] or Decimal(0)
        gastos_viaje = v["_gastos"] or 0
        subtotal = bruto - gastos_viaje
        base = subtotal if subtotal > 0 else Decimal(0)
        pago_chofer = base * v["porcentaje_chofer"] / 100
        total += bruto
        gastos += gastos_viaje + pago_chofer

    total = int(round(total))
    gastos = int(round(gastos))
    total_mas_iva = int(round(total * Decimal("1.21")))
    ganancia = total_mas_iva - gastos

    return {
        "total": total,
        "total_mas_iva": total_mas_iva,
        "gastos": gastos,
        "ganancia": ganancia,
    }


def obtener_datos_viaje_cereal(id_viaje_cereal):
    # Trae un viaje de cereal activo con sus relaciones listas para la vista de informacion.
    # Precargo tambien los gastos para que la tarjeta de calculo no dispare queries extra.
    return get_object_or_404(
        ViajeCereal.objects.select_related("cliente", "chofer", "vehiculo")
        .prefetch_related("destinos", "detalle_gastos"),
        id=id_viaje_cereal,
        activo=True,
    )


def editar_viaje_cereal(id_viaje_cereal, id_cliente, id_chofer, id_vehiculo, tipo_cereal, codigo_trazabilidad,
                        toneladas, precio_tonelada, porcentaje_chofer, fecha_viaje_cereal, destinos,
                        pagado=None):
    # 'pagado' llega en None cuando quien edita no puede tocar el cobro (no staff):
    # en ese caso el estado de pago queda como estaba, no se pisa con un False.
    codigo, toneladas_val, precio_val, porcentaje_val, destinos_limpios = _validar_viaje_cereal(
        id_cliente, id_chofer, id_vehiculo, tipo_cereal, codigo_trazabilidad,
        toneladas, precio_tonelada, porcentaje_chofer, fecha_viaje_cereal, destinos
    )

    with transaction.atomic():
        viaje_cereal = get_object_or_404(ViajeCereal, id=id_viaje_cereal)

        viaje_cereal.cliente_id = id_cliente or None
        viaje_cereal.chofer_id = id_chofer
        viaje_cereal.vehiculo_id = id_vehiculo
        viaje_cereal.tipo_cereal = tipo_cereal
        viaje_cereal.codigo_trazabilidad_granos = codigo
        viaje_cereal.toneladas = toneladas_val
        viaje_cereal.precio_tonelada = precio_val
        viaje_cereal.porcentaje_chofer = porcentaje_val
        viaje_cereal.fecha_viaje_cereal = fecha_viaje_cereal
        if pagado is not None:
            _aplicar_estado_pago(viaje_cereal, pagado)
        viaje_cereal.save()

        # Reemplazo los destinos (mismo patron que editar_viaje)
        viaje_cereal.destinos.all().delete()
        for destino_nombre in destinos_limpios:
            DetalleViajeCereal.objects.create(
                viaje_cereal=viaje_cereal,
                destino=destino_nombre
            )

    return viaje_cereal


def marcar_pago_viaje_cereal(id_viaje_cereal, pagado):
    """Marca (o desmarca) el cobro de un viaje de cereal.

    Es el servicio detras de la casilla de la tabla: solo toca 'pagado', por eso
    guardo con update_fields y no arrastro el resto de la fila.
    """
    viaje_cereal = get_object_or_404(ViajeCereal, id=id_viaje_cereal, activo=True)
    _aplicar_estado_pago(viaje_cereal, pagado)
    viaje_cereal.save(update_fields=["pagado", "fecha_pago"])
    return viaje_cereal


def eliminar_viaje_cereal(id_viaje_cereal):
    viaje_cereal = get_object_or_404(ViajeCereal, id=id_viaje_cereal)
    # Borrado logico: lo marco inactivo para no perder el historial
    viaje_cereal.activo = False
    viaje_cereal.save()
    return viaje_cereal


def crear_gasto_viaje_cereal(id_viaje_cereal, tipo_gasto, monto):
    # Mismo patron que crear_gasto (viajes comunes), pero sobre la tabla GastoViajeCereal.
    # Cada gasto cargado recalcula automaticamente el subtotal y el pago del chofer, porque
    # esas propiedades del modelo se derivan de la suma de gastos del viaje.
    viaje_cereal = get_object_or_404(ViajeCereal, id=id_viaje_cereal)

    # Validamos que el tipo de gasto sea correcto
    tipos_validos = dict(GastoViajeCereal._meta.get_field("gasto").choices).keys()
    if tipo_gasto not in tipos_validos:
        raise ValueError(f"El tipo de gasto '{tipo_gasto}' no es válido.")

    # Validamos el monto
    try:
        monto_val = int(monto)
        if monto_val <= 0:
            raise ValueError()
    except (ValueError, TypeError):
        raise ValueError("El monto debe ser un número entero positivo mayor a 0.")

    nuevo_gasto = GastoViajeCereal.objects.create(
        viaje_cereal=viaje_cereal,
        gasto=tipo_gasto,
        monto=monto_val
    )
    return nuevo_gasto


# --- Viajes de reparto (Mercado Libre) ---

def _validar_viaje_reparto(id_chofer, id_vehiculo, gasto_combustible,
                           costo_empleado, valor_viaje, fecha_viaje_reparto, destinos):
    """
    Centraliza las validaciones de un viaje de reparto (crear y editar comparten las
    mismas reglas). Devuelve una tupla con los valores ya limpios y convertidos,
    listos para persistir, o lanza ValueError ante el primer dato invalido.
    """
    # 1. El chofer debe existir en la base de datos
    if not Chofer.objects.filter(id=id_chofer).exists():
        raise ValueError("El chofer seleccionado no existe en el sistema.")

    # 2. El vehiculo debe existir en la base de datos
    if not Vehiculo.objects.filter(id=id_vehiculo).exists():
        raise ValueError("El vehiculo seleccionado no existe en el sistema.")

    # 3. Gasto de combustible: entero positivo dentro del limite de la BD
    try:
        gasto_val = int(gasto_combustible)
        if gasto_val <= 0 or gasto_val > 2147483647:
            raise ValueError()
    except (ValueError, TypeError):
        raise ValueError("El gasto de combustible debe ser un numero entero positivo.")

    # 4. Costo del empleado: entero positivo dentro del limite de la BD
    try:
        costo_val = int(costo_empleado)
        if costo_val <= 0 or costo_val > 2147483647:
            raise ValueError()
    except (ValueError, TypeError):
        raise ValueError("El costo del empleado debe ser un numero entero positivo.")

    # 5. Valor del viaje: entero positivo dentro del limite de la BD
    try:
        valor_val = int(valor_viaje)
        if valor_val <= 0 or valor_val > 2147483647:
            raise ValueError()
    except (ValueError, TypeError):
        raise ValueError("El valor del viaje debe ser un numero entero positivo.")

    # 6. Fecha del reparto: obligatoria y con formato YYYY-MM-DD
    try:
        datetime.strptime(fecha_viaje_reparto, "%Y-%m-%d")
    except (ValueError, TypeError):
        raise ValueError("La fecha del reparto debe tener el formato valido YYYY-MM-DD.")

    # 7. Destinos: al menos uno, cada uno alfanumerico de 3 a 30 caracteres
    if not destinos:
        raise ValueError("Debe ingresar al menos un destino.")

    destinos_limpios = []
    for d in destinos:
        d_limpio = d.strip()
        if not (3 <= len(d_limpio) <= 30) or not REGEX_TEXTO_NUMEROS.match(d_limpio):
            raise ValueError(f"El destino '{d}' es invalido (debe tener entre 3 y 30 caracteres alfanumericos).")
        destinos_limpios.append(d_limpio)

    return gasto_val, costo_val, valor_val, destinos_limpios


def crear_viaje_reparto(id_chofer, id_vehiculo, gasto_combustible, costo_empleado,
                        valor_viaje, fecha_viaje_reparto, destinos, pagado=False):
    """
    Crea un viaje de reparto (maestro) y sus destinos asociados (detalle) en una
    transaccion atomica. 'destinos' es una lista de strings.

    'pagado' es el cobro del reparto: la empresa no acepta pagos parciales, asi que
    alcanza con el booleano (o esta cobrado o no lo esta). Por defecto nace impago.
    """
    gasto_val, costo_val, valor_val, destinos_limpios = _validar_viaje_reparto(
        id_chofer, id_vehiculo, gasto_combustible, costo_empleado,
        valor_viaje, fecha_viaje_reparto, destinos
    )

    with transaction.atomic():
        nuevo_viaje_reparto = ViajeReparto.objects.create(
            chofer_id=id_chofer,
            vehiculo_id=id_vehiculo,
            gasto_combustible_viaje_reparto=gasto_val,
            costo_empleado=costo_val,
            valor_viaje=valor_val,
            fecha_viaje_reparto=fecha_viaje_reparto,
            pagado=bool(pagado),
            # Si nace cobrado, el momento del cobro es el del alta
            fecha_pago=timezone.now() if pagado else None,
        )

        for destino_nombre in destinos_limpios:
            DetalleViajeReparto.objects.create(
                viaje_reparto=nuevo_viaje_reparto,
                destinos_reparto=destino_nombre
            )

    return nuevo_viaje_reparto


def obtener_viajes_reparto():
    # Solo los viajes activos (borrado logico), con relaciones precargadas para evitar el N+1
    return (
        ViajeReparto.objects.filter(activo=True)
        .select_related("chofer", "vehiculo")
        .prefetch_related("destinos")
        .order_by("-fecha_viaje_reparto")
    )


def obtener_resumen_reparto(viajes):
    """Totales para las tarjetas de resumen de la vista de repartos.

    'viajes' es el listado ya filtrado (texto, fecha), de modo que las tarjetas
    reflejan los mismos filtros que la tabla. Se calcula sobre todo ese conjunto,
    no solo la pagina visible.

    Re-scopeo por pk a una base limpia: 'viajes' puede venir con un JOIN a los
    destinos y .distinct() (filtro por texto), que en un aggregate multiplicaria
    las filas y falsearia los totales. Filtrar por pk__in evita ese fanout.

    Uso dos aggregate() separados a proposito: sumar valor_viaje y los gastos
    hijos (detalle_gastos) en la misma query volveria a multiplicar filas por el
    JOIN a la tabla de gastos. Asi son dos queries planas, sin N+1.

    Gastos = combustible + costo del empleado + gastos extra, igual criterio que
    la ganancia neta por viaje (ver ViajeReparto.ganancia y la vista de detalle).
    Ganancia = (total + 21%) - gastos, segun lo pedido para esta tarjeta.
    """
    ids = viajes.values("pk")
    base = ViajeReparto.objects.filter(pk__in=ids)

    cabecera = base.aggregate(
        total=Coalesce(Sum("valor_viaje"), 0),
        combustible=Coalesce(Sum("gasto_combustible_viaje_reparto"), 0),
        empleado=Coalesce(Sum("costo_empleado"), 0),
    )
    gastos_extra = GastoViajeReparto.objects.filter(
        viaje_reparto__in=ids
    ).aggregate(total=Coalesce(Sum("monto"), 0))["total"]

    total = cabecera["total"]
    gastos = cabecera["combustible"] + cabecera["empleado"] + gastos_extra
    total_mas_iva = int(round(total * Decimal("1.21")))
    ganancia = total_mas_iva - gastos

    return {
        "total": total,
        "total_mas_iva": total_mas_iva,
        "gastos": gastos,
        "ganancia": ganancia,
    }


def obtener_datos_viaje_reparto(id_viaje_reparto):
    # Trae un viaje de reparto activo con sus relaciones listas para la vista de informacion.
    # Precargo tambien los gastos para que la tarjeta de resultado no dispare queries extra.
    return get_object_or_404(
        ViajeReparto.objects.select_related("chofer", "vehiculo")
        .prefetch_related("destinos", "detalle_gastos"),
        id=id_viaje_reparto,
        activo=True,
    )


def crear_gasto_viaje_reparto(id_viaje_reparto, tipo_gasto, monto):
    # Mismo patron que crear_gasto_viaje_cereal, sobre la tabla GastoViajeReparto.
    # Cada gasto cargado recalcula la ganancia, porque la property del modelo se deriva
    # de la suma de gastos del viaje.
    viaje_reparto = get_object_or_404(ViajeReparto, id=id_viaje_reparto)

    # Validamos que el tipo de gasto sea correcto
    tipos_validos = dict(GastoViajeReparto._meta.get_field("gasto").choices).keys()
    if tipo_gasto not in tipos_validos:
        raise ValueError(f"El tipo de gasto '{tipo_gasto}' no es válido.")

    # Validamos el monto
    try:
        monto_val = int(monto)
        if monto_val <= 0:
            raise ValueError()
    except (ValueError, TypeError):
        raise ValueError("El monto debe ser un número entero positivo mayor a 0.")

    nuevo_gasto = GastoViajeReparto.objects.create(
        viaje_reparto=viaje_reparto,
        gasto=tipo_gasto,
        monto=monto_val
    )
    return nuevo_gasto


def editar_viaje_reparto(id_viaje_reparto, id_chofer, id_vehiculo, gasto_combustible,
                         costo_empleado, valor_viaje, fecha_viaje_reparto, destinos, pagado=None):
    # 'pagado' llega en None cuando quien edita no puede tocar el cobro (no staff):
    # en ese caso el estado de pago queda como estaba, no se pisa con un False.
    gasto_val, costo_val, valor_val, destinos_limpios = _validar_viaje_reparto(
        id_chofer, id_vehiculo, gasto_combustible, costo_empleado,
        valor_viaje, fecha_viaje_reparto, destinos
    )

    with transaction.atomic():
        viaje_reparto = get_object_or_404(ViajeReparto, id=id_viaje_reparto)

        viaje_reparto.chofer_id = id_chofer
        viaje_reparto.vehiculo_id = id_vehiculo
        viaje_reparto.gasto_combustible_viaje_reparto = gasto_val
        viaje_reparto.costo_empleado = costo_val
        viaje_reparto.valor_viaje = valor_val
        viaje_reparto.fecha_viaje_reparto = fecha_viaje_reparto
        if pagado is not None:
            _aplicar_estado_pago(viaje_reparto, pagado)
        viaje_reparto.save()

        # Reemplazo los destinos (mismo patron que editar_viaje_cereal)
        viaje_reparto.destinos.all().delete()
        for destino_nombre in destinos_limpios:
            DetalleViajeReparto.objects.create(
                viaje_reparto=viaje_reparto,
                destinos_reparto=destino_nombre
            )

    return viaje_reparto


def marcar_pago_viaje_reparto(id_viaje_reparto, pagado):
    """Marca (o desmarca) el cobro de un viaje de reparto.

    Mismo criterio que marcar_pago_viaje_cereal: solo toca 'pagado' y guarda con
    update_fields, porque es la accion de la casilla de la tabla.
    """
    viaje_reparto = get_object_or_404(ViajeReparto, id=id_viaje_reparto, activo=True)
    _aplicar_estado_pago(viaje_reparto, pagado)
    viaje_reparto.save(update_fields=["pagado", "fecha_pago"])
    return viaje_reparto


def eliminar_viaje_reparto(id_viaje_reparto):
    viaje_reparto = get_object_or_404(ViajeReparto, id=id_viaje_reparto)
    # Borrado logico: lo marco inactivo para no perder el historial
    viaje_reparto.activo = False
    viaje_reparto.save()
    return viaje_reparto
