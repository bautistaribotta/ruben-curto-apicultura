# Clientes: listado, perfil con sus operaciones, busqueda y resumen de cuenta corriente.

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.contrib import messages
from django.http import JsonResponse, HttpResponse
from django.utils import timezone
from django.utils.dateparse import parse_date

from main.models import Cliente, Operacion
from main.pdf_services import ResumenCuenta

from main.services.cereales import obtener_viajes_cereal_de_cliente
from main.services.clientes import (buscar_clientes, editar_cliente, eliminar_cliente,
                                    nuevo_cliente, obtener_datos_cliente,
                                    obtener_movimientos_cuenta_corriente,
                                    obtener_saldo_anterior_cuenta_corriente)
from main.services.comunes import filtro_nombre_apellido


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

    operaciones_cliente = Operacion.objects.filter(cliente=cliente).con_totales().prefetch_related("detalleoperacion_set__producto", "detalleoperacion_set__cotizacion", "pago_set").order_by("-fecha", "-id")

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
    saldo_anterior = obtener_saldo_anterior_cuenta_corriente(cliente, desde)
    movimientos, totales = obtener_movimientos_cuenta_corriente(
        cliente, desde, hasta, saldo_inicial=saldo_anterior
    )

    pdf = ResumenCuenta(
        cliente=cliente,
        movimientos=movimientos,
        totales=totales,
        desde=desde,
        hasta=hasta,
        saldo_anterior=saldo_anterior if desde else None,
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
