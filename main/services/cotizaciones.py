"""
Cotizaciones: dolar oficial (API externa con cache), precios de miel y cera
y el tablero de resumen de la pantalla de inicio.
"""

from decimal import Decimal

import requests

from django.db.models import Sum, Count
from django.core.cache import cache

from main.models import Producto, ProductoPorKg


def get_cotizacion_dolar_oficial():
    cotizacion = cache.get("cotizacion_oficial")
    if cotizacion:
        return cotizacion

    url_dolar_oficial = "https://dolarapi.com/v1/dolares/oficial"

    # cache.add() es atómico (set-if-not-exists): solo un worker gana el lock y
    # consulta la API externa. El resto evita el cache stampede (varios workers
    # golpeando la API a la vez cuando expira la clave).
    if not cache.add("cotizacion_oficial_lock", "1", 10):
        # No gané el lock: devuelvo lo que haya en cache o un fallback neutro
        return cache.get("cotizacion_oficial") or {"compra": None, "venta": None}

    try:
        # timeout para no bloquear el worker si la API externa cuelga
        respuesta = requests.get(url_dolar_oficial, verify=True, timeout=5)
        respuesta.raise_for_status()
        datos = respuesta.json()
        resultado = {"compra": datos.get("compra"), "venta": datos.get("venta")}
        cache.set("cotizacion_oficial", resultado, 3600)  # Cache por 1 hora
        return resultado
    except requests.RequestException:
        return {"compra": None, "venta": None}
    finally:
        cache.delete("cotizacion_oficial_lock")


"""
Icono con el que cada categoria se dibuja en el tablero de inicio, y la etiqueta
de su tarjeta de resumen cuando el nombre de la categoria no es el que se venia
mostrando. Es lo unico del tablero que sigue viviendo en el codigo: que producto
aparece lo decide el flag mostrar_en_inicio de cada base, no una lista de aca.
"""
CATEGORIAS_INICIO = {
    "Miel": {"icono": "water_drop"},
    "Alimento": {"icono": "nutrition"},
    "Cera": {"icono": "hexagon"},
    "Madera": {"icono": "forest"},
    "Estampado": {"icono": "grid_on"},
    "Insumos": {"icono": "handyman"},
    "Medicamentos": {"icono": "medication"},
    "Tambores Vacios": {"icono": "oil_barrel", "etiqueta": "Tambores vacios"},
    "Otros": {"icono": "category"},
}


def _grupo_inicio(categoria):
    return {
        "categoria": categoria,
        "icono": CATEGORIAS_INICIO.get(categoria, {}).get("icono", "inventory_2"),
        "articulos": [],
        "kilos": Decimal("0"),
        "litros": Decimal("0"),
        "resumenes": [],
    }


def get_tablero_inicio():
    """
    Arma los grupos del tablero de inicio con los productos marcados con
    mostrar_en_inicio. Cada grupo es una categoria: adentro van las tarjetas de
    los articulos que se venden a granel (precio editable, stock disponible) y
    los kilos y los litros sumados de esos articulos, cada magnitud por su lado.

    Los productos que se venden por unidad no van tarjeta por tarjeta: se
    resumen en una sola por categoria, con el total de unidades y cuantos
    productos la componen. Esa tarjeta acompana al tablero de su categoria y, si
    esa categoria no tiene articulos por kilo, viaja con el primer grupo: es el
    caso de los tambores vacios, que siempre se mostraron junto a la miel.
    """
    orden = {categoria: i for i, (categoria, _) in enumerate(Producto.categorias)}
    por_categoria = {}
    grupos = []

    """
    Ordeno por id, o sea por orden de alta: es el orden en el que se vienen
    mostrando las tarjetas y no se reacomoda solo cuando cambia un precio.
    """
    for articulo in ProductoPorKg.objects.filter(activo=True, mostrar_en_inicio=True).order_by("id"):
        grupo = por_categoria.get(articulo.categoria)
        if grupo is None:
            grupo = _grupo_inicio(articulo.categoria)
            por_categoria[articulo.categoria] = grupo
            grupos.append(grupo)

        grupo["articulos"].append(articulo)
        if articulo.es_por_litro:
            grupo["litros"] += articulo.cantidad
        else:
            grupo["kilos"] += articulo.cantidad

    # Ordeno antes de repartir los resumenes: el que no tiene tablero propio se
    # cuelga del primer grupo, y "primero" tiene que ser el de siempre
    grupos.sort(key=lambda grupo: orden.get(grupo["categoria"], len(orden)))

    resumenes = (Producto.objects.filter(activo=True, mostrar_en_inicio=True)
                 .values("categoria")
                 .annotate(unidades=Sum("cantidad"), tipos=Count("id"))
                 .order_by())

    for fila in sorted(resumenes, key=lambda f: orden.get(f["categoria"], len(orden))):
        categoria = fila["categoria"]
        datos = CATEGORIAS_INICIO.get(categoria, {})

        grupo = por_categoria.get(categoria) or (grupos[0] if grupos else None)
        if grupo is None:
            grupo = _grupo_inicio(categoria)
            por_categoria[categoria] = grupo
            grupos.append(grupo)

        grupo["resumenes"].append({
            "titulo": datos.get("etiqueta", categoria),
            "icono": datos.get("icono", "inventory_2"),
            "unidades": fila["unidades"] or 0,
            "tipos": fila["tipos"],
        })

    return grupos


def actualizar_cotizacion(articulo, monto):
    """
    Actualiza o crea una cotización en la base de datos.
    """
    cotizacion, created = ProductoPorKg.objects.update_or_create(
        articulo=articulo,
        defaults={"monto": monto}
    )
    return cotizacion


def get_cotizacion_miel_50mm():
    """
    Obtiene la cotización de la miel. Se toma 'Miel menor a 50 mm' como referencia por defecto.
    """
    try:
        miel = ProductoPorKg.objects.get(articulo="Miel menor a 50 mm")
        return miel.monto
    except ProductoPorKg.DoesNotExist:
        return 1.00


def get_cotizacion_cera_operculo():
    """
    Obtiene la cotización de la cera. Se toma 'Cera Operculo' como referencia.
    Devuelve None si no existe para que quien la use muestre un guion en vez
    de calcular una equivalencia sin sentido.
    """
    try:
        cera = ProductoPorKg.objects.get(articulo="Cera Operculo")
        return cera.monto
    except ProductoPorKg.DoesNotExist:
        return None
