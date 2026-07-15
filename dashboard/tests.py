from decimal import Decimal
import uuid

from django.test import RequestFactory, TestCase
from django.urls import reverse
from django.contrib.auth import get_user_model

from .models import EquipeChoices, InventorySku, Membro, PaymentMethodChoices, PreOrderPaymentStatusChoices, PreOrderRecord, PreOrderSourceChoices, PreOrderStatusChoices, ProductColorChoices, ProductSizeChoices, StatusTarefaChoices, Tarefa
from .views import _commercial_totals, team_page


class DashboardViewTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='tester',
            password='Strong1!pass',
            role='nobreak',
            must_change_password=False,
        )
        self.client.force_login(self.user)

        Tarefa.objects.all().delete()
        Membro.objects.all().delete()

        self.eventos_member = Membro.objects.create(nome='Ana Paula', equipe=EquipeChoices.EVENTOS)
        self.financeiro_member = Membro.objects.create(nome='Rafaela Gomes', equipe=EquipeChoices.FINANCEIRO)

        Tarefa.objects.create(
            titulo='Fechar programação',
            descricao='Ajustar os horários finais do evento.',
            equipe=EquipeChoices.EVENTOS,
            responsavel=self.eventos_member,
            status=StatusTarefaChoices.PENDENTE,
            valor_estimado=Decimal('0.00'),
        )
        Tarefa.objects.create(
            titulo='Conferir saldo',
            descricao='Revisar entradas e saídas do financeiro.',
            equipe=EquipeChoices.FINANCEIRO,
            responsavel=self.financeiro_member,
            status=StatusTarefaChoices.ANDAMENTO,
            valor_estimado=Decimal('150.50'),
        )

    def test_root_redirects_to_dashboard(self):
        response = self.client.get('/')

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('dashboard'))

    def test_dashboard_view_returns_overview_context(self):
        response = self.client.get(reverse('dashboard'))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'dashboard/index.html')
        self.assertEqual(response.context['active_page'], 'dashboard')
        self.assertEqual(response.context['total_members'], 2)
        self.assertEqual(response.context['total_pending'], 1)
        self.assertEqual(response.context['total_progress'], 1)
        self.assertEqual(response.context['total_done'], 0)
        self.assertEqual(response.context['finance_total'], 'R$ 150,50')
        self.assertEqual(len(response.context['cards']), 11)

    def test_eventos_team_page_uses_specific_template_and_context(self):
        response = self.client.get(reverse('eventos'))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'dashboard/eventos.html')
        self.assertEqual(response.context['team_title'], 'Eventos')
        self.assertEqual(response.context['task_total'], 1)
        self.assertEqual(response.context['task_pending'], 1)
        self.assertEqual(response.context['task_done'], 0)
        self.assertEqual([str(member) for member in response.context['members']], ['Ana Paula - Eventos'])

    def test_invalid_team_slug_falls_back_to_eventos(self):
        request = RequestFactory().get('/dashboard/invalida/')
        request.user = self.user
        response = team_page(request, 'invalida')

        self.assertEqual(response.status_code, 200)
        self.assertIn('Equipe Eventos', response.content.decode('utf-8'))

    def test_member_list_filters_by_name_and_team(self):
        Membro.objects.create(nome='Maria', equipe=EquipeChoices.LOGISTICA)
        Membro.objects.create(nome='Ronaldo', equipe=EquipeChoices.EVENTOS)
        Membro.objects.create(nome='João', equipe=EquipeChoices.COMUNICACAO)

        response = self.client.get(reverse('membros'), {'q': 'ma', 'equipe': 'logistica'})

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'dashboard/member_list.html')
        self.assertEqual(response.context['selected_team'], 'logistica')
        self.assertEqual([member.nome for member in response.context['members']], ['Maria'])

    def test_team_quick_add_creates_member_in_current_sector(self):
        response = self.client.post(
            reverse('team_member_create', kwargs={'team_slug': 'logistica'}),
            {
                'nome': 'Júlia',
                'ativo': 'on',
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('logistica'))
        self.assertTrue(Membro.objects.filter(nome='Júlia', equipe=EquipeChoices.LOGISTICA).exists())

    def test_member_update_can_transfer_between_sectors(self):
        member = Membro.objects.create(nome='Ronaldo', equipe=EquipeChoices.EVENTOS)

        response = self.client.post(
            reverse('membro_update', args=[member.pk]),
            {
                'nome': 'Ronaldo',
                'equipe': EquipeChoices.LOGISTICA,
                'ativo': 'on',
            },
        )

        member.refresh_from_db()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('membros'))
        self.assertEqual(member.equipe, EquipeChoices.LOGISTICA)

    def test_member_delete_removes_record_and_returns_to_members_list(self):
        member = Membro.objects.create(nome='Maria', equipe=EquipeChoices.LOGISTICA)

        response = self.client.post(
            reverse('membro_delete', args=[member.pk]),
            {'next': 'logistica'},
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('logistica'))
        self.assertFalse(Membro.objects.filter(pk=member.pk).exists())

    def test_team_task_create_creates_task_in_current_sector(self):
        member = Membro.objects.create(nome='Carlos', equipe=EquipeChoices.LOGISTICA)

        response = self.client.post(
            reverse('task_create', kwargs={'team_slug': 'logistica'}),
            {
                'titulo': 'Organizar transporte',
                'descricao': 'Definir veiculos e horarios.',
                'responsavel': member.pk,
                'status': StatusTarefaChoices.ANDAMENTO,
                'prazo': '2026-07-15',
                'valor_estimado': '250.00',
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('logistica'))
        self.assertTrue(
            Tarefa.objects.filter(
                titulo='Organizar transporte',
                equipe=EquipeChoices.LOGISTICA,
                responsavel=member,
            ).exists()
        )

    def test_task_update_changes_data_and_redirects_to_team(self):
        task = Tarefa.objects.filter(equipe=EquipeChoices.EVENTOS).first()

        response = self.client.post(
            reverse('task_update', args=[task.pk]),
            {
                'titulo': 'Fechar programação final',
                'descricao': 'Atualizacao da agenda geral.',
                'responsavel': self.eventos_member.pk,
                'status': StatusTarefaChoices.CONCLUIDA,
                'prazo': '2026-07-20',
                'valor_estimado': '75.50',
            },
        )

        task.refresh_from_db()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('eventos'))
        self.assertEqual(task.titulo, 'Fechar programação final')
        self.assertEqual(task.status, StatusTarefaChoices.CONCLUIDA)

    def test_task_delete_removes_task_and_redirects_to_team(self):
        task = Tarefa.objects.create(
            titulo='Conferir equipamentos',
            equipe=EquipeChoices.LOGISTICA,
            status=StatusTarefaChoices.PENDENTE,
        )

        response = self.client.post(reverse('task_delete', args=[task.pk]))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('logistica'))
        self.assertFalse(Tarefa.objects.filter(pk=task.pk).exists())


class CommerceCheckoutTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='commerce_tester',
            password='Strong1!pass',
            role='nobreak',
            must_change_password=False,
        )
        self.client.force_login(self.user)

    def test_checkout_deducts_only_selected_size_sku(self):
        sku_pp = InventorySku.objects.create(
            color=ProductColorChoices.WHITE,
            size=ProductSizeChoices.PP,
            initial_quantity=10,
            sold_quantity=0,
            reserved_quantity=0,
        )
        sku_g = InventorySku.objects.create(
            color=ProductColorChoices.WHITE,
            size=ProductSizeChoices.G,
            initial_quantity=10,
            sold_quantity=0,
            reserved_quantity=0,
        )

        response = self.client.post(
            reverse('commerce_dashboard'),
            {
                'action': 'sale',
                'product_name': 'Pedido teste',
                'color': ProductColorChoices.WHITE,
                'size': ProductSizeChoices.G,
                'quantity': 3,
                'payment_method': 'pix_cash',
            },
        )

        sku_pp.refresh_from_db()
        sku_g.refresh_from_db()

        self.assertEqual(response.status_code, 302)
        self.assertEqual(sku_pp.sold_quantity, 0)
        self.assertEqual(sku_g.sold_quantity, 3)


class PreOrderPaymentFlowTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='preorder_tester',
            password='Strong1!pass',
            role='nobreak',
            must_change_password=False,
        )
        self.client.force_login(self.user)

    def test_marking_preorder_paid_moves_reserved_to_sold(self):
        sku = InventorySku.objects.create(
            color=ProductColorChoices.WHITE,
            size=ProductSizeChoices.G,
            initial_quantity=10,
            sold_quantity=0,
            reserved_quantity=3,
        )
        preorder = PreOrderRecord.objects.create(
            external_key=str(uuid.uuid4()),
            source=PreOrderSourceChoices.FORM,
            volunteer_name='Teste',
            color=ProductColorChoices.WHITE,
            size=ProductSizeChoices.G,
            quantity=3,
            payment_status=PreOrderPaymentStatusChoices.PENDENTE,
            payment_method='',
            status=PreOrderStatusChoices.RESERVADO,
            created_by=self.user,
        )

        response = self.client.post(
            reverse('preorder_dashboard'),
            {
                'action': 'update_payment',
                'preorder_id': preorder.id,
                'payment_status': PreOrderPaymentStatusChoices.PAGO,
                'payment_method': PaymentMethodChoices.PIX_CASH,
            },
        )

        preorder.refresh_from_db()
        sku.refresh_from_db()

        self.assertEqual(response.status_code, 302)
        self.assertEqual(preorder.payment_status, PreOrderPaymentStatusChoices.PAGO)
        self.assertEqual(preorder.payment_method, PaymentMethodChoices.PIX_CASH)
        self.assertEqual(sku.sold_quantity, 3)
        self.assertEqual(sku.reserved_quantity, 0)

    def test_paid_preorders_are_counted_in_commercial_revenue_totals(self):
        PreOrderRecord.objects.create(
            external_key=str(uuid.uuid4()),
            source=PreOrderSourceChoices.SHEET,
            volunteer_name='Teste Receita',
            color=ProductColorChoices.BLACK,
            size=ProductSizeChoices.M,
            quantity=2,
            payment_status=PreOrderPaymentStatusChoices.PAGO,
            payment_method=PaymentMethodChoices.CARD,
            status=PreOrderStatusChoices.IMPORTADO,
            created_by=self.user,
        )

        total_pix_cash, total_card, total_sales, _preorder_estimate = _commercial_totals()

        self.assertEqual(total_pix_cash, Decimal('0'))
        self.assertEqual(total_card, Decimal('140.00'))
        self.assertEqual(total_sales, Decimal('140.00'))


class AuthenticationTests(TestCase):
    def setUp(self):
        self.user_model = get_user_model()

    def test_login_page_loads(self):
        response = self.client.get(reverse('login'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Entrar no sistema')

    def test_user_must_change_password_on_first_login(self):
        user = self.user_model.objects.create_user(
            username='firstlogin',
            password='OldPass1!',
            role='chefe_equipe',
            must_change_password=True,
        )

        self.client.force_login(user)
        response = self.client.get(reverse('dashboard'))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('password_change'))

    def test_password_validator_rejects_weak_password(self):
        user = self.user_model.objects.create_user(
            username='validator',
            password='Strong1!pass',
            role='chefe_equipe',
            must_change_password=True,
        )

        self.client.force_login(user)
        response = self.client.post(
            reverse('password_change'),
            {
                'new_password1': 'abcdef',
                'new_password2': 'abcdef',
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'A senha deve conter pelo menos 1 letra maiuscula.')

    def test_anonymous_user_is_redirected_to_login(self):
        response = self.client.get(reverse('dashboard'))

        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('login'), response.url)


class ModelTests(TestCase):
    def test_member_string_representation_uses_team_label(self):
        member = Membro(nome='Lucas', equipe=EquipeChoices.LOGISTICA)

        self.assertEqual(str(member), 'Lucas - Logística')

    def test_task_string_representation_uses_team_label(self):
        member = Membro.objects.create(nome='Bruno', equipe=EquipeChoices.PROGRAMA)
        task = Tarefa.objects.create(
            titulo='Montar cronograma',
            equipe=EquipeChoices.PROGRAMA,
            responsavel=member,
        )

        self.assertEqual(str(task), 'Montar cronograma - Programa')