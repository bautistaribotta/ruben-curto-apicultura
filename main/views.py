import json
from datetime import date, timedelta

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
from django.utils.dateparse import parse_date
from django.utils.formats import date_format
from django.contrib.humanize.templatetags.humanize import intcomma
from django.template.defaultfilters import floatformat

from .models import (Cliente, Producto, Operacion, DetalleOperacion, Pago, Cotizaciones, Empleado,
                     Vehiculo, Viaje, ViajeCereal, ViajeReparto, Gasto, GastoViajeCereal, GastoViajeReparto,
                     periodo_actual)
from .pdf_services import Remito, ResumenCuenta
from .services import (nuevo_producto, editar_producto, eliminar_producto, nuevo_cliente, editar_cliente,
                       eliminar_cliente, buscar_clientes, get_cotizacion_dolar_oficial, get_cotizaciones, get_total_kilos_granel, get_articulos_granel, actualizar_cotizacion, obtener_datos_cliente,
                       obtener_datos_producto, modificar_stock, crear_operacion, editar_operacion, servicio_cancelar_operacion,
                       obtener_movimientos_cuenta_corriente,
                       obtener_listado_deudores, _iniciales, filtro_nombre_apellido, filtro_tokens, crear_empleado, crear_vehiculo, crear_viaje, obtener_empleados_activos,
                       obtener_vehiculos_activos, obtener_viajes, obtener_datos_viaje, editar_viaje, eliminar_viaje, crear_gasto,
                       editar_gasto_viaje, eliminar_gasto_viaje,
                       incluir_asignado,
                       opciones_empleados_filtro, opciones_vehiculos_filtro,
                       opciones_destinos_viaje, opciones_destinos_cereal, opciones_destinos_reparto_filtro,
                       nombre_empleado_filtro, nombre_vehiculo_filtro, nombre_destino_reparto_filtro,
                       editar_empleado, eliminar_empleado, obtener_datos_empleado, crear_pago_empleado, fijar_sueldo_empleado,
                       editar_pago_empleado, eliminar_pago_empleado,
                       obtener_gastos_empleado, obtener_viajes_empleado, TIPOS_VIAJE_EMPLEADO,
                       obtener_cuenta_corriente, resolver_granularidad_pagos, resolver_ancla_pagos,
                       rango_periodo_pagos, desplazar_periodo_pagos, etiqueta_periodo_pagos,
                       editar_vehiculo, eliminar_vehiculo,
                       crear_registro_km, editar_registro_km, eliminar_registro_km, obtener_registros_km,
                       crear_seguro, editar_seguro, eliminar_seguro, obtener_seguros,
                       crear_vtv, editar_vtv, eliminar_vtv, obtener_vtvs,
                       crear_servis, editar_servis, eliminar_servis, obtener_servicios,
                       crear_observacion, editar_observacion, eliminar_observacion, obtener_observaciones,
                       crear_viaje_cereal, obtener_viajes_cereales, obtener_viajes_cereal_de_cliente,
                       obtener_datos_viaje_cereal,
                       editar_viaje_cereal, eliminar_viaje_cereal, crear_gasto_viaje_cereal,
                       obtener_resumen_cereal, marcar_pago_viaje_cereal,
                       crear_viaje_reparto, obtener_viajes_reparto, obtener_datos_viaje_reparto,
                       editar_viaje_reparto, eliminar_viaje_reparto, crear_gasto_viaje_reparto,
                       obtener_resumen_reparto, marcar_pago_viaje_reparto,
                       obtener_destinos_reparto, crear_destino_reparto, editar_destino_reparto,
                       eliminar_destino_reparto,
                       obtener_casas, obtener_datos_casa, crear_casa, editar_casa, eliminar_casa,
                       crear_contrato, editar_contrato, eliminar_contrato, obtener_contrato_de_casa,
                       obtener_detalle_alquiler,
                       crear_gasto_casa, editar_gasto_casa, eliminar_gasto_casa,
                       obtener_resumen_alquileres, marcar_pago_alquiler, resolver_periodo,
                       mes_desplazado, FILTROS_ALQUILERES)


def _pagado_del_formulario(request):
    """Lee la casilla de cobro de los slide-over de viajes (reparto y cereal).

    El estado de pago lo maneja solo el staff, asi que para el resto devuelvo None:
    los servicios de edicion interpretan ese None como "no toques el campo" y el
    viaje conserva el estado que ya tenia en vez de volver a impago.
    """
    if not request.user.is_staff:
        return None
    # Un checkbox sin marcar directamente no viaja en el POST: la ausencia es "no pagado"
    return request.POST.get("pagado") is not None


def _url_con_gasto(url, id_gasto):
    """Marca en la vuelta cual fue el gasto que se acaba de tocar.

    Despues del POST la pagina se recarga entera y la lista de gastos vuelve al
    principio del scroll: sin esta marca el usuario ve un cartel verde pero no
    ve que cambio. Con el id en la URL, el front busca esa fila, la trae a la
    vista y la resalta un segundo.

    Al eliminar no hay fila que marcar, asi que la URL vuelve limpia.
    """
    if not id_gasto:
        return url
    separador = "&" if "?" in url else "?"
    return f"{url}{separador}gasto={id_gasto}"


def _rango_fechas(request):
    """Lee y normaliza el rango de fechas del filtro (chip + popover) reutilizado
    en las vistas de viajes. Reciclado de la logica del filtro de Deudas.

    Devuelve (desde, hasta, ctx) donde desde/hasta son date o None (ya listos para
    filtrar el queryset) y ctx trae desde/hasta en ISO y fecha_label para la
    plantilla (rellenan el popover y pintan el chip ya al cargar la pagina).
    """
    desde = parse_date(request.GET.get("desde", ""))
    hasta = parse_date(request.GET.get("hasta", ""))
    # Si el usuario invierte el rango, lo normalizo para no devolver un listado vacio.
    if desde and hasta and desde > hasta:
        desde, hasta = hasta, desde

    if desde and hasta and desde == hasta:
        fecha_label = desde.strftime("%d/%m/%Y")
    elif desde and hasta:
        fecha_label = f"{desde.strftime('%d/%m')} – {hasta.strftime('%d/%m/%Y')}"
    elif desde:
        fecha_label = f"Desde {desde.strftime('%d/%m/%Y')}"
    elif hasta:
        fecha_label = f"Hasta {hasta.strftime('%d/%m/%Y')}"
    else:
        fecha_label = "Fechas"

    ctx = {
        "desde": desde.isoformat() if desde else "",
        "hasta": hasta.isoformat() if hasta else "",
        "fecha_label": fecha_label,
    }
    return desde, hasta, ctx


def _rango_gastos(request):
    """Igual que _rango_fechas pero etiquetando el mes entero por su nombre.

    Los gastos de una casa se miran casi siempre de a un mes, y ahi "Julio 2026"
    se lee mejor que "01/07 – 31/07/2026". Como el popover manda el mes expandido
    a sus dos extremos, el mes entero se reconoce por las fechas y no hace falta
    ningun parametro nuevo.

    Va aparte y no dentro de _rango_fechas para no cambiarle la etiqueta a
    deudores y a viajes, que no ofrecen el modo mes.
    """
    desde, hasta, ctx = _rango_fechas(request)

    if (desde and hasta and desde.day == 1
            and (desde.year, desde.month) == (hasta.year, hasta.month)
            and hasta + timedelta(days=1) == mes_desplazado(desde, 1)):
        ctx["fecha_label"] = date_format(desde, "F Y").capitalize()

    return desde, hasta, ctx


def _rango_fechas_empleado(request):
    """Igual que _rango_fechas pero con el año en curso como valor por defecto.

    El perfil del empleado arranca mostrando el año actual, no txdo el historial.
    Para poder distinguir "recien entre a la pagina" de "vacie el filtro a mano"
    miro si los parametros vinieron en la URL: informacion_empleado.js los manda
    siempre, aunque esten vacios, justamente para poder ver el historial completo.
    """
    if "desde" in request.GET or "hasta" in request.GET:
        return _rango_fechas(request)

    año = timezone.localdate().year
    desde = date(año, 1, 1)
    hasta = date(año, 12, 31)
    ctx = {
        "desde": desde.isoformat(),
        "hasta": hasta.isoformat(),
        "fecha_label": f"Año {año}",
    }
    return desde, hasta, ctx


def _contexto_pagos_empleado(request, empleado):
    """Arma el bloque de pagos del perfil para el periodo pedido en la URL.

    La granularidad ('semana' o 'mes') y el periodo (su primer dia, en
    'pagos_ancla') viajan por la URL, asi el bloque es enlazable y sobrevive al
    POST de un pago nuevo. El periodo se identifica siempre por su primer dia.
    """
    granularidad = resolver_granularidad_pagos(request.GET.get("pagos_gran"))
    inicio = resolver_ancla_pagos(request.GET.get("pagos_ancla"), granularidad)
    desde, hasta = rango_periodo_pagos(inicio, granularidad)

    cuenta = obtener_cuenta_corriente(empleado, desde, hasta)

    # El saldo inicial/final del periodo se calcula sobre todas las filas; recien
    # despues pagino de a 8 para no romper esos bordes de la cuenta.
    paginador_pagos = Paginator(cuenta["filas"], 8)
    pagina_pagos = paginador_pagos.get_page(request.GET.get("pagos_page"))

    return {
        "pagos": pagina_pagos,
        "cuenta": cuenta,
        "pagos_granularidad": granularidad,
        "pagos_inicio": inicio,
        "pagos_fin": hasta,
        "pagos_label": etiqueta_periodo_pagos(inicio, hasta, granularidad),
        "pagos_ancla_anterior": desplazar_periodo_pagos(inicio, granularidad, -1),
        "pagos_ancla_siguiente": desplazar_periodo_pagos(inicio, granularidad, 1),
    }


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


@staff_member_required
def empleados(request):
    if request.method == "POST":
        accion = request.POST.get("accion")
        id_eliminar = request.POST.get("id_eliminar")

        try:
            if accion == "eliminar" and id_eliminar:
                eliminar_empleado(id_eliminar)
                messages.success(request, "Empleado eliminado correctamente")
            else:
                id_empleado = request.POST.get("id_empleado")
                nombre = request.POST.get("nombre", "")
                apellido = request.POST.get("apellido", "")

                # Si viene id_empleado es una EDICION, si no es un NUEVO empleado
                if id_empleado:
                    editar_empleado(id_empleado, nombre, apellido, True)
                    messages.success(request, "Empleado editado correctamente")
                else:
                    crear_empleado(nombre, apellido)
                    messages.success(request, "Empleado agregado correctamente")
        except ValueError as e:
            # Errores de validacion provenientes de services.py
            messages.error(request, str(e))
        except Exception as e:
            messages.error(request, f"Ocurrió un error inesperado: {e}")

        return redirect("empleados")

    q = request.GET.get("q", "")

    empleados_list = Empleado.objects.filter(activo=True)

    if q:
        if q.isdigit():
            empleados_list = empleados_list.filter(id__icontains=q)
        else:
            empleados_list = empleados_list.filter(filtro_nombre_apellido(q))

    empleados_list = empleados_list.order_by("nombre")

    paginator_empleados = Paginator(empleados_list, 10)
    pagina_numero = request.GET.get("page")
    pagina_obj = paginator_empleados.get_page(pagina_numero)

    contexto = {"empleados": pagina_obj, "q": q}

    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        return render(request, "tabla_empleados.html", contexto)

    return render(request, "empleados.html", contexto)


@staff_member_required
def informacion_empleado(request, id_empleado):
    empleado = get_object_or_404(Empleado, id=id_empleado, activo=True)

    if request.method == "POST":
        # El perfil abre los mismos paneles que el listado, asi que reutiliza sus
        # servicios: eliminar es una baja logica (activo=False), igual que alli.
        accion = request.POST.get("accion")

        try:
            if accion == "eliminar":
                eliminar_empleado(empleado.id)
                messages.success(request, "Empleado eliminado correctamente")
                # El perfil ya no existe para el usuario: vuelvo al listado
                return redirect("empleados")

            if accion == "pago":
                # El mismo modal da de alta y edita: si viene pago_id es una
                # edicion, si no un alta.
                pago_id = request.POST.get("pago_id")
                if pago_id:
                    editar_pago_empleado(
                        pago_id,
                        empleado.id,
                        request.POST.get("monto"),
                        request.POST.get("observaciones", ""),
                        request.POST.get("fecha"),
                    )
                    messages.success(request, "Pago actualizado correctamente")
                else:
                    crear_pago_empleado(
                        empleado.id,
                        request.POST.get("monto"),
                        request.POST.get("observaciones", ""),
                        request.POST.get("fecha"),
                    )
                    messages.success(request, "Pago registrado correctamente")
                return redirect("informacion_empleado", id_empleado=empleado.id)

            if accion == "eliminar_pago":
                eliminar_pago_empleado(request.POST.get("id_eliminar"), empleado.id)
                messages.success(request, "Pago eliminado correctamente")
                return redirect("informacion_empleado", id_empleado=empleado.id)

            if accion == "sueldo":
                fijar_sueldo_empleado(empleado.id, request.POST.get("sueldo"))
                messages.success(request, "Sueldo actualizado correctamente")
                return redirect("informacion_empleado", id_empleado=empleado.id)

            editar_empleado(
                empleado.id,
                request.POST.get("nombre", ""),
                request.POST.get("apellido", ""),
                True,
            )
            messages.success(request, "Empleado editado correctamente")
        except ValueError as e:
            # Errores de validacion provenientes de services.py
            messages.error(request, str(e))
        except Exception as e:
            messages.error(request, f"Ocurrió un error inesperado: {e}")

        return redirect("informacion_empleado", id_empleado=empleado.id)

    # Rango de fechas del chip. Por defecto, el año en curso.
    desde, hasta, ctx_fechas = _rango_fechas_empleado(request)

    # Gastos rendidos y viajes, ambos acotados al mismo rango de fechas.
    gastos = obtener_gastos_empleado(empleado, desde, hasta)

    tipo = request.GET.get("tipo", "todos")
    if tipo not in TIPOS_VIAJE_EMPLEADO:
        tipo = "todos"

    filas_viajes, conteos_viajes = obtener_viajes_empleado(empleado, tipo, desde, hasta)
    paginador_viajes = Paginator(filas_viajes, 10)
    pagina_viajes = paginador_viajes.get_page(request.GET.get("page_viajes"))

    # Las pestañas se arman aca y no en la plantilla: Django no sabe buscar en un
    # diccionario con una clave variable.
    pestañas_viajes = [{
        "clave": "todos",
        "etiqueta": "Todos",
        "cuenta": conteos_viajes["todos"],
        "activa": tipo == "todos",
    }]
    pestañas_viajes += [{
        "clave": clave,
        "etiqueta": config["etiqueta"],
        "cuenta": conteos_viajes[clave],
        "activa": tipo == clave,
    } for clave, config in TIPOS_VIAJE_EMPLEADO.items()]

    es_ajax = request.headers.get("x-requested-with") == "XMLHttpRequest"

    # El bloque de pagos se refresca solo con su propio filtro (semana/mes +
    # flechas), asi que ante frag=pagos devuelvo unicamente ese pedazo.
    if es_ajax and request.GET.get("frag") == "pagos":
        return render(request, "pagos_empleado.html", {
            "empleado": empleado,
            **_contexto_pagos_empleado(request, empleado),
        })

    contexto = {
        "empleado": empleado,
        "gastos": gastos,
        "viajes": pagina_viajes,
        "tipo": tipo,
        "pestañas_viajes": pestañas_viajes,
        "total_viajes_periodo": conteos_viajes["todos"],
        **ctx_fechas,
    }

    # Las pestañas de tipo, el filtro de fechas y la paginacion de viajes van por
    # AJAX: devuelvo solo el bloque de gastos + viajes, que es lo que depende de
    # esos filtros. Los pagos tienen su propio filtro, asi que quedan afuera.
    if es_ajax:
        return render(request, "secciones_empleado.html", contexto)

    contexto.update(_contexto_pagos_empleado(request, empleado))

    return render(request, "informacion_empleado.html", contexto)


@staff_member_required
def obtener_empleado_json(request, id_empleado):
    datos = obtener_datos_empleado(id_empleado)

    if datos:
        # Si el empleado existe y está activo, devuelvo sus datos en formato JSON
        return JsonResponse(datos)

    # Si no lo encuentro o está inactivo, devuelvo un error 404
    return JsonResponse({"Error": "Empleado no encontrado"}, status=404)


@login_required
@ensure_csrf_cookie
def actualizar_cotizacion_ajax(request):
    # Las cotizaciones las maneja solo el personal administrativo. El resto ve
    # las tarjetas sin la edicion, pero el chequeo va aca porque la plantilla
    # sola no frena un POST armado a mano contra esta URL.
    if not request.user.is_staff:
        return JsonResponse({"error": "No tiene permiso para modificar las cotizaciones"}, status=403)

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
            # Si no, buscamos por nombre (multi-palabra: "cera laminada"
            # encuentra "Cera Estampada Laminada")
            productos = productos.filter(filtro_tokens(q, "nombre"))

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
            # Buscar por nombre y apellido concatenados ("carola diaz")
            clientes_list = clientes_list.filter(filtro_nombre_apellido(q))

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

    # Los fletes de cereal del cliente van en su propia tabla, tambien de a 5.
    # Usan un parametro aparte ("page_cereal") para que avanzar de pagina en una
    # tabla no reinicie la otra: las dos conviven en la misma URL.
    paginator_cereal = Paginator(obtener_viajes_cereal_de_cliente(cliente), 5)
    pagina_cereal = paginator_cereal.get_page(request.GET.get("page_cereal"))

    contexto = {
        "cliente": cliente,
        "operaciones": pagina_obj,
        "tipo_actual": tipo_actual,
        "viajes_cereal": pagina_cereal,
    }

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

    # Los usuarios no administrativos reciben el remito sin ningun importe: no
    # se calculan los subtotales ni el total, asi el PDF no los contiene
    mostrar_importes = request.user.is_staff

    # Armamos la lista estructurada de los productos para enviarlo al PDF
    lista_productos = []
    total = 0
    for d in detalles:
        if d.es_granel:
            # Los kilos se muestran sin ceros de mas y con la unidad explicita
            cantidad = f"{d.cantidad:.2f}".rstrip("0").rstrip(".") + " kg"
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


def _rango_resumen_cuenta(request):
    """Lee el rango de fechas que manda el modal de resumen de cuenta.

    Devuelve (desde, hasta) ya normalizados: si el usuario invierte el rango lo
    doy vuelta, para que el resumen no salga vacio por un error de tipeo.
    """
    desde = parse_date(request.GET.get("desde", ""))
    hasta = parse_date(request.GET.get("hasta", ""))
    if desde and hasta and desde > hasta:
        desde, hasta = hasta, desde
    return desde, hasta


@login_required
def generar_resumen_cuenta(request, id_cliente):
    """Imprime el resumen de cuenta corriente del cliente en formato Debe / Haber.

    Solo staff: el resumen es enteramente plata, asi que a diferencia del remito
    no tiene una version sin importes que tenga sentido emitir.
    """
    if not request.user.is_staff:
        messages.error(request, "No tenés permiso para imprimir resúmenes de cuenta.")
        return redirect("informacion_clientes", id_cliente=id_cliente)

    cliente = get_object_or_404(Cliente, id=id_cliente, activo=True)
    desde, hasta = _rango_resumen_cuenta(request)
    movimientos, totales = obtener_movimientos_cuenta_corriente(cliente, desde, hasta)

    pdf = ResumenCuenta(
        cliente=cliente,
        movimientos=movimientos,
        totales=totales,
        desde=desde,
        hasta=hasta,
        fecha_emision=timezone.localdate(),
    )

    response = HttpResponse(pdf.generate_pdf(), content_type="application/pdf")
    response["Content-Disposition"] = f'inline; filename="resumen_cuenta_{cliente.id}.pdf"'
    return response


@login_required
def contar_movimientos_cuenta_json(request, id_cliente):
    """Cuenta los movimientos del rango para el modal de resumen de cuenta.

    El modal lo consulta mientras el usuario elige las fechas, asi sabe si el PDF
    va a traer algo antes de imprimirlo. Devuelve solo el conteo, no los importes.
    """
    if not request.user.is_staff:
        return JsonResponse({"error": "No tenés permiso para ver la cuenta corriente."}, status=403)

    cliente = get_object_or_404(Cliente, id=id_cliente, activo=True)
    desde, hasta = _rango_resumen_cuenta(request)
    movimientos, _ = obtener_movimientos_cuenta_corriente(cliente, desde, hasta)
    return JsonResponse({"cantidad": len(movimientos)})


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
                id_empleado = request.POST.get("id_empleado")
                id_vehiculo = request.POST.get("id_vehiculo")
                destinos = request.POST.getlist("destino")
                inicio_caja = request.POST.get("inicio_caja")
                fecha_inicio_viaje = request.POST.get("fecha_inicio_viaje")
                fecha_regreso_viaje = request.POST.get("fecha_regreso_viaje") or None

                # 2. Validación de presencia requerida por el backend (lo esencial)
                if not all([id_empleado, id_vehiculo, fecha_inicio_viaje]) or not destinos:
                    messages.error(request, "Faltan datos obligatorios para crear el viaje.")
                    return redirect("viajes")

                # 3. Delegación al servicio (donde apliqué las reglas del negocio)
                crear_viaje(id_empleado, id_vehiculo, destinos, inicio_caja, fecha_inicio_viaje, fecha_regreso_viaje)
                messages.success(request, "Viaje registrado exitosamente.")

            elif accion == "nuevo_empleado":
                nombre_empleado = request.POST.get("nombre_empleado", "")
                apellido_empleado = request.POST.get("apellido_empleado", "")
                
                # Delegación al servicio
                crear_empleado(nombre_empleado, apellido_empleado)
                messages.success(request, "Empleado registrado exitosamente.")

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

    # Filtros por entidad (chip -> modal selector). Reemplazan al buscador de texto:
    # el usuario elige empleado, vehiculo o destino de una lista en vez de tipear.
    empleado = request.GET.get("empleado", "")
    vehiculo = request.GET.get("vehiculo", "")
    destino = request.GET.get("destino", "")
    if empleado.isdigit():
        lista_viajes = lista_viajes.filter(empleado_id=empleado)
    if vehiculo.isdigit():
        lista_viajes = lista_viajes.filter(vehiculo_id=vehiculo)
    if destino:
        lista_viajes = lista_viajes.filter(destinos__destino=destino).distinct()

    # Filtro por estado (chips). Replico la lógica de la property Viaje.estado en la query.
    estado = request.GET.get("estado", "")
    if estado == "Finalizado":
        lista_viajes = lista_viajes.filter(fecha_vuelta__isnull=False, fecha_vuelta__lt=hoy)
    elif estado == "En curso":
        lista_viajes = lista_viajes.filter(Q(fecha_vuelta__isnull=True) | Q(fecha_vuelta__gte=hoy))

    # Filtro por rango de fechas (chip + popover). Los viajes miel/cera tienen dos
    # fechas; se filtra por la de inicio (la salida), que siempre existe.
    desde, hasta, ctx_fechas = _rango_fechas(request)
    if desde:
        lista_viajes = lista_viajes.filter(fecha_inicio__gte=desde)
    if hasta:
        lista_viajes = lista_viajes.filter(fecha_inicio__lte=hasta)

    paginator = Paginator(lista_viajes, 5)
    pagina_numero = request.GET.get("page")
    page_obj = paginator.get_page(pagina_numero)

    contexto = {
        "page_obj": page_obj,
        "empleados": obtener_empleados_activos(),
        "vehiculos": obtener_vehiculos_activos(),
        "empleado": empleado,
        "empleado_nombre": nombre_empleado_filtro(empleado),
        "vehiculo": vehiculo,
        "vehiculo_nombre": nombre_vehiculo_filtro(vehiculo),
        "destino": destino,
        "destino_nombre": destino,
        "empleados_filtro": opciones_empleados_filtro(),
        "vehiculos_filtro": opciones_vehiculos_filtro(),
        "destinos_filtro": opciones_destinos_viaje(),
        "estado": estado,
        "count_total": count_total,
        "count_en_curso": count_en_curso,
        "count_finalizado": count_finalizado,
        **ctx_fechas,
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
            # Los empleados ya no se gestionan desde flota: alta, edicion y baja
            # viven en la vista de empleados. Aca solo quedan los vehiculos.
            if accion == "nuevo_vehiculo":
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

        return redirect("flota")

    contexto = {
        "vehiculos": obtener_vehiculos_activos(),
        "pestaña": "viajes",
    }
    return render(request, "flota.html", contexto)


def _con_dias_restantes(registros, hoy):
    """Anota en cada registro con vigencia el estado de su vencimiento.

    Devuelve la lista ya evaluada (no un queryset) porque el template vuelve a
    recorrerla y los atributos calculados se perderian si se re-consultara. En
    cada registro deja:
      - dias_restantes: dias hasta el fin (negativo si ya venció)
      - dias_abs: la misma cantidad en positivo, para redactar el texto
      - nivel: "vencido", "proximo" (vence dentro de 30 dias) o "vigente"
    """
    lista = list(registros)
    for registro in lista:
        dias = (registro.fin - hoy).days
        registro.dias_restantes = dias
        registro.dias_abs = abs(dias)
        if dias < 0:
            registro.nivel = "vencido"
        elif dias <= 30:
            registro.nivel = "proximo"
        else:
            registro.nivel = "vigente"
    return lista


@login_required
def informacion_vehiculo(request, id_vehiculo):
    """Perfil de un vehiculo: kilometraje, seguros, VTV, services y observaciones.

    Cada tipo de dato cuelga del vehiculo con su propia tabla editable. Un solo
    POST rutea por el campo 'accion' hacia el servicio correspondiente (mismo
    patron que la vista de flota), y el GET arma el contexto con los historiales
    y los dias que faltan para cada vencimiento.
    """
    vehiculo = get_object_or_404(Vehiculo, id=id_vehiculo, activo=True)

    if request.method == "POST":
        accion = request.POST.get("accion")
        p = request.POST
        try:
            if accion == "nuevo_km":
                crear_registro_km(id_vehiculo, p.get("fecha"), p.get("kilometros"))
                messages.success(request, "Kilometraje agregado correctamente.")
            elif accion == "editar_km":
                editar_registro_km(p.get("id_registro"), p.get("fecha"), p.get("kilometros"))
                messages.success(request, "Kilometraje actualizado correctamente.")
            elif accion == "eliminar_km":
                eliminar_registro_km(p.get("id_registro"))
                messages.success(request, "Carga de kilometraje eliminada.")

            elif accion == "nuevo_seguro":
                crear_seguro(id_vehiculo, p.get("inicio"), p.get("fin"), p.get("costo"), p.get("observaciones"))
                messages.success(request, "Seguro agregado correctamente.")
            elif accion == "editar_seguro":
                editar_seguro(p.get("id_registro"), p.get("inicio"), p.get("fin"), p.get("costo"), p.get("observaciones"))
                messages.success(request, "Seguro actualizado correctamente.")
            elif accion == "eliminar_seguro":
                eliminar_seguro(p.get("id_registro"))
                messages.success(request, "Seguro eliminado.")

            elif accion == "nueva_vtv":
                crear_vtv(id_vehiculo, p.get("inicio"), p.get("fin"), p.get("costo"), p.get("observaciones"))
                messages.success(request, "VTV agregada correctamente.")
            elif accion == "editar_vtv":
                editar_vtv(p.get("id_registro"), p.get("inicio"), p.get("fin"), p.get("costo"), p.get("observaciones"))
                messages.success(request, "VTV actualizada correctamente.")
            elif accion == "eliminar_vtv":
                eliminar_vtv(p.get("id_registro"))
                messages.success(request, "VTV eliminada.")

            elif accion == "nuevo_servis":
                crear_servis(id_vehiculo, p.get("fecha"), p.get("costo"), p.get("observaciones"))
                messages.success(request, "Service agregado correctamente.")
            elif accion == "editar_servis":
                editar_servis(p.get("id_registro"), p.get("fecha"), p.get("costo"), p.get("observaciones"))
                messages.success(request, "Service actualizado correctamente.")
            elif accion == "eliminar_servis":
                eliminar_servis(p.get("id_registro"))
                messages.success(request, "Service eliminado.")

            elif accion == "nueva_obs":
                crear_observacion(id_vehiculo, p.get("fecha"), p.get("texto"))
                messages.success(request, "Observación agregada correctamente.")
            elif accion == "editar_obs":
                editar_observacion(p.get("id_registro"), p.get("fecha"), p.get("texto"))
                messages.success(request, "Observación actualizada correctamente.")
            elif accion == "eliminar_obs":
                eliminar_observacion(p.get("id_registro"))
                messages.success(request, "Observación eliminada.")

        except ValueError as e:
            messages.error(request, str(e))
        except Exception as e:
            messages.error(request, f"Ocurrió un error inesperado: {e}")

        return redirect("informacion_vehiculo", id_vehiculo=id_vehiculo)

    hoy = timezone.localdate()
    seguros = _con_dias_restantes(obtener_seguros(id_vehiculo), hoy)
    vtvs = _con_dias_restantes(obtener_vtvs(id_vehiculo), hoy)
    servicios = list(obtener_servicios(id_vehiculo))

    contexto = {
        "vehiculo": vehiculo,
        "registros_km": list(obtener_registros_km(id_vehiculo)),
        "kilometraje_total": vehiculo.kilometraje_total,
        "seguros": seguros,
        "vtvs": vtvs,
        "servicios": servicios,
        "observaciones": list(obtener_observaciones(id_vehiculo)),
        # El registro vigente es el primero (orden por -fin / -fecha): de el sale el
        # resumen de vencimientos de la cabecera.
        "seguro_vigente": seguros[0] if seguros else None,
        "vtv_vigente": vtvs[0] if vtvs else None,
        "ultimo_servis": servicios[0] if servicios else None,
        "pestaña": "viajes",
    }
    return render(request, "informacion_vehiculo.html", contexto)


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
            id_empleado = request.POST.get("id_empleado")
            id_vehiculo = request.POST.get("id_vehiculo")
            inicio_caja = request.POST.get("inicio_caja", 0)
            fecha_inicio = request.POST.get("fecha_inicio_viaje")
            fecha_vuelta = request.POST.get("fecha_regreso_viaje")
            destinos = request.POST.getlist("destino")

            try:
                editar_viaje(
                    id_viaje=id_viaje,
                    id_empleado=id_empleado,
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

        elif accion in ("nuevo_gasto", "editar_gasto", "eliminar_gasto"):
            # El resumen de caja es solo del staff, igual que el boton que abre el
            # modal: el servidor tiene que decir lo mismo que el template.
            if accion != "nuevo_gasto" and not request.user.is_staff:
                messages.error(request, "No tenés permiso para tocar los gastos del viaje.")
                return redirect("informacion_viaje", id_viaje=id_viaje)

            url_detalle = reverse("informacion_viaje", kwargs={"id_viaje": id_viaje})
            tipo_gasto = request.POST.get("tipo_gasto")
            monto_gasto = request.POST.get("monto_gasto")
            id_gasto = request.POST.get("id_gasto")
            gasto_marcado = ""

            try:
                if accion == "nuevo_gasto":
                    gasto_marcado = crear_gasto(id_viaje, tipo_gasto, monto_gasto).id
                    messages.success(request, "Gasto registrado exitosamente.")
                elif accion == "editar_gasto":
                    gasto_marcado = editar_gasto_viaje(Gasto, id_gasto, tipo_gasto, monto_gasto).id
                    messages.success(request, "Gasto actualizado correctamente.")
                else:
                    eliminar_gasto_viaje(Gasto, id_gasto)
                    messages.success(request, "Gasto eliminado correctamente.")
            except ValueError as e:
                messages.error(request, str(e))
            except Exception as e:
                messages.error(request, f"Ocurrió un error inesperado: {e}")

            return redirect(_url_con_gasto(url_detalle, gasto_marcado))

    # Operaciones asociadas al viaje, para el listado
    operaciones_viaje = (
        viaje.operaciones
        .con_totales()
        .select_related("cliente")
        .prefetch_related("detalleoperacion_set__producto", "detalleoperacion_set__cotizacion", "pago_set")
        .order_by("-fecha")
    )

    # Items para el modal selector de cliente (mismo componente que el filtro de deudas,
    # pero sin monto debajo del nombre). Se elige de la lista para no confundir clientes
    # de nombre parecido antes de arrancar una compra/venta.
    clientes_items = [
        {
            "id": c.id,
            "principal": f"{c.nombre} {c.apellido or ''}".strip(),
            "busqueda": f"{c.nombre} {c.apellido or ''}".strip().lower(),
            "iniciales": _iniciales(c.nombre, c.apellido),
        }
        for c in Cliente.objects.filter(activo=True).order_by("nombre", "apellido")
    ]

    contexto = {
        'viaje': viaje,
        'pestaña': 'viajes',
        'empleados': incluir_asignado(obtener_empleados_activos(), viaje.empleado),
        'vehiculos': incluir_asignado(obtener_vehiculos_activos(), viaje.vehiculo),
        'operaciones': operaciones_viaje,
        'clientes_items': clientes_items,
    }
    return render(request, "informacion_viaje.html", contexto)


@staff_member_required(login_url="inicio")
def deudores(request):
    import re
    from collections import defaultdict
    from decimal import Decimal

    # Filtro por cliente: en vez de un texto libre (propenso a errores de tipeo o a
    # confundir nombres parecidos) se elige un cliente desde el modal selector. Viaja
    # su id; cualquier valor no numerico se ignora y se muestran todos.
    cliente_id = request.GET.get("cliente", "")
    if not cliente_id.isdigit():
        cliente_id = ""

    # Filtro por producto: tambien via modal selector. El valor es un token que
    # distingue producto de catalogo ("p<id>") de articulo a granel ("g<id_cotizacion>"),
    # porque una linea de operacion apunta a uno u otro. Un token mal formado se ignora.
    producto_token = request.GET.get("producto", "")
    if not re.fullmatch(r"[pg]\d+", producto_token):
        producto_token = ""

    # Filtro por tipo de deuda: 'cobros' (ventas impagas) o 'pagos' (compras impagas).
    # Cualquier otro valor se ignora y se muestran todas.
    tipo = request.GET.get("tipo", "")
    if tipo not in ("cobros", "pagos"):
        tipo = ""

    # Filtro por rango de fechas de la operacion. Las fechas llegan en ISO
    # (yyyy-mm-dd) desde el <input type="date">; parse_date devuelve None si el
    # valor es invalido, asi que un parametro roto simplemente se ignora. El modo
    # "un solo dia" del popover manda desde == hasta.
    desde = parse_date(request.GET.get("desde", ""))
    hasta = parse_date(request.GET.get("hasta", ""))
    # Si el usuario invierte el rango, lo normalizo para no devolver un listado vacio.
    if desde and hasta and desde > hasta:
        desde, hasta = hasta, desde

    # Base de valuacion de las equivalencias en las tarjetas: 'hoy' (cotizacion
    # actual) u 'origen' (la cotizacion guardada al crear cada operacion). No afecta
    # a la tabla, que sigue mostrando ambas, ni al total en pesos, que es nominal.
    valuacion = request.GET.get("valuacion", "")
    if valuacion != "origen":
        valuacion = "hoy"

    # Modo de las tarjetas de resumen segun el filtro de tipo:
    #   - sin filtro (por defecto, tambien al elegir un cliente): "saldo", el neto
    #     entre lo que hay por cobrar (ventas impagas) y lo que hay por pagar (compras
    #     impagas). Positivo = a favor (nos deben); negativo = en contra (debemos).
    #   - filtro cobros: "cobrar", solo el total por cobrar.
    #   - filtro pagos:  "pagar", solo el total por pagar.
    if tipo == "cobros":
        modo = "cobrar"
    elif tipo == "pagos":
        modo = "pagar"
    else:
        modo = "saldo"

    # Traigo el listado completo bajo el filtro de tipo/fechas (sin acotar por cliente):
    # la tabla y las tarjetas usan la version filtrada por el cliente elegido, mientras
    # que el selector muestra todos los clientes con deuda para que elegir siempre de un
    # resultado. Una sola llamada evita golpear dos veces las cotizaciones.
    todas = obtener_listado_deudores("", tipo, desde, hasta)

    def _formato_pesos_ar(valor):
        # 1234567.5 -> "1.234.567,50" (miles con punto, decimales con coma)
        crudo = f"{abs(valor):,.2f}"
        return crudo.replace(",", "@").replace(".", ",").replace("@", ".")

    # Mapa operacion -> tokens de sus items, y las opciones del selector de producto.
    # Cada linea apunta a un producto de catalogo ("p<id>") o a un articulo a granel
    # ("g<id_cotizacion>"); ambos entran como opciones filtrables. Se arma sobre 'todas'
    # (solo tipo/fechas), independiente del cliente/producto elegidos, para que la lista
    # del modal siempre este poblada.
    tokens_por_operacion = defaultdict(set)
    opciones_producto = {}
    ids_operaciones = [d["id"] for d in todas]
    detalles = (
        DetalleOperacion.objects
        .filter(operacion_id__in=ids_operaciones)
        .select_related("producto", "cotizacion")
    )
    for det in detalles:
        if det.cotizacion_id:
            token = f"g{det.cotizacion_id}"
            nombre = f"{det.cotizacion.articulo} (granel)"
        else:
            token = f"p{det.producto_id}"
            nombre = det.producto.nombre
        tokens_por_operacion[det.operacion_id].add(token)
        info = opciones_producto.get(token)
        if info is None:
            info = opciones_producto[token] = {"id": token, "principal": nombre, "operaciones": set()}
        info["operaciones"].add(det.operacion_id)

    productos_con_deuda = []
    for info in sorted(opciones_producto.values(), key=lambda i: i["principal"].lower()):
        cantidad = len(info["operaciones"])
        productos_con_deuda.append({
            "id": info["id"],
            "principal": info["principal"],
            "busqueda": info["principal"].lower(),
            "secundario": f"En {cantidad} deuda{'' if cantidad == 1 else 's'}",
            "tono": "neutro",
        })

    # Filtro de la tabla/tarjetas: cliente Y producto se combinan (AND) sobre el listado.
    lista_deudores = todas
    if cliente_id:
        lista_deudores = [d for d in lista_deudores if str(d["cliente_id"]) == cliente_id]
    if producto_token:
        lista_deudores = [
            d for d in lista_deudores if producto_token in tokens_por_operacion.get(d["id"], set())
        ]

    # Items del selector de cliente: un cliente por fila con su saldo agregado en el modo
    # vigente (neto en "saldo"; total a cobrar o a pagar en los otros). El saldo acompana
    # al nombre para decidir con el monto a la vista antes de filtrar.
    agrupado = {}
    for d in todas:
        cid = d["cliente_id"]
        fila = agrupado.get(cid)
        if fila is None:
            fila = agrupado[cid] = {
                "id": cid,
                "principal": d["cliente"],
                "busqueda": d["cliente"].lower(),
                "iniciales": d["iniciales"],
                "pesos": Decimal("0"),
            }
        signo = 1 if d["tipo_operacion"] == "venta" else -1
        # En "saldo" las ventas suman y las compras restan; en cobrar/pagar el listado ya
        # viene acotado a un solo tipo, asi que sumo el monto directo.
        fila["pesos"] += (signo if modo == "saldo" else 1) * (d["deuda_pesos"] or 0)

    clientes_con_deuda = []
    for fila in sorted(agrupado.values(), key=lambda f: f["principal"].lower()):
        pesos = fila["pesos"]
        if modo == "cobrar" or (modo == "saldo" and pesos > 0):
            tono, secundario = "cobrar", f"+ $ {_formato_pesos_ar(pesos)}"
        elif modo == "pagar" or (modo == "saldo" and pesos < 0):
            tono, secundario = "pagar", f"− $ {_formato_pesos_ar(pesos)}"
        else:
            tono, secundario = "neutro", f"$ {_formato_pesos_ar(pesos)}"
        clientes_con_deuda.append({
            "id": fila["id"],
            "principal": fila["principal"],
            "busqueda": fila["busqueda"],
            "iniciales": fila["iniciales"],
            "secundario": secundario,
            "tono": tono,
        })

    # Nombres elegidos para rehidratar los chips al cargar por URL directa.
    cliente_nombre = ""
    if cliente_id:
        elegido = next((c for c in clientes_con_deuda if str(c["id"]) == cliente_id), None)
        cliente_nombre = elegido["principal"] if elegido else ""
    producto_nombre = ""
    if producto_token:
        elegido = next((p for p in productos_con_deuda if p["id"] == producto_token), None)
        producto_nombre = elegido["principal"] if elegido else ""

    # Cada equivalencia suma la columna de la valuacion elegida. Una operacion sin
    # cotizacion de origen guardada cae a su valor actual: aporta lo mismo a ambos
    # totales en vez de desaparecer del total origen y desbalancear la comparacion.
    def _valor_equivalencia(fila, campo):
        if valuacion == "origen" and fila[f"{campo}_historico"] is not None:
            return fila[f"{campo}_historico"]
        return fila[f"{campo}_actual"] or 0

    def _total_pesos(filas):
        return sum((d["deuda_pesos"] or 0) for d in filas)

    def _total_equiv(filas, campo):
        return sum(_valor_equivalencia(d, campo) for d in filas)

    # Totales sobre el listado completo (no solo la pagina) para las tarjetas. En saldo
    # el neto se arma campo por campo: las ventas suman (nos deben) y las compras restan
    # (debemos); asi cada equivalencia queda con su propio signo.
    ventas = [d for d in lista_deudores if d["tipo_operacion"] == "venta"]
    compras = [d for d in lista_deudores if d["tipo_operacion"] == "compra"]

    if modo == "saldo":
        total_pesos = _total_pesos(ventas) - _total_pesos(compras)
        total_usd = _total_equiv(ventas, "deuda_dolar") - _total_equiv(compras, "deuda_dolar")
        total_miel = _total_equiv(ventas, "kg_miel") - _total_equiv(compras, "kg_miel")
        total_cera = _total_equiv(ventas, "kg_cera") - _total_equiv(compras, "kg_cera")
    else:
        filas_tarjetas = ventas if modo == "cobrar" else compras
        total_pesos = _total_pesos(filas_tarjetas)
        total_usd = _total_equiv(filas_tarjetas, "deuda_dolar")
        total_miel = _total_equiv(filas_tarjetas, "kg_miel")
        total_cera = _total_equiv(filas_tarjetas, "kg_cera")

    # Texto del chip de fechas: un solo dia (desde == hasta), rango cerrado, o
    # rango abierto con un solo extremo. Se calcula en el server para que el chip
    # ya se pinte correcto al cargar, sin depender del JS.
    if desde and hasta and desde == hasta:
        fecha_label = desde.strftime("%d/%m/%Y")
    elif desde and hasta:
        fecha_label = f"{desde.strftime('%d/%m')} – {hasta.strftime('%d/%m/%Y')}"
    elif desde:
        fecha_label = f"Desde {desde.strftime('%d/%m/%Y')}"
    elif hasta:
        fecha_label = f"Hasta {hasta.strftime('%d/%m/%Y')}"
    else:
        fecha_label = "Fechas"

    # Las deudas se ordenan siempre de la más antigua a la más nueva
    lista_deudores.sort(key=lambda d: d["dias"], reverse=True)

    paginator_deudores = Paginator(lista_deudores, 8)
    pagina_numero = request.GET.get("page")
    pagina_obj = paginator_deudores.get_page(pagina_numero)

    contexto = {
        "deudores": pagina_obj,
        # Cliente elegido en el selector: id para armar los links de paginacion y el
        # nombre para pintar el chip; vacio si no hay filtro de cliente activo.
        "cliente": cliente_id,
        "cliente_nombre": cliente_nombre,
        "clientes_con_deuda": clientes_con_deuda,
        # Producto elegido en el selector: token para los links de paginacion y nombre
        # para el chip; vacio si no hay filtro de producto activo.
        "producto": producto_token,
        "producto_nombre": producto_nombre,
        "productos_con_deuda": productos_con_deuda,
        "tipo": tipo,
        # Fechas en ISO para rellenar los <input type="date"> y armar los links de
        # paginacion; vacio si no hay filtro activo.
        "desde": desde.isoformat() if desde else "",
        "hasta": hasta.isoformat() if hasta else "",
        "fecha_label": fecha_label,
        "modo": modo,
        "valuacion": valuacion,
        "total_pesos": total_pesos,
        "total_usd": total_usd,
        "total_miel": total_miel,
        "total_cera": total_cera,
        "total_deudores": len(lista_deudores),
    }

    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        # El AJAX refresca tanto las tarjetas (que cambian de a cobrar a pagar) como la tabla.
        return render(request, "deudores_ajax.html", contexto)
        
    return render(request, "deudores.html", contexto)


@staff_member_required(login_url="inicio")
def alquileres(request):
    """Listado de casas en alquiler con el estado de cobro del mes en curso.

    Un solo POST con el campo 'accion' que rutea a cada servicio, igual que en
    destinos de reparto y flota. Concentra el ABM de casas y el alta y correccion
    de contratos; los cobros no pasan por aca, los carga la casilla de la tabla
    contra su propio endpoint AJAX.
    """
    if request.method == "POST":
        accion = request.POST.get("accion")

        try:
            if accion == "nueva_casa":
                crear_casa(
                    nombre=request.POST.get("nombre"),
                    localidad=request.POST.get("localidad"),
                    direccion=request.POST.get("direccion"),
                )
                messages.success(request, "Casa registrada correctamente")

            elif accion == "editar_casa":
                editar_casa(
                    request.POST.get("id_casa"),
                    nombre=request.POST.get("nombre"),
                    localidad=request.POST.get("localidad"),
                    direccion=request.POST.get("direccion"),
                )
                messages.success(request, "Casa actualizada correctamente")

            elif accion == "eliminar_casa":
                eliminar_casa(request.POST.get("id_casa"))
                messages.success(request, "Casa eliminada correctamente")

            elif accion == "nuevo_contrato":
                crear_contrato(
                    request.POST.get("id_casa"),
                    inicio=request.POST.get("inicio"),
                    fin=request.POST.get("fin"),
                    monto_mensual=request.POST.get("monto_mensual"),
                    comision_inmobiliaria=request.POST.get("comision_inmobiliaria"),
                    nombre_inquilino=request.POST.get("nombre_inquilino"),
                )
                messages.success(request, "Contrato guardado correctamente")

            elif accion == "editar_contrato":
                editar_contrato(
                    request.POST.get("id_contrato"),
                    inicio=request.POST.get("inicio"),
                    fin=request.POST.get("fin"),
                    monto_mensual=request.POST.get("monto_mensual"),
                    comision_inmobiliaria=request.POST.get("comision_inmobiliaria"),
                    nombre_inquilino=request.POST.get("nombre_inquilino"),
                )
                messages.success(request, "Contrato actualizado correctamente")

        except ValueError as e:
            # Errores de validacion que llegan desde services.py
            messages.error(request, str(e))
        except Exception as e:
            messages.error(request, f"Ocurrió un error inesperado: {e}")

        # El formulario postea a la URL actual, asi que el mes que se estaba
        # mirando sigue en request.GET: lo devuelvo para no patear al usuario
        # de vuelta al mes en curso despues de editar una casa. Rearmo el
        # parametro desde la fecha ya parseada y no desde el texto crudo.
        destino = reverse("alquileres")
        periodo_visto = resolver_periodo(request.GET.get("mes"))
        if periodo_visto != periodo_actual():
            destino = f"{destino}?mes={periodo_visto:%Y-%m}"
        return redirect(destino)

    estado = request.GET.get("estado", "")
    if estado not in FILTROS_ALQUILERES:
        estado = ""

    # Mes que se esta mirando. Toda la pantalla cuelga de aca: los totales de la
    # cabecera, el estado de cada fila y el mes que carga la casilla de cobro.
    # Sin parametro es el mes en curso.
    periodo = resolver_periodo(request.GET.get("mes"))

    casas = obtener_casas(estado, periodo)

    paginator = Paginator(casas, 10)
    pagina_obj = paginator.get_page(request.GET.get("page"))

    contexto = {
        "casas": pagina_obj,
        "estado": estado,
        "periodo": periodo,
    }

    # Los chips y la paginacion refrescan solo la tabla. La cabecera queda afuera
    # a proposito: mide el mes completo y no se mueve con el filtro. Cambiar de
    # mes si recarga la pagina, porque mueve los totales y la tabla a la vez.
    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        return render(request, "tabla_alquileres.html", contexto)

    # Listado completo (sin filtros) para los totales de la cabecera
    casas_mes = obtener_casas(periodo=periodo)

    contexto.update({
        "resumen": obtener_resumen_alquileres(casas_mes, periodo),
        "es_mes_actual": periodo == periodo_actual(),
        "mes_actual": periodo_actual(),
        # Para las flechas del navegador de mes
        "periodo_anterior": mes_desplazado(periodo, -1),
        "periodo_siguiente": mes_desplazado(periodo, 1),
    })

    return render(request, "alquileres.html", contexto)


@staff_member_required(login_url="inicio")
def informacion_alquileres(request, id_casa):
    """Perfil de una casa: la propiedad, su contrato vigente y el historial.

    Comparte los tres paneles con el listado (casa, contrato y eliminacion), asi
    que tambien comparte las acciones del POST. La diferencia esta en a donde
    vuelve cada una: todas recargan este mismo perfil, salvo la baja de la casa,
    que lo deja sin sujeto y devuelve al listado.

    El mes y el filtro con los que se venia mirando el listado viajan en la URL y
    solo se usan para armar el enlace de vuelta: el perfil no depende de un mes,
    muestra el contrato que corre hoy.
    """
    volver = reverse("alquileres")
    parametros = []
    periodo_visto = resolver_periodo(request.GET.get("mes"))
    if periodo_visto != periodo_actual():
        parametros.append(f"mes={periodo_visto:%Y-%m}")
    estado = request.GET.get("estado", "")
    if estado in FILTROS_ALQUILERES:
        parametros.append(f"estado={estado}")
    if parametros:
        volver = f"{volver}?{'&'.join(parametros)}"

    if request.method == "POST":
        accion = request.POST.get("accion")

        try:
            if accion == "editar_casa":
                editar_casa(
                    id_casa,
                    nombre=request.POST.get("nombre"),
                    localidad=request.POST.get("localidad"),
                    direccion=request.POST.get("direccion"),
                )
                messages.success(request, "Casa actualizada correctamente")

            elif accion == "eliminar_casa":
                eliminar_casa(id_casa)
                messages.success(request, "Casa eliminada correctamente")
                # La casa ya no existe para el perfil: el unico destino posible
                # es el listado, y ahi tampoco va a aparecer
                return redirect(volver)

            elif accion == "nuevo_contrato":
                crear_contrato(
                    id_casa,
                    inicio=request.POST.get("inicio"),
                    fin=request.POST.get("fin"),
                    monto_mensual=request.POST.get("monto_mensual"),
                    comision_inmobiliaria=request.POST.get("comision_inmobiliaria"),
                    nombre_inquilino=request.POST.get("nombre_inquilino"),
                )
                messages.success(request, "Contrato guardado correctamente")

            elif accion == "editar_contrato":
                editar_contrato(
                    request.POST.get("id_contrato"),
                    inicio=request.POST.get("inicio"),
                    fin=request.POST.get("fin"),
                    monto_mensual=request.POST.get("monto_mensual"),
                    comision_inmobiliaria=request.POST.get("comision_inmobiliaria"),
                    nombre_inquilino=request.POST.get("nombre_inquilino"),
                )
                messages.success(request, "Contrato actualizado correctamente")

            elif accion == "eliminar_contrato":
                eliminar_contrato(request.POST.get("id_contrato"))
                messages.success(request, "Contrato eliminado correctamente")

            elif accion == "nuevo_gasto":
                crear_gasto_casa(
                    id_casa,
                    categoria=request.POST.get("categoria"),
                    fecha=request.POST.get("fecha"),
                    monto=request.POST.get("monto"),
                    detalle=request.POST.get("detalle"),
                )
                messages.success(request, "Gasto guardado correctamente")

            elif accion == "editar_gasto":
                editar_gasto_casa(
                    request.POST.get("id_gasto"),
                    categoria=request.POST.get("categoria"),
                    fecha=request.POST.get("fecha"),
                    monto=request.POST.get("monto"),
                    detalle=request.POST.get("detalle"),
                )
                messages.success(request, "Gasto actualizado correctamente")

            elif accion == "eliminar_gasto":
                eliminar_gasto_casa(request.POST.get("id_gasto"))
                messages.success(request, "Gasto eliminado correctamente")

        except ValueError as e:
            messages.error(request, str(e))
        except Exception as e:
            messages.error(request, f"Ocurrió un error inesperado: {e}")

        # Vuelve al perfil conservando el rastro del listado, para que el enlace
        # de vuelta siga apuntando al mes desde el que se entro
        destino = reverse("informacion_alquileres", args=[id_casa])
        consulta = request.GET.urlencode()
        return redirect(f"{destino}?{consulta}" if consulta else destino)

    # El rango solo recorta los gastos; el contrato y el historial no dependen
    # de ningun periodo. Viaja en la URL, asi que el filtro sobrevive al POST de
    # cualquier accion y se puede compartir el enlace ya filtrado.
    desde, hasta, ctx_fechas = _rango_gastos(request)

    contexto = obtener_detalle_alquiler(id_casa, desde, hasta)
    contexto.update(ctx_fechas)

    # Los gastos se acumulan para siempre, asi que se paginan de a cinco. El
    # contrato y el historial no: son un puñado y entran enteros.
    contexto["gastos"] = Paginator(contexto["gastos"], 5).get_page(request.GET.get("page"))

    # Todo lo que hay en la URL menos la pagina, para que los enlaces de
    # anterior y siguiente no se lleven puesto el filtro de fechas ni el rastro
    # del listado
    filtros = request.GET.copy()
    filtros.pop("page", None)
    contexto["filtros_url"] = filtros.urlencode()

    contexto["volver_url"] = volver
    return render(request, "informacion_alquileres.html", contexto)


@staff_member_required(login_url="inicio")
def obtener_casa_json(request, id_casa):
    datos = obtener_datos_casa(id_casa)

    if datos:
        return JsonResponse(datos)

    return JsonResponse({"error": "Casa no encontrada"}, status=404)


@staff_member_required(login_url="inicio")
def obtener_contrato_casa_json(request, id_casa):
    # Lo que el modal de contrato necesita antes de abrirse: el vigente para
    # corregirlo, o el anterior para precargar la renovacion.
    return JsonResponse(obtener_contrato_de_casa(id_casa))


def _pesos(monto):
    """Monto en el mismo formato que la plantilla: sin centavos y con puntos."""
    return intcomma(floatformat(monto, 0))


def marcar_pago_alquiler_ajax(request, id_casa, periodo):
    """Casilla de cobro de la tabla de alquileres: carga o borra el pago del mes.

    Habla el mismo protocolo que las casillas de reparto y cereal (POST con
    'pagado' 1/0, respuesta con el estado que quedo) para poder reusar tal cual
    pago_viaje.js. La diferencia es que el mes no se deduce: viaja en la URL,
    porque la tabla puede estar mostrando cualquier periodo.

    Ademas devuelve 'mensaje', porque aca desmarcar borra un registro y el aviso
    generico no alcanza para avisarlo.

    Es la unica via de carga de cobros de la pantalla, asi que los rechazos que
    devuelve (casa sin precio, sin inquilino, contrato vencido) son los que ve el
    usuario: tienen que decir que hacer, no solo que fallo.
    """
    if request.method != "POST":
        return JsonResponse({"error": "Método no permitido"}, status=405)

    if not request.user.is_staff:
        return JsonResponse({"error": "No tenés permiso para registrar cobros."}, status=403)

    try:
        resultado = marcar_pago_alquiler(id_casa, periodo, request.POST.get("pagado") == "1")
    except ValueError as e:
        return JsonResponse({"error": str(e)}, status=400)

    periodo = resultado["periodo"]
    mes = date_format(periodo, "F \\d\\e Y")
    monto = resultado["monto"]

    if resultado["pagado"]:
        mensaje = f"Alquiler de {mes} cobrado: ${_pesos(monto)}."
    elif monto is None:
        mensaje = f"El alquiler de {mes} figura como pendiente."
    else:
        # Borro un registro, asi que digo cuanto era: si estaba cargado a mano con
        # otro importe, es la unica pista de lo que hay que volver a cargar.
        mensaje = f"Se borró el pago de {mes} por ${_pesos(monto)}."

    # La cabecera vive fuera de la tabla y no se entera sola de que cambio el mes.
    # Devuelvo los totales ya recalculados para que no queden mintiendo hasta la
    # proxima recarga.
    resumen = obtener_resumen_alquileres(obtener_casas(periodo=periodo), periodo)
    casa = obtener_casas(periodo=periodo).filter(id=id_casa).first()

    return JsonResponse({
        "ok": True,
        "pagado": resultado["pagado"],
        "mensaje": mensaje,
        "estado": casa.estado_mes if casa else "",
        "resumen": {
            "cobrado": _pesos(resumen["cobrado"]),
            "pendiente": _pesos(resumen["monto_pendiente"]),
            "pendientes": resumen["pendientes"],
        },
    })


@staff_member_required(login_url="inicio")
def combustible(request):
    return render(request, "combustible.html")


@login_required
def mercado_libre(request):
    if request.method == "POST":
        accion = request.POST.get("accion")

        try:
            if accion == "nuevo_viaje_reparto":
                # 1. Extraccion de datos del formulario
                id_empleado = request.POST.get("id_empleado")
                id_vehiculo = request.POST.get("id_vehiculo")
                gasto_combustible = request.POST.get("gasto_combustible_viaje_reparto")
                costo_empleado = request.POST.get("costo_empleado")
                valor_viaje = request.POST.get("valor_viaje")
                fecha_viaje_reparto = request.POST.get("fecha_viaje_reparto")
                id_destino = request.POST.get("id_destino")

                # 2. Validacion de presencia de lo obligatorio (lo esencial en la vista)
                if not all([id_empleado, id_vehiculo, gasto_combustible, costo_empleado,
                            valor_viaje, fecha_viaje_reparto, id_destino]):
                    messages.error(request, "Faltan datos obligatorios para crear el viaje de reparto.")
                    return redirect("mercado_libre")

                # 3. Delegacion al servicio (reglas de negocio y validacion)
                crear_viaje_reparto(id_empleado, id_vehiculo, gasto_combustible, costo_empleado,
                                    valor_viaje, fecha_viaje_reparto, id_destino,
                                    pagado=bool(_pagado_del_formulario(request)))
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

    # Filtros por entidad (chip -> modal selector). El destino sale del catalogo de
    # localidades, asi que se filtra por su id (no por texto libre como los otros viajes).
    empleado = request.GET.get("empleado", "")
    vehiculo = request.GET.get("vehiculo", "")
    destino = request.GET.get("destino", "")
    if empleado.isdigit():
        lista_viajes = lista_viajes.filter(empleado_id=empleado)
    if vehiculo.isdigit():
        lista_viajes = lista_viajes.filter(vehiculo_id=vehiculo)
    if destino.isdigit():
        lista_viajes = lista_viajes.filter(destino_id=destino)

    # Filtro por rango de fechas (chip + popover), por la fecha del reparto.
    desde, hasta, ctx_fechas = _rango_fechas(request)
    if desde:
        lista_viajes = lista_viajes.filter(fecha_viaje_reparto__gte=desde)
    if hasta:
        lista_viajes = lista_viajes.filter(fecha_viaje_reparto__lte=hasta)

    # Cargo de a 5 viajes
    paginator = Paginator(lista_viajes, 5)
    pagina_numero = request.GET.get("page")
    page_obj = paginator.get_page(pagina_numero)

    contexto = {
        "page_obj": page_obj,
        "empleados": obtener_empleados_activos(),
        "vehiculos": obtener_vehiculos_activos(),
        # Catalogo de localidades: el alta de un reparto elige de aca, no escribe a mano
        "destinos": obtener_destinos_reparto(),
        "empleado": empleado,
        "empleado_nombre": nombre_empleado_filtro(empleado),
        "vehiculo": vehiculo,
        "vehiculo_nombre": nombre_vehiculo_filtro(vehiculo),
        "destino": destino,
        "destino_nombre": nombre_destino_reparto_filtro(destino),
        "empleados_filtro": opciones_empleados_filtro(),
        "vehiculos_filtro": opciones_vehiculos_filtro(),
        "destinos_filtro": opciones_destinos_reparto_filtro(),
        # Las tarjetas reflejan los mismos filtros que la tabla: calculo el resumen
        # sobre el listado ya filtrado (antes de paginar), no sobre todos los viajes.
        "resumen": obtener_resumen_reparto(lista_viajes),
        **ctx_fechas,
    }

    # Si es una peticion AJAX (buscador/fecha/paginacion), devuelvo el fragmento que
    # refresca tanto las tarjetas de resumen como la tabla (mercado_libre.js reemplaza
    # cada region por su id).
    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        return render(request, "mercado_libre_ajax.html", contexto)

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
            id_empleado = request.POST.get("id_empleado")
            id_vehiculo = request.POST.get("id_vehiculo")
            gasto_combustible = request.POST.get("gasto_combustible_viaje_reparto")
            costo_empleado = request.POST.get("costo_empleado")
            valor_viaje = request.POST.get("valor_viaje")
            fecha_viaje_reparto = request.POST.get("fecha_viaje_reparto")
            id_destino = request.POST.get("id_destino")

            try:
                editar_viaje_reparto(
                    id_viaje_reparto=id_viaje_reparto,
                    id_empleado=id_empleado,
                    id_vehiculo=id_vehiculo,
                    gasto_combustible=gasto_combustible,
                    costo_empleado=costo_empleado,
                    valor_viaje=valor_viaje,
                    fecha_viaje_reparto=fecha_viaje_reparto,
                    id_destino=id_destino,
                    pagado=_pagado_del_formulario(request),
                )
                messages.success(request, "Viaje de reparto modificado exitosamente.")
            except ValueError as e:
                messages.error(request, str(e))
            except Exception as e:
                messages.error(request, f"Ocurrió un error inesperado: {e}")

            return redirect("informacion_viaje_reparto", id_viaje_reparto=id_viaje_reparto)

        elif accion in ("nuevo_gasto_reparto", "editar_gasto_reparto", "eliminar_gasto_reparto"):
            # El resultado del reparto es solo del staff, igual que el boton que abre
            # el modal: el servidor tiene que decir lo mismo que el template.
            if accion != "nuevo_gasto_reparto" and not request.user.is_staff:
                messages.error(request, "No tenés permiso para tocar los gastos del reparto.")
                return redirect("informacion_viaje_reparto", id_viaje_reparto=id_viaje_reparto)

            url_detalle = reverse("informacion_viaje_reparto",
                                  kwargs={"id_viaje_reparto": id_viaje_reparto})
            tipo_gasto = request.POST.get("tipo_gasto")
            monto_gasto = request.POST.get("monto_gasto")
            id_gasto = request.POST.get("id_gasto")
            gasto_marcado = ""

            try:
                if accion == "nuevo_gasto_reparto":
                    gasto_marcado = crear_gasto_viaje_reparto(id_viaje_reparto, tipo_gasto, monto_gasto).id
                    messages.success(request, "Gasto registrado exitosamente.")
                elif accion == "editar_gasto_reparto":
                    gasto_marcado = editar_gasto_viaje(GastoViajeReparto, id_gasto,
                                                       tipo_gasto, monto_gasto).id
                    messages.success(request, "Gasto actualizado correctamente.")
                else:
                    eliminar_gasto_viaje(GastoViajeReparto, id_gasto)
                    messages.success(request, "Gasto eliminado correctamente.")
            except ValueError as e:
                messages.error(request, str(e))
            except Exception as e:
                messages.error(request, f"Ocurrió un error inesperado: {e}")

            return redirect(_url_con_gasto(url_detalle, gasto_marcado))

    contexto = {
        "viaje_reparto": viaje_reparto,
        "pestaña": "viajes",
        "empleados": incluir_asignado(obtener_empleados_activos(), viaje_reparto.empleado),
        "vehiculos": incluir_asignado(obtener_vehiculos_activos(), viaje_reparto.vehiculo),
        # Incluyo el destino del viaje aunque este dado de baja, para que al editar
        # siga preseleccionado en vez de obligar a elegir otra localidad.
        "destinos": incluir_asignado(obtener_destinos_reparto(), viaje_reparto.destino),
    }
    return render(request, "informacion_viaje_reparto.html", contexto)


@login_required
def marcar_pago_reparto_ajax(request, id_viaje_reparto):
    """Casilla de cobro de la tabla de repartos: alterna 'pagado' sin recargar.

    Solo staff, con el mismo criterio que el resto de la plata en esta seccion: la
    tarjeta de resultado del reparto ya vive detras de user.is_staff.
    """
    if request.method != "POST":
        return JsonResponse({"error": "Método no permitido"}, status=405)

    if not request.user.is_staff:
        return JsonResponse({"error": "No tenés permiso para cambiar el estado de pago."}, status=403)

    viaje_reparto = marcar_pago_viaje_reparto(id_viaje_reparto, request.POST.get("pagado") == "1")
    return JsonResponse({"ok": True, "pagado": viaje_reparto.pagado})


@login_required
def destinos_reparto(request):
    """Catalogo de localidades de reparto con su tarifa (alta, edicion y baja).

    Mismo patron que la vista de flota: un solo POST con el campo 'accion' que rutea
    a cada servicio, y redirect para no repetir el envio si se recarga la pagina.

    Solo staff: aca se define cuanto se cobra cada reparto. Sin el permiso vuelvo al
    listado con un aviso, en vez de usar staff_member_required, que manda al login
    del admin y deja al usuario fuera de la aplicacion.
    """
    if not request.user.is_staff:
        messages.error(request, "No tenés permiso para gestionar los destinos de reparto.")
        return redirect("mercado_libre")

    if request.method == "POST":
        accion = request.POST.get("accion")

        try:
            if accion == "nuevo_destino":
                crear_destino_reparto(request.POST.get("localidad_destino", ""),
                                      request.POST.get("valor_viaje"))
                messages.success(request, "Destino registrado exitosamente.")

            elif accion == "editar_destino":
                editar_destino_reparto(request.POST.get("id_destino"),
                                       request.POST.get("localidad_destino", ""),
                                       request.POST.get("valor_viaje"))
                messages.success(request, "Destino actualizado correctamente.")

            elif accion == "eliminar_destino":
                eliminar_destino_reparto(request.POST.get("id_destino"))
                messages.success(request, "Destino eliminado correctamente.")

        except ValueError as e:
            # Errores de validacion que llegan desde services.py
            messages.error(request, str(e))
        except Exception as e:
            messages.error(request, f"Ocurrió un error inesperado: {e}")

        return redirect("destinos_reparto")

    contexto = {
        "destinos": obtener_destinos_reparto(),
        "pestaña": "viajes",
    }
    return render(request, "destinos_reparto.html", contexto)


@login_required
def viaje_cereales(request):
    if request.method == "POST":
        accion = request.POST.get("accion")

        try:
            if accion == "nuevo_viaje_cereal":
                # 1. Extraccion de datos del formulario
                id_cliente = request.POST.get("id_cliente")
                id_empleado = request.POST.get("id_empleado")
                id_vehiculo = request.POST.get("id_vehiculo")
                tipo_cereal = request.POST.get("tipo_cereal")
                codigo_trazabilidad = request.POST.get("codigo_trazabilidad")
                toneladas = request.POST.get("toneladas")
                precio_tonelada = request.POST.get("precio_tonelada")
                # El porcentaje es opcional: si llega vacio lo paso como None
                porcentaje_empleado = request.POST.get("porcentaje_empleado") or None
                fecha_viaje_cereal = request.POST.get("fecha_viaje_cereal")
                destinos = request.POST.getlist("destino")
                # Dadora de carga: toda opcional. El nombre vacio significa "sin dadora"
                # y el servicio normaliza el tipo de cobro y el valor en consecuencia.
                dadora_carga = request.POST.get("dadora_carga")
                dadora_tipo_cobro = request.POST.get("dadora_tipo_cobro")
                dadora_valor = request.POST.get("dadora_valor") or None

                # 2. Validacion de presencia de lo obligatorio (lo esencial en la vista)
                if not all([id_cliente, id_empleado, id_vehiculo, tipo_cereal, codigo_trazabilidad,
                            toneladas, precio_tonelada, fecha_viaje_cereal]) or not destinos:
                    messages.error(request, "Faltan datos obligatorios para crear el viaje de cereal.")
                    return redirect("viajes_cereales")

                # 3. Delegacion al servicio (reglas de negocio y validacion con regex)
                crear_viaje_cereal(id_cliente, id_empleado, id_vehiculo, tipo_cereal, codigo_trazabilidad,
                                   toneladas, precio_tonelada, porcentaje_empleado, fecha_viaje_cereal, destinos,
                                   dadora_carga=dadora_carga, dadora_tipo_cobro=dadora_tipo_cobro,
                                   dadora_valor=dadora_valor,
                                   pagado=bool(_pagado_del_formulario(request)))
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

    # Filtros por entidad (chip -> modal selector). Reemplazan al buscador de texto:
    # el usuario elige empleado, vehiculo o destino de una lista en vez de tipear.
    empleado = request.GET.get("empleado", "")
    vehiculo = request.GET.get("vehiculo", "")
    destino = request.GET.get("destino", "")
    if empleado.isdigit():
        lista_viajes = lista_viajes.filter(empleado_id=empleado)
    if vehiculo.isdigit():
        lista_viajes = lista_viajes.filter(vehiculo_id=vehiculo)
    if destino:
        lista_viajes = lista_viajes.filter(destinos__destino=destino).distinct()

    # Filtro por rango de fechas (chip + popover), por la fecha del viaje.
    desde, hasta, ctx_fechas = _rango_fechas(request)
    if desde:
        lista_viajes = lista_viajes.filter(fecha_viaje_cereal__gte=desde)
    if hasta:
        lista_viajes = lista_viajes.filter(fecha_viaje_cereal__lte=hasta)

    # Cargo de a 5 viajes
    paginator = Paginator(lista_viajes, 5)
    pagina_numero = request.GET.get("page")
    page_obj = paginator.get_page(pagina_numero)

    contexto = {
        "page_obj": page_obj,
        "empleados": obtener_empleados_activos(),
        "vehiculos": obtener_vehiculos_activos(),
        "cereales": ViajeCereal.cereales,
        "empleado": empleado,
        "empleado_nombre": nombre_empleado_filtro(empleado),
        "vehiculo": vehiculo,
        "vehiculo_nombre": nombre_vehiculo_filtro(vehiculo),
        "destino": destino,
        "destino_nombre": destino,
        "empleados_filtro": opciones_empleados_filtro(),
        "vehiculos_filtro": opciones_vehiculos_filtro(),
        "destinos_filtro": opciones_destinos_cereal(),
        # Las tarjetas reflejan los mismos filtros que la tabla: calculo el resumen
        # sobre el listado ya filtrado (antes de paginar), no sobre todos los viajes.
        "resumen": obtener_resumen_cereal(lista_viajes),
        **ctx_fechas,
    }

    # Si es una peticion AJAX (buscador/fecha/paginacion), devuelvo el fragmento que
    # refresca tanto las tarjetas de resumen como la tabla (viajes_cereales.js
    # reemplaza cada region por su id).
    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        return render(request, "viajes_cereales_ajax.html", contexto)

    return render(request, "viajes_cereales.html", contexto)


@login_required
def informacion_viaje_cereal(request, id_viaje_cereal):
    viaje_cereal = obtener_datos_viaje_cereal(id_viaje_cereal)

    # Al detalle se llega desde el listado de cereales o desde el perfil del cliente
    # (?origen=cliente), y de ahi depende a donde vuelve el boton "Volver". Los
    # formularios postean a esta misma URL, asi que el origen sobrevive al POST pero
    # no al redirect: sin volver a pegarlo, despues de editar o de cargar un gasto el
    # boton cambiaria de destino solo.
    origen = request.GET.get("origen", "")
    url_detalle = reverse("informacion_viaje_cereal", kwargs={"id_viaje_cereal": id_viaje_cereal})
    if origen:
        url_detalle = f"{url_detalle}?origen={origen}"

    if request.method == "POST":
        accion = request.POST.get("accion")

        if accion == "eliminar_viaje_cereal":
            try:
                eliminar_viaje_cereal(id_viaje_cereal)
                messages.success(request, "Viaje de cereal eliminado correctamente")
                # Sin viaje ya no hay detalle al que volver: al que venia del perfil
                # del cliente lo devuelvo ahi, no al listado de cereales.
                if origen == "cliente" and viaje_cereal.cliente_id:
                    return redirect("informacion_clientes", id_cliente=viaje_cereal.cliente_id)
                return redirect("viajes_cereales")
            except Exception as e:
                messages.error(request, f"{e}")
                return redirect(url_detalle)

        elif accion == "editar_viaje_cereal":
            id_cliente = request.POST.get("id_cliente")
            id_empleado = request.POST.get("id_empleado")
            id_vehiculo = request.POST.get("id_vehiculo")
            tipo_cereal = request.POST.get("tipo_cereal")
            codigo_trazabilidad = request.POST.get("codigo_trazabilidad")
            toneladas = request.POST.get("toneladas")
            precio_tonelada = request.POST.get("precio_tonelada")
            porcentaje_empleado = request.POST.get("porcentaje_empleado") or None
            fecha_viaje_cereal = request.POST.get("fecha_viaje_cereal")
            destinos = request.POST.getlist("destino")
            dadora_carga = request.POST.get("dadora_carga")
            dadora_tipo_cobro = request.POST.get("dadora_tipo_cobro")
            dadora_valor = request.POST.get("dadora_valor") or None

            try:
                editar_viaje_cereal(
                    id_viaje_cereal=id_viaje_cereal,
                    id_cliente=id_cliente,
                    id_empleado=id_empleado,
                    id_vehiculo=id_vehiculo,
                    tipo_cereal=tipo_cereal,
                    codigo_trazabilidad=codigo_trazabilidad,
                    toneladas=toneladas,
                    precio_tonelada=precio_tonelada,
                    porcentaje_empleado=porcentaje_empleado,
                    fecha_viaje_cereal=fecha_viaje_cereal,
                    destinos=destinos,
                    dadora_carga=dadora_carga,
                    dadora_tipo_cobro=dadora_tipo_cobro,
                    dadora_valor=dadora_valor,
                    pagado=_pagado_del_formulario(request),
                )
                messages.success(request, "Viaje de cereal modificado exitosamente.")
            except ValueError as e:
                messages.error(request, str(e))
            except Exception as e:
                messages.error(request, f"Ocurrió un error inesperado: {e}")

            return redirect(url_detalle)

        elif accion in ("nuevo_gasto_cereal", "editar_gasto_cereal", "eliminar_gasto_cereal"):
            # El calculo del flete es solo del staff, igual que el boton que abre el
            # modal: el servidor tiene que decir lo mismo que el template.
            if accion != "nuevo_gasto_cereal" and not request.user.is_staff:
                messages.error(request, "No tenés permiso para tocar los gastos del viaje.")
                return redirect(url_detalle)

            tipo_gasto = request.POST.get("tipo_gasto")
            monto_gasto = request.POST.get("monto_gasto")
            id_gasto = request.POST.get("id_gasto")
            gasto_marcado = ""

            try:
                if accion == "nuevo_gasto_cereal":
                    gasto_marcado = crear_gasto_viaje_cereal(id_viaje_cereal, tipo_gasto, monto_gasto).id
                    messages.success(request, "Gasto registrado exitosamente.")
                elif accion == "editar_gasto_cereal":
                    gasto_marcado = editar_gasto_viaje(GastoViajeCereal, id_gasto,
                                                       tipo_gasto, monto_gasto).id
                    messages.success(request, "Gasto actualizado correctamente.")
                else:
                    eliminar_gasto_viaje(GastoViajeCereal, id_gasto)
                    messages.success(request, "Gasto eliminado correctamente.")
            except ValueError as e:
                messages.error(request, str(e))
            except Exception as e:
                messages.error(request, f"Ocurrió un error inesperado: {e}")

            return redirect(_url_con_gasto(url_detalle, gasto_marcado))

    contexto = {
        "viaje_cereal": viaje_cereal,
        "pestaña": "viajes",
        "empleados": incluir_asignado(obtener_empleados_activos(), viaje_cereal.empleado),
        "vehiculos": incluir_asignado(obtener_vehiculos_activos(), viaje_cereal.vehiculo),
        "cereales": ViajeCereal.cereales,
    }
    return render(request, "informacion_viaje_cereal.html", contexto)


@login_required
def marcar_pago_cereal_ajax(request, id_viaje_cereal):
    """Casilla de cobro de la tabla de cereales: alterna 'pagado' sin recargar.

    Mismo criterio que en repartos: solo staff, porque es informacion de cobro.
    """
    if request.method != "POST":
        return JsonResponse({"error": "Método no permitido"}, status=405)

    if not request.user.is_staff:
        return JsonResponse({"error": "No tenés permiso para cambiar el estado de pago."}, status=403)

    viaje_cereal = marcar_pago_viaje_cereal(id_viaje_cereal, request.POST.get("pagado") == "1")
    return JsonResponse({"ok": True, "pagado": viaje_cereal.pagado})


def cerrar_sesion(request):
    auth_logout(request)
    return redirect("login")