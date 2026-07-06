from datetime import timedelta

from django.db import migrations
from django.utils import timezone


SEED_DATA = {
    'eventos': {
        'members': ['Ana Paula', 'Bruno Lima'],
        'tasks': [
            ('Fechar programação principal', 'Conferir horários e responsáveis das atividades.', 'pendente', 4, 0),
            ('Validar roteiro da abertura', 'Ajustar falas, entrada e transição musical.', 'andamento', 2, 0),
            ('Revisar cerimônia final', 'Confirmar participações e ordem dos momentos.', 'concluida', 1, 0),
        ],
    },
    'logistica': {
        'members': ['Carlos Nunes', 'Daniela Rocha'],
        'tasks': [
            ('Mapear transporte', 'Listar vans, horários e pontos de encontro.', 'pendente', 5, 0),
            ('Conferir check-in de materiais', 'Revisar chegada de caixas e equipamentos.', 'andamento', 3, 0),
            ('Organizar fluxo do refeitório', 'Ajustar filas e sinalização de acesso.', 'concluida', 1, 0),
        ],
    },
    'aconselhamento': {
        'members': ['Elisa Martins', 'Felipe Costa'],
        'tasks': [
            ('Montar escala de escuta', 'Distribuir horários de atendimento individual.', 'pendente', 4, 0),
            ('Preparar ambiente reservado', 'Separar local para aconselhamento e oração.', 'andamento', 2, 0),
            ('Atualizar lista de pedidos', 'Registrar solicitações recebidas no fim do dia.', 'concluida', 1, 0),
        ],
    },
    'programa': {
        'members': ['Gabriela Alves', 'Hugo Pereira'],
        'tasks': [
            ('Fechar cronograma diário', 'Revisar blocos de culto, atividades e intervalos.', 'pendente', 5, 0),
            ('Alinhar preletores', 'Confirmar disponibilidade e tempo de fala.', 'andamento', 2, 0),
            ('Publicar agenda do dia', 'Enviar versão final para comunicação.', 'concluida', 1, 0),
        ],
    },
    'lojinha_cantina': {
        'members': ['Ingrid Souza', 'João Mendes'],
        'tasks': [
            ('Repor itens mais vendidos', 'Garantir estoque de água, lanche e lembranças.', 'pendente', 3, 350),
            ('Fechar caixa parcial', 'Conferir vendas e troco do turno atual.', 'andamento', 1, 120),
            ('Conferir etiquetas de preço', 'Padronizar valores expostos nas prateleiras.', 'concluida', 2, 80),
        ],
    },
    'oracao': {
        'members': ['Karla Ferreira', 'Leandro Barros'],
        'tasks': [
            ('Montar escala de intercessão', 'Cobrir os turnos de oração durante o acampamento.', 'pendente', 4, 0),
            ('Recolher pedidos', 'Organizar pedidos enviados pelos participantes.', 'andamento', 2, 0),
            ('Ajustar sala de oração', 'Preparar ambiente para momentos de ministração.', 'concluida', 1, 0),
        ],
    },
    'comunicacao': {
        'members': ['Marina Azevedo', 'Nicolas Ribeiro'],
        'tasks': [
            ('Criar peças do evento', 'Preparar artes de aviso e divulgação interna.', 'pendente', 4, 0),
            ('Cobrir abertura', 'Registrar fotos e vídeos da primeira programação.', 'andamento', 1, 0),
            ('Publicar resumo diário', 'Enviar conteúdo para redes e grupo oficial.', 'concluida', 1, 0),
        ],
    },
    'administracao': {
        'members': ['Otávio Martins', 'Patrícia Dias'],
        'tasks': [
            ('Conferir cadastros', 'Validar presença e dados principais dos inscritos.', 'pendente', 5, 0),
            ('Organizar documentos', 'Separar autorizações e listas de apoio.', 'andamento', 2, 0),
            ('Salvar arquivos finais', 'Arquivar versões assinadas e relatórios.', 'concluida', 1, 0),
        ],
    },
    'financeiro': {
        'members': ['Rafaela Gomes', 'Samuel Vieira'],
        'tasks': [
            ('Fechar previsão orçamentária', 'Revisar entradas, saídas e saldo estimado.', 'pendente', 4, 1800),
            ('Registrar pagamentos', 'Atualizar despesas já confirmadas.', 'andamento', 2, 950),
            ('Conferir comprovantes', 'Separar recibos e anexos pendentes.', 'concluida', 1, 420),
        ],
    },
    'materiais': {
        'members': ['Tatiane Silva', 'Ulisses Rocha'],
        'tasks': [
            ('Inventariar caixa central', 'Checar lista de entrada e saída de equipamentos.', 'pendente', 4, 0),
            ('Separar kits por equipe', 'Montar entregas individuais para o início do evento.', 'andamento', 2, 0),
            ('Conferir devoluções', 'Validar o retorno de materiais após uso.', 'concluida', 1, 0),
        ],
    },
    'pessoal': {
        'members': ['Vera Lúcia', 'William Santos'],
        'tasks': [
            ('Montar escala geral', 'Distribuir voluntários por bloco de serviço.', 'pendente', 5, 0),
            ('Cobrir substituições', 'Ajustar ausências de última hora.', 'andamento', 2, 0),
            ('Atualizar lista de voluntários', 'Consolidar nomes confirmados por equipe.', 'concluida', 1, 0),
        ],
    },
}


def seed_dashboard(apps, schema_editor):
    Membro = apps.get_model('dashboard', 'Membro')
    Tarefa = apps.get_model('dashboard', 'Tarefa')

    today = timezone.localdate()

    for team_slug, payload in SEED_DATA.items():
        members = {}

        for member_name in payload['members']:
            member, _ = Membro.objects.get_or_create(
                nome=member_name,
                equipe=team_slug,
                defaults={'ativo': True},
            )
            members[member_name] = member

        for title, description, status, days_ahead, amount in payload['tasks']:
            responsible = members[payload['members'][0]] if payload['members'] else None
            Tarefa.objects.get_or_create(
                titulo=title,
                equipe=team_slug,
                defaults={
                    'descricao': description,
                    'responsavel': responsible,
                    'status': status,
                    'prazo': today + timedelta(days=days_ahead),
                    'valor_estimado': amount,
                },
            )


def unseed_dashboard(apps, schema_editor):
    Membro = apps.get_model('dashboard', 'Membro')
    Tarefa = apps.get_model('dashboard', 'Tarefa')

    for team_slug, payload in SEED_DATA.items():
        Tarefa.objects.filter(equipe=team_slug, titulo__in=[task[0] for task in payload['tasks']]).delete()
        Membro.objects.filter(equipe=team_slug, nome__in=payload['members']).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('dashboard', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(seed_dashboard, unseed_dashboard),
    ]