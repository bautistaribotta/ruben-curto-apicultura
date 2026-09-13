# Marcos: listado de recepciones, procesamiento y entregas, y datos para el modal.

from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.contrib import messages
from django.http import JsonResponse
from django.utils import timezone

from main.models import OperacionMarco

from main.services.marcos import (crear_marco, editar_marco, eliminar_marco,
                                  nombre_cliente_marcos_filtro, obtener_datos_marco, obtener_marcos,
                                  opciones_clientes_marcos)

from .comunes import _rango_fechas


@login_required
def marcos(request):
    """Listado de operaciones de marcos: alta, edicion, baja y filtros.

    Mismo esquema que las demas secciones: el POST hace su accion y redirige
    (patron POST-Redirect-GET) y el GET arma el listado filtrado. Cuando la
    peticion es AJAX devuelve solo la tabla, que es la region que refrescan los
    filtros y la paginacion.
    """
    if request.method == "POST":
        accion = request.POST.get("accion")

        try:
            if accion == "eliminar_marco":
                eliminar_marco(request.POST.get("id_eliminar"))
                messages.success(request, "Operación de marcos eliminada.")

            else:
                # Alta y edicion comparten el formulario del slide-over: si viaja
                # el id oculto es una edicion, si no es una tanda nueva.
                id_marco = request.POST.get("id_marco")
                datos = (request.POST.get("id_cliente"),
                         request.POST.get("cantidad"),
                         request.POST.get("estado"),
                         request.POST.get("fecha_recepcion"),
                         # Vacia mientras los marcos siguen en el galpon
                         request.POST.get("fecha_entrega") or None)

                if id_marco:
                    editar_marco(id_marco, *datos)
                    messages.success(request, "Operación de marcos actualizada.")
                else:
                    crear_marco(*datos)
                    messages.success(request, "Operación de marcos registrada.")

        except ValueError as e:
            # Errores de validacion que llegan de services.py
            messages.error(request, str(e))
        except Exception as e:
            messages.error(request, f"Ocurrió un error inesperado: {e}")

        return redirect("marcos")

    lista_marcos = obtener_marcos()

    # Filtro por cliente (chip -> modal selector): se elige de una lista, no se tipea.
    cliente = request.GET.get("cliente", "")
    if cliente.isdigit():
        lista_marcos = lista_marcos.filter(cliente_id=cliente)

    # Filtro por estado de los marcos (pildora con menu). Vacio = todos.
    estado = request.GET.get("estado", "")
    if estado not in dict(OperacionMarco.ESTADOS):
        estado = ""
    if estado:
        lista_marcos = lista_marcos.filter(estado=estado)

    # Filtro por fecha (chip + popover), sobre la fecha de recepcion: es el dia en
    # que la tanda entro a la empresa y el eje de toda la operacion.
    desde, hasta, ctx_fechas = _rango_fechas(request)
    if desde:
        lista_marcos = lista_marcos.filter(fecha_recepcion__gte=desde)
    if hasta:
        lista_marcos = lista_marcos.filter(fecha_recepcion__lte=hasta)

    paginator = Paginator(lista_marcos, 10)
    page_obj = paginator.get_page(request.GET.get("page"))

    contexto = {
        "page_obj": page_obj,
        "cliente": cliente,
        "cliente_nombre": nombre_cliente_marcos_filtro(cliente),
        "clientes_filtro": opciones_clientes_marcos(),
        "estado": estado,
        "estados": OperacionMarco.ESTADOS,
        # Hoy, para que el slide-over abra con la recepcion del dia ya puesta
        "hoy": timezone.localdate().isoformat(),
        **ctx_fechas,
    }

    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        return render(request, "tabla_marcos.html", contexto)

    return render(request, "marcos.html", contexto)


@login_required
def obtener_marco_json(request, id_marco):
    """Datos de una operacion de marcos para rellenar el slide-over de edicion."""
    datos = obtener_datos_marco(id_marco)
    if datos is None:
        return JsonResponse({"error": "Operación de marcos no encontrada"}, status=404)
    return JsonResponse(datos)
