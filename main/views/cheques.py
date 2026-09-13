# Cheques a pagar: listado por empresa, bancos y cuentas corrientes.

from django.shortcuts import render, redirect, get_object_or_404
from django.core.paginator import Paginator
from django.contrib import messages
from django.http import JsonResponse
from django.template.defaultfilters import floatformat

from main.models import Empresa, Cheque, periodo_actual

from main.services.cheques import (crear_banco, crear_cheque, crear_cuenta_corriente, editar_banco,
                                   editar_cheque, editar_cuenta_corriente, eliminar_banco,
                                   eliminar_cheque, eliminar_cuenta_corriente,
                                   marcar_cobrado_cheque, obtener_bancos_activos, obtener_cheques,
                                   obtener_cuentas_corrientes, obtener_datos_cheque,
                                   obtener_empresas_con_cheques,
                                   obtener_empresas_para_selector_cheques, obtener_totales_cheques)
from main.services.comunes import mes_desplazado, resolver_periodo
from main.services.iva import crear_empresa, editar_empresa, eliminar_empresa

from .comunes import _rango_fechas, staff_required


# ==========================================================================
#  CHEQUES
# ==========================================================================

def _url_cheques(empresa_id, **params):
    """Query string del listado de cheques preservando la empresa elegida.

    Las flechas y el toggle Mes/Año cambian el periodo pero no deben perder el
    filtro de empresa de la pildora, asi que este helper lo reinyecta en cada URL.
    """
    partes = []
    if empresa_id:
        partes.append(f"empresa={empresa_id}")
    partes += [f"{clave}={valor}" for clave, valor in params.items()]
    return "?" + "&".join(partes)


def _contexto_totales_cheques(request, empresa_id=""):
    """Contexto de la banda de totales de cheques (todas las empresas juntas).

    A diferencia de IVA, arranca en el MES en curso: los cheques son flujo mensual
    (fecha de cobro, vencimiento a 30 dias). ?mes=YYYY-MM fija un mes puntual y
    ?anio=YYYY totaliza el anio entero. Devuelve tambien el (anio, mes) del periodo
    para que la vista arme las cifras y las tarjetas. Cada cheque cae en el periodo
    por su fecha de cobro.
    """
    hoy = periodo_actual()

    # --- Modo anio: ?anio=YYYY (explicito, sin ?mes) ---
    if request.GET.get("anio") and not request.GET.get("mes"):
        try:
            anio = int(request.GET.get("anio"))
        except (TypeError, ValueError):
            anio = hoy.year
        if not (2000 <= anio <= 2100):
            anio = hoy.year
        # El toggle "Mes" cae en el mes en curso si es el anio actual; si no, enero
        mes_destino = hoy.month if anio == hoy.year else 1
        ctx = {
            "cheque_modo": "anio",
            "cheque_anio": anio,
            "cheque_url_anterior": _url_cheques(empresa_id, anio=anio - 1),
            "cheque_url_siguiente": _url_cheques(empresa_id, anio=anio + 1),
            "cheque_url_mes": _url_cheques(empresa_id, mes=f"{anio}-{mes_destino:02d}"),
            "cheque_url_anio": _url_cheques(empresa_id, anio=anio),
        }
        return ctx, anio, None

    # --- Modo mes (default): ?mes=YYYY-MM o el mes en curso ---
    periodo = resolver_periodo(request.GET.get("mes"))
    anterior = mes_desplazado(periodo, -1)
    siguiente = mes_desplazado(periodo, 1)
    ctx = {
        "cheque_modo": "mes",
        "cheque_periodo": periodo,
        "cheque_url_anterior": _url_cheques(empresa_id, mes=f"{anterior:%Y-%m}"),
        "cheque_url_siguiente": _url_cheques(empresa_id, mes=f"{siguiente:%Y-%m}"),
        "cheque_url_mes": _url_cheques(empresa_id, mes=f"{periodo:%Y-%m}"),
        "cheque_url_anio": _url_cheques(empresa_id, anio=periodo.year),
    }
    return ctx, periodo.year, periodo.month


@staff_required
def cheques(request):
    """Listado de empresas/sociedades con su total a pagar en cheques del periodo.

    Espejo de la vista iva: tarjetas por empresa y un POST que rutea por 'accion'
    hacia el alta/edicion de la empresa (compartida con IVA). La banda navega el
    periodo (Mes/Año, arrancando en el mes en curso) y una pildora filtra por
    empresa; cada cheque cae en el periodo por su fecha de cobro. La baja de empresa
    no se ofrece aca: se hace desde IVA para no ocultarla de ambas secciones.
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
                # Baja logica compartida con IVA: la empresa es la misma entidad.
                eliminar_empresa(p.get("id_empresa"))
                messages.success(request, "Empresa eliminada correctamente.")
        except ValueError as e:
            messages.error(request, str(e))
        except Exception as e:
            messages.error(request, f"Ocurrió un error inesperado: {e}")

        return redirect("cheques")

    # Empresa elegida en la pildora (filtra la grilla). Un id invalido se ignora
    # para no dejar el filtro pegado sobre una empresa inexistente o dada de baja.
    empresa_id = request.GET.get("empresa") or ""
    empresa_sel = None
    if empresa_id:
        empresa_sel = Empresa.objects.filter(activa=True, id=empresa_id).first()
        if empresa_sel is None:
            empresa_id = ""

    ctx_periodo, anio, mes = _contexto_totales_cheques(request, empresa_id)

    empresas = obtener_empresas_con_cheques(anio, mes)
    if empresa_sel:
        empresas = empresas.filter(id=empresa_sel.id)

    contexto = {
        "empresas": empresas,
        "totales": obtener_totales_cheques(anio, mes),
        "empresas_selector": obtener_empresas_para_selector_cheques(),
        "empresa_filtro": empresa_id,
        "empresa_filtro_nombre": empresa_sel.nombre if empresa_sel else "",
    }
    contexto.update(ctx_periodo)
    return render(request, "cheques.html", contexto)


@staff_required
def informacion_empresa_cheques(request, id_empresa):
    """Ficha de cheques de una empresa: sus cuentas corrientes (con saldo desglosado)
    y el historial de cheques filtrable. Un solo POST rutea por 'accion' hacia el
    servicio correspondiente (cuenta corriente o cheque); el GET arma el historial.
    """
    empresa = get_object_or_404(Empresa.objects.con_totales_cheques(), id=id_empresa, activa=True)

    if request.method == "POST":
        accion = request.POST.get("accion")
        p = request.POST
        try:
            if accion == "editar_empresa":
                editar_empresa(id_empresa, p.get("nombre"))
                messages.success(request, "Empresa actualizada correctamente.")
            elif accion == "eliminar_empresa":
                # Baja logica compartida con IVA: vuelve al listado de Cheques.
                eliminar_empresa(id_empresa)
                messages.success(request, "Empresa eliminada correctamente.")
                return redirect("cheques")
            elif accion == "nueva_cuenta":
                crear_cuenta_corriente(id_empresa, p.get("id_banco"), p.get("numero"))
                messages.success(request, "Cuenta corriente agregada correctamente.")
            elif accion == "editar_cuenta":
                editar_cuenta_corriente(p.get("id_registro"), p.get("id_banco"), p.get("numero"))
                messages.success(request, "Cuenta corriente actualizada correctamente.")
            elif accion == "eliminar_cuenta":
                eliminar_cuenta_corriente(p.get("id_registro"))
                messages.success(request, "Cuenta corriente eliminada.")
            elif accion == "nuevo_cheque":
                crear_cheque(p.get("id_cuenta_corriente"), p.get("numero"), p.get("fecha_emision"),
                             p.get("fecha_cobro"), p.get("concepto"), p.get("importe"))
                messages.success(request, "Cheque agregado correctamente.")
            elif accion == "editar_cheque":
                editar_cheque(p.get("id_registro"), p.get("id_cuenta_corriente"), p.get("numero"),
                              p.get("fecha_emision"), p.get("fecha_cobro"), p.get("concepto"), p.get("importe"))
                messages.success(request, "Cheque actualizado correctamente.")
            elif accion == "eliminar_cheque":
                eliminar_cheque(p.get("id_registro"))
                messages.success(request, "Cheque eliminado.")
        except ValueError as e:
            messages.error(request, str(e))
        except Exception as e:
            messages.error(request, f"Ocurrió un error inesperado: {e}")

        return redirect("informacion_empresa_cheques", id_empresa=id_empresa)

    # Filtro por fecha de cobro (chip + popover, reutilizado de deudas)
    desde, hasta, ctx_fechas = _rango_fechas(request)

    # Filtro por estado de cobro (pildora + menu). Por defecto se muestran solo los
    # pendientes; cualquier valor no reconocido tambien cae en "pendientes".
    ESTADOS_CHEQUE = {"pendientes": "Pendientes", "cobrados": "Cobrados", "todos": "Todos"}
    estado = request.GET.get("estado", "pendientes")
    if estado not in ESTADOS_CHEQUE:
        estado = "pendientes"

    lista_cheques = obtener_cheques(id_empresa, desde, hasta, estado)
    paginator = Paginator(lista_cheques, 8)
    page_obj = paginator.get_page(request.GET.get("page"))

    contexto = {
        "empresa": empresa,
        "cuentas": obtener_cuentas_corrientes(id_empresa),
        "bancos": obtener_bancos_activos(),
        "page_obj": page_obj,
        "cheques": page_obj,
        "total_cheques": Cheque.objects.filter(cuenta_corriente__empresa_id=id_empresa,
                                               cuenta_corriente__activa=True).count(),
        "estado_cheques": estado,
        "estado_label": ESTADOS_CHEQUE[estado],
    }
    contexto.update(ctx_fechas)
    return render(request, "informacion_empresa_cheques.html", contexto)


@staff_required
def bancos(request):
    """Catalogo de bancos (alta / edicion / baja logica). Espejo del de destinos."""
    if request.method == "POST":
        accion = request.POST.get("accion")
        p = request.POST
        try:
            if accion == "nuevo_banco":
                crear_banco(p.get("nombre"))
                messages.success(request, "Banco agregado correctamente.")
            elif accion == "editar_banco":
                editar_banco(p.get("id_banco"), p.get("nombre"))
                messages.success(request, "Banco actualizado correctamente.")
            elif accion == "eliminar_banco":
                eliminar_banco(p.get("id_banco"))
                messages.success(request, "Banco eliminado correctamente.")
        except ValueError as e:
            messages.error(request, str(e))
        except Exception as e:
            messages.error(request, f"Ocurrió un error inesperado: {e}")

        return redirect("bancos")

    return render(request, "bancos.html", {"bancos": obtener_bancos_activos()})


@staff_required
def obtener_cheque_json(request, id_cheque):
    datos = obtener_datos_cheque(id_cheque)
    if datos:
        return JsonResponse(datos)
    return JsonResponse({"Error": "Cheque no encontrado"}, status=404)


@staff_required
def marcar_cobrado_cheque_ajax(request, id_cheque):
    """Casilla de cobrado de la tabla de cheques: alterna 'cobrado' sin recargar.

    Como el cobrado saca al cheque del total a pagar, la respuesta trae los saldos
    ya recalculados (empresa y cuenta) para que la vista los actualice sin refrescar.
    Devuelve 'pagado' ademas de 'cobrado' para reutilizar pago_viaje.js tal cual.
    """
    if request.method != "POST":
        return JsonResponse({"error": "Método no permitido"}, status=405)

    cheque = marcar_cobrado_cheque(id_cheque, request.POST.get("pagado") == "1")
    cuenta = cheque.cuenta_corriente
    mensaje = "Cheque marcado como cobrado." if cheque.cobrado else "Cheque marcado como no cobrado."
    return JsonResponse({
        "ok": True,
        "pagado": cheque.cobrado,
        "cobrado": cheque.cobrado,
        "mensaje": mensaje,
        "id_cuenta": cuenta.id,
        "total_empresa_txt": floatformat(cuenta.empresa.cheques_a_pagar, "2g"),
        "total_cuenta_txt": floatformat(cuenta.cheques_a_pagar, "2g"),
    })
