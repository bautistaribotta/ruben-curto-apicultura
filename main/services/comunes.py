"""
Helpers compartidos por varios servicios: validadores de texto, numero y
fecha, rangos de fechas y navegacion por mes, filtros de busqueda por
palabras, traduccion del IntegrityError de un unique al aviso de nombre
repetido, y el estado de cobro de los viajes.
"""

import re
from datetime import date, datetime, time
from decimal import Decimal, InvalidOperation

from django.utils import timezone
from django.conf import settings
from django.db import transaction, IntegrityError
from django.db.models import Q

from main.models import periodo_actual


def _aplicar_estado_pago(viaje, pagado):
    """Sincroniza el estado de cobro de un viaje con su fecha de pago.

    Lo usan por igual los viajes de reparto y los de cereal: ambos tienen los
    campos 'pagado' y 'fecha_pago'. Reglas:
    - pasa de impago a pagado -> sella el momento del cobro
    - ya estaba pagado        -> conserva la fecha original, no la refresca
    - vuelve a impago         -> limpia la fecha, para no mostrar una que ya no aplica

    No guarda: deja el objeto listo y que lo persista quien lo llamo.
    """
    pagado = bool(pagado)
    if pagado and not viaje.pagado:
        viaje.fecha_pago = timezone.now()
    elif not pagado:
        viaje.fecha_pago = None
    viaje.pagado = pagado
    return viaje


# --- Validadores REGEX ---
REGEX_TEXTO_BASICO = re.compile(r"^[a-zA-ZÁÉÍÓÚáéíóúñÑ\s]+$")
REGEX_TEXTO_NUMEROS = re.compile(r"^[a-zA-ZÁÉÍÓÚáéíóúñÑ\s\d]+$")
REGEX_PATENTE = re.compile(r"^[A-Z0-9]{6,7}$")
# El codigo de trazabilidad de granos (CTG) admite hasta 15 digitos, solo numeros
REGEX_CTG = re.compile(r"^[0-9]{1,15}$")
# El numero de factura admite hasta 20 digitos, solo numeros (conserva ceros a la izquierda)
REGEX_FACTURA = re.compile(r"^[0-9]{1,20}$")


def _guardar_unico(accion, mensaje):
    """
    Ejecuta 'accion' (un create o un save) y traduce el IntegrityError que tira la
    restriccion unica de la base al mismo ValueError que da el chequeo previo.

    El chequeo con exists() y el guardado son dos sentencias distintas: dos altas
    concurrentes del mismo nombre pasan las dos el chequeo y la segunda choca contra
    el unique de la base. Tambien cubre el nombre de un registro dado de baja, que
    el chequeo (acotado a los activos) deja pasar pero la base rechaza igual. Sin
    esto el usuario veia un error 500 en vez del aviso.

    El atomic interno es un savepoint: si el guardado falla, la transaccion que lo
    envuelve (si la hay) sigue usable, en vez de quedar rota como pasa en Postgres.
    """
    try:
        with transaction.atomic():
            return accion()
    except IntegrityError:
        raise ValueError(mensaje)


def filtro_tokens(q, *campos):
    """
    Arma un Q para buscar por varias palabras sobre uno o más campos: cada
    palabra del texto tiene que aparecer (icontains) en alguno de los campos, y
    todas las palabras tienen que estar presentes. Así "cera laminada" encuentra
    "Cera Estampada Laminada" y el orden no importa. Una sola palabra se comporta
    como un icontains común. Sin palabras devuelve un Q() vacío (no filtra nada).
    """
    filtro = Q()
    for palabra in (q or "").split():
        por_palabra = Q()
        for campo in campos:
            por_palabra |= Q(**{f"{campo}__icontains": palabra})
        filtro &= por_palabra
    return filtro


def filtro_nombre_apellido(q, prefijo=""):
    """
    Caso particular de filtro_tokens para nombre + apellido: "carola diaz"
    encuentra a Carola Diaz aunque sean columnas separadas y sin importar el
    orden. 'prefijo' permite reutilizarlo sobre relaciones, por ejemplo
    "cliente__" o "empleado__".
    """
    return filtro_tokens(q, f"{prefijo}nombre", f"{prefijo}apellido")


def _iniciales(nombre, apellido=None):
    # Siempre dos letras: inicial de nombre + inicial de apellido.
    # Sin apellido, uso las dos primeras letras del nombre.
    nombre = (nombre or "").strip()
    apellido = (apellido or "").strip()
    if apellido:
        return (nombre[:1] + apellido[:1]).upper()
    return nombre[:2].upper()


# Topes de la BD: 10 digitos con 2 decimales para el kilometraje, 12 para los
# costos. Los dejo como constantes para no repetir el numero magico en cada
# validador y que se lea de donde sale.
MAX_KILOMETROS = Decimal("99999999.99")
MAX_COSTO = Decimal("9999999999.99")


def _momento_local(fecha, fin_del_dia):
    """Convierte una fecha suelta en el instante que le corresponde en la zona local.

    Es el arranque (00:00) o el cierre (23:59:59) del dia segun el extremo del
    rango que se este armando.
    """
    momento = datetime.combine(fecha, time.max if fin_del_dia else time.min)
    if settings.USE_TZ:
        return timezone.make_aware(momento, timezone.get_current_timezone())
    return momento


def _acotar_rango(queryset, campo, desde, hasta, es_fecha_hora=True):
    """Acota un queryset a un rango de fechas inclusivo en ambos extremos.

    Los DateTimeField se comparan contra los instantes limite del dia y no con el
    lookup __date: sobre MySQL ese lookup se traduce a CONVERT_TZ(), que devuelve
    NULL si el motor no tiene cargadas las tablas de zonas horarias y deja el
    resumen vacio aunque el cliente tenga movimientos.
    """
    if desde:
        valor = _momento_local(desde, fin_del_dia=False) if es_fecha_hora else desde
        queryset = queryset.filter(**{f"{campo}__gte": valor})
    if hasta:
        valor = _momento_local(hasta, fin_del_dia=True) if es_fecha_hora else hasta
        queryset = queryset.filter(**{f"{campo}__lte": valor})
    return queryset


def _texto_opcional(valor, maximo, etiqueta):
    """Normaliza un campo de texto que puede venir vacio.

    En alquileres ningun dato es obligatorio, asi que el vacio no es un error:
    se guarda como None para que la base distinga "no lo cargue" de "es un
    string vacio". Lo unico que si valido es que no exceda el largo del modelo.
    """
    texto = str(valor or "").strip()
    if not texto:
        return None
    if len(texto) > maximo:
        raise ValueError(f"{etiqueta} no puede superar los {maximo} caracteres.")
    return texto


def _decimal_opcional(valor, etiqueta, maximo=None):
    """Convierte a Decimal un monto opcional del formulario de alquileres.

    Vacio devuelve None (dato sin cargar). Un texto que no es numero o un valor
    negativo si son errores: prefiero cortar aca con un mensaje claro antes de
    que la base rechace el insert.
    """
    if valor in (None, ""):
        return None

    try:
        numero = Decimal(str(valor).strip().replace(" ", ""))
    except (InvalidOperation, AttributeError):
        raise ValueError(f"{etiqueta} no es un número válido.")

    if numero < 0:
        raise ValueError(f"{etiqueta} no puede ser negativo.")

    numero = numero.quantize(Decimal("0.01"))
    if maximo is not None and numero > maximo:
        raise ValueError(f"{etiqueta} es demasiado grande.")
    return numero


def _entero_opcional(valor, etiqueta, maximo=None):
    """Como _decimal_opcional pero para los campos que no llevan centavos.

    Lo usan el alquiler mensual y la comision de la inmobiliaria, que se pactan
    en numeros redondos. Un valor con coma o punto decimal no se redondea por
    las buenas: corto con un mensaje, porque redondear en silencio cambiaria el
    monto que el usuario cree haber cargado.
    """
    if valor in (None, ""):
        return None

    texto = str(valor).strip().replace(" ", "")
    # El navegador manda "1500.00" cuando el input arranca con un valor viejo de
    # la base; esos ceros no son un decimal cargado a mano y se pueden tirar
    if "." in texto or "," in texto:
        entera, _, decimales = texto.replace(",", ".").partition(".")
        if decimales.strip("0"):
            raise ValueError(f"{etiqueta} tiene que ser un número entero, sin decimales.")
        texto = entera

    try:
        numero = int(texto)
    except ValueError:
        raise ValueError(f"{etiqueta} no es un número válido.")

    if numero < 0:
        raise ValueError(f"{etiqueta} no puede ser negativo.")

    if maximo is not None and numero > maximo:
        raise ValueError(f"{etiqueta} es demasiado grande.")
    return numero


def _parsear_dia(fecha, etiqueta):
    """Convierte a date lo que llega de un <input type="date">, o None si vino vacio."""
    if fecha in (None, ""):
        return None

    if isinstance(fecha, datetime):
        return fecha.date()

    if isinstance(fecha, date):
        return fecha

    try:
        return datetime.strptime(str(fecha).strip(), "%Y-%m-%d").date()
    except (ValueError, TypeError):
        raise ValueError(f"{etiqueta} no es válida.")


def resolver_periodo(valor):
    """Mes a mostrar en la pantalla, a partir del parametro 'mes' de la URL.

    Se diferencia de _parsear_periodo en que no explota: una URL escrita a mano
    o un enlace viejo no tienen por que romper la pantalla, simplemente caen en
    el mes en curso, que es lo que el usuario esperaba ver al entrar.
    """
    try:
        return _parsear_periodo(valor)
    except ValueError:
        return periodo_actual()


def mes_desplazado(periodo, meses):
    """Corre un periodo hacia adelante o atras. Sirve para las flechas del mes.

    Aritmetica sobre el indice absoluto de mes para no tener que pensar en el
    cambio de año: enero menos uno es diciembre del año anterior.
    """
    indice = periodo.year * 12 + (periodo.month - 1) + meses
    return date(indice // 12, indice % 12 + 1, 1)


def _fecha_obligatoria(fecha, etiqueta):
    """Como _parsear_dia pero sin permitir el vacio."""
    dia = _parsear_dia(fecha, etiqueta)
    if dia is None:
        raise ValueError(f"{etiqueta} es obligatoria.")
    return dia


def _parsear_periodo(periodo):
    """Mes que cubre el pago, normalizado siempre al dia 1.

    Acepta "YYYY-MM" (lo que manda un input month) y "YYYY-MM-DD" (por si el
    front usa un date comun). Vacio es el mes en curso, que es el caso normal:
    se cobra el alquiler del mes y se carga en el momento.
    """
    if periodo in (None, ""):
        return periodo_actual()

    if isinstance(periodo, datetime):
        periodo = periodo.date()

    if isinstance(periodo, date):
        return date(periodo.year, periodo.month, 1)

    texto = str(periodo).strip()
    for formato in ("%Y-%m", "%Y-%m-%d"):
        try:
            convertida = datetime.strptime(texto, formato).date()
        except ValueError:
            continue
        return date(convertida.year, convertida.month, 1)

    raise ValueError("El período del pago no es válido.")
