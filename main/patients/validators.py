from django.core.exceptions import ValidationError
from django.utils import timezone
import re

def validate_not_future(value):
    if value > timezone.localdate():
        raise ValidationError("A data de nascimento não pode estar no futuro.", code="future_date")

def phone_validator(value):
    if re.fullmatch(r"\d{10,11}", value) is None:
        raise ValidationError("O telefone deve ter 10 ou 11 dígitos.", code="invalid_phone")

def cep_validator(value):
    if re.fullmatch(r"\d{8}", value) is None:
        raise ValidationError("O CEP deve ter 8 dígitos.", code="invalid_cep")

def sus_validator(value):
    if re.fullmatch(r"\d{15}", value) is None:
        raise ValidationError("O número do SUS deve ter 15 dígitos.", code="invalid_sus")

def house_number_validator(value):
    if re.search(r"\d", value) is None:
        raise ValidationError("O número da casa deve conter ao menos um dígito.", code="invalid_house_number")