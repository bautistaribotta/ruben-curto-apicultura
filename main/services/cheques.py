# Cheques a pagar: bancos, cuentas corrientes y cheques de cada empresa.

from decimal import Decimal

from django.shortcuts import get_object_or_404
from django.db import transaction
from django.db.models import Sum
from django.template.defaultfilters import floatformat

from main.models import Empresa, Banco, CuentaCorriente, Cheque

from .comunes import _decimal_opcional, _fecha_obligatoria, _guardar_unico, filtro_tokens


# ==========================================================================
#  CHEQUES
# ==========================================================================
# Tres piezas: el banco (catalogo compartido), la cuenta corriente (empresa +
# banco) y el cheque (siempre a pagar, cuelga de una cuenta). La empresa no recibe
# cheques como cobro; su total a pagar es la suma de los importes de sus cheques.

MAX_IMPORTE_CHEQUE = Decimal("9999999999999.99")

# --- BANCOS ------------------------------------------------------------------
# Catalogo simple (nombre + activo), espejo de las estaciones de servicio. La
# baja es logica para no perder las cuentas y los cheques que lo referencian.

def _validar_nombre_banco(nombre, excluir_id=None):
    """Limpia y valida el nombre de un banco. Devuelve el nombre normalizado."""
    nombre = (nombre or "").strip()
    if not (2 <= len(nombre) <= 60):
        raise ValueError("El nombre del banco debe tener entre 2 y 60 caracteres.")

    duplicado = (Banco.objects
                 .filter(nombre__iexact=nombre, activo=True)
                 .exclude(id=excluir_id)
                 .exists())
    if duplicado:
        raise ValueError("Ya existe un banco con ese nombre.")
    return nombre


def obtener_bancos_activos(q=None):
    """Bancos activos en orden alfabetico. Filtra por nombre si llega busqueda."""
    bancos = Banco.objects.filter(activo=True)
    if q:
        bancos = bancos.filter(filtro_tokens(q, "nombre"))
    return bancos.order_by("nombre", "id")


def crear_banco(nombre):
    nombre = _validar_nombre_banco(nombre)
    return _guardar_unico(lambda: Banco.objects.create(nombre=nombre),
                          "Ya existe un banco con ese nombre.")


def editar_banco(id_banco, nombre):
    banco = get_object_or_404(Banco, id=id_banco)
    banco.nombre = _validar_nombre_banco(nombre, excluir_id=banco.id)
    _guardar_unico(banco.save, "Ya existe un banco con ese nombre.")
    return banco


def eliminar_banco(id_banco):
    """Baja logica: preserva las cuentas corrientes y cheques del banco."""
    banco = get_object_or_404(Banco, id=id_banco)
    banco.activo = False
    banco.save(update_fields=["activo"])
    return banco


def obtener_datos_banco(id_banco):
    """Datos de un banco para precargar el panel de edicion, o None."""
    try:
        banco = Banco.objects.get(id=id_banco, activo=True)
    except Banco.DoesNotExist:
        return None
    return {"id": banco.id, "nombre": banco.nombre}


# --- CUENTAS CORRIENTES ------------------------------------------------------

def _validar_numero_cuenta(numero):
    numero = (numero or "").strip()
    if not (1 <= len(numero) <= 40):
        raise ValueError("El número de cuenta corriente es obligatorio (hasta 40 caracteres).")
    return numero


def obtener_cuentas_corrientes(id_empresa):
    """Cuentas corrientes activas de una empresa, con su saldo de cheques anotado.

    Ordenadas por banco y numero. Trae el banco en la misma query (select_related)
    para no disparar una consulta por cuenta al mostrar su nombre.
    """
    return (CuentaCorriente.objects
            .filter(empresa_id=id_empresa, activa=True)
            .select_related("banco")
            .con_totales_cheques()
            .order_by("banco__nombre", "numero", "id"))


def crear_cuenta_corriente(id_empresa, id_banco, numero):
    """Registra una cuenta corriente de una empresa en un banco.

    Serializa las altas de una misma empresa bloqueando su fila (select_for_update),
    igual que marcar_pago_alquiler bloquea la casa. El chequeo de duplicado corre
    recien bajo ese lock, asi que dos altas concurrentes de la misma cuenta no
    pueden pasar las dos: la segunda espera y ya ve la que creo la primera. No hay
    UniqueConstraint que lo respalde porque MySQL no soporta constraints
    condicionales, y una sin condicion impediria volver a dar de alta un numero
    cuya cuenta anterior fue dada de baja (activa=False), que hoy esta permitido.
    """
    with transaction.atomic():
        empresa = get_object_or_404(Empresa.objects.select_for_update(), id=id_empresa, activa=True)
        if not id_banco:
            raise ValueError("Elegí un banco para la cuenta corriente.")
        banco = get_object_or_404(Banco, id=id_banco, activo=True)
        numero = _validar_numero_cuenta(numero)

        # No repetir la misma cuenta (empresa + banco + numero) entre las activas
        duplicada = (CuentaCorriente.objects
                     .filter(empresa=empresa, banco=banco, numero__iexact=numero, activa=True)
                     .exists())
        if duplicada:
            raise ValueError("Esa cuenta corriente ya existe para esta empresa en ese banco.")

        return CuentaCorriente.objects.create(empresa=empresa, banco=banco, numero=numero)


def editar_cuenta_corriente(id_cuenta, id_banco, numero):
    # Mismo lock por empresa que crear_cuenta_corriente: una edicion que choque con
    # un alta (o con otra edicion) de la misma cuenta tampoco puede duplicarla.
    with transaction.atomic():
        cuenta = get_object_or_404(CuentaCorriente, id=id_cuenta)
        get_object_or_404(Empresa.objects.select_for_update(), id=cuenta.empresa_id)
        if not id_banco:
            raise ValueError("Elegí un banco para la cuenta corriente.")
        banco = get_object_or_404(Banco, id=id_banco, activo=True)
        numero = _validar_numero_cuenta(numero)

        duplicada = (CuentaCorriente.objects
                     .filter(empresa=cuenta.empresa, banco=banco, numero__iexact=numero, activa=True)
                     .exclude(id=cuenta.id)
                     .exists())
        if duplicada:
            raise ValueError("Esa cuenta corriente ya existe para esta empresa en ese banco.")

        cuenta.banco = banco
        cuenta.numero = numero
        cuenta.save()
        return cuenta


def eliminar_cuenta_corriente(id_cuenta):
    """Baja logica: saca la cuenta (y sus cheques del saldo) sin perder el historial."""
    cuenta = get_object_or_404(CuentaCorriente, id=id_cuenta)
    cuenta.activa = False
    cuenta.save(update_fields=["activa"])
    return cuenta


def obtener_datos_cuenta_corriente(id_cuenta):
    """Datos de una cuenta corriente para precargar el panel de edicion, o None."""
    try:
        cuenta = CuentaCorriente.objects.get(id=id_cuenta, activa=True)
    except CuentaCorriente.DoesNotExist:
        return None
    return {"id": cuenta.id, "id_banco": cuenta.banco_id, "numero": cuenta.numero}


# --- CHEQUES -----------------------------------------------------------------

def _validar_numero_cheque(numero):
    """Numero del cheque: obligatorio, solo digitos, hasta 20. Devuelve el texto."""
    texto = (numero or "").strip()
    if not texto:
        raise ValueError("El número de cheque es obligatorio.")
    if not texto.isdigit() or len(texto) > 20:
        raise ValueError("El número de cheque debe tener solo dígitos (hasta 20).")
    return texto


def _validar_cheque(numero, fecha_emision, fecha_cobro, concepto, importe):
    """Limpia y valida los datos de un cheque. Devuelve la tupla lista."""
    nro = _validar_numero_cheque(numero)

    emision = _fecha_obligatoria(fecha_emision, "La fecha de emisión")
    cobro = _fecha_obligatoria(fecha_cobro, "La fecha de cobro")
    if cobro < emision:
        raise ValueError("La fecha de cobro no puede ser anterior a la de emisión.")

    texto = (concepto or "").strip()
    if not (2 <= len(texto) <= 250):
        raise ValueError("El concepto es obligatorio y puede tener hasta 250 caracteres.")

    monto = _decimal_opcional(importe, "El importe", MAX_IMPORTE_CHEQUE)
    if not monto:
        raise ValueError("El importe es obligatorio y tiene que ser mayor a cero.")

    return nro, emision, cobro, texto, monto


def obtener_cheques(id_empresa, desde=None, hasta=None, estado="pendientes"):
    """Cheques a pagar de las cuentas corrientes activas de una empresa.

    Ordenados por fecha de cobro (los mas proximos primero, ver Meta del modelo).
    Trae la cuenta y el banco en la misma query para la tabla. El filtro de fecha
    (desde/hasta, inclusive) acota por la fecha de cobro, que es la que ordena y
    agrupa los cheques.

    'estado' filtra por el cobro: "pendientes" (por defecto, cobrado=False),
    "cobrados" (cobrado=True) o "todos" (sin filtrar). Cualquier valor no
    reconocido cae en "pendientes", que es la vista por defecto.
    """
    cheques = (Cheque.objects
               .filter(cuenta_corriente__empresa_id=id_empresa, cuenta_corriente__activa=True)
               .select_related("cuenta_corriente__banco"))
    if estado == "cobrados":
        cheques = cheques.filter(cobrado=True)
    elif estado != "todos":
        cheques = cheques.filter(cobrado=False)
    if desde:
        cheques = cheques.filter(fecha_cobro__gte=desde)
    if hasta:
        cheques = cheques.filter(fecha_cobro__lte=hasta)
    return cheques


def crear_cheque(id_cuenta_corriente, numero=None, fecha_emision=None, fecha_cobro=None,
                 concepto=None, importe=None):
    """Registra un cheque a pagar en una cuenta corriente activa."""
    if not id_cuenta_corriente:
        raise ValueError("Elegí la cuenta corriente del cheque.")
    cuenta = get_object_or_404(CuentaCorriente, id=id_cuenta_corriente, activa=True)
    nro, emision, cobro, texto, monto = _validar_cheque(numero, fecha_emision, fecha_cobro,
                                                        concepto, importe)
    return Cheque.objects.create(
        cuenta_corriente=cuenta, numero=nro, fecha_emision=emision, fecha_cobro=cobro,
        concepto=texto, importe=monto,
    )


def editar_cheque(id_cheque, id_cuenta_corriente=None, numero=None, fecha_emision=None,
                  fecha_cobro=None, concepto=None, importe=None):
    """Corrige un cheque ya cargado (puede moverse a otra cuenta de la empresa)."""
    cheque = get_object_or_404(Cheque, id=id_cheque)
    if not id_cuenta_corriente:
        raise ValueError("Elegí la cuenta corriente del cheque.")
    cuenta = get_object_or_404(CuentaCorriente, id=id_cuenta_corriente, activa=True)
    nro, emision, cobro, texto, monto = _validar_cheque(numero, fecha_emision, fecha_cobro,
                                                        concepto, importe)
    cheque.cuenta_corriente = cuenta
    cheque.numero = nro
    cheque.fecha_emision, cheque.fecha_cobro = emision, cobro
    cheque.concepto, cheque.importe = texto, monto
    """
    Guardo solo los campos del formulario: un save() completo reescribia tambien
    'cobrado' con el valor leido al abrir el panel, y pisaba el cobro que alguien
    marcara desde la casilla mientras tanto.
    """
    cheque.save(update_fields=["cuenta_corriente", "numero", "fecha_emision", "fecha_cobro",
                               "concepto", "importe"])
    return cheque


def eliminar_cheque(id_cheque):
    """Borra un cheque: lo unico que se borra es un registro cargado mal, y ahi el
    borrado real es lo correcto (no ensucia el saldo con bajas logicas)."""
    cheque = get_object_or_404(Cheque, id=id_cheque)
    cheque.delete()
    return cheque


def marcar_cobrado_cheque(id_cheque, cobrado):
    """Alterna el estado de cobro de un cheque (casilla de la tabla).

    Un cheque cobrado deja de sumar en el total a pagar; por eso este toggle mueve
    el saldo de la cuenta y de la empresa. No guarda mas que el propio flag.
    """
    cheque = get_object_or_404(Cheque, id=id_cheque)
    cheque.cobrado = bool(cobrado)
    cheque.save(update_fields=["cobrado"])
    return cheque


def obtener_datos_cheque(id_cheque):
    """Datos de un cheque para precargar el panel de edicion y el modal de detalle,
    o None. Incluye los campos crudos (para el form) y algunos ya formateados para
    mostrar (banco, cuenta, fechas, vencimiento) sin recalcular en el cliente."""
    try:
        cheque = Cheque.objects.select_related("cuenta_corriente__banco").get(id=id_cheque)
    except Cheque.DoesNotExist:
        return None
    return {
        "id": cheque.id,
        "id_cuenta_corriente": cheque.cuenta_corriente_id,
        "id_banco": cheque.cuenta_corriente.banco_id,
        "numero": cheque.numero,
        "fecha_emision": cheque.fecha_emision.strftime("%Y-%m-%d"),
        "fecha_cobro": cheque.fecha_cobro.strftime("%Y-%m-%d"),
        "concepto": cheque.concepto,
        "importe": str(cheque.importe),
        "cobrado": cheque.cobrado,
        # Formateados para el modal de detalle (no vuelven al form)
        "banco_nombre": cheque.cuenta_corriente.banco.nombre,
        "cuenta_numero": cheque.cuenta_corriente.numero,
        "fecha_emision_txt": cheque.fecha_emision.strftime("%d/%m/%Y"),
        "fecha_cobro_txt": cheque.fecha_cobro.strftime("%d/%m/%Y"),
        "vencimiento_txt": cheque.vencimiento.strftime("%d/%m/%Y"),
        "vencido": cheque.vencido,
        "importe_txt": floatformat(cheque.importe, "2g"),
    }


# --- LISTADO Y TOTALES -------------------------------------------------------

def obtener_empresas_con_cheques(anio=None, mes=None):
    """Empresas activas con su total a pagar en cheques anotado, alfabeticamente.

    El total se acota al periodo (anio/mes) por la fecha de cobro de cada cheque,
    que es con la que el listado agrupa mes a mes. Sin periodo suma todos los
    pendientes.
    """
    empresas = Empresa.objects.filter(activa=True).con_totales_cheques(anio, mes)
    return empresas.order_by("nombre", "id")


def obtener_empresas_para_selector_cheques():
    """Items para la pildora de empresa del listado de cheques: todas las activas.

    Forma que espera selector_entidad (id, principal, busqueda). La lista es fija
    (no depende del periodo): la pildora deja elegir cualquier empresa activa.
    """
    return [
        {"id": e.id, "principal": e.nombre, "busqueda": e.nombre.lower()}
        for e in Empresa.objects.filter(activa=True).order_by("nombre", "id")
    ]


def obtener_totales_cheques(anio=None, mes=None):
    """Total a pagar en cheques de TODAS las empresas activas juntas, en el periodo.

    Suma sobre los cheques pendientes de cuentas corrientes activas de empresas
    activas cuya fecha de cobro cae en el periodo (anio/mes). Sin periodo suma
    todos los pendientes.
    """
    qs = Cheque.objects.filter(cuenta_corriente__empresa__activa=True,
                               cuenta_corriente__activa=True, cobrado=False)
    if anio:
        qs = qs.filter(fecha_cobro__year=anio)
    if mes:
        qs = qs.filter(fecha_cobro__month=mes)
    a_pagar = (qs.aggregate(t=Sum("importe"))["t"] or Decimal("0")).quantize(Decimal("0.01"))

    return {"a_pagar": a_pagar}
