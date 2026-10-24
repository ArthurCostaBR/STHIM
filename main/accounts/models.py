from django.db import models
from django.contrib.auth.models import AbstractUser

class User(AbstractUser):
    username = models.CharField(unique=False, max_length=150)

    registration = models.CharField(unique=True, max_length=100)

    USERNAME_FIELD = "registration"
    REQUIRED_FIELDS = ["username"]