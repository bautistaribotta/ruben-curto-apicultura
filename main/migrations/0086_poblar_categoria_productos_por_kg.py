from django.db import migrations


def poblar_categoria(apps, schema_editor):
    """
    Los articulos historicos por kilo (miel y cera) no tenian categoria propia:
    el listado la deducia del prefijo del nombre. Ahora que el campo existe,
    lo relleno una sola vez para que el filtro por categoria no dependa del nombre.
    """
    ProductoPorKg = apps.get_model("main", "ProductoPorKg")
    for prefijo, categoria in (("Miel", "Miel"), ("Cera", "Cera")):
        ProductoPorKg.objects.filter(articulo__startswith=prefijo, categoria__isnull=True).update(
            categoria=categoria
        )


def revertir(apps, schema_editor):
    ProductoPorKg = apps.get_model("main", "ProductoPorKg")
    ProductoPorKg.objects.update(categoria=None)


class Migration(migrations.Migration):

    dependencies = [
        ("main", "0085_productoporkg_activo_productoporkg_categoria_and_more"),
    ]

    operations = [
        migrations.RunPython(poblar_categoria, revertir),
    ]
