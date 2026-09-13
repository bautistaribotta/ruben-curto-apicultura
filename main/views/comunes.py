"""
Helpers compartidos por varias vistas: lectura de rangos de fechas y flags
del formulario, armado de URLs de vuelta, estado del carnet de conducir y el
decorador de acceso del staff.
"""

from datetime import timedelta

from django.urls import reverse
from django.contrib.auth.decorators import user_passes_test
from django.utils.dateparse import parse_date
from django.utils.formats import date_format

from main.services.comunes import mes_desplazado


def _pagado_del_formulario(request):
    """Lee la casilla de cobro de los slide-over de viajes (reparto y cereal).

    El estado de pago lo maneja solo el staff, asi que para el resto devuelvo None:
    los servicios de edicion interpretan ese None como "no toques el campo" y el
    viaje conserva el estado que ya tenia en vez de volver a impago.
    """
    if not request.user.is_staff:
        return None
    # Un checkbox sin marcar directamente no viaja en el POST: la ausencia es "no pagado"
    return request.POST.get("pagado") is not None


def _url_con_gasto(url, id_gasto):
    """Marca en la vuelta cual fue el gasto que se acaba de tocar.

    Despues del POST la pagina se recarga entera y la lista de gastos vuelve al
    principio del scroll: sin esta marca el usuario ve un cartel verde pero no
    ve que cambio. Con el id en la URL, el front busca esa fila, la trae a la
    vista y la resalta un segundo.

    Al eliminar no hay fila que marcar, asi que la URL vuelve limpia.
    """
    if not id_gasto:
        return url
    separador = "&" if "?" in url else "?"
    return f"{url}{separador}gasto={id_gasto}"


def _volver_estacion_url(request):
    """URL de la ficha de estacion a la que debe volver el boton del viaje.

    Cuando se entra a un viaje desde una carga de combustible, la fila manda
    ?volver_estacion=<id>. Solo acepto un id numerico y armo la URL yo, asi el
    boton nunca redirige a un destino arbitrario. Vacia si no vino el parametro.
    """
    id_estacion = request.GET.get("volver_estacion", "")
    if id_estacion.isdigit():
        return reverse("informacion_estacion", kwargs={"id_estacion": id_estacion})
    return ""


def _etiqueta_rango(desde, hasta):
    """Texto del chip de fechas para un rango ya normalizado (desde/hasta date o None).

    Un mes entero (del 1 al ultimo dia del mismo mes) se nombra por su mes y año
    ("Julio 2026"), que es lo que arma el modo "mes" del popover; si no, cae en un
    solo dia, un rango cerrado o un rango abierto con un unico extremo. Es la unica
    fuente del texto del chip, compartida por todas las vistas que filtran por fecha.
    """
    if (desde and hasta and desde.day == 1
            and (desde.year, desde.month) == (hasta.year, hasta.month)
            and hasta + timedelta(days=1) == mes_desplazado(desde, 1)):
        return date_format(desde, "F Y").capitalize()
    if desde and hasta and desde == hasta:
        return desde.strftime("%d/%m/%Y")
    if desde and hasta:
        return f"{desde.strftime('%d/%m')} – {hasta.strftime('%d/%m/%Y')}"
    if desde:
        return f"Desde {desde.strftime('%d/%m/%Y')}"
    if hasta:
        return f"Hasta {hasta.strftime('%d/%m/%Y')}"
    return "Fechas"


def _rango_fechas(request):
    """Lee y normaliza el rango de fechas del filtro (chip + popover) reutilizado en
    varias vistas (viajes, estacion, alquileres, cheques, deudas).

    Devuelve (desde, hasta, ctx) donde desde/hasta son date o None (ya listos para
    filtrar el queryset) y ctx trae desde/hasta en ISO y fecha_label para la
    plantilla (rellenan el popover y pintan el chip ya al cargar la pagina). El
    popover ofrece los modos dia / mes / rango; los tres terminan en un desde y un
    hasta, asi que el mes entero se reconoce por sus extremos (ver _etiqueta_rango).
    """
    desde = parse_date(request.GET.get("desde", ""))
    hasta = parse_date(request.GET.get("hasta", ""))
    # Si el usuario invierte el rango, lo normalizo para no devolver un listado vacio.
    if desde and hasta and desde > hasta:
        desde, hasta = hasta, desde

    ctx = {
        "desde": desde.isoformat() if desde else "",
        "hasta": hasta.isoformat() if hasta else "",
        "fecha_label": _etiqueta_rango(desde, hasta),
    }
    return desde, hasta, ctx


def _estado_carnet(fecha, hoy):
    """Traduce la fecha de vencimiento del carnet a un estado con semaforo.

    Mismo lenguaje que los vencimientos de los vehiculos (vencido/proximo/
    vigente), pero con una ventana de aviso mas amplia: el carnet se renueva
    con turno y tramite, asi que "por vencer" se enciende con 60 dias de
    anticipacion en vez de 30. Devuelve None si todavia no se cargo la fecha,
    para que la plantilla muestre el estado "sin dato".
    """
    if not fecha:
        return None

    dias = (fecha - hoy).days
    if dias < 0:
        nivel = "vencido"
    elif dias <= 60:
        nivel = "proximo"
    else:
        nivel = "vigente"

    return {
        "fecha": fecha,
        "dias_restantes": dias,
        "dias_abs": abs(dias),
        "nivel": nivel,
    }


"""
Las secciones de combustible, IVA y cheques son solo para el personal: las ve
cualquier miembro del staff, sin necesidad de ser superusuario.
"""
staff_required = user_passes_test(lambda u: u.is_staff, login_url="inicio")
