from django.db import migrations


"""
Articulos por kilo que el tablero de inicio ya venia mostrando con su tarjeta.
Los dejo escritos aca, y no importados del modelo, porque una migracion de datos
es una foto de este momento: si manana cambia la lista, cambia hacia adelante y
no reescribe lo que ya se aplico.
"""
ARTICULOS_DE_INICIO = [
    "Miel menor a 34 mm",
    "Miel menor a 50 mm",
    "Miel mayor a 50 mm",
    "Cera Operculo",
    "Cera Recupero",
]


def marcar(apps, schema_editor):
    """
    Enciendo el flag en lo que inicio ya mostraba: los articulos por kilo de
    cotizaciones y los tambores vacios, que en inicio van en una sola tarjeta
    con la suma de sus unidades. El resto arranca sin marcar.
    """
    ProductoPorKg = apps.get_model("main", "ProductoPorKg")
    Producto = apps.get_model("main", "Producto")

    ProductoPorKg.objects.filter(articulo__in=ARTICULOS_DE_INICIO).update(mostrar_en_inicio=True)
    Producto.objects.filter(categoria="Tambores Vacios").update(mostrar_en_inicio=True)


def desmarcar(apps, schema_editor):
    apps.get_model("main", "ProductoPorKg").objects.update(mostrar_en_inicio=False)
    apps.get_model("main", "Producto").objects.update(mostrar_en_inicio=False)


class Migration(migrations.Migration):

    dependencies = [
        ("main", "0087_producto_mostrar_en_inicio_and_more"),
    ]

    operations = [
        migrations.RunPython(marcar, desmarcar),
    ]
