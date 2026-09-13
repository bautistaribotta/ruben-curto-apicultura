# IVA: empresas y sus operaciones de debito y credito fiscal.

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.contrib import messages
from django.http import JsonResponse

from main.models import Empresa, OperacionIva, periodo_actual

from main.services.comunes import mes_desplazado, resolver_periodo
from main.services.iva import (crear_empresa, crear_operacion_iva, editar_empresa,
                               editar_operacion_iva, eliminar_empresa, eliminar_operacion_iva,
                               obtener_datos_empresa, obtener_datos_operacion_iva,
                               obtener_empresas_activas, obtener_operaciones_iva,
                               obtener_totales_iva)

from .comunes import staff_required


def _contexto_totales_iva(request):
    """Contexto de la barra superior de totales de IVA (todas las empresas juntas).

    Por defecto totaliza el anio en curso. Con ?mes=YYYY-MM pasa a un mes puntual
    y con ?anio=YYYY vuelve a un anio entero. Arma tambien las URLs de las flechas
    y del toggle Mes/Ano aca, para no meter esa logica en la plantilla.
    """
    hoy = periodo_actual()

    # --- Modo mes: ?mes=YYYY-MM ---
    if request.GET.get("mes"):
        periodo = resolver_periodo(request.GET.get("mes"))
        anterior = mes_desplazado(periodo, -1)
        siguiente = mes_desplazado(periodo, 1)
        return {
            "iva_modo": "mes",
            "iva_totales": obtener_totales_iva(periodo.year, periodo.month),
            "iva_periodo": periodo,
            "iva_url_anterior": f"?mes={anterior:%Y-%m}",
            "iva_url_siguiente": f"?mes={siguiente:%Y-%m}",
            "iva_url_mes": f"?mes={periodo:%Y-%m}",
            "iva_url_anio": f"?anio={periodo.year}",
        }

    # --- Modo anio (default): ?anio=YYYY ---
    try:
        anio = int(request.GET.get("anio", hoy.year))
    except (TypeError, ValueError):
        anio = hoy.year
    # Acoto el rango para no totalizar anios absurdos escritos a mano en la URL
    if not (2000 <= anio <= 2100):
        anio = hoy.year

    # El toggle "Mes" cae en el mes en curso si es el anio actual; si no, en enero
    mes_destino = hoy.month if anio == hoy.year else 1
    return {
        "iva_modo": "anio",
        "iva_totales": obtener_totales_iva(anio),
        "iva_anio": anio,
        "iva_url_anterior": f"?anio={anio - 1}",
        "iva_url_siguiente": f"?anio={anio + 1}",
        "iva_url_mes": f"?mes={anio}-{mes_destino:02d}",
        "iva_url_anio": f"?anio={anio}",
    }


@staff_required
def iva(request):
    """Listado de empresas/sociedades con su IVA debito, credito y saldo.

    Cada empresa se muestra como tarjeta (mismo patron que la flota). Un solo POST
    rutea por 'accion' hacia el servicio de alta, edicion o baja de la empresa; el
    buscador filtra las tarjetas del lado del cliente, como en flota.
    """
    if request.method == "POST":
        accion = request.POST.get("accion")
        p = request.POST
        try:
            if accion == "nueva_empresa":
                crear_empresa(p.get("nombre"))
                messages.success(request, "Empresa agregada correctamente.")
            elif accion == "editar_empresa":
                editar_empresa(p.get("id_empresa"), p.get("nombre"))
                messages.success(request, "Empresa actualizada correctamente.")
            elif accion == "eliminar_empresa":
                eliminar_empresa(p.get("id_empresa"))
                messages.success(request, "Empresa eliminada correctamente.")
        except ValueError as e:
            messages.error(request, str(e))
        except Exception as e:
            messages.error(request, f"Ocurrió un error inesperado: {e}")

        return redirect("iva")

    contexto = {"empresas": obtener_empresas_activas()}
    contexto.update(_contexto_totales_iva(request))
    return render(request, "iva.html", contexto)


@login_required
def obtener_empresa_json(request, id_empresa):
    datos = obtener_datos_empresa(id_empresa)
    if datos:
        return JsonResponse(datos)
    return JsonResponse({"Error": "Empresa no encontrada"}, status=404)


@login_required
def obtener_operacion_iva_json(request, id_operacion):
    datos = obtener_datos_operacion_iva(id_operacion)
    if datos:
        return JsonResponse(datos)
    return JsonResponse({"Error": "Operacion no encontrada"}, status=404)


@staff_required
def informacion_empresa(request, id_empresa):
    """Ficha de una empresa: su IVA debito/credito/saldo y el historial de
    operaciones. Un solo POST rutea por 'accion' hacia el servicio correspondiente
    (mismo patron que informacion_estacion); el GET arma el historial filtrable.
    """
    # Con con_totales_iva ya llega anotada para el resumen, sin N+1 en el GET
    empresa = get_object_or_404(Empresa.objects.con_totales_iva(), id=id_empresa, activa=True)

    if request.method == "POST":
        accion = request.POST.get("accion")
        p = request.POST
        try:
            if accion == "editar_empresa":
                editar_empresa(id_empresa, p.get("nombre"))
                messages.success(request, "Empresa actualizada correctamente.")
            elif accion == "eliminar_empresa":
                eliminar_empresa(id_empresa)
                messages.success(request, "Empresa eliminada correctamente.")
                return redirect("iva")
            elif accion == "nueva_operacion":
                crear_operacion_iva(id_empresa, p.get("tipo"), p.get("fecha"), p.get("monto_neto"),
                                    p.get("alicuota"), p.get("detalle"))
                messages.success(request, "Operación agregada correctamente.")
            elif accion == "editar_operacion":
                editar_operacion_iva(p.get("id_registro"), p.get("tipo"), p.get("fecha"),
                                     p.get("monto_neto"), p.get("alicuota"), p.get("detalle"))
                messages.success(request, "Operación actualizada correctamente.")
            elif accion == "eliminar_operacion":
                eliminar_operacion_iva(p.get("id_registro"))
                messages.success(request, "Operación eliminada.")
        except ValueError as e:
            messages.error(request, str(e))
        except Exception as e:
            messages.error(request, f"Ocurrió un error inesperado: {e}")

        return redirect("informacion_empresa", id_empresa=id_empresa)

    # Filtro por tipo de operacion (segmentado): todas por defecto
    tipo = request.GET.get("tipo", "todas")
    if tipo not in ("todas", "ventas", "compras"):
        tipo = "todas"

    operaciones = obtener_operaciones_iva(id_empresa, tipo)
    paginator = Paginator(operaciones, 8)
    page_obj = paginator.get_page(request.GET.get("page"))

    contexto = {
        "empresa": empresa,
        "page_obj": page_obj,
        "operaciones": page_obj,
        "tipo": tipo,
        "total_operaciones": OperacionIva.objects.filter(empresa_id=id_empresa).count(),
        "alicuotas": OperacionIva.ALICUOTAS,
    }
    return render(request, "informacion_empresa.html", contexto)
