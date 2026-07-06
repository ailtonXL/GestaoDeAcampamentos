import json
from pathlib import Path
from urllib import error as urllib_error
from urllib import request as urllib_request

from decimal import Decimal

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from accounts.models import User
from .forms import MembroForm, MembroQuickForm, PreparoForm, TaskForm
from .models import (
    ClassroomStatusChoices,
    EquipeChoices,
    Membro,
    PreparoRegistro,
    StatusTarefaChoices,
    SyncStatusChoices,
    Tarefa,
)


TEAM_META = {
    'eventos': {'title': 'Eventos', 'subtitle': 'Programação, cerimônias e agenda geral.'},
    'logistica': {'title': 'Logística', 'subtitle': 'Fluxo, transporte e suporte operacional.'},
    'aconselhamento': {'title': 'Aconselhamento', 'subtitle': 'Acompanhamento pastoral e cuidado.'},
    'programa': {'title': 'Programa', 'subtitle': 'Conteúdo, horários e condução das atividades.'},
    'lojinha_cantina': {'title': 'Lojinha e Cantina', 'subtitle': 'Vendas, reposição e atendimento.'},
    'oracao': {'title': 'Oração', 'subtitle': 'Intercessão, escala e pedidos de oração.'},
    'comunicacao': {'title': 'Comunicação', 'subtitle': 'Avisos, mídia e cobertura do acampamento.'},
    'administracao': {'title': 'Administração', 'subtitle': 'Controle, cadastros e documentação.'},
    'financeiro': {'title': 'Financeiro', 'subtitle': 'Saldo, despesas e previsões.'},
    'materiais': {'title': 'Materiais', 'subtitle': 'Inventário, entregas e reposição.'},
    'pessoal': {'title': 'Pessoal', 'subtitle': 'Escalas, membros e distribuição de funções.'},
}

TEAM_ORDER = list(TEAM_META.keys())
ALL_TEAMS = set(TEAM_META.keys())
RESTRICTED_TEAMS = {'financeiro', 'administracao'}

ROLE_TEAM_ACCESS = {
    User.Role.CHEFIA_LOGISTICA: {'logistica'},
    User.Role.CHEFIA_EVENTOS: {'eventos'},
    User.Role.CHEFIA_ORACAO: {'oracao'},
    User.Role.CHEFIA_PROGRAMA: {'programa'},
    User.Role.CHEFIA_ACONSELHAMENTO: {'aconselhamento'},
    User.Role.CHEFIA_COMUNICACAO: {'comunicacao'},
    User.Role.CHEFIA_LOJINHA_CANTINA: {'lojinha_cantina'},
    User.Role.ADMINISTRACAO: {'financeiro', 'administracao'},
    User.Role.CHEFE_PESSOAL: {'pessoal'},
    User.Role.CHEFE_MATERIAIS: {'materiais'},
    User.Role.CHEFE_EQUIPE: ALL_TEAMS - RESTRICTED_TEAMS,
    User.Role.TRIPE: ALL_TEAMS - RESTRICTED_TEAMS,
    User.Role.NOBREAK: ALL_TEAMS,
}

GOOGLE_CLASSROOM_SCOPES = [
    'https://www.googleapis.com/auth/classroom.courses.readonly',
    'https://www.googleapis.com/auth/classroom.coursework.students',
]

GOOGLE_CREDENTIALS_SESSION_KEY = 'google_classroom_credentials'
GOOGLE_OAUTH_STATE_SESSION_KEY = 'google_classroom_oauth_state'


def _team_label(team_slug):
    return TEAM_META.get(team_slug, {}).get('title', team_slug.replace('_', ' ').title())


def _currency(value):
    value = Decimal(value or 0)
    return f'R$ {value:,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.')


def _team_snapshot(team_slug):
    tarefas = Tarefa.objects.filter(equipe=team_slug)
    membros = Membro.objects.filter(equipe=team_slug, ativo=True)
    return {
        'slug': team_slug,
        'title': _team_label(team_slug),
        'subtitle': TEAM_META.get(team_slug, {}).get('subtitle', ''),
        'total_tasks': tarefas.count(),
        'pending_tasks': tarefas.filter(status=StatusTarefaChoices.PENDENTE).count(),
        'in_progress_tasks': tarefas.filter(status=StatusTarefaChoices.ANDAMENTO).count(),
        'completed_tasks': tarefas.filter(status=StatusTarefaChoices.CONCLUIDA).count(),
        'members_count': membros.count(),
        'finance_total': tarefas.aggregate(total=models.Sum('valor_estimado'))['total'] or Decimal('0'),
    }


# Model import local to keep the query helpers compact.
from django.db import models  # noqa: E402


def _allowed_teams_for_user(user):
    if not user.is_authenticated:
        return set()
    if user.is_superuser:
        return set(ALL_TEAMS)
    return set(ROLE_TEAM_ACCESS.get(user.role, set()))


def _can_access_team(user, team_slug):
    return team_slug in _allowed_teams_for_user(user)


def _can_manage_membership(user):
    if not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    return user.role in {User.Role.TRIPE, User.Role.NOBREAK}


def _can_view_members_index(user):
    return _can_manage_membership(user)


def _can_access_preparo(user):
    if not getattr(settings, 'FEATURE_PREPARO_ENABLED', False):
        return False
    if not user.is_authenticated:
        return False
    return user.role == User.Role.NOBREAK


def _deny_access(team_slug):
    return HttpResponseForbidden(f'Voce nao tem permissao para acessar a area: {team_slug}.')


def _get_formspree_endpoint():
    return str(getattr(settings, 'FORMSPREE_PREPARO_ENDPOINT', '')).strip()


def _google_client_secrets_path():
    raw_path = str(getattr(settings, 'GOOGLE_CLASSROOM_CLIENT_SECRETS_FILE', '')).strip()
    if raw_path:
        return Path(raw_path)
    return settings.BASE_DIR / 'google_client_secret.json'


def _load_google_modules():
    try:
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import Flow
        from googleapiclient.discovery import build
    except ImportError:
        return None, None, None
    return Credentials, Flow, build


def _get_google_credentials_from_session(request):
    credentials_json = request.session.get(GOOGLE_CREDENTIALS_SESSION_KEY)
    if not credentials_json:
        return None

    Credentials, _, _ = _load_google_modules()
    if Credentials is None:
        return None

    try:
        credentials = Credentials.from_authorized_user_info(json.loads(credentials_json), GOOGLE_CLASSROOM_SCOPES)
    except Exception:
        request.session.pop(GOOGLE_CREDENTIALS_SESSION_KEY, None)
        return None

    if credentials.expired and credentials.refresh_token:
        try:
            from google.auth.transport.requests import Request as GoogleRequest

            credentials.refresh(GoogleRequest())
            request.session[GOOGLE_CREDENTIALS_SESSION_KEY] = credentials.to_json()
        except Exception:
            request.session.pop(GOOGLE_CREDENTIALS_SESSION_KEY, None)
            return None

    return credentials


def _list_google_courses(credentials):
    _, _, build = _load_google_modules()
    if build is None:
        return []

    try:
        service = build('classroom', 'v1', credentials=credentials)
        result = service.courses().list(pageSize=50, courseStates=['ACTIVE']).execute()
        courses = result.get('courses', [])
    except Exception:
        return []

    return [
        {
            'id': course.get('id', ''),
            'name': course.get('name', ''),
            'section': course.get('section', ''),
        }
        for course in courses
        if course.get('id')
    ]


def _sync_to_formspree(registro):
    endpoint = _get_formspree_endpoint()
    if not endpoint:
        return SyncStatusChoices.NAO_CONFIGURADO, 'FORMSPREE_PREPARO_ENDPOINT nao configurado.'

    payload = {
        'nome_completo': registro.nome_completo,
        'email': registro.email,
        'telefone': registro.telefone,
        'titulo_atividade': registro.titulo_atividade,
        'descricao_atividade': registro.descricao_atividade,
        'prazo_entrega': str(registro.prazo_entrega or ''),
        'criado_em': registro.criado_em.isoformat(),
    }

    try:
        req = urllib_request.Request(
            endpoint,
            data=json.dumps(payload).encode('utf-8'),
            headers={'Content-Type': 'application/json', 'Accept': 'application/json'},
            method='POST',
        )
        with urllib_request.urlopen(req, timeout=12) as response:
            body = response.read().decode('utf-8', errors='ignore')
            if 200 <= response.status < 300:
                return SyncStatusChoices.SUCESSO, body[:1500]
            return SyncStatusChoices.FALHA, f'Status {response.status}: {body[:1500]}'
    except urllib_error.HTTPError as exc:
        body = exc.read().decode('utf-8', errors='ignore')
        return SyncStatusChoices.FALHA, f'HTTP {exc.code}: {body[:1500]}'
    except Exception as exc:
        return SyncStatusChoices.FALHA, str(exc)


def _publish_to_google_classroom(credentials, *, course_id, registro):
    _, _, build = _load_google_modules()
    if build is None:
        return ClassroomStatusChoices.FALHA, '', 'Dependencias do Google Classroom nao instaladas.'

    body = {
        'title': registro.titulo_atividade,
        'description': registro.descricao_atividade,
        'workType': 'ASSIGNMENT',
        'state': 'PUBLISHED',
    }

    if registro.prazo_entrega:
        body['dueDate'] = {
            'year': registro.prazo_entrega.year,
            'month': registro.prazo_entrega.month,
            'day': registro.prazo_entrega.day,
        }

    try:
        service = build('classroom', 'v1', credentials=credentials)
        created = service.courses().courseWork().create(courseId=course_id, body=body).execute()
        return ClassroomStatusChoices.SUCESSO, created.get('id', ''), json.dumps(created)[:1500]
    except Exception as exc:
        return ClassroomStatusChoices.FALHA, '', str(exc)


@login_required
def index(request):
    allowed_teams = _allowed_teams_for_user(request.user)
    visible_teams = [team_slug for team_slug in TEAM_ORDER if team_slug in allowed_teams]
    if not visible_teams:
        return HttpResponseForbidden('Voce nao possui areas liberadas para acesso.')

    snapshots = [_team_snapshot(team_slug) for team_slug in visible_teams]
    total_pending = sum(item['pending_tasks'] for item in snapshots)
    total_progress = sum(item['in_progress_tasks'] for item in snapshots)
    total_done = sum(item['completed_tasks'] for item in snapshots)
    total_members = Membro.objects.filter(ativo=True).count()
    financeiro_snapshot = next((item for item in snapshots if item['slug'] == 'financeiro'), None)

    cards = []
    for item in snapshots:
        if item['slug'] == 'financeiro':
            value = _currency(item['finance_total'])
            subtitle = 'Saldo estimado'
        else:
            value = str(item['pending_tasks'])
            subtitle = 'pendências'
        cards.append({
            'title': item['title'],
            'value': value,
            'subtitle': subtitle,
            'description': item['subtitle'],
            'url_name': item['slug'],
        })

    return render(request, 'dashboard/index.html', {
        'page_title': 'Visão Geral',
        'active_page': 'dashboard',
        'cards': cards,
        'total_pending': total_pending,
        'total_progress': total_progress,
        'total_done': total_done,
        'total_members': total_members,
        'finance_total': _currency(financeiro_snapshot['finance_total']) if financeiro_snapshot else _currency(0),
        'chart_labels': ['Pendentes', 'Em andamento', 'Concluídas'],
        'chart_values': [total_pending, total_progress, total_done],
        'can_view_members_index': _can_view_members_index(request.user),
    })


def _member_queryset(request):
    allowed_teams = _allowed_teams_for_user(request.user)
    members = Membro.objects.filter(equipe__in=allowed_teams).order_by('nome')
    search_query = request.GET.get('q', '').strip()
    selected_team = request.GET.get('equipe', '').strip()

    if search_query:
        members = members.filter(nome__icontains=search_query)
    if selected_team in allowed_teams:
        members = members.filter(equipe=selected_team)

    return members, search_query, selected_team


@login_required
def member_list(request):
    if not _can_view_members_index(request.user):
        return HttpResponseForbidden('Voce nao tem permissao para acessar a aba geral de membros.')

    members, search_query, selected_team = _member_queryset(request)
    allowed_teams = _allowed_teams_for_user(request.user)
    team_choices = [choice for choice in EquipeChoices.choices if choice[0] in allowed_teams]
    return render(request, 'dashboard/member_list.html', {
        'page_title': 'Membros',
        'active_page': 'membros',
        'members': members,
        'team_choices': team_choices,
        'search_query': search_query,
        'selected_team': selected_team,
        'total_members': members.count(),
        'active_members': members.filter(ativo=True).count(),
        'inactive_members': members.filter(ativo=False).count(),
        'can_manage_membership': _can_manage_membership(request.user),
    })


def _member_form_context(form, *, page_title, page_subtitle, cancel_url, submit_label, active_page='membros'):
    return {
        'page_title': page_title,
        'active_page': active_page,
        'form': form,
        'page_subtitle': page_subtitle,
        'cancel_url': cancel_url,
        'submit_label': submit_label,
    }


def _task_form_context(form, *, page_title, page_subtitle, cancel_url, submit_label, active_page):
    return {
        'page_title': page_title,
        'active_page': active_page,
        'form': form,
        'page_subtitle': page_subtitle,
        'cancel_url': cancel_url,
        'submit_label': submit_label,
    }


@login_required
def member_create(request):
    if not _can_manage_membership(request.user):
        return HttpResponseForbidden('Somente TRIPÉ ou NoBreak pode adicionar novos membros.')

    allowed_teams = _allowed_teams_for_user(request.user)
    if not allowed_teams:
        return HttpResponseForbidden('Voce nao tem permissao para cadastrar membros.')

    if request.method == 'POST':
        form = MembroForm(request.POST)
        form.fields['equipe'].choices = [choice for choice in EquipeChoices.choices if choice[0] in allowed_teams]
        if form.is_valid():
            form.save()
            return redirect('membros')
    else:
        initial_data = {'ativo': True}
        if len(allowed_teams) == 1:
            initial_data['equipe'] = next(iter(allowed_teams))
        form = MembroForm(initial=initial_data)
        form.fields['equipe'].choices = [choice for choice in EquipeChoices.choices if choice[0] in allowed_teams]

    return render(request, 'dashboard/member_form.html', _member_form_context(
        form,
        page_title='Novo membro',
        page_subtitle='Cadastre uma pessoa e escolha o setor responsável.',
        cancel_url=reverse('membros'),
        submit_label='Salvar membro',
    ))


@login_required
def member_update(request, pk):
    member = get_object_or_404(Membro, pk=pk)
    allowed_teams = _allowed_teams_for_user(request.user)
    if member.equipe not in allowed_teams:
        return _deny_access(member.equipe)

    if request.method == 'POST':
        requested_team = request.POST.get('equipe')
        if requested_team and requested_team != member.equipe and not _can_manage_membership(request.user):
            return HttpResponseForbidden('Somente TRIPÉ ou NoBreak pode trocar membros de equipe.')
        form = MembroForm(request.POST, instance=member)
        form.fields['equipe'].choices = [choice for choice in EquipeChoices.choices if choice[0] in allowed_teams]
        if not _can_manage_membership(request.user):
            form.fields['equipe'].disabled = True
        if form.is_valid():
            form.save()
            return redirect('membros')
    else:
        form = MembroForm(instance=member)
        form.fields['equipe'].choices = [choice for choice in EquipeChoices.choices if choice[0] in allowed_teams]
        if not _can_manage_membership(request.user):
            form.fields['equipe'].disabled = True

    return render(request, 'dashboard/member_form.html', _member_form_context(
        form,
        page_title='Editar membro',
        page_subtitle='Altere o nome, o setor ou o status da pessoa.',
        cancel_url=reverse('membros'),
        submit_label='Atualizar membro',
    ))


@login_required
def member_delete(request, pk):
    member = get_object_or_404(Membro, pk=pk)
    if not _can_manage_membership(request.user):
        return HttpResponseForbidden('Somente TRIPÉ ou NoBreak pode excluir membros.')
    if not _can_access_team(request.user, member.equipe):
        return _deny_access(member.equipe)

    if request.method == 'POST':
        redirect_url = reverse('membros')
        if request.POST.get('next') in TEAM_META:
            redirect_url = reverse(request.POST.get('next'))
        member.delete()
        return redirect(redirect_url)

    return render(request, 'dashboard/member_delete.html', {
        'page_title': 'Excluir membro',
        'active_page': 'membros',
        'member': member,
        'cancel_url': reverse('membro_update', args=[member.pk]),
    })


@login_required
def team_member_create(request, team_slug):
    if team_slug not in TEAM_META:
        team_slug = 'eventos'
    if not _can_manage_membership(request.user):
        return HttpResponseForbidden('Somente TRIPÉ ou NoBreak pode adicionar novos membros.')
    if not _can_access_team(request.user, team_slug):
        return _deny_access(team_slug)

    if request.method == 'POST':
        form = MembroQuickForm(request.POST)
        if form.is_valid():
            member = form.save(commit=False)
            member.equipe = team_slug
            member.save()
            return redirect(reverse(team_slug))
    else:
        form = MembroQuickForm(initial={'ativo': True})

    return render(request, 'dashboard/member_form.html', _member_form_context(
        form,
        page_title=f'Adicionar membro em {_team_label(team_slug)}',
        page_subtitle='Inclua rapidamente alguém neste setor.',
        cancel_url=reverse(team_slug),
        submit_label='Salvar pessoa',
        active_page=team_slug,
    ))


@login_required
def task_create(request, team_slug):
    if team_slug not in TEAM_META:
        team_slug = 'eventos'
    if not _can_access_team(request.user, team_slug):
        return _deny_access(team_slug)

    if request.method == 'POST':
        form = TaskForm(request.POST, team_slug=team_slug)
        if form.is_valid():
            task = form.save(commit=False)
            task.equipe = team_slug
            task.save()
            return redirect(reverse(team_slug))
    else:
        form = TaskForm(team_slug=team_slug, initial={'status': StatusTarefaChoices.PENDENTE, 'valor_estimado': 0})

    return render(request, 'dashboard/task_form.html', _task_form_context(
        form,
        page_title=f'Nova tarefa em {_team_label(team_slug)}',
        page_subtitle='Cadastre uma tarefa e acompanhe a execucao da equipe.',
        cancel_url=reverse(team_slug),
        submit_label='Salvar tarefa',
        active_page=team_slug,
    ))


@login_required
def task_update(request, pk):
    task = get_object_or_404(Tarefa, pk=pk)
    team_slug = task.equipe if task.equipe in TEAM_META else 'eventos'
    if not _can_access_team(request.user, team_slug):
        return _deny_access(team_slug)

    if request.method == 'POST':
        form = TaskForm(request.POST, instance=task, team_slug=team_slug)
        if form.is_valid():
            form.save()
            return redirect(reverse(team_slug))
    else:
        form = TaskForm(instance=task, team_slug=team_slug)

    return render(request, 'dashboard/task_form.html', _task_form_context(
        form,
        page_title='Editar tarefa',
        page_subtitle='Atualize status, prazo, responsavel e demais informacoes.',
        cancel_url=reverse(team_slug),
        submit_label='Atualizar tarefa',
        active_page=team_slug,
    ))


@login_required
def task_delete(request, pk):
    task = get_object_or_404(Tarefa, pk=pk)
    team_slug = task.equipe if task.equipe in TEAM_META else 'eventos'
    if not _can_access_team(request.user, team_slug):
        return _deny_access(team_slug)

    if request.method == 'POST':
        task.delete()
        return redirect(reverse(team_slug))

    return render(request, 'dashboard/task_delete.html', {
        'page_title': 'Excluir tarefa',
        'active_page': team_slug,
        'task': task,
        'cancel_url': reverse(team_slug),
    })


@login_required
def team_page(request, team_slug):
    if team_slug not in TEAM_META:
        team_slug = 'eventos'
    if not _can_access_team(request.user, team_slug):
        return _deny_access(team_slug)

    meta = TEAM_META[team_slug]
    tarefas = Tarefa.objects.filter(equipe=team_slug).select_related('responsavel')
    membros = Membro.objects.filter(equipe=team_slug, ativo=True)
    member_form = MembroQuickForm(initial={'ativo': True})

    template_name = 'dashboard/eventos.html' if team_slug == 'eventos' else 'dashboard/team_page.html'
    return render(request, template_name, {
        'page_title': meta['title'],
        'active_page': team_slug,
        'team_slug': team_slug,
        'team_title': meta['title'],
        'team_subtitle': meta['subtitle'],
        'members': membros,
        'can_view_members_index': _can_view_members_index(request.user),
        'can_manage_membership': _can_manage_membership(request.user),
        'member_form': member_form,
        'member_create_url': reverse('team_member_create', kwargs={'team_slug': team_slug}),
        'member_delete_url_name': 'membro_delete',
        'members_index_url': reverse('membros'),
        'task_create_url': reverse('task_create', kwargs={'team_slug': team_slug}),
        'task_update_url_name': 'task_update',
        'task_delete_url_name': 'task_delete',
        'tasks': tarefas,
        'task_total': tarefas.count(),
        'task_pending': tarefas.filter(status=StatusTarefaChoices.PENDENTE).count(),
        'task_done': tarefas.filter(status=StatusTarefaChoices.CONCLUIDA).count(),
    })


@login_required
def preparo_page(request):
    if not _can_access_preparo(request.user):
        return HttpResponseForbidden('Somente usuarios NoBreak podem acessar a aba Preparo.')

    credentials = _get_google_credentials_from_session(request)
    google_courses = _list_google_courses(credentials) if credentials else []

    if request.method == 'POST':
        form = PreparoForm(request.POST)
        if form.is_valid():
            registro = form.save(commit=False)
            registro.criado_por = request.user
            registro.save()

            external_status, external_response = _sync_to_formspree(registro)
            registro.external_sync_status = external_status
            registro.external_sync_response = external_response

            publicar_no_classroom = form.cleaned_data.get('publicar_no_classroom')
            google_course_id = (form.cleaned_data.get('google_course_id') or '').strip()
            if publicar_no_classroom:
                if not credentials:
                    registro.classroom_status = ClassroomStatusChoices.FALHA
                    registro.classroom_response = 'Conecte sua conta Google Classroom antes de publicar.'
                elif not google_course_id:
                    registro.classroom_status = ClassroomStatusChoices.FALHA
                    registro.classroom_response = 'Informe o ID da turma para publicar a atividade.'
                else:
                    status, coursework_id, classroom_response = _publish_to_google_classroom(
                        credentials,
                        course_id=google_course_id,
                        registro=registro,
                    )
                    registro.classroom_status = status
                    registro.classroom_coursework_id = coursework_id
                    registro.classroom_course_id = google_course_id
                    registro.classroom_response = classroom_response

            registro.save(update_fields=[
                'external_sync_status',
                'external_sync_response',
                'classroom_status',
                'classroom_course_id',
                'classroom_coursework_id',
                'classroom_response',
            ])

            if registro.classroom_status == ClassroomStatusChoices.SUCESSO:
                messages.success(request, 'Registro salvo, enviado para API externa e publicado no Google Classroom.')
            elif registro.classroom_status == ClassroomStatusChoices.FALHA:
                messages.warning(request, 'Registro salvo, mas houve falha ao publicar no Google Classroom.')
            elif registro.external_sync_status == SyncStatusChoices.FALHA:
                messages.warning(request, 'Registro salvo no banco, mas houve falha na API externa.')
            else:
                messages.success(request, 'Registro de preparo salvo com sucesso.')

            return redirect('preparo')
    else:
        form = PreparoForm()

    registros = PreparoRegistro.objects.select_related('criado_por')[:20]
    return render(request, 'dashboard/preparo.html', {
        'page_title': 'Preparo',
        'active_page': 'preparo',
        'form': form,
        'google_connected': credentials is not None,
        'google_courses': google_courses,
        'registros': registros,
        'formspree_endpoint_configured': bool(_get_formspree_endpoint()),
    })


@login_required
def preparo_google_connect(request):
    if not _can_access_preparo(request.user):
        return HttpResponseForbidden('Somente usuarios NoBreak podem acessar a integracao Google Classroom.')

    _, Flow, _ = _load_google_modules()
    if Flow is None:
        messages.error(request, 'Dependencias do Google Classroom nao instaladas no projeto.')
        return redirect('preparo')

    secrets_path = _google_client_secrets_path()
    if not secrets_path.exists():
        messages.error(request, 'Arquivo de credenciais Google nao encontrado para iniciar o login OAuth.')
        return redirect('preparo')

    flow = Flow.from_client_secrets_file(
        str(secrets_path),
        scopes=GOOGLE_CLASSROOM_SCOPES,
        redirect_uri=request.build_absolute_uri(reverse('preparo_google_callback')),
    )
    authorization_url, state = flow.authorization_url(
        access_type='offline',
        include_granted_scopes='true',
        prompt='consent',
    )
    request.session[GOOGLE_OAUTH_STATE_SESSION_KEY] = state
    return redirect(authorization_url)


@login_required
def preparo_google_callback(request):
    if not _can_access_preparo(request.user):
        return HttpResponseForbidden('Somente usuarios NoBreak podem acessar a integracao Google Classroom.')

    _, Flow, _ = _load_google_modules()
    if Flow is None:
        messages.error(request, 'Dependencias do Google Classroom nao instaladas no projeto.')
        return redirect('preparo')

    expected_state = request.session.get(GOOGLE_OAUTH_STATE_SESSION_KEY)
    current_state = request.GET.get('state')
    if not expected_state or expected_state != current_state:
        messages.error(request, 'Falha ao validar o estado do login OAuth do Google Classroom.')
        return redirect('preparo')

    secrets_path = _google_client_secrets_path()
    if not secrets_path.exists():
        messages.error(request, 'Arquivo de credenciais Google nao encontrado para concluir o login OAuth.')
        return redirect('preparo')

    flow = Flow.from_client_secrets_file(
        str(secrets_path),
        scopes=GOOGLE_CLASSROOM_SCOPES,
        state=expected_state,
        redirect_uri=request.build_absolute_uri(reverse('preparo_google_callback')),
    )

    try:
        flow.fetch_token(authorization_response=request.build_absolute_uri())
    except Exception:
        messages.error(request, 'Nao foi possivel concluir o login com Google Classroom.')
        return redirect('preparo')

    request.session[GOOGLE_CREDENTIALS_SESSION_KEY] = flow.credentials.to_json()
    request.session.pop(GOOGLE_OAUTH_STATE_SESSION_KEY, None)
    messages.success(request, 'Google Classroom conectado com sucesso.')
    return redirect('preparo')


@login_required
def preparo_google_disconnect(request):
    if not _can_access_preparo(request.user):
        return HttpResponseForbidden('Somente usuarios NoBreak podem acessar a integracao Google Classroom.')

    request.session.pop(GOOGLE_CREDENTIALS_SESSION_KEY, None)
    request.session.pop(GOOGLE_OAUTH_STATE_SESSION_KEY, None)
    messages.info(request, 'Conexao com Google Classroom removida desta sessao.')
    return redirect('preparo')
