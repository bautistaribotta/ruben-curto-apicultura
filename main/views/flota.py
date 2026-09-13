# Flota: listado de vehiculos y perfil con km, seguros, VTV, services y observaciones.

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone

from main.models import Vehiculo

from main.services.empleados import obtener_empleados_activos
from main.services.flota import (crear_observacion, crear_registro_km, crear_seguro, crear_servis,
                                 crear_vehiculo, crear_vtv, editar_observacion, editar_registro_km,
                                 editar_seguro, editar_servis, editar_vehiculo, editar_vtv,
                                 eliminar_observacion, eliminar_registro_km, eliminar_seguro,
                                 eliminar_servis, eliminar_vehiculo, eliminar_vtv,
                                 obtener_observaciones, obtener_registros_km, obtener_seguros,
                                 obtener_servicios, obtener_vehiculos_activos, obtener_vtvs)

from .comunes import _estado_carnet


@login_required
def flota(request):
    if request.method == "POST":
        accion = request.POST.get("accion")

        try:
            # Los empleados ya no se gestionan desde flota: alta, edicion y baja
            # viven en la vista de empleados. Aca solo quedan los vehiculos.
            if accion == "nuevo_vehiculo":
                crear_vehiculo(request.POST.get("nombre_vehiculo", ""), request.POST.get("patente_vehiculo", ""))
                messages.success(request, "Vehículo registrado exitosamente.")

            elif accion == "editar_vehiculo":
                editar_vehiculo(request.POST.get("id_vehiculo"), request.POST.get("nombre_vehiculo", ""),
                                request.POST.get("patente_vehiculo", ""), True)
                messages.success(request, "Vehículo actualizado correctamente.")

            elif accion == "eliminar_vehiculo":
                eliminar_vehiculo(request.POST.get("id_vehiculo"))
                messages.success(request, "Vehículo eliminado correctamente.")

        except ValueError as e:
            # Capturo cualquier error de validación proveniente de services.py
            messages.error(request, str(e))
        except Exception as e:
            # Capturo errores inesperados (ej: base de datos)
            messages.error(request, f"Ocurrió un error inesperado: {e}")

        return redirect("flota")

    # Lista de empleados con el vencimiento de su carnet para el modal de la
    # barra de herramientas. Se ordena por vencimiento mas proximo primero y
    # los que no tienen fecha cargada quedan al final.
    hoy = timezone.localdate()
    empleados_carnet = list(obtener_empleados_activos())
    for emp in empleados_carnet:
        emp.estado_carnet = _estado_carnet(emp.vencimiento_carnet, hoy)
    empleados_carnet.sort(key=lambda e: (e.vencimiento_carnet is None, e.vencimiento_carnet or hoy))

    contexto = {
        "vehiculos": obtener_vehiculos_activos(),
        "empleados_carnet": empleados_carnet,
        "pestaña": "viajes",
    }
    return render(request, "flota.html", contexto)


def _con_dias_restantes(registros, hoy):
    """Anota en cada registro con vigencia el estado de su vencimiento.

    Devuelve la lista ya evaluada (no un queryset) porque el template vuelve a
    recorrerla y los atributos calculados se perderian si se re-consultara. En
    cada registro deja:
      - dias_restantes: dias hasta el fin (negativo si ya venció)
      - dias_abs: la misma cantidad en positivo, para redactar el texto
      - nivel: "vencido", "proximo" (vence dentro de 30 dias) o "vigente"
    """
    lista = list(registros)
    for registro in lista:
        dias = (registro.fin - hoy).days
        registro.dias_restantes = dias
        registro.dias_abs = abs(dias)
        if dias < 0:
            registro.nivel = "vencido"
        elif dias <= 30:
            registro.nivel = "proximo"
        else:
            registro.nivel = "vigente"
    return lista


@login_required
def informacion_vehiculo(request, id_vehiculo):
    """Perfil de un vehiculo: kilometraje, seguros, VTV, services y observaciones.

    Cada tipo de dato cuelga del vehiculo con su propia tabla editable. Un solo
    POST rutea por el campo 'accion' hacia el servicio correspondiente (mismo
    patron que la vista de flota), y el GET arma el contexto con los historiales
    y los dias que faltan para cada vencimiento.
    """
    vehiculo = get_object_or_404(Vehiculo, id=id_vehiculo, activo=True)

    if request.method == "POST":
        accion = request.POST.get("accion")
        p = request.POST
        try:
            if accion == "nuevo_km":
                crear_registro_km(id_vehiculo, p.get("fecha"), p.get("kilometros"))
                messages.success(request, "Kilometraje agregado correctamente.")
            elif accion == "editar_km":
                editar_registro_km(p.get("id_registro"), p.get("fecha"), p.get("kilometros"))
                messages.success(request, "Kilometraje actualizado correctamente.")
            elif accion == "eliminar_km":
                eliminar_registro_km(p.get("id_registro"))
                messages.success(request, "Carga de kilometraje eliminada.")

            elif accion == "nuevo_seguro":
                crear_seguro(id_vehiculo, p.get("inicio"), p.get("fin"), p.get("costo"), p.get("observaciones"))
                messages.success(request, "Seguro agregado correctamente.")
            elif accion == "editar_seguro":
                editar_seguro(p.get("id_registro"), p.get("inicio"), p.get("fin"), p.get("costo"), p.get("observaciones"))
                messages.success(request, "Seguro actualizado correctamente.")
            elif accion == "eliminar_seguro":
                eliminar_seguro(p.get("id_registro"))
                messages.success(request, "Seguro eliminado.")

            elif accion == "nueva_vtv":
                crear_vtv(id_vehiculo, p.get("inicio"), p.get("fin"), p.get("costo"), p.get("observaciones"))
                messages.success(request, "VTV agregada correctamente.")
            elif accion == "editar_vtv":
                editar_vtv(p.get("id_registro"), p.get("inicio"), p.get("fin"), p.get("costo"), p.get("observaciones"))
                messages.success(request, "VTV actualizada correctamente.")
            elif accion == "eliminar_vtv":
                eliminar_vtv(p.get("id_registro"))
                messages.success(request, "VTV eliminada.")

            elif accion == "nuevo_servis":
                crear_servis(id_vehiculo, p.get("fecha"), p.get("costo"), p.get("observaciones"))
                messages.success(request, "Service agregado correctamente.")
            elif accion == "editar_servis":
                editar_servis(p.get("id_registro"), p.get("fecha"), p.get("costo"), p.get("observaciones"))
                messages.success(request, "Service actualizado correctamente.")
            elif accion == "eliminar_servis":
                eliminar_servis(p.get("id_registro"))
                messages.success(request, "Service eliminado.")

            elif accion == "nueva_obs":
                crear_observacion(id_vehiculo, p.get("fecha"), p.get("texto"))
                messages.success(request, "Observación agregada correctamente.")
            elif accion == "editar_obs":
                editar_observacion(p.get("id_registro"), p.get("fecha"), p.get("texto"))
                messages.success(request, "Observación actualizada correctamente.")
            elif accion == "eliminar_obs":
                eliminar_observacion(p.get("id_registro"))
                messages.success(request, "Observación eliminada.")

        except ValueError as e:
            messages.error(request, str(e))
        except Exception as e:
            messages.error(request, f"Ocurrió un error inesperado: {e}")

        return redirect("informacion_vehiculo", id_vehiculo=id_vehiculo)

    hoy = timezone.localdate()
    seguros = _con_dias_restantes(obtener_seguros(id_vehiculo), hoy)
    vtvs = _con_dias_restantes(obtener_vtvs(id_vehiculo), hoy)
    servicios = list(obtener_servicios(id_vehiculo))

    contexto = {
        "vehiculo": vehiculo,
        "registros_km": list(obtener_registros_km(id_vehiculo)),
        "kilometraje_actual": vehiculo.kilometraje_actual,
        "seguros": seguros,
        "vtvs": vtvs,
        "servicios": servicios,
        "observaciones": list(obtener_observaciones(id_vehiculo)),
        # El registro vigente es el primero (orden por -fin / -fecha): de el sale el
        # resumen de vencimientos de la cabecera.
        "seguro_vigente": seguros[0] if seguros else None,
        "vtv_vigente": vtvs[0] if vtvs else None,
        "ultimo_servis": servicios[0] if servicios else None,
        "pestaña": "viajes",
    }
    return render(request, "informacion_vehiculo.html", contexto)
