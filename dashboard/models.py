from django.conf import settings
from django.db import models
from decimal import Decimal


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


class ProductColorChoices(models.TextChoices):
    WHITE = 'white', 'Branco'
    BLACK = 'black', 'Preto'


class ProductSizeChoices(models.TextChoices):
    PP = 'pp', 'PP'
    P = 'p', 'P'
    M = 'm', 'M'
    G = 'g', 'G'
    GG = 'gg', 'GG'
    XG = 'xg', 'XG'


class PaymentMethodChoices(models.TextChoices):
    PIX_CASH = 'pix_cash', 'Pix/Dinheiro'
    CARD = 'card', 'Cartão'


class PreOrderSourceChoices(models.TextChoices):
    FORM = 'form', 'Formulário'
    SHEET = 'sheet', 'Planilha'


class InventorySku(models.Model):
    color = models.CharField(max_length=20, choices=ProductColorChoices.choices)
    size = models.CharField(max_length=10, choices=ProductSizeChoices.choices)
    initial_quantity = models.PositiveIntegerField(default=0)
    sold_quantity = models.PositiveIntegerField(default=0)
    reserved_quantity = models.PositiveIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['color', 'size']
        unique_together = [('color', 'size')]
        verbose_name = 'SKU de inventário'
        verbose_name_plural = 'SKUs de inventário'

    @property
    def balance_quantity(self):
        return max(self.initial_quantity - self.sold_quantity - self.reserved_quantity, 0)

    def __str__(self):
        return f'{self.get_color_display()} - {self.get_size_display()}'


class SaleRecord(models.Model):
    product_name = models.CharField(max_length=120)
    color = models.CharField(max_length=20, choices=ProductColorChoices.choices)
    size = models.CharField(max_length=10, choices=ProductSizeChoices.choices)
    quantity = models.PositiveIntegerField(default=1)
    payment_method = models.CharField(max_length=20, choices=PaymentMethodChoices.choices)
    unit_value = models.DecimalField(max_digits=10, decimal_places=2)
    total_value = models.DecimalField(max_digits=10, decimal_places=2)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Registro de venda'
        verbose_name_plural = 'Registros de venda'

    def __str__(self):
        return f'{self.product_name} - {self.get_size_display()} x {self.quantity}'


class PreOrderStatusChoices(models.TextChoices):
    RESERVADO = 'reservado', 'Reservado'
    IMPORTADO = 'importado', 'Importado'
    SINCRONIZADO = 'sincronizado', 'Sincronizado'


class PreOrderPaymentStatusChoices(models.TextChoices):
    PENDENTE = 'pendente', 'Pendente'
    PAGO = 'pago', 'Pago'


class PreOrderRecord(models.Model):
    external_key = models.CharField(max_length=80, unique=True)
    source = models.CharField(max_length=20, choices=PreOrderSourceChoices.choices, default=PreOrderSourceChoices.FORM)
    volunteer_name = models.CharField(max_length=120)
    color = models.CharField(max_length=20, choices=ProductColorChoices.choices)
    size = models.CharField(max_length=10, choices=ProductSizeChoices.choices)
    quantity = models.PositiveIntegerField(default=1)
    payment_method = models.CharField(max_length=20, choices=PaymentMethodChoices.choices, blank=True, default='')
    payment_status = models.CharField(max_length=20, choices=PreOrderPaymentStatusChoices.choices, default=PreOrderPaymentStatusChoices.PENDENTE)
    status = models.CharField(max_length=20, choices=PreOrderStatusChoices.choices, default=PreOrderStatusChoices.RESERVADO)
    sheet_row_number = models.PositiveIntegerField(null=True, blank=True)
    sheet_payload = models.JSONField(default=dict, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)
    imported_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Pré-encomenda'
        verbose_name_plural = 'Pré-encomendas'

    def __str__(self):
        return f'{self.volunteer_name} - {self.get_color_display()} {self.get_size_display()}'

    @property
    def payment_value(self):
        if self.payment_status != PreOrderPaymentStatusChoices.PAGO:
            return Decimal('0.00')
        if self.payment_method == PaymentMethodChoices.PIX_CASH:
            return Decimal('65.00')
        if self.payment_method == PaymentMethodChoices.CARD:
            return Decimal('70.00')
        return Decimal('0.00')


class PreOrderSheetConfig(models.Model):
    sheet_link = models.URLField(blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Configuração de importação de pré-encomendas'
        verbose_name_plural = 'Configurações de importação de pré-encomendas'

    def __str__(self):
        return 'Configuração de importação de pré-encomendas'


class AconselhamentoSalaCaracteristicaChoices(models.TextChoices):
    MASCULINO = 'masculino', 'Masculino'
    FEMININO = 'feminino', 'Feminino'


class AconselhamentoCampistaSexoChoices(models.TextChoices):
    MASCULINO = 'masculino', 'Masculino'
    FEMININO = 'feminino', 'Feminino'
    OUTRO = 'outro', 'Outro'


class AconselhamentoConfig(models.Model):
    sheet_link = models.URLField(blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Configuração de aconselhamento'
        verbose_name_plural = 'Configurações de aconselhamento'

    def __str__(self):
        return 'Configuração de aconselhamento'


class AconselhamentoSala(models.Model):
    nome = models.CharField(max_length=120)
    capacidade = models.PositiveIntegerField(default=1)
    caracteristica = models.CharField(max_length=20, choices=AconselhamentoSalaCaracteristicaChoices.choices, default=AconselhamentoSalaCaracteristicaChoices.MASCULINO)
    observacoes = models.TextField(blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['nome']
        verbose_name = 'Sala de aconselhamento'
        verbose_name_plural = 'Salas de aconselhamento'

    def __str__(self):
        return self.nome

    @property
    def ocupacao_total(self):
        return self.campistas.count()

    @property
    def vagas_livres(self):
        return max(self.capacidade - self.ocupacao_total, 0)


class AconselhamentoCampista(models.Model):
    nome = models.CharField(max_length=120)
    idade = models.PositiveIntegerField(null=True, blank=True)
    sexo = models.CharField(max_length=20, choices=AconselhamentoCampistaSexoChoices.choices, blank=True, default='')
    celula = models.CharField(max_length=120, blank=True)
    observacoes = models.TextField(blank=True)
    origem_planilha = models.CharField(max_length=120, blank=True)
    linha_planilha = models.PositiveIntegerField(null=True, blank=True)
    sala = models.ForeignKey(AconselhamentoSala, null=True, blank=True, on_delete=models.SET_NULL, related_name='campistas')
    criado_por = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['nome']
        verbose_name = 'Acampante'
        verbose_name_plural = 'Acampantes'

    def __str__(self):
        return self.nome


class AconselhamentoHistorico(models.Model):
    campista = models.ForeignKey(AconselhamentoCampista, on_delete=models.CASCADE, related_name='historicos')
    sala_origem = models.ForeignKey(AconselhamentoSala, null=True, blank=True, on_delete=models.SET_NULL, related_name='historico_origem')
    sala_destino = models.ForeignKey(AconselhamentoSala, null=True, blank=True, on_delete=models.SET_NULL, related_name='historico_destino')
    acao = models.CharField(max_length=60)
    detalhe = models.TextField(blank=True)
    criado_por = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-criado_em']
        verbose_name = 'Histórico de aconselhamento'
        verbose_name_plural = 'Históricos de aconselhamento'

    def __str__(self):
        return f'{self.campista.nome} - {self.acao}'


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
