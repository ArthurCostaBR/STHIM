from .validators import min_max_validator, validate_plate
from django.db import models
from django.conf import settings
from django.utils import timezone

class VehicleType(models.TextChoices):
    CAR = "carro", "Carro"
    VAN = "van", "Van"
    MICROBUS = "micro-onibus", "Micro-ônibus"
    BUS = "onibus", "Ônibus"
    AMBULANCE = "ambulancia", "Ambulância"


class Vehicle(models.Model):

    # Public fields
    vehicle_type = models.CharField(max_length=20, choices=VehicleType.choices)
    plate = models.CharField(
        max_length=7,
        unique=True,
        error_messages={"unique": "Já existe um veículo com esta placa."},
        validators=[validate_plate]
    )
    seats = models.PositiveSmallIntegerField(validators=[min_max_validator])

    # Private fields
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_operational = models.BooleanField("Funcionando", default=True)

    def is_assigned(self) -> bool:
        return self.routes.filter(date__gte=timezone.localdate()).exists()

    def __str__(self):
        return f"{self.get_vehicle_type_display()} ({self.plate})"

    def is_assigned(self) -> bool:
        return False