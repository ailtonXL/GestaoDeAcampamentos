from django import forms

from .models import (
    AconselhamentoCampistaSexoChoices,
    AconselhamentoSalaCaracteristicaChoices,
    EquipeChoices,
    InventorySku,
    Membro,
    PaymentMethodChoices,
    PreOrderRecord,
    PreOrderSourceChoices,
    PreOrderPaymentStatusChoices,
    PreparoRegistro,
    ProductColorChoices,
    ProductSizeChoices,
    StatusTarefaChoices,
    Tarefa,
)


class MembroQuickForm(forms.ModelForm):
    class Meta:
        model = Membro
        fields = ('nome', 'ativo')
        labels = {
            'nome': 'Nome',
            'ativo': 'Ativo',
        }
        widgets = {
            'nome': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Nome da pessoa'}),
            'ativo': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }


class MembroForm(forms.ModelForm):
    class Meta:
        model = Membro
        fields = ('nome', 'equipe', 'ativo')
        labels = {
            'nome': 'Nome',
            'equipe': 'Setor',
            'ativo': 'Ativo',
        }
        widgets = {
            'nome': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Nome da pessoa'}),
            'equipe': forms.Select(attrs={'class': 'form-select'}, choices=EquipeChoices.choices),
            'ativo': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }


class TaskForm(forms.ModelForm):
    class Meta:
        model = Tarefa
        fields = ('titulo', 'descricao', 'responsavel', 'status', 'prazo', 'valor_estimado')
        labels = {
            'titulo': 'Titulo',
            'descricao': 'Descricao',
            'responsavel': 'Responsavel',
            'status': 'Status',
            'prazo': 'Prazo',
            'valor_estimado': 'Valor estimado',
        }
        widgets = {
            'titulo': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Nome da tarefa'}),
            'descricao': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Detalhes opcionais'}),
            'responsavel': forms.Select(attrs={'class': 'form-select'}),
            'status': forms.Select(attrs={'class': 'form-select'}, choices=StatusTarefaChoices.choices),
            'prazo': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'valor_estimado': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0'}),
        }

    def __init__(self, *args, **kwargs):
        team_slug = kwargs.pop('team_slug', None)
        super().__init__(*args, **kwargs)
        queryset = Membro.objects.filter(ativo=True).order_by('nome')
        if team_slug:
            queryset = queryset.filter(equipe=team_slug)
        self.fields['responsavel'].queryset = queryset
        self.fields['responsavel'].required = False


class PreparoForm(forms.ModelForm):
    publicar_no_classroom = forms.BooleanField(
        required=False,
        label='Publicar atividade no Google Sala de Aula',
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
    )
    google_course_id = forms.CharField(
        required=False,
        label='ID da turma no Google Sala de Aula',
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ex.: 123456789101'}),
    )

    class Meta:
        model = PreparoRegistro
        fields = (
            'nome_completo',
            'email',
            'telefone',
            'titulo_atividade',
            'descricao_atividade',
            'prazo_entrega',
        )
        labels = {
            'nome_completo': 'Nome completo',
            'email': 'E-mail',
            'telefone': 'Telefone',
            'titulo_atividade': 'Titulo da atividade',
            'descricao_atividade': 'Descricao da atividade',
            'prazo_entrega': 'Prazo de entrega',
        }
        widgets = {
            'nome_completo': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Nome da pessoa responsavel'}),
            'email': forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'email@exemplo.com'}),
            'telefone': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '(00) 00000-0000'}),
            'titulo_atividade': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Titulo da atividade'}),
            'descricao_atividade': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Detalhes da atividade'}),
            'prazo_entrega': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
        }


class SaleForm(forms.Form):
    product_name = forms.CharField(
        label='Produto',
        max_length=120,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Nome do produto'}),
    )
    color = forms.ChoiceField(
        label='Cor',
        choices=ProductColorChoices.choices,
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    size = forms.ChoiceField(
        label='Tamanho',
        choices=ProductSizeChoices.choices,
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    quantity = forms.IntegerField(
        label='Quantidade',
        min_value=1,
        initial=1,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'min': '1'}),
    )
    payment_method = forms.ChoiceField(
        label='Forma de pagamento',
        choices=PaymentMethodChoices.choices,
        widget=forms.Select(attrs={'class': 'form-select'}),
    )


class InventoryAdjustForm(forms.Form):
    color = forms.ChoiceField(
        label='Cor',
        choices=ProductColorChoices.choices,
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    size = forms.ChoiceField(
        label='Tamanho',
        choices=ProductSizeChoices.choices,
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    initial_quantity = forms.IntegerField(
        label='Quantidade inicial',
        min_value=0,
        initial=0,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'min': '0'}),
    )


class PreOrderForm(forms.Form):
    volunteer_name = forms.CharField(
        label='Nome',
        max_length=120,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Nome do voluntário'}),
    )
    color = forms.ChoiceField(
        label='Cor',
        choices=ProductColorChoices.choices,
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    size = forms.ChoiceField(
        label='Tamanho',
        choices=ProductSizeChoices.choices,
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    quantity = forms.IntegerField(
        label='Quantidade',
        min_value=1,
        initial=1,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'min': '1'}),
    )


class SheetImportForm(forms.Form):
    sheet_link = forms.URLField(
        required=False,
        label='Link da planilha',
        widget=forms.URLInput(attrs={'class': 'form-control', 'placeholder': 'https://docs.google.com/spreadsheets/d/...'}),
    )


class PreOrderPaymentForm(forms.Form):
    preorder_id = forms.IntegerField(widget=forms.HiddenInput())
    payment_status = forms.ChoiceField(
        label='Status',
        choices=PreOrderPaymentStatusChoices.choices,
        initial=PreOrderPaymentStatusChoices.PENDENTE,
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    payment_method = forms.ChoiceField(
        label='Forma de pagamento',
        choices=PaymentMethodChoices.choices,
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'}),
    )


class PreOrderSearchForm(forms.Form):
    q = forms.CharField(
        required=False,
        label='Buscar por nome',
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Digite um nome'}),
    )


class AconselhamentoSalaForm(forms.Form):
    nome = forms.CharField(
        label='Nome do quarto',
        max_length=120,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ex.: Quarto 1'}),
    )
    capacidade = forms.IntegerField(
        label='Capacidade',
        min_value=1,
        initial=1,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'min': '1'}),
    )
    caracteristica = forms.ChoiceField(
        label='Características',
        choices=AconselhamentoSalaCaracteristicaChoices.choices,
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    observacoes = forms.CharField(
        label='Observações',
        required=False,
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 2, 'placeholder': 'Detalhes do quarto'}),
    )


class AconselhamentoFiltroForm(forms.Form):
    nome = forms.CharField(required=False, label='Nome', widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Buscar por nome'}))
    sexo = forms.ChoiceField(required=False, label='Sexo', choices=[('', 'Todos'), *AconselhamentoCampistaSexoChoices.choices], widget=forms.Select(attrs={'class': 'form-select'}))
    celula = forms.CharField(required=False, label='Célula', widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Célula'}))
    idade_min = forms.IntegerField(required=False, min_value=0, label='Idade Mínima', widget=forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Min.'}))
    idade_max = forms.IntegerField(required=False, min_value=0, label='Idade Máxima', widget=forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Máx.'}))


class AconselhamentoImportarForm(forms.Form):
    sheet_link = forms.URLField(
        required=False,
        label='Link da planilha',
        widget=forms.URLInput(attrs={'class': 'form-control', 'placeholder': 'https://docs.google.com/spreadsheets/d/...'}),
    )