from django.db import migrations, models
import django.db.models.deletion


def casas_a_contratos(apps, schema_editor):
    """Convierte el alquiler que vivia en cada casa en su primer contrato.

    Se migra solo lo que estaba marcado como alquilado: sin contrato la casa
    figura sin alquilar, que es exactamente lo que decia el booleano. El precio
    de una casa vacia se pierde, y esta bien que se pierda: era un dato sin
    respaldo, nadie habia pactado ese monto con nadie.

    El fin queda en null (contrato sin vencimiento) porque hasta ahora ninguna
    casa tenia esa fecha cargada. Inventarle un vencimiento a cada una las
    dejaria a todas vencidas o a todas eternas segun la fecha que eligiera yo;
    null conserva el comportamiento de hoy, que es "alquilada", y el usuario va
    completando la fecha real a medida que abre cada contrato.
    """
    Casa = apps.get_model("main", "Casa")
    Contrato = apps.get_model("main", "Contrato")

    Contrato.objects.bulk_create([
        Contrato(
            casa=casa,
            inicio=casa.inicio_contrato,
            fin=casa.fin_contrato,
            # El precio podia estar vacio; el contrato lo necesita si o si
            monto_mensual=casa.precio or 0,
            comision_inmobiliaria=casa.comision_inmobiliaria,
        )
        for casa in Casa.objects.filter(alquilada=True)
    ])


def contratos_a_casas(apps, schema_editor):
    """Vuelta atras: cada casa recupera los numeros de su contrato mas nuevo."""
    Casa = apps.get_model("main", "Casa")
    Contrato = apps.get_model("main", "Contrato")

    for contrato in Contrato.objects.order_by("inicio", "id"):
        Casa.objects.filter(id=contrato.casa_id).update(
            precio=contrato.monto_mensual,
            comision_inmobiliaria=contrato.comision_inmobiliaria,
            inicio_contrato=contrato.inicio,
            fin_contrato=contrato.fin,
            alquilada=True,
        )


class Migration(migrations.Migration):
    """El alquiler se muda de la casa al contrato.

    Una casa tiene varios contratos a lo largo del tiempo y el de hoy no puede
    pisar al del año pasado, que es lo que pasaba mientras el monto, la comision
    y el plazo vivian en una sola fila.

    Estar alquilada deja de ser un booleano que alguien mantiene a mano: pasa a
    ser "hay contrato que cubra este mes". Por eso el campo desaparece.
    """

    dependencies = [
        ('main', '0057_casa_contrato'),
    ]

    operations = [
        migrations.CreateModel(
            name='Contrato',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('inicio', models.DateField()),
                ('fin', models.DateField(blank=True, null=True)),
                ('monto_mensual', models.DecimalField(decimal_places=2, max_digits=12)),
                ('comision_inmobiliaria', models.DecimalField(blank=True, decimal_places=2, max_digits=5, null=True)),
                ('nombre_inquilino', models.CharField(blank=True, max_length=60, null=True)),
                ('casa', models.ForeignKey(db_column='id_casa', on_delete=django.db.models.deletion.CASCADE,
                                           related_name='contratos', to='main.casa')),
            ],
            options={
                'verbose_name_plural': 'Contratos',
                'db_table': 'contratos',
                'ordering': ['-inicio', '-id'],
            },
        ),
        migrations.RunPython(casas_a_contratos, contratos_a_casas),
        migrations.RemoveField(model_name='casa', name='precio'),
        migrations.RemoveField(model_name='casa', name='comision_inmobiliaria'),
        migrations.RemoveField(model_name='casa', name='alquilada'),
        migrations.RemoveField(model_name='casa', name='inicio_contrato'),
        migrations.RemoveField(model_name='casa', name='fin_contrato'),
    ]
