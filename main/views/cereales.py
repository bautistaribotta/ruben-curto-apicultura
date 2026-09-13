# Viajes de cereales.

from django.shortcuts import render, redirect
from django.urls import reverse
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.contrib import messages
from django.http import JsonResponse

from main.models import ViajeCereal, GastoViajeCereal

from main.services.cereales import (crear_gasto_viaje_cereal, crear_viaje_cereal,
                                    editar_viaje_cereal, eliminar_viaje_cereal,
                                    marcar_pago_viaje_cereal, obtener_datos_viaje_cereal,
                                    obtener_resumen_cereal, obtener_viajes_cereales)
from main.services.combustible import obtener_estaciones_activas
from main.services.empleados import obtener_empleados_activos
from main.services.filtros import (incluir_asignado, nombre_empleado_filtro, nombre_vehiculo_filtro,
                                   opciones_destinos_cereal, opciones_empleados_filtro,
                                   opciones_vehiculos_filtro)
from main.services.flota import obtener_vehiculos_activos
from main.services.viajes import editar_gasto_viaje, eliminar_gasto_viaje

from .comunes import _pagado_del_formulario, _rango_fechas, _url_con_gasto, _volver_estacion_url


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
                # La factura es opcional: si llega vacia el servicio la guarda como None
                numero_factura = request.POST.get("numero_factura")
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
                                   pagado=bool(_pagado_del_formulario(request)),
                                   numero_factura=numero_factura)
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

    # Busqueda por numero de factura (pildora -> modal con input de texto). A
    # diferencia de los otros filtros, es texto libre: uso icontains para que sirva
    # aunque el operador no recuerde los ceros a la izquierda (buscar "7777" trae
    # tambien la factura "0007777").
    factura = request.GET.get("factura", "").strip()
    if factura:
        lista_viajes = lista_viajes.filter(numero_factura__icontains=factura)

    # Estado de cobro (segmentado "Por cobrar / Todas"). Por defecto "cobrar": la
    # tabla y las tarjetas arrancan mostrando lo que todavia falta cobrar (viajes
    # con pagado=False), que es lo que el cliente mira primero. El segmentado vive
    # con las tarjetas (solo staff), asi que el filtro solo aplica para el staff:
    # el resto sigue viendo el listado completo como antes.
    pago = request.GET.get("pago", "cobrar")
    if pago not in ("cobrar", "todas"):
        pago = "cobrar"
    if request.user.is_staff and pago == "cobrar":
        lista_viajes = lista_viajes.filter(pagado=False)

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
        "factura": factura,
        "pago": pago,
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
            numero_factura = request.POST.get("numero_factura")
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
                    numero_factura=numero_factura,
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
            # Datos extra que solo llegan cuando el gasto es de combustible.
            id_estacion = request.POST.get("estacion_gasto")
            litros_gasto = request.POST.get("litros_gasto")
            pagada_gasto = request.POST.get("pagada_gasto") == "on"
            gasto_marcado = ""

            try:
                if accion == "nuevo_gasto_cereal":
                    gasto_marcado = crear_gasto_viaje_cereal(id_viaje_cereal, tipo_gasto, monto_gasto,
                                                             id_estacion, litros_gasto, pagada_gasto).id
                    messages.success(request, "Gasto registrado exitosamente.")
                elif accion == "editar_gasto_cereal":
                    gasto_marcado = editar_gasto_viaje(GastoViajeCereal, id_gasto,
                                                       tipo_gasto, monto_gasto,
                                                       id_estacion, litros_gasto, pagada_gasto).id
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
        "estaciones": obtener_estaciones_activas(),
        "volver_url": _volver_estacion_url(request),
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
