# Productos envasados y productos a granel (por kilo o por litro): alta, edicion, baja y stock.

from decimal import Decimal, InvalidOperation

from django.shortcuts import get_object_or_404
from django.http import Http404
from django.db.models import F

from main.models import Producto, ProductoPorKg

from .comunes import REGEX_TEXTO_NUMEROS


def nuevo_producto(nombre, categoria=None, precio=None, cantidad=None):
    nuevo_producto = Producto.objects.create(
        nombre=nombre, categoria=categoria, precio=precio, cantidad=cantidad
    )
    return nuevo_producto


def obtener_datos_producto(id_producto):
    try:
        # Busco el producto asegurándome de que esté activo en el inventario
        producto = Producto.objects.get(id=id_producto, activo=True)

        # Estructuro la información en un diccionario limpio para que la API JSON lo consuma fácilmente
        return {
            "id": producto.id,
            "nombre": producto.nombre,
            "categoria": producto.categoria,
            "precio": str(
                producto.precio
            ),  # Convierto el Decimal a string para evitar errores de serialización JSON
            "cantidad": str(producto.cantidad),
        }
    except Producto.DoesNotExist:
        # Si el producto no existe o está inactivo, devuelvo None
        return None


def modificar_stock(id_producto, cantidad, permitir_inactivos=False):
    """
    Modifica el stock de un producto sumando o restando según el valor de 'cantidad'.
    - cantidad > 0 → suma stock (ingreso de mercadería, devolución, etc.)
    - cantidad < 0 → resta stock (venta, egreso, etc.)

    Con permitir_inactivos=True también opera sobre productos dados de baja
    (activo=False): lo usan las reversiones de stock al cancelar o editar una
    operación, porque el historial puede referenciar productos ya eliminados.

    Retorna el producto actualizado o lanza ValueError si el stock quedaría negativo.
    """
    filtro_base = {"id": id_producto}
    if not permitir_inactivos:
        filtro_base["activo"] = True

    # Verifico existencia para mantener el comportamiento 404 ante productos
    # inexistentes o inactivos
    if not Producto.objects.filter(**filtro_base).exists():
        raise Http404("Producto no encontrado")

    if cantidad < 0:
        # UPDATE condicional atómico: el chequeo de stock (WHERE cantidad__gte)
        # y el descuento (SET cantidad = cantidad + n) ocurren en UNA sola
        # sentencia SQL. No hay ventana entre verificar y escribir, por lo que
        # se elimina el read-modify-write que permitía lost updates y sobreventa.
        filas = Producto.objects.filter(
            **filtro_base, cantidad__gte=abs(cantidad)
        ).update(cantidad=F("cantidad") + cantidad)

        if filas == 0:
            # 0 filas afectadas significa que no había stock suficiente
            raise ValueError("No se puede quitar más stock del existente.")
    else:
        # Ingreso de stock: incremento atómico sin lectura previa
        Producto.objects.filter(**filtro_base).update(
            cantidad=F("cantidad") + cantidad
        )

    return Producto.objects.get(id=id_producto)


def editar_producto(id_producto, nombre, categoria, precio, activo):
    # El stock NO se modifica al editar: se gestiona solo en el alta y con el modal
    # de agregar/quitar (UPDATE atomico). Asi evito el lost update de pisar 'cantidad'
    # con un valor del form leido al abrir la pantalla, descartando una venta o compra
    # concurrente que haya movido el stock entremedio.
    producto = get_object_or_404(Producto, id=id_producto)

    producto.nombre = nombre
    producto.categoria = categoria
    producto.precio = precio
    producto.activo = activo

    producto.save()
    return producto


def eliminar_producto(id_producto):
    producto = get_object_or_404(Producto, id=id_producto)

    # En lugar de borrarlo de la base de datos, lo marco como inactivo
    # para no perder el historial de ventas en las otras tablas
    producto.activo = False
    producto.save()
    return producto


# --- PRODUCTOS A GRANEL (POR KILO O POR LITRO) ---
"""
Mismo ciclo de vida que un producto envasado, pero sobre ProductoPorKg: la
unidad de venta es el kilo o el litro, asi que el stock admite decimales y el
precio se guarda por unidad de medida. Los articulos historicos de miel y cera
(ARTICULOS_COTIZACION) quedan fuera de la edicion y de la baja: su precio se
toca en cotizaciones. Las funciones conservan el sufijo "por_kg" de cuando la
tabla era solo de kilos.
"""


def _validar_producto_por_kg(nombre, categoria, precio, id_excluir=None):
    """
    Normaliza y valida los datos comunes al alta y a la edicion. Devuelve la
    tupla (nombre, categoria, precio) ya lista para escribir en la base.
    """
    nombre = (nombre or "").strip()

    if not (3 <= len(nombre) <= 30) or not REGEX_TEXTO_NUMEROS.match(nombre):
        raise ValueError("El nombre debe tener entre 3 y 30 caracteres, sin simbolos.")

    # El nombre es unico en la tabla: aviso antes de que la base tire IntegrityError
    repetidos = ProductoPorKg.objects.filter(articulo__iexact=nombre)
    if id_excluir:
        repetidos = repetidos.exclude(id=id_excluir)
    if repetidos.exists():
        raise ValueError("Ya existe un producto a granel con ese nombre.")

    if categoria not in dict(Producto.categorias):
        raise ValueError("Seleccione una categoria valida.")

    try:
        precio = Decimal(str(precio).strip())
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError("Ingrese un precio valido.")

    # El precio por kilo o litro se guarda entero: un valor con decimales seria
    # un separador de miles mal escrito, y truncarlo guardaria otro precio
    if precio != precio.to_integral_value():
        raise ValueError("El precio se escribe sin decimales.")

    precio = int(precio)

    if precio < 1:
        raise ValueError("El precio no puede ser menor a 1.")

    return nombre, categoria, precio


def _a_kilos(cantidad):
    # La cantidad (kilos o litros) llega del formulario como texto; acepto vacio como 0
    if cantidad in (None, ""):
        return Decimal("0")
    try:
        kilos = Decimal(str(cantidad).replace(",", "."))
    except InvalidOperation:
        raise ValueError("Ingrese una cantidad valida.")
    return kilos.quantize(Decimal("0.01"))


def nuevo_producto_por_kg(nombre, categoria=None, precio=None, cantidad=None, unidad=None):
    nombre, categoria, precio = _validar_producto_por_kg(nombre, categoria, precio)
    kilos = _a_kilos(cantidad)

    if kilos < 0:
        raise ValueError("El stock inicial no puede ser negativo.")

    # La unidad se fija en el alta y no se edita: cambiarla convertiria el
    # stock y las operaciones viejas en otra magnitud
    if unidad not in dict(ProductoPorKg.unidades):
        raise ValueError("Elija si el producto se vende por kilo o por litro.")

    return ProductoPorKg.objects.create(
        articulo=nombre, categoria=categoria, unidad=unidad, monto=precio, cantidad=kilos
    )


def obtener_datos_producto_por_kg(id_producto):
    try:
        producto = ProductoPorKg.objects.get(id=id_producto, activo=True)
    except ProductoPorKg.DoesNotExist:
        return None

    return {
        "id": producto.id,
        "nombre": producto.articulo,
        "categoria": producto.categoria,
        "unidad": producto.unidad,
        "precio": str(producto.monto),
        "cantidad": str(producto.cantidad),
        "es_cotizacion": producto.es_cotizacion,
    }


def editar_producto_por_kg(id_producto, nombre, categoria, precio):
    # Como en los envasados, el stock no viaja en la edicion: se mueve solo con
    # el modal de ajuste y con las operaciones (UPDATE atomico)
    producto = get_object_or_404(ProductoPorKg, id=id_producto)

    if producto.es_cotizacion:
        raise ValueError("La miel y la cera se editan desde las cotizaciones.")

    nombre, categoria, precio = _validar_producto_por_kg(nombre, categoria, precio, id_excluir=producto.id)

    producto.articulo = nombre
    producto.categoria = categoria
    producto.monto = precio
    producto.save()
    return producto


def eliminar_producto_por_kg(id_producto):
    producto = get_object_or_404(ProductoPorKg, id=id_producto)

    if producto.es_cotizacion:
        raise ValueError("La miel y la cera no se pueden eliminar del inventario.")

    # Baja logica, igual que en Producto: las operaciones historicas siguen
    # apuntando a esta fila
    producto.activo = False
    producto.save()
    return producto


def modificar_stock_por_kg(id_producto, cantidad):
    """
    Suma o resta kilos con el mismo UPDATE condicional atomico que uso en los
    productos envasados: el chequeo de stock y el descuento van en una sola
    sentencia, para que dos ajustes simultaneos no se pisen.
    """
    kilos = _a_kilos(cantidad)

    if not ProductoPorKg.objects.filter(id=id_producto, activo=True).exists():
        raise Http404("Producto no encontrado")

    if kilos < 0:
        filas = ProductoPorKg.objects.filter(
            id=id_producto, activo=True, cantidad__gte=abs(kilos)
        ).update(cantidad=F("cantidad") + kilos)

        if filas == 0:
            raise ValueError("No se puede quitar mas stock del existente.")
    else:
        ProductoPorKg.objects.filter(id=id_producto, activo=True).update(
            cantidad=F("cantidad") + kilos
        )

    return ProductoPorKg.objects.get(id=id_producto)
