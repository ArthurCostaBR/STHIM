from django.conf import settings
from django.db import models
from core.fields import CPFField
from .validators import sus_validator, phone_validator, cep_validator, validate_not_future, house_number_validator

class Sex(models.TextChoices):
    FEMININO = "f", "Feminino"
    MASCULINO = "m", "Masculino"


class Color(models.TextChoices):
    BRANCA = "branca", "Branca"
    PRETA = "preta", "Preta"
    PARDA = "parda", "Parda"
    AMARELA = "amarela", "Amarela"
    INDIGENA = "indigena", "Indígena"


class Patient(models.Model):

    # Personal public fields
    name = models.CharField(max_length=150)
    cpf = CPFField(unique=True)
    sus = models.CharField(max_length=15, blank=True, null=True, unique=True, validators=[sus_validator])
    phone = models.CharField(max_length=11, validators=[phone_validator])
    sex = models.CharField(max_length=1, choices=Sex.choices)
    birth_date = models.DateField(validators=[validate_not_future])
    color = models.CharField(max_length=20, choices=Color.choices)

    # Address public fields
    cep = models.CharField(max_length=8, validators=[cep_validator])
    street = models.CharField(max_length=150)
    house_number = models.CharField(max_length=20, validators=[house_number_validator])
    neighborhood = models.CharField(max_length=150)
    city = models.CharField(max_length=100)

    # Private fields
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    registered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="registered_patients",
        editable=False,
    )

    def __str__(self):
        return f"{self.name} ({self.cpf})"