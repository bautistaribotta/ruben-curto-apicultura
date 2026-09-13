# Combustible: estaciones de servicio y cargas.

from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.contrib import messages
from django.http import JsonResponse

from main.models import EstacionDeServicio, CargaCombustible, periodo_actual

from main.services.combustible import (alternar_pago_carga, crear_carga, crear_estacion,
                                       editar_carga, editar_estacion, eliminar_carga,
                                       eliminar_estacion, obtener_cargas, obtener_datos_carga,
                                       obtener_datos_estacion, obtener_totales_cargas)
from main.services.comunes import filtro_tokens, mes_desplazado, resolver_periodo
from main.services.empleados import obtener_empleados_activos
from main.services.flota import obtener_vehiculos_activos

from .comunes import _rango_fechas, staff_required


@login_required(login_url="inicio")
def combustible(request):
    if request.method == "POST":
        id_estacion = request.POST.get("id_estacion")
        nombre = request.POST.get("nombre")
        id_eliminar = request.POST.get("id_eliminar")

        try:
            if id_eliminar:
                eliminar_estacion(id_eliminar)
                messages.success(request, "Estacion eliminada correctamente")
            elif id_estacion:
                editar_estacion(id_estacion, nombre)
                messages.success(request, "Estacion editada correctamente")
            else:
                crear_estacion(nombre)
                messages.success(request, "Estacion agregada correctamente")
        except ValueError as e:
            messages.error(request, str(e))

        # El formulario postea a la URL actual, asi que el mes que se estaba
        # mirando sigue en request.GET: lo devuelvo para no patear al usuario de
        # vuelta al mes en curso despues de tocar una estacion.
        destino = reverse("combustible")
        periodo_visto = resolver_periodo(request.GET.get("mes"))
        if periodo_visto != periodo_actual():
            destino = f"{destino}?mes={periodo_visto:%Y-%m}"
        return redirect(destino)

    # Listado de estaciones activas, con busqueda por nombre o id
    from django.db.models import Exists, OuterRef

    q = request.GET.get("q", "")
    estaciones = EstacionDeServicio.objects.filter(activa=True)

    if q:
        if q.isdigit():
            estaciones = estaciones.filter(id__icontains=q)
        else:
            estaciones = estaciones.filter(filtro_tokens(q, "nombre"))

    # Anoto el estado de deuda en una sola query (Exists) en vez de una por fila,
    # y de paso la suma de lo impago (Sum con filtro) para la columna de deuda.
    from django.db.models import Q, Sum

    cargas_impagas = CargaCombustible.objects.filter(
        estacion=OuterRef("pk"), activa=True, pagada=False
    )
    estaciones = estaciones.annotate(
        _tiene_deuda_anotado=Exists(cargas_impagas),
        _total_deuda_anotado=Sum(
            "cargas__monto", filter=Q(cargas__activa=True, cargas__pagada=False)
        ),
    ).order_by("nombre")

    paginator_estaciones = Paginator(estaciones, 5)
    pagina_numero = request.GET.get("page")
    pagina_obj = paginator_estaciones.get_page(pagina_numero)

    contexto = {"estaciones": pagina_obj, "q": q}

    # Peticion AJAX (busqueda/paginacion): devuelvo solo la tabla
    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        return render(request, "tabla_estaciones.html", contexto)

    # Mes que muestra la tarjeta de la cabecera. Sin parametro es el mes en curso;
    # las flechas del navegador lo corren con ?mes=YYYY-MM. La tabla de estaciones
    # no depende del mes (mide deuda total), asi que esto vive solo en el render
    # completo y no en la respuesta AJAX de busqueda/paginacion.
    periodo = resolver_periodo(request.GET.get("mes"))

    # Gasto en combustible del periodo: suma de las cargas activas cuya fecha cae
    # en ese mes (pagas o impagas, no importa el estado del pago). Los litros son
    # dato opcional en la carga, asi que Sum ignora las cargas sin litros: el total
    # es de las que si lo tienen y puede quedar por debajo del gasto real.
    totales_mes = CargaCombustible.objects.filter(
        activa=True, fecha__year=periodo.year, fecha__month=periodo.month
    ).aggregate(gasto=Sum("monto"), litros=Sum("litros"))
    contexto["periodo"] = periodo
    contexto["gasto_mes"] = totales_mes["gasto"] or 0
    contexto["litros_mes"] = totales_mes["litros"] or 0
    contexto["es_mes_actual"] = periodo == periodo_actual()
    contexto["mes_actual"] = periodo_actual()
    # Para las flechas del navegador de mes
    contexto["periodo_anterior"] = mes_desplazado(periodo, -1)
    contexto["periodo_siguiente"] = mes_desplazado(periodo, 1)

    return render(request, "combustible.html", contexto)


@login_required
def obtener_estacion_json(request, id_estacion):
    datos = obtener_datos_estacion(id_estacion)

    if datos:
        return JsonResponse(datos)

    return JsonResponse({"Error": "Estacion no encontrada"}, status=404)


@login_required(login_url="inicio")
def informacion_estacion(request, id_estacion):
    """Perfil de una estacion: todas sus cargas de combustible, pagas e impagas.

    Un solo POST rutea por 'accion' hacia el servicio correspondiente (mismo patron
    que la vista de flota): alta, edicion, baja logica y el toggle de pagado. El GET
    arma el historial de cargas y la lista de vehiculos para el alta.
    """
    estacion = get_object_or_404(EstacionDeServicio, id=id_estacion, activa=True)

    if request.method == "POST":
        accion = request.POST.get("accion")
        p = request.POST
        try:
            if accion == "editar_estacion":
                editar_estacion(id_estacion, p.get("nombre"))
                messages.success(request, "Estacion editada correctamente.")
            elif accion == "eliminar_estacion":
                eliminar_estacion(id_estacion)
                messages.success(request, "Estacion eliminada correctamente.")
                return redirect("combustible")
            elif accion == "nueva_carga":
                crear_carga(id_estacion, p.get("empleado"), p.get("vehiculo"), p.get("fecha"), p.get("monto"),
                            p.get("litros"), p.get("pagada") == "on")
                messages.success(request, "Carga agregada correctamente.")
            elif accion == "editar_carga":
                editar_carga(p.get("id_registro"), p.get("empleado"), p.get("vehiculo"), p.get("fecha"), p.get("monto"),
                             p.get("litros"), p.get("pagada") == "on")
                messages.success(request, "Carga actualizada correctamente.")
            elif accion == "eliminar_carga":
                eliminar_carga(p.get("id_registro"))
                messages.success(request, "Carga eliminada.")
            elif accion == "alternar_pago":
                alternar_pago_carga(p.get("id_registro"))
                messages.success(request, "Estado de pago actualizado.")
        except ValueError as e:
            messages.error(request, str(e))
        except Exception as e:
            messages.error(request, f"Ocurrió un error inesperado: {e}")

        return redirect("informacion_estacion", id_estacion=id_estacion)

    # Filtro por estado de pago (segmentado): por defecto solo las impagas.
    estado = request.GET.get("estado", "impagas")
    if estado not in ("impagas", "pagadas", "todas"):
        estado = "impagas"

    # Filtro por rango de fechas (chip + popover), por la fecha de la carga.
    desde, hasta, ctx_fechas = _rango_fechas(request)

    cargas = obtener_cargas(id_estacion, estado, desde, hasta)
    paginator = Paginator(cargas, 5)
    page_obj = paginator.get_page(request.GET.get("page"))

    # Totales de dinero y litros del mismo recorte que muestran los filtros.
    totales = obtener_totales_cargas(id_estacion, estado, desde, hasta)

    contexto = {
        "estacion": estacion,
        "page_obj": page_obj,
        "cargas": page_obj,
        "estado": estado,
        "total_monto": totales["total_monto"],
        "total_litros": totales["total_litros"],
        "total_cargas": estacion.cargas.filter(activa=True).count(),
        "empleados": obtener_empleados_activos(),
        "vehiculos": obtener_vehiculos_activos(),
        "pestaña": "viajes",
        **ctx_fechas,
    }
    return render(request, "informacion_estacion.html", contexto)


@staff_required
def obtener_carga_json(request, id_carga):
    datos = obtener_datos_carga(id_carga)

    if datos:
        return JsonResponse(datos)

    return JsonResponse({"Error": "Carga no encontrada"}, status=404)
