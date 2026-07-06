from django.contrib import admin

from .models import Membro, Tarefa


class TarefaInline(admin.TabularInline):
    model = Tarefa
    extra = 0
    fields = ('titulo', 'equipe', 'status', 'prazo', 'valor_estimado')
    show_change_link = True


@admin.register(Membro)
class MembroAdmin(admin.ModelAdmin):
    list_display = ('nome', 'equipe', 'ativo', 'criado_em')
    list_filter = ('equipe', 'ativo')
    search_fields = ('nome',)
    list_select_related = ()
    date_hierarchy = 'criado_em'
    ordering = ('nome',)
    inlines = (TarefaInline,)


@admin.register(Tarefa)
class TarefaAdmin(admin.ModelAdmin):
    list_display = ('titulo', 'equipe', 'status', 'responsavel', 'prazo', 'valor_estimado')
    list_filter = ('equipe', 'status')
    search_fields = ('titulo', 'descricao', 'responsavel__nome')
    autocomplete_fields = ('responsavel',)
    date_hierarchy = 'prazo'
    ordering = ('status', 'prazo', 'titulo')
    list_select_related = ('responsavel',)
