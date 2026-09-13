# Empleados: listado, perfil con pagos y cuenta corriente, y datos para el modal.

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.admin.views.decorators import staff_member_required
from django.core.paginator import Paginator
from django.contrib import messages
from django.http import JsonResponse
from django.utils import timezone

from main.models import Empleado

from main.services.comunes import filtro_nombre_apellido
from main.services.empleados import (crear_empleado, crear_pago_empleado, desplazar_periodo_pagos,
                                     editar_empleado, editar_pago_empleado, eliminar_empleado,
                                     eliminar_pago_empleado, etiqueta_periodo_pagos,
                                     fijar_sueldo_empleado, fijar_vencimiento_carnet,
                                     obtener_cuenta_corriente, obtener_datos_empleado,
                                     rango_periodo_pagos, resolver_ancla_pagos)

from .comunes import _estado_carnet


def _contexto_pagos_empleado(request, empleado):
    """Arma el bloque de cuenta corriente del perfil para el mes pedido en la URL.

    El mes (su primer dia, en 'pagos_ancla') viaja por la URL, asi el bloque es
    enlazable y sobrevive al POST de un pago nuevo. Se muestran todos los
    movimientos del mes, sin paginar, para no cortar semanas entre paginas.
    """
    inicio = resolver_ancla_pagos(request.GET.get("pagos_ancla"))
    desde, hasta = rango_periodo_pagos(inicio)

    cuenta = obtener_cuenta_corriente(empleado, desde, hasta)

    # Mes actual: resolver_ancla_pagos(None) cae siempre en el mes de hoy. Si el
    # mes que se mira no es ese, la barra ofrece un atajo para volver.
    mes_actual = resolver_ancla_pagos(None)

    return {
        "pagos": cuenta["filas"],
        "cuenta": cuenta,
        "pagos_inicio": inicio,
        "pagos_fin": hasta,
        "pagos_label": etiqueta_periodo_pagos(inicio),
        "pagos_ancla_anterior": desplazar_periodo_pagos(inicio, -1),
        "pagos_ancla_siguiente": desplazar_periodo_pagos(inicio, 1),
        "pagos_es_mes_actual": inicio == mes_actual,
        "pagos_mes_actual": mes_actual,
    }


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

    # El listado muestra el vencimiento del carnet con su semaforo: anoto el
    # estado en cada empleado de la pagina (solo 10, no hace falta tocar la query).
    hoy = timezone.localdate()
    for emp in pagina_obj:
        emp.estado_carnet = _estado_carnet(emp.vencimiento_carnet, hoy)

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

            if accion == "carnet":
                # El mismo modal da de alta la fecha del carnet y despues la edita.
                nuevo = empleado.vencimiento_carnet is None
                fijar_vencimiento_carnet(empleado.id, request.POST.get("vencimiento_carnet"))
                messages.success(
                    request,
                    "Vencimiento del carnet cargado correctamente" if nuevo
                    else "Vencimiento del carnet actualizado correctamente",
                )
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

    # El bloque de cuenta corriente se refresca solo con sus flechas de mes, asi
    # que ante frag=pagos devuelvo unicamente ese pedazo.
    es_ajax = request.headers.get("x-requested-with") == "XMLHttpRequest"
    if es_ajax and request.GET.get("frag") == "pagos":
        return render(request, "pagos_empleado.html", {
            "empleado": empleado,
            **_contexto_pagos_empleado(request, empleado),
        })

    contexto = {
        "empleado": empleado,
        "estado_carnet": _estado_carnet(empleado.vencimiento_carnet, timezone.localdate()),
        **_contexto_pagos_empleado(request, empleado),
    }

    return render(request, "informacion_empleado.html", contexto)


@staff_member_required
def obtener_empleado_json(request, id_empleado):
    datos = obtener_datos_empleado(id_empleado)

    if datos:
        # Si el empleado existe y está activo, devuelvo sus datos en formato JSON
        return JsonResponse(datos)

    # Si no lo encuentro o está inactivo, devuelvo un error 404
    return JsonResponse({"Error": "Empleado no encontrado"}, status=404)
