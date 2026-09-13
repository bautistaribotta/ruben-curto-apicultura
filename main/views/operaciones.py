"""
Operaciones de compra y venta: detalle, remito, alta y edicion, registro de
pagos, cancelacion y listado global.
"""

import json

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import ensure_csrf_cookie
from django.core.paginator import Paginator
from django.contrib import messages
from django.http import JsonResponse, HttpResponse
from django.db import transaction
from django.utils import timezone

from main.models import Cliente, Producto, Operacion, DetalleOperacion, Pago, ProductoPorKg, Viaje
from main.pdf_services import Remito

from main.services.comunes import filtro_tokens
from main.services.filtros import (nombre_cliente_operaciones_filtro,
                                   nombre_producto_operaciones_filtro,
                                   opciones_clientes_operaciones, opciones_productos_operaciones)
from main.services.operaciones import (crear_operacion, editar_operacion,
                                       obtener_operaciones_listado, servicio_cancelar_operacion)

from .comunes import _rango_fechas
from .productos import _productos_por_kg_del_listado


@login_required
@ensure_csrf_cookie
def informacion_operacion(request, id_operacion):
    operacion = get_object_or_404(Operacion.objects.con_totales(), id=id_operacion)

    from django.db.models import F
    pagos = operacion.pago_set.all().order_by("-fecha", "-id")
    # Anoto el subtotal por linea (cantidad * precio fijado en la operacion) para la tabla de productos
    detalles = DetalleOperacion.objects.filter(operacion=operacion).annotate(
        subtotal=F("cantidad") * F("precio_unitario")
    )

    # Calculate rest
    from decimal import Decimal
    monto_total = operacion.monto_total or Decimal('0')
    total_pagado = operacion.total_pagado or Decimal('0')
    restante = monto_total - total_pagado

    # Porcentaje pagado para la barra de progreso
    pct_pagado = float(total_pagado / monto_total * 100) if monto_total else 0
    pct_pagado = max(0, min(100, pct_pagado))

    contexto = {
        'operacion': operacion,
        'cliente': operacion.cliente,
        'pagos': pagos,
        'detalles': detalles,
        'restante': restante,
        'total_pagado': total_pagado,
        'pct_pagado': pct_pagado,
        'pestaña': 'clientes'
    }
    return render(request, "informacion_operacion.html", contexto)


@login_required
def generar_remito(request, id_operacion):
    operacion = get_object_or_404(Operacion, id=id_operacion)
    cliente = operacion.cliente
    detalles = DetalleOperacion.objects.filter(operacion=operacion)
    """
        Como esta relacionado en Django la operacion con el detalle
        Solo le paso el de la operacion que acabo de encontrar en la Query anterior
    """

    # Los usuarios no administrativos reciben el remito sin ningun importe: no
    # se calculan los subtotales ni el total, asi el PDF no los contiene
    mostrar_importes = request.user.is_staff

    # Armamos la lista estructurada de los productos para enviarlo al PDF
    lista_productos = []
    total = 0
    for d in detalles:
        if d.es_granel:
            # Los kilos o litros se muestran sin ceros de mas y con la unidad explicita
            cantidad = f"{d.cantidad:.2f}".rstrip("0").rstrip(".") + f" {d.abreviatura}"
        else:
            cantidad = d.cantidad
        # Subtotal de la fila: cantidad por precio unitario
        subtotal = d.cantidad * d.precio_unitario if mostrar_importes else 0
        total += subtotal
        lista_productos.append({
            'cantidad': cantidad,
            'detalle': d.nombre_item,
            'subtotal': subtotal,
        })

    pdf = Remito(
        id_operacion=operacion.id,
        fecha=operacion.fecha,
        nombre=cliente.nombre,
        localidad=cliente.localidad if cliente.localidad else "",
        direccion=cliente.direccion if cliente.direccion else "",
        productos=lista_productos,
        apellido=cliente.apellido if cliente.apellido else "",
        cuit=cliente.cuit if cliente.cuit else "",
        telefono=cliente.telefono if cliente.telefono else "",
        observaciones=operacion.observaciones,
        total=total,
        mostrar_importes=mostrar_importes
    )

    pdf_bytes = pdf.generate_pdf()
    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    response["Content-Disposition"] = f'inline; filename="remito_{operacion.id}.pdf"'

    return response


def _contexto_edicion(operacion):
    """
    Arma los datos que el front necesita para precargar el carrito al editar
    una operación: ítems (con stock ajustado), fecha y métxdo de pago inferido.
    """
    es_venta = operacion.tipo_operacion == "venta"

    items = []
    detalles = operacion.detalleoperacion_set.select_related("producto", "cotizacion")
    for d in detalles:
        if d.cotizacion_id:
            # En una venta editada, los kilos de esta operación vuelven a estar
            # disponibles, por eso el stock efectivo suma los propios
            stock = d.cotizacion.cantidad + d.cantidad if es_venta else d.cotizacion.cantidad
            items.append({
                "tipo": "granel",
                "id": d.cotizacion_id,
                "nombre": d.cotizacion.articulo,
                "unidad": d.cotizacion.unidad,
                "cantidad": str(d.cantidad),
                "precio": str(d.precio_unitario),
                "stock": str(stock),
            })
        else:
            stock = d.producto.cantidad + int(d.cantidad) if es_venta else d.producto.cantidad
            items.append({
                "tipo": "producto",
                "id": d.producto_id,
                "nombre": d.producto.nombre,
                "cantidad": int(d.cantidad),
                "precio": str(d.precio_unitario),
                "stock": stock,
                # Producto dado de baja: la línea queda congelada en el carrito
                # (sin cambiar cantidad ni precio, sin poder quitarla)
                "bloqueado": not d.producto.activo,
            })

    # El métxdo de pago no se guarda: se infiere de los pagos. Con pagos
    # registrados queda bloqueado (regla de edición)
    cantidad_pagos = operacion.pago_set.count()
    total_pagado = operacion.total_pagado or 0
    monto_total = operacion.monto_total or 0
    metodo = "contado" if cantidad_pagos and total_pagado >= monto_total else "cuenta_corriente"

    return {
        "id": operacion.id,
        "fecha": timezone.localtime(operacion.fecha).strftime("%Y-%m-%d"),
        "metodo": metodo,
        "metodo_bloqueado": cantidad_pagos > 0,
        "observaciones": operacion.observaciones,
        "items": items,
    }


def _paginar_operacion_con_granel(productos, categoria, q, pagina_numero):
    """
    Arma la pagina del listado de una operacion (venta o compra) intercalando los
    productos a granel (ProductoPorKg, por kilo o por litro) con los que se venden
    por unidad. Los de granel entran con la misma regla que en el inventario y se
    cuentan dentro de la paginacion, apareciendo primero en su pagina. Devuelve
    (granel_pagina, productos_pagina, pagina_obj).
    """
    granel = _productos_por_kg_del_listado(q, categoria)

    items = list(granel) + list(productos)
    pagina_obj = Paginator(items, 6).get_page(pagina_numero)

    granel_pagina = [item for item in pagina_obj if isinstance(item, ProductoPorKg)]
    productos_pagina = [item for item in pagina_obj if isinstance(item, Producto)]
    return granel_pagina, productos_pagina, pagina_obj


@login_required
@ensure_csrf_cookie
def nueva_operacion_venta(request, id_cliente):
    cliente = get_object_or_404(Cliente, id=id_cliente)

    if request.method == "POST":
        try:
            datos = json.loads(request.body)
            items = datos.get("items", [])
            metodo_pago = datos.get("metodo_pago", "cuenta_corriente")  # Fallback
            tipo_operacion = datos.get("tipo_operacion", "venta")  # Esta vista corresponde al flujo de ventas

            if not items:
                return JsonResponse({"error": "El carrito está vacío"}, status=400)

            # Si la operacion se crea desde un viaje, queda asociada a el
            id_viaje = request.GET.get("viaje")
            viaje = get_object_or_404(Viaje, id=id_viaje) if id_viaje else None

            # Fecha opcional para cargar operaciones viejas (None = hoy)
            fecha = datos.get("fecha")

            # Cotizaciones de aquel día (obligatorias con fecha anterior a hoy)
            cotizaciones_historicas = datos.get("cotizaciones_historicas")

            # Nota opcional que se imprime en el remito
            observaciones = datos.get("observaciones")

            # Modo edición (solo staff): reemplaza los ítems de una operación existente
            id_editar = datos.get("editar")
            if id_editar:
                if not request.user.is_staff:
                    return JsonResponse({"error": "Solo el personal autorizado puede editar operaciones."}, status=403)
                # Valido que la operación exista, sea de este cliente y de este tipo
                get_object_or_404(Operacion, id=id_editar, cliente=cliente, tipo_operacion="venta", activa=True)
                operacion = editar_operacion(id_editar, items, metodo_pago, fecha=fecha,
                                             cotizaciones_historicas=cotizaciones_historicas,
                                             observaciones=observaciones)
                messages.success(request, "Operación actualizada correctamente")
                return JsonResponse({"ok": True, "id_cliente": cliente.id, "id_operacion": operacion.id, "editada": True})

            # Delegamos toda la lógica de creación a la capa de servicios
            operacion = crear_operacion(cliente, items, metodo_pago, tipo_operacion, viaje, fecha=fecha,
                                        cotizaciones_historicas=cotizaciones_historicas,
                                        observaciones=observaciones)

            # Enviar mensaje de éxito a través del framework de mensajes de Django
            messages.success(request, "Operación creada correctamente")

            return JsonResponse(
                {
                    "ok": True,
                    "id_cliente": cliente.id,
                    "id_operacion": operacion.id,
                    "id_viaje": viaje.id if viaje else None,
                }
            )

        except ValueError as e:
            return JsonResponse({"error": str(e)}, status=400)
        except Exception as e:
            return JsonResponse(
                {"error": f"Error al procesar la operación: {e}"}, status=500
            )

    # Parámetros de búsqueda y filtro por categoría
    q = request.GET.get("q", "")
    categoria_filtrada = request.GET.get("categoria", "")

    productos = Producto.objects.filter(activo=True)

    if q:
        if q.isdigit():
            productos = productos.filter(id__icontains=q)
        else:
            productos = productos.filter(filtro_tokens(q, "nombre"))

    if categoria_filtrada:
        productos = productos.filter(categoria=categoria_filtrada)

    productos = productos.order_by("nombre")

    # Stock a granel (por kilo o por litro): se intercala en el listado respetando
    # la busqueda y la categoria. Se integra a la misma paginacion (aparece primero)
    # para que la pagina no supere las 6 filas.
    granel_pagina, productos_pagina, pagina_obj = _paginar_operacion_con_granel(
        productos, categoria_filtrada, q, request.GET.get("page")
    )

    # Modo edición (solo staff): precarga el carrito con la operación existente
    edicion = None
    id_editar = request.GET.get("editar")
    if id_editar:
        if not request.user.is_staff:
            return redirect("informacion_operacion", id_operacion=id_editar)
        operacion = get_object_or_404(Operacion, id=id_editar, cliente=cliente, tipo_operacion="venta", activa=True)
        edicion = _contexto_edicion(operacion)

    contexto = {
        "cliente": cliente,
        "productos": productos_pagina,
        "granel": granel_pagina,
        "pagina": pagina_obj,
        "q": q,
        "categoria": categoria_filtrada,
        "categorias": Producto.categorias,
        "edicion": edicion,
    }

    # Si es una petición AJAX, devuelvo solo la tabla parcial
    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        return render(request, "tabla_operaciones_productos.html", contexto)

    return render(request, "nueva_operacion_venta.html", contexto)


@login_required
@ensure_csrf_cookie
def nueva_operacion_compra(request, id_cliente):
    cliente = get_object_or_404(Cliente, id=id_cliente)

    if request.method == "POST":
        try:
            datos = json.loads(request.body)
            items = datos.get("items", [])
            metodo_pago = datos.get("metodo_pago", "cuenta_corriente")  # Fallback

            if not items:
                return JsonResponse({"error": "El carrito está vacío"}, status=400)

            # Si la compra se crea desde un viaje, queda asociada a el
            id_viaje = request.GET.get("viaje")
            viaje = get_object_or_404(Viaje, id=id_viaje) if id_viaje else None

            # Fecha opcional para cargar compras viejas (None = hoy)
            fecha = datos.get("fecha")

            # Cotizaciones de aquel día (obligatorias con fecha anterior a hoy)
            cotizaciones_historicas = datos.get("cotizaciones_historicas")

            # Nota opcional que se imprime en el remito
            observaciones = datos.get("observaciones")

            # Modo edición (solo staff): reemplaza los ítems de una compra existente
            id_editar = datos.get("editar")
            if id_editar:
                if not request.user.is_staff:
                    return JsonResponse({"error": "Solo el personal autorizado puede editar operaciones."}, status=403)
                get_object_or_404(Operacion, id=id_editar, cliente=cliente, tipo_operacion="compra", activa=True)
                operacion = editar_operacion(id_editar, items, metodo_pago, fecha=fecha,
                                             cotizaciones_historicas=cotizaciones_historicas,
                                             observaciones=observaciones)
                messages.success(request, "Compra actualizada correctamente")
                return JsonResponse({"ok": True, "id_cliente": cliente.id, "id_operacion": operacion.id, "editada": True})

            # El tipo se fuerza a "compra"; en compra el precio viene en cada item
            operacion = crear_operacion(cliente, items, metodo_pago, "compra", viaje, fecha=fecha,
                                        cotizaciones_historicas=cotizaciones_historicas,
                                        observaciones=observaciones)

            messages.success(request, "Compra creada correctamente")

            return JsonResponse(
                {
                    "ok": True,
                    "id_cliente": cliente.id,
                    "id_operacion": operacion.id,
                    "id_viaje": viaje.id if viaje else None,
                }
            )

        except ValueError as e:
            return JsonResponse({"error": str(e)}, status=400)
        except Exception as e:
            return JsonResponse(
                {"error": f"Error al procesar la compra: {e}"}, status=500
            )

    # Parámetros de búsqueda y filtro por categoría
    q = request.GET.get("q", "")
    categoria_filtrada = request.GET.get("categoria", "")

    productos = Producto.objects.filter(activo=True)

    if q:
        if q.isdigit():
            productos = productos.filter(id__icontains=q)
        else:
            productos = productos.filter(filtro_tokens(q, "nombre"))

    if categoria_filtrada:
        productos = productos.filter(categoria=categoria_filtrada)

    productos = productos.order_by("nombre")

    # Igual que en venta: el stock a granel se intercala en el listado, integrado a
    # la paginacion (aparece primero en su pagina).
    granel_pagina, productos_pagina, pagina_obj = _paginar_operacion_con_granel(
        productos, categoria_filtrada, q, request.GET.get("page")
    )

    # Modo edición (solo staff): precarga el carrito con la compra existente
    edicion = None
    id_editar = request.GET.get("editar")
    if id_editar:
        if not request.user.is_staff:
            return redirect("informacion_operacion", id_operacion=id_editar)
        operacion = get_object_or_404(Operacion, id=id_editar, cliente=cliente, tipo_operacion="compra", activa=True)
        edicion = _contexto_edicion(operacion)

    contexto = {
        "cliente": cliente,
        "productos": productos_pagina,
        "granel": granel_pagina,
        "pagina": pagina_obj,
        "q": q,
        "categoria": categoria_filtrada,
        "categorias": Producto.categorias,
        "edicion": edicion,
    }

    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        return render(request, "tabla_compras_productos.html", contexto)

    return render(request, "nueva_operacion_compra.html", contexto)


@login_required
@ensure_csrf_cookie
def registrar_pago(request, id_operacion):
    if request.method == "POST":
        try:
            datos = json.loads(request.body)
            monto_str = datos.get("monto")

            if not monto_str:
                return JsonResponse({"error": "Debe ingresar un monto."}, status=400)

            # Usamos Decimal para máxima precisión en dinero
            from decimal import Decimal
            monto = Decimal(monto_str)
            if monto <= 0:
                return JsonResponse({"error": "El monto debe ser mayor a 0."}, status=400)

            with transaction.atomic():
                # Bloqueo la operación con select_for_update para que el cálculo
                # del restante y el INSERT del pago sean atómicos. Sin esto, dos
                # pagos concurrentes leen el mismo restante, ambos validan y
                # ambos insertan, produciendo un sobrepago (TOCTOU).
                operacion = get_object_or_404(
                    Operacion.objects.select_for_update(), id=id_operacion
                )

                restante = Decimal(str(operacion.monto_total or 0)) - Decimal(str(operacion.total_pagado))

                if monto > restante:
                    return JsonResponse({"error": "El monto no puede superar el restante a pagar."}, status=400)

                # Crear el pago
                Pago.objects.create(
                    operacion=operacion,
                    monto=monto
                )

            messages.success(request, "Pago registrado correctamente")
            return JsonResponse({"ok": True})

        except ValueError:
            return JsonResponse({"error": "Monto inválido."}, status=400)
        except Exception as e:
            return JsonResponse({"error": f"Error al registrar el pago: {str(e)}"}, status=500)

    return JsonResponse({"error": "Método no permitido"}, status=405)


@login_required
def cancelar_operacion(request, id_operacion):
    if request.method == "POST":
        try:
            servicio_cancelar_operacion(id_operacion)
            messages.success(request, "Operación cancelada correctamente")
            return JsonResponse({"ok": True})
        except Exception as e:
            return JsonResponse({"error": str(e)}, status=500)
    return JsonResponse({"error": "Método no permitido"}, status=405)


@login_required
def operaciones(request):
    """Listado global de operaciones de compra/venta, de solo lectura.

    Muestra las operaciones activas de la mas reciente a la mas vieja y se puede
    filtrar por producto (chip + modal) y por rango de fechas (chip + popover),
    combinados entre si. Los montos y el estado de pago solo se muestran al personal
    (is_staff); el resto ve el historial operativo sin la informacion de dinero. La
    fila lleva al detalle de la operacion (?origen=operaciones para volver aca).
    """
    import re
    from datetime import datetime, time

    lista = obtener_operaciones_listado()

    """
    Filtro por producto: token que distingue producto de catalogo ("p<id>") de
    articulo a granel ("g<id_cotizacion>"), porque una linea apunta a uno u otro.
    Un token mal formado se ignora y se muestran todas las operaciones.
    """
    producto = request.GET.get("producto", "")
    if not re.fullmatch(r"[pg]\d+", producto):
        producto = ""
    if producto:
        ident = producto[1:]
        if producto[0] == "p":
            lista = lista.filter(detalleoperacion__producto_id=ident).distinct()
        else:
            lista = lista.filter(detalleoperacion__cotizacion_id=ident).distinct()

    """
    Filtro por cliente: el id viaja tal cual (numerico). Un id mal formado se ignora
    y se muestran todas las operaciones. Se combina con el resto de los filtros.
    """
    cliente = request.GET.get("cliente", "")
    if not cliente.isdigit():
        cliente = ""
    if cliente:
        lista = lista.filter(cliente_id=cliente)

    """
    Filtro por rango de fechas de la operacion (componente compartido). La fecha es
    un DateTimeField: en SQLite con USE_TZ el lookup __date no matchea, asi que
    comparo contra los limites del rango como datetimes con zona (mismo criterio que
    el listado de deudores): desde al inicio del dia y hasta al final.
    """
    desde, hasta, ctx_fechas = _rango_fechas(request)
    if desde:
        inicio = timezone.make_aware(datetime.combine(desde, time.min))
        lista = lista.filter(fecha__gte=inicio)
    if hasta:
        fin = timezone.make_aware(datetime.combine(hasta, time.max))
        lista = lista.filter(fecha__lte=fin)

    paginator = Paginator(lista, 10)
    page_obj = paginator.get_page(request.GET.get("page"))

    contexto = {
        "page_obj": page_obj,
        "producto": producto,
        "producto_nombre": nombre_producto_operaciones_filtro(producto),
        "productos_filtro": opciones_productos_operaciones(),
        "cliente": cliente,
        "cliente_nombre": nombre_cliente_operaciones_filtro(cliente),
        "clientes_filtro": opciones_clientes_operaciones(),
        **ctx_fechas,
    }

    # Peticion AJAX (chips de filtro o paginacion): devuelvo solo la tabla parcial.
    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        return render(request, "tabla_operaciones.html", contexto)

    return render(request, "operaciones.html", contexto)
