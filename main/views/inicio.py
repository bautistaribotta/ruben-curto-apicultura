# Login, cierre de sesion, tablero de inicio y actualizacion de cotizaciones.

import json

from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login as auth_login, logout as auth_logout
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import ensure_csrf_cookie
from django.contrib import messages
from django.http import JsonResponse

from main.services.cotizaciones import (actualizar_cotizacion, get_cotizacion_dolar_oficial,
                                        get_tablero_inicio)


def login(request):
    if request.method == "POST":
        usuario = request.POST.get("user")
        password = request.POST.get("password")

        usuario_valido = authenticate(request, username=usuario, password=password)

        # Si es válido los redirijo, si no, envío el error por mensaje
        if usuario_valido is not None:
            auth_login(request, usuario_valido)
            return redirect("inicio")

        else:
            messages.error(request, "Usuario y/o contraseña incorrectos")
            return redirect("login")

    return render(request, "login.html")


"""
Si un usuario anónimo (sin loguearse) quiere acceder a las paginas internas, 
le bloqueo el acceso y lo envio de vuelta a '/' (pagina configurada del inicio del server) 
para que se loguee. Todo esto implementado usando el wrapped @login_required
"""


@login_required
def inicio(request):
    dolar_oficial = get_cotizacion_dolar_oficial()
    contexto = {"oficial": dolar_oficial, "grupos": get_tablero_inicio()}
    return render(request, "inicio.html", contexto)


@login_required
@ensure_csrf_cookie
def actualizar_cotizacion_ajax(request):
    # Las cotizaciones las maneja solo el personal administrativo. El resto ve
    # las tarjetas sin la edicion, pero el chequeo va aca porque la plantilla
    # sola no frena un POST armado a mano contra esta URL.
    if not request.user.is_staff:
        return JsonResponse({"error": "No tiene permiso para modificar las cotizaciones"}, status=403)

    if request.method == "POST":
        try:
            datos = json.loads(request.body)
            articulo = datos.get("articulo")
            monto = datos.get("monto")

            if articulo and monto is not None:
                if float(monto) < 1:
                    return JsonResponse({"error": "La cotización no puede ser menor a 1"}, status=400)
                actualizar_cotizacion(articulo, monto)
                return JsonResponse({"ok": True})
            else:
                return JsonResponse({"error": "Datos incompletos"}, status=400)
        except Exception as e:
            return JsonResponse({"error": str(e)}, status=500)
    return JsonResponse({"error": "Método no permitido"}, status=405)


def cerrar_sesion(request):
    auth_logout(request)
    return redirect("login")
