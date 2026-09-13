# Viajes de miel/cera: listado y detalle con gastos, caja y devolucion.

from django.shortcuts import render, redirect
from django.urls import reverse
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.contrib import messages

from main.models import Cliente, Viaje, Gasto

from main.services.combustible import obtener_estaciones_activas
from main.services.comunes import _iniciales
from main.services.empleados import crear_empleado, obtener_empleados_activos
from main.services.filtros import (incluir_asignado, nombre_empleado_filtro, nombre_vehiculo_filtro,
                                   opciones_destinos_viaje, opciones_empleados_filtro,
                                   opciones_vehiculos_filtro)
from main.services.flota import crear_vehiculo, obtener_vehiculos_activos
from main.services.viajes import (crear_gasto, crear_ingreso_caja, crear_viaje, editar_gasto_viaje,
                                  editar_ingreso_caja, editar_viaje, eliminar_gasto_viaje,
                                  eliminar_ingreso_caja, eliminar_viaje, obtener_datos_viaje,
                                  obtener_viajes, registrar_devolucion_caja)

from .comunes import _rango_fechas, _url_con_gasto, _volver_estacion_url


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
            # Datos extra que solo llegan cuando el gasto es de combustible.
            id_estacion = request.POST.get("estacion_gasto")
            litros_gasto = request.POST.get("litros_gasto")
            pagada_gasto = request.POST.get("pagada_gasto") == "on"
            gasto_marcado = ""

            try:
                if accion == "nuevo_gasto":
                    gasto_marcado = crear_gasto(id_viaje, tipo_gasto, monto_gasto,
                                                id_estacion, litros_gasto, pagada_gasto).id
                    messages.success(request, "Gasto registrado exitosamente.")
                elif accion == "editar_gasto":
                    gasto_marcado = editar_gasto_viaje(Gasto, id_gasto, tipo_gasto, monto_gasto,
                                                       id_estacion, litros_gasto, pagada_gasto).id
                    messages.success(request, "Gasto actualizado correctamente.")
                else:
                    eliminar_gasto_viaje(Gasto, id_gasto)
                    messages.success(request, "Gasto eliminado correctamente.")
            except ValueError as e:
                messages.error(request, str(e))
            except Exception as e:
                messages.error(request, f"Ocurrió un error inesperado: {e}")

            return redirect(_url_con_gasto(url_detalle, gasto_marcado))

        elif accion in ("nuevo_ingreso", "editar_ingreso", "eliminar_ingreso"):
            # El dinero de la caja lo maneja solo el staff, igual que el resumen
            # y los botones que abren el modal: el servidor dice lo mismo que el
            # template, que muestra todo esto dentro de {% if user.is_staff %}.
            if not request.user.is_staff:
                messages.error(request, "No tenés permiso para tocar la caja del viaje.")
                return redirect("informacion_viaje", id_viaje=id_viaje)

            url_detalle = reverse("informacion_viaje", kwargs={"id_viaje": id_viaje})
            monto_ingreso = request.POST.get("monto_ingreso")
            id_ingreso = request.POST.get("id_ingreso")
            ingreso_marcado = ""

            try:
                if accion == "nuevo_ingreso":
                    ingreso_marcado = crear_ingreso_caja(id_viaje, monto_ingreso).id
                    messages.success(request, "Dinero agregado a la caja exitosamente.")
                elif accion == "editar_ingreso":
                    ingreso_marcado = editar_ingreso_caja(id_ingreso, monto_ingreso).id
                    messages.success(request, "Ingreso a caja actualizado correctamente.")
                else:
                    eliminar_ingreso_caja(id_ingreso)
                    messages.success(request, "Ingreso a caja eliminado correctamente.")
            except ValueError as e:
                messages.error(request, str(e))
            except Exception as e:
                messages.error(request, f"Ocurrió un error inesperado: {e}")

            # Misma marca que los gastos, pero con su propia clave para que el
            # front resalte la fila del ingreso recien tocado (ver ingreso_caja.js).
            destino = url_detalle
            if ingreso_marcado:
                separador = "&" if "?" in destino else "?"
                destino = f"{destino}{separador}ingreso={ingreso_marcado}"
            return redirect(destino)

        elif accion == "registrar_devolucion":
            # La devolucion del sobrante toca la caja y puede generar un pago del
            # empleado: es solo del staff, igual que el resto del resumen de caja.
            if not request.user.is_staff:
                messages.error(request, "No tenés permiso para tocar la caja del viaje.")
                return redirect("informacion_viaje", id_viaje=id_viaje)

            estado = request.POST.get("estado_devolucion", "")
            monto_devuelto = request.POST.get("monto_devuelto")

            try:
                registrar_devolucion_caja(id_viaje, estado, monto_devuelto)
                if estado == Viaje.DEVOLUCION_SIN_REGISTRAR:
                    messages.success(request, "Devolución de caja borrada correctamente.")
                else:
                    messages.success(request, "Devolución de caja registrada correctamente.")
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
        .order_by("-fecha", "-id")
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
        'estaciones': obtener_estaciones_activas(),
        'volver_url': _volver_estacion_url(request),
    }
    return render(request, "informacion_viaje.html", contexto)
