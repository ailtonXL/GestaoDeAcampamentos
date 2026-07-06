from django import forms

from .models import EquipeChoices, Membro, PreparoRegistro, StatusTarefaChoices, Tarefa


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
        label='Publicar atividade no Google Classroom',
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
    )
    google_course_id = forms.CharField(
        required=False,
        label='ID da turma no Google Classroom',
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