"""
Viajes de miel/cera: alta, edicion, baja, gastos (compartidos con cereal y
reparto), ingresos a la caja y devolucion del sobrante.
"""

from datetime import datetime

from django.utils import timezone
from django.shortcuts import get_object_or_404
from django.db import transaction

from main.models import (Empleado, PagosEmpleados, Vehiculo, Viaje, DetalleViaje, Gasto,
                         IngresoCaja, EstacionDeServicio, CargaCombustible)

from .comunes import REGEX_TEXTO_NUMEROS, _decimal_opcional


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
    with transaction.atomic():
        """
        Bloqueo la fila del viaje con select_for_update, y recien ahi leo su estado.
        Sin el lock, dos registros concurrentes de la misma devolucion (doble click,
        dos pestañas) leian ambos pago_devolucion=None y creaban dos PagosEmpleados:
        el segundo quedaba huerfano del viaje pero sumaba igual en la cuenta
        corriente del empleado. Con el lock, el segundo espera y al desbloquearse ya
        ve el pago que creo el primero, asi que solo lo actualiza.
        """
        viaje = get_object_or_404(Viaje.objects.select_for_update(), id=id_viaje, activo=True)

        if estado not in (Viaje.DEVOLUCION_SIN_REGISTRAR, Viaje.DEVOLUCION_TOTAL, Viaje.DEVOLUCION_PARCIAL):
            raise ValueError("El estado de la devolución no es válido.")

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
