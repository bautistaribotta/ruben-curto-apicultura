"""
Flota: vehiculos y lo que cuelga de cada uno (kilometraje, seguros, VTV,
services y observaciones).
"""

from decimal import Decimal

from django.utils import timezone
from django.shortcuts import get_object_or_404
from django.db.models import Count, Q, Subquery, OuterRef, DecimalField, DateField

from main.models import Vehiculo, RegistroKilometraje, Seguro, VTV, Servis, ObservacionVehiculo

from .comunes import (MAX_COSTO, MAX_KILOMETROS, REGEX_PATENTE, REGEX_TEXTO_NUMEROS,
                      _decimal_opcional, _fecha_obligatoria, _texto_opcional)


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
