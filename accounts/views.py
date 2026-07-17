from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordChangeForm, SetPasswordForm
from django.contrib.auth.views import PasswordChangeDoneView, PasswordChangeView
from django.shortcuts import redirect
from django.urls import reverse_lazy

from .models import User


@login_required
def post_login_redirect(request):
    user = request.user
    if user.is_superuser:
        return redirect('dashboard')

    role_to_area = {
        User.Role.CHEFIA_LOGISTICA: 'logistica',
        User.Role.CHEFIA_EVENTOS: 'eventos',
        User.Role.CHEFIA_ORACAO: 'oracao',
        User.Role.CHEFIA_PROGRAMA: 'programa',
        User.Role.CHEFIA_ACONSELHAMENTO: 'aconselhamento',
        User.Role.CHEFIA_COMUNICACAO: 'comunicacao',
        User.Role.CHEFIA_LOJINHA_CANTINA: 'lojinha_cantina',
        User.Role.ADMINISTRACAO: 'administracao',
        User.Role.CHEFE_PESSOAL: 'pessoal',
        User.Role.CHEFE_MATERIAIS: 'materiais',
        User.Role.CHEFE_EQUIPE: 'eventos',
        User.Role.TRIPE: 'eventos',
        User.Role.NOBREAK: 'dashboard',
    }
    return redirect(role_to_area.get(getattr(user, 'role', ''), 'eventos'))


class FirstAccessPasswordChangeView(PasswordChangeView):
    template_name = 'registration/password_change_form.html'
    success_url = reverse_lazy('password_change_done')

    def get_form_class(self):
        if getattr(self.request.user, 'must_change_password', False):
            return SetPasswordForm
        return PasswordChangeForm

    def form_valid(self, form):
        response = super().form_valid(form)
        user = self.request.user
        if getattr(user, 'must_change_password', False):
            user.must_change_password = False
            user.save(update_fields=['must_change_password'])
        return response


class FirstAccessPasswordChangeDoneView(PasswordChangeDoneView):
    template_name = 'registration/password_change_done.html'
