# Alquileres: listado mes a mes, perfil de una casa, contratos, gastos y cobro del mes.

from django.shortcuts import render, redirect
from django.urls import reverse
from django.contrib.admin.views.decorators import staff_member_required
from django.core.paginator import Paginator
from django.contrib import messages
from django.http import JsonResponse
from django.utils.formats import date_format
from django.contrib.humanize.templatetags.humanize import intcomma
from django.template.defaultfilters import floatformat

from main.models import periodo_actual

from main.services.alquileres import (FILTROS_ALQUILERES, crear_casa, crear_contrato,
                                      crear_gasto_casa, editar_casa, editar_contrato,
                                      editar_gasto_casa, eliminar_casa, eliminar_contrato,
                                      eliminar_gasto_casa, marcar_pago_alquiler, obtener_casas,
                                      obtener_contrato_de_casa, obtener_datos_casa,
                                      obtener_detalle_alquiler, obtener_resumen_alquileres)
from main.services.comunes import mes_desplazado, resolver_periodo

from .comunes import _rango_fechas


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
    desde, hasta, ctx_fechas = _rango_fechas(request)

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
