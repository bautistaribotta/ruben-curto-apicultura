from django.db import migrations, models


"""
Los productos a granel dejan de ser solo por kilo: la unidad dice si el
articulo se pesa (kg) o se mide (l). Todo lo existente queda en kilos.
"""
class Migration(migrations.Migration):

    dependencies = [
        ("main", "0089_operacionmarco"),
    ]

    operations = [
        migrations.AddField(
            model_name="productoporkg",
            name="unidad",
            field=models.CharField(
                choices=[("kg", "Kilo"), ("l", "Litro")], default="kg", max_length=2
            ),
        ),
    ]
