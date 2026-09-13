# Listado de deudores con sus filtros y tarjetas de resumen.

from django.shortcuts import render
from django.contrib.admin.views.decorators import staff_member_required
from django.core.paginator import Paginator
from django.utils.dateparse import parse_date

from main.models import DetalleOperacion

from main.services.deudores import obtener_listado_deudores

from .comunes import _etiqueta_rango


@staff_member_required(login_url="inicio")
def deudores(request):
    import re
    from collections import defaultdict
    from decimal import Decimal

    # Filtro por cliente: en vez de un texto libre (propenso a errores de tipeo o a
    # confundir nombres parecidos) se elige un cliente desde el modal selector. Viaja
    # su id; cualquier valor no numerico se ignora y se muestran todos.
    cliente_id = request.GET.get("cliente", "")
    if not cliente_id.isdigit():
        cliente_id = ""

    # Filtro por producto: tambien via modal selector. El valor es un token que
    # distingue producto de catalogo ("p<id>") de articulo a granel ("g<id_cotizacion>"),
    # porque una linea de operacion apunta a uno u otro. Un token mal formado se ignora.
    producto_token = request.GET.get("producto", "")
    if not re.fullmatch(r"[pg]\d+", producto_token):
        producto_token = ""

    # Filtro por tipo de deuda: 'cobros' (ventas impagas) o 'pagos' (compras impagas).
    # Cualquier otro valor se ignora y se muestran todas.
    tipo = request.GET.get("tipo", "")
    if tipo not in ("cobros", "pagos"):
        tipo = ""

    # Filtro por rango de fechas de la operacion. Las fechas llegan en ISO
    # (yyyy-mm-dd) desde el <input type="date">; parse_date devuelve None si el
    # valor es invalido, asi que un parametro roto simplemente se ignora. El modo
    # "un solo dia" del popover manda desde == hasta.
    desde = parse_date(request.GET.get("desde", ""))
    hasta = parse_date(request.GET.get("hasta", ""))
    # Si el usuario invierte el rango, lo normalizo para no devolver un listado vacio.
    if desde and hasta and desde > hasta:
        desde, hasta = hasta, desde

    # Base de valuacion de las equivalencias en las tarjetas: 'hoy' (cotizacion
    # actual) u 'origen' (la cotizacion guardada al crear cada operacion). No afecta
    # a la tabla, que sigue mostrando ambas, ni al total en pesos, que es nominal.
    valuacion = request.GET.get("valuacion", "")
    if valuacion != "origen":
        valuacion = "hoy"

    # Modo de las tarjetas de resumen segun el filtro de tipo:
    #   - sin filtro (por defecto, tambien al elegir un cliente): "saldo", el neto
    #     entre lo que hay por cobrar (ventas impagas) y lo que hay por pagar (compras
    #     impagas). Positivo = a favor (nos deben); negativo = en contra (debemos).
    #   - filtro cobros: "cobrar", solo el total por cobrar.
    #   - filtro pagos:  "pagar", solo el total por pagar.
    if tipo == "cobros":
        modo = "cobrar"
    elif tipo == "pagos":
        modo = "pagar"
    else:
        modo = "saldo"

    # Traigo el listado completo bajo el filtro de tipo/fechas (sin acotar por cliente):
    # la tabla y las tarjetas usan la version filtrada por el cliente elegido, mientras
    # que el selector muestra todos los clientes con deuda para que elegir siempre de un
    # resultado. Una sola llamada evita golpear dos veces las cotizaciones.
    todas = obtener_listado_deudores("", tipo, desde, hasta)

    def _formato_pesos_ar(valor):
        # 1234567.5 -> "1.234.567,50" (miles con punto, decimales con coma)
        crudo = f"{abs(valor):,.2f}"
        return crudo.replace(",", "@").replace(".", ",").replace("@", ".")

    # Mapa operacion -> tokens de sus items, y las opciones del selector de producto.
    # Cada linea apunta a un producto de catalogo ("p<id>") o a un articulo a granel
    # ("g<id_cotizacion>"); ambos entran como opciones filtrables. Se arma sobre 'todas'
    # (solo tipo/fechas), independiente del cliente/producto elegidos, para que la lista
    # del modal siempre este poblada.
    tokens_por_operacion = defaultdict(set)
    opciones_producto = {}
    ids_operaciones = [d["id"] for d in todas]
    detalles = (
        DetalleOperacion.objects
        .filter(operacion_id__in=ids_operaciones)
        .select_related("producto", "cotizacion")
    )
    for det in detalles:
        if det.cotizacion_id:
            token = f"g{det.cotizacion_id}"
            nombre = f"{det.cotizacion.articulo} (por {det.cotizacion.abreviatura})"
        else:
            token = f"p{det.producto_id}"
            nombre = det.producto.nombre
        tokens_por_operacion[det.operacion_id].add(token)
        info = opciones_producto.get(token)
        if info is None:
            info = opciones_producto[token] = {"id": token, "principal": nombre, "operaciones": set()}
        info["operaciones"].add(det.operacion_id)

    productos_con_deuda = []
    for info in sorted(opciones_producto.values(), key=lambda i: i["principal"].lower()):
        cantidad = len(info["operaciones"])
        productos_con_deuda.append({
            "id": info["id"],
            "principal": info["principal"],
            "busqueda": info["principal"].lower(),
            "secundario": f"En {cantidad} deuda{'' if cantidad == 1 else 's'}",
            "tono": "neutro",
        })

    # Filtro de la tabla/tarjetas: cliente Y producto se combinan (AND) sobre el listado.
    lista_deudores = todas
    if cliente_id:
        lista_deudores = [d for d in lista_deudores if str(d["cliente_id"]) == cliente_id]
    if producto_token:
        lista_deudores = [
            d for d in lista_deudores if producto_token in tokens_por_operacion.get(d["id"], set())
        ]

    # Items del selector de cliente: un cliente por fila con su saldo agregado en el modo
    # vigente (neto en "saldo"; total a cobrar o a pagar en los otros). El saldo acompana
    # al nombre para decidir con el monto a la vista antes de filtrar.
    agrupado = {}
    for d in todas:
        cid = d["cliente_id"]
        fila = agrupado.get(cid)
        if fila is None:
            fila = agrupado[cid] = {
                "id": cid,
                "principal": d["cliente"],
                "busqueda": d["cliente"].lower(),
                "iniciales": d["iniciales"],
                "pesos": Decimal("0"),
            }
        signo = 1 if d["tipo_operacion"] == "venta" else -1
        # En "saldo" las ventas suman y las compras restan; en cobrar/pagar el listado ya
        # viene acotado a un solo tipo, asi que sumo el monto directo.
        fila["pesos"] += (signo if modo == "saldo" else 1) * (d["deuda_pesos"] or 0)

    clientes_con_deuda = []
    for fila in sorted(agrupado.values(), key=lambda f: f["principal"].lower()):
        pesos = fila["pesos"]
        if modo == "cobrar" or (modo == "saldo" and pesos > 0):
            tono, secundario = "cobrar", f"+ $ {_formato_pesos_ar(pesos)}"
        elif modo == "pagar" or (modo == "saldo" and pesos < 0):
            tono, secundario = "pagar", f"− $ {_formato_pesos_ar(pesos)}"
        else:
            tono, secundario = "neutro", f"$ {_formato_pesos_ar(pesos)}"
        clientes_con_deuda.append({
            "id": fila["id"],
            "principal": fila["principal"],
            "busqueda": fila["busqueda"],
            "iniciales": fila["iniciales"],
            "secundario": secundario,
            "tono": tono,
        })

    # Nombres elegidos para rehidratar los chips al cargar por URL directa.
    cliente_nombre = ""
    if cliente_id:
        elegido = next((c for c in clientes_con_deuda if str(c["id"]) == cliente_id), None)
        cliente_nombre = elegido["principal"] if elegido else ""
    producto_nombre = ""
    if producto_token:
        elegido = next((p for p in productos_con_deuda if p["id"] == producto_token), None)
        producto_nombre = elegido["principal"] if elegido else ""

    # Cada equivalencia suma la columna de la valuacion elegida. Una operacion sin
    # cotizacion de origen guardada cae a su valor actual: aporta lo mismo a ambos
    # totales en vez de desaparecer del total origen y desbalancear la comparacion.
    def _valor_equivalencia(fila, campo):
        if valuacion == "origen" and fila[f"{campo}_historico"] is not None:
            return fila[f"{campo}_historico"]
        return fila[f"{campo}_actual"] or 0

    def _total_pesos(filas):
        return sum((d["deuda_pesos"] or 0) for d in filas)

    def _total_equiv(filas, campo):
        return sum(_valor_equivalencia(d, campo) for d in filas)

    # Totales sobre el listado completo (no solo la pagina) para las tarjetas. En saldo
    # el neto se arma campo por campo: las ventas suman (nos deben) y las compras restan
    # (debemos); asi cada equivalencia queda con su propio signo.
    ventas = [d for d in lista_deudores if d["tipo_operacion"] == "venta"]
    compras = [d for d in lista_deudores if d["tipo_operacion"] == "compra"]

    if modo == "saldo":
        total_pesos = _total_pesos(ventas) - _total_pesos(compras)
        total_usd = _total_equiv(ventas, "deuda_dolar") - _total_equiv(compras, "deuda_dolar")
        total_miel = _total_equiv(ventas, "kg_miel") - _total_equiv(compras, "kg_miel")
        total_cera = _total_equiv(ventas, "kg_cera") - _total_equiv(compras, "kg_cera")
    else:
        filas_tarjetas = ventas if modo == "cobrar" else compras
        total_pesos = _total_pesos(filas_tarjetas)
        total_usd = _total_equiv(filas_tarjetas, "deuda_dolar")
        total_miel = _total_equiv(filas_tarjetas, "kg_miel")
        total_cera = _total_equiv(filas_tarjetas, "kg_cera")

    # Texto del chip de fechas (mismo helper que el resto de las vistas): mes entero
    # por su nombre, un solo dia, rango cerrado o abierto. Se calcula en el server
    # para que el chip ya se pinte correcto al cargar, sin depender del JS.
    fecha_label = _etiqueta_rango(desde, hasta)

    # Las deudas se ordenan siempre de la mas reciente a la mas antigua. El id
    # desempata las operaciones del mismo dia, dejando arriba la ultima cargada.
    lista_deudores.sort(key=lambda d: (d["fecha"], d["id"]), reverse=True)

    paginator_deudores = Paginator(lista_deudores, 8)
    pagina_numero = request.GET.get("page")
    pagina_obj = paginator_deudores.get_page(pagina_numero)

    contexto = {
        "deudores": pagina_obj,
        # Cliente elegido en el selector: id para armar los links de paginacion y el
        # nombre para pintar el chip; vacio si no hay filtro de cliente activo.
        "cliente": cliente_id,
        "cliente_nombre": cliente_nombre,
        "clientes_con_deuda": clientes_con_deuda,
        # Producto elegido en el selector: token para los links de paginacion y nombre
        # para el chip; vacio si no hay filtro de producto activo.
        "producto": producto_token,
        "producto_nombre": producto_nombre,
        "productos_con_deuda": productos_con_deuda,
        "tipo": tipo,
        # Fechas en ISO para rellenar los <input type="date"> y armar los links de
        # paginacion; vacio si no hay filtro activo.
        "desde": desde.isoformat() if desde else "",
        "hasta": hasta.isoformat() if hasta else "",
        "fecha_label": fecha_label,
        "modo": modo,
        "valuacion": valuacion,
        "total_pesos": total_pesos,
        "total_usd": total_usd,
        "total_miel": total_miel,
        "total_cera": total_cera,
        "total_deudores": len(lista_deudores),
    }

    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        # El AJAX refresca tanto las tarjetas (que cambian de a cobrar a pagar) como la tabla.
        return render(request, "deudores_ajax.html", contexto)
        
    return render(request, "deudores.html", contexto)
