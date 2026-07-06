from django.db import migrations, models


def migrate_role_values(apps, schema_editor):
    User = apps.get_model('accounts', 'User')
    role_map = {
        'chefia': 'chefe_equipe',
        'tripe7': 'tripe',
    }
    for old_value, new_value in role_map.items():
        User.objects.filter(role=old_value).update(role=new_value)


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0003_user_must_change_password'),
    ]

    operations = [
        migrations.RunPython(migrate_role_values, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='user',
            name='role',
            field=models.CharField(
                choices=[
                    ('chefia_logistica', 'ChefiaLogistica'),
                    ('chefia_eventos', 'ChefiaEventos'),
                    ('chefia_oracao', 'ChefiaOração'),
                    ('chefia_programa', 'ChefiaPrograma'),
                    ('chefia_aconselhamento', 'ChefiaAconselhamento'),
                    ('chefia_comunicacao', 'ChefiaComunicação'),
                    ('chefia_lojinha_cantina', 'ChefiaLojinha&Cantina'),
                    ('administracao', 'Administração'),
                    ('chefe_pessoal', 'ChefeDePessoal'),
                    ('chefe_materiais', 'ChefeDeMateriais'),
                    ('chefe_equipe', 'ChefeDaEquipe'),
                    ('tripe', 'TRIPÉ'),
                ],
                default='chefe_equipe',
                max_length=30,
            ),
        ),
    ]
