from django.db import models
from django.contrib.auth.models import AbstractUser
from core.fields import CPFField

class Sector(models.TextChoices):
    ADMINISTRACAO = "administracao", "Administração"
    MARCACAO = "marcacao", "Marcação"
    GESTAO = "gestao", "Gestão"

class User(AbstractUser):

    # Public fields
    username = models.CharField(unique=False, max_length=150)
    cpf = CPFField(unique=True)
    sector = models.CharField(choices=Sector.choices)

    # Private fields
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    USERNAME_FIELD = "cpf"
    REQUIRED_FIELDS = ["username", "sector"]
