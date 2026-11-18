from django.conf import settings
from django.db import models
from django.utils import timezone
from core.choices import Region
from fleet.models import Vehicle
from motorists.models import Motorists
from patients.models import Color, Sex

class RouteQuerySet(models.QuerySet):
    def upcoming(self):
        return self.filter(date__gte=timezone.localdate())


class Route(models.Model):
    date = models.DateField("Data da viagem", db_index=True)
    departure_time = models.TimeField("Horário de saída")
    region = models.CharField("Região", max_length=20, choices=Region.choices)
    vehicle = models.ForeignKey(
        Vehicle, on_delete=models.PROTECT, related_name="routes", verbose_name="Veículo"
    )
    motorist = models.ForeignKey(
        Motorists, on_delete=models.PROTECT, related_name="routes", verbose_name="Motorista"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    registered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="registered_routes",
        editable=False,
    )

    objects = RouteQuerySet.as_manager()

    class Meta:
        ordering = ["date", "departure_time"]
        constraints = [
            models.UniqueConstraint(
                fields=["vehicle", "date"],
                name="one_route_per_vehicle_per_date",
                violation_error_message="Este veículo já está em outra rota nesta data.",
            ),
            models.UniqueConstraint(
                fields=["motorist", "date"],
                name="one_route_per_motorist_per_date",
                violation_error_message="Este motorista já está em outra rota nesta data.",
            ),
        ]

    def __str__(self):
        return self.name

    @property
    def name(self) -> str:
        return (
            f"{self.date:%d/%m/%Y} | {self.get_region_display()} - "
            f"{self.departure_time:%H:%M} | {self.vehicle.plate}"
        )

    @property
    def capacity(self) -> int:
        return self.vehicle.seats

    @property
    def is_concluded(self) -> bool:
        return self.date < timezone.localdate()


class TransportRecord(models.Model):

    # Origin
    route_id = models.PositiveIntegerField(db_index=True)
    person_id = models.PositiveIntegerField()
    is_companion = models.BooleanField(default=False)

    # route
    route_date = models.DateField(db_index=True)
    departure_time = models.TimeField()
    region = models.CharField(max_length=20, choices=Region.choices)
    vehicle_type = models.CharField(max_length=50)
    vehicle_plate = models.CharField(max_length=7)
    motorist_name = models.CharField(max_length=150)

    # Travel
    destination = models.CharField(max_length=150)
    boarding_place = models.CharField(max_length=150)
    appointment_time = models.TimeField()
    has_comorbidity = models.BooleanField()
    notes = models.CharField(max_length=500, blank=True)

    # Patient
    name = models.CharField(max_length=150)
    cpf = models.CharField(max_length=11, null=True, blank=True)
    sus = models.CharField(max_length=15, null=True, blank=True)
    birth_date = models.DateField()
    phone = models.CharField(max_length=11)
    sex = models.CharField(max_length=1, choices=Sex.choices)
    color = models.CharField(max_length=20, choices=Color.choices)
    city = models.CharField(max_length=100)
    cep = models.CharField(max_length=8)
    street = models.CharField(max_length=150)
    neighborhood = models.CharField(max_length=150)
    house_number = models.CharField(max_length=20)

    class Meta:
        ordering = ["route_date", "departure_time", "route_id", "is_companion", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["route_id", "person_id"], name="one_record_per_person_per_route"
            )
        ]

    def __str__(self):
        return f"{self.route_date:%d/%m/%Y} | {self.name}"