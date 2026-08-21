from django.db import migrations


# Nombres mas descriptivos para los articulos de miel a granel. La clave del
# articulo se usa como identificador en varios lugares (tablero de inicio,
# get_cotizacion_miel_50mm, edicion de cotizaciones), por eso el rename va junto
# con la actualizacion de esas referencias en el codigo.
RENOMBRES = {
    "Miel 34mm": "Miel menor a 34 mm",
    "Miel 50mm": "Miel menor a 50 mm",
    "Miel +50mm": "Miel mayor a 50 mm",
}


def renombrar(apps, schema_editor):
    Cotizaciones = apps.get_model("main", "Cotizaciones")
    for viejo, nuevo in RENOMBRES.items():
        Cotizaciones.objects.filter(articulo=viejo).update(articulo=nuevo)


def revertir(apps, schema_editor):
    Cotizaciones = apps.get_model("main", "Cotizaciones")
    for viejo, nuevo in RENOMBRES.items():
        Cotizaciones.objects.filter(articulo=nuevo).update(articulo=viejo)


class Migration(migrations.Migration):

    dependencies = [
        ("main", "0080_pagosempleados_origen_viaje_devolucion_estado_and_more"),
    ]

    operations = [
        migrations.RunPython(renombrar, revertir),
    ]
