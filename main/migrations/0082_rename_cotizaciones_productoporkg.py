from django.db import migrations


# Renombro el modelo Cotizaciones a ProductoPorKg y su tabla a "productos_por_kg".
# La tabla dejo de ser solo cotizaciones: hoy guarda los articulos a granel con su
# stock en kilos, ademas del precio por kilo. El nombre refleja mejor ese rol.
# Se hace por RenameModel + AlterModelTable para no perder datos (no es un DROP/CREATE).
class Migration(migrations.Migration):

    dependencies = [
        ("main", "0081_renombrar_articulos_miel_granel"),
    ]

    operations = [
        migrations.RenameModel(old_name="Cotizaciones", new_name="ProductoPorKg"),
        migrations.AlterModelTable(name="productoporkg", table="productos_por_kg"),
        migrations.AlterModelOptions(
            name="productoporkg",
            options={"verbose_name_plural": "Productos por kg"},
        ),
    ]
