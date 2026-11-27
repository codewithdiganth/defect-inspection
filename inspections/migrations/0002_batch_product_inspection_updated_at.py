import django.db.models.deletion
from django.db import migrations, models


def populate_new_fields(apps, schema_editor):
    Batch = apps.get_model("inspections", "Batch")
    Inspection = apps.get_model("inspections", "Inspection")
    Product = apps.get_model("inspections", "Product")
    database = schema_editor.connection.alias
    fallback_product_id = Product.objects.using(database).order_by("pk").values_list(
        "pk", flat=True
    ).first()

    for batch in Batch.objects.using(database).filter(product__isnull=True).iterator():
        product_id = (
            Inspection.objects.using(database)
            .filter(batch_id=batch.pk)
            .order_by("pk")
            .values_list("product_id", flat=True)
            .first()
        ) or fallback_product_id
        if product_id is None:
            raise RuntimeError(
                f"Cannot migrate batch {batch.pk}: no product is available."
            )
        Batch.objects.using(database).filter(pk=batch.pk).update(product_id=product_id)

    for inspection in Inspection.objects.using(database).filter(
        updated_at__isnull=True
    ).iterator():
        Inspection.objects.using(database).filter(pk=inspection.pk).update(
            updated_at=inspection.created_at
        )


class Migration(migrations.Migration):
    dependencies = [
        ("inspections", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="batch",
            name="product",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="batches",
                to="inspections.product",
            ),
        ),
        migrations.AddField(
            model_name="inspection",
            name="updated_at",
            field=models.DateTimeField(null=True),
        ),
        migrations.RunPython(populate_new_fields, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="batch",
            name="product",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="batches",
                to="inspections.product",
            ),
        ),
        migrations.AlterField(
            model_name="inspection",
            name="updated_at",
            field=models.DateTimeField(auto_now=True),
        ),
        migrations.AlterField(
            model_name="inspection",
            name="batch",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="inspections",
                to="inspections.batch",
            ),
        ),
        migrations.AlterField(
            model_name="inspection",
            name="image",
            field=models.ImageField(
                blank=True, null=True, upload_to="inspections/%Y/%m/%d/"
            ),
        ),
        migrations.AlterField(
            model_name="inspection",
            name="predicted_class",
            field=models.CharField(
                blank=True,
                choices=[("Normal", "Normal"), ("Defective", "Defective")],
                max_length=20,
                null=True,
            ),
        ),
    ]
