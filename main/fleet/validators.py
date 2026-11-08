import re
from django.core.exceptions import ValidationError

def validate_plate(value: str) -> None:
    if not re.fullmatch(r"[A-Z]{3}[0-9][A-Z0-9][0-9]{2}", value):
        raise ValidationError(
            "Placa inválida. Use o formato ABC1234 ou ABC1D23.", code="invalid_plate"
        )

def min_max_validator(value: int) -> None:
    if value < 1 or value > 100:
        raise ValidationError(
            "O número de vagas deve estar entre 1 e 100.", code="invalid_seats"
        )