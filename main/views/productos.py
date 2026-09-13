# Productos envasados y a granel: listado, alta, edicion, baja y stock.

from decimal import Decimal, InvalidOperation

from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.contrib import messages
from django.http import JsonResponse

from main.models import Producto, ProductoPorKg

from main.services.comunes import filtro_tokens
from main.services.productos import (editar_producto, editar_producto_por_kg, eliminar_producto,
                                     eliminar_producto_por_kg, modificar_stock,
                                     modificar_stock_por_kg, nuevo_producto, nuevo_producto_por_kg,
                                     obtener_datos_producto, obtener_datos_producto_por_kg)


def _productos_por_kg_del_listado(q, categoria):
    """
    Productos a granel (por kilo o por litro) que entran en un listado, segun el
    buscador y el chip de categoria. Entran con las mismas reglas que los
    productos por unidad: todos con "Todas", los de la categoria elegida al
    filtrar y los que coinciden por nombre al buscar, asi el inventario y las
    operaciones muestran las dos tablas como un solo catalogo. La busqueda por
    ID es solo de los productos por unidad: los de granel no muestran ID.
    """
    if q and q.isdigit():
        return ProductoPorKg.objects.none()

    granel = ProductoPorKg.objects.filter(activo=True)

    if categoria:
        granel = granel.filter(categoria=categoria)

    if q:
        granel = granel.filter(filtro_tokens(q, "articulo"))

    return granel.order_by("articulo")


@login_required
def productos(request):
    """
    Recibo el metodo POST, guardo los datos del formulario y creo
    el producto en la base de datos, queda realizar validaciones
    """
    if request.method == "POST":
        id_producto = request.POST.get("id_producto")
        nombre_producto = request.POST.get("nombre")
        categoria = request.POST.get("categoria")
        precio = request.POST.get("precio")
        cantidad = request.POST.get("stock")

        """
        Unidad de venta elegida en el panel: "kg" o "l" mandan el producto a
        productos_por_kg (stock con decimales, precio por kilo o por litro) y
        cualquier otro valor lo trata como producto por unidad, en la tabla de
        productos. Los formularios de baja y de ajuste de stock mandan la misma
        marca para saber sobre que tabla operar.
        """
        unidad_venta = request.POST.get("unidad_venta")
        por_granel = unidad_venta in dict(ProductoPorKg.unidades)

        # Si el usuario no ingresó un stock (campo vacío), lo coloco en 0
        if not cantidad:
            cantidad = 0

        # Verifico qué acción se está realizando
        accion = request.POST.get("accion")
        id_eliminar = request.POST.get("id_eliminar")

        if accion == "modificar_stock":
            id_producto_stock = request.POST.get("id_producto_stock")
            tipo_modificacion = request.POST.get("tipo_modificacion")
            cantidad_modificar = request.POST.get("cantidad")
            
            if id_producto_stock and cantidad_modificar and por_granel:
                try:
                    producto = ProductoPorKg.objects.get(id=id_producto_stock, activo=True)
                    kilos = Decimal(str(cantidad_modificar).replace(",", "."))
                    if tipo_modificacion == "quitar":
                        kilos = -kilos

                    modificar_stock_por_kg(id_producto_stock, kilos)

                    verbo = "quitó" if tipo_modificacion == "quitar" else "agregó"
                    messages.success(request, f"Se {verbo} {abs(kilos):g} {producto.abreviatura} de {producto.articulo}")
                except ProductoPorKg.DoesNotExist:
                    messages.error(request, "El producto no existe.")
                except InvalidOperation:
                    messages.error(request, "Ingrese una cantidad válida.")
                except ValueError as e:
                    messages.error(request, str(e))

                return redirect("productos")

            if id_producto_stock and cantidad_modificar:
                try:
                    producto = Producto.objects.get(id=id_producto_stock)
                    cantidad_modificar = int(cantidad_modificar)
                    if tipo_modificacion == "quitar":
                        cantidad_modificar = -cantidad_modificar
                        
                    modificar_stock(id_producto_stock, cantidad_modificar)
                    
                    if tipo_modificacion == "quitar":
                        unidad_str = "unidad" if abs(cantidad_modificar) == 1 else "unidades"
                        messages.success(request, f"Se quitó {abs(cantidad_modificar)} {unidad_str} de {producto.nombre}")
                    else:
                        unidad_str = "unidad" if abs(cantidad_modificar) == 1 else "unidades"
                        messages.success(request, f"Se agregó {abs(cantidad_modificar)} {unidad_str} de {producto.nombre}")
                except Producto.DoesNotExist:
                    messages.error(request, "El producto no existe.")
                except ValueError as e:
                    messages.error(request, str(e))
                except Exception as e:
                    messages.error(request, f"Error al modificar el stock: {str(e)}")
                    
            return redirect("productos")

        elif id_eliminar:
            try:
                if por_granel:
                    eliminar_producto_por_kg(id_eliminar)
                else:
                    eliminar_producto(id_eliminar)
                messages.success(request, "Producto eliminado correctamente")
            except ValueError as e:
                messages.error(request, str(e))
            return redirect("productos")

        elif unidad_venta != "unidad" and not por_granel:
            # El panel obliga a elegir como se vende: sin ese dato no se sabe en
            # que tabla va el producto, asi que no lo doy de alta a medias
            messages.error(request, "Elija si el producto se vende por unidad, por kilo o por litro.")

        elif por_granel:
            # Producto que se pesa o se mide: vive en la tabla de productos a granel
            try:
                if id_producto:
                    editar_producto_por_kg(id_producto, nombre_producto, categoria, precio)
                    messages.success(request, "Producto editado correctamente")
                else:
                    nuevo_producto_por_kg(nombre_producto, categoria, precio, cantidad, unidad_venta)
                    messages.success(request, "Producto agregado correctamente")
            except ValueError as e:
                messages.error(request, str(e))

        else:
            # Si es una EDICION
            if id_producto:
                editar_producto(
                    id_producto, nombre_producto, categoria, precio, True
                )
                messages.success(request, "Producto editado correctamente")

            # Si es un NUEVO producto
            else:
                nuevo_producto(nombre_producto, categoria, precio, cantidad)
                messages.success(request, "Producto agregado correctamente")

        return redirect("productos")

    # Parámetros de búsqueda y filtrado
    q = request.GET.get("q", "")
    categoria_filtrada = request.GET.get("categoria", "")

    productos = Producto.objects.filter(activo=True)

    if q:
        if q.isdigit():
            # Si es solo números, busco por ID (exacto o que contenga)
            productos = productos.filter(id__icontains=q)
        else:
            # Si no, buscamos por nombre (multi-palabra: "cera laminada"
            # encuentra "Cera Estampada Laminada")
            productos = productos.filter(filtro_tokens(q, "nombre"))

    if categoria_filtrada:
        productos = productos.filter(categoria=categoria_filtrada)

    productos = productos.order_by("nombre")

    # Los productos que se venden por kilo o por litro viven en ProductoPorKg, no en Producto:
    # se listan aparte y el template les da su propia fila
    granel = _productos_por_kg_del_listado(q, categoria_filtrada)

    # Integro granel y productos en una sola lista paginada de a 5 filas: el stock a
    # granel aparece primero y despues los productos envasados, contando ambos para la
    # paginacion (asi la pagina nunca supera 5 filas). Cada pagina se separa de nuevo
    # por tipo para que el template mantenga su propio render de cada fila.
    items = list(granel) + list(productos)
    paginator_productos = Paginator(items, 5)
    pagina_obj = paginator_productos.get_page(request.GET.get("page"))

    granel_pagina = [item for item in pagina_obj if isinstance(item, ProductoPorKg)]
    productos_pagina = [item for item in pagina_obj if isinstance(item, Producto)]

    contexto = {
        "productos": productos_pagina,
        "granel": granel_pagina,
        "pagina": pagina_obj,
        "q": q,
        "categoria": categoria_filtrada,
    }

    # Si es una petición AJAX, devuelvo solo la tabla
    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        return render(request, "tabla_productos.html", contexto)

    return render(request, "productos.html", contexto)


@login_required
def obtener_producto_json(request, id_producto):
    datos = obtener_datos_producto(id_producto)

    if datos:
        # Si el producto existe, devuelvo la respuesta exitosa en JSON
        return JsonResponse(datos)

    # Si no lo encuentro o está inactivo, devuelvo un error 404
    return JsonResponse({"Error": "Producto no encontrado"}, status=404)


@login_required
def obtener_producto_por_kg_json(request, id_producto):
    datos = obtener_datos_producto_por_kg(id_producto)

    if datos:
        return JsonResponse(datos)

    return JsonResponse({"Error": "Producto no encontrado"}, status=404)
