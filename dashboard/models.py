from django.conf import settings
from django.db import models


class EquipeChoices(models.TextChoices):
    EVENTOS = 'eventos', 'Eventos'
    LOGISTICA = 'logistica', 'Logística'
    ACONSELHAMENTO = 'aconselhamento', 'Aconselhamento'
    PROGRAMA = 'programa', 'Programa'
    LOJINHA_CANTINA = 'lojinha_cantina', 'Lojinha e Cantina'
    ORACAO = 'oracao', 'Oração'
    COMUNICACAO = 'comunicacao', 'Comunicação'
    ADMINISTRACAO = 'administracao', 'Administração'
    FINANCEIRO = 'financeiro', 'Financeiro'
    MATERIAIS = 'materiais', 'Materiais'
    PESSOAL = 'pessoal', 'Pessoal'


class StatusTarefaChoices(models.TextChoices):
    PENDENTE = 'pendente', 'Pendente'
    ANDAMENTO = 'andamento', 'Em andamento'
    CONCLUIDA = 'concluida', 'Concluída'


class Membro(models.Model):
    nome = models.CharField(max_length=120)
    equipe = models.CharField(max_length=30, choices=EquipeChoices.choices)
    ativo = models.BooleanField(default=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['nome']
        verbose_name = 'Membro'
        verbose_name_plural = 'Membros'

    def __str__(self):
        return f'{self.nome} - {self.get_equipe_display()}'


class Tarefa(models.Model):
    titulo = models.CharField(max_length=150)
    descricao = models.TextField(blank=True)
    equipe = models.CharField(max_length=30, choices=EquipeChoices.choices)
    responsavel = models.ForeignKey(Membro, on_delete=models.SET_NULL, null=True, blank=True, related_name='tarefas')
    status = models.CharField(max_length=20, choices=StatusTarefaChoices.choices, default=StatusTarefaChoices.PENDENTE)
    prazo = models.DateField(null=True, blank=True)
    valor_estimado = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['status', 'prazo', '-criado_em']
        verbose_name = 'Tarefa'
        verbose_name_plural = 'Tarefas'

    def __str__(self):
        return f'{self.titulo} - {self.get_equipe_display()}'


class SyncStatusChoices(models.TextChoices):
    NAO_CONFIGURADO = 'nao_configurado', 'Nao configurado'
    SUCESSO = 'sucesso', 'Sucesso'
    FALHA = 'falha', 'Falha'


class ClassroomStatusChoices(models.TextChoices):
    NAO_ENVIADO = 'nao_enviado', 'Nao enviado'
    SUCESSO = 'sucesso', 'Sucesso'
    FALHA = 'falha', 'Falha'


class PreparoRegistro(models.Model):
    nome_completo = models.CharField(max_length=120)
    email = models.EmailField(blank=True)
    telefone = models.CharField(max_length=30, blank=True)
    titulo_atividade = models.CharField(max_length=180)
    descricao_atividade = models.TextField(blank=True)
    prazo_entrega = models.DateField(null=True, blank=True)
    external_sync_status = models.CharField(
        max_length=20,
        choices=SyncStatusChoices.choices,
        default=SyncStatusChoices.NAO_CONFIGURADO,
    )
    external_sync_response = models.TextField(blank=True)
    classroom_course_id = models.CharField(max_length=120, blank=True)
    classroom_status = models.CharField(
        max_length=20,
        choices=ClassroomStatusChoices.choices,
        default=ClassroomStatusChoices.NAO_ENVIADO,
    )
    classroom_coursework_id = models.CharField(max_length=120, blank=True)
    classroom_response = models.TextField(blank=True)
    criado_por = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-criado_em']
        verbose_name = 'Registro de Preparo'
        verbose_name_plural = 'Registros de Preparo'

    def __str__(self):
        return f'{self.titulo_atividade} - {self.nome_completo}'
