from django import forms
from django.db.models import Q
from django.utils import timezone
from appointments.models import Appointment
from core.choices import Region
from fleet.models import Vehicle
from patients.models import Patient
from .models import Route

REGION_CHOICES = [("", "Todas")] + list(Region.choices)

class RouteForm(forms.ModelForm):
    date = forms.DateField(widget=forms.HiddenInput)
    appointments = forms.ModelMultipleChoiceField(
        queryset=Appointment.objects.none(),
        widget=forms.CheckboxSelectMultiple,
        label="Pacientes agendados",
        error_messages={"required": "Selecione ao menos um agendamento."},
    )

    class Meta:
        model = Route
        fields = ["vehicle", "motorist", "departure_time", "region", "date"]
        widgets = {
            "departure_time": forms.TimeInput(attrs={"type": "time"}, format="%H:%M"),
        }

    def __init__(self, *args, route_date, **kwargs):
        super().__init__(*args, **kwargs)
        self.route_date = route_date

        self.fields["vehicle"].queryset = Vehicle.objects.filter(is_operational=True)
        self.fields["vehicle"].label_from_instance = lambda v: f"{v} – {v.seats} vagas"
        self.fields["motorist"].label_from_instance = lambda m: m.name
        self.fields["appointments"].queryset = self._base_queryset()

        if self.instance.pk:
            self.fields["date"].disabled = True  # para mudar a data, exclua e recrie a rota
        else:
            self.initial["date"] = route_date

    def _base_queryset(self):
        query = Q(route__isnull=True)
        if self.instance.pk:
            query |= Q(route=self.instance)
        return (
            Appointment.objects.upcoming()
            .filter(query)
            .select_related("patient")
            .prefetch_related("companions")
        )

    def available_options(self, region="", search=""):
        shown = Q(date=self.route_date, route__isnull=True)
        if region:
            shown &= Q(region=region)
        if search:
            shown &= Q(patient__in=Patient.objects.search(search).values("pk"))
        if self.instance.pk:
            shown |= Q(route=self.instance)  # nunca esconde o que já está na rota
        return self.fields["appointments"].queryset.filter(shown)

    def selected_ids(self):
        if self.is_bound:
            raw = self.data.getlist("appointments")
        elif self.instance.pk:
            raw = list(self.instance.appointments.values_list("pk", flat=True))
        else:
            raw = []
        return {int(value) for value in raw if str(value).isdigit()}

    def clean_date(self):
        date = self.cleaned_data["date"]
        if date != self.route_date:
            raise forms.ValidationError(
                "A data da rota deve ser a mesma da busca de agendamentos."
            )
        if date < timezone.localdate():
            raise forms.ValidationError("A data da rota não pode ser no passado.")
        return date

    def clean(self):
        cleaned = super().clean()
        date = cleaned.get("date")
        vehicle = cleaned.get("vehicle")
        appointments = list(cleaned.get("appointments") or [])

        if date and any(a.date != date for a in appointments):
            self.add_error(
                "appointments",
                f"Todos os agendamentos devem ser da data da rota ({date:%d/%m/%Y}).",
            )
        elif vehicle and appointments:
            people = sum(1 + len(a.companions.all()) for a in appointments)
            if people > vehicle.seats:
                self.add_error(
                    "vehicle",
                    f"A rota tem {people} pessoas (pacientes e acompanhantes), "
                    f"mas o veículo tem apenas {vehicle.seats} vagas.",
                )
        return cleaned


class AvailableAppointmentFilterForm(forms.Form):
    date = forms.DateField(
        label="Data da viagem",
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
    )
    region = forms.ChoiceField(
        label="Região do agendamento", required=False, choices=REGION_CHOICES
    )
    q = forms.CharField(label="Pesquisar paciente", required=False)

    def clean_date(self):
        date = self.cleaned_data["date"]
        if date and date < timezone.localdate():
            raise forms.ValidationError("A data da rota não pode ser no passado.")
        return date


class RouteFilterForm(forms.Form):
    date = forms.DateField(
        label="Data",
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
    )
    region = forms.ChoiceField(label="Região", required=False, choices=REGION_CHOICES)
    time = forms.ChoiceField(label="Horário", required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        times = (
            Route.objects.upcoming()
            .order_by("departure_time")
            .values_list("departure_time", flat=True)
            .distinct()
        )
        self.fields["time"].choices = [("", "Todos")] + [
            (t.strftime("%H:%M"), t.strftime("%H:%M")) for t in times
        ]

    def clean_date(self):
        date = self.cleaned_data["date"]
        if date and date < timezone.localdate():
            raise forms.ValidationError("Não é possível pesquisar rotas com datas passadas.")
        return date