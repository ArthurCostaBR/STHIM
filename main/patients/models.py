from django.conf import settings
from django.db import models
from django.db.models import Q
from core.fields import CPFField
from .validators import cep_validator, sus_validator, validate_not_future
from core.validators import phone_validator

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

    # Public fields
    name = models.CharField(max_length=150)
    cpf = CPFField(unique=True, null=True, blank=True)
    sus = models.CharField(max_length=15, unique=True, null=True, blank=True, validators=[sus_validator])
    birth_date = models.DateField(validators=[validate_not_future])
    phone = models.CharField(max_length=11, validators=[phone_validator])
    sex = models.CharField(max_length=1, choices=Sex.choices)
    color = models.CharField(max_length=20, choices=Color.choices)
    city = models.CharField(max_length=100)
    cep = models.CharField(max_length=8, validators=[cep_validator])
    street = models.CharField(max_length=150)
    neighborhood = models.CharField(max_length=150)
    house_number = models.CharField(max_length=20)

    # Private fields
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    registered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="registered_patients",
        editable=False,
    )

    class Meta:
        ordering = ["name"]
        constraints = [
            models.CheckConstraint(
                condition=Q(cpf__isnull=False) | Q(sus__isnull=False),
                name="patient_has_cpf_or_sus",
                violation_error_message="Informe o CPF ou o SUS.",
            )
        ]

    def __str__(self):
        return f"{self.name} ({self.cpf or self.sus})"

    def delete_blockers(self) -> list[str]:
        return []