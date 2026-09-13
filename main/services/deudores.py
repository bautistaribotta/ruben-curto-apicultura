# Listado de deudores: operaciones impagas con su equivalencia en dolares, miel y cera.

from datetime import datetime, time
from decimal import Decimal, InvalidOperation

from django.utils import timezone
from django.db.models import Sum, F, Value
from django.db.models.functions import Coalesce

from main.models import Operacion, DetalleOperacion, Pago

from .comunes import _iniciales, filtro_nombre_apellido
from .cotizaciones import (get_cotizacion_cera_operculo, get_cotizacion_dolar_oficial,
                           get_cotizacion_miel_50mm)


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
