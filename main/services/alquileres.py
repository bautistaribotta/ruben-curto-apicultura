# Alquileres: casas, contratos, pagos mensuales, gastos y perfil de una casa.

from decimal import Decimal

from django.utils import timezone
from django.shortcuts import get_object_or_404
from django.http import Http404
from django.db import transaction
from django.db.models import Value, Q, OuterRef, Exists, Case, When, IntegerField

from main.models import (Casa, Contrato, PagoAlquiler, GastoCasa, contratos_del_periodo,
                         periodo_actual)

from .comunes import (_acotar_rango, _decimal_opcional, _entero_opcional, _fecha_obligatoria,
                      _parsear_periodo, _texto_opcional, mes_desplazado)


# ==========================================================================
#  ALQUILERES
# ==========================================================================

def _validar_casa(nombre, localidad, direccion):
    """Limpia y valida los datos de una casa. Devuelve la tupla ya normalizada.

    Son tres campos porque la casa ya no guarda nada del alquiler: el plazo, el
    monto, la comision y el inquilino son del contrato.
    """
    return (_texto_opcional(nombre, 60, "El nombre de la casa"),
            _texto_opcional(localidad, 60, "La localidad"),
            _texto_opcional(direccion, 120, "La dirección"))


# Condiciones que reproducen en SQL lo que Casa.estado_mes calcula en Python.
# Existen para poder filtrar y ordenar el listado por el estado del mes sin
# traer todas las casas a memoria.
#
# Como el alquiler se cobra completo, el estado no compara montos: mira si el
# mes tiene pago o no. Por eso alcanza con el signo de lo cobrado y el precio
# de la casa no entra en la cuenta.
#
# El orden de las condiciones copia el de Casa.estado_mes y no es casual: el
# pago se pregunta primero y le gana al contrato, porque es un hecho de ese mes.
# Si las dos versiones se separan, el chip deja de coincidir con la pildora.
#
# Cuelgan de las anotaciones de con_estado_del_mes y no de campos de la casa:
# son las unicas que saben de que mes estamos hablando. Estar alquilada es tener
# contrato que cubra ese mes, asi que un contrato vencido ya cuenta como libre
# sin necesidad de una condicion aparte.
Q_COBRADA = Q(_pagado_periodo_anotado__gt=0)
Q_PENDIENTE = Q(_contrato_periodo_anotado__isnull=False) & Q(_pagado_periodo_anotado__lte=0)
Q_LIBRE = Q(_contrato_periodo_anotado__isnull=True) & Q(_pagado_periodo_anotado__lte=0)

# Filtros del listado. La clave viaja en la URL y la etiqueta la pinta el chip.
FILTROS_ALQUILERES = {
    "pendientes": Q_PENDIENTE,
    "cobradas": Q_COBRADA,
    "libres": Q_LIBRE,
}


def obtener_casas(estado="", periodo=None):
    """Listado de casas vigentes, ya anotado con lo cobrado en el periodo pedido.

    La anotacion viene de arranque porque el listado pinta el estado de cada
    fila: sin ella serian tantas queries como casas haya.

    El orden por defecto no es alfabetico sino por urgencia (pendientes de cobro,
    cobradas y al final las que no estan alquiladas). La pantalla existe para
    responder que falta cobrar este mes, asi que eso va arriba sin que el usuario
    tenga que filtrar; dentro de cada grupo si ordena por nombre.

    Que casas entran en un mes:

    - Las que tienen pago cargado en ese mes, siempre. Un pago es un hecho, asi
      que la casa aparece aunque hoy este dada de baja: si no, la plata cobrada
      desaparecia del total del mes.
    - En el mes en curso y en los que vienen, todas las vigentes. Aunque no tengan
      contrato: es justamente la pantalla donde hay que poder cargarles uno.
    - En los meses pasados, solo las que ya tenian algun contrato empezado. Sin
      esto, una casa cargada hoy reaparece en todos los meses anteriores.

    El vencimiento no saca a la casa del listado, a proposito: sigue existiendo y
    hay que poder verla para renovarla. Lo que cambia es que pasa a "Sin alquilar"
    y deja de sumar a lo pendiente.
    """
    periodo = periodo or periodo_actual()

    vigentes = Q(activa=True)
    if periodo < periodo_actual():
        # Ya tenia contrato si alguno arranco en ese mes o antes; comparo contra el
        # primero del mes siguiente para no perder los que arrancan en el propio mes.
        vigentes &= Q(Exists(
            Contrato.objects.filter(casa=OuterRef("pk"), inicio__lt=mes_desplazado(periodo, 1))
        ))

    casas = Casa.objects.con_estado_del_mes(periodo).filter(Q_COBRADA | vigentes)

    filtro = FILTROS_ALQUILERES.get(estado)
    if filtro is not None:
        casas = casas.filter(filtro)

    return casas.annotate(
        _orden_estado=Case(
            When(Q_PENDIENTE, then=Value(0)),
            When(Q_COBRADA, then=Value(1)),
            default=Value(2),
            output_field=IntegerField(),
        )
    ).order_by("_orden_estado", "nombre", "id")


def obtener_casa(id_casa):
    """Casa vigente con su pago del mes ya anotado, para el perfil."""
    casa = Casa.objects.filter(activa=True).con_estado_del_mes().filter(id=id_casa).first()
    if casa is None:
        raise Http404("La casa no existe o fue dada de baja.")
    return casa


def obtener_datos_casa(id_casa):
    """Datos de la casa en dict, para rellenar el panel de edicion via JSON."""
    try:
        casa = Casa.objects.get(id=id_casa, activa=True)
        return {
            "id": casa.id,
            "nombre": casa.nombre or "",
            "localidad": casa.localidad or "",
            "direccion": casa.direccion or "",
        }
    except Casa.DoesNotExist:
        return None


def crear_casa(nombre=None, localidad=None, direccion=None):
    nombre, localidad, direccion = _validar_casa(nombre, localidad, direccion)
    return Casa.objects.create(nombre=nombre, localidad=localidad, direccion=direccion)


def editar_casa(id_casa, nombre=None, localidad=None, direccion=None):
    casa = get_object_or_404(Casa, id=id_casa)
    casa.nombre, casa.localidad, casa.direccion = _validar_casa(nombre, localidad, direccion)
    casa.save()
    return casa


def eliminar_casa(id_casa):
    # Baja logica, como en el resto del sistema: la casa desaparece de los
    # listados pero conserva su historial de pagos por si hay que consultarlo
    casa = get_object_or_404(Casa, id=id_casa)
    casa.activa = False
    casa.save()
    return casa


# ==========================================================================
#  CONTRATOS
# ==========================================================================

def _validar_contrato(inicio, fin, monto_mensual, comision_inmobiliaria, nombre_inquilino):
    """Limpia y valida los datos de un contrato. Devuelve la tupla normalizada.

    A diferencia de la casa, aca casi txdo es obligatorio: un contrato sin plazo
    ni monto no dice nada, y de esas tres fechas y ese numero cuelga el estado de
    la casa mes a mes. Lo unico opcional es el inquilino, que es un dato de
    agenda, y la comision, que no siempre hay inmobiliaria.
    """
    inicio = _fecha_obligatoria(inicio, "La fecha de inicio del contrato")
    fin = _fecha_obligatoria(fin, "La fecha de fin del contrato")
    if fin < inicio:
        raise ValueError("El fin del contrato no puede ser anterior a su inicio.")

    # Entero y sin centavos, como se pacta un alquiler. El tope lo pone el
    # PositiveIntegerField de la columna, que en MySQL llega hasta 4294967295
    monto = _entero_opcional(monto_mensual, "El alquiler mensual", 999999999)
    if not monto:
        raise ValueError("El alquiler mensual es obligatorio y tiene que ser mayor a cero.")

    # La comision es un porcentaje del alquiler, no un monto: mas de 100 no existe
    comision = _entero_opcional(comision_inmobiliaria, "La comisión de la inmobiliaria", 100)
    return inicio, fin, monto, comision, _texto_opcional(nombre_inquilino, 60, "El nombre del inquilino")


def _validar_plazo_libre(casa, inicio, fin, excluir_id=None):
    """Corta si el plazo pisa a otro contrato de la misma casa.

    Una casa no puede estar alquilada dos veces al mismo tiempo, y si lo estuviera
    no habria forma de decidir con que monto se cobra el mes. MySQL no tiene
    constraint de exclusion para rangos, asi que el corte vive aca.

    Dos plazos se pisan si cada uno empieza antes de que termine el otro. El fin
    vacio es un contrato sin vencimiento: se pisa con txdo lo que venga despues.
    """
    otros = casa.contratos.filter(Q(fin__isnull=True) | Q(fin__gte=inicio), inicio__lte=fin)
    if excluir_id:
        otros = otros.exclude(id=excluir_id)

    choque = otros.order_by("inicio").first()
    if choque is None:
        return

    hasta = choque.fin.strftime("%d/%m/%Y") if choque.fin else "sin vencimiento"
    raise ValueError(
        f"Esas fechas se pisan con el contrato del {choque.inicio:%d/%m/%Y} al {hasta}. "
        "Una casa no puede tener dos contratos a la vez."
    )


def crear_contrato(id_casa, inicio=None, fin=None, monto_mensual=None,
                   comision_inmobiliaria=None, nombre_inquilino=None):
    """Nuevo contrato de una casa. Renovar es esto: el anterior no se toca."""
    inicio, fin, monto, comision, inquilino = _validar_contrato(
        inicio, fin, monto_mensual, comision_inmobiliaria, nombre_inquilino
    )

    with transaction.atomic():
        # Bloqueo la fila de la casa para serializar el alta de contratos: chequear el
        # solapamiento (_validar_plazo_libre) y crear el contrato es un check-then-act,
        # y MySQL no tiene constraint de exclusion para rangos. Sin el lock, dos altas
        # concurrentes de la misma casa leen los mismos contratos, pasan las dos la
        # validacion y crean dos plazos que se pisan. Mismo criterio que marcar_pago_alquiler.
        casa = get_object_or_404(
            Casa.objects.select_for_update(), id=id_casa, activa=True
        )
        _validar_plazo_libre(casa, inicio, fin)

        return Contrato.objects.create(casa=casa, inicio=inicio, fin=fin, monto_mensual=monto,
                                       comision_inmobiliaria=comision, nombre_inquilino=inquilino)


def editar_contrato(id_contrato, inicio=None, fin=None, monto_mensual=None,
                    comision_inmobiliaria=None, nombre_inquilino=None):
    """Corrige un contrato ya cargado. Es para arreglar lo que se tipeo mal.

    Renovar no pasa por aca: eso es un contrato nuevo. Si se corre el plazo de uno
    viejo, los meses que dejan de estar cubiertos pasan a figurar sin alquilar, que
    es lo correcto, pero los pagos que tuvieran cargados no se borran.

    Hoy ningun boton de la pantalla lo dispara: el de la fila solo carga contratos
    nuevos y se bloquea mientras haya uno vigente. Se llega por la accion
    'editar_contrato' del POST o por el admin.
    """
    inicio, fin, monto, comision, inquilino = _validar_contrato(
        inicio, fin, monto_mensual, comision_inmobiliaria, nombre_inquilino
    )

    with transaction.atomic():
        contrato = get_object_or_404(Contrato, id=id_contrato)
        # Bloqueo la casa (no el contrato) para serializar contra crear_contrato y
        # contra otras ediciones de la misma casa: el chequeo de solapamiento mira
        # todos sus contratos, asi que la exclusion mutua tiene que vivir a nivel casa.
        # Sin el lock, un alta y una edicion concurrentes se cruzan y dejan plazos pisados.
        casa = get_object_or_404(Casa.objects.select_for_update(), id=contrato.casa_id)
        _validar_plazo_libre(casa, inicio, fin, excluir_id=contrato.id)

        contrato.inicio, contrato.fin = inicio, fin
        contrato.monto_mensual, contrato.comision_inmobiliaria = monto, comision
        contrato.nombre_inquilino = inquilino
        contrato.save()
    return contrato


def eliminar_contrato(id_contrato):
    """Borra un contrato. Es para el que se cargo mal, no para el que se termino.

    Un contrato terminado no se borra: vence solo el dia que pasa su fin y queda
    en el historial, que es justamente para lo que existe la tabla. Por eso el
    borrado es de verdad y no logico: lo unico que llega hasta aca es un registro
    equivocado, y guardarlo solo ensuciaria la cadena.

    Los pagos cuelgan de la casa y no del contrato, asi que no se van con el. Los
    meses que cubria pasan a figurar sin alquilar, pero los que tenian cobro
    cargado lo conservan y siguen sumando al total de su mes.
    """
    contrato = get_object_or_404(Contrato, id=id_contrato)
    id_casa = contrato.casa_id
    contrato.delete()
    return id_casa


def _contrato_en_dict(contrato):
    if contrato is None:
        return None
    return {
        "id": contrato.id,
        "inicio": contrato.inicio.isoformat(),
        # Vacio y no null: lo lee un input date, que espera un string
        "fin": contrato.fin.isoformat() if contrato.fin else "",
        # Monto pelado, sin separadores, para que el input lo acepte tal cual
        "monto_mensual": str(contrato.monto_mensual),
        "comision_inmobiliaria": (
            str(contrato.comision_inmobiliaria) if contrato.comision_inmobiliaria is not None else ""
        ),
        "nombre_inquilino": contrato.nombre_inquilino or "",
        "vencido": contrato.vencido,
        "meses": contrato.meses,
    }


def obtener_contrato_de_casa(id_casa):
    """Lo que el modal necesita saber de una casa antes de abrirse.

    Manda dos contratos y no uno:

    - 'vigente' es el contrato que cubre hoy. Si existe, el modal ni se abre: no
      hay contrato nuevo que cargar y el que se cargara se solaparia. El boton de
      la fila ya viene bloqueado, pero la tabla se refresca por AJAX y puede estar
      vieja, asi que el dato viaja igual como ultimo control.
    - 'anterior' es el ultimo que ya termino. Con el se precarga el formulario,
      que es lo que pasa al renovar: mismo inquilino, plazo nuevo, monto que casi
      siempre se retoca.
    """
    casa = get_object_or_404(Casa, id=id_casa, activa=True)
    hoy = timezone.localdate()

    vigente = casa.contratos.filter(Q(fin__isnull=True) | Q(fin__gte=hoy), inicio__lte=hoy).first()
    anterior = casa.contratos.filter(fin__lt=hoy).order_by("-fin", "-id").first()

    return {
        "casa": {"id": casa.id, "nombre": casa.nombre or "Sin nombre"},
        "vigente": _contrato_en_dict(vigente),
        "anterior": _contrato_en_dict(anterior),
    }


def marcar_pago_alquiler(id_casa, periodo, pagado):
    """Casilla de cobro de la tabla: crea o borra el pago del mes de una tirada.

    Es la unica via de carga de la pantalla, y alcanza porque el alquiler no
    tiene medias tintas: se cobra entero, por el monto del contrato que cubria ese
    mes, en el mes que se esta mirando. La fecha del cobro es la de hoy.

    Es idempotente: marcar lo ya marcado, o desmarcar lo que no esta cargado, no
    hace nada y tampoco es un error. Dos clicks seguidos o dos pestañas abiertas
    no tienen por que romper nada.

    Devuelve el estado que quedo y el monto involucrado. Desmarcar borra un
    registro de verdad, asi que la vista necesita poder decir cuanto era: si el
    precio cambio desde que se cargo, el usuario tiene que enterarse de lo que
    acaba de perder.
    """
    periodo = _parsear_periodo(periodo)

    with transaction.atomic():
        # Bloqueo la fila de la casa con select_for_update para serializar todas las
        # marcas/desmarcas de esa casa. Sin esto, dos "marcar" concurrentes del mismo
        # mes leian ambos pago=None y ambos hacian INSERT: el segundo chocaba contra
        # el UniqueConstraint(casa, periodo) y salia como IntegrityError (500), en vez
        # del retorno idempotente que promete la casilla. Con el lock, el segundo espera
        # y al desbloquearse ya ve el pago creado por el primero.
        casa = get_object_or_404(
            Casa.objects.select_for_update(), id=id_casa, activa=True
        )
        pago = PagoAlquiler.objects.filter(casa=casa, periodo=periodo).first()

        if not pagado:
            if pago is None:
                return {"pagado": False, "monto": None, "periodo": periodo}
            monto = pago.monto
            pago.delete()
            return {"pagado": False, "monto": monto, "periodo": periodo}

        if pago is not None:
            return {"pagado": True, "monto": pago.monto, "periodo": periodo}

        # La casilla no puede inventar un monto: sin contrato no hay pago que crear
        contrato = contratos_del_periodo(periodo).filter(casa=casa).first()
        if contrato is None:
            anterior = casa.contratos.filter(fin__lt=periodo).order_by("-fin").first()
            if anterior is not None:
                raise ValueError(
                    f"El contrato venció el {anterior.fin:%d/%m/%Y}, así que ese mes no corresponde "
                    "cobrarlo. Cargá el contrato nuevo para poder seguir."
                )
            raise ValueError(
                "La casa no tiene contrato en ese mes, así que no se sabe por cuánto es el pago. "
                "Cargale un contrato desde el botón de la fila."
            )

        PagoAlquiler.objects.create(
            casa=casa,
            periodo=periodo,
            monto=contrato.monto_mensual,
            fecha=timezone.localdate(),
        )
        return {"pagado": True, "monto": contrato.monto_mensual, "periodo": periodo}


def obtener_resumen_alquileres(casas, periodo=None):
    """Totales del periodo para la cabecera.

    Recibe siempre el listado completo, no el filtrado: la cabecera mide el mes
    entero. Si se moviera con los filtros, ver solo las cobradas la dejaria en
    cero pendiente y dejaria de decir la verdad.
    """
    periodo = periodo or periodo_actual()
    total_casas = 0
    alquiladas = 0
    esperado = Decimal("0")
    cobrado = Decimal("0")
    pendientes = 0
    monto_pendiente = Decimal("0")

    for casa in casas:
        total_casas += 1
        # "Alquilada" es tener contrato que cubra ese mes, asi que el vencido ya
        # queda afuera: la misma regla que aplica Casa.estado_mes.
        if casa.alquilada:
            alquiladas += 1

        pagado = casa.total_pagado_periodo
        if pagado > 0:
            # Lo cobrado se suma antes de mirar "alquilada": un pago cargado es
            # plata que entro ese mes, este la casa alquilada hoy o no. Antes se
            # salteaba el continue y la plata de una casa desocupada despues
            # desaparecia del total del mes.
            #
            # Y para ese mes lo esperado fue exactamente lo que se cobro, no el
            # precio de hoy: asi esperado sigue siendo cobrado mas pendiente.
            cobrado += pagado
            esperado += pagado
            continue

        # Sin pago, solo se reclama a las que tenian contrato ese mes
        if not casa.alquilada:
            continue

        # Sin parciales, lo que falta cobrar de una casa es su alquiler entero
        precio = casa.precio or Decimal("0")
        esperado += precio
        pendientes += 1
        monto_pendiente += precio

    return {
        "periodo": periodo,
        "total_casas": total_casas,
        "alquiladas": alquiladas,
        "sin_alquilar": total_casas - alquiladas,
        "esperado": esperado,
        "cobrado": cobrado,
        "pendientes": pendientes,
        "monto_pendiente": monto_pendiente,
    }


# ==========================================================================
#  GASTOS DE UNA CASA
# ==========================================================================

# Las categorias vienen del modelo para no tener dos listas que se separen: el
# formulario dibuja estas mismas opciones y la validacion corta contra ellas.
CATEGORIAS_GASTO_CASA = [clave for clave, _ in GastoCasa.CATEGORIAS]


def _validar_gasto_casa(categoria, fecha, monto, detalle):
    """Limpia y valida un gasto. Devuelve la tupla ya normalizada.

    Los tres primeros son obligatorios: un gasto sin monto no es un gasto, y sin
    fecha ni categoria no hay forma de ordenarlo ni de saber de que es. El
    detalle si es opcional, porque la categoria ya ubica el gasto.
    """
    categoria = _texto_opcional(categoria, 30, "La categoría del gasto")
    if categoria not in CATEGORIAS_GASTO_CASA:
        raise ValueError("Elegí una categoría de la lista.")

    fecha = _fecha_obligatoria(fecha, "La fecha del gasto")

    # Tope por DecimalField(max_digits=12, decimal_places=2): 10 enteros
    monto = _decimal_opcional(monto, "El monto del gasto", Decimal("9999999999.99"))
    if not monto:
        raise ValueError("El monto del gasto es obligatorio y tiene que ser mayor a cero.")

    return categoria, fecha, monto, _texto_opcional(detalle, 120, "El detalle del gasto")


def crear_gasto_casa(id_casa, categoria=None, fecha=None, monto=None, detalle=None):
    casa = get_object_or_404(Casa, id=id_casa, activa=True)
    categoria, fecha, monto, detalle = _validar_gasto_casa(categoria, fecha, monto, detalle)
    return GastoCasa.objects.create(casa=casa, categoria=categoria, fecha=fecha,
                                    monto=monto, detalle=detalle)


def editar_gasto_casa(id_gasto, categoria=None, fecha=None, monto=None, detalle=None):
    gasto = get_object_or_404(GastoCasa, id=id_gasto)
    gasto.categoria, gasto.fecha, gasto.monto, gasto.detalle = _validar_gasto_casa(
        categoria, fecha, monto, detalle
    )
    gasto.save()
    return gasto


def eliminar_gasto_casa(id_gasto):
    """Borrado de verdad y no logico: un gasto mal cargado no es historia.

    A diferencia de la casa, el gasto no tiene nada colgando que se pierda al
    borrarlo, asi que no hace falta la baja logica que usa el resto del sistema.
    """
    gasto = get_object_or_404(GastoCasa, id=id_gasto)
    id_casa = gasto.casa_id
    gasto.delete()
    return id_casa


# ==========================================================================
#  PERFIL DE UNA CASA
# ==========================================================================

def obtener_detalle_alquiler(id_casa, desde=None, hasta=None):
    """Todo lo que necesita el perfil de una casa, en una sola pasada.

    El desde y el hasta son solo para los gastos: el contrato y el historial no
    dependen de ningun periodo, muestran siempre lo que hay.

    Reparte los contratos en dos: el que corre hoy, que se muestra entero, y el
    resto, que va al historial. En el resto entran los que ya vencieron y
    tambien los que todavia no arrancaron, que existen porque nada impide dejar
    cargada la renovacion antes de tiempo.

    El vigente se busca en la lista ya traida y no con otra query: son un puñado
    de contratos por casa y el historial los necesita igual.
    """
    casa = obtener_casa(id_casa)
    hoy = timezone.localdate()

    # El orden del modelo es del mas nuevo al mas viejo, que es como los quiere
    # el historial
    contratos = list(casa.contratos.all())
    vigente = next(
        (c for c in contratos
         if c.inicio <= hoy and (c.fin is None or c.fin >= hoy)),
        None,
    )

    # Los gastos no dependen del contrato ni se renuevan con el mes: son de la
    # casa y quedan guardados para siempre. Sin filtro se muestran todos, y el
    # filtro solo recorta lo que se ve, nunca borra nada.
    #
    # Va como queryset y no como lista porque la vista lo pagina: asi la pagina
    # que se pide se trae con un LIMIT y no se levantan de la base todos los
    # gastos de la casa para mostrar cinco.
    gastos = _acotar_rango(casa.gastos.all(), "fecha", desde, hasta,
                           es_fecha_hora=False)

    return {
        "casa": casa,
        "contrato": vigente,
        "historial": [c for c in contratos if c is not vigente],
        "gastos": gastos,
        "categorias_gasto": CATEGORIAS_GASTO_CASA,
        # Para poder decir "no hay gastos en ese periodo" en vez de "no hay
        # gastos", que con un filtro puesto seria mentira
        "gastos_filtrados": bool(desde or hasta),
    }
