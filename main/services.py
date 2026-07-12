import re
from datetime import datetime
import requests
from decimal import Decimal, InvalidOperation

from django.shortcuts import get_object_or_404
from django.http import Http404
from django.db import transaction
from django.db.models import Sum, F, Value, Count, Q
from django.db.models.functions import Coalesce
from django.core.cache import cache
from .models import (Producto, Cliente, Operacion, DetalleOperacion, Pago, Cotizaciones, Chofer, Vehiculo, Viaje,
                     DetalleViaje, Gasto, ViajeCereal, DetalleViajeCereal, GastoViajeCereal,
                     ViajeReparto, DetalleViajeReparto, GastoViajeReparto)


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


def modificar_stock(id_producto, cantidad):
    """
    Modifica el stock de un producto sumando o restando según el valor de 'cantidad'.
    - cantidad > 0 → suma stock (ingreso de mercadería, devolución, etc.)
    - cantidad < 0 → resta stock (venta, egreso, etc.)

    Retorna el producto actualizado o lanza ValueError si el stock quedaría negativo.
    """
    # Verifico existencia para mantener el comportamiento 404 ante productos
    # inexistentes o inactivos
    if not Producto.objects.filter(id=id_producto, activo=True).exists():
        raise Http404("Producto no encontrado")

    if cantidad < 0:
        # UPDATE condicional atómico: el chequeo de stock (WHERE cantidad__gte)
        # y el descuento (SET cantidad = cantidad + n) ocurren en UNA sola
        # sentencia SQL. No hay ventana entre verificar y escribir, por lo que
        # se elimina el read-modify-write que permitía lost updates y sobreventa.
        filas = Producto.objects.filter(
            id=id_producto, activo=True, cantidad__gte=abs(cantidad)
        ).update(cantidad=F("cantidad") + cantidad)

        if filas == 0:
            # 0 filas afectadas significa que no había stock suficiente
            raise ValueError("No se puede quitar más stock del existente.")
    else:
        # Ingreso de stock: incremento atómico sin lectura previa
        Producto.objects.filter(id=id_producto, activo=True).update(
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
        clientes = clientes.filter(Q(nombre__icontains=q) | Q(apellido__icontains=q))

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


def crear_operacion(cliente, items, metodo_pago, tipo_operacion, viaje=None):
    # Obtenemos las cotizaciones actuales antes de la transacción
    cotizacion_dolar = get_cotizacion_dolar_oficial()
    if cotizacion_dolar:
        valor_dolar = cotizacion_dolar.get("venta")
    else:
        valor_dolar = None

    valor_miel = get_cotizacion_miel_50mm()

    with transaction.atomic():
        # Creo la operación con las cotizaciones actuales
        operacion = Operacion.objects.create(
            cliente=cliente,
            viaje=viaje,
            tipo_operacion=tipo_operacion,
            valor_dolar=valor_dolar,
            valor_kilo_miel=valor_miel
        )

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
                # En una venta, el precio se toma del producto
                precio_unitario = producto.precio
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

        # Si el pago es "contado", generamos automáticamente un pago usando el monto_total calculado
        if metodo_pago.lower() == "contado":
            Pago.objects.create(
                operacion=operacion,
                monto=operacion.monto_total
            )

    return operacion


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

        # Revertimos el stock de cada producto en el detalle según el tipo de operación
        for detalle in detalles:
            # Lineas a granel: los kilos se revierten sobre la tabla de cotizaciones
            if detalle.cotizacion_id:
                if operacion.tipo_operacion == "venta":
                    # Venta cancelada: los kilos vuelven al deposito
                    Cotizaciones.objects.filter(id=detalle.cotizacion_id).update(
                        cantidad=F("cantidad") + detalle.cantidad
                    )
                else:
                    # Compra cancelada: quito los kilos, con el mismo chequeo
                    # condicional atomico para no dejar el stock negativo
                    filas = Cotizaciones.objects.filter(
                        id=detalle.cotizacion_id, cantidad__gte=detalle.cantidad
                    ).update(cantidad=F("cantidad") - detalle.cantidad)

                    if filas == 0:
                        raise ValueError(
                            "No se puede cancelar la compra: los kilos a granel ya fueron vendidos."
                        )
                continue

            producto = detalle.producto

            if operacion.tipo_operacion == "venta":
                # Si era venta, devuelvo stock y resto de cantidad vendida de
                # forma atómica con F()
                modificar_stock(producto.id, detalle.cantidad)
                Producto.objects.filter(id=producto.id).update(
                    cantidad_vendida=F("cantidad_vendida") - detalle.cantidad
                )
            else:
                # Si era compra, quito stock y resto de cantidad comprada
                modificar_stock(producto.id, -detalle.cantidad)
                Producto.objects.filter(id=producto.id).update(
                    cantidad_comprada=F("cantidad_comprada") - detalle.cantidad
                )

        # Marcamos la operación como inactiva (cancelada)
        operacion.activa = False
        operacion.save(update_fields=["activa"])

    return operacion


def _iniciales(nombre, apellido=None):
    # Siempre dos letras: inicial de nombre + inicial de apellido.
    # Sin apellido, uso las dos primeras letras del nombre.
    nombre = (nombre or "").strip()
    apellido = (apellido or "").strip()
    if apellido:
        return (nombre[:1] + apellido[:1]).upper()
    return nombre[:2].upper()


def obtener_listado_deudores(q=""):
    dolar_actual_data = get_cotizacion_dolar_oficial()
    dolar_actual = Decimal(str(dolar_actual_data.get("venta") or 1))  # Prevención división por 0 si falla la API

    miel_actual_data = get_cotizacion_miel_50mm()
    try:
        miel_actual = Decimal(str(miel_actual_data)) if miel_actual_data else None
    except ValueError:
        miel_actual = None

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

    if q:
        from django.db.models import Q
        if q.isdigit():
            operaciones_adeudadas = operaciones_adeudadas.filter(id__icontains=q)
        else:
            operaciones_adeudadas = operaciones_adeudadas.filter(
                Q(cliente__nombre__icontains=q) | Q(cliente__apellido__icontains=q)
            )

    from django.utils import timezone
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

        lista_deudores.append({
            "id": operacion.id,
            "cliente": f"{operacion.cliente.nombre} {operacion.cliente.apellido or ''}".strip(),
            "iniciales": _iniciales(operacion.cliente.nombre, operacion.cliente.apellido),
            "fecha": operacion.fecha,
            "dias": dias,
            "deuda_pesos": deuda_pesos,
            "deuda_dolar_historico": round(deuda_dolar_historico, 2) if deuda_dolar_historico else None,
            "deuda_dolar_actual": round(deuda_dolar_actual, 2) if deuda_dolar_actual else None,
            "kg_miel_historico": round(kg_miel_historico, 2) if kg_miel_historico else None,
            "kg_miel_actual": round(kg_miel_actual, 2) if kg_miel_actual else None
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

    # 6. Toneladas: entero positivo dentro del limite de la BD
    try:
        toneladas_val = int(toneladas)
        if toneladas_val <= 0 or toneladas_val > 2147483647:
            raise ValueError()
    except (ValueError, TypeError):
        raise ValueError("Las toneladas deben ser un numero entero positivo.")

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
                       toneladas, precio_tonelada, porcentaje_chofer, fecha_viaje_cereal, destinos):
    """
    Crea un viaje de cereal (maestro) y sus destinos asociados (detalle) en una
    transaccion atomica. 'destinos' es una lista de strings.
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
                        toneladas, precio_tonelada, porcentaje_chofer, fecha_viaje_cereal, destinos):
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
        viaje_cereal.save()

        # Reemplazo los destinos (mismo patron que editar_viaje)
        viaje_cereal.destinos.all().delete()
        for destino_nombre in destinos_limpios:
            DetalleViajeCereal.objects.create(
                viaje_cereal=viaje_cereal,
                destino=destino_nombre
            )

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
                        valor_viaje, fecha_viaje_reparto, destinos):
    """
    Crea un viaje de reparto (maestro) y sus destinos asociados (detalle) en una
    transaccion atomica. 'destinos' es una lista de strings.
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
                         costo_empleado, valor_viaje, fecha_viaje_reparto, destinos):
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
        viaje_reparto.save()

        # Reemplazo los destinos (mismo patron que editar_viaje_cereal)
        viaje_reparto.destinos.all().delete()
        for destino_nombre in destinos_limpios:
            DetalleViajeReparto.objects.create(
                viaje_reparto=viaje_reparto,
                destinos_reparto=destino_nombre
            )

    return viaje_reparto


def eliminar_viaje_reparto(id_viaje_reparto):
    viaje_reparto = get_object_or_404(ViajeReparto, id=id_viaje_reparto)
    # Borrado logico: lo marco inactivo para no perder el historial
    viaje_reparto.activo = False
    viaje_reparto.save()
    return viaje_reparto
