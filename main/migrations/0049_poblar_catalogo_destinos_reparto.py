from django.db import migrations


def poblar_catalogo(apps, schema_editor):
    """Arma el catalogo de destinos a partir de los repartos ya cargados.

    Hasta ahora el destino se escribia a mano en detalle_viaje_reparto. Tomo esos
    nombres, doy de alta un destino por cada uno (con valor 0, para que el cliente
    le ponga la tarifa real desde la vista de destinos) y engancho cada reparto a
    su primera parada, que es la que pasa a ser su destino unico.
    """
    DestinoViajeReparto = apps.get_model("main", "DestinoViajeReparto")
    DetalleViajeReparto = apps.get_model("main", "DetalleViajeReparto")
    ViajeReparto = apps.get_model("main", "ViajeReparto")

    # Agrupo por nombre en minusculas para no crear dos destinos que solo se
    # diferencian en como esta escrito ("Cordoba" y "cordoba" son el mismo lugar).
    # Me quedo con la primera forma escrita de cada uno.
    nombres = {}
    for detalle in DetalleViajeReparto.objects.all().order_by("id"):
        nombre = (detalle.destinos_reparto or "").strip()
        if nombre:
            nombres.setdefault(nombre.lower(), nombre)

    destinos_por_nombre = {}
    for clave, nombre in nombres.items():
        destino, _ = DestinoViajeReparto.objects.get_or_create(
            localidad_destino=nombre,
            defaults={"valor_viaje": 0, "cant_viajes": 0, "activo": True},
        )
        destinos_por_nombre[clave] = destino

    # Primera parada de cada reparto: es la que queda como destino del viaje.
    primeras_paradas = {}
    for detalle in DetalleViajeReparto.objects.all().order_by("id"):
        primeras_paradas.setdefault(detalle.viaje_reparto_id, detalle.destinos_reparto)

    for viaje in ViajeReparto.objects.all():
        nombre = (primeras_paradas.get(viaje.id) or "").strip()
        destino = destinos_por_nombre.get(nombre.lower())
        if destino:
            viaje.destino = destino
            viaje.save(update_fields=["destino"])

    # El contador cuenta viajes vigentes: los que ya estaban dados de baja no suman,
    # igual que despues cuando eliminar un reparto descuenta una unidad.
    for destino in DestinoViajeReparto.objects.all():
        destino.cant_viajes = ViajeReparto.objects.filter(destino=destino, activo=True).count()
        destino.save(update_fields=["cant_viajes"])


class Migration(migrations.Migration):

    dependencies = [
        ("main", "0048_catalogo_destinos_reparto"),
    ]

    operations = [
        # Sin vuelta atras: revertir la migracion anterior borra la tabla del catalogo
        # y la columna del viaje, con lo cual no queda nada que deshacer aca.
        migrations.RunPython(poblar_catalogo, migrations.RunPython.noop),
    ]
