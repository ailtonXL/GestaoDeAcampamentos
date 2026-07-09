import json
import csv
import hashlib
import io
import uuid
import unicodedata
from pathlib import Path
from urllib import error as urllib_error
from urllib import request as urllib_request
from urllib.parse import parse_qs, urlparse

from decimal import Decimal

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.db import transaction

from accounts.models import User
from .forms import AconselhamentoFiltroForm, AconselhamentoImportarForm, AconselhamentoSalaForm, DocumentoImportanteForm, InventoryAdjustForm, MembroForm, MembroImportForm, MembroQuickForm, PreOrderForm, PreOrderPaymentForm, PreOrderSearchForm, PreparoForm, SaleForm, SheetImportForm, TaskForm
from .models import (
    ClassroomStatusChoices,
    AconselhamentoCampista,
    AconselhamentoCampistaSexoChoices,
    AconselhamentoConfig,
    AconselhamentoHistorico,
    AconselhamentoSala,
    AconselhamentoSalaCaracteristicaChoices,
    DocumentoImportante,
    InventorySku,
    EquipeChoices,
    Membro,
    MembroSheetConfig,
    PaymentMethodChoices,
    PreOrderRecord,
    PreOrderPaymentStatusChoices,
    PreOrderSheetConfig,
    PreOrderSourceChoices,
    PreOrderStatusChoices,
    PreparoRegistro,
    ProductColorChoices,
    ProductSizeChoices,
    SaleRecord,
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
GOOGLE_SHEETS_CREDENTIALS_FILE = 'GOOGLE_SHEETS_SERVICE_ACCOUNT_FILE'
GOOGLE_SHEETS_SPREADSHEET_ID = 'GOOGLE_SHEETS_SPREADSHEET_ID'
GOOGLE_SHEETS_RANGE_NAME = 'GOOGLE_SHEETS_RANGE_NAME'
DEFAULT_PRODUCT_NAME = 'Camiseta'
PIX_CASH_VALUE = Decimal('65.00')
CARD_VALUE = Decimal('70.00')


def _commercial_allowed(user):
    if not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    return user.role in {User.Role.ADMINISTRACAO, User.Role.NOBREAK, User.Role.CHEFIA_LOJINHA_CANTINA}


def _ensure_inventory_grid():
    for color, _ in ProductColorChoices.choices:
        for size, _ in ProductSizeChoices.choices:
            InventorySku.objects.get_or_create(color=color, size=size, defaults={'initial_quantity': 0})


def _inventory_matrix():
    _ensure_inventory_grid()
    matrix = []
    for color, color_label in ProductColorChoices.choices:
        row = {'color': color, 'label': color_label, 'sizes': []}
        for size, size_label in ProductSizeChoices.choices:
            sku = InventorySku.objects.get(color=color, size=size)
            row['sizes'].append({
                'size': size,
                'label': size_label,
                'initial': sku.initial_quantity,
                'sold': sku.sold_quantity,
                'reserved': sku.reserved_quantity,
                'balance': sku.balance_quantity,
            })
        matrix.append(row)
    return matrix


def _commercial_totals():
    total_pix_cash = SaleRecord.objects.filter(payment_method=PaymentMethodChoices.PIX_CASH).aggregate(total=models.Sum('total_value'))['total'] or Decimal('0')
    total_card = SaleRecord.objects.filter(payment_method=PaymentMethodChoices.CARD).aggregate(total=models.Sum('total_value'))['total'] or Decimal('0')
    total_sales = SaleRecord.objects.aggregate(total=models.Sum('total_value'))['total'] or Decimal('0')
    total_preorders = PreOrderRecord.objects.aggregate(total=models.Sum('quantity'))['total'] or 0
    preorder_estimate = Decimal(total_preorders) * PIX_CASH_VALUE
    return total_pix_cash, total_card, total_sales, preorder_estimate


def _inventory_evolution_series():
    sales = [
        {'timestamp': item['created_at'], 'delta': -int(item['quantity'])}
        for item in SaleRecord.objects.order_by('created_at').values('created_at', 'quantity')
    ]
    preorders = [
        {'timestamp': item['created_at'], 'delta': int(item['quantity'])}
        for item in PreOrderRecord.objects.order_by('created_at').values('created_at', 'quantity')
    ]
    movements = sorted(sales + preorders, key=lambda item: item['timestamp'])
    points = []
    balance = 0
    for movement in movements:
        balance += movement['delta']
        points.append({'label': movement['timestamp'].date().isoformat(), 'value': balance})
    return points[-30:]


def _sheet_service():
    creds_file = str(getattr(settings, GOOGLE_SHEETS_CREDENTIALS_FILE, '')).strip()
    spreadsheet_id = str(getattr(settings, GOOGLE_SHEETS_SPREADSHEET_ID, '')).strip()
    if not creds_file or not spreadsheet_id:
        return None, None
    try:
        from google.oauth2.service_account import Credentials as ServiceAccountCredentials
        from googleapiclient.discovery import build
    except ImportError:
        return None, None
    credentials = ServiceAccountCredentials.from_service_account_file(
        creds_file,
        scopes=['https://www.googleapis.com/auth/spreadsheets'],
    )
    return build('sheets', 'v4', credentials=credentials), spreadsheet_id


def _get_saved_preorder_sheet_link():
    return (
        PreOrderSheetConfig.objects.filter(pk=1).values_list('sheet_link', flat=True).first() or ''
    ).strip()


def _save_preorder_sheet_link(sheet_link):
    sheet_link = str(sheet_link or '').strip()
    config, _ = PreOrderSheetConfig.objects.get_or_create(pk=1)
    if config.sheet_link != sheet_link:
        config.sheet_link = sheet_link
        config.save(update_fields=['sheet_link', 'updated_at'])
    return config


def _extract_sheet_link_parts(sheet_link):
    parsed_url = urlparse(str(sheet_link or '').strip())
    path_parts = [part for part in parsed_url.path.split('/') if part]
    spreadsheet_id = ''
    if 'd' in path_parts:
        try:
            spreadsheet_id = path_parts[path_parts.index('d') + 1]
        except IndexError:
            spreadsheet_id = ''
    sheet_gid = parse_qs(parsed_url.fragment).get('gid', [''])[0] or parse_qs(parsed_url.query).get('gid', [''])[0]
    return spreadsheet_id, sheet_gid


def _fetch_sheet_rows_via_csv(sheet_link):
    spreadsheet_id, sheet_gid = _extract_sheet_link_parts(sheet_link)
    if not spreadsheet_id:
        return []
    csv_urls = []
    if sheet_gid:
        csv_urls.append(f'https://docs.google.com/spreadsheets/d/{spreadsheet_id}/export?format=csv&gid={sheet_gid}')
        csv_urls.append(f'https://docs.google.com/spreadsheets/d/{spreadsheet_id}/gviz/tq?tqx=out:csv&gid={sheet_gid}')
    csv_urls.append(f'https://docs.google.com/spreadsheets/d/{spreadsheet_id}/export?format=csv')
    csv_urls.append(f'https://docs.google.com/spreadsheets/d/{spreadsheet_id}/gviz/tq?tqx=out:csv')

    last_error = None
    for url in csv_urls:
        try:
            with urllib_request.urlopen(url, timeout=20) as response:
                content = response.read().decode('utf-8-sig')
            reader = csv.reader(io.StringIO(content))
            return [row for row in reader if any(str(cell).strip() for cell in row)]
        except Exception as exc:
            last_error = exc
    return []


def _append_preorder_to_sheet(preorder):
    service, spreadsheet_id = _sheet_service()
    if not service or not spreadsheet_id:
        return False, 'Planilha Google nao configurada.'
    range_name = str(getattr(settings, GOOGLE_SHEETS_RANGE_NAME, 'Preorders!A:G')).strip() or 'Preorders!A:G'
    values = [[
        preorder.external_key,
        preorder.volunteer_name,
        preorder.color,
        preorder.size,
        preorder.quantity,
        preorder.created_at.isoformat(),
        preorder.status,
    ]]
    try:
        service.spreadsheets().values().append(
            spreadsheetId=spreadsheet_id,
            range=range_name,
            valueInputOption='USER_ENTERED',
            insertDataOption='INSERT_ROWS',
            body={'values': values},
        ).execute()
        return True, 'ok'
    except Exception as exc:
        return False, str(exc)


def _read_preorders_from_sheet(sheet_tab=''):
    rows = _fetch_sheet_rows_via_csv(sheet_tab)
    if not rows:
        service, default_spreadsheet_id = _sheet_service()
        if not service or not default_spreadsheet_id:
            return []

        spreadsheet_id = default_spreadsheet_id
        sheet_name = ''
        if sheet_tab:
            spreadsheet_id, sheet_gid = _extract_sheet_link_parts(sheet_tab)
            if not spreadsheet_id:
                spreadsheet_id = default_spreadsheet_id
            try:
                metadata = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
                sheets = metadata.get('sheets', [])
                if sheet_gid:
                    for sheet in sheets:
                        if str(sheet.get('properties', {}).get('sheetId')) == sheet_gid:
                            sheet_name = sheet.get('properties', {}).get('title', '')
                            break
                if not sheet_name and sheets:
                    sheet_name = sheets[0].get('properties', {}).get('title', '')
            except Exception:
                sheet_name = ''

        base_range = f'{sheet_name}!A:G' if sheet_name else str(getattr(settings, GOOGLE_SHEETS_RANGE_NAME, 'Preorders!A:G')).strip() or 'Preorders!A:G'
        try:
            result = service.spreadsheets().values().get(spreadsheetId=spreadsheet_id, range=base_range).execute()
            rows = result.get('values', [])
        except Exception:
            return []

    def normalize_header(value):
        normalized = unicodedata.normalize('NFKD', str(value or '').strip()).encode('ascii', 'ignore').decode('ascii')
        return normalized.lower().replace(' ', '_').replace('-', '_')

    def pick_value(mapping, row, *candidates, default=''):
        for candidate in candidates:
            if candidate in mapping:
                idx = mapping[candidate]
                if idx < len(row) and row[idx] not in (None, ''):
                    return row[idx]
        return default

    def normalize_choice(value, choices):
        text = str(value or '').strip().lower()
        for choice_value, choice_label in choices:
            if text == str(choice_value).strip().lower() or text == str(choice_label).strip().lower():
                return choice_value
        return text

    header_map = {normalize_header(value): index for index, value in enumerate(rows[0])}
    name_candidates = (
        'nome', 'nome_completo', 'nomecompleto', 'voluntario', 'voluntario_nome', 'volunteer_name',
        'nome_do_comprador', 'comprador', 'seu_nome', 'name',
    )
    color_candidates = (
        'cor', 'color', 'modelo', 'produto', 'camisa', 'selecione_o_modelo_que_deseja',
        'selecione_o_modelo_que_deseja_atencao_por_favor_ter_a_consciencia_de_nao_divulgar_as',
    )
    size_candidates = (
        'tamanho', 'size', 'selecione_seu_tamanho',
    )
    quantity_candidates = ('quantidade', 'qtd', 'quantity')
    external_key_candidates = ('id', 'chave', 'external_key', 'codigo', 'código')

    has_name_column = any(candidate in header_map for candidate in name_candidates)
    if has_name_column:
        data_rows = rows[1:]
    else:
        # If there is no recognizable header, treat all rows as data.
        data_rows = rows
    def normalize_color_value(value):
        text = str(value or '').strip()
        normalized = normalize_choice(text, ProductColorChoices.choices)
        allowed_colors = {choice for choice, _ in ProductColorChoices.choices}
        if normalized in allowed_colors:
            return normalized
        lowered = text.lower()
        if any(token in lowered for token in ('white', 'branco', 'send me')):
            return ProductColorChoices.WHITE
        if any(token in lowered for token in ('black', 'preto', 'belong', 'jesus')):
            return ProductColorChoices.BLACK
        return ProductColorChoices.WHITE

    def normalize_size_value(value):
        normalized = normalize_choice(value, ProductSizeChoices.choices)
        allowed_sizes = {choice for choice, _ in ProductSizeChoices.choices}
        if normalized in allowed_sizes:
            return normalized
        return ProductSizeChoices.PP

    imported_rows = []
    for index, row in enumerate(data_rows, start=2 if has_name_column else 1):
        name_value = pick_value(header_map, row, *name_candidates, default='')
        if not name_value and len(row) > 1:
            name_value = row[1]
        if not name_value and row:
            name_value = row[0]

        color_value = pick_value(header_map, row, *color_candidates, default='')
        if not color_value and len(row) > 4:
            color_value = row[4]

        size_value = pick_value(header_map, row, *size_candidates, default='')
        if not size_value and len(row) > 3:
            size_value = row[3]
        if not size_value and len(row) > 2:
            size_value = row[2]

        quantity_value = pick_value(header_map, row, *quantity_candidates, default='1')
        external_key = pick_value(header_map, row, *external_key_candidates, default='')

        if not str(name_value or '').strip() or not str(size_value or '').strip():
            continue
        if not external_key:
            raw_signature = f'{name_value}|{color_value}|{size_value}|{quantity_value}'
            external_key = hashlib.sha1(raw_signature.encode('utf-8')).hexdigest()
        try:
            quantity_value = int(quantity_value or 1)
        except (TypeError, ValueError):
            quantity_value = 1
        imported_rows.append({
            'external_key': external_key,
            'volunteer_name': str(name_value).strip(),
            'color': normalize_color_value(color_value),
            'size': normalize_size_value(size_value),
            'quantity': quantity_value,
            'sheet_row_number': index,
            'raw': row,
        })
    return imported_rows


def _sync_preorders_from_sheet(sheet_link, created_by=None, delete_missing=False):
    sheet_link = str(sheet_link or '').strip()
    if not sheet_link:
        sheet_link = _get_saved_preorder_sheet_link()
    if not sheet_link:
        return 0, 0, 0

    imported_rows = _read_preorders_from_sheet(sheet_link)
    created_count = 0
    deleted_count = 0
    reserve_failed_count = 0
    with transaction.atomic():
        for row in imported_rows:
            if PreOrderRecord.objects.filter(external_key=row['external_key']).exists():
                continue
            ok, _sku = _reserve_inventory(row['color'], row['size'], row['quantity'])
            reserve_failed_count += 0 if ok else 1
            PreOrderRecord.objects.create(
                external_key=row['external_key'],
                source=PreOrderSourceChoices.SHEET,
                volunteer_name=row['volunteer_name'],
                color=row['color'],
                size=row['size'],
                quantity=row['quantity'],
                payment_status=PreOrderPaymentStatusChoices.PENDENTE,
                payment_method='',
                status=PreOrderStatusChoices.IMPORTADO,
                sheet_row_number=row['sheet_row_number'],
                sheet_payload={
                    'raw': row['raw'],
                    'reserved_applied': ok,
                    'reserve_error': '' if ok else 'Saldo insuficiente para reservar automaticamente.',
                },
                created_by=created_by,
                imported_at=timezone.now(),
            )
            created_count += 1

        if delete_missing and imported_rows:
            imported_keys = {row['external_key'] for row in imported_rows}
            obsolete_preorders = PreOrderRecord.objects.filter(
                source=PreOrderSourceChoices.SHEET,
            ).exclude(external_key__in=imported_keys)
            for preorder in obsolete_preorders:
                if _preorder_has_reserved_inventory(preorder):
                    _release_reserved_inventory(preorder.color, preorder.size, preorder.quantity)
                preorder.delete()
                deleted_count += 1

    return created_count, deleted_count, reserve_failed_count


def _get_saved_aconselhamento_sheet_link():
    return (AconselhamentoConfig.objects.filter(pk=1).values_list('sheet_link', flat=True).first() or '').strip()


def _save_aconselhamento_sheet_link(sheet_link):
    sheet_link = str(sheet_link or '').strip()
    config, _ = AconselhamentoConfig.objects.get_or_create(pk=1)
    if config.sheet_link != sheet_link:
        config.sheet_link = sheet_link
        config.save(update_fields=['sheet_link', 'updated_at'])
    return config


def _sync_campistas_da_planilha(sheet_link, criado_por=None):
    sheet_link = str(sheet_link or '').strip() or _get_saved_aconselhamento_sheet_link()
    if not sheet_link:
        return 0

    linhas = _fetch_sheet_rows_via_csv(sheet_link)
    if len(linhas) < 2:
        return 0

    def normalizar_cabecalho(valor):
        texto = unicodedata.normalize('NFKD', str(valor or '').strip()).encode('ascii', 'ignore').decode('ascii')
        return texto.lower().replace(' ', '_').replace('-', '_')

    def escolher_valor(mapa, linha, *candidatos, padrao=''):
        for candidato in candidatos:
            if candidato in mapa:
                indice = mapa[candidato]
                if indice < len(linha) and linha[indice] not in (None, ''):
                    return linha[indice]
        return padrao

    def normalizar_escolha(valor, escolhas):
        texto = str(valor or '').strip().lower()
        for valor_escolha, rotulo in escolhas:
            if texto == str(valor_escolha).strip().lower() or texto == str(rotulo).strip().lower():
                return valor_escolha
        return ''

    cabecalho = {normalizar_cabecalho(valor): indice for indice, valor in enumerate(linhas[0])}
    spreadsheet_id, sheet_gid = _extract_sheet_link_parts(sheet_link)
    origem_planilha = f'{spreadsheet_id}:{sheet_gid or "principal"}'

    total = 0
    for numero_linha, linha in enumerate(linhas[1:], start=2):
        nome = escolher_valor(cabecalho, linha, 'nome', 'acampante', 'nome_completo', 'participante', padrao=linha[0] if linha else '')
        if not nome:
            continue
        idade_bruta = escolher_valor(cabecalho, linha, 'idade', 'anos', padrao='')
        sexo = normalizar_escolha(escolher_valor(cabecalho, linha, 'sexo', 'genero', 'gênero', padrao=''), AconselhamentoCampistaSexoChoices.choices)
        celula = escolher_valor(cabecalho, linha, 'celula', 'célula', 'turma', 'equipe', padrao='')
        observacoes = escolher_valor(cabecalho, linha, 'observacoes', 'observação', 'observacao', 'obs', padrao='')
        try:
            idade = int(idade_bruta) if str(idade_bruta).strip() else None
        except (TypeError, ValueError):
            idade = None

        AconselhamentoCampista.objects.update_or_create(
            origem_planilha=origem_planilha,
            linha_planilha=numero_linha,
            defaults={
                'nome': nome,
                'idade': idade,
                'sexo': sexo,
                'celula': celula,
                'observacoes': observacoes,
                'criado_por': criado_por,
            },
        )
        total += 1

    return total


def _validar_campista_para_sala(campista, sala_destino):
    if not sala_destino:
        return True, ''
    if sala_destino.vagas_livres <= 0 and campista.sala_id != sala_destino.id:
        return False, 'O quarto está cheio.'
    if campista.sexo and campista.sexo != sala_destino.caracteristica:
        return False, 'O sexo do acampante não bate com as características do quarto.'
    return True, ''


def _registrar_movimento_campista(campista, sala_origem, sala_destino, acao, detalhe='', criado_por=None):
    AconselhamentoHistorico.objects.create(
        campista=campista,
        sala_origem=sala_origem,
        sala_destino=sala_destino,
        acao=acao,
        detalhe=detalhe,
        criado_por=criado_por,
    )


def _reserve_inventory(color, size, quantity):
    _ensure_inventory_grid()
    sku = InventorySku.objects.select_for_update().get(color=color, size=size)
    if sku.balance_quantity < quantity:
        return False, sku
    sku.reserved_quantity += quantity
    sku.save(update_fields=['reserved_quantity', 'updated_at'])
    return True, sku


def _release_reserved_inventory(color, size, quantity):
    _ensure_inventory_grid()
    sku = InventorySku.objects.select_for_update().get(color=color, size=size)
    sku.reserved_quantity = max(0, sku.reserved_quantity - int(quantity or 0))
    sku.save(update_fields=['reserved_quantity', 'updated_at'])
    return sku


def _preorder_has_reserved_inventory(preorder):
    if preorder.source != PreOrderSourceChoices.SHEET:
        return True
    payload = preorder.sheet_payload
    if isinstance(payload, dict):
        return bool(payload.get('reserved_applied', True))
    return True


def _sell_inventory(color, size, quantity):
    _ensure_inventory_grid()
    sku = InventorySku.objects.select_for_update().get(color=color, size=size)
    if sku.balance_quantity < quantity:
        return False, sku
    sku.sold_quantity += quantity
    sku.save(update_fields=['sold_quantity', 'updated_at'])
    return True, sku


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


def _can_view_overview(user):
    if not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    return user.role == User.Role.NOBREAK


def _sync_members_from_sheet(sheet_link, allowed_teams):
    rows = _fetch_sheet_rows_via_csv(sheet_link)
    if not rows:
        return 0, 0, 0, 0

    def normalize_text(value):
        normalized = unicodedata.normalize('NFKD', str(value or '').strip()).encode('ascii', 'ignore').decode('ascii')
        return normalized.lower().replace(' ', '_').replace('-', '_')

    def pick_value(mapping, row, *candidates, default=''):
        for candidate in candidates:
            if candidate in mapping:
                idx = mapping[candidate]
                if idx < len(row) and row[idx] not in (None, ''):
                    return row[idx]
        return default

    def parse_active(value):
        text = str(value or '').strip().lower()
        return text not in {'0', 'nao', 'não', 'false', 'falso', 'inativo'}

    team_map = {}
    for value, label in EquipeChoices.choices:
        if value not in allowed_teams:
            continue
        team_map[normalize_text(value)] = value
        team_map[normalize_text(label)] = value
        team_map[normalize_text(value).replace('_', '')] = value
        team_map[normalize_text(label).replace('_', '')] = value

    team_aliases = {
        'lojinhaecantina': EquipeChoices.LOJINHA_CANTINA,
        'lojinha_cantina': EquipeChoices.LOJINHA_CANTINA,
        'cantina': EquipeChoices.LOJINHA_CANTINA,
        'chefiadelojinhaecantina': EquipeChoices.LOJINHA_CANTINA,
        'oracao': EquipeChoices.ORACAO,
        'oração': EquipeChoices.ORACAO,
        'comunicacao': EquipeChoices.COMUNICACAO,
        'comunicação': EquipeChoices.COMUNICACAO,
    }
    for alias, team_value in team_aliases.items():
        if team_value in allowed_teams:
            team_map[normalize_text(alias)] = team_value
            team_map[normalize_text(alias).replace('_', '')] = team_value

    header_map = {normalize_text(value): index for index, value in enumerate(rows[0])}
    nome_candidates = ('nome', 'membro', 'name', 'nome_completo', 'membro_nome')
    equipe_candidates = ('equipe', 'setor', 'ministerio', 'ministério', 'area', 'área', 'team')
    ativo_candidates = ('ativo', 'status', 'active', 'situacao', 'situação')
    has_nome_column = any(candidate in header_map for candidate in nome_candidates)
    has_equipe_column = any(candidate in header_map for candidate in equipe_candidates)
    has_ativo_column = any(candidate in header_map for candidate in ativo_candidates)
    if not has_nome_column:
        header_map = {'nome': 0, 'equipe': 1, 'ativo': 2}
        has_nome_column = True
        has_equipe_column = len(rows[0]) > 1
        has_ativo_column = len(rows[0]) > 2
        data_rows = rows
    else:
        data_rows = rows[1:]

    if EquipeChoices.PESSOAL in allowed_teams:
        default_team = EquipeChoices.PESSOAL
    else:
        default_team = sorted(allowed_teams)[0] if allowed_teams else None

    created_count = 0
    updated_count = 0
    skipped_count = 0
    deleted_count = 0

    for row in data_rows:
        nome = str(pick_value(header_map, row, *nome_candidates, default='')).strip()
        equipe_raw = pick_value(header_map, row, *equipe_candidates, default='')
        ativo_raw = pick_value(header_map, row, *ativo_candidates, default='sim')

        if not nome:
            skipped_count += 1
            continue

        existing_member = Membro.objects.filter(nome__iexact=nome, equipe__in=allowed_teams).first()
        team_key = normalize_text(equipe_raw)
        equipe = team_map.get(team_key) or team_map.get(team_key.replace('_', ''))

        if not equipe:
            if existing_member:
                equipe = existing_member.equipe
            elif default_team:
                equipe = default_team

        if not equipe:
            skipped_count += 1
            continue

        ativo = parse_active(ativo_raw) if has_ativo_column else (existing_member.ativo if existing_member else True)

        if existing_member:
            existing_member.nome = nome
            existing_member.equipe = equipe
            existing_member.ativo = ativo
            existing_member.save(update_fields=['nome', 'equipe', 'ativo'])
            updated_count += 1
        else:
            Membro.objects.create(nome=nome, equipe=equipe, ativo=ativo)
            created_count += 1

    return created_count, updated_count, skipped_count, deleted_count


def _get_saved_member_sheet_config():
    config, _ = MembroSheetConfig.objects.get_or_create(pk=1)
    return config


def _save_member_sheet_config(sheet_link='', mirror_mode=True, auto_sync=True):
    config, _ = MembroSheetConfig.objects.get_or_create(pk=1)
    sheet_link = str(sheet_link or '').strip()
    if sheet_link:
        config.sheet_link = sheet_link
    config.mirror_mode = bool(mirror_mode)
    config.auto_sync = bool(auto_sync)
    config.save(update_fields=['sheet_link', 'mirror_mode', 'auto_sync', 'updated_at'])
    return config


def _apply_member_mirror(sheet_link, allowed_teams):
    rows = _fetch_sheet_rows_via_csv(sheet_link)
    if not rows:
        return 0

    def normalize_text(value):
        normalized = unicodedata.normalize('NFKD', str(value or '').strip()).encode('ascii', 'ignore').decode('ascii')
        return normalized.lower().replace(' ', '_').replace('-', '_')

    def pick_value(mapping, row, *candidates, default=''):
        for candidate in candidates:
            if candidate in mapping:
                idx = mapping[candidate]
                if idx < len(row) and row[idx] not in (None, ''):
                    return row[idx]
        return default

    team_map = {}
    for value, label in EquipeChoices.choices:
        if value in allowed_teams:
            team_map[normalize_text(value)] = value
            team_map[normalize_text(label)] = value
            team_map[normalize_text(value).replace('_', '')] = value
            team_map[normalize_text(label).replace('_', '')] = value

    header_map = {normalize_text(value): index for index, value in enumerate(rows[0])}
    nome_candidates = ('nome', 'membro', 'name', 'nome_completo', 'membro_nome')
    equipe_candidates = ('equipe', 'setor', 'ministerio', 'ministério', 'area', 'área', 'team')
    has_nome_column = any(candidate in header_map for candidate in nome_candidates)
    has_equipe_column = any(candidate in header_map for candidate in equipe_candidates)
    if not has_nome_column:
        header_map = {'nome': 0, 'equipe': 1}
        has_equipe_column = len(rows[0]) > 1
        data_rows = rows
    else:
        data_rows = rows[1:]

    if EquipeChoices.PESSOAL in allowed_teams:
        default_team = EquipeChoices.PESSOAL
    else:
        default_team = sorted(allowed_teams)[0] if allowed_teams else None

    imported_keys = set()
    for row in data_rows:
        nome = str(pick_value(header_map, row, *nome_candidates, default='')).strip()
        equipe_raw = pick_value(header_map, row, *equipe_candidates, default='')
        if not nome:
            continue

        existing_member = Membro.objects.filter(nome__iexact=nome, equipe__in=allowed_teams).first()
        team_key = normalize_text(equipe_raw)
        equipe = team_map.get(team_key) or team_map.get(team_key.replace('_', ''))
        if not equipe:
            if existing_member:
                equipe = existing_member.equipe
            elif default_team:
                equipe = default_team

        if equipe:
            imported_keys.add(f'{nome.lower()}|{equipe}')

    # Protect against accidental mass delete when sheet cannot be parsed.
    if not imported_keys:
        return 0

    deleted_count = 0
    target_teams = {key.rsplit('|', 1)[-1] for key in imported_keys}
    existing_members = Membro.objects.filter(equipe__in=target_teams)
    for member in existing_members:
        member_key = f'{member.nome.lower()}|{member.equipe}'
        if member_key not in imported_keys:
            member.delete()
            deleted_count += 1
    return deleted_count


def _can_access_preparo(user):
    if not getattr(settings, 'FEATURE_PREPARO_ENABLED', False):
        return False
    if not user.is_authenticated:
        return False
    return user.role == User.Role.NOBREAK


def _can_access_documentos(user):
    if not user.is_authenticated:
        return False
    return user.role == User.Role.NOBREAK


def _deny_access(team_slug):
    return HttpResponseForbidden(f'Voce nao tem permissao para acessar a area: {team_slug}.')


@login_required
def documentos_page(request):
    if not _can_access_documentos(request.user):
        return HttpResponseForbidden('Voce nao tem permissao para acessar os documentos importantes.')

    if request.method == 'POST':
        form = DocumentoImportanteForm(request.POST, request.FILES)
        if form.is_valid():
            document = form.save(commit=False)
            document.criado_por = request.user
            document.save()
            messages.success(request, 'Documento salvo com sucesso.')
            return redirect('documentos')
    else:
        form = DocumentoImportanteForm()

    documentos = DocumentoImportante.objects.select_related('criado_por').all()
    return render(request, 'dashboard/documentos.html', {
        'page_title': 'Documentos Importantes',
        'active_page': 'documentos',
        'form': form,
        'documentos': documentos,
    })


@login_required
def documento_delete(request, pk):
    if not _can_access_documentos(request.user):
        return HttpResponseForbidden('Voce nao tem permissao para excluir documentos importantes.')
    documento = get_object_or_404(DocumentoImportante, pk=pk)
    if request.method == 'POST':
        documento.delete()
        messages.success(request, 'Documento removido com sucesso.')
        return redirect('documentos')
    return redirect('documentos')


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
    if not _can_view_overview(request.user):
        return HttpResponseForbidden('Voce nao tem permissao para acessar a Visao Geral.')

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

    allowed_teams = _allowed_teams_for_user(request.user)
    saved_config = _get_saved_member_sheet_config()
    member_import_form = MembroImportForm(initial={
        'sheet_link': saved_config.sheet_link,
        'mirror_mode': saved_config.mirror_mode,
        'auto_sync': saved_config.auto_sync,
    })

    if request.method == 'GET' and saved_config.sheet_link and saved_config.auto_sync:
        created_count, updated_count, skipped_count, _ = _sync_members_from_sheet(saved_config.sheet_link, allowed_teams)
        deleted_count = _apply_member_mirror(saved_config.sheet_link, allowed_teams) if saved_config.mirror_mode else 0
        if created_count or updated_count:
            messages.info(request, f'Sincronização automática: novos {created_count}, atualizados {updated_count}.')
        if deleted_count:
            messages.info(request, f'Modo espelho: {deleted_count} membros removidos por não estarem na planilha.')
        if skipped_count:
            messages.info(request, f'{skipped_count} linhas ignoradas na sincronização automática.')

    if request.method == 'POST' and request.POST.get('action') == 'import_members':
        member_import_form = MembroImportForm(request.POST)
        if member_import_form.is_valid():
            sheet_link = (member_import_form.cleaned_data.get('sheet_link') or saved_config.sheet_link or '').strip()
            mirror_mode = bool(member_import_form.cleaned_data.get('mirror_mode'))
            auto_sync = bool(member_import_form.cleaned_data.get('auto_sync'))
            if not sheet_link:
                messages.error(request, 'Informe o link da planilha ao menos uma vez para ativar a sincronização.')
                return redirect('membros')

            _save_member_sheet_config(sheet_link=sheet_link, mirror_mode=mirror_mode, auto_sync=auto_sync)
            created_count, updated_count, skipped_count, _ = _sync_members_from_sheet(
                sheet_link,
                allowed_teams,
            )
            deleted_count = _apply_member_mirror(sheet_link, allowed_teams) if mirror_mode else 0
            if created_count or updated_count:
                messages.success(request, f'Importação concluída. Novos: {created_count}, atualizados: {updated_count}.')
            if deleted_count:
                messages.info(request, f'Modo espelho: {deleted_count} membros removidos por não estarem na planilha.')
            if skipped_count:
                messages.info(request, f'{skipped_count} linhas foram ignoradas (sem nome ou setor inválido).')
            if not created_count and not updated_count and not skipped_count and not deleted_count:
                messages.error(request, 'Não foi possível importar. Verifique o link e os cabeçalhos da planilha.')
            return redirect('membros')
        messages.error(request, 'Informe um link de planilha válido para importar membros.')

    members, search_query, selected_team = _member_queryset(request)
    team_choices = [choice for choice in EquipeChoices.choices if choice[0] in allowed_teams]
    return render(request, 'dashboard/member_list.html', {
        'page_title': 'Membros',
        'active_page': 'membros',
        'members': members,
        'member_import_form': member_import_form,
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

    if team_slug == 'aconselhamento':
        import_form = AconselhamentoImportarForm(request.POST or None, initial={'sheet_link': _get_saved_aconselhamento_sheet_link()})
        sala_form = AconselhamentoSalaForm()
        filtro_form = AconselhamentoFiltroForm(request.GET or None)
        saved_sheet_link = _get_saved_aconselhamento_sheet_link()
        if request.method == 'POST' and request.POST.get('acao') == 'importar_planilha' and import_form.is_valid():
            if import_form.cleaned_data.get('sheet_link'):
                _save_aconselhamento_sheet_link(import_form.cleaned_data['sheet_link'])
            _sync_campistas_da_planilha(import_form.cleaned_data.get('sheet_link'), criado_por=request.user)
            return redirect(reverse('aconselhamento'))

        if request.method == 'GET' and saved_sheet_link:
            _sync_campistas_da_planilha(saved_sheet_link, criado_por=request.user)

        campistas_base = AconselhamentoCampista.objects.select_related('sala').order_by('sala__nome', 'nome')
        campistas_disponiveis = campistas_base.filter(sala__isnull=True)
        if filtro_form.is_valid():
            nome = filtro_form.cleaned_data.get('nome', '').strip()
            sexo = filtro_form.cleaned_data.get('sexo')
            celula = filtro_form.cleaned_data.get('celula', '').strip()
            idade_min = filtro_form.cleaned_data.get('idade_min')
            idade_max = filtro_form.cleaned_data.get('idade_max')
            
            if nome:
                campistas_disponiveis = campistas_disponiveis.filter(nome__icontains=nome)
            if sexo:
                campistas_disponiveis = campistas_disponiveis.filter(sexo=sexo)
            if celula:
                campistas_disponiveis = campistas_disponiveis.filter(celula__icontains=celula)
            if idade_min is not None:
                campistas_disponiveis = campistas_disponiveis.filter(idade__gte=idade_min)
            if idade_max is not None:
                campistas_disponiveis = campistas_disponiveis.filter(idade__lte=idade_max)

        salas = list(AconselhamentoSala.objects.prefetch_related('campistas').order_by('nome'))
        historicos = AconselhamentoHistorico.objects.select_related('campista', 'sala_origem', 'sala_destino', 'criado_por')[:50]
        total_campistas = campistas_base.count()
        campistas_nao_alocados = campistas_base.filter(sala__isnull=True).count()
        salas_cheias = sum(1 for sala in salas if sala.ocupacao_total >= sala.capacidade)
        vagas_livres = sum(sala.vagas_livres for sala in salas)
        return render(request, 'dashboard/aconselhamento.html', {
            'page_title': meta['title'],
            'active_page': team_slug,
            'team_slug': team_slug,
            'team_title': meta['title'],
            'team_subtitle': meta['subtitle'],
            'filtro_form': filtro_form,
            'import_form': import_form,
            'sala_form': sala_form,
            'salas': salas,
            'campistas_disponiveis': campistas_disponiveis,
            'campistas_base': campistas_base,
            'historicos': historicos,
            'total_campistas': total_campistas,
            'campistas_nao_alocados': campistas_nao_alocados,
            'salas_cheias': salas_cheias,
            'vagas_livres': vagas_livres,
            'can_view_members_index': _can_view_members_index(request.user),
            'can_manage_membership': _can_manage_membership(request.user),
            'member_form': member_form,
            'member_create_url': reverse('team_member_create', kwargs={'team_slug': team_slug}),
            'members_index_url': reverse('membros'),
            'campista_move_url': reverse('aconselhamento_campista_mover'),
            'sala_create_url': reverse('aconselhamento_sala_criar'),
            'import_url': reverse('aconselhamento_importar_planilha'),
        })

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
def aconselhamento_importar_planilha(request):
    if not _can_access_team(request.user, 'aconselhamento'):
        return _deny_access('aconselhamento')
    if request.method != 'POST':
        return HttpResponseForbidden('Requisição inválida.')

    form = AconselhamentoImportarForm(request.POST)
    if form.is_valid():
        sheet_link = form.cleaned_data.get('sheet_link') or ''
        if sheet_link:
            _save_aconselhamento_sheet_link(sheet_link)
        total = _sync_campistas_da_planilha(sheet_link, criado_por=request.user)
        messages.success(request, f'{total} campistas sincronizados da planilha.')
    else:
        messages.error(request, 'Informe um link válido da planilha.')
    return redirect(reverse('aconselhamento'))


@login_required
def aconselhamento_sala_criar(request):
    if not _can_access_team(request.user, 'aconselhamento'):
        return _deny_access('aconselhamento')
    if request.method != 'POST':
        return HttpResponseForbidden('Requisição inválida.')

    form = AconselhamentoSalaForm(request.POST)
    if form.is_valid():
        AconselhamentoSala.objects.create(
            nome=form.cleaned_data['nome'],
            capacidade=form.cleaned_data['capacidade'],
            caracteristica=form.cleaned_data['caracteristica'],
            observacoes=form.cleaned_data['observacoes'],
        )
        messages.success(request, 'Sala criada com sucesso.')
    else:
        messages.error(request, 'Confira os dados da sala.')
    return redirect(reverse('aconselhamento'))


@login_required
def aconselhamento_sala_editar(request, sala_id):
    if not _can_access_team(request.user, 'aconselhamento'):
        return _deny_access('aconselhamento')
    
    sala = get_object_or_404(AconselhamentoSala, pk=sala_id)
    
    if request.method == 'POST':
        form = AconselhamentoSalaForm(request.POST)
        if form.is_valid():
            sala.nome = form.cleaned_data['nome']
            sala.capacidade = form.cleaned_data['capacidade']
            sala.caracteristica = form.cleaned_data['caracteristica']
            sala.observacoes = form.cleaned_data['observacoes']
            sala.save()
            messages.success(request, 'Quarto atualizado com sucesso.')
            return redirect(reverse('aconselhamento'))
        else:
            messages.error(request, 'Confira os dados do quarto.')
            return redirect(reverse('aconselhamento'))
    
    return JsonResponse({'ok': False, 'mensagem': 'Requisição inválida.'}, status=405)


@login_required
def aconselhamento_campista_mover(request):
    if not _can_access_team(request.user, 'aconselhamento'):
        return _deny_access('aconselhamento')
    if request.method != 'POST':
        return JsonResponse({'ok': False, 'mensagem': 'Requisição inválida.'}, status=405)

    campista_id = request.POST.get('campista_id')
    sala_id = request.POST.get('sala_id')
    campista = get_object_or_404(AconselhamentoCampista.objects.select_related('sala'), pk=campista_id)
    sala_destino = AconselhamentoSala.objects.filter(pk=sala_id).first() if sala_id else None
    sala_origem = campista.sala

    ok, mensagem = _validar_campista_para_sala(campista, sala_destino)
    if not ok:
        return JsonResponse({'ok': False, 'mensagem': mensagem}, status=400)

    if sala_origem_id := getattr(sala_origem, 'id', None):
        if sala_destino and sala_origem_id == sala_destino.id:
            return JsonResponse({'ok': True, 'mensagem': 'Acampante já está neste quarto.'})

    campista.sala = sala_destino
    campista.save(update_fields=['sala', 'atualizado_em'])
    acao = 'movido_para_sala' if sala_destino else 'removido_da_sala'
    detalhe = f'{campista.nome} foi movido para {sala_destino.nome if sala_destino else "sem quarto"}.'
    _registrar_movimento_campista(campista, sala_origem, sala_destino, acao, detalhe, criado_por=request.user)
    return JsonResponse({'ok': True, 'mensagem': 'Acampante movido com sucesso.'})


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


@login_required
def commerce_dashboard(request):
    if not _commercial_allowed(request.user):
        return HttpResponseForbidden('Voce nao tem permissao para acessar o modulo comercial.')

    _ensure_inventory_grid()
    active_tab = request.GET.get('tab', 'inventory')
    sale_form = SaleForm(request.POST or None)
    inventory_form = InventoryAdjustForm(request.POST or None)
    if request.method == 'POST' and request.POST.get('action') == 'inventory_adjust' and inventory_form.is_valid():
        with transaction.atomic():
            sku, _ = InventorySku.objects.select_for_update().get_or_create(
                color=inventory_form.cleaned_data['color'],
                size=inventory_form.cleaned_data['size'],
                defaults={'initial_quantity': 0},
            )
            sku.initial_quantity = inventory_form.cleaned_data['initial_quantity']
            sku.save(update_fields=['initial_quantity', 'updated_at'])
        messages.success(request, 'Estoque inicial atualizado.')
        return redirect(f"{reverse('commerce_dashboard')}?tab=inventory")

    if request.method == 'POST' and request.POST.get('action') == 'sale' and sale_form.is_valid():
        unit_value = PIX_CASH_VALUE if sale_form.cleaned_data['payment_method'] == PaymentMethodChoices.PIX_CASH else CARD_VALUE
        total_value = unit_value * sale_form.cleaned_data['quantity']
        with transaction.atomic():
            ok, sku = _sell_inventory(
                sale_form.cleaned_data['color'],
                sale_form.cleaned_data['size'],
                sale_form.cleaned_data['quantity'],
            )
            if not ok:
                sale_form.add_error('quantity', 'Saldo insuficiente para esta cor e tamanho.')
            else:
                SaleRecord.objects.create(
                    product_name=sale_form.cleaned_data['product_name'],
                    color=sale_form.cleaned_data['color'],
                    size=sale_form.cleaned_data['size'],
                    quantity=sale_form.cleaned_data['quantity'],
                    payment_method=sale_form.cleaned_data['payment_method'],
                    unit_value=unit_value,
                    total_value=total_value,
                    created_by=request.user,
                )
                messages.success(request, 'Venda registrada e estoque atualizado.')
                return redirect(f"{reverse('commerce_dashboard')}?tab={active_tab}")

    sales = SaleRecord.objects.order_by('-created_at')[:30]
    inventory_matrix = _inventory_matrix()
    total_pix_cash, total_card, total_sales, preorder_estimate = _commercial_totals()
    payment_chart_labels = ['Pix/Dinheiro', 'Cartão']
    payment_chart_values = [float(total_pix_cash), float(total_card)]
    inventory_chart_labels = [f"{row['label']} / {slot['label']}" for row in inventory_matrix for slot in row['sizes']]
    inventory_chart_values = [slot['balance'] for row in inventory_matrix for slot in row['sizes']]
    evolution_series = _inventory_evolution_series()

    return render(request, 'dashboard/commerce_dashboard.html', {
        'page_title': 'Vendas',
        'active_page': 'commerce',
        'active_tab': active_tab,
        'sale_form': sale_form,
        'inventory_form': inventory_form,
        'sales': sales,
        'inventory_matrix': inventory_matrix,
        'total_pix_cash': total_pix_cash,
        'total_card': total_card,
        'total_sales': total_sales,
        'preorder_estimate': preorder_estimate,
        'payment_chart_labels': payment_chart_labels,
        'payment_chart_values': payment_chart_values,
        'inventory_chart_labels': inventory_chart_labels,
        'inventory_chart_values': inventory_chart_values,
        'evolution_chart_labels': [item['label'] for item in evolution_series],
        'evolution_chart_values': [item['value'] for item in evolution_series],
    })


@login_required
def preorder_dashboard(request):
    if not _commercial_allowed(request.user):
        return HttpResponseForbidden('Voce nao tem permissao para acessar o modulo de pre-encomendas.')

    _ensure_inventory_grid()
    active_tab = request.GET.get('tab', 'form')
    preorder_form = PreOrderForm(request.POST or None)
    saved_sheet_link = _get_saved_preorder_sheet_link()
    import_form = SheetImportForm(request.POST or None, initial={'sheet_link': saved_sheet_link})
    payment_form = PreOrderPaymentForm(request.POST or None)
    search_form = PreOrderSearchForm(request.GET or None)

    if request.method == 'POST' and request.POST.get('action') == 'preorder' and preorder_form.is_valid():
        external_key = str(uuid.uuid4())
        with transaction.atomic():
            ok, sku = _reserve_inventory(
                preorder_form.cleaned_data['color'],
                preorder_form.cleaned_data['size'],
                preorder_form.cleaned_data['quantity'],
            )
            if not ok:
                preorder_form.add_error('quantity', 'Saldo insuficiente para reservar esta cor e tamanho.')
            else:
                preorder = PreOrderRecord.objects.create(
                    external_key=external_key,
                    source=PreOrderSourceChoices.FORM,
                    volunteer_name=preorder_form.cleaned_data['volunteer_name'],
                    color=preorder_form.cleaned_data['color'],
                    size=preorder_form.cleaned_data['size'],
                    quantity=preorder_form.cleaned_data['quantity'],
                    payment_status=PreOrderPaymentStatusChoices.PENDENTE,
                    payment_method='',
                    status=PreOrderStatusChoices.RESERVADO,
                    created_by=request.user,
                )
                sheet_ok, sheet_response = _append_preorder_to_sheet(preorder)
                if sheet_ok:
                    preorder.status = PreOrderStatusChoices.SINCRONIZADO
                preorder.sheet_payload = {'sheet_response': sheet_response}
                preorder.save(update_fields=['status', 'sheet_payload'])
                messages.success(request, 'Pré-encomenda salva e reserva aplicada.')
                return redirect(f"{reverse('preorder_dashboard')}?tab=reservations")

    if request.method == 'POST' and request.POST.get('action') == 'import_sheet':
        sheet_link = (import_form.data.get('sheet_link') or '').strip()
        delete_missing = import_form.data.get('delete_missing') in {'on', 'true', '1'}
        if sheet_link:
            _save_preorder_sheet_link(sheet_link)
        created_count, deleted_count, reserve_failed_count = _sync_preorders_from_sheet(
            sheet_link,
            created_by=request.user,
            delete_missing=delete_missing,
        )
        if created_count:
            messages.success(request, f'{created_count} pré-encomendas importadas da planilha.')
        if reserve_failed_count:
            messages.warning(
                request,
                f'{reserve_failed_count} pré-encomendas foram importadas sem reserva de estoque automática por falta de saldo.',
            )
        if deleted_count:
            messages.info(request, f'{deleted_count} pré-encomendas foram apagadas do sistema por não estarem mais na planilha.')
        if not created_count and not deleted_count and not reserve_failed_count:
            messages.error(request, 'Não consegui importar nenhuma linha. Verifique se a planilha está compartilhada com a conta de serviço e se a primeira aba tem os cabeçalhos corretos.')
        return redirect(f"{reverse('preorder_dashboard')}?tab=imports")

    if request.method == 'POST' and request.POST.get('action') == 'delete_preorder':
        preorder_id = request.POST.get('preorder_id')
        preorder = get_object_or_404(PreOrderRecord, pk=preorder_id)
        with transaction.atomic():
            _release_reserved_inventory(preorder.color, preorder.size, preorder.quantity)
            preorder.delete()
        messages.success(request, 'Pré-encomenda apagada do sistema.')
        return redirect(f"{reverse('preorder_dashboard')}?tab=edit")

    if request.method == 'POST' and request.POST.get('action') == 'update_payment' and payment_form.is_valid():
        preorder = get_object_or_404(PreOrderRecord, pk=payment_form.cleaned_data['preorder_id'])
        preorder.payment_status = payment_form.cleaned_data['payment_status']
        payment_method = (payment_form.cleaned_data.get('payment_method') or '').strip()
        if preorder.payment_status == PreOrderPaymentStatusChoices.PAGO and not payment_method:
            payment_form.add_error('payment_method', 'Escolha a forma de pagamento para marcar como pago.')
        else:
            preorder.payment_method = payment_method if preorder.payment_status == PreOrderPaymentStatusChoices.PAGO else ''
            preorder.save(update_fields=['payment_status', 'payment_method'])
            messages.success(request, 'Forma de pagamento atualizada.')
            return redirect(f"{reverse('preorder_dashboard')}?tab=edit")

    auto_imported_count = 0
    auto_deleted_count = 0
    auto_reserve_failed_count = 0
    if request.method == 'GET' and saved_sheet_link:
        auto_imported_count, auto_deleted_count, auto_reserve_failed_count = _sync_preorders_from_sheet(saved_sheet_link)
        if auto_imported_count:
            messages.info(request, f'{auto_imported_count} novas pré-encomendas foram sincronizadas automaticamente.')
        if auto_reserve_failed_count:
            messages.warning(
                request,
                f'{auto_reserve_failed_count} novas pré-encomendas ficaram sem reserva automática por falta de saldo.',
            )

    preorder_qs = PreOrderRecord.objects.order_by('-created_at')
    preorders = preorder_qs[:50]
    edit_preorders = preorder_qs
    search_query = ''
    if search_form.is_valid():
        search_query = search_form.cleaned_data.get('q', '').strip()
        if search_query:
            edit_preorders = preorder_qs.filter(volunteer_name__icontains=search_query)
    inventory_matrix = _inventory_matrix()
    total_pix_cash, total_card, total_sales, preorder_estimate = _commercial_totals()
    evolution_series = _inventory_evolution_series()
    return render(request, 'dashboard/preorder_dashboard.html', {
        'page_title': 'Pré-encomendas',
        'active_page': 'preorder',
        'active_tab': active_tab,
        'preorder_form': preorder_form,
        'import_form': import_form,
        'payment_form': payment_form,
        'search_form': search_form,
        'edit_preorders': edit_preorders,
        'search_query': search_query,
        'saved_sheet_link': saved_sheet_link,
        'auto_imported_count': auto_imported_count,
        'auto_deleted_count': auto_deleted_count,
        'preorders': preorders,
        'inventory_matrix': inventory_matrix,
        'total_preorders': PreOrderRecord.objects.count(),
        'reserved_total': PreOrderRecord.objects.aggregate(total=models.Sum('quantity'))['total'] or 0,
        'balance_total': sum(slot['balance'] for row in inventory_matrix for slot in row['sizes']),
        'total_pix_cash': total_pix_cash,
        'total_card': total_card,
        'total_sales': total_sales,
        'preorder_estimate': preorder_estimate,
        'payment_chart_labels': ['Vendas', 'Pré-encomendas'],
        'payment_chart_values': [float(total_sales), float(preorder_estimate)],
        'inventory_chart_labels': [f"{row['label']} / {slot['label']}" for row in inventory_matrix for slot in row['sizes']],
        'inventory_chart_values': [slot['balance'] for row in inventory_matrix for slot in row['sizes']],
        'evolution_chart_labels': [item['label'] for item in evolution_series],
        'evolution_chart_values': [item['value'] for item in evolution_series],
    })
