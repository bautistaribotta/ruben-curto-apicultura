import re
from datetime import date, datetime, time, timedelta
import requests
from django.utils import timezone
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.shortcuts import get_object_or_404
from django.http import Http404
from django.db import transaction
from django.db.models import (Sum, F, Value, Count, Q, Subquery, OuterRef, Exists, Case, When,
                              IntegerField, DecimalField, DateField)
from django.db.models.functions import Coalesce
from django.template.defaultfilters import floatformat
from django.core.cache import cache
from .models import (Producto, Cliente, Operacion, DetalleOperacion, Pago, ProductoPorKg, Empleado, PagosEmpleados,
                     Vehiculo, Viaje, DetalleViaje, Gasto, IngresoCaja, ViajeCereal, DetalleViajeCereal, GastoViajeCereal,
                     ViajeReparto, GastoViajeReparto, DestinoViajeReparto, Casa, Contrato, PagoAlquiler,
                     GastoCasa, RegistroKilometraje, Seguro, VTV, Servis, ObservacionVehiculo,
                     EstacionDeServicio, CargaCombustible, Empresa, OperacionIva,
                     Banco, CuentaCorriente, Cheque,
                     contratos_del_periodo, periodo_actual, _expresion_iva)


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
# El numero de factura admite hasta 20 digitos, solo numeros (conserva ceros a la izquierda)
REGEX_FACTURA = re.compile(r"^[0-9]{1,20}$")


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


# --- PRODUCTOS POR KILO ---
"""
Mismo ciclo de vida que un producto envasado, pero sobre ProductoPorKg: la
unidad de venta es el kilo, asi que el stock admite decimales y el precio se
guarda por kilo. Los articulos historicos de miel y cera (ARTICULOS_COTIZACION)
quedan fuera de la edicion y de la baja: su precio se toca en cotizaciones.
"""


def _validar_producto_por_kg(nombre, categoria, precio, id_excluir=None):
    """
    Normaliza y valida los datos comunes al alta y a la edicion. Devuelve la
    tupla (nombre, categoria, precio) ya lista para escribir en la base.
    """
    nombre = (nombre or "").strip()

    if not (3 <= len(nombre) <= 30) or not REGEX_TEXTO_NUMEROS.match(nombre):
        raise ValueError("El nombre debe tener entre 3 y 30 caracteres, sin simbolos.")

    # El nombre es unico en la tabla: aviso antes de que la base tire IntegrityError
    repetidos = ProductoPorKg.objects.filter(articulo__iexact=nombre)
    if id_excluir:
        repetidos = repetidos.exclude(id=id_excluir)
    if repetidos.exists():
        raise ValueError("Ya existe un producto por kilo con ese nombre.")

    if categoria not in dict(Producto.categorias):
        raise ValueError("Seleccione una categoria valida.")

    try:
        precio = Decimal(str(precio).strip())
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError("Ingrese un precio por kilo valido.")

    # El precio por kilo se guarda entero: un valor con decimales seria un
    # separador de miles mal escrito, y truncarlo guardaria otro precio
    if precio != precio.to_integral_value():
        raise ValueError("El precio por kilo se escribe sin decimales.")

    precio = int(precio)

    if precio < 1:
        raise ValueError("El precio por kilo no puede ser menor a 1.")

    return nombre, categoria, precio


def _a_kilos(cantidad):
    # Los kilos llegan del formulario como texto; acepto vacio como 0
    if cantidad in (None, ""):
        return Decimal("0")
    try:
        kilos = Decimal(str(cantidad).replace(",", "."))
    except InvalidOperation:
        raise ValueError("Ingrese una cantidad de kilos valida.")
    return kilos.quantize(Decimal("0.01"))


def nuevo_producto_por_kg(nombre, categoria=None, precio=None, cantidad=None):
    nombre, categoria, precio = _validar_producto_por_kg(nombre, categoria, precio)
    kilos = _a_kilos(cantidad)

    if kilos < 0:
        raise ValueError("El stock inicial no puede ser negativo.")

    return ProductoPorKg.objects.create(
        articulo=nombre, categoria=categoria, monto=precio, cantidad=kilos
    )


def obtener_datos_producto_por_kg(id_producto):
    try:
        producto = ProductoPorKg.objects.get(id=id_producto, activo=True)
    except ProductoPorKg.DoesNotExist:
        return None

    return {
        "id": producto.id,
        "nombre": producto.articulo,
        "categoria": producto.categoria,
        "precio": str(producto.monto),
        "cantidad": str(producto.cantidad),
        "es_cotizacion": producto.es_cotizacion,
    }


def editar_producto_por_kg(id_producto, nombre, categoria, precio):
    # Como en los envasados, el stock no viaja en la edicion: se mueve solo con
    # el modal de ajuste y con las operaciones (UPDATE atomico)
    producto = get_object_or_404(ProductoPorKg, id=id_producto)

    if producto.es_cotizacion:
        raise ValueError("La miel y la cera se editan desde las cotizaciones.")

    nombre, categoria, precio = _validar_producto_por_kg(nombre, categoria, precio, id_excluir=producto.id)

    producto.articulo = nombre
    producto.categoria = categoria
    producto.monto = precio
    producto.save()
    return producto


def eliminar_producto_por_kg(id_producto):
    producto = get_object_or_404(ProductoPorKg, id=id_producto)

    if producto.es_cotizacion:
        raise ValueError("La miel y la cera no se pueden eliminar del inventario.")

    # Baja logica, igual que en Producto: las operaciones historicas siguen
    # apuntando a esta fila
    producto.activo = False
    producto.save()
    return producto


def modificar_stock_por_kg(id_producto, cantidad):
    """
    Suma o resta kilos con el mismo UPDATE condicional atomico que uso en los
    productos envasados: el chequeo de stock y el descuento van en una sola
    sentencia, para que dos ajustes simultaneos no se pisen.
    """
    kilos = _a_kilos(cantidad)

    if not ProductoPorKg.objects.filter(id=id_producto, activo=True).exists():
        raise Http404("Producto no encontrado")

    if kilos < 0:
        filas = ProductoPorKg.objects.filter(
            id=id_producto, activo=True, cantidad__gte=abs(kilos)
        ).update(cantidad=F("cantidad") + kilos)

        if filas == 0:
            raise ValueError("No se puede quitar mas stock del existente.")
    else:
        ProductoPorKg.objects.filter(id=id_producto, activo=True).update(
            cantidad=F("cantidad") + kilos
        )

    return ProductoPorKg.objects.get(id=id_producto)


# --- ESTACIONES DE SERVICIO ---
# Catalogo simple (solo nombre + activa). La baja es logica para no perder
# el historial cuando las cargas de combustible referencien la estacion.
def crear_estacion(nombre):
    nombre = (nombre or "").strip()
    if not nombre:
        raise ValueError("El nombre de la estacion es obligatorio.")

    # El nombre es unico: aviso antes de que la base tire IntegrityError. Ignoro
    # las inactivas para poder reutilizar un nombre dado de baja.
    if EstacionDeServicio.objects.filter(nombre__iexact=nombre, activa=True).exists():
        raise ValueError("Ya existe una estacion con ese nombre.")

    return EstacionDeServicio.objects.create(nombre=nombre)


def obtener_estaciones_activas():
    """Estaciones activas en orden alfabetico, para los desplegables de combustible."""
    return EstacionDeServicio.objects.filter(activa=True).order_by("nombre")


def obtener_datos_estacion(id_estacion):
    try:
        estacion = EstacionDeServicio.objects.get(id=id_estacion, activa=True)
        return {"id": estacion.id, "nombre": estacion.nombre}
    except EstacionDeServicio.DoesNotExist:
        return None


def editar_estacion(id_estacion, nombre):
    nombre = (nombre or "").strip()
    if not nombre:
        raise ValueError("El nombre de la estacion es obligatorio.")

    estacion = get_object_or_404(EstacionDeServicio, id=id_estacion)

    # Descarto choques con otra estacion activa (la propia no cuenta)
    duplicada = (EstacionDeServicio.objects
                 .filter(nombre__iexact=nombre, activa=True)
                 .exclude(id=estacion.id)
                 .exists())
    if duplicada:
        raise ValueError("Ya existe una estacion con ese nombre.")

    estacion.nombre = nombre
    estacion.save()
    return estacion


def eliminar_estacion(id_estacion):
    estacion = get_object_or_404(EstacionDeServicio, id=id_estacion)
    # Baja logica: preserva el historial de cargas de combustible
    estacion.activa = False
    estacion.save()
    return estacion


# --- CARGAS DE COMBUSTIBLE ---------------------------------------------------

def _validar_carga(id_empleado, id_vehiculo, fecha, monto, litros):
    """Limpia y valida los datos de una carga. Devuelve (empleado, vehiculo, fecha, monto, litros).

    El empleado y el vehiculo son obligatorios (cada carga la hace una persona con
    una unidad de la flota), igual que la fecha y el monto. Los litros son opcionales.
    """
    empleado = get_object_or_404(Empleado, id=id_empleado, activo=True)
    vehiculo = get_object_or_404(Vehiculo, id=id_vehiculo, activo=True)
    dia = _fecha_obligatoria(fecha, "La fecha de la carga")
    total = _decimal_opcional(monto, "El monto de la carga", MAX_COSTO)
    if not total:
        raise ValueError("El monto de la carga es obligatorio y tiene que ser mayor a cero.")
    cantidad = _decimal_opcional(litros, "Los litros de la carga")
    return empleado, vehiculo, dia, total, cantidad


def crear_carga(id_estacion, id_empleado=None, id_vehiculo=None, fecha=None, monto=None, litros=None, pagada=False):
    """Registra una carga de combustible de una estacion activa."""
    estacion = get_object_or_404(EstacionDeServicio, id=id_estacion, activa=True)
    empleado, vehiculo, dia, total, cantidad = _validar_carga(id_empleado, id_vehiculo, fecha, monto, litros)
    return CargaCombustible.objects.create(
        estacion=estacion, empleado=empleado, vehiculo=vehiculo, fecha=dia, monto=total,
        litros=cantidad, pagada=bool(pagada),
    )


def editar_carga(id_carga, id_empleado=None, id_vehiculo=None, fecha=None, monto=None, litros=None, pagada=False):
    """Corrige una carga de combustible ya cargada."""
    carga = get_object_or_404(CargaCombustible, id=id_carga, activa=True)
    empleado, vehiculo, dia, total, cantidad = _validar_carga(id_empleado, id_vehiculo, fecha, monto, litros)
    carga.empleado, carga.vehiculo, carga.fecha, carga.monto = empleado, vehiculo, dia, total
    carga.litros, carga.pagada = cantidad, bool(pagada)
    carga.save()
    return carga


def alternar_pago_carga(id_carga):
    """Invierte el estado de pago de una carga (paga <-> impaga)."""
    with transaction.atomic():
        # Bloqueo la fila antes de leer 'pagada': el toggle es un read-modify-write
        # (leo el valor, lo invierto, lo guardo). Sin el lock, dos requests leen el
        # mismo estado y ambos lo invierten al mismo valor: un click se pierde.
        carga = get_object_or_404(
            CargaCombustible.objects.select_for_update(), id=id_carga, activa=True
        )
        carga.pagada = not carga.pagada
        carga.save(update_fields=["pagada"])
    return carga


def eliminar_carga(id_carga):
    """Baja logica de una carga: la saca del saldo sin perder el historial."""
    carga = get_object_or_404(CargaCombustible, id=id_carga)
    carga.activa = False
    carga.save(update_fields=["activa"])
    return carga


def obtener_cargas(id_estacion, estado="impagas", desde=None, hasta=None):
    """Historial de cargas activas de una estacion, de la mas nueva a la mas vieja.

    estado filtra por pago: "impagas" (por defecto), "pagadas" o "todas".
    desde/hasta acotan por la fecha de la carga (date o None si no hay filtro).
    """
    estacion = get_object_or_404(EstacionDeServicio, id=id_estacion)
    cargas = estacion.cargas.filter(activa=True).select_related("empleado", "vehiculo")
    if estado == "impagas":
        cargas = cargas.filter(pagada=False)
    elif estado == "pagadas":
        cargas = cargas.filter(pagada=True)
    if desde:
        cargas = cargas.filter(fecha__gte=desde)
    if hasta:
        cargas = cargas.filter(fecha__lte=hasta)
    return cargas


def obtener_totales_cargas(id_estacion, estado="impagas", desde=None, hasta=None):
    """Total de dinero y de litros de las cargas que muestran los filtros activos.

    Reusa el mismo queryset filtrado que obtener_cargas para que el resumen siga
    exactamente el estado de pago y el rango de fechas elegidos (no es un total
    historico). Los litros son opcionales: Sum ignora los None, asi que el total
    suma solo las cargas que los tienen. Coalesce deja 0 cuando no hay ninguna
    carga en el filtro (evita None en la plantilla).
    """
    cargas = obtener_cargas(id_estacion, estado, desde, hasta)
    return cargas.aggregate(
        total_monto=Coalesce(Sum("monto"), Decimal("0")),
        total_litros=Coalesce(Sum("litros"), Decimal("0")),
    )


def obtener_datos_carga(id_carga):
    """Datos de una carga para precargar el panel de edicion, o None si no existe."""
    try:
        carga = CargaCombustible.objects.get(id=id_carga, activa=True)
    except CargaCombustible.DoesNotExist:
        return None
    return {
        "id": carga.id,
        "empleado": carga.empleado_id,
        "vehiculo": carga.vehiculo_id,
        "fecha": carga.fecha.strftime("%Y-%m-%d"),
        "monto": str(carga.monto),
        "litros": str(carga.litros) if carga.litros is not None else "",
        "pagada": carga.pagada,
    }


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
    "cliente__" o "empleado__".
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
    # local antes de extraer la fecha, y devuelve NULL -> descarta txdo- si el
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
            # Id del cliente: permite agrupar por cliente para el selector y filtrar el
            # listado por el cliente elegido (en vez de por texto libre).
            "cliente_id": operacion.cliente.id,
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


"""
Icono con el que cada categoria se dibuja en el tablero de inicio, y la etiqueta
de su tarjeta de resumen cuando el nombre de la categoria no es el que se venia
mostrando. Es lo unico del tablero que sigue viviendo en el codigo: que producto
aparece lo decide el flag mostrar_en_inicio de cada base, no una lista de aca.
"""
CATEGORIAS_INICIO = {
    "Miel": {"icono": "water_drop"},
    "Alimento": {"icono": "nutrition"},
    "Cera": {"icono": "hexagon"},
    "Madera": {"icono": "forest"},
    "Estampado": {"icono": "grid_on"},
    "Insumos": {"icono": "handyman"},
    "Medicamentos": {"icono": "medication"},
    "Tambores Vacios": {"icono": "oil_barrel", "etiqueta": "Tambores vacios"},
    "Otros": {"icono": "category"},
}


def _grupo_inicio(categoria):
    return {
        "categoria": categoria,
        "icono": CATEGORIAS_INICIO.get(categoria, {}).get("icono", "inventory_2"),
        "articulos": [],
        "kilos": Decimal("0"),
        "resumenes": [],
    }


def get_tablero_inicio():
    """
    Arma los grupos del tablero de inicio con los productos marcados con
    mostrar_en_inicio. Cada grupo es una categoria: adentro van las tarjetas de
    los articulos que se venden por kilo (precio editable, kilos disponibles) y
    los kilos sumados de esos articulos.

    Los productos que se venden por unidad no van tarjeta por tarjeta: se
    resumen en una sola por categoria, con el total de unidades y cuantos
    productos la componen. Esa tarjeta acompana al tablero de su categoria y, si
    esa categoria no tiene articulos por kilo, viaja con el primer grupo: es el
    caso de los tambores vacios, que siempre se mostraron junto a la miel.
    """
    orden = {categoria: i for i, (categoria, _) in enumerate(Producto.categorias)}
    por_categoria = {}
    grupos = []

    """
    Ordeno por id, o sea por orden de alta: es el orden en el que se vienen
    mostrando las tarjetas y no se reacomoda solo cuando cambia un precio.
    """
    for articulo in ProductoPorKg.objects.filter(activo=True, mostrar_en_inicio=True).order_by("id"):
        grupo = por_categoria.get(articulo.categoria)
        if grupo is None:
            grupo = _grupo_inicio(articulo.categoria)
            por_categoria[articulo.categoria] = grupo
            grupos.append(grupo)

        grupo["articulos"].append(articulo)
        grupo["kilos"] += articulo.cantidad

    # Ordeno antes de repartir los resumenes: el que no tiene tablero propio se
    # cuelga del primer grupo, y "primero" tiene que ser el de siempre
    grupos.sort(key=lambda grupo: orden.get(grupo["categoria"], len(orden)))

    resumenes = (Producto.objects.filter(activo=True, mostrar_en_inicio=True)
                 .values("categoria")
                 .annotate(unidades=Sum("cantidad"), tipos=Count("id"))
                 .order_by())

    for fila in sorted(resumenes, key=lambda f: orden.get(f["categoria"], len(orden))):
        categoria = fila["categoria"]
        datos = CATEGORIAS_INICIO.get(categoria, {})

        grupo = por_categoria.get(categoria) or (grupos[0] if grupos else None)
        if grupo is None:
            grupo = _grupo_inicio(categoria)
            por_categoria[categoria] = grupo
            grupos.append(grupo)

        grupo["resumenes"].append({
            "titulo": datos.get("etiqueta", categoria),
            "icono": datos.get("icono", "inventory_2"),
            "unidades": fila["unidades"] or 0,
            "tipos": fila["tipos"],
        })

    return grupos


def actualizar_cotizacion(articulo, monto):
    """
    Actualiza o crea una cotización en la base de datos.
    """
    cotizacion, created = ProductoPorKg.objects.update_or_create(
        articulo=articulo,
        defaults={"monto": monto}
    )
    return cotizacion


def get_cotizacion_miel_50mm():
    """
    Obtiene la cotización de la miel. Se toma 'Miel menor a 50 mm' como referencia por defecto.
    """
    try:
        miel = ProductoPorKg.objects.get(articulo="Miel menor a 50 mm")
        return miel.monto
    except ProductoPorKg.DoesNotExist:
        return 1.00


def get_cotizacion_cera_operculo():
    """
    Obtiene la cotización de la cera. Se toma 'Cera Operculo' como referencia.
    Devuelve None si no existe para que quien la use muestre un guion en vez
    de calcular una equivalencia sin sentido.
    """
    try:
        cera = ProductoPorKg.objects.get(articulo="Cera Operculo")
        return cera.monto
    except ProductoPorKg.DoesNotExist:
        return None


def crear_empleado(nombre, apellido):
    # Aplico limpieza de espacios
    nombre = nombre.strip()
    apellido = apellido.strip()

    # Valido la longitud y formato del nombre
    if not (3 <= len(nombre) <= 25) or not REGEX_TEXTO_BASICO.match(nombre):
        raise ValueError("El nombre debe tener entre 3 y 25 letras, sin números ni símbolos.")

    # Valido la longitud y formato del apellido
    if not (3 <= len(apellido) <= 25) or not REGEX_TEXTO_BASICO.match(apellido):
        raise ValueError("El apellido debe tener entre 3 y 25 letras, sin números ni símbolos.")

    nuevo_empleado = Empleado.objects.create(
        nombre=nombre,
        apellido=apellido
    )
    return nuevo_empleado


def editar_empleado(id_empleado, nombre, apellido, activo):
    empleado = get_object_or_404(Empleado, id=id_empleado)

    # Aplico limpieza de espacios
    nombre = nombre.strip()
    apellido = apellido.strip()

    # Valido la longitud y formato del nombre
    if not (3 <= len(nombre) <= 25) or not REGEX_TEXTO_BASICO.match(nombre):
        raise ValueError("El nombre debe tener entre 3 y 25 letras, sin números ni símbolos.")

    # Valido la longitud y formato del apellido
    if not (3 <= len(apellido) <= 25) or not REGEX_TEXTO_BASICO.match(apellido):
        raise ValueError("El apellido debe tener entre 3 y 25 letras, sin números ni símbolos.")

    empleado.nombre = nombre
    empleado.apellido = apellido
    empleado.activo = activo

    empleado.save()
    return empleado


def fijar_sueldo_empleado(id_empleado, sueldo):
    """Fija el sueldo mensual de un empleado.

    El sueldo llega del modal como texto ya normalizado a punto decimal por
    formato_miles.js (el submit limpia el separador de miles antes del POST). Se
    acepta 0 para dejar el sueldo sin definir; un valor negativo o no numerico se
    rechaza. El campo es DecimalField(max_digits=10, decimal_places=2), asi que
    corto en 8 enteros para no romper el insert de la base.
    """
    empleado = get_object_or_404(Empleado, id=id_empleado, activo=True)

    try:
        sueldo = Decimal(str(sueldo).strip())
    except (InvalidOperation, AttributeError):
        raise ValueError("El sueldo no es un número válido.")

    if sueldo < 0:
        raise ValueError("El sueldo no puede ser negativo.")

    sueldo = sueldo.quantize(Decimal("0.01"))
    if sueldo >= Decimal("100000000"):
        raise ValueError("El sueldo es demasiado grande.")

    empleado.sueldo = sueldo

    # La cuenta corriente arranca la primera vez que se carga un sueldo real: fijo
    # el corte en hoy y de ahi en adelante se devenga el sueldo. No lo piso en las
    # ediciones siguientes para no reiniciar el saldo ya acumulado.
    campos = ["sueldo"]
    if sueldo > 0 and empleado.inicio_cuenta is None:
        empleado.inicio_cuenta = timezone.localdate()
        campos.append("inicio_cuenta")

    empleado.save(update_fields=campos)
    return empleado


def fijar_vencimiento_carnet(id_empleado, fecha):
    """Fija la fecha de vencimiento del carnet de conducir de un empleado.

    La fecha llega del modal como texto "YYYY-MM-DD". El mismo servicio sirve
    para el alta (todavia no habia fecha) y para las ediciones posteriores. Se
    admite cualquier fecha, incluso pasada: un carnet ya vencido es justamente
    lo que hay que poder registrar para que el aviso lo marque.
    """
    empleado = get_object_or_404(Empleado, id=id_empleado, activo=True)

    if fecha in (None, ""):
        raise ValueError("La fecha de vencimiento del carnet es obligatoria.")

    try:
        fecha = datetime.strptime(str(fecha).strip(), "%Y-%m-%d").date()
    except (ValueError, TypeError):
        raise ValueError("La fecha de vencimiento del carnet no es válida.")

    empleado.vencimiento_carnet = fecha
    empleado.save(update_fields=["vencimiento_carnet"])
    return empleado


def eliminar_empleado(id_empleado):
    empleado = get_object_or_404(Empleado, id=id_empleado)
    empleado.activo = False
    empleado.save()
    return empleado


def obtener_datos_empleado(id_empleado):
    try:
        # Solo empleados activos, para no exponer registros dados de baja
        empleado = Empleado.objects.get(id=id_empleado, activo=True)
        return {
            "id": empleado.id,
            "nombre": empleado.nombre,
            "apellido": empleado.apellido,
        }
    except Empleado.DoesNotExist:
        return None


def _normalizar_datos_pago(monto, observaciones="", fecha=None):
    """Valida y normaliza los datos crudos de un pago (alta o edicion).

    La fecha llega del modal en formato "YYYY-MM-DD" y puede ser de hoy o de
    cualquier dia anterior, para poder cargar pagos que se hicieron y no se
    anotaron en el momento. Si no viene nada, queda la fecha de hoy. Un pago
    con fecha futura no tiene sentido, asi que se rechaza aca y no solo con el
    max del input, que el navegador puede saltearse.

    Devuelve (fecha, monto, observaciones) ya listos para guardar.
    """
    hoy = timezone.localdate()

    if fecha in (None, ""):
        fecha = hoy
    else:
        try:
            fecha = datetime.strptime(str(fecha).strip(), "%Y-%m-%d").date()
        except (ValueError, TypeError):
            raise ValueError("La fecha del pago no es válida.")

        if fecha > hoy:
            raise ValueError("La fecha del pago no puede ser posterior a hoy.")

    try:
        monto = Decimal(str(monto).strip())
    except (InvalidOperation, AttributeError):
        raise ValueError("El monto del pago no es un número válido.")

    if monto <= 0:
        raise ValueError("El monto del pago debe ser mayor a cero.")

    # El campo es DecimalField(max_digits=12, decimal_places=2): con mas de 10
    # enteros la base rechaza el insert, asi que corto antes con un mensaje claro
    monto = monto.quantize(Decimal("0.01"))
    if monto >= Decimal("10000000000"):
        raise ValueError("El monto del pago es demasiado grande.")

    observaciones = (observaciones or "").strip()
    if len(observaciones) > 250:
        raise ValueError("La observación no puede superar los 250 caracteres.")

    return fecha, monto, observaciones


def crear_pago_empleado(id_empleado, monto, observaciones="", fecha=None):
    """Registra un pago a un empleado."""
    empleado = get_object_or_404(Empleado, id=id_empleado, activo=True)
    fecha, monto, observaciones = _normalizar_datos_pago(monto, observaciones, fecha)

    return PagosEmpleados.objects.create(
        empleado=empleado,
        fecha=fecha,
        monto=monto,
        observaciones=observaciones,
    )


def editar_pago_empleado(id_pago, id_empleado, monto, observaciones="", fecha=None):
    """Actualiza un pago cargado a mano.

    Acota la busqueda al empleado del perfil para que un id de otro empleado no
    permita tocar su pago. La comision de un viaje de cereal no es un
    PagosEmpleados, asi que nunca llega por aca (no tiene botones de accion).
    """
    pago = get_object_or_404(PagosEmpleados, id=id_pago, empleado_id=id_empleado)
    fecha, monto, observaciones = _normalizar_datos_pago(monto, observaciones, fecha)

    pago.fecha = fecha
    pago.monto = monto
    pago.observaciones = observaciones
    pago.save(update_fields=["fecha", "monto", "observaciones"])
    return pago


def eliminar_pago_empleado(id_pago, id_empleado):
    """Borra un pago cargado a mano, acotado al empleado del perfil."""
    pago = get_object_or_404(PagosEmpleados, id=id_pago, empleado_id=id_empleado)
    pago.delete()


# -----------------------------------------------------------------------------
# PERIODO DE PAGOS DEL EMPLEADO (mes a mes)
#
# El perfil mira la cuenta corriente de a un mes por vez, navegable con flechas,
# igual que el mes a mes de alquileres. El mes se identifica siempre por su
# primer dia (el 1), asi entra en un DateField, se ordena y se compara sin
# ambiguedad y no importa que dia del mes lo escriba el usuario. Dentro del mes,
# las filas se agrupan por semana (lunes a domingo) con una franja divisoria.
# -----------------------------------------------------------------------------


def _lunes_de(fecha):
    """Lunes de la semana (lunes a domingo) que contiene a 'fecha'."""
    return fecha - timedelta(days=fecha.weekday())


def resolver_ancla_pagos(valor):
    """Primer dia del mes a mostrar, a partir del parametro 'pagos_ancla'.

    No explota si el valor viene vacio, mal escrito o pegado a mano: cae en el
    mes que contiene el dia de hoy, que es lo que el usuario espera al entrar.
    """
    try:
        ancla = datetime.strptime(str(valor).strip(), "%Y-%m-%d").date()
    except (ValueError, TypeError, AttributeError):
        ancla = timezone.localdate()
    return ancla.replace(day=1)


def rango_periodo_pagos(inicio):
    """(desde, hasta) inclusivos del mes que empieza en 'inicio'."""
    return inicio, mes_desplazado(inicio, 1) - timedelta(days=1)


def desplazar_periodo_pagos(inicio, paso):
    """Corre el mes 'paso' unidades hacia adelante (o atras). Sirve para las
    flechas: mes_desplazado ya contempla el cambio de año."""
    return mes_desplazado(inicio, paso)


def etiqueta_periodo_pagos(inicio):
    """Texto legible del mes para la barra de navegacion: "Agosto 2026"."""
    from django.utils.formats import date_format

    return date_format(inicio, "F Y").capitalize()


def _presentar_saldo(saldo):
    """Traduce un saldo (positivo = a favor del empleado) a los datos que la
    plantilla necesita para pintarlo: valor absoluto, si esta a favor y si esta
    saldado. Positivo = la empresa le debe; negativo = el empleado cobro de mas."""
    return {
        "valor": saldo,
        "abs": abs(saldo),
        "a_favor": saldo > 0,
        "en_contra": saldo < 0,
        "saldado": saldo == 0,
    }


def _movimientos_cuenta_corriente(empleado, desde, hasta):
    """Movimientos que le pagan al empleado dentro del mes [desde, hasta], sin
    ordenar. Dos fuentes, ambas suman a lo cobrado:

    - Comisiones cobradas por viajes de cereal.
    - Pagos reales cargados a mano.
    """
    eventos = []

    # Comisiones: fecha_pago es DateTimeField, acoto por momentos en zona local
    # (mismo motivo que el resto: CONVERT_TZ no sirve sin las tablas de zonas).
    tz = timezone.get_current_timezone()
    desde_dt = timezone.make_aware(datetime.combine(desde, time.min), tz)
    hasta_dt = timezone.make_aware(datetime.combine(hasta, time.max), tz)
    comisiones = (ViajeCereal.objects
                  .filter(empleado=empleado, activo=True, pagado=True,
                          porcentaje_empleado__gt=0,
                          fecha_pago__gte=desde_dt, fecha_pago__lte=hasta_dt)
                  .prefetch_related("detalle_gastos"))
    for viaje in comisiones:
        eventos.append({
            "fecha": timezone.localtime(viaje.fecha_pago).date(),
            "orden": 0,  # dentro del mismo dia, la comision antes que el pago
            "tipo": "comision",
            "concepto": f"Comisión viaje #{viaje.id}",
            "monto": viaje.pago_empleado,
            "viaje_id": viaje.id,
            "porcentaje": viaje.porcentaje_empleado,
        })

    pagos = PagosEmpleados.objects.filter(empleado=empleado, fecha__gte=desde, fecha__lte=hasta)
    for pago in pagos:
        # Los pagos que nacen de una devolucion de caja se muestran diferenciados
        # (badge propio y viaje de origen), aunque se editen como cualquier pago.
        es_devolucion = pago.origen == PagosEmpleados.ORIGEN_DEVOLUCION
        viaje_devolucion_id = None
        if es_devolucion:
            try:
                viaje_devolucion_id = pago.viaje_devolucion.id
            except Viaje.DoesNotExist:
                viaje_devolucion_id = None
        eventos.append({
            "fecha": pago.fecha,
            "orden": 1,
            "tipo": "pago",
            "origen": pago.origen,
            "es_devolucion": es_devolucion,
            "viaje_devolucion_id": viaje_devolucion_id,
            "concepto": pago.observaciones or "Pago",
            "monto": pago.monto,
            "pago_id": pago.id,
            "pago_monto": pago.monto,
            "observaciones": pago.observaciones,
        })

    return eventos


def _saldo_arrastre(empleado, desde):
    """Saldo que llega arrastrado al mes que empieza en 'desde', con signo.

    Se acumula mes a mes desde el inicio de la cuenta: cada mes suma sus
    movimientos al arrastre que traia y le resta el sueldo; el resultado pasa al
    mes siguiente. Positivo significa que se le pago de mas (a favor); negativo,
    que se le quedo debiendo. Es, en definitiva, todo lo pagado menos todos los
    sueldos anteriores a 'desde'."""
    inicio_mes = empleado.inicio_cuenta.replace(day=1)
    if desde <= inicio_mes:
        return Decimal("0")

    saldo = Decimal("0")
    mes = inicio_mes
    while mes < desde:
        m_desde, m_hasta = mes, mes_desplazado(mes, 1) - timedelta(days=1)
        pagado = sum((e["monto"] for e in _movimientos_cuenta_corriente(empleado, m_desde, m_hasta)),
                     Decimal("0"))
        saldo += pagado - empleado.sueldo
        mes = mes_desplazado(mes, 1)
    return saldo


def obtener_cuenta_corriente(empleado, desde, hasta):
    """Cuenta corriente del empleado para el mes [desde, hasta].

    Modelo mensual: cada mes es independiente. Devuelve un dict listo para la
    plantilla:

    - 'activa': si el empleado tiene cuenta (sueldo + fecha de inicio).
    - 'filas': los movimientos que le pagaron ese mes (comisiones y pagos), viejo
      -> nuevo, cada uno etiquetado con la semana a la que pertenece.
    - 'objetivo': el monto al que tenia que llegar en el mes, que es su sueldo.
    - 'alcanzado': lo pagado del mes contando el arrastre del mes anterior
      (movimientos del mes + arrastre, este ultimo con signo).
    - 'diferencia': alcanzado - objetivo. Positivo (se pago de mas) queda a favor
      del empleado; negativo (se pago de menos) queda en contra.
    - 'arrastre': el saldo con que se cerro el mes anterior. A favor suma a lo
      pagado de este mes; en contra (se le debe) lo resta. La plantilla lo muestra
      como una fila de aviso arriba de todo.
    """
    if not empleado.sueldo or empleado.sueldo <= 0 or not empleado.inicio_cuenta:
        return {"activa": False, "filas": [], "cantidad": 0}

    eventos = _movimientos_cuenta_corriente(empleado, desde, hasta)
    eventos.sort(key=lambda e: (e["fecha"], e["orden"]))

    movimientos_total = Decimal("0")
    filas = []
    for ev in eventos:
        movimientos_total += ev["monto"]
        fila = dict(ev)
        fila["monto_abs"] = abs(ev["monto"])
        # Semana (lunes a domingo) a la que pertenece la fila: la plantilla abre
        # una franja divisoria cada vez que cambia, para separar el mes por semanas.
        lunes = _lunes_de(ev["fecha"])
        fila["semana_inicio"] = lunes
        fila["semana_fin"] = lunes + timedelta(days=6)
        filas.append(fila)

    # El saldo con que cerro el mes anterior se arrastra. A favor cuenta como ya
    # pagado de este mes; en contra (se le debe) sube el objetivo, porque hay que
    # cubrir tambien lo que se venia debiendo. En los dos casos la diferencia
    # final es el saldo acumulado real y ni objetivo ni pagado quedan negativos.
    arrastre = _saldo_arrastre(empleado, desde)
    if arrastre >= 0:
        objetivo = empleado.sueldo
        alcanzado = movimientos_total + arrastre
    else:
        objetivo = empleado.sueldo - arrastre
        alcanzado = movimientos_total

    return {
        "activa": True,
        "objetivo": objetivo,
        "alcanzado": alcanzado,
        "diferencia": _presentar_saldo(alcanzado - objetivo),
        "arrastre": _presentar_saldo(arrastre),
        "filas": filas,
        "cantidad": len(filas),
    }


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


# ---------------------------------------------------------------------------
# Kilometraje, seguros, VTV y services de un vehiculo
#
# Los cuatro cuelgan del vehiculo con una relacion uno a muchos y comparten el
# mismo patron de CRUD: validar con los helpers de siempre (_fecha_obligatoria,
# _decimal_opcional, _texto_opcional) y borrar de verdad, porque lo unico que se
# borra es un registro cargado mal; el historial vive de no reescribirse.
# ---------------------------------------------------------------------------

# Topes de la BD: 10 digitos con 2 decimales para el kilometraje, 12 para los
# costos. Los dejo como constantes para no repetir el numero magico en cada
# validador y que se lea de donde sale.
MAX_KILOMETROS = Decimal("99999999.99")
MAX_COSTO = Decimal("9999999999.99")


def _validar_kilometraje(fecha, kilometros):
    """Limpia y valida una lectura de odometro. Devuelve (fecha, kilometros)."""
    dia = _fecha_obligatoria(fecha, "La fecha del kilometraje")
    km = _decimal_opcional(kilometros, "El kilometraje", MAX_KILOMETROS)
    if km is None:
        raise ValueError("Tenés que ingresar el kilometraje actual del vehículo.")
    if km < 0:
        raise ValueError("El kilometraje no puede ser negativo.")
    return dia, km


def crear_registro_km(id_vehiculo, fecha=None, kilometros=None):
    """Registra la lectura de odometro actual de un vehiculo activo."""
    vehiculo = get_object_or_404(Vehiculo, id=id_vehiculo, activo=True)
    dia, km = _validar_kilometraje(fecha, kilometros)
    return RegistroKilometraje.objects.create(vehiculo=vehiculo, fecha=dia, kilometros=km)


def editar_registro_km(id_registro, fecha=None, kilometros=None):
    """Corrige una lectura de odometro ya guardada (para lo que se tipeo mal)."""
    registro = get_object_or_404(RegistroKilometraje, id=id_registro)
    dia, km = _validar_kilometraje(fecha, kilometros)
    registro.fecha, registro.kilometros = dia, km
    registro.save()
    return registro


def eliminar_registro_km(id_registro):
    """Borra una carga de kilometraje cargada por error. Devuelve el id del vehiculo."""
    registro = get_object_or_404(RegistroKilometraje, id=id_registro)
    id_vehiculo = registro.vehiculo_id
    registro.delete()
    return id_vehiculo


def obtener_registros_km(id_vehiculo):
    """Historial de lecturas de odometro de un vehiculo, del mas nuevo al mas viejo."""
    vehiculo = get_object_or_404(Vehiculo, id=id_vehiculo)
    return vehiculo.registros_km.all()


def _validar_vigencia(inicio, fin, costo, observaciones, articulo):
    """Valida los datos de un seguro o una VTV (mismos campos y reglas).

    'articulo' arma los mensajes de error ("del seguro", "de la VTV"). Las dos
    fechas de vigencia son obligatorias y el fin no puede caer antes del inicio;
    el costo y las observaciones son opcionales.
    """
    ini = _fecha_obligatoria(inicio, f"La fecha de inicio {articulo}")
    f = _fecha_obligatoria(fin, f"La fecha de fin {articulo}")
    if f < ini:
        raise ValueError(f"El fin {articulo} no puede ser anterior a su inicio.")
    monto = _decimal_opcional(costo, "El costo", MAX_COSTO)
    obs = _texto_opcional(observaciones, 200, "Las observaciones")
    return ini, f, monto, obs


def crear_seguro(id_vehiculo, inicio=None, fin=None, costo=None, observaciones=None):
    """Nueva poliza de seguro de un vehiculo activo. Renovar es esto, no editar la vieja."""
    vehiculo = get_object_or_404(Vehiculo, id=id_vehiculo, activo=True)
    ini, f, monto, obs = _validar_vigencia(inicio, fin, costo, observaciones, "del seguro")
    return Seguro.objects.create(vehiculo=vehiculo, inicio=ini, fin=f, costo=monto, observaciones=obs)


def editar_seguro(id_seguro, inicio=None, fin=None, costo=None, observaciones=None):
    """Corrige una poliza de seguro ya cargada."""
    seguro = get_object_or_404(Seguro, id=id_seguro)
    ini, f, monto, obs = _validar_vigencia(inicio, fin, costo, observaciones, "del seguro")
    seguro.inicio, seguro.fin = ini, f
    seguro.costo, seguro.observaciones = monto, obs
    seguro.save()
    return seguro


def eliminar_seguro(id_seguro):
    """Borra una poliza cargada por error. Devuelve el id del vehiculo."""
    seguro = get_object_or_404(Seguro, id=id_seguro)
    id_vehiculo = seguro.vehiculo_id
    seguro.delete()
    return id_vehiculo


def obtener_seguros(id_vehiculo):
    """Historial de seguros de un vehiculo, del vencimiento mas nuevo al mas viejo."""
    vehiculo = get_object_or_404(Vehiculo, id=id_vehiculo)
    return vehiculo.seguros.all()


def crear_vtv(id_vehiculo, inicio=None, fin=None, costo=None, observaciones=None):
    """Nueva VTV de un vehiculo activo. Cada verificacion es un registro aparte."""
    vehiculo = get_object_or_404(Vehiculo, id=id_vehiculo, activo=True)
    ini, f, monto, obs = _validar_vigencia(inicio, fin, costo, observaciones, "de la VTV")
    return VTV.objects.create(vehiculo=vehiculo, inicio=ini, fin=f, costo=monto, observaciones=obs)


def editar_vtv(id_vtv, inicio=None, fin=None, costo=None, observaciones=None):
    """Corrige una VTV ya cargada."""
    vtv = get_object_or_404(VTV, id=id_vtv)
    ini, f, monto, obs = _validar_vigencia(inicio, fin, costo, observaciones, "de la VTV")
    vtv.inicio, vtv.fin = ini, f
    vtv.costo, vtv.observaciones = monto, obs
    vtv.save()
    return vtv


def eliminar_vtv(id_vtv):
    """Borra una VTV cargada por error. Devuelve el id del vehiculo."""
    vtv = get_object_or_404(VTV, id=id_vtv)
    id_vehiculo = vtv.vehiculo_id
    vtv.delete()
    return id_vehiculo


def obtener_vtvs(id_vehiculo):
    """Historial de VTV de un vehiculo, del vencimiento mas nuevo al mas viejo."""
    vehiculo = get_object_or_404(Vehiculo, id=id_vehiculo)
    return vehiculo.vtvs.all()


def _validar_servis(fecha, costo, observaciones):
    """Valida los datos de un service. La fecha es obligatoria; el resto opcional."""
    dia = _fecha_obligatoria(fecha, "La fecha del servis")
    monto = _decimal_opcional(costo, "El costo del servis", MAX_COSTO)
    obs = _texto_opcional(observaciones, 200, "Las observaciones")
    return dia, monto, obs


def crear_servis(id_vehiculo, fecha=None, costo=None, observaciones=None):
    """Anota un service de un vehiculo activo en una fecha puntual."""
    vehiculo = get_object_or_404(Vehiculo, id=id_vehiculo, activo=True)
    dia, monto, obs = _validar_servis(fecha, costo, observaciones)
    return Servis.objects.create(vehiculo=vehiculo, fecha=dia, costo=monto, observaciones=obs)


def editar_servis(id_servis, fecha=None, costo=None, observaciones=None):
    """Corrige un service ya cargado."""
    servis = get_object_or_404(Servis, id=id_servis)
    dia, monto, obs = _validar_servis(fecha, costo, observaciones)
    servis.fecha, servis.costo, servis.observaciones = dia, monto, obs
    servis.save()
    return servis


def eliminar_servis(id_servis):
    """Borra un service cargado por error. Devuelve el id del vehiculo."""
    servis = get_object_or_404(Servis, id=id_servis)
    id_vehiculo = servis.vehiculo_id
    servis.delete()
    return id_vehiculo


def obtener_servicios(id_vehiculo):
    """Historial de services de un vehiculo, del mas nuevo al mas viejo."""
    vehiculo = get_object_or_404(Vehiculo, id=id_vehiculo)
    return vehiculo.servicios.all()


def _validar_observacion(fecha, texto):
    """Valida una nota libre de vehiculo. La fecha es obligatoria; el texto tambien."""
    dia = _fecha_obligatoria(fecha, "La fecha de la observación")
    nota = _texto_opcional(texto, 250, "La observación")
    if not nota:
        raise ValueError("La observación no puede estar vacía.")
    return dia, nota


def crear_observacion(id_vehiculo, fecha=None, texto=None):
    """Anota una observacion libre sobre un vehiculo activo."""
    vehiculo = get_object_or_404(Vehiculo, id=id_vehiculo, activo=True)
    dia, nota = _validar_observacion(fecha, texto)
    return ObservacionVehiculo.objects.create(vehiculo=vehiculo, fecha=dia, texto=nota)


def editar_observacion(id_observacion, fecha=None, texto=None):
    """Corrige una observacion ya cargada."""
    observacion = get_object_or_404(ObservacionVehiculo, id=id_observacion)
    dia, nota = _validar_observacion(fecha, texto)
    observacion.fecha, observacion.texto = dia, nota
    observacion.save()
    return observacion


def eliminar_observacion(id_observacion):
    """Borra una observacion. Devuelve el id del vehiculo."""
    observacion = get_object_or_404(ObservacionVehiculo, id=id_observacion)
    id_vehiculo = observacion.vehiculo_id
    observacion.delete()
    return id_vehiculo


def obtener_observaciones(id_vehiculo):
    """Historial de observaciones de un vehiculo, de la mas nueva a la mas vieja."""
    vehiculo = get_object_or_404(Vehiculo, id=id_vehiculo)
    return vehiculo.observaciones.all()


def _validar_viaje(id_empleado, id_vehiculo, destinos, inicio_caja, fecha_inicio, fecha_vuelta):
    """
    Centraliza las validaciones de un viaje comun (crear y editar comparten las
    mismas reglas). Devuelve una tupla con los valores ya limpios y convertidos
    (caja_val, destinos_limpios), o lanza ValueError ante el primer dato invalido.
    """
    # 1. El empleado debe existir en la base de datos
    if not Empleado.objects.filter(id=id_empleado).exists():
        raise ValueError("El empleado seleccionado no existe en el sistema.")

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


def crear_viaje(id_empleado, id_vehiculo, destinos, inicio_caja, fecha_inicio, fecha_vuelta=None):
    """
    Crea un viaje (maestro) y sus destinos asociados (detalle) usando una transacción atómica.
    'destinos' debe ser una lista de strings. Ejemplo: ["Buenos Aires", "Rosario"].
    """
    caja_val, destinos_limpios = _validar_viaje(
        id_empleado, id_vehiculo, destinos, inicio_caja, fecha_inicio, fecha_vuelta
    )

    with transaction.atomic():
        # Creamos el viaje (Tabla Maestra)
        nuevo_viaje = Viaje.objects.create(
            empleado_id=id_empleado,
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


def obtener_empleados_activos():
    # Anoto _num_viajes (viajes activos) para que la property total_viajes no
    # dispare una query por cada empleado en el listado de flota. Sumo los tres
    # tipos de viaje. Uso distinct=True en cada Count porque los tres LEFT JOIN
    # generan fan-out y sin el distinct los conteos se multiplicarian entre si.
    return (
        Empleado.objects.filter(activo=True)
        .annotate(_num_viajes=(
            Count("viaje", filter=Q(viaje__activo=True), distinct=True)
            + Count("viajereparto", filter=Q(viajereparto__activo=True), distinct=True)
            + Count("viajecereal", filter=Q(viajecereal__activo=True), distinct=True)
        ))
        .order_by('nombre')
    )


def obtener_vehiculos_activos():
    # El listado se muestra como tarjetas y cada una resume el estado del vehiculo:
    # kilometraje, ultimo vencimiento de seguro y VTV, y fecha del ultimo service.
    # Traigo esos cuatro datos con subconsultas (una sola query, sin N+1) en vez de
    # apoyarme en las properties del modelo, que dispararian una consulta por tarjeta.
    hoy = timezone.localdate()

    # El [:1] con el ordering de cada modelo toma el registro vigente: el seguro y la
    # VTV con el vencimiento mas lejano (-fin), el service mas reciente (-fecha) y la
    # ultima lectura de odometro (-fecha), que es el kilometraje actual del vehiculo.
    ultimo_seguro = Seguro.objects.filter(vehiculo=OuterRef("pk")).values("fin")[:1]
    ultima_vtv = VTV.objects.filter(vehiculo=OuterRef("pk")).values("fin")[:1]
    ultimo_servis = Servis.objects.filter(vehiculo=OuterRef("pk")).values("fecha")[:1]
    km_actual = RegistroKilometraje.objects.filter(vehiculo=OuterRef("pk")).values("kilometros")[:1]

    vehiculos = list(
        Vehiculo.objects.filter(activo=True)
        .annotate(
            _num_viajes=(
                Count("viaje", filter=Q(viaje__activo=True), distinct=True)
                + Count("viajereparto", filter=Q(viajereparto__activo=True), distinct=True)
                + Count("viajecereal", filter=Q(viajecereal__activo=True), distinct=True)
            ),
            _seguro_fin=Subquery(ultimo_seguro, output_field=DateField()),
            _vtv_fin=Subquery(ultima_vtv, output_field=DateField()),
            _servis_fecha=Subquery(ultimo_servis, output_field=DateField()),
            _km_actual=Subquery(km_actual, output_field=DecimalField()),
        )
        .order_by('nombre')
    )

    # Dejo listos, sobre cada instancia, los datos que la tarjeta muestra tal cual:
    # las fechas, el kilometraje (cero si nunca se cargo) y si seguro/VTV estan vencidos.
    for vehiculo in vehiculos:
        vehiculo.seguro_fin = vehiculo._seguro_fin
        vehiculo.vtv_fin = vehiculo._vtv_fin
        vehiculo.servis_fecha = vehiculo._servis_fecha
        vehiculo.km_actual = vehiculo._km_actual or Decimal("0")
        vehiculo.seguro_vencido = bool(vehiculo._seguro_fin and vehiculo._seguro_fin < hoy)
        vehiculo.vtv_vencido = bool(vehiculo._vtv_fin and vehiculo._vtv_fin < hoy)

    return vehiculos


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


def opciones_productos_operaciones():
    """Items para el modal selector_entidad del chip "Producto" del listado.

    Ofrece solo lo que realmente aparece en alguna operacion activa, asi el filtro
    nunca lista un producto que no daria resultados. Cada linea de operacion apunta
    a un producto de catalogo o a un articulo a granel (nunca a los dos), por eso el
    id viaja como token: "p<id>" para el producto y "g<id>" para el articulo por kg,
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
        nombre = f"{cotizacion.articulo} (por kg)"
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
    return f"{cotizacion.articulo} (por kg)" if cotizacion else ""


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


def obtener_viajes():
    return Viaje.objects.filter(activo=True).select_related('empleado', 'vehiculo').prefetch_related('destinos').order_by('-fecha_inicio', '-id')


def obtener_datos_viaje(id_viaje):
    # Trae un viaje comun activo con sus relaciones listas para la vista de informacion.
    # Mismo patron que obtener_datos_viaje_cereal / _reparto: la vista no toca el ORM directo.
    return get_object_or_404(
        Viaje.objects.select_related("empleado", "vehiculo").prefetch_related("destinos", "detalle_gastos"),
        id=id_viaje,
        activo=True,
    )


def editar_viaje(id_viaje, id_empleado, id_vehiculo, destinos, inicio_caja, fecha_inicio, fecha_vuelta):
    caja_val, destinos_limpios = _validar_viaje(
        id_empleado, id_vehiculo, destinos, inicio_caja, fecha_inicio, fecha_vuelta
    )

    with transaction.atomic():
        viaje = get_object_or_404(Viaje, id=id_viaje)

        viaje.empleado_id = id_empleado
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


# --- Gastos de viaje (miel/cera, cereal y reparto) ---
#
# Los tres modelos de gasto heredan de GastoBase, asi que las reglas son las
# mismas y viven una sola vez aca. Lo unico que cambia es la tabla, que entra
# por parametro.

def _validar_gasto_viaje(modelo, tipo_gasto, monto):
    """Reglas comunes a los gastos de cualquier viaje. Devuelve los valores limpios."""
    tipos_validos = dict(modelo._meta.get_field("gasto").choices).keys()
    if tipo_gasto not in tipos_validos:
        raise ValueError(f"El tipo de gasto '{tipo_gasto}' no es válido.")

    try:
        monto_val = int(monto)
        if monto_val <= 0:
            raise ValueError()
    except (ValueError, TypeError):
        raise ValueError("El monto debe ser un número entero positivo mayor a 0.")

    return tipo_gasto, monto_val


# Como cada tabla de gasto cuelga de un viaje distinto, este mapa dice, para cada
# modelo de gasto: el atributo del gasto que apunta al viaje, el campo de la carga
# que guarda ese mismo viaje, y de donde sale la fecha del viaje. Asi la sincro de
# la carga de combustible es una sola, comun a miel/cera, cereal y reparto.
_CONFIG_CARGA_GASTO = {
    "Gasto": ("viaje", "viaje", "fecha_inicio"),
    "GastoViajeReparto": ("viaje_reparto", "viaje_reparto", "fecha_viaje_reparto"),
    "GastoViajeCereal": ("viaje_cereal", "viaje_cereal", "fecha_viaje_cereal"),
}


def _sincronizar_carga_combustible(gasto, id_estacion, litros, pagada):
    """Mantiene al dia la carga de combustible que representa un gasto de viaje.

    Un gasto de tipo Combustible tiene, ademas del monto, una carga en una estacion
    de servicio (con litros y estado de pago). Empleado, vehiculo y fecha salen del
    viaje, no se piden de nuevo. Si el gasto deja de ser Combustible, la carga que
    tenia se da de baja.
    """
    attr_gasto_viaje, campo_carga_viaje, attr_fecha = _CONFIG_CARGA_GASTO[type(gasto).__name__]
    viaje = getattr(gasto, attr_gasto_viaje)
    carga = gasto.carga_combustible

    if gasto.gasto != "Combustible":
        # Cambio de tipo: la carga que hubiera quedado ya no corresponde.
        if carga is not None:
            carga.activa = False
            carga.save(update_fields=["activa"])
            gasto.carga_combustible = None
            gasto.save(update_fields=["carga_combustible"])
        return

    if not id_estacion:
        raise ValueError("Elegí una estación de servicio para el gasto de combustible.")
    estacion = get_object_or_404(EstacionDeServicio, id=id_estacion, activa=True)
    cantidad = _decimal_opcional(litros, "Los litros de la carga")
    fecha_viaje = getattr(viaje, attr_fecha)

    if carga is None:
        carga = CargaCombustible.objects.create(
            estacion=estacion, empleado=viaje.empleado, vehiculo=viaje.vehiculo,
            fecha=fecha_viaje, monto=gasto.monto, litros=cantidad, pagada=bool(pagada),
            **{campo_carga_viaje: viaje},
        )
        gasto.carga_combustible = carga
        gasto.save(update_fields=["carga_combustible"])
    else:
        carga.estacion, carga.monto, carga.litros = estacion, gasto.monto, cantidad
        carga.pagada, carga.fecha, carga.activa = bool(pagada), fecha_viaje, True
        carga.empleado, carga.vehiculo = viaje.empleado, viaje.vehiculo
        carga.save()
    return carga


def editar_gasto_viaje(modelo, id_gasto, tipo_gasto, monto, id_estacion=None, litros=None, pagada=False):
    """Corrige el tipo y el monto de un gasto ya cargado.

    La fecha no se toca: es auto_now_add, queda la del dia en que se registro.
    Al guardar, los totales del viaje (caja, subtotal, pago del empleado,
    ganancia) se recalculan solos, porque son properties derivadas de la suma
    de gastos. Si el gasto es de combustible, se sincroniza su carga.
    """
    tipo_val, monto_val = _validar_gasto_viaje(modelo, tipo_gasto, monto)
    with transaction.atomic():
        # Bloqueo la fila del gasto: sincronizar la carga es un check-then-create (si el
        # gasto todavia no tiene carga, la crea) encadenado con varios save. Sin el lock,
        # dos ediciones concurrentes del mismo gasto a Combustible leen ambas carga=None
        # y crean dos CargaCombustible en la estacion. La transaccion ademas deja el par
        # gasto/carga consistente: si la sincro falla a mitad, no queda un gasto guardado
        # sin su carga vinculada.
        gasto = get_object_or_404(modelo.objects.select_for_update(), id=id_gasto)
        gasto.gasto, gasto.monto = tipo_val, monto_val
        gasto.save()
        _sincronizar_carga_combustible(gasto, id_estacion, litros, pagada)
    return gasto


def eliminar_gasto_viaje(modelo, id_gasto):
    """Borrado de verdad y no logico, igual que el gasto de una casa.

    Un gasto mal cargado no es historia y no tiene nada colgando que se pierda
    al borrarlo, asi que no necesita la baja logica del resto del sistema. Si tenia
    una carga de combustible asociada, se da de baja para que no siga en la estacion.
    """
    with transaction.atomic():
        # Bloqueo el gasto para serializar contra una edicion concurrente del mismo
        # registro y para que dar de baja la carga y borrar el gasto sean un solo paso.
        gasto = get_object_or_404(modelo.objects.select_for_update(), id=id_gasto)
        carga = gasto.carga_combustible
        if carga is not None:
            carga.activa = False
            carga.save(update_fields=["activa"])
        gasto.delete()


def crear_gasto(id_viaje, tipo_gasto, monto, id_estacion=None, litros=None, pagada=False):
    viaje = get_object_or_404(Viaje, id=id_viaje)
    tipo_gasto, monto_val = _validar_gasto_viaje(Gasto, tipo_gasto, monto)

    with transaction.atomic():
        # El alta y la sincro de la carga van juntas: si el gasto es de combustible y
        # falta la estacion (o cualquier dato de la carga), _sincronizar_carga_combustible
        # corta, y la transaccion revierte el gasto para no dejarlo huerfano sin su carga.
        nuevo_gasto = Gasto.objects.create(
            viaje=viaje,
            gasto=tipo_gasto,
            monto=monto_val
        )
        _sincronizar_carga_combustible(nuevo_gasto, id_estacion, litros, pagada)
    return nuevo_gasto


# --- Ingresos a la caja del viaje (transferencia al chofer) ---
#
# Dinero que entra a la caja por fuera de las ventas. Es mas simple que un gasto:
# no tiene tipo ni carga de combustible, solo un monto. Al guardar, el Total
# restante del viaje se recalcula solo, porque final_caja suma total_ingresos.

def _validar_monto_ingreso(monto):
    """Un ingreso a caja es siempre un entero positivo, igual que un gasto."""
    try:
        monto_val = int(monto)
        if monto_val <= 0:
            raise ValueError()
    except (ValueError, TypeError):
        raise ValueError("El monto debe ser un número entero positivo mayor a 0.")
    return monto_val


def crear_ingreso_caja(id_viaje, monto):
    viaje = get_object_or_404(Viaje, id=id_viaje)
    monto_val = _validar_monto_ingreso(monto)
    return IngresoCaja.objects.create(viaje=viaje, monto=monto_val)


def editar_ingreso_caja(id_ingreso, monto):
    """Corrige el monto de un ingreso ya cargado. La fecha no se toca."""
    monto_val = _validar_monto_ingreso(monto)
    ingreso = get_object_or_404(IngresoCaja, id=id_ingreso)
    ingreso.monto = monto_val
    ingreso.save(update_fields=["monto"])
    return ingreso


def eliminar_ingreso_caja(id_ingreso):
    """Borrado de verdad: un ingreso mal cargado no es historia y no cuelga nada."""
    ingreso = get_object_or_404(IngresoCaja, id=id_ingreso)
    ingreso.delete()


# --- Devolucion del sobrante de la caja (miel/cera) ---
#
# Cuando la caja de un viaje cierra con sobrante (final_caja > 0), el chofer tiene
# esa plata fisica. Aca se registra que hizo con ella: la devolvio toda (no queda
# nada pendiente) o devolvio una parte y se quedo con el resto. Lo que se queda no
# vuelve a la empresa: cuenta como plata que ya cobro, asi que se anota como un
# pago del empleado (PagosEmpleados con origen "devolucion") y figura en su cuenta
# corriente, diferenciado de los pagos que se cargan a mano.


def _validar_monto_devuelto(monto, sobrante):
    """Valida cuanto devolvio el chofer en una devolucion parcial.

    Tiene que ser un entero entre 0 y el sobrante, sin llegar a el: devolver todo
    es la otra opcion ("Devolvió todo"), no una parcial. Cero es valido: el chofer
    no devolvio nada y se quedo con todo el sobrante.
    """
    try:
        monto_val = int(monto)
    except (ValueError, TypeError):
        raise ValueError("El monto devuelto debe ser un número entero.")
    if monto_val < 0:
        raise ValueError("El monto devuelto no puede ser negativo.")
    if monto_val >= sobrante:
        raise ValueError(
            'Lo devuelto tiene que ser menor al sobrante. Si devolvió todo, usá "Devolvió todo".'
        )
    return monto_val


def _limpiar_devolucion(viaje):
    """Deja el viaje sin devolucion registrada y borra el pago que la respaldaba."""
    if viaje.pago_devolucion_id:
        viaje.pago_devolucion.delete()  # SET_NULL deja el vinculo en null solo
    viaje.pago_devolucion = None
    viaje.devolucion_estado = Viaje.DEVOLUCION_SIN_REGISTRAR
    viaje.monto_devuelto = 0
    viaje.sobrante_devolucion = 0
    viaje.save(update_fields=[
        "pago_devolucion", "devolucion_estado", "monto_devuelto", "sobrante_devolucion",
    ])


def registrar_devolucion_caja(id_viaje, estado, monto_devuelto=None):
    """Registra que hizo el chofer con el sobrante de la caja del viaje.

    - estado "" (sin registrar): borra lo que hubiera cargado y su pago.
    - estado "total": devolvio todo el sobrante. No genera pago.
    - estado "parcial": devolvio 'monto_devuelto' y se quedo con el resto, que se
      registra como un pago del empleado (lo que retuvo = sobrante - devuelto).

    El sobrante se toma de final_caja en el momento y queda congelado en
    sobrante_devolucion, asi el registro no se descuadra si despues cambian las
    operaciones o los gastos.
    """
    viaje = get_object_or_404(Viaje, id=id_viaje, activo=True)

    if estado not in (Viaje.DEVOLUCION_SIN_REGISTRAR, Viaje.DEVOLUCION_TOTAL, Viaje.DEVOLUCION_PARCIAL):
        raise ValueError("El estado de la devolución no es válido.")

    with transaction.atomic():
        if estado == Viaje.DEVOLUCION_SIN_REGISTRAR:
            _limpiar_devolucion(viaje)
            return viaje

        sobrante = viaje.final_caja
        if sobrante <= 0:
            raise ValueError("No hay sobrante en la caja para registrar una devolución.")

        if estado == Viaje.DEVOLUCION_TOTAL:
            devuelto = sobrante
            retenido = 0
        else:  # parcial
            devuelto = _validar_monto_devuelto(monto_devuelto, sobrante)
            retenido = sobrante - devuelto

        if retenido > 0:
            # El chofer se quedo con plata: nace o se actualiza el pago del empleado.
            pago = viaje.pago_devolucion
            if pago is None:
                pago = PagosEmpleados.objects.create(
                    empleado=viaje.empleado,
                    fecha=viaje.fecha_vuelta or timezone.localdate(),
                    monto=retenido,
                    observaciones=f"Devolución de caja — viaje #{viaje.id}",
                    origen=PagosEmpleados.ORIGEN_DEVOLUCION,
                )
                viaje.pago_devolucion = pago
            else:
                # Reescribo el monto y me aseguro empleado/origen; fecha y
                # observacion no las piso, por si se corrigieron a mano.
                pago.empleado = viaje.empleado
                pago.monto = retenido
                pago.origen = PagosEmpleados.ORIGEN_DEVOLUCION
                pago.save(update_fields=["empleado", "monto", "origen"])
        elif viaje.pago_devolucion_id:
            # Devolvio todo: si venia de una parcial, el pago ya no corresponde.
            viaje.pago_devolucion.delete()
            viaje.pago_devolucion = None

        viaje.devolucion_estado = estado
        viaje.monto_devuelto = devuelto
        viaje.sobrante_devolucion = sobrante
        viaje.save(update_fields=[
            "devolucion_estado", "monto_devuelto", "sobrante_devolucion", "pago_devolucion",
        ])

    return viaje


# --- Viajes de cereales ---

def _validar_viaje_cereal(id_cliente, id_empleado, id_vehiculo, tipo_cereal, codigo_trazabilidad,
                          toneladas, precio_tonelada, porcentaje_empleado, fecha_viaje_cereal, destinos,
                          dadora_carga, dadora_tipo_cobro, dadora_valor, numero_factura=None):
    """
    Centraliza las validaciones de un viaje de cereal (crear y editar comparten las
    mismas reglas). Devuelve una tupla con los valores ya limpios y convertidos,
    listos para persistir, o lanza ValueError ante el primer dato invalido.
    """
    # 1. El cliente es opcional (el modelo permite null). Si se informa, debe existir y estar activo.
    if id_cliente and not Cliente.objects.filter(id=id_cliente, activo=True).exists():
        raise ValueError("El cliente seleccionado no existe en el sistema.")

    # 2. El empleado debe existir en la base de datos
    if not Empleado.objects.filter(id=id_empleado).exists():
        raise ValueError("El empleado seleccionado no existe en el sistema.")

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

    """
    5.b. Numero de factura: opcional. Si viene vacio queda en None (viajes sin
    factura asociada). Si viene, solo numeros de hasta 20 digitos, conservando
    los ceros a la izquierda al guardarse como texto (mismo criterio que el CTG).
    """
    factura_limpia = (numero_factura or "").strip()
    if not factura_limpia:
        factura_val = None
    elif not REGEX_FACTURA.match(factura_limpia):
        raise ValueError("El numero de factura debe ser numerico y tener hasta 20 digitos.")
    else:
        factura_val = factura_limpia

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

    # 8. Porcentaje del empleado: opcional. Si no se carga queda en 0; si viene, debe ser 1 a 100
    if porcentaje_empleado in (None, ""):
        porcentaje_val = 0
    else:
        try:
            porcentaje_val = int(porcentaje_empleado)
            if porcentaje_val < 1 or porcentaje_val > 100:
                raise ValueError()
        except (ValueError, TypeError):
            raise ValueError("El porcentaje del empleado debe ser un numero entero entre 1 y 100.")

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

    # 11. Dadora de carga: opcional. Si no se informa el nombre, el viaje no tuvo
    #     dadora y el tipo de cobro y el valor quedan neutros. Si se informa, hay
    #     que decir como cobra (porcentaje o por tonelada) y con que valor.
    dadora_nombre = (dadora_carga or "").strip()
    if not dadora_nombre:
        dadora_tipo_val = ""
        dadora_valor_val = 0
    else:
        if not (3 <= len(dadora_nombre) <= 60) or not REGEX_TEXTO_NUMEROS.match(dadora_nombre):
            raise ValueError("El nombre de la dadora de carga debe tener entre 3 y 60 caracteres "
                             "(solo letras y numeros).")

        tipos_dadora = dict(ViajeCereal.COBROS_DADORA).keys()
        if dadora_tipo_cobro not in tipos_dadora:
            raise ValueError("Debe indicar como cobra la dadora de carga (porcentaje o por tonelada).")
        dadora_tipo_val = dadora_tipo_cobro

        try:
            dadora_valor_val = int(dadora_valor)
        except (ValueError, TypeError):
            raise ValueError("El valor que cobra la dadora de carga debe ser un numero entero positivo.")

        if dadora_tipo_val == "porcentaje":
            if dadora_valor_val < 1 or dadora_valor_val > 100:
                raise ValueError("El porcentaje de la dadora de carga debe ser un numero entero entre 1 y 100.")
        elif dadora_tipo_val == "tonelada":
            # Es una cantidad de toneladas que despues se valua al precio del viaje.
            if dadora_valor_val < 1 or dadora_valor_val > 2147483647:
                raise ValueError("La cantidad de toneladas de la dadora de carga debe ser un numero entero positivo.")
        else:  # efectivo: un monto en pesos
            if dadora_valor_val < 1 or dadora_valor_val > 2147483647:
                raise ValueError("El monto en efectivo de la dadora de carga debe ser un numero entero positivo.")

    return (codigo_limpio, toneladas_val, precio_val, porcentaje_val, destinos_limpios,
            dadora_nombre, dadora_tipo_val, dadora_valor_val, factura_val)


def crear_viaje_cereal(id_cliente, id_empleado, id_vehiculo, tipo_cereal, codigo_trazabilidad,
                       toneladas, precio_tonelada, porcentaje_empleado, fecha_viaje_cereal, destinos,
                       dadora_carga=None, dadora_tipo_cobro=None, dadora_valor=None,
                       pagado=False, numero_factura=None):
    """
    Crea un viaje de cereal (maestro) y sus destinos asociados (detalle) en una
    transaccion atomica. 'destinos' es una lista de strings.

    'pagado' es el cobro del flete: la empresa no acepta pagos parciales, asi que
    alcanza con el booleano (o esta cobrado o no lo esta). Por defecto nace impago.
    """
    (codigo, toneladas_val, precio_val, porcentaje_val, destinos_limpios,
     dadora_nombre, dadora_tipo_val, dadora_valor_val, factura_val) = _validar_viaje_cereal(
        id_cliente, id_empleado, id_vehiculo, tipo_cereal, codigo_trazabilidad,
        toneladas, precio_tonelada, porcentaje_empleado, fecha_viaje_cereal, destinos,
        dadora_carga, dadora_tipo_cobro, dadora_valor, numero_factura
    )

    with transaction.atomic():
        nuevo_viaje_cereal = ViajeCereal.objects.create(
            cliente_id=id_cliente or None,
            empleado_id=id_empleado,
            vehiculo_id=id_vehiculo,
            tipo_cereal=tipo_cereal,
            codigo_trazabilidad_granos=codigo,
            numero_factura=factura_val,
            toneladas=toneladas_val,
            precio_tonelada=precio_val,
            porcentaje_empleado=porcentaje_val,
            fecha_viaje_cereal=fecha_viaje_cereal,
            dadora_carga=dadora_nombre,
            dadora_tipo_cobro=dadora_tipo_val,
            dadora_valor=dadora_valor_val,
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
        .select_related("cliente", "empleado", "vehiculo")
        .prefetch_related("destinos")
        .order_by("-fecha_viaje_cereal", "-id")
    )


def obtener_viajes_cereal_de_cliente(cliente):
    """Fletes de cereal hechos a nombre de un cliente, del mas nuevo al mas viejo.

    Solo los activos: un viaje dado de baja no es historial del cliente sino un
    registro borrado. Los destinos vienen por prefetch porque la tabla los muestra
    como ruta, y sin eso serian tantas consultas extra como filas.

    Desempato por id descendente: varios fletes en la misma fecha son lo normal y,
    sin el desempate, el orden entre ellos lo decide la base y un mismo viaje puede
    aparecer en dos paginas distintas o en ninguna.
    """
    return (
        ViajeCereal.objects.filter(cliente=cliente, activo=True)
        .prefetch_related("destinos")
        .order_by("-fecha_viaje_cereal", "-id")
    )


def obtener_resumen_cereal(viajes):
    """Totales para las tarjetas de resumen de la vista de viajes de cereal.

    'viajes' es el listado ya filtrado (texto, fecha), de modo que las tarjetas
    reflejan los mismos filtros que la tabla. Se calcula sobre txdo ese conjunto,
    no solo la pagina visible.

    Total   = suma de (toneladas * precio_tonelada) de cada viaje (total_bruto).
    Gastos  = suma de los gastos de cada viaje MAS el pago al empleado de cada uno.
    Ganancia = (total + 21%) - gastos.

    El pago al empleado no es un aggregate plano: depende del subtotal por viaje
    (bruto - gastos de ese viaje) con un tope en 0 (si los gastos superan al
    bruto el empleado no aporta plata). Por eso anoto los gastos de cada viaje con
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
        .values("_bruto", "_gastos", "precio_tonelada", "porcentaje_empleado",
                "dadora_carga", "dadora_tipo_cobro", "dadora_valor")
    )

    total = Decimal(0)
    gastos = Decimal(0)
    for v in viajes:
        bruto = v["_bruto"] or Decimal(0)
        gastos_viaje = v["_gastos"] or 0

        # Comision de la dadora (mismo criterio que la property costo_dadora del
        # modelo): se calcula sobre la facturacion (bruto), antes que los gastos.
        # Un porcentaje del bruto, un fijo por tonelada, o un monto en efectivo.
        if not v["dadora_carga"]:
            costo_dadora = Decimal(0)
        elif v["dadora_tipo_cobro"] == "porcentaje":
            costo_dadora = bruto * v["dadora_valor"] / 100
        elif v["dadora_tipo_cobro"] == "tonelada":
            costo_dadora = v["dadora_valor"] * v["precio_tonelada"]
        elif v["dadora_tipo_cobro"] == "efectivo":
            costo_dadora = Decimal(v["dadora_valor"])
        else:
            costo_dadora = Decimal(0)

        subtotal = bruto - costo_dadora - gastos_viaje
        base = subtotal if subtotal > 0 else Decimal(0)
        pago_empleado = base * v["porcentaje_empleado"] / 100
        total += bruto
        gastos += gastos_viaje + costo_dadora + pago_empleado

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
        ViajeCereal.objects.select_related("cliente", "empleado", "vehiculo")
        .prefetch_related("destinos", "detalle_gastos"),
        id=id_viaje_cereal,
        activo=True,
    )


def editar_viaje_cereal(id_viaje_cereal, id_cliente, id_empleado, id_vehiculo, tipo_cereal, codigo_trazabilidad,
                        toneladas, precio_tonelada, porcentaje_empleado, fecha_viaje_cereal, destinos,
                        dadora_carga=None, dadora_tipo_cobro=None, dadora_valor=None,
                        pagado=None, numero_factura=None):
    # 'pagado' llega en None cuando quien edita no puede tocar el cobro (no staff):
    # en ese caso el estado de pago queda como estaba, no se pisa con un False.
    (codigo, toneladas_val, precio_val, porcentaje_val, destinos_limpios,
     dadora_nombre, dadora_tipo_val, dadora_valor_val, factura_val) = _validar_viaje_cereal(
        id_cliente, id_empleado, id_vehiculo, tipo_cereal, codigo_trazabilidad,
        toneladas, precio_tonelada, porcentaje_empleado, fecha_viaje_cereal, destinos,
        dadora_carga, dadora_tipo_cobro, dadora_valor, numero_factura
    )

    with transaction.atomic():
        viaje_cereal = get_object_or_404(ViajeCereal, id=id_viaje_cereal)

        viaje_cereal.cliente_id = id_cliente or None
        viaje_cereal.empleado_id = id_empleado
        viaje_cereal.vehiculo_id = id_vehiculo
        viaje_cereal.tipo_cereal = tipo_cereal
        viaje_cereal.codigo_trazabilidad_granos = codigo
        viaje_cereal.numero_factura = factura_val
        viaje_cereal.toneladas = toneladas_val
        viaje_cereal.precio_tonelada = precio_val
        viaje_cereal.porcentaje_empleado = porcentaje_val
        viaje_cereal.fecha_viaje_cereal = fecha_viaje_cereal
        viaje_cereal.dadora_carga = dadora_nombre
        viaje_cereal.dadora_tipo_cobro = dadora_tipo_val
        viaje_cereal.dadora_valor = dadora_valor_val
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


def crear_gasto_viaje_cereal(id_viaje_cereal, tipo_gasto, monto, id_estacion=None, litros=None, pagada=False):
    # Mismo patron que crear_gasto (viajes comunes), pero sobre la tabla GastoViajeCereal.
    # Cada gasto cargado recalcula automaticamente el subtotal y el pago del empleado, porque
    # esas propiedades del modelo se derivan de la suma de gastos del viaje.
    viaje_cereal = get_object_or_404(ViajeCereal, id=id_viaje_cereal)
    tipo_gasto, monto_val = _validar_gasto_viaje(GastoViajeCereal, tipo_gasto, monto)

    with transaction.atomic():
        # Igual que crear_gasto: alta y sincro de la carga en una sola transaccion para
        # no dejar un gasto de combustible huerfano si falta algun dato de la carga.
        nuevo_gasto = GastoViajeCereal.objects.create(
            viaje_cereal=viaje_cereal,
            gasto=tipo_gasto,
            monto=monto_val
        )
        _sincronizar_carga_combustible(nuevo_gasto, id_estacion, litros, pagada)
    return nuevo_gasto


# --- Catalogo de destinos de reparto ---

def obtener_destinos_reparto():
    # Solo los destinos vigentes (borrado logico), ordenados alfabeticamente por el Meta
    return DestinoViajeReparto.objects.filter(activo=True)


def _validar_destino_reparto(localidad_destino, valor_viaje):
    """Valida el nombre y la tarifa de un destino. Devuelve ambos ya limpios."""
    localidad = (localidad_destino or "").strip()

    if not (3 <= len(localidad) <= 60) or not REGEX_TEXTO_NUMEROS.match(localidad):
        raise ValueError("El nombre del destino debe tener entre 3 y 60 caracteres (solo letras y numeros).")

    return localidad, _limpiar_valor_viaje(valor_viaje)


def _limpiar_valor_viaje(valor_viaje):
    """Deja el valor de un viaje de reparto listo para un DecimalField(12, 2).

    Acepta centavos: la tarifa puede no ser redonda. Recorto a dos decimales y
    corto los montos que no entran en el campo antes de que los rechace la base.
    """
    try:
        valor_val = Decimal(str(valor_viaje).strip().replace(",", "."))
    except (InvalidOperation, AttributeError, TypeError):
        raise ValueError("El valor del viaje debe ser un numero positivo.")

    # is_finite() descarta el "nan" y el "inf", que Decimal acepta como texto
    # pero despues comparan False contra cualquier limite
    if not valor_val.is_finite() or valor_val <= 0 or valor_val >= Decimal("10000000000"):
        raise ValueError("El valor del viaje debe ser un numero positivo.")

    # Redondear a centavos puede dejar en cero un monto como "0,004"
    valor_val = valor_val.quantize(Decimal("0.01"))
    if valor_val <= 0:
        raise ValueError("El valor del viaje debe ser un numero positivo.")

    return valor_val


def crear_destino_reparto(localidad_destino, valor_viaje):
    """Da de alta un destino del catalogo.

    Si el nombre ya existe pero esta dado de baja, revive ese registro con la tarifa
    nueva en lugar de fallar: el nombre es unico en la base y asi el destino vuelve
    con su historial de viajes intacto.
    """
    localidad, valor_val = _validar_destino_reparto(localidad_destino, valor_viaje)

    existente = DestinoViajeReparto.objects.filter(localidad_destino__iexact=localidad).first()
    if existente:
        if existente.activo:
            raise ValueError(f"Ya existe un destino llamado '{existente.localidad_destino}'.")
        existente.localidad_destino = localidad
        existente.valor_viaje = valor_val
        existente.activo = True
        existente.save()
        return existente

    return DestinoViajeReparto.objects.create(localidad_destino=localidad, valor_viaje=valor_val)


def editar_destino_reparto(id_destino, localidad_destino, valor_viaje):
    """Cambia el nombre y la tarifa de un destino.

    La tarifa nueva rige para los repartos que se carguen de ahora en mas: cada viaje
    guarda su propia copia del monto, asi que actualizar el precio no reescribe la
    plata de los viajes ya registrados.
    """
    destino = get_object_or_404(DestinoViajeReparto, id=id_destino)
    localidad, valor_val = _validar_destino_reparto(localidad_destino, valor_viaje)

    if DestinoViajeReparto.objects.filter(localidad_destino__iexact=localidad).exclude(id=destino.id).exists():
        raise ValueError(f"Ya existe otro destino llamado '{localidad}'.")

    destino.localidad_destino = localidad
    destino.valor_viaje = valor_val
    destino.save()
    return destino


def eliminar_destino_reparto(id_destino):
    # Borrado logico: sale del selector de nuevos repartos, pero los viajes
    # que ya lo usaban lo siguen mostrando
    destino = get_object_or_404(DestinoViajeReparto, id=id_destino)
    destino.activo = False
    destino.save()
    return destino


def _sumar_viaje_a_destino(id_destino):
    # Uso update() con F() en vez de leer-y-guardar para que el incremento lo haga
    # la base y dos altas simultaneas no se pisen el contador.
    if id_destino:
        DestinoViajeReparto.objects.filter(id=id_destino).update(cant_viajes=F("cant_viajes") + 1)


def _restar_viaje_a_destino(id_destino):
    # El filtro cant_viajes__gt=0 es la red de seguridad: si el contador ya estaba en
    # cero (un destino creado a mano, por ejemplo) no lo deja quedar en negativo.
    if id_destino:
        DestinoViajeReparto.objects.filter(id=id_destino, cant_viajes__gt=0).update(cant_viajes=F("cant_viajes") - 1)


# --- Viajes de reparto (Mercado Libre) ---

def _validar_viaje_reparto(id_empleado, id_vehiculo, gasto_combustible,
                           costo_empleado, valor_viaje, fecha_viaje_reparto, id_destino):
    """
    Centraliza las validaciones de un viaje de reparto (crear y editar comparten las
    mismas reglas). Devuelve una tupla con los valores ya limpios y convertidos,
    listos para persistir, o lanza ValueError ante el primer dato invalido.
    """
    # 1. El empleado debe existir en la base de datos
    if not Empleado.objects.filter(id=id_empleado).exists():
        raise ValueError("El empleado seleccionado no existe en el sistema.")

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

    # 5. Destino: tiene que ser uno del catalogo. Acepto tambien los dados de baja
    # porque al editar un reparto viejo su destino puede ya no estar vigente.
    destino = DestinoViajeReparto.objects.filter(id=id_destino).first()
    if destino is None:
        raise ValueError("El destino seleccionado no existe en el sistema.")

    # 6. Valor del viaje: numero positivo (admite centavos) dentro del limite de la BD.
    # Si el formulario no lo manda, vale la tarifa del destino; si lo manda, gana lo
    # que escribio el usuario, porque un reparto puntual puede haberse cobrado distinto.
    if valor_viaje in (None, ""):
        valor_viaje = destino.valor_viaje
    valor_val = _limpiar_valor_viaje(valor_viaje)

    # 7. Fecha del reparto: obligatoria y con formato YYYY-MM-DD
    try:
        datetime.strptime(fecha_viaje_reparto, "%Y-%m-%d")
    except (ValueError, TypeError):
        raise ValueError("La fecha del reparto debe tener el formato valido YYYY-MM-DD.")

    return gasto_val, costo_val, valor_val, destino


def crear_viaje_reparto(id_empleado, id_vehiculo, gasto_combustible, costo_empleado,
                        valor_viaje, fecha_viaje_reparto, id_destino, pagado=False):
    """
    Crea un viaje de reparto. El destino se elige del catalogo (DestinoViajeReparto)
    y el viaje guarda su propia copia del valor cobrado, para que cambiar la tarifa
    del catalogo mas adelante no altere la plata de los viajes ya cargados.

    'pagado' es el cobro del reparto: la empresa no acepta pagos parciales, asi que
    alcanza con el booleano (o esta cobrado o no lo esta). Por defecto nace impago.
    """
    gasto_val, costo_val, valor_val, destino = _validar_viaje_reparto(
        id_empleado, id_vehiculo, gasto_combustible, costo_empleado,
        valor_viaje, fecha_viaje_reparto, id_destino
    )

    with transaction.atomic():
        nuevo_viaje_reparto = ViajeReparto.objects.create(
            empleado_id=id_empleado,
            vehiculo_id=id_vehiculo,
            destino=destino,
            gasto_combustible_viaje_reparto=gasto_val,
            costo_empleado=costo_val,
            valor_viaje=valor_val,
            fecha_viaje_reparto=fecha_viaje_reparto,
            pagado=bool(pagado),
            # Si nace cobrado, el momento del cobro es el del alta
            fecha_pago=timezone.now() if pagado else None,
        )
        _sumar_viaje_a_destino(destino.id)

    return nuevo_viaje_reparto


def obtener_viajes_reparto():
    # Solo los viajes activos (borrado logico), con relaciones precargadas para evitar el N+1
    return (
        ViajeReparto.objects.filter(activo=True)
        .select_related("empleado", "vehiculo", "destino")
        .order_by("-fecha_viaje_reparto", "-id")
    )


def obtener_resumen_reparto(viajes):
    """Totales para las tarjetas de resumen de la vista de repartos.

    'viajes' es el listado ya filtrado (texto, fecha), de modo que las tarjetas
    reflejan los mismos filtros que la tabla. Se calcula sobre txdo ese conjunto,
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
        # El valor del viaje es decimal: el cero del Coalesce va como Decimal para
        # no mezclar tipos en la misma expresion
        total=Coalesce(Sum("valor_viaje"), Decimal("0")),
        combustible=Coalesce(Sum("gasto_combustible_viaje_reparto"), 0),
        empleado=Coalesce(Sum("costo_empleado"), 0),
    )
    gastos_extra = GastoViajeReparto.objects.filter(
        viaje_reparto__in=ids
    ).aggregate(total=Coalesce(Sum("monto"), 0))["total"]

    total = cabecera["total"]
    gastos = cabecera["combustible"] + cabecera["empleado"] + gastos_extra
    total_mas_iva = (total * Decimal("1.21")).quantize(Decimal("0.01"))
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
        ViajeReparto.objects.select_related("empleado", "vehiculo", "destino")
        .prefetch_related("detalle_gastos"),
        id=id_viaje_reparto,
        activo=True,
    )


def crear_gasto_viaje_reparto(id_viaje_reparto, tipo_gasto, monto, id_estacion=None, litros=None, pagada=False):
    # Mismo patron que crear_gasto_viaje_cereal, sobre la tabla GastoViajeReparto.
    # Cada gasto cargado recalcula la ganancia, porque la property del modelo se deriva
    # de la suma de gastos del viaje.
    viaje_reparto = get_object_or_404(ViajeReparto, id=id_viaje_reparto)
    tipo_gasto, monto_val = _validar_gasto_viaje(GastoViajeReparto, tipo_gasto, monto)

    with transaction.atomic():
        # Igual que crear_gasto: alta y sincro de la carga en una sola transaccion para
        # no dejar un gasto de combustible huerfano si falta algun dato de la carga.
        nuevo_gasto = GastoViajeReparto.objects.create(
            viaje_reparto=viaje_reparto,
            gasto=tipo_gasto,
            monto=monto_val
        )
        _sincronizar_carga_combustible(nuevo_gasto, id_estacion, litros, pagada)
    return nuevo_gasto


def editar_viaje_reparto(id_viaje_reparto, id_empleado, id_vehiculo, gasto_combustible,
                         costo_empleado, valor_viaje, fecha_viaje_reparto, id_destino, pagado=None):
    # 'pagado' llega en None cuando quien edita no puede tocar el cobro (no staff):
    # en ese caso el estado de pago queda como estaba, no se pisa con un False.
    gasto_val, costo_val, valor_val, destino = _validar_viaje_reparto(
        id_empleado, id_vehiculo, gasto_combustible, costo_empleado,
        valor_viaje, fecha_viaje_reparto, id_destino
    )

    with transaction.atomic():
        # Bloqueo la fila: la edicion mueve el contador de viajes entre destinos
        # (resta al anterior, suma al nuevo). Sin el lock, una edicion y un borrado
        # concurrentes leen el mismo destino_anterior y desincronizan cant_viajes.
        viaje_reparto = get_object_or_404(
            ViajeReparto.objects.select_for_update(), id=id_viaje_reparto
        )
        destino_anterior_id = viaje_reparto.destino_id

        viaje_reparto.empleado_id = id_empleado
        viaje_reparto.vehiculo_id = id_vehiculo
        viaje_reparto.destino = destino
        viaje_reparto.gasto_combustible_viaje_reparto = gasto_val
        viaje_reparto.costo_empleado = costo_val
        viaje_reparto.valor_viaje = valor_val
        viaje_reparto.fecha_viaje_reparto = fecha_viaje_reparto
        if pagado is not None:
            _aplicar_estado_pago(viaje_reparto, pagado)
        viaje_reparto.save()

        # El contador sigue al viaje: si cambio de localidad, el destino viejo pierde
        # ese viaje y el nuevo lo gana. Si no cambio, no se toca nada.
        if destino_anterior_id != destino.id:
            _restar_viaje_a_destino(destino_anterior_id)
            _sumar_viaje_a_destino(destino.id)

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
    with transaction.atomic():
        # Bloqueo la fila con select_for_update y leo 'activo' YA bloqueado: un
        # segundo borrado concurrente espera aca y, al desbloquearse tras el commit,
        # encuentra activo=False y sale por el guard. Sin el lock, ambos leian
        # activo=True y descontaban el viaje del destino dos veces (TOCTOU).
        viaje_reparto = get_object_or_404(
            ViajeReparto.objects.select_for_update(), id=id_viaje_reparto
        )

        # Guardo si estaba vigente antes de tocarlo: eliminar dos veces el mismo reparto
        # no tiene que descontar dos viajes del destino.
        estaba_activo = viaje_reparto.activo

        # Borrado logico: lo marco inactivo para no perder el historial
        viaje_reparto.activo = False
        viaje_reparto.save()
        if estaba_activo:
            _restar_viaje_a_destino(viaje_reparto.destino_id)

    return viaje_reparto


# ==========================================================================
#  CUENTA CORRIENTE DEL CLIENTE
# ==========================================================================

# Peso de cada tipo de movimiento cuando varios caen el mismo dia: primero lo que
# se factura y despues lo que se cobra, para que el saldo de la fila lea como la
# historia real del dia y no arranque en negativo.
ORDEN_MOVIMIENTO = {
    "operacion": 0,
    "flete": 1,
    "pago": 2,
    "cobro_flete": 3,
}


def _momento_local(fecha, fin_del_dia):
    """Convierte una fecha suelta en el instante que le corresponde en la zona local.

    Es el arranque (00:00) o el cierre (23:59:59) del dia segun el extremo del
    rango que se este armando.
    """
    momento = datetime.combine(fecha, time.max if fin_del_dia else time.min)
    if settings.USE_TZ:
        return timezone.make_aware(momento, timezone.get_current_timezone())
    return momento


def _acotar_rango(queryset, campo, desde, hasta, es_fecha_hora=True):
    """Acota un queryset a un rango de fechas inclusivo en ambos extremos.

    Los DateTimeField se comparan contra los instantes limite del dia y no con el
    lookup __date: sobre MySQL ese lookup se traduce a CONVERT_TZ(), que devuelve
    NULL si el motor no tiene cargadas las tablas de zonas horarias y deja el
    resumen vacio aunque el cliente tenga movimientos.
    """
    if desde:
        valor = _momento_local(desde, fin_del_dia=False) if es_fecha_hora else desde
        queryset = queryset.filter(**{f"{campo}__gte": valor})
    if hasta:
        valor = _momento_local(hasta, fin_del_dia=True) if es_fecha_hora else hasta
        queryset = queryset.filter(**{f"{campo}__lte": valor})
    return queryset


def _items_operacion(operacion):
    """Lista todos los renglones de una operacion para desplegarlos en el resumen.

    Va completa, sin condensar en un "y N mas": el resumen es el comprobante que
    se le entrega al cliente y tiene que poder verificar cada producto que
    entro o salio, con el importe al que se cerro ese renglon.
    """
    items = []
    for detalle in operacion.detalleoperacion_set.all():
        if detalle.es_granel:
            cantidad = f"{detalle.cantidad:.2f}".rstrip("0").rstrip(".") + " kg"
        else:
            cantidad = f"{detalle.cantidad:.0f}x"
        items.append({
            "texto": f"{cantidad} {detalle.nombre_item}",
            "subtotal": detalle.cantidad * detalle.precio_unitario,
        })
    return items


def obtener_saldo_anterior_cuenta_corriente(cliente, desde):
    """Devuelve el saldo con el que el cliente llega al periodo que se imprime.

    Es todo lo que se movio antes del dia 'desde', condensado en un solo numero:
    el resumen tiene que arrancar de ahi y no de cero, o el saldo final no seria
    lo que el cliente realmente debe. Sin 'desde' no hay historia previa que
    juntar, porque el resumen ya sale desde el primer movimiento.
    """
    if not desde:
        return Decimal(0)
    _, totales = obtener_movimientos_cuenta_corriente(
        cliente, hasta=desde - timedelta(days=1)
    )
    return totales["saldo"]


def obtener_movimientos_cuenta_corriente(cliente, desde=None, hasta=None, saldo_inicial=None):
    """Arma el libro de cuenta corriente del cliente en formato Debe / Haber.

    Criterio de signos, siempre desde la empresa: al Debe va lo que el cliente nos
    debe (ventas y fletes de cereal que le prestamos, mas la plata que le pagamos
    por una compra) y al Haber lo que lo descarga (compras que le hicimos y los
    pagos que nos hizo). Un saldo positivo significa que el cliente debe.

    El saldo arranca en 'saldo_inicial', que es lo que el cliente traia de antes
    del periodo (ver obtener_saldo_anterior_cuenta_corriente). Sin ese dato
    arranca en cero y el resumen refleja solo el movimiento del periodo.

    Devuelve (movimientos, totales); cada movimiento ya trae su saldo acumulado.
    """
    movimientos = []

    # --- Ventas y compras ---
    operaciones = _acotar_rango(
        Operacion.objects.filter(cliente=cliente, activa=True)
        .con_totales()
        .prefetch_related("detalleoperacion_set__producto", "detalleoperacion_set__cotizacion"),
        "fecha", desde, hasta,
    )
    for operacion in operaciones:
        es_venta = operacion.tipo_operacion == "venta"
        monto = Decimal(operacion.monto_total or 0)
        items = _items_operacion(operacion)
        movimientos.append({
            "fecha": timezone.localtime(operacion.fecha).date() if timezone.is_aware(operacion.fecha) else operacion.fecha.date(),
            "comprobante": f"{'Venta' if es_venta else 'Compra'} Nro {str(operacion.id).zfill(5)}",
            # El detalle de la fila queda vacio porque los productos se despliegan
            # abajo, uno por linea; solo se escribe algo si la operacion no tiene
            "detalle": "" if items else "Sin items",
            "items": items,
            "debe": monto if es_venta else Decimal(0),
            "haber": Decimal(0) if es_venta else monto,
            "orden": ORDEN_MOVIMIENTO["operacion"],
        })

    # --- Pagos de esas operaciones ---
    # El pago cancela la deuda en el sentido contrario a la operacion que lo origina:
    # el de una venta nos entra (Haber) y el de una compra nos sale (Debe).
    pagos = _acotar_rango(
        Pago.objects.filter(operacion__cliente=cliente, operacion__activa=True).select_related("operacion"),
        "fecha", desde, hasta,
    )
    for pago in pagos:
        es_venta = pago.operacion.tipo_operacion == "venta"
        etiqueta = "venta" if es_venta else "compra"
        monto = Decimal(pago.monto or 0)
        movimientos.append({
            "fecha": timezone.localtime(pago.fecha).date() if timezone.is_aware(pago.fecha) else pago.fecha.date(),
            "comprobante": "Recibo" if es_venta else "Pago emitido",
            "detalle": f"Pago de {etiqueta} Nro {str(pago.operacion_id).zfill(5)}",
            "items": [],
            "debe": Decimal(0) if es_venta else monto,
            "haber": monto if es_venta else Decimal(0),
            "orden": ORDEN_MOVIMIENTO["pago"],
        })

    # --- Fletes de cereal prestados al cliente ---
    fletes = _acotar_rango(
        ViajeCereal.objects.filter(cliente=cliente, activo=True),
        "fecha_viaje_cereal", desde, hasta, es_fecha_hora=False,
    )
    for flete in fletes:
        toneladas = f"{flete.toneladas:.2f}".rstrip("0").rstrip(".")
        movimientos.append({
            "fecha": flete.fecha_viaje_cereal,
            "comprobante": f"Flete Nro {str(flete.id).zfill(5)}",
            "detalle": f"{flete.tipo_cereal} - {toneladas} tn (CTG {flete.codigo_trazabilidad_granos})",
            "items": [],
            "debe": Decimal(flete.total_bruto or 0),
            "haber": Decimal(0),
            "orden": ORDEN_MOVIMIENTO["flete"],
        })

    # --- Cobros de esos fletes ---
    # El viaje de cereal no tiene tabla de pagos: se cobra entero o no se cobra, asi
    # que el cobro es una sola fila con la fecha en que se sello el pago.
    cobros = _acotar_rango(
        ViajeCereal.objects.filter(cliente=cliente, activo=True, pagado=True, fecha_pago__isnull=False),
        "fecha_pago", desde, hasta,
    )
    for cobro in cobros:
        movimientos.append({
            "fecha": timezone.localtime(cobro.fecha_pago).date() if timezone.is_aware(cobro.fecha_pago) else cobro.fecha_pago.date(),
            "comprobante": "Recibo",
            "detalle": f"Cobro del flete Nro {str(cobro.id).zfill(5)}",
            "items": [],
            "debe": Decimal(0),
            "haber": Decimal(cobro.total_bruto or 0),
            "orden": ORDEN_MOVIMIENTO["cobro_flete"],
        })

    movimientos.sort(key=lambda m: (m["fecha"], m["orden"], m["comprobante"]))

    # Saldo acumulado fila por fila, que es lo que convierte el listado en un libro
    saldo = Decimal(saldo_inicial or 0)
    total_debe = Decimal(0)
    total_haber = Decimal(0)
    for movimiento in movimientos:
        saldo += movimiento["debe"] - movimiento["haber"]
        total_debe += movimiento["debe"]
        total_haber += movimiento["haber"]
        movimiento["saldo"] = saldo

    totales = {"debe": total_debe, "haber": total_haber, "saldo": saldo}
    return movimientos, totales


# ==========================================================================
#  ALQUILERES
# ==========================================================================

def _texto_opcional(valor, maximo, etiqueta):
    """Normaliza un campo de texto que puede venir vacio.

    En alquileres ningun dato es obligatorio, asi que el vacio no es un error:
    se guarda como None para que la base distinga "no lo cargue" de "es un
    string vacio". Lo unico que si valido es que no exceda el largo del modelo.
    """
    texto = str(valor or "").strip()
    if not texto:
        return None
    if len(texto) > maximo:
        raise ValueError(f"{etiqueta} no puede superar los {maximo} caracteres.")
    return texto


def _decimal_opcional(valor, etiqueta, maximo=None):
    """Convierte a Decimal un monto opcional del formulario de alquileres.

    Vacio devuelve None (dato sin cargar). Un texto que no es numero o un valor
    negativo si son errores: prefiero cortar aca con un mensaje claro antes de
    que la base rechace el insert.
    """
    if valor in (None, ""):
        return None

    try:
        numero = Decimal(str(valor).strip().replace(" ", ""))
    except (InvalidOperation, AttributeError):
        raise ValueError(f"{etiqueta} no es un número válido.")

    if numero < 0:
        raise ValueError(f"{etiqueta} no puede ser negativo.")

    numero = numero.quantize(Decimal("0.01"))
    if maximo is not None and numero > maximo:
        raise ValueError(f"{etiqueta} es demasiado grande.")
    return numero


def _entero_opcional(valor, etiqueta, maximo=None):
    """Como _decimal_opcional pero para los campos que no llevan centavos.

    Lo usan el alquiler mensual y la comision de la inmobiliaria, que se pactan
    en numeros redondos. Un valor con coma o punto decimal no se redondea por
    las buenas: corto con un mensaje, porque redondear en silencio cambiaria el
    monto que el usuario cree haber cargado.
    """
    if valor in (None, ""):
        return None

    texto = str(valor).strip().replace(" ", "")
    # El navegador manda "1500.00" cuando el input arranca con un valor viejo de
    # la base; esos ceros no son un decimal cargado a mano y se pueden tirar
    if "." in texto or "," in texto:
        entera, _, decimales = texto.replace(",", ".").partition(".")
        if decimales.strip("0"):
            raise ValueError(f"{etiqueta} tiene que ser un número entero, sin decimales.")
        texto = entera

    try:
        numero = int(texto)
    except ValueError:
        raise ValueError(f"{etiqueta} no es un número válido.")

    if numero < 0:
        raise ValueError(f"{etiqueta} no puede ser negativo.")

    if maximo is not None and numero > maximo:
        raise ValueError(f"{etiqueta} es demasiado grande.")
    return numero


def _parsear_dia(fecha, etiqueta):
    """Convierte a date lo que llega de un <input type="date">, o None si vino vacio."""
    if fecha in (None, ""):
        return None

    if isinstance(fecha, datetime):
        return fecha.date()

    if isinstance(fecha, date):
        return fecha

    try:
        return datetime.strptime(str(fecha).strip(), "%Y-%m-%d").date()
    except (ValueError, TypeError):
        raise ValueError(f"{etiqueta} no es válida.")


def _validar_casa(nombre, localidad, direccion):
    """Limpia y valida los datos de una casa. Devuelve la tupla ya normalizada.

    Son tres campos porque la casa ya no guarda nada del alquiler: el plazo, el
    monto, la comision y el inquilino son del contrato.
    """
    return (_texto_opcional(nombre, 60, "El nombre de la casa"),
            _texto_opcional(localidad, 60, "La localidad"),
            _texto_opcional(direccion, 120, "La dirección"))


# Condiciones que reproducen en SQL lo que Casa.estado_mes calcula en Python.
# Existen para poder filtrar y ordenar el listado por el estado del mes sin
# traer todas las casas a memoria.
#
# Como el alquiler se cobra completo, el estado no compara montos: mira si el
# mes tiene pago o no. Por eso alcanza con el signo de lo cobrado y el precio
# de la casa no entra en la cuenta.
#
# El orden de las condiciones copia el de Casa.estado_mes y no es casual: el
# pago se pregunta primero y le gana al contrato, porque es un hecho de ese mes.
# Si las dos versiones se separan, el chip deja de coincidir con la pildora.
#
# Cuelgan de las anotaciones de con_estado_del_mes y no de campos de la casa:
# son las unicas que saben de que mes estamos hablando. Estar alquilada es tener
# contrato que cubra ese mes, asi que un contrato vencido ya cuenta como libre
# sin necesidad de una condicion aparte.
Q_COBRADA = Q(_pagado_periodo_anotado__gt=0)
Q_PENDIENTE = Q(_contrato_periodo_anotado__isnull=False) & Q(_pagado_periodo_anotado__lte=0)
Q_LIBRE = Q(_contrato_periodo_anotado__isnull=True) & Q(_pagado_periodo_anotado__lte=0)

# Filtros del listado. La clave viaja en la URL y la etiqueta la pinta el chip.
FILTROS_ALQUILERES = {
    "pendientes": Q_PENDIENTE,
    "cobradas": Q_COBRADA,
    "libres": Q_LIBRE,
}


def resolver_periodo(valor):
    """Mes a mostrar en la pantalla, a partir del parametro 'mes' de la URL.

    Se diferencia de _parsear_periodo en que no explota: una URL escrita a mano
    o un enlace viejo no tienen por que romper la pantalla, simplemente caen en
    el mes en curso, que es lo que el usuario esperaba ver al entrar.
    """
    try:
        return _parsear_periodo(valor)
    except ValueError:
        return periodo_actual()


def mes_desplazado(periodo, meses):
    """Corre un periodo hacia adelante o atras. Sirve para las flechas del mes.

    Aritmetica sobre el indice absoluto de mes para no tener que pensar en el
    cambio de año: enero menos uno es diciembre del año anterior.
    """
    indice = periodo.year * 12 + (periodo.month - 1) + meses
    return date(indice // 12, indice % 12 + 1, 1)


def obtener_casas(estado="", periodo=None):
    """Listado de casas vigentes, ya anotado con lo cobrado en el periodo pedido.

    La anotacion viene de arranque porque el listado pinta el estado de cada
    fila: sin ella serian tantas queries como casas haya.

    El orden por defecto no es alfabetico sino por urgencia (pendientes de cobro,
    cobradas y al final las que no estan alquiladas). La pantalla existe para
    responder que falta cobrar este mes, asi que eso va arriba sin que el usuario
    tenga que filtrar; dentro de cada grupo si ordena por nombre.

    Que casas entran en un mes:

    - Las que tienen pago cargado en ese mes, siempre. Un pago es un hecho, asi
      que la casa aparece aunque hoy este dada de baja: si no, la plata cobrada
      desaparecia del total del mes.
    - En el mes en curso y en los que vienen, todas las vigentes. Aunque no tengan
      contrato: es justamente la pantalla donde hay que poder cargarles uno.
    - En los meses pasados, solo las que ya tenian algun contrato empezado. Sin
      esto, una casa cargada hoy reaparece en todos los meses anteriores.

    El vencimiento no saca a la casa del listado, a proposito: sigue existiendo y
    hay que poder verla para renovarla. Lo que cambia es que pasa a "Sin alquilar"
    y deja de sumar a lo pendiente.
    """
    periodo = periodo or periodo_actual()

    vigentes = Q(activa=True)
    if periodo < periodo_actual():
        # Ya tenia contrato si alguno arranco en ese mes o antes; comparo contra el
        # primero del mes siguiente para no perder los que arrancan en el propio mes.
        vigentes &= Q(Exists(
            Contrato.objects.filter(casa=OuterRef("pk"), inicio__lt=mes_desplazado(periodo, 1))
        ))

    casas = Casa.objects.con_estado_del_mes(periodo).filter(Q_COBRADA | vigentes)

    filtro = FILTROS_ALQUILERES.get(estado)
    if filtro is not None:
        casas = casas.filter(filtro)

    return casas.annotate(
        _orden_estado=Case(
            When(Q_PENDIENTE, then=Value(0)),
            When(Q_COBRADA, then=Value(1)),
            default=Value(2),
            output_field=IntegerField(),
        )
    ).order_by("_orden_estado", "nombre", "id")


def obtener_casa(id_casa):
    """Casa vigente con su pago del mes ya anotado, para el perfil."""
    casa = Casa.objects.filter(activa=True).con_estado_del_mes().filter(id=id_casa).first()
    if casa is None:
        raise Http404("La casa no existe o fue dada de baja.")
    return casa


def obtener_datos_casa(id_casa):
    """Datos de la casa en dict, para rellenar el panel de edicion via JSON."""
    try:
        casa = Casa.objects.get(id=id_casa, activa=True)
        return {
            "id": casa.id,
            "nombre": casa.nombre or "",
            "localidad": casa.localidad or "",
            "direccion": casa.direccion or "",
        }
    except Casa.DoesNotExist:
        return None


def crear_casa(nombre=None, localidad=None, direccion=None):
    nombre, localidad, direccion = _validar_casa(nombre, localidad, direccion)
    return Casa.objects.create(nombre=nombre, localidad=localidad, direccion=direccion)


def editar_casa(id_casa, nombre=None, localidad=None, direccion=None):
    casa = get_object_or_404(Casa, id=id_casa)
    casa.nombre, casa.localidad, casa.direccion = _validar_casa(nombre, localidad, direccion)
    casa.save()
    return casa


def eliminar_casa(id_casa):
    # Baja logica, como en el resto del sistema: la casa desaparece de los
    # listados pero conserva su historial de pagos por si hay que consultarlo
    casa = get_object_or_404(Casa, id=id_casa)
    casa.activa = False
    casa.save()
    return casa


# ==========================================================================
#  CONTRATOS
# ==========================================================================

def _fecha_obligatoria(fecha, etiqueta):
    """Como _parsear_dia pero sin permitir el vacio."""
    dia = _parsear_dia(fecha, etiqueta)
    if dia is None:
        raise ValueError(f"{etiqueta} es obligatoria.")
    return dia


def _validar_contrato(inicio, fin, monto_mensual, comision_inmobiliaria, nombre_inquilino):
    """Limpia y valida los datos de un contrato. Devuelve la tupla normalizada.

    A diferencia de la casa, aca casi txdo es obligatorio: un contrato sin plazo
    ni monto no dice nada, y de esas tres fechas y ese numero cuelga el estado de
    la casa mes a mes. Lo unico opcional es el inquilino, que es un dato de
    agenda, y la comision, que no siempre hay inmobiliaria.
    """
    inicio = _fecha_obligatoria(inicio, "La fecha de inicio del contrato")
    fin = _fecha_obligatoria(fin, "La fecha de fin del contrato")
    if fin < inicio:
        raise ValueError("El fin del contrato no puede ser anterior a su inicio.")

    # Entero y sin centavos, como se pacta un alquiler. El tope lo pone el
    # PositiveIntegerField de la columna, que en MySQL llega hasta 4294967295
    monto = _entero_opcional(monto_mensual, "El alquiler mensual", 999999999)
    if not monto:
        raise ValueError("El alquiler mensual es obligatorio y tiene que ser mayor a cero.")

    # La comision es un porcentaje del alquiler, no un monto: mas de 100 no existe
    comision = _entero_opcional(comision_inmobiliaria, "La comisión de la inmobiliaria", 100)
    return inicio, fin, monto, comision, _texto_opcional(nombre_inquilino, 60, "El nombre del inquilino")


def _validar_plazo_libre(casa, inicio, fin, excluir_id=None):
    """Corta si el plazo pisa a otro contrato de la misma casa.

    Una casa no puede estar alquilada dos veces al mismo tiempo, y si lo estuviera
    no habria forma de decidir con que monto se cobra el mes. MySQL no tiene
    constraint de exclusion para rangos, asi que el corte vive aca.

    Dos plazos se pisan si cada uno empieza antes de que termine el otro. El fin
    vacio es un contrato sin vencimiento: se pisa con txdo lo que venga despues.
    """
    otros = casa.contratos.filter(Q(fin__isnull=True) | Q(fin__gte=inicio), inicio__lte=fin)
    if excluir_id:
        otros = otros.exclude(id=excluir_id)

    choque = otros.order_by("inicio").first()
    if choque is None:
        return

    hasta = choque.fin.strftime("%d/%m/%Y") if choque.fin else "sin vencimiento"
    raise ValueError(
        f"Esas fechas se pisan con el contrato del {choque.inicio:%d/%m/%Y} al {hasta}. "
        "Una casa no puede tener dos contratos a la vez."
    )


def crear_contrato(id_casa, inicio=None, fin=None, monto_mensual=None,
                   comision_inmobiliaria=None, nombre_inquilino=None):
    """Nuevo contrato de una casa. Renovar es esto: el anterior no se toca."""
    inicio, fin, monto, comision, inquilino = _validar_contrato(
        inicio, fin, monto_mensual, comision_inmobiliaria, nombre_inquilino
    )

    with transaction.atomic():
        # Bloqueo la fila de la casa para serializar el alta de contratos: chequear el
        # solapamiento (_validar_plazo_libre) y crear el contrato es un check-then-act,
        # y MySQL no tiene constraint de exclusion para rangos. Sin el lock, dos altas
        # concurrentes de la misma casa leen los mismos contratos, pasan las dos la
        # validacion y crean dos plazos que se pisan. Mismo criterio que marcar_pago_alquiler.
        casa = get_object_or_404(
            Casa.objects.select_for_update(), id=id_casa, activa=True
        )
        _validar_plazo_libre(casa, inicio, fin)

        return Contrato.objects.create(casa=casa, inicio=inicio, fin=fin, monto_mensual=monto,
                                       comision_inmobiliaria=comision, nombre_inquilino=inquilino)


def editar_contrato(id_contrato, inicio=None, fin=None, monto_mensual=None,
                    comision_inmobiliaria=None, nombre_inquilino=None):
    """Corrige un contrato ya cargado. Es para arreglar lo que se tipeo mal.

    Renovar no pasa por aca: eso es un contrato nuevo. Si se corre el plazo de uno
    viejo, los meses que dejan de estar cubiertos pasan a figurar sin alquilar, que
    es lo correcto, pero los pagos que tuvieran cargados no se borran.

    Hoy ningun boton de la pantalla lo dispara: el de la fila solo carga contratos
    nuevos y se bloquea mientras haya uno vigente. Se llega por la accion
    'editar_contrato' del POST o por el admin.
    """
    inicio, fin, monto, comision, inquilino = _validar_contrato(
        inicio, fin, monto_mensual, comision_inmobiliaria, nombre_inquilino
    )

    with transaction.atomic():
        contrato = get_object_or_404(Contrato, id=id_contrato)
        # Bloqueo la casa (no el contrato) para serializar contra crear_contrato y
        # contra otras ediciones de la misma casa: el chequeo de solapamiento mira
        # todos sus contratos, asi que la exclusion mutua tiene que vivir a nivel casa.
        # Sin el lock, un alta y una edicion concurrentes se cruzan y dejan plazos pisados.
        casa = get_object_or_404(Casa.objects.select_for_update(), id=contrato.casa_id)
        _validar_plazo_libre(casa, inicio, fin, excluir_id=contrato.id)

        contrato.inicio, contrato.fin = inicio, fin
        contrato.monto_mensual, contrato.comision_inmobiliaria = monto, comision
        contrato.nombre_inquilino = inquilino
        contrato.save()
    return contrato


def eliminar_contrato(id_contrato):
    """Borra un contrato. Es para el que se cargo mal, no para el que se termino.

    Un contrato terminado no se borra: vence solo el dia que pasa su fin y queda
    en el historial, que es justamente para lo que existe la tabla. Por eso el
    borrado es de verdad y no logico: lo unico que llega hasta aca es un registro
    equivocado, y guardarlo solo ensuciaria la cadena.

    Los pagos cuelgan de la casa y no del contrato, asi que no se van con el. Los
    meses que cubria pasan a figurar sin alquilar, pero los que tenian cobro
    cargado lo conservan y siguen sumando al total de su mes.
    """
    contrato = get_object_or_404(Contrato, id=id_contrato)
    id_casa = contrato.casa_id
    contrato.delete()
    return id_casa


def _contrato_en_dict(contrato):
    if contrato is None:
        return None
    return {
        "id": contrato.id,
        "inicio": contrato.inicio.isoformat(),
        # Vacio y no null: lo lee un input date, que espera un string
        "fin": contrato.fin.isoformat() if contrato.fin else "",
        # Monto pelado, sin separadores, para que el input lo acepte tal cual
        "monto_mensual": str(contrato.monto_mensual),
        "comision_inmobiliaria": (
            str(contrato.comision_inmobiliaria) if contrato.comision_inmobiliaria is not None else ""
        ),
        "nombre_inquilino": contrato.nombre_inquilino or "",
        "vencido": contrato.vencido,
        "meses": contrato.meses,
    }


def obtener_contrato_de_casa(id_casa):
    """Lo que el modal necesita saber de una casa antes de abrirse.

    Manda dos contratos y no uno:

    - 'vigente' es el contrato que cubre hoy. Si existe, el modal ni se abre: no
      hay contrato nuevo que cargar y el que se cargara se solaparia. El boton de
      la fila ya viene bloqueado, pero la tabla se refresca por AJAX y puede estar
      vieja, asi que el dato viaja igual como ultimo control.
    - 'anterior' es el ultimo que ya termino. Con el se precarga el formulario,
      que es lo que pasa al renovar: mismo inquilino, plazo nuevo, monto que casi
      siempre se retoca.
    """
    casa = get_object_or_404(Casa, id=id_casa, activa=True)
    hoy = timezone.localdate()

    vigente = casa.contratos.filter(Q(fin__isnull=True) | Q(fin__gte=hoy), inicio__lte=hoy).first()
    anterior = casa.contratos.filter(fin__lt=hoy).order_by("-fin", "-id").first()

    return {
        "casa": {"id": casa.id, "nombre": casa.nombre or "Sin nombre"},
        "vigente": _contrato_en_dict(vigente),
        "anterior": _contrato_en_dict(anterior),
    }


def _parsear_periodo(periodo):
    """Mes que cubre el pago, normalizado siempre al dia 1.

    Acepta "YYYY-MM" (lo que manda un input month) y "YYYY-MM-DD" (por si el
    front usa un date comun). Vacio es el mes en curso, que es el caso normal:
    se cobra el alquiler del mes y se carga en el momento.
    """
    if periodo in (None, ""):
        return periodo_actual()

    if isinstance(periodo, datetime):
        periodo = periodo.date()

    if isinstance(periodo, date):
        return date(periodo.year, periodo.month, 1)

    texto = str(periodo).strip()
    for formato in ("%Y-%m", "%Y-%m-%d"):
        try:
            convertida = datetime.strptime(texto, formato).date()
        except ValueError:
            continue
        return date(convertida.year, convertida.month, 1)

    raise ValueError("El período del pago no es válido.")


def marcar_pago_alquiler(id_casa, periodo, pagado):
    """Casilla de cobro de la tabla: crea o borra el pago del mes de una tirada.

    Es la unica via de carga de la pantalla, y alcanza porque el alquiler no
    tiene medias tintas: se cobra entero, por el monto del contrato que cubria ese
    mes, en el mes que se esta mirando. La fecha del cobro es la de hoy.

    Es idempotente: marcar lo ya marcado, o desmarcar lo que no esta cargado, no
    hace nada y tampoco es un error. Dos clicks seguidos o dos pestañas abiertas
    no tienen por que romper nada.

    Devuelve el estado que quedo y el monto involucrado. Desmarcar borra un
    registro de verdad, asi que la vista necesita poder decir cuanto era: si el
    precio cambio desde que se cargo, el usuario tiene que enterarse de lo que
    acaba de perder.
    """
    periodo = _parsear_periodo(periodo)

    with transaction.atomic():
        # Bloqueo la fila de la casa con select_for_update para serializar todas las
        # marcas/desmarcas de esa casa. Sin esto, dos "marcar" concurrentes del mismo
        # mes leian ambos pago=None y ambos hacian INSERT: el segundo chocaba contra
        # el UniqueConstraint(casa, periodo) y salia como IntegrityError (500), en vez
        # del retorno idempotente que promete la casilla. Con el lock, el segundo espera
        # y al desbloquearse ya ve el pago creado por el primero.
        casa = get_object_or_404(
            Casa.objects.select_for_update(), id=id_casa, activa=True
        )
        pago = PagoAlquiler.objects.filter(casa=casa, periodo=periodo).first()

        if not pagado:
            if pago is None:
                return {"pagado": False, "monto": None, "periodo": periodo}
            monto = pago.monto
            pago.delete()
            return {"pagado": False, "monto": monto, "periodo": periodo}

        if pago is not None:
            return {"pagado": True, "monto": pago.monto, "periodo": periodo}

        # La casilla no puede inventar un monto: sin contrato no hay pago que crear
        contrato = contratos_del_periodo(periodo).filter(casa=casa).first()
        if contrato is None:
            anterior = casa.contratos.filter(fin__lt=periodo).order_by("-fin").first()
            if anterior is not None:
                raise ValueError(
                    f"El contrato venció el {anterior.fin:%d/%m/%Y}, así que ese mes no corresponde "
                    "cobrarlo. Cargá el contrato nuevo para poder seguir."
                )
            raise ValueError(
                "La casa no tiene contrato en ese mes, así que no se sabe por cuánto es el pago. "
                "Cargale un contrato desde el botón de la fila."
            )

        PagoAlquiler.objects.create(
            casa=casa,
            periodo=periodo,
            monto=contrato.monto_mensual,
            fecha=timezone.localdate(),
        )
        return {"pagado": True, "monto": contrato.monto_mensual, "periodo": periodo}


def obtener_resumen_alquileres(casas, periodo=None):
    """Totales del periodo para la cabecera.

    Recibe siempre el listado completo, no el filtrado: la cabecera mide el mes
    entero. Si se moviera con los filtros, ver solo las cobradas la dejaria en
    cero pendiente y dejaria de decir la verdad.
    """
    periodo = periodo or periodo_actual()
    total_casas = 0
    alquiladas = 0
    esperado = Decimal("0")
    cobrado = Decimal("0")
    pendientes = 0
    monto_pendiente = Decimal("0")

    for casa in casas:
        total_casas += 1
        # "Alquilada" es tener contrato que cubra ese mes, asi que el vencido ya
        # queda afuera: la misma regla que aplica Casa.estado_mes.
        if casa.alquilada:
            alquiladas += 1

        pagado = casa.total_pagado_periodo
        if pagado > 0:
            # Lo cobrado se suma antes de mirar "alquilada": un pago cargado es
            # plata que entro ese mes, este la casa alquilada hoy o no. Antes se
            # salteaba el continue y la plata de una casa desocupada despues
            # desaparecia del total del mes.
            #
            # Y para ese mes lo esperado fue exactamente lo que se cobro, no el
            # precio de hoy: asi esperado sigue siendo cobrado mas pendiente.
            cobrado += pagado
            esperado += pagado
            continue

        # Sin pago, solo se reclama a las que tenian contrato ese mes
        if not casa.alquilada:
            continue

        # Sin parciales, lo que falta cobrar de una casa es su alquiler entero
        precio = casa.precio or Decimal("0")
        esperado += precio
        pendientes += 1
        monto_pendiente += precio

    return {
        "periodo": periodo,
        "total_casas": total_casas,
        "alquiladas": alquiladas,
        "sin_alquilar": total_casas - alquiladas,
        "esperado": esperado,
        "cobrado": cobrado,
        "pendientes": pendientes,
        "monto_pendiente": monto_pendiente,
    }


# ==========================================================================
#  GASTOS DE UNA CASA
# ==========================================================================

# Las categorias vienen del modelo para no tener dos listas que se separen: el
# formulario dibuja estas mismas opciones y la validacion corta contra ellas.
CATEGORIAS_GASTO_CASA = [clave for clave, _ in GastoCasa.CATEGORIAS]


def _validar_gasto_casa(categoria, fecha, monto, detalle):
    """Limpia y valida un gasto. Devuelve la tupla ya normalizada.

    Los tres primeros son obligatorios: un gasto sin monto no es un gasto, y sin
    fecha ni categoria no hay forma de ordenarlo ni de saber de que es. El
    detalle si es opcional, porque la categoria ya ubica el gasto.
    """
    categoria = _texto_opcional(categoria, 30, "La categoría del gasto")
    if categoria not in CATEGORIAS_GASTO_CASA:
        raise ValueError("Elegí una categoría de la lista.")

    fecha = _fecha_obligatoria(fecha, "La fecha del gasto")

    # Tope por DecimalField(max_digits=12, decimal_places=2): 10 enteros
    monto = _decimal_opcional(monto, "El monto del gasto", Decimal("9999999999.99"))
    if not monto:
        raise ValueError("El monto del gasto es obligatorio y tiene que ser mayor a cero.")

    return categoria, fecha, monto, _texto_opcional(detalle, 120, "El detalle del gasto")


def crear_gasto_casa(id_casa, categoria=None, fecha=None, monto=None, detalle=None):
    casa = get_object_or_404(Casa, id=id_casa, activa=True)
    categoria, fecha, monto, detalle = _validar_gasto_casa(categoria, fecha, monto, detalle)
    return GastoCasa.objects.create(casa=casa, categoria=categoria, fecha=fecha,
                                    monto=monto, detalle=detalle)


def editar_gasto_casa(id_gasto, categoria=None, fecha=None, monto=None, detalle=None):
    gasto = get_object_or_404(GastoCasa, id=id_gasto)
    gasto.categoria, gasto.fecha, gasto.monto, gasto.detalle = _validar_gasto_casa(
        categoria, fecha, monto, detalle
    )
    gasto.save()
    return gasto


def eliminar_gasto_casa(id_gasto):
    """Borrado de verdad y no logico: un gasto mal cargado no es historia.

    A diferencia de la casa, el gasto no tiene nada colgando que se pierda al
    borrarlo, asi que no hace falta la baja logica que usa el resto del sistema.
    """
    gasto = get_object_or_404(GastoCasa, id=id_gasto)
    id_casa = gasto.casa_id
    gasto.delete()
    return id_casa


# ==========================================================================
#  PERFIL DE UNA CASA
# ==========================================================================

def obtener_detalle_alquiler(id_casa, desde=None, hasta=None):
    """Todo lo que necesita el perfil de una casa, en una sola pasada.

    El desde y el hasta son solo para los gastos: el contrato y el historial no
    dependen de ningun periodo, muestran siempre lo que hay.

    Reparte los contratos en dos: el que corre hoy, que se muestra entero, y el
    resto, que va al historial. En el resto entran los que ya vencieron y
    tambien los que todavia no arrancaron, que existen porque nada impide dejar
    cargada la renovacion antes de tiempo.

    El vigente se busca en la lista ya traida y no con otra query: son un puñado
    de contratos por casa y el historial los necesita igual.
    """
    casa = obtener_casa(id_casa)
    hoy = timezone.localdate()

    # El orden del modelo es del mas nuevo al mas viejo, que es como los quiere
    # el historial
    contratos = list(casa.contratos.all())
    vigente = next(
        (c for c in contratos
         if c.inicio <= hoy and (c.fin is None or c.fin >= hoy)),
        None,
    )

    # Los gastos no dependen del contrato ni se renuevan con el mes: son de la
    # casa y quedan guardados para siempre. Sin filtro se muestran todos, y el
    # filtro solo recorta lo que se ve, nunca borra nada.
    #
    # Va como queryset y no como lista porque la vista lo pagina: asi la pagina
    # que se pide se trae con un LIMIT y no se levantan de la base todos los
    # gastos de la casa para mostrar cinco.
    gastos = _acotar_rango(casa.gastos.all(), "fecha", desde, hasta,
                           es_fecha_hora=False)

    return {
        "casa": casa,
        "contrato": vigente,
        "historial": [c for c in contratos if c is not vigente],
        "gastos": gastos,
        "categorias_gasto": CATEGORIAS_GASTO_CASA,
        # Para poder decir "no hay gastos en ese periodo" en vez de "no hay
        # gastos", que con un filtro puesto seria mentira
        "gastos_filtrados": bool(desde or hasta),
    }


# ===========================================================================
# IVA: empresas / sociedades y sus operaciones
#
# Cada empresa deriva su IVA debito (ventas) y credito (compras) de sus
# operaciones, sin guardar totales. El listado se pinta con tarjetas, asi que
# obtener_empresas_activas anota los dos totales con con_totales_iva para no
# disparar una query por tarjeta. El CRUD sigue el mismo patron que estaciones:
# baja logica de la empresa (preserva las operaciones) y borrado real de una
# operacion cargada mal.
# ===========================================================================

# Tope del monto neto: 15 digitos con 2 decimales en la base
MAX_MONTO_IVA = Decimal("9999999999999.99")


def obtener_empresas_activas(q=None):
    """Empresas activas con su IVA debito y credito anotados, alfabeticamente.

    Filtra por nombre cuando llega un texto de busqueda (cada palabra tiene que
    aparecer, ver filtro_tokens).
    """
    empresas = Empresa.objects.filter(activa=True).con_totales_iva()
    if q:
        empresas = empresas.filter(filtro_tokens(q, "nombre"))
    return empresas.order_by("nombre", "id")


def obtener_totales_iva(anio, mes=None):
    """IVA debito, credito y saldo de TODAS las empresas activas juntas.

    Totaliza el anio entero o, si llega 'mes' (1-12), solo ese mes. El debito sale
    de las ventas y el credito de las compras; ambos son la suma de la base
    imponible por su alicuota (misma expresion que en las tarjetas). El estado del
    saldo sigue el mismo semaforo que la empresa: a pagar / a favor / al dia.
    """
    ops = OperacionIva.objects.filter(empresa__activa=True, fecha__year=anio)
    if mes:
        ops = ops.filter(fecha__month=mes)

    debito = (ops.filter(tipo="venta").aggregate(t=_expresion_iva())["t"]
              or Decimal("0")).quantize(Decimal("0.01"))
    credito = (ops.filter(tipo="compra").aggregate(t=_expresion_iva())["t"]
               or Decimal("0")).quantize(Decimal("0.01"))
    saldo = debito - credito

    if saldo > 0:
        estado = "a_pagar"
    elif saldo < 0:
        estado = "a_favor"
    else:
        estado = "al_dia"

    return {
        "debito": debito,
        "credito": credito,
        "saldo": saldo,
        "saldo_abs": abs(saldo),
        "estado": estado,
    }


def _validar_nombre_empresa(nombre, excluir_id=None):
    """Limpia y valida el nombre de una empresa. Devuelve el nombre normalizado.

    El nombre es lo unico propio de la empresa y no puede repetirse entre las
    activas (aviso antes de que la base tire IntegrityError). Admito puntos y
    simbolos porque las razones sociales los llevan (S.A., S.R.L., etc.).
    """
    nombre = (nombre or "").strip()
    if not (2 <= len(nombre) <= 60):
        raise ValueError("El nombre de la empresa debe tener entre 2 y 60 caracteres.")

    duplicada = (Empresa.objects
                 .filter(nombre__iexact=nombre, activa=True)
                 .exclude(id=excluir_id)
                 .exists())
    if duplicada:
        raise ValueError("Ya existe una empresa con ese nombre.")
    return nombre


def crear_empresa(nombre):
    nombre = _validar_nombre_empresa(nombre)
    return Empresa.objects.create(nombre=nombre)


def editar_empresa(id_empresa, nombre):
    empresa = get_object_or_404(Empresa, id=id_empresa)
    empresa.nombre = _validar_nombre_empresa(nombre, excluir_id=empresa.id)
    empresa.save()
    return empresa


def eliminar_empresa(id_empresa):
    """Baja logica: saca la empresa del listado sin perder sus operaciones."""
    empresa = get_object_or_404(Empresa, id=id_empresa)
    empresa.activa = False
    empresa.save(update_fields=["activa"])
    return empresa


def obtener_datos_empresa(id_empresa):
    """Datos de una empresa para precargar el panel de edicion, o None."""
    try:
        empresa = Empresa.objects.get(id=id_empresa, activa=True)
    except Empresa.DoesNotExist:
        return None
    return {"id": empresa.id, "nombre": empresa.nombre}


# --- OPERACIONES DE IVA ------------------------------------------------------

def _validar_tipo_operacion(tipo):
    if tipo not in dict(OperacionIva.TIPOS):
        raise ValueError("Elegi si la operacion es una venta o una compra.")
    return tipo


def _validar_alicuota(valor):
    alicuota = _decimal_opcional(valor, "La alicuota")
    if alicuota is None:
        raise ValueError("Elegi una alicuota de IVA.")
    # Comparo numericamente contra las alicuotas validas (21, 10,5 y 27)
    if alicuota not in [a for a, _ in OperacionIva.ALICUOTAS]:
        raise ValueError("La alicuota de IVA no es valida.")
    return alicuota


def _validar_operacion_iva(tipo, fecha, monto_neto, alicuota, detalle):
    """Limpia y valida los datos de una operacion. Devuelve la tupla lista."""
    tipo = _validar_tipo_operacion(tipo)
    dia = _fecha_obligatoria(fecha, "La fecha de la operacion")
    monto = _decimal_opcional(monto_neto, "El monto neto", MAX_MONTO_IVA)
    if not monto:
        raise ValueError("El monto neto es obligatorio y tiene que ser mayor a cero.")
    alic = _validar_alicuota(alicuota)
    texto = _texto_opcional(detalle, 120, "El detalle")
    return tipo, dia, monto, alic, texto


def crear_operacion_iva(id_empresa, tipo=None, fecha=None, monto_neto=None, alicuota=None, detalle=None):
    """Registra una operacion de venta o compra de una empresa activa."""
    empresa = get_object_or_404(Empresa, id=id_empresa, activa=True)
    tipo, dia, monto, alic, texto = _validar_operacion_iva(tipo, fecha, monto_neto, alicuota, detalle)
    return OperacionIva.objects.create(
        empresa=empresa, tipo=tipo, fecha=dia, monto_neto=monto, alicuota=alic, detalle=texto,
    )


def editar_operacion_iva(id_operacion, tipo=None, fecha=None, monto_neto=None, alicuota=None, detalle=None):
    """Corrige una operacion ya cargada."""
    operacion = get_object_or_404(OperacionIva, id=id_operacion)
    tipo, dia, monto, alic, texto = _validar_operacion_iva(tipo, fecha, monto_neto, alicuota, detalle)
    operacion.tipo, operacion.fecha, operacion.monto_neto = tipo, dia, monto
    operacion.alicuota, operacion.detalle = alic, texto
    operacion.save()
    return operacion


def eliminar_operacion_iva(id_operacion):
    """Borra una operacion: lo unico que se borra es un registro cargado mal, y
    ahi el borrado real es lo correcto (no ensucia el saldo con bajas logicas)."""
    operacion = get_object_or_404(OperacionIva, id=id_operacion)
    operacion.delete()
    return operacion


def obtener_operaciones_iva(id_empresa, tipo="todas"):
    """Historial de operaciones de una empresa, de la mas nueva a la mas vieja.

    tipo filtra el listado: "ventas", "compras" o "todas" (por defecto).
    """
    operaciones = OperacionIva.objects.filter(empresa_id=id_empresa)
    if tipo == "ventas":
        operaciones = operaciones.filter(tipo="venta")
    elif tipo == "compras":
        operaciones = operaciones.filter(tipo="compra")
    return operaciones


def obtener_datos_operacion_iva(id_operacion):
    """Datos de una operacion para precargar el panel de edicion, o None."""
    try:
        operacion = OperacionIva.objects.get(id=id_operacion)
    except OperacionIva.DoesNotExist:
        return None
    return {
        "id": operacion.id,
        "tipo": operacion.tipo,
        "fecha": operacion.fecha.strftime("%Y-%m-%d"),
        "monto_neto": str(operacion.monto_neto),
        "alicuota": str(operacion.alicuota),
        "detalle": operacion.detalle or "",
    }


# ==========================================================================
#  CHEQUES
# ==========================================================================
# Tres piezas: el banco (catalogo compartido), la cuenta corriente (empresa +
# banco) y el cheque (siempre a pagar, cuelga de una cuenta). La empresa no recibe
# cheques como cobro; su total a pagar es la suma de los importes de sus cheques.

MAX_IMPORTE_CHEQUE = Decimal("9999999999999.99")

# --- BANCOS ------------------------------------------------------------------
# Catalogo simple (nombre + activo), espejo de las estaciones de servicio. La
# baja es logica para no perder las cuentas y los cheques que lo referencian.

def _validar_nombre_banco(nombre, excluir_id=None):
    """Limpia y valida el nombre de un banco. Devuelve el nombre normalizado."""
    nombre = (nombre or "").strip()
    if not (2 <= len(nombre) <= 60):
        raise ValueError("El nombre del banco debe tener entre 2 y 60 caracteres.")

    duplicado = (Banco.objects
                 .filter(nombre__iexact=nombre, activo=True)
                 .exclude(id=excluir_id)
                 .exists())
    if duplicado:
        raise ValueError("Ya existe un banco con ese nombre.")
    return nombre


def obtener_bancos_activos(q=None):
    """Bancos activos en orden alfabetico. Filtra por nombre si llega busqueda."""
    bancos = Banco.objects.filter(activo=True)
    if q:
        bancos = bancos.filter(filtro_tokens(q, "nombre"))
    return bancos.order_by("nombre", "id")


def crear_banco(nombre):
    nombre = _validar_nombre_banco(nombre)
    return Banco.objects.create(nombre=nombre)


def editar_banco(id_banco, nombre):
    banco = get_object_or_404(Banco, id=id_banco)
    banco.nombre = _validar_nombre_banco(nombre, excluir_id=banco.id)
    banco.save()
    return banco


def eliminar_banco(id_banco):
    """Baja logica: preserva las cuentas corrientes y cheques del banco."""
    banco = get_object_or_404(Banco, id=id_banco)
    banco.activo = False
    banco.save(update_fields=["activo"])
    return banco


def obtener_datos_banco(id_banco):
    """Datos de un banco para precargar el panel de edicion, o None."""
    try:
        banco = Banco.objects.get(id=id_banco, activo=True)
    except Banco.DoesNotExist:
        return None
    return {"id": banco.id, "nombre": banco.nombre}


# --- CUENTAS CORRIENTES ------------------------------------------------------

def _validar_numero_cuenta(numero):
    numero = (numero or "").strip()
    if not (1 <= len(numero) <= 40):
        raise ValueError("El número de cuenta corriente es obligatorio (hasta 40 caracteres).")
    return numero


def obtener_cuentas_corrientes(id_empresa):
    """Cuentas corrientes activas de una empresa, con su saldo de cheques anotado.

    Ordenadas por banco y numero. Trae el banco en la misma query (select_related)
    para no disparar una consulta por cuenta al mostrar su nombre.
    """
    return (CuentaCorriente.objects
            .filter(empresa_id=id_empresa, activa=True)
            .select_related("banco")
            .con_totales_cheques()
            .order_by("banco__nombre", "numero", "id"))


def crear_cuenta_corriente(id_empresa, id_banco, numero):
    """Registra una cuenta corriente de una empresa en un banco."""
    empresa = get_object_or_404(Empresa, id=id_empresa, activa=True)
    if not id_banco:
        raise ValueError("Elegí un banco para la cuenta corriente.")
    banco = get_object_or_404(Banco, id=id_banco, activo=True)
    numero = _validar_numero_cuenta(numero)

    # No repetir la misma cuenta (empresa + banco + numero) entre las activas
    duplicada = (CuentaCorriente.objects
                 .filter(empresa=empresa, banco=banco, numero__iexact=numero, activa=True)
                 .exists())
    if duplicada:
        raise ValueError("Esa cuenta corriente ya existe para esta empresa en ese banco.")

    return CuentaCorriente.objects.create(empresa=empresa, banco=banco, numero=numero)


def editar_cuenta_corriente(id_cuenta, id_banco, numero):
    cuenta = get_object_or_404(CuentaCorriente, id=id_cuenta)
    if not id_banco:
        raise ValueError("Elegí un banco para la cuenta corriente.")
    banco = get_object_or_404(Banco, id=id_banco, activo=True)
    numero = _validar_numero_cuenta(numero)

    duplicada = (CuentaCorriente.objects
                 .filter(empresa=cuenta.empresa, banco=banco, numero__iexact=numero, activa=True)
                 .exclude(id=cuenta.id)
                 .exists())
    if duplicada:
        raise ValueError("Esa cuenta corriente ya existe para esta empresa en ese banco.")

    cuenta.banco = banco
    cuenta.numero = numero
    cuenta.save()
    return cuenta


def eliminar_cuenta_corriente(id_cuenta):
    """Baja logica: saca la cuenta (y sus cheques del saldo) sin perder el historial."""
    cuenta = get_object_or_404(CuentaCorriente, id=id_cuenta)
    cuenta.activa = False
    cuenta.save(update_fields=["activa"])
    return cuenta


def obtener_datos_cuenta_corriente(id_cuenta):
    """Datos de una cuenta corriente para precargar el panel de edicion, o None."""
    try:
        cuenta = CuentaCorriente.objects.get(id=id_cuenta, activa=True)
    except CuentaCorriente.DoesNotExist:
        return None
    return {"id": cuenta.id, "id_banco": cuenta.banco_id, "numero": cuenta.numero}


# --- CHEQUES -----------------------------------------------------------------

def _validar_numero_cheque(numero):
    """Numero del cheque: obligatorio, solo digitos, hasta 20. Devuelve el texto."""
    texto = (numero or "").strip()
    if not texto:
        raise ValueError("El número de cheque es obligatorio.")
    if not texto.isdigit() or len(texto) > 20:
        raise ValueError("El número de cheque debe tener solo dígitos (hasta 20).")
    return texto


def _validar_cheque(numero, fecha_emision, fecha_cobro, concepto, importe):
    """Limpia y valida los datos de un cheque. Devuelve la tupla lista."""
    nro = _validar_numero_cheque(numero)

    emision = _fecha_obligatoria(fecha_emision, "La fecha de emisión")
    cobro = _fecha_obligatoria(fecha_cobro, "La fecha de cobro")
    if cobro < emision:
        raise ValueError("La fecha de cobro no puede ser anterior a la de emisión.")

    texto = (concepto or "").strip()
    if not (2 <= len(texto) <= 250):
        raise ValueError("El concepto es obligatorio y puede tener hasta 250 caracteres.")

    monto = _decimal_opcional(importe, "El importe", MAX_IMPORTE_CHEQUE)
    if not monto:
        raise ValueError("El importe es obligatorio y tiene que ser mayor a cero.")

    return nro, emision, cobro, texto, monto


def obtener_cheques(id_empresa, desde=None, hasta=None, estado="pendientes"):
    """Cheques a pagar de las cuentas corrientes activas de una empresa.

    Ordenados por fecha de cobro (los mas proximos primero, ver Meta del modelo).
    Trae la cuenta y el banco en la misma query para la tabla. El filtro de fecha
    (desde/hasta, inclusive) acota por la fecha de cobro, que es la que ordena y
    agrupa los cheques.

    'estado' filtra por el cobro: "pendientes" (por defecto, cobrado=False),
    "cobrados" (cobrado=True) o "todos" (sin filtrar). Cualquier valor no
    reconocido cae en "pendientes", que es la vista por defecto.
    """
    cheques = (Cheque.objects
               .filter(cuenta_corriente__empresa_id=id_empresa, cuenta_corriente__activa=True)
               .select_related("cuenta_corriente__banco"))
    if estado == "cobrados":
        cheques = cheques.filter(cobrado=True)
    elif estado != "todos":
        cheques = cheques.filter(cobrado=False)
    if desde:
        cheques = cheques.filter(fecha_cobro__gte=desde)
    if hasta:
        cheques = cheques.filter(fecha_cobro__lte=hasta)
    return cheques


def crear_cheque(id_cuenta_corriente, numero=None, fecha_emision=None, fecha_cobro=None,
                 concepto=None, importe=None):
    """Registra un cheque a pagar en una cuenta corriente activa."""
    if not id_cuenta_corriente:
        raise ValueError("Elegí la cuenta corriente del cheque.")
    cuenta = get_object_or_404(CuentaCorriente, id=id_cuenta_corriente, activa=True)
    nro, emision, cobro, texto, monto = _validar_cheque(numero, fecha_emision, fecha_cobro,
                                                        concepto, importe)
    return Cheque.objects.create(
        cuenta_corriente=cuenta, numero=nro, fecha_emision=emision, fecha_cobro=cobro,
        concepto=texto, importe=monto,
    )


def editar_cheque(id_cheque, id_cuenta_corriente=None, numero=None, fecha_emision=None,
                  fecha_cobro=None, concepto=None, importe=None):
    """Corrige un cheque ya cargado (puede moverse a otra cuenta de la empresa)."""
    cheque = get_object_or_404(Cheque, id=id_cheque)
    if not id_cuenta_corriente:
        raise ValueError("Elegí la cuenta corriente del cheque.")
    cuenta = get_object_or_404(CuentaCorriente, id=id_cuenta_corriente, activa=True)
    nro, emision, cobro, texto, monto = _validar_cheque(numero, fecha_emision, fecha_cobro,
                                                        concepto, importe)
    cheque.cuenta_corriente = cuenta
    cheque.numero = nro
    cheque.fecha_emision, cheque.fecha_cobro = emision, cobro
    cheque.concepto, cheque.importe = texto, monto
    cheque.save()
    return cheque


def eliminar_cheque(id_cheque):
    """Borra un cheque: lo unico que se borra es un registro cargado mal, y ahi el
    borrado real es lo correcto (no ensucia el saldo con bajas logicas)."""
    cheque = get_object_or_404(Cheque, id=id_cheque)
    cheque.delete()
    return cheque


def marcar_cobrado_cheque(id_cheque, cobrado):
    """Alterna el estado de cobro de un cheque (casilla de la tabla).

    Un cheque cobrado deja de sumar en el total a pagar; por eso este toggle mueve
    el saldo de la cuenta y de la empresa. No guarda mas que el propio flag.
    """
    cheque = get_object_or_404(Cheque, id=id_cheque)
    cheque.cobrado = bool(cobrado)
    cheque.save(update_fields=["cobrado"])
    return cheque


def obtener_datos_cheque(id_cheque):
    """Datos de un cheque para precargar el panel de edicion y el modal de detalle,
    o None. Incluye los campos crudos (para el form) y algunos ya formateados para
    mostrar (banco, cuenta, fechas, vencimiento) sin recalcular en el cliente."""
    try:
        cheque = Cheque.objects.select_related("cuenta_corriente__banco").get(id=id_cheque)
    except Cheque.DoesNotExist:
        return None
    return {
        "id": cheque.id,
        "id_cuenta_corriente": cheque.cuenta_corriente_id,
        "id_banco": cheque.cuenta_corriente.banco_id,
        "numero": cheque.numero,
        "fecha_emision": cheque.fecha_emision.strftime("%Y-%m-%d"),
        "fecha_cobro": cheque.fecha_cobro.strftime("%Y-%m-%d"),
        "concepto": cheque.concepto,
        "importe": str(cheque.importe),
        "cobrado": cheque.cobrado,
        # Formateados para el modal de detalle (no vuelven al form)
        "banco_nombre": cheque.cuenta_corriente.banco.nombre,
        "cuenta_numero": cheque.cuenta_corriente.numero,
        "fecha_emision_txt": cheque.fecha_emision.strftime("%d/%m/%Y"),
        "fecha_cobro_txt": cheque.fecha_cobro.strftime("%d/%m/%Y"),
        "vencimiento_txt": cheque.vencimiento.strftime("%d/%m/%Y"),
        "vencido": cheque.vencido,
        "importe_txt": floatformat(cheque.importe, "2g"),
    }


# --- LISTADO Y TOTALES -------------------------------------------------------

def obtener_empresas_con_cheques(anio=None, mes=None):
    """Empresas activas con su total a pagar en cheques anotado, alfabeticamente.

    El total se acota al periodo (anio/mes) por la fecha de cobro de cada cheque,
    que es con la que el listado agrupa mes a mes. Sin periodo suma todos los
    pendientes.
    """
    empresas = Empresa.objects.filter(activa=True).con_totales_cheques(anio, mes)
    return empresas.order_by("nombre", "id")


def obtener_empresas_para_selector_cheques():
    """Items para la pildora de empresa del listado de cheques: todas las activas.

    Forma que espera selector_entidad (id, principal, busqueda). La lista es fija
    (no depende del periodo): la pildora deja elegir cualquier empresa activa.
    """
    return [
        {"id": e.id, "principal": e.nombre, "busqueda": e.nombre.lower()}
        for e in Empresa.objects.filter(activa=True).order_by("nombre", "id")
    ]


def obtener_totales_cheques(anio=None, mes=None):
    """Total a pagar en cheques de TODAS las empresas activas juntas, en el periodo.

    Suma sobre los cheques pendientes de cuentas corrientes activas de empresas
    activas cuya fecha de cobro cae en el periodo (anio/mes). Sin periodo suma
    todos los pendientes.
    """
    qs = Cheque.objects.filter(cuenta_corriente__empresa__activa=True,
                               cuenta_corriente__activa=True, cobrado=False)
    if anio:
        qs = qs.filter(fecha_cobro__year=anio)
    if mes:
        qs = qs.filter(fecha_cobro__month=mes)
    a_pagar = (qs.aggregate(t=Sum("importe"))["t"] or Decimal("0")).quantize(Decimal("0.01"))

    return {"a_pagar": a_pagar}
