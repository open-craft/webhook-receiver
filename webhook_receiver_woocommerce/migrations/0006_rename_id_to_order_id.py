from django.db import migrations, models
import django.db.models.deletion


def populate(apps, schema_editor):
   model = apps.get_model('webhook_receiver_woocommerce', 'woocommerceorder')
   for index, item in enumerate(model.objects.all(), start=1):
       item.id = index
       item.save()


class Migration(migrations.Migration):

    dependencies = [
        ('webhook_receiver_woocommerce', '0005_fix_unique_constraint_name'),
    ]

    operations = [
        migrations.AlterField(
            model_name='woocommerceorderitem',
            name='order',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='webhook_receiver_woocommerce.WoocommerceOrder', db_constraint=False, db_index=True, null=False),
        ),
        migrations.RenameField(
            model_name='woocommerceorder',
            old_name='id',
            new_name='order_id',
        ),
        migrations.AlterField(
            model_name='woocommerceorder',
            name='order_id',
            field=models.BigIntegerField(editable=False),
        ),
        migrations.AddField(
            model_name='woocommerceorder',
            name='id',
            field=models.BigAutoField(primary_key=True, serialize=False, verbose_name='ID'),
        ),
        migrations.RunPython(populate),
        migrations.AlterField(
            model_name='woocommerceorderitem',
            name='order',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                to='webhook_receiver_woocommerce.WoocommerceOrder'
            ),
        ),
    ]
