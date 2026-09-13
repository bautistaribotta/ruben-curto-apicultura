# Clientes: alta, edicion, baja, busqueda y cuenta corriente del cliente.

from datetime import timedelta
from decimal import Decimal

from django.utils import timezone
from django.shortcuts import get_object_or_404

from main.models import Cliente, Operacion, Pago, ViajeCereal

from .comunes import _acotar_rango, filtro_nombre_apellido


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
        clientes = clientes.filter(filtro_nombre_apellido(q))

    clientes = clientes.order_by("nombre", "apellido")[:limite]
    return [
        {"id": c.id, "texto": f"{c.nombre} {c.apellido or ''}".strip()}
        for c in clientes
    ]


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


def _items_operacion(operacion):
    """Lista todos los renglones de una operacion para desplegarlos en el resumen.

    Va completa, sin condensar en un "y N mas": el resumen es el comprobante que
    se le entrega al cliente y tiene que poder verificar cada producto que
    entro o salio, con el importe al que se cerro ese renglon.
    """
    items = []
    for detalle in operacion.detalleoperacion_set.all():
        if detalle.es_granel:
            cantidad = f"{detalle.cantidad:.2f}".rstrip("0").rstrip(".") + f" {detalle.abreviatura}"
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
