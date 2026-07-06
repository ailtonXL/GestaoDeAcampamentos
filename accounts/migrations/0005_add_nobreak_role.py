from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0004_expand_roles_and_migrate_values'),
    ]

    operations = [
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
                    ('nobreak', 'NoBreak'),
                ],
                default='chefe_equipe',
                max_length=30,
            ),
        ),
    ]
