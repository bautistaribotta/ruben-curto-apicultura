# Viajes de reparto (Mercado Libre) y el catalogo de destinos.

from datetime import datetime
from decimal import Decimal, InvalidOperation

from django.utils import timezone
from django.shortcuts import get_object_or_404
from django.db import transaction
from django.db.models import Sum, F
from django.db.models.functions import Coalesce

from main.models import Empleado, Vehiculo, ViajeReparto, GastoViajeReparto, DestinoViajeReparto

from .comunes import REGEX_TEXTO_NUMEROS, _aplicar_estado_pago, _guardar_unico
from .viajes import _sincronizar_carga_combustible, _validar_gasto_viaje


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
        _guardar_unico(existente.save, f"Ya existe un destino llamado '{localidad}'.")
        return existente

    return _guardar_unico(
        lambda: DestinoViajeReparto.objects.create(localidad_destino=localidad, valor_viaje=valor_val),
        f"Ya existe un destino llamado '{localidad}'.")


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
    _guardar_unico(destino.save, f"Ya existe otro destino llamado '{localidad}'.")
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
