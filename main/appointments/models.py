from django.conf import settings
from django.db import models
from django.utils import timezone
from core.choices import Region
from patients.models import Patient

class AppointmentQuerySet(models.QuerySet):
    def upcoming(self):
        return self.filter(date__gte=timezone.localdate())

    def search(self, text):
        if not (text or "").strip():
            return self
        return self.filter(patient__in=Patient.objects.search(text).values("pk"))

class Appointment(models.Model):
    patient = models.ForeignKey(
        Patient,
        on_delete=models.PROTECT,
        related_name="appointments",
        verbose_name="Paciente",
    )
    companions = models.ManyToManyField(
        Patient,
        blank=True,
        related_name="companion_appointments",
        verbose_name="Acompanhantes",
    )
    region = models.CharField("Região", max_length=20, choices=Region.choices)
    destination = models.CharField("Destino", max_length=150)
    boarding_place = models.CharField("Local de embarque", max_length=150)
    neighborhood = models.CharField("Bairro", max_length=150)
    date = models.DateField("Data da viagem")
    appointment_time = models.TimeField("Horário da consulta")
    has_comorbidity = models.BooleanField("Comorbidade", default=False)
    notes = models.CharField("Observações", max_length=500, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    registered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="registered_appointments",
        editable=False,
    )

    objects = AppointmentQuerySet.as_manager()

    class Meta:
        ordering = ["date", "appointment_time", "patient__name"]
        indexes = [models.Index(fields=["date"])]
        constraints = [
            models.UniqueConstraint(
                fields=["patient", "date"],
                name="one_appointment_per_patient_per_date",
                violation_error_message="Este paciente já possui um agendamento nesta data.",
            )
        ]

    def __str__(self):
        return f"{self.patient.name} – {self.date:%d/%m/%Y}"

    def is_in_route(self) -> bool:
        return False

    def lock_reason(self) -> str | None:
        if self.date < timezone.localdate():
            return
        if self.is_in_route():
            return
        return None