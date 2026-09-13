# Viajes de reparto (Mercado Libre) y catalogo de destinos.

from django.shortcuts import render, redirect
from django.urls import reverse
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.contrib import messages
from django.http import JsonResponse

from main.models import GastoViajeReparto

from main.services.combustible import obtener_estaciones_activas
from main.services.empleados import obtener_empleados_activos
from main.services.filtros import (incluir_asignado, nombre_destino_reparto_filtro,
                                   nombre_empleado_filtro, nombre_vehiculo_filtro,
                                   opciones_destinos_reparto_filtro, opciones_empleados_filtro,
                                   opciones_vehiculos_filtro)
from main.services.flota import obtener_vehiculos_activos
from main.services.reparto import (crear_destino_reparto, crear_gasto_viaje_reparto,
                                   crear_viaje_reparto, editar_destino_reparto,
                                   editar_viaje_reparto, eliminar_destino_reparto,
                                   eliminar_viaje_reparto, marcar_pago_viaje_reparto,
                                   obtener_datos_viaje_reparto, obtener_destinos_reparto,
                                   obtener_resumen_reparto, obtener_viajes_reparto)
from main.services.viajes import editar_gasto_viaje, eliminar_gasto_viaje

from .comunes import _pagado_del_formulario, _rango_fechas, _url_con_gasto, _volver_estacion_url


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
                fecha_viaje_reparto = request.POST.get("fecha_viaje_reparto")
                id_destino = request.POST.get("id_destino")
                # Cuanto se cobra el viaje lo maneja solo el staff: el campo ni siquiera
                # esta en el formulario del resto, y lo que llegue por POST se ignora
                # para que nadie fije la tarifa a mano. Con None, el servicio le pone la
                # tarifa del catalogo del destino elegido.
                valor_viaje = request.POST.get("valor_viaje") if request.user.is_staff else None

                # 2. Validacion de presencia de lo obligatorio (lo esencial en la vista).
                # El valor del viaje solo es obligatorio para el staff: si no lo mandan,
                # el destino ya trae su tarifa.
                obligatorios = [id_empleado, id_vehiculo, gasto_combustible, costo_empleado,
                                fecha_viaje_reparto, id_destino]
                if request.user.is_staff:
                    obligatorios.append(valor_viaje)
                if not all(obligatorios):
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
        "pago": pago,
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
            fecha_viaje_reparto = request.POST.get("fecha_viaje_reparto")
            id_destino = request.POST.get("id_destino")
            # Cuanto se cobra el viaje lo maneja solo el staff: el campo no esta en el
            # formulario del resto y lo que llegue por POST se ignora. Sin staff, el
            # monto guardado se conserva tal cual; si la edicion cambia de localidad
            # mando None para que el servicio aplique la tarifa del destino nuevo, que
            # es lo mismo que hace el JS en el formulario del staff.
            if request.user.is_staff:
                valor_viaje = request.POST.get("valor_viaje")
            elif str(viaje_reparto.destino_id) == str(id_destino):
                valor_viaje = viaje_reparto.valor_viaje
            else:
                valor_viaje = None

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
            # Datos extra que solo llegan cuando el gasto es de combustible.
            id_estacion = request.POST.get("estacion_gasto")
            litros_gasto = request.POST.get("litros_gasto")
            pagada_gasto = request.POST.get("pagada_gasto") == "on"
            gasto_marcado = ""

            try:
                if accion == "nuevo_gasto_reparto":
                    gasto_marcado = crear_gasto_viaje_reparto(id_viaje_reparto, tipo_gasto, monto_gasto,
                                                              id_estacion, litros_gasto, pagada_gasto).id
                    messages.success(request, "Gasto registrado exitosamente.")
                elif accion == "editar_gasto_reparto":
                    gasto_marcado = editar_gasto_viaje(GastoViajeReparto, id_gasto,
                                                       tipo_gasto, monto_gasto,
                                                       id_estacion, litros_gasto, pagada_gasto).id
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
        "estaciones": obtener_estaciones_activas(),
        "volver_url": _volver_estacion_url(request),
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
