from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    class Role(models.TextChoices):
        CHEFIA_LOGISTICA = 'chefia_logistica', 'ChefiaLogistica'
        CHEFIA_EVENTOS = 'chefia_eventos', 'ChefiaEventos'
        CHEFIA_ORACAO = 'chefia_oracao', 'ChefiaOração'
        CHEFIA_PROGRAMA = 'chefia_programa', 'ChefiaPrograma'
        CHEFIA_ACONSELHAMENTO = 'chefia_aconselhamento', 'ChefiaAconselhamento'
        CHEFIA_COMUNICACAO = 'chefia_comunicacao', 'ChefiaComunicação'
        CHEFIA_LOJINHA_CANTINA = 'chefia_lojinha_cantina', 'ChefiaLojinha&Cantina'
        ADMINISTRACAO = 'administracao', 'Administração'
        CHEFE_PESSOAL = 'chefe_pessoal', 'ChefeDePessoal'
        CHEFE_MATERIAIS = 'chefe_materiais', 'ChefeDeMateriais'
        CHEFE_EQUIPE = 'chefe_equipe', 'ChefeDaEquipe'
        TRIPE = 'tripe', 'TRIPÉ'
        NOBREAK = 'nobreak', 'NoBreak'

    role = models.CharField(max_length=30, choices=Role.choices, default=Role.CHEFE_EQUIPE)
    must_change_password = models.BooleanField(default=False, help_text='Força a troca da senha no primeiro acesso.')

    def __str__(self):
        return f'{self.username} ({self.get_role_display()})'
