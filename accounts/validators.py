from django.core.exceptions import ValidationError
from django.utils.translation import gettext as _


class StrongPasswordValidator:
    def validate(self, password, user=None):
        errors = []
        if len(password) < 6:
            errors.append(_('A senha deve ter no minimo 6 caracteres.'))
        if not any(char.isupper() for char in password):
            errors.append(_('A senha deve conter pelo menos 1 letra maiuscula.'))
        if not any(char.isdigit() for char in password):
            errors.append(_('A senha deve conter pelo menos 1 numero.'))
        if not any(not char.isalnum() for char in password):
            errors.append(_('A senha deve conter pelo menos 1 caractere especial.'))

        if errors:
            raise ValidationError(errors)

    def get_help_text(self):
        return _(
            'A senha precisa ter no minimo 6 caracteres, 1 letra maiuscula, 1 numero e 1 caractere especial.'
        )
