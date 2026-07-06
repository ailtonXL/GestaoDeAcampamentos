from django.db import migrations, models


SIZE_MAP = {
    'xs': 'pp',
    's': 'p',
    'm': 'm',
    'l': 'g',
    'xl': 'gg',
    'xxl': 'xg',
}


def forwards(apps, schema_editor):
    inventory_model = apps.get_model('dashboard', 'InventorySku')
    sale_model = apps.get_model('dashboard', 'SaleRecord')
    preorder_model = apps.get_model('dashboard', 'PreOrderRecord')

    for model in (inventory_model, sale_model, preorder_model):
        for old_value, new_value in SIZE_MAP.items():
            model.objects.filter(size=old_value).update(size=new_value)


def backwards(apps, schema_editor):
    inventory_model = apps.get_model('dashboard', 'InventorySku')
    sale_model = apps.get_model('dashboard', 'SaleRecord')
    preorder_model = apps.get_model('dashboard', 'PreOrderRecord')

    reverse_map = {new_value: old_value for old_value, new_value in SIZE_MAP.items()}
    for model in (inventory_model, sale_model, preorder_model):
        for new_value, old_value in reverse_map.items():
            model.objects.filter(size=new_value).update(size=old_value)


class Migration(migrations.Migration):

    dependencies = [
        ('dashboard', '0004_inventorysku_preorderrecord_salerecord'),
    ]

    operations = [
        migrations.AlterField(
            model_name='inventorysku',
            name='size',
            field=models.CharField(choices=[('pp', 'PP'), ('p', 'P'), ('m', 'M'), ('g', 'G'), ('gg', 'GG'), ('xg', 'XG')], max_length=10),
        ),
        migrations.AlterField(
            model_name='salerecord',
            name='size',
            field=models.CharField(choices=[('pp', 'PP'), ('p', 'P'), ('m', 'M'), ('g', 'G'), ('gg', 'GG'), ('xg', 'XG')], max_length=10),
        ),
        migrations.AlterField(
            model_name='preorderrecord',
            name='size',
            field=models.CharField(choices=[('pp', 'PP'), ('p', 'P'), ('m', 'M'), ('g', 'G'), ('gg', 'GG'), ('xg', 'XG')], max_length=10),
        ),
        migrations.RunPython(forwards, backwards),
    ]
