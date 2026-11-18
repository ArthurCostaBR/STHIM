from django.db import models
from core.fields import CPFField
from core.validators import phone_validator
from django.utils import timezone

class Motorists(models.Model):
    
    # Public fields
    name = models.CharField("Nome completo", max_length=150)
    cpf = CPFField(verbose_name="CPF",unique=True,error_messages={"unique": "Já existe um motorista com este CPF."},)
    phone = models.CharField("Telefone", max_length=11, validators=[phone_validator])

    # Private fields
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.cpf})"

    def delete_blockers(self) -> list[str]:
        if self.routes.filter(date__gte=timezone.localdate()).exists():
            return ["está designado em uma rota ativa"]
        return []