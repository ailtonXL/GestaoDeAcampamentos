from django.contrib.auth.forms import PasswordChangeForm, SetPasswordForm
from django.contrib.auth.views import PasswordChangeDoneView, PasswordChangeView
from django.urls import reverse_lazy


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
