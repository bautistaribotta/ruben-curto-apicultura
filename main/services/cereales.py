# Viajes de cereales y sus gastos.

from datetime import datetime
from decimal import Decimal, InvalidOperation

from django.utils import timezone
from django.shortcuts import get_object_or_404
from django.db import transaction
from django.db.models import Sum, F, Value, Subquery, OuterRef
from django.db.models.functions import Coalesce

from main.models import (Cliente, Empleado, Vehiculo, ViajeCereal, DetalleViajeCereal,
                         GastoViajeCereal)

from .comunes import REGEX_CTG, REGEX_FACTURA, REGEX_TEXTO_NUMEROS, _aplicar_estado_pago
from .viajes import _sincronizar_carga_combustible, _validar_gasto_viaje


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
    # Solo 'activo': un save() completo pisaba 'pagado' y 'fecha_pago' con lo leido
    # al entrar, y deshacia un cobro marcado desde la casilla mientras tanto.
    viaje_cereal.save(update_fields=["activo"])
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
