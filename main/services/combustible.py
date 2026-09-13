# Estaciones de servicio y cargas de combustible.

from decimal import Decimal

from django.shortcuts import get_object_or_404
from django.db import transaction
from django.db.models import Sum
from django.db.models.functions import Coalesce

from main.models import Empleado, Vehiculo, EstacionDeServicio, CargaCombustible

from .comunes import MAX_COSTO, _decimal_opcional, _fecha_obligatoria, _guardar_unico


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

    return _guardar_unico(lambda: EstacionDeServicio.objects.create(nombre=nombre),
                          "Ya existe una estacion con ese nombre.")


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
    _guardar_unico(estacion.save, "Ya existe una estacion con ese nombre.")
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
