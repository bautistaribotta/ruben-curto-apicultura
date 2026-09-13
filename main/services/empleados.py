"""
Empleados: alta, edicion, baja, sueldo, carnet, pagos y cuenta corriente
mes a mes.
"""

from datetime import datetime, time, timedelta
from decimal import Decimal, InvalidOperation

from django.utils import timezone
from django.shortcuts import get_object_or_404
from django.db.models import Count, Q

from main.models import Empleado, PagosEmpleados, Viaje, ViajeCereal

from .comunes import REGEX_TEXTO_BASICO, mes_desplazado


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
