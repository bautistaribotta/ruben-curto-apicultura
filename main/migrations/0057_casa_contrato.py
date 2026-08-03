from django.db import migrations, models


class Migration(migrations.Migration):
    """La fecha de alta de la casa pasa a ser el inicio del contrato, y se suma el fin.

    Es un RenameField y no un remove mas un add: el dato que ya esta cargado dice
    exactamente lo mismo (desde cuando se le puede reclamar el alquiler), asi que
    tirarlo dejaria a todas las casas dadas de alta el dia de la migracion y
    borraria de los listados sus meses anteriores.

    El fin arranca en null para todas: un contrato sin vencimiento cargado no
    caduca nunca, que es la unica suposicion que no le inventa un vencimiento a
    nadie. Se completa a mano casa por casa.
    """

    dependencies = [
        ('main', '0056_casa_fecha_alta'),
    ]

    operations = [
        migrations.RenameField(
            model_name='casa',
            old_name='fecha_alta',
            new_name='inicio_contrato',
        ),
        migrations.AddField(
            model_name='casa',
            name='fin_contrato',
            field=models.DateField(blank=True, null=True),
        ),
    ]
