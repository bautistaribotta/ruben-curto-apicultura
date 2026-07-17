import json

from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.contrib.auth import authenticate, login as auth_login, logout as auth_logout
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import ensure_csrf_cookie
from django.core.paginator import Paginator
from django.contrib import messages
from django.http import JsonResponse, HttpResponse
from django.db import transaction
from django.utils import timezone

from .models import Cliente, Producto, Operacion, DetalleOperacion, Pago, Cotizaciones, Chofer, Vehiculo, Viaje, ViajeCereal, ViajeReparto
from .pdf_services import Remito
from .services import (nuevo_producto, editar_producto, eliminar_producto, nuevo_cliente, editar_cliente,
                       eliminar_cliente, buscar_clientes, get_cotizacion_dolar_oficial, get_cotizaciones, get_total_kilos_granel, get_articulos_granel, actualizar_cotizacion, obtener_datos_cliente,
                       obtener_datos_producto, modificar_stock, crear_operacion, editar_operacion, servicio_cancelar_operacion,
                       obtener_listado_deudores, crear_chofer, crear_vehiculo, crear_viaje, obtener_choferes_activos,
                       obtener_vehiculos_activos, obtener_viajes, obtener_datos_viaje, editar_viaje, eliminar_viaje, crear_gasto,
                       incluir_asignado,
                       editar_chofer, eliminar_chofer, editar_vehiculo, eliminar_vehiculo,
                       crear_viaje_cereal, obtener_viajes_cereales, obtener_datos_viaje_cereal,
                       editar_viaje_cereal, eliminar_viaje_cereal, crear_gasto_viaje_cereal,
                       crear_viaje_reparto, obtener_viajes_reparto, obtener_datos_viaje_reparto,
                       editar_viaje_reparto, eliminar_viaje_reparto, crear_gasto_viaje_reparto)


def login(request):
    if request.method == "POST":
        usuario = request.POST.get("user")
        password = request.POST.get("password")

        usuario_valido = authenticate(request, username=usuario, password=password)

        # Si es válido los redirijo, si no, envío el error por mensaje
        if usuario_valido is not None:
            auth_login(request, usuario_valido)
            return redirect("inicio")

        else:
            messages.error(request, "Usuario y/o contraseña incorrectos")
            return redirect("login")

    return render(request, "login.html")


"""
Si un usuario anónimo (sin loguearse) quiere acceder a las paginas internas, 
le bloqueo el acceso y lo envio de vuelta a '/' (pagina configurada del inicio del server) 
para que se loguee. Todo esto implementado usando el wrapped @login_required
"""


@login_required
def inicio(request):
    dolar_oficial = get_cotizacion_dolar_oficial()
    cotizaciones = get_cotizaciones()
    totales_granel = get_total_kilos_granel()
    contexto = {"oficial": dolar_oficial, "cotizaciones": cotizaciones, "totales_granel": totales_granel}
    return render(request, "inicio.html", contexto)


@login_required
@ensure_csrf_cookie
def actualizar_cotizacion_ajax(request):
    if request.method == "POST":
        try:
            datos = json.loads(request.body)
            articulo = datos.get("articulo")
            monto = datos.get("monto")

            if articulo and monto is not None:
                if float(monto) < 1:
                    return JsonResponse({"error": "La cotización no puede ser menor a 1"}, status=400)
                actualizar_cotizacion(articulo, monto)
                return JsonResponse({"ok": True})
            else:
                return JsonResponse({"error": "Datos incompletos"}, status=400)
        except Exception as e:
            return JsonResponse({"error": str(e)}, status=500)
    return JsonResponse({"error": "Método no permitido"}, status=405)


@login_required
def productos(request):
    """
    Recibo el metodo POST, guardo los datos del formulario y creo
    el producto en la base de datos, queda realizar validaciones
    """
    if request.method == "POST":
        id_producto = request.POST.get("id_producto")
        nombre_producto = request.POST.get("nombre")
        categoria = request.POST.get("categoria")
        precio = request.POST.get("precio")
        cantidad = request.POST.get("stock")

        # Si el usuario no ingresó un stock (campo vacío), lo coloco en 0
        if not cantidad:
            cantidad = 0

        # Verifico qué acción se está realizando
        accion = request.POST.get("accion")
        id_eliminar = request.POST.get("id_eliminar")

        if accion == "modificar_stock":
            id_producto_stock = request.POST.get("id_producto_stock")
            tipo_modificacion = request.POST.get("tipo_modificacion")
            cantidad_modificar = request.POST.get("cantidad")
            
            if id_producto_stock and cantidad_modificar:
                try:
                    producto = Producto.objects.get(id=id_producto_stock)
                    cantidad_modificar = int(cantidad_modificar)
                    if tipo_modificacion == "quitar":
                        cantidad_modificar = -cantidad_modificar
                        
                    modificar_stock(id_producto_stock, cantidad_modificar)
                    
                    if tipo_modificacion == "quitar":
                        unidad_str = "unidad" if abs(cantidad_modificar) == 1 else "unidades"
                        messages.success(request, f"Se quitó {abs(cantidad_modificar)} {unidad_str} de {producto.nombre}")
                    else:
                        unidad_str = "unidad" if abs(cantidad_modificar) == 1 else "unidades"
                        messages.success(request, f"Se agregó {abs(cantidad_modificar)} {unidad_str} de {producto.nombre}")
                except Producto.DoesNotExist:
                    messages.error(request, "El producto no existe.")
                except ValueError as e:
                    messages.error(request, str(e))
                except Exception as e:
                    messages.error(request, f"Error al modificar el stock: {str(e)}")
                    
            return redirect("productos")

        elif id_eliminar:
            eliminar_producto(id_eliminar)
            messages.success(request, "Producto eliminado correctamente")
            return redirect("productos")

        else:
            # Si es una EDICION
            if id_producto:
                editar_producto(
                    id_producto, nombre_producto, categoria, precio, True
                )
                messages.success(request, "Producto editado correctamente")

            # Si es un NUEVO producto
            else:
                nuevo_producto(nombre_producto, categoria, precio, cantidad)
                messages.success(request, "Producto agregado correctamente")

        return redirect("productos")

    # Parámetros de búsqueda y filtrado
    q = request.GET.get("q", "")
    categoria_filtrada = request.GET.get("categoria", "")

    productos = Producto.objects.filter(activo=True)

    if q:
        if q.isdigit():
            # Si es solo números, busco por ID (exacto o que contenga)
            productos = productos.filter(id__icontains=q)
        else:
            # Si no, buscamos por nombre
            productos = productos.filter(nombre__icontains=q)

    if categoria_filtrada:
        productos = productos.filter(categoria=categoria_filtrada)

    productos = productos.order_by("nombre")

    # Cargo de a 5 productos
    paginator_productos = Paginator(productos, 5)
    pagina_numero = request.GET.get("page")
    pagina_obj = paginator_productos.get_page(pagina_numero)

    contexto = {"productos": pagina_obj, "q": q, "categoria": categoria_filtrada}

    # Si es una petición AJAX, devuelvo solo la tabla
    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        return render(request, "tabla_productos.html", contexto)

    return render(request, "productos.html", contexto)


@login_required
def obtener_producto_json(request, id_producto):
    datos = obtener_datos_producto(id_producto)

    if datos:
        # Si el producto existe, devuelvo la respuesta exitosa en JSON
        return JsonResponse(datos)

    # Si no lo encuentro o está inactivo, devuelvo un error 404
    return JsonResponse({"Error": "Producto no encontrado"}, status=404)


@login_required
def clientes(request):
    if request.method == "POST":
        id_cliente = request.POST.get("id_cliente")
        nombre_cliente = request.POST.get("nombre")
        apellido = request.POST.get("apellido")
        telefono = request.POST.get("telefono")
        localidad = request.POST.get("localidad")
        direccion = request.POST.get("direccion")
        # El checkbox llega como 'on' si está marcado, lo convierto en un booleano
        factura = request.POST.get("factura") == "on"
        cuit = request.POST.get("cuit")
        if not factura:
            cuit = None
        elif cuit:
            # Elimina todos los guiones antes de guardarlo en la base de datos
            cuit = cuit.replace("-", "")

        # Si es una ELIMINACION, aqui traigo el id a borrar
        id_eliminar = request.POST.get("id_eliminar")
        if id_eliminar:
            eliminar_cliente(id_eliminar)
            messages.success(request, "Cliente eliminado correctamente")
            return redirect("clientes")

        else:
            # Si es una EDICION
            if id_cliente:
                editar_cliente(
                    id_cliente,
                    nombre_cliente,
                    apellido,
                    telefono,
                    localidad,
                    direccion,
                    factura,
                    cuit,
                    True,
                )
                messages.success(request, "Cliente editado correctamente")

            # Si es un NUEVO cliente
            else:
                nuevo_cliente(
                    nombre_cliente,
                    apellido,
                    telefono,
                    localidad,
                    direccion,
                    factura,
                    cuit,
                )
                messages.success(request, "Cliente agregado correctamente")

        return redirect("clientes")

    # Parámetros de búsqueda
    q = request.GET.get("q", "")

    clientes_list = Cliente.objects.filter(activo=True)

    if q:
        if q.isdigit():
            # Si es solo números, busco por ID (exacto o que contenga)
            clientes_list = clientes_list.filter(id__icontains=q)
        else:
            # Buscar por nombre o apellido
            from django.db.models import Q

            clientes_list = clientes_list.filter(
                Q(nombre__icontains=q) | Q(apellido__icontains=q)
            )

    clientes_list = clientes_list.order_by("nombre")

    # Cargo de a 5 clientes
    paginator_clientes = Paginator(clientes_list, 5)
    pagina_numero = request.GET.get("page")
    pagina_obj = paginator_clientes.get_page(pagina_numero)

    contexto = {"clientes": pagina_obj, "q": q}

    # Si es AJAX, devolvemos el parcial
    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        return render(request, "tabla_clientes.html", contexto)

    return render(request, "clientes.html", contexto)


@login_required
def informacion_clientes(request, id_cliente):
    cliente = get_object_or_404(Cliente, id=id_cliente, activo=True)

    if request.method == "POST":
        id_cliente_form = request.POST.get("id_cliente")
        nombre = request.POST.get("nombre")
        apellido = request.POST.get("apellido")
        telefono = request.POST.get("telefono")
        localidad = request.POST.get("localidad")
        direccion = request.POST.get("direccion")
        factura = request.POST.get("factura") == "on"
        cuit = request.POST.get("cuit")
        if not factura:
            cuit = None
        elif cuit:
            cuit = cuit.replace("-", "")

        editar_cliente(
            id_cliente_form,
            nombre,
            apellido,
            telefono,
            localidad,
            direccion,
            factura,
            cuit,
            True,
        )
        messages.success(request, "Cliente editado correctamente")
        return redirect("informacion_clientes", id_cliente=id_cliente)

    operaciones_cliente = Operacion.objects.filter(cliente=cliente).con_totales().prefetch_related("detalleoperacion_set__producto", "detalleoperacion_set__cotizacion", "pago_set").order_by("-fecha")

    # Filtro por tipo de operacion segun la pestaña activa (todas / venta / compra)
    tipo_actual = request.GET.get("tipo", "todas")
    if tipo_actual in ("venta", "compra"):
        operaciones_cliente = operaciones_cliente.filter(tipo_operacion=tipo_actual)
    else:
        tipo_actual = "todas"

    # Cargo de a 5 operaciones
    paginator_operaciones = Paginator(operaciones_cliente, 5)
    pagina_numero = request.GET.get("page")
    pagina_obj = paginator_operaciones.get_page(pagina_numero)

    contexto = {"cliente": cliente, "operaciones": pagina_obj, "tipo_actual": tipo_actual}

    return render(request, "informacion_clientes.html", contexto)


@login_required
def obtener_cliente_json(request, id_cliente):
    # Obtengo los datos ya procesados y filtrados
    datos = obtener_datos_cliente(id_cliente)

    if datos:
        # Si el cliente existe y está activo, devuelvo sus datos en formato JSON
        return JsonResponse(datos)

    # Si el servicio me devuelve None (cliente no encontrado o inactivo), respondo con un error 404
    return JsonResponse({"Error": "Cliente no encontrado"}, status=404)


@login_required
def buscar_clientes_json(request):
    # Autocompletado del select de cliente: devuelve hasta 10 coincidencias activas.
    q = request.GET.get("q", "")
    return JsonResponse({"clientes": buscar_clientes(q)})


@login_required
@ensure_csrf_cookie
def informacion_operacion(request, id_operacion):
    operacion = get_object_or_404(Operacion.objects.con_totales(), id=id_operacion)

    from django.db.models import F
    pagos = operacion.pago_set.all().order_by("-fecha")
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

    # Armamos la lista estructurada de los productos para enviarlo al PDF
    lista_productos = []
    for d in detalles:
        if d.es_granel:
            # Los kilos se muestran sin ceros de mas y con la unidad explicita
            cantidad = f"{d.cantidad:.2f}".rstrip("0").rstrip(".") + " kg"
        else:
            cantidad = d.cantidad
        lista_productos.append({
            'cantidad': cantidad,
            'detalle': d.nombre_item,
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
        telefono=cliente.telefono if cliente.telefono else ""
    )

    pdf_bytes = pdf.generate_pdf()
    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    response["Content-Disposition"] = f'inline; filename="remito_{operacion.id}.pdf"'

    return response


def _contexto_edicion(operacion):
    """
    Arma los datos que el front necesita para precargar el carrito al editar
    una operación: ítems (con stock ajustado), fecha y método de pago inferido.
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
            })

    # El método de pago no se guarda: se infiere de los pagos. Con pagos
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
        "items": items,
    }


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

            # Modo edición (solo staff): reemplaza los ítems de una operación existente
            id_editar = datos.get("editar")
            if id_editar:
                if not request.user.is_staff:
                    return JsonResponse({"error": "Solo el personal autorizado puede editar operaciones."}, status=403)
                # Valido que la operación exista, sea de este cliente y de este tipo
                get_object_or_404(Operacion, id=id_editar, cliente=cliente, tipo_operacion="venta", activa=True)
                operacion = editar_operacion(id_editar, items, metodo_pago, fecha=fecha,
                                             cotizaciones_historicas=cotizaciones_historicas)
                messages.success(request, "Operación actualizada correctamente")
                return JsonResponse({"ok": True, "id_cliente": cliente.id, "id_operacion": operacion.id, "editada": True})

            # Delegamos toda la lógica de creación a la capa de servicios
            operacion = crear_operacion(cliente, items, metodo_pago, tipo_operacion, viaje, fecha=fecha,
                                        cotizaciones_historicas=cotizaciones_historicas)

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
            productos = productos.filter(nombre__icontains=q)

    if categoria_filtrada:
        productos = productos.filter(categoria=categoria_filtrada)

    productos = productos.order_by("nombre")

    # Cargo de a 6 productos para tener un alto de tabla acorde
    paginator_productos = Paginator(productos, 6)
    pagina_numero = request.GET.get("page")
    pagina_obj = paginator_productos.get_page(pagina_numero)

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
        "productos": pagina_obj,
        "q": q,
        "categoria": categoria_filtrada,
        "categorias": Producto.categorias,
        "granel": get_articulos_granel(),
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

            # Modo edición (solo staff): reemplaza los ítems de una compra existente
            id_editar = datos.get("editar")
            if id_editar:
                if not request.user.is_staff:
                    return JsonResponse({"error": "Solo el personal autorizado puede editar operaciones."}, status=403)
                get_object_or_404(Operacion, id=id_editar, cliente=cliente, tipo_operacion="compra", activa=True)
                operacion = editar_operacion(id_editar, items, metodo_pago, fecha=fecha,
                                             cotizaciones_historicas=cotizaciones_historicas)
                messages.success(request, "Compra actualizada correctamente")
                return JsonResponse({"ok": True, "id_cliente": cliente.id, "id_operacion": operacion.id, "editada": True})

            # El tipo se fuerza a "compra"; en compra el precio viene en cada item
            operacion = crear_operacion(cliente, items, metodo_pago, "compra", viaje, fecha=fecha,
                                        cotizaciones_historicas=cotizaciones_historicas)

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
            productos = productos.filter(nombre__icontains=q)

    if categoria_filtrada:
        productos = productos.filter(categoria=categoria_filtrada)

    productos = productos.order_by("nombre")

    paginator_productos = Paginator(productos, 6)
    pagina_numero = request.GET.get("page")
    pagina_obj = paginator_productos.get_page(pagina_numero)

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
        "productos": pagina_obj,
        "q": q,
        "categoria": categoria_filtrada,
        "categorias": Producto.categorias,
        "granel": get_articulos_granel(),
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
def viajes(request):
    if request.method == "POST":
        accion = request.POST.get("accion")

        try:
            if accion == "nuevo_viaje":
                # 1. Extracción de datos
                id_chofer = request.POST.get("id_chofer")
                id_vehiculo = request.POST.get("id_vehiculo")
                destinos = request.POST.getlist("destino")
                inicio_caja = request.POST.get("inicio_caja")
                fecha_inicio_viaje = request.POST.get("fecha_inicio_viaje")
                fecha_regreso_viaje = request.POST.get("fecha_regreso_viaje") or None

                # 2. Validación de presencia requerida por el backend (lo esencial)
                if not all([id_chofer, id_vehiculo, fecha_inicio_viaje]) or not destinos:
                    messages.error(request, "Faltan datos obligatorios para crear el viaje.")
                    return redirect("viajes")

                # 3. Delegación al servicio (donde apliqué las reglas del negocio)
                crear_viaje(id_chofer, id_vehiculo, destinos, inicio_caja, fecha_inicio_viaje, fecha_regreso_viaje)
                messages.success(request, "Viaje registrado exitosamente.")

            elif accion == "nuevo_chofer":
                nombre_chofer = request.POST.get("nombre_chofer", "")
                apellido_chofer = request.POST.get("apellido_chofer", "")
                
                # Delegación al servicio
                crear_chofer(nombre_chofer, apellido_chofer)
                messages.success(request, "Chofer registrado exitosamente.")

            elif accion == "nuevo_vehiculo":
                nombre_vehiculo = request.POST.get("nombre_vehiculo", "")
                patente_vehiculo = request.POST.get("patente_vehiculo", "")

                # Delegación al servicio
                crear_vehiculo(nombre_vehiculo, patente_vehiculo)
                messages.success(request, "Vehículo registrado exitosamente.")

        except ValueError as e:
            # Capturo cualquier error de validación proveniente de services.py
            messages.error(request, str(e))
        except Exception as e:
            # Capturo errores inesperados (ej: base de datos)
            messages.error(request, f"Ocurrió un error inesperado: {e}")

        return redirect("viajes")

    from django.utils import timezone
    from django.db.models import Q

    # Base de viajes activos (sirve para los conteos y para filtrar)
    base_viajes = obtener_viajes()
    hoy = timezone.localdate()

    # Conteos por estado, calculados sobre el total (no dependen de la búsqueda ni del chip).
    # Un viaje está "Finalizado" si tiene fecha de vuelta y ya pasó; en otro caso, "En curso".
    count_finalizado = base_viajes.filter(fecha_vuelta__isnull=False, fecha_vuelta__lt=hoy).count()
    count_total = base_viajes.count()
    count_en_curso = count_total - count_finalizado

    lista_viajes = base_viajes

    # Búsqueda por vehículo, chofer, destino o ID
    q = request.GET.get("q", "")
    if q:
        if q.isdigit():
            lista_viajes = lista_viajes.filter(id__icontains=q)
        else:
            lista_viajes = lista_viajes.filter(
                Q(vehiculo__nombre__icontains=q)
                | Q(vehiculo__patente__icontains=q)
                | Q(chofer__nombre__icontains=q)
                | Q(chofer__apellido__icontains=q)
                | Q(destinos__destino__icontains=q)
            ).distinct()

    # Filtro por estado (chips). Replico la lógica de la property Viaje.estado en la query.
    estado = request.GET.get("estado", "")
    if estado == "Finalizado":
        lista_viajes = lista_viajes.filter(fecha_vuelta__isnull=False, fecha_vuelta__lt=hoy)
    elif estado == "En curso":
        lista_viajes = lista_viajes.filter(Q(fecha_vuelta__isnull=True) | Q(fecha_vuelta__gte=hoy))

    paginator = Paginator(lista_viajes, 5)
    pagina_numero = request.GET.get("page")
    page_obj = paginator.get_page(pagina_numero)

    contexto = {
        "page_obj": page_obj,
        "choferes": obtener_choferes_activos(),
        "vehiculos": obtener_vehiculos_activos(),
        "q": q,
        "estado": estado,
        "count_total": count_total,
        "count_en_curso": count_en_curso,
        "count_finalizado": count_finalizado,
    }

    # Si es una petición AJAX (buscador/chips/paginación), devuelvo solo la tabla parcial
    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        return render(request, "tabla_viajes.html", contexto)

    return render(request, "viajes.html", contexto)


@login_required
def flota(request):
    if request.method == "POST":
        accion = request.POST.get("accion")

        try:
            if accion == "nuevo_chofer":
                crear_chofer(request.POST.get("nombre_chofer", ""), request.POST.get("apellido_chofer", ""))
                messages.success(request, "Chofer registrado exitosamente.")

            elif accion == "editar_chofer":
                editar_chofer(request.POST.get("id_chofer"), request.POST.get("nombre_chofer", ""),
                              request.POST.get("apellido_chofer", ""), True)
                messages.success(request, "Chofer actualizado correctamente.")

            elif accion == "eliminar_chofer":
                eliminar_chofer(request.POST.get("id_chofer"))
                messages.success(request, "Chofer eliminado correctamente.")

            elif accion == "nuevo_vehiculo":
                crear_vehiculo(request.POST.get("nombre_vehiculo", ""), request.POST.get("patente_vehiculo", ""))
                messages.success(request, "Vehículo registrado exitosamente.")

            elif accion == "editar_vehiculo":
                editar_vehiculo(request.POST.get("id_vehiculo"), request.POST.get("nombre_vehiculo", ""),
                                request.POST.get("patente_vehiculo", ""), True)
                messages.success(request, "Vehículo actualizado correctamente.")

            elif accion == "eliminar_vehiculo":
                eliminar_vehiculo(request.POST.get("id_vehiculo"))
                messages.success(request, "Vehículo eliminado correctamente.")

        except ValueError as e:
            # Capturo cualquier error de validación proveniente de services.py
            messages.error(request, str(e))
        except Exception as e:
            # Capturo errores inesperados (ej: base de datos)
            messages.error(request, f"Ocurrió un error inesperado: {e}")

        # Conservo el origen de navegacion para que el boton "Volver" siga apuntando bien
        origen = request.GET.get("origen", "")
        url_flota = reverse("flota")
        if origen:
            url_flota = f"{url_flota}?origen={origen}"
        return redirect(url_flota)

    contexto = {
        "choferes": obtener_choferes_activos(),
        "vehiculos": obtener_vehiculos_activos(),
        "pestaña": "viajes",
    }
    return render(request, "flota.html", contexto)


@login_required
def informacion_viaje(request, id_viaje):
    viaje = obtener_datos_viaje(id_viaje)

    if request.method == "POST":
        accion = request.POST.get("accion")
        if accion == "eliminar_viaje":
            try:
                eliminar_viaje(id_viaje)
                messages.success(request, "Viaje eliminado correctamente")
                return redirect("viajes")
            except Exception as e:
                messages.error(request, f"{e}")
                return redirect("informacion_viaje", id_viaje=id_viaje)
        
        elif accion == "editar_viaje":
            id_chofer = request.POST.get("id_chofer")
            id_vehiculo = request.POST.get("id_vehiculo")
            inicio_caja = request.POST.get("inicio_caja", 0)
            fecha_inicio = request.POST.get("fecha_inicio_viaje")
            fecha_vuelta = request.POST.get("fecha_regreso_viaje")
            destinos = request.POST.getlist("destino")

            try:
                editar_viaje(
                    id_viaje=id_viaje,
                    id_chofer=id_chofer,
                    id_vehiculo=id_vehiculo,
                    destinos=destinos,
                    inicio_caja=inicio_caja,
                    fecha_inicio=fecha_inicio,
                    fecha_vuelta=fecha_vuelta,
                )
                messages.success(request, "Viaje modificado exitosamente.")
            except ValueError as e:
                messages.error(request, str(e))
            except Exception as e:
                messages.error(request, f"Ocurrió un error inesperado: {e}")

            return redirect("informacion_viaje", id_viaje=id_viaje)

        elif accion == "nuevo_gasto":
            tipo_gasto = request.POST.get("tipo_gasto")
            monto_gasto = request.POST.get("monto_gasto")

            try:
                crear_gasto(id_viaje, tipo_gasto, monto_gasto)
                messages.success(request, "Gasto registrado exitosamente.")
            except ValueError as e:
                messages.error(request, str(e))
            except Exception as e:
                messages.error(request, f"Ocurrió un error inesperado: {e}")

            return redirect("informacion_viaje", id_viaje=id_viaje)

    # Operaciones asociadas al viaje, para el listado
    operaciones_viaje = (
        viaje.operaciones
        .con_totales()
        .select_related("cliente")
        .prefetch_related("detalleoperacion_set__producto", "detalleoperacion_set__cotizacion", "pago_set")
        .order_by("-fecha")
    )

    contexto = {
        'viaje': viaje,
        'pestaña': 'viajes',
        'choferes': incluir_asignado(obtener_choferes_activos(), viaje.chofer),
        'vehiculos': incluir_asignado(obtener_vehiculos_activos(), viaje.vehiculo),
        'operaciones': operaciones_viaje,
        'clientes': Cliente.objects.filter(activo=True).order_by("nombre", "apellido"),
    }
    return render(request, "informacion_viaje.html", contexto)


# Verifico que solo un administrador pueda ver la vista, tambien verifica que el usuario este logueado
@staff_member_required(login_url="inicio")
def deudores(request):
    q = request.GET.get("q", "")

    # Filtro por tipo de deuda: 'cobros' (ventas impagas) o 'pagos' (compras impagas).
    # Cualquier otro valor se ignora y se muestran todas.
    tipo = request.GET.get("tipo", "")
    if tipo not in ("cobros", "pagos"):
        tipo = ""

    lista_deudores = obtener_listado_deudores(q, tipo)

    # Las tarjetas de resumen muestran un solo lado: por defecto (y con el filtro de
    # cobros) el total a cobrar; con el filtro de pagos activo, el total a pagar.
    # Por eso los totales se calculan sobre el subconjunto del tipo correspondiente,
    # aunque la tabla sin filtro muestre ambos.
    modo = "pagar" if tipo == "pagos" else "cobrar"
    tipo_op_tarjetas = "compra" if modo == "pagar" else "venta"
    filas_tarjetas = [d for d in lista_deudores if d["tipo_operacion"] == tipo_op_tarjetas]

    # Totales sobre el listado completo (no solo la página) para las tarjetas de resumen
    total_pesos = sum((d["deuda_pesos"] or 0) for d in filas_tarjetas)
    total_usd_hoy = sum((d["deuda_dolar_actual"] or 0) for d in filas_tarjetas)
    total_miel_hoy = sum((d["kg_miel_actual"] or 0) for d in filas_tarjetas)

    # Las deudas se ordenan siempre de la más antigua a la más nueva
    lista_deudores.sort(key=lambda d: d["dias"], reverse=True)

    paginator_deudores = Paginator(lista_deudores, 8)
    pagina_numero = request.GET.get("page")
    pagina_obj = paginator_deudores.get_page(pagina_numero)

    contexto = {
        "deudores": pagina_obj,
        "q": q,
        "tipo": tipo,
        "modo": modo,
        "total_pesos": total_pesos,
        "total_usd_hoy": total_usd_hoy,
        "total_miel_hoy": total_miel_hoy,
        "total_deudores": len(lista_deudores),
    }

    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        # El AJAX refresca tanto las tarjetas (que cambian de a cobrar a pagar) como la tabla.
        return render(request, "deudores_ajax.html", contexto)
        
    return render(request, "deudores.html", contexto)


@login_required
def mercado_libre(request):
    if request.method == "POST":
        accion = request.POST.get("accion")

        try:
            if accion == "nuevo_viaje_reparto":
                # 1. Extraccion de datos del formulario
                id_chofer = request.POST.get("id_chofer")
                id_vehiculo = request.POST.get("id_vehiculo")
                gasto_combustible = request.POST.get("gasto_combustible_viaje_reparto")
                costo_empleado = request.POST.get("costo_empleado")
                valor_viaje = request.POST.get("valor_viaje")
                fecha_viaje_reparto = request.POST.get("fecha_viaje_reparto")
                destinos = request.POST.getlist("destino_reparto")

                # 2. Validacion de presencia de lo obligatorio (lo esencial en la vista)
                if not all([id_chofer, id_vehiculo, gasto_combustible, costo_empleado,
                            valor_viaje, fecha_viaje_reparto]) or not destinos:
                    messages.error(request, "Faltan datos obligatorios para crear el viaje de reparto.")
                    return redirect("mercado_libre")

                # 3. Delegacion al servicio (reglas de negocio y validacion)
                crear_viaje_reparto(id_chofer, id_vehiculo, gasto_combustible, costo_empleado,
                                    valor_viaje, fecha_viaje_reparto, destinos)
                messages.success(request, "Viaje de reparto registrado exitosamente.")

        except ValueError as e:
            # Captura los errores de validacion provenientes de services.py
            messages.error(request, str(e))
        except Exception as e:
            # Captura errores inesperados (ej: base de datos)
            messages.error(request, f"Ocurrió un error inesperado: {e}")

        return redirect("mercado_libre")

    from django.db.models import Q

    # Base de viajes de reparto activos
    lista_viajes = obtener_viajes_reparto()

    # Busqueda por vehiculo, chofer, destino o ID
    q = request.GET.get("q", "")
    if q:
        if q.isdigit():
            lista_viajes = lista_viajes.filter(id__icontains=q)
        else:
            lista_viajes = lista_viajes.filter(
                Q(vehiculo__nombre__icontains=q)
                | Q(vehiculo__patente__icontains=q)
                | Q(chofer__nombre__icontains=q)
                | Q(chofer__apellido__icontains=q)
                | Q(destinos__destinos_reparto__icontains=q)
            ).distinct()

    # Cargo de a 5 viajes
    paginator = Paginator(lista_viajes, 5)
    pagina_numero = request.GET.get("page")
    page_obj = paginator.get_page(pagina_numero)

    contexto = {
        "page_obj": page_obj,
        "choferes": obtener_choferes_activos(),
        "vehiculos": obtener_vehiculos_activos(),
        "q": q,
    }

    # Si es una peticion AJAX (buscador/paginacion), devuelvo solo la tabla parcial
    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        return render(request, "tabla_viajes_mercado_libre.html", contexto)

    return render(request, "mercado_libre.html", contexto)


@login_required
def informacion_viaje_reparto(request, id_viaje_reparto):
    viaje_reparto = obtener_datos_viaje_reparto(id_viaje_reparto)

    if request.method == "POST":
        accion = request.POST.get("accion")

        if accion == "eliminar_viaje_reparto":
            try:
                eliminar_viaje_reparto(id_viaje_reparto)
                messages.success(request, "Viaje de reparto eliminado correctamente")
                return redirect("mercado_libre")
            except Exception as e:
                messages.error(request, f"{e}")
                return redirect("informacion_viaje_reparto", id_viaje_reparto=id_viaje_reparto)

        elif accion == "editar_viaje_reparto":
            id_chofer = request.POST.get("id_chofer")
            id_vehiculo = request.POST.get("id_vehiculo")
            gasto_combustible = request.POST.get("gasto_combustible_viaje_reparto")
            costo_empleado = request.POST.get("costo_empleado")
            valor_viaje = request.POST.get("valor_viaje")
            fecha_viaje_reparto = request.POST.get("fecha_viaje_reparto")
            destinos = request.POST.getlist("destino_reparto")

            try:
                editar_viaje_reparto(
                    id_viaje_reparto=id_viaje_reparto,
                    id_chofer=id_chofer,
                    id_vehiculo=id_vehiculo,
                    gasto_combustible=gasto_combustible,
                    costo_empleado=costo_empleado,
                    valor_viaje=valor_viaje,
                    fecha_viaje_reparto=fecha_viaje_reparto,
                    destinos=destinos,
                )
                messages.success(request, "Viaje de reparto modificado exitosamente.")
            except ValueError as e:
                messages.error(request, str(e))
            except Exception as e:
                messages.error(request, f"Ocurrió un error inesperado: {e}")

            return redirect("informacion_viaje_reparto", id_viaje_reparto=id_viaje_reparto)

        elif accion == "nuevo_gasto_reparto":
            tipo_gasto = request.POST.get("tipo_gasto")
            monto_gasto = request.POST.get("monto_gasto")

            try:
                crear_gasto_viaje_reparto(id_viaje_reparto, tipo_gasto, monto_gasto)
                messages.success(request, "Gasto registrado exitosamente.")
            except ValueError as e:
                messages.error(request, str(e))
            except Exception as e:
                messages.error(request, f"Ocurrió un error inesperado: {e}")

            return redirect("informacion_viaje_reparto", id_viaje_reparto=id_viaje_reparto)

    contexto = {
        "viaje_reparto": viaje_reparto,
        "pestaña": "viajes",
        "choferes": incluir_asignado(obtener_choferes_activos(), viaje_reparto.chofer),
        "vehiculos": incluir_asignado(obtener_vehiculos_activos(), viaje_reparto.vehiculo),
    }
    return render(request, "informacion_viaje_reparto.html", contexto)


@login_required
def viaje_cereales(request):
    if request.method == "POST":
        accion = request.POST.get("accion")

        try:
            if accion == "nuevo_viaje_cereal":
                # 1. Extraccion de datos del formulario
                id_cliente = request.POST.get("id_cliente")
                id_chofer = request.POST.get("id_chofer")
                id_vehiculo = request.POST.get("id_vehiculo")
                tipo_cereal = request.POST.get("tipo_cereal")
                codigo_trazabilidad = request.POST.get("codigo_trazabilidad")
                toneladas = request.POST.get("toneladas")
                precio_tonelada = request.POST.get("precio_tonelada")
                # El porcentaje es opcional: si llega vacio lo paso como None
                porcentaje_chofer = request.POST.get("porcentaje_chofer") or None
                fecha_viaje_cereal = request.POST.get("fecha_viaje_cereal")
                destinos = request.POST.getlist("destino")

                # 2. Validacion de presencia de lo obligatorio (lo esencial en la vista)
                if not all([id_cliente, id_chofer, id_vehiculo, tipo_cereal, codigo_trazabilidad,
                            toneladas, precio_tonelada, fecha_viaje_cereal]) or not destinos:
                    messages.error(request, "Faltan datos obligatorios para crear el viaje de cereal.")
                    return redirect("viajes_cereales")

                # 3. Delegacion al servicio (reglas de negocio y validacion con regex)
                crear_viaje_cereal(id_cliente, id_chofer, id_vehiculo, tipo_cereal, codigo_trazabilidad,
                                   toneladas, precio_tonelada, porcentaje_chofer, fecha_viaje_cereal, destinos)
                messages.success(request, "Viaje de cereal registrado exitosamente.")

        except ValueError as e:
            # Captura los errores de validacion provenientes de services.py
            messages.error(request, str(e))
        except Exception as e:
            # Captura errores inesperados (ej: base de datos)
            messages.error(request, f"Ocurrió un error inesperado: {e}")

        return redirect("viajes_cereales")

    from django.db.models import Q

    lista_viajes = obtener_viajes_cereales()

    # Busqueda por vehiculo, chofer, tipo de cereal, destino o ID
    q = request.GET.get("q", "")
    if q:
        if q.isdigit():
            lista_viajes = lista_viajes.filter(id__icontains=q)
        else:
            lista_viajes = lista_viajes.filter(
                Q(vehiculo__nombre__icontains=q)
                | Q(vehiculo__patente__icontains=q)
                | Q(chofer__nombre__icontains=q)
                | Q(chofer__apellido__icontains=q)
                | Q(tipo_cereal__icontains=q)
                | Q(destinos__destino__icontains=q)
            ).distinct()

    # Cargo de a 5 viajes
    paginator = Paginator(lista_viajes, 5)
    pagina_numero = request.GET.get("page")
    page_obj = paginator.get_page(pagina_numero)

    contexto = {
        "page_obj": page_obj,
        "choferes": obtener_choferes_activos(),
        "vehiculos": obtener_vehiculos_activos(),
        "cereales": ViajeCereal.cereales,
        "q": q,
    }

    # Si es una peticion AJAX (buscador/chips/paginacion), devuelvo solo la tabla parcial
    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        return render(request, "tabla_viajes_cereales.html", contexto)

    return render(request, "viajes_cereales.html", contexto)


@login_required
def informacion_viaje_cereal(request, id_viaje_cereal):
    viaje_cereal = obtener_datos_viaje_cereal(id_viaje_cereal)

    if request.method == "POST":
        accion = request.POST.get("accion")

        if accion == "eliminar_viaje_cereal":
            try:
                eliminar_viaje_cereal(id_viaje_cereal)
                messages.success(request, "Viaje de cereal eliminado correctamente")
                return redirect("viajes_cereales")
            except Exception as e:
                messages.error(request, f"{e}")
                return redirect("informacion_viaje_cereal", id_viaje_cereal=id_viaje_cereal)

        elif accion == "editar_viaje_cereal":
            id_cliente = request.POST.get("id_cliente")
            id_chofer = request.POST.get("id_chofer")
            id_vehiculo = request.POST.get("id_vehiculo")
            tipo_cereal = request.POST.get("tipo_cereal")
            codigo_trazabilidad = request.POST.get("codigo_trazabilidad")
            toneladas = request.POST.get("toneladas")
            precio_tonelada = request.POST.get("precio_tonelada")
            porcentaje_chofer = request.POST.get("porcentaje_chofer") or None
            fecha_viaje_cereal = request.POST.get("fecha_viaje_cereal")
            destinos = request.POST.getlist("destino")

            try:
                editar_viaje_cereal(
                    id_viaje_cereal=id_viaje_cereal,
                    id_cliente=id_cliente,
                    id_chofer=id_chofer,
                    id_vehiculo=id_vehiculo,
                    tipo_cereal=tipo_cereal,
                    codigo_trazabilidad=codigo_trazabilidad,
                    toneladas=toneladas,
                    precio_tonelada=precio_tonelada,
                    porcentaje_chofer=porcentaje_chofer,
                    fecha_viaje_cereal=fecha_viaje_cereal,
                    destinos=destinos,
                )
                messages.success(request, "Viaje de cereal modificado exitosamente.")
            except ValueError as e:
                messages.error(request, str(e))
            except Exception as e:
                messages.error(request, f"Ocurrió un error inesperado: {e}")

            return redirect("informacion_viaje_cereal", id_viaje_cereal=id_viaje_cereal)

        elif accion == "nuevo_gasto_cereal":
            tipo_gasto = request.POST.get("tipo_gasto")
            monto_gasto = request.POST.get("monto_gasto")

            try:
                crear_gasto_viaje_cereal(id_viaje_cereal, tipo_gasto, monto_gasto)
                messages.success(request, "Gasto registrado exitosamente.")
            except ValueError as e:
                messages.error(request, str(e))
            except Exception as e:
                messages.error(request, f"Ocurrió un error inesperado: {e}")

            return redirect("informacion_viaje_cereal", id_viaje_cereal=id_viaje_cereal)

    contexto = {
        "viaje_cereal": viaje_cereal,
        "pestaña": "viajes",
        "choferes": incluir_asignado(obtener_choferes_activos(), viaje_cereal.chofer),
        "vehiculos": incluir_asignado(obtener_vehiculos_activos(), viaje_cereal.vehiculo),
        "cereales": ViajeCereal.cereales,
    }
    return render(request, "informacion_viaje_cereal.html", contexto)


def cerrar_sesion(request):
    auth_logout(request)
    return redirect("login")