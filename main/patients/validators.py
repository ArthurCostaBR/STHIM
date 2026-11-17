import re
from django.core.exceptions import ValidationError
from django.utils import timezone
from core.validators import phone_validator

def validate_not_future(value):
    if value > timezone.localdate():
        raise ValidationError(
            "A data de nascimento não pode estar no futuro.", code="future_date"
        )

def cep_validator(value):
    if not re.fullmatch(r"[0-9]{8}", value):
        raise ValidationError("O CEP deve ter 8 dígitos.", code="invalid_cep")

def sus_validator(value):
    if not re.fullmatch(r"[0-9]{15}", value):
        raise ValidationError("O número do SUS deve ter 15 dígitos.", code="invalid_sus")