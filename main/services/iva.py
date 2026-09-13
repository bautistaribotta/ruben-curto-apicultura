# IVA: empresas y sus operaciones de debito y credito fiscal.

from decimal import Decimal

from django.shortcuts import get_object_or_404

from main.models import Empresa, OperacionIva, _expresion_iva

from .comunes import (_decimal_opcional, _fecha_obligatoria, _guardar_unico, _texto_opcional,
                      filtro_tokens)


# ===========================================================================
# IVA: empresas / sociedades y sus operaciones
#
# Cada empresa deriva su IVA debito (ventas) y credito (compras) de sus
# operaciones, sin guardar totales. El listado se pinta con tarjetas, asi que
# obtener_empresas_activas anota los dos totales con con_totales_iva para no
# disparar una query por tarjeta. El CRUD sigue el mismo patron que estaciones:
# baja logica de la empresa (preserva las operaciones) y borrado real de una
# operacion cargada mal.
# ===========================================================================

# Tope del monto neto: 15 digitos con 2 decimales en la base
MAX_MONTO_IVA = Decimal("9999999999999.99")


def obtener_empresas_activas(q=None):
    """Empresas activas con su IVA debito y credito anotados, alfabeticamente.

    Filtra por nombre cuando llega un texto de busqueda (cada palabra tiene que
    aparecer, ver filtro_tokens).
    """
    empresas = Empresa.objects.filter(activa=True).con_totales_iva()
    if q:
        empresas = empresas.filter(filtro_tokens(q, "nombre"))
    return empresas.order_by("nombre", "id")


def obtener_totales_iva(anio, mes=None):
    """IVA debito, credito y saldo de TODAS las empresas activas juntas.

    Totaliza el anio entero o, si llega 'mes' (1-12), solo ese mes. El debito sale
    de las ventas y el credito de las compras; ambos son la suma de la base
    imponible por su alicuota (misma expresion que en las tarjetas). El estado del
    saldo sigue el mismo semaforo que la empresa: a pagar / a favor / al dia.
    """
    ops = OperacionIva.objects.filter(empresa__activa=True, fecha__year=anio)
    if mes:
        ops = ops.filter(fecha__month=mes)

    debito = (ops.filter(tipo="venta").aggregate(t=_expresion_iva())["t"]
              or Decimal("0")).quantize(Decimal("0.01"))
    credito = (ops.filter(tipo="compra").aggregate(t=_expresion_iva())["t"]
               or Decimal("0")).quantize(Decimal("0.01"))
    saldo = debito - credito

    if saldo > 0:
        estado = "a_pagar"
    elif saldo < 0:
        estado = "a_favor"
    else:
        estado = "al_dia"

    return {
        "debito": debito,
        "credito": credito,
        "saldo": saldo,
        "saldo_abs": abs(saldo),
        "estado": estado,
    }


def _validar_nombre_empresa(nombre, excluir_id=None):
    """Limpia y valida el nombre de una empresa. Devuelve el nombre normalizado.

    El nombre es lo unico propio de la empresa y no puede repetirse entre las
    activas (aviso antes de que la base tire IntegrityError). Admito puntos y
    simbolos porque las razones sociales los llevan (S.A., S.R.L., etc.).
    """
    nombre = (nombre or "").strip()
    if not (2 <= len(nombre) <= 60):
        raise ValueError("El nombre de la empresa debe tener entre 2 y 60 caracteres.")

    duplicada = (Empresa.objects
                 .filter(nombre__iexact=nombre, activa=True)
                 .exclude(id=excluir_id)
                 .exists())
    if duplicada:
        raise ValueError("Ya existe una empresa con ese nombre.")
    return nombre


def crear_empresa(nombre):
    nombre = _validar_nombre_empresa(nombre)
    return _guardar_unico(lambda: Empresa.objects.create(nombre=nombre),
                          "Ya existe una empresa con ese nombre.")


def editar_empresa(id_empresa, nombre):
    empresa = get_object_or_404(Empresa, id=id_empresa)
    empresa.nombre = _validar_nombre_empresa(nombre, excluir_id=empresa.id)
    _guardar_unico(empresa.save, "Ya existe una empresa con ese nombre.")
    return empresa


def eliminar_empresa(id_empresa):
    """Baja logica: saca la empresa del listado sin perder sus operaciones."""
    empresa = get_object_or_404(Empresa, id=id_empresa)
    empresa.activa = False
    empresa.save(update_fields=["activa"])
    return empresa


def obtener_datos_empresa(id_empresa):
    """Datos de una empresa para precargar el panel de edicion, o None."""
    try:
        empresa = Empresa.objects.get(id=id_empresa, activa=True)
    except Empresa.DoesNotExist:
        return None
    return {"id": empresa.id, "nombre": empresa.nombre}


# --- OPERACIONES DE IVA ------------------------------------------------------

def _validar_tipo_operacion(tipo):
    if tipo not in dict(OperacionIva.TIPOS):
        raise ValueError("Elegi si la operacion es una venta o una compra.")
    return tipo


def _validar_alicuota(valor):
    alicuota = _decimal_opcional(valor, "La alicuota")
    if alicuota is None:
        raise ValueError("Elegi una alicuota de IVA.")
    # Comparo numericamente contra las alicuotas validas (21, 10,5 y 27)
    if alicuota not in [a for a, _ in OperacionIva.ALICUOTAS]:
        raise ValueError("La alicuota de IVA no es valida.")
    return alicuota


def _validar_operacion_iva(tipo, fecha, monto_neto, alicuota, detalle):
    """Limpia y valida los datos de una operacion. Devuelve la tupla lista."""
    tipo = _validar_tipo_operacion(tipo)
    dia = _fecha_obligatoria(fecha, "La fecha de la operacion")
    monto = _decimal_opcional(monto_neto, "El monto neto", MAX_MONTO_IVA)
    if not monto:
        raise ValueError("El monto neto es obligatorio y tiene que ser mayor a cero.")
    alic = _validar_alicuota(alicuota)
    texto = _texto_opcional(detalle, 120, "El detalle")
    return tipo, dia, monto, alic, texto


def crear_operacion_iva(id_empresa, tipo=None, fecha=None, monto_neto=None, alicuota=None, detalle=None):
    """Registra una operacion de venta o compra de una empresa activa."""
    empresa = get_object_or_404(Empresa, id=id_empresa, activa=True)
    tipo, dia, monto, alic, texto = _validar_operacion_iva(tipo, fecha, monto_neto, alicuota, detalle)
    return OperacionIva.objects.create(
        empresa=empresa, tipo=tipo, fecha=dia, monto_neto=monto, alicuota=alic, detalle=texto,
    )


def editar_operacion_iva(id_operacion, tipo=None, fecha=None, monto_neto=None, alicuota=None, detalle=None):
    """Corrige una operacion ya cargada."""
    operacion = get_object_or_404(OperacionIva, id=id_operacion)
    tipo, dia, monto, alic, texto = _validar_operacion_iva(tipo, fecha, monto_neto, alicuota, detalle)
    operacion.tipo, operacion.fecha, operacion.monto_neto = tipo, dia, monto
    operacion.alicuota, operacion.detalle = alic, texto
    operacion.save()
    return operacion


def eliminar_operacion_iva(id_operacion):
    """Borra una operacion: lo unico que se borra es un registro cargado mal, y
    ahi el borrado real es lo correcto (no ensucia el saldo con bajas logicas)."""
    operacion = get_object_or_404(OperacionIva, id=id_operacion)
    operacion.delete()
    return operacion


def obtener_operaciones_iva(id_empresa, tipo="todas"):
    """Historial de operaciones de una empresa, de la mas nueva a la mas vieja.

    tipo filtra el listado: "ventas", "compras" o "todas" (por defecto).
    """
    operaciones = OperacionIva.objects.filter(empresa_id=id_empresa)
    if tipo == "ventas":
        operaciones = operaciones.filter(tipo="venta")
    elif tipo == "compras":
        operaciones = operaciones.filter(tipo="compra")
    return operaciones


def obtener_datos_operacion_iva(id_operacion):
    """Datos de una operacion para precargar el panel de edicion, o None."""
    try:
        operacion = OperacionIva.objects.get(id=id_operacion)
    except OperacionIva.DoesNotExist:
        return None
    return {
        "id": operacion.id,
        "tipo": operacion.tipo,
        "fecha": operacion.fecha.strftime("%Y-%m-%d"),
        "monto_neto": str(operacion.monto_neto),
        "alicuota": str(operacion.alicuota),
        "detalle": operacion.detalle or "",
    }
