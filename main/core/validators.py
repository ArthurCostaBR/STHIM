from django.core.exceptions import ValidationError
import re

def validate_cpf(cpf: str) -> None:
    if not cpf:
        raise ValidationError("O campo CPF é obrigatório.", code="empty_cpf")

    if not re.fullmatch(r"[0-9]{11}", cpf) or len(set(cpf)) == 1:
        raise ValidationError("CPF inválido.", code="invalid_cpf")

    generated_cpf = _append_verification_digit(cpf[:9])
    generated_cpf = _append_verification_digit(generated_cpf)

    if generated_cpf != cpf:
        raise ValidationError("CPF inválido.", code="invalid_cpf")

def _append_verification_digit(partial_cpf: str) -> str:
        total = 0

        for index, multiplier in enumerate(
            range(len(partial_cpf) + 1, 1, -1)
        ):
            total += int(partial_cpf[index]) * multiplier

        digit = 11 - (total % 11)
        digit = digit if digit <= 9 else 0

        return f"{partial_cpf}{digit}"

def phone_validator(value: str) -> None:
    if not re.fullmatch(r"[0-9]{10,11}", value):
        raise ValidationError("O telefone deve ter 10 ou 11 dígitos.", code="invalid_phone")