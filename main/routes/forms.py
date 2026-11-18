from collections import Counter
from django import forms
from django.urls import reverse
from django.utils import timezone
from django.utils.http import urlencode
from appointments.models import Appointment
from core.choices import Region
from core.forms import SelectPlaceholderMixin
from fleet.models import Vehicle
from .models import Route

REGION_CHOICES = [("", "Todas")] + list(Region.choices)


class SelectionFilterForm(forms.Form):
    date = forms.DateField(
        label="Data",
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
    )
    time = forms.ChoiceField(label="Horário", required=False)
    region = forms.ChoiceField(label="Região", required=False, choices=REGION_CHOICES)

    def __init__(self, *args, editing=None, **kwargs):
        super().__init__(*args, **kwargs)
        times = (
            Appointment.objects.upcoming()
            .order_by("appointment_time")
            .values_list("appointment_time", flat=True)
            .distinct()
        )
        self.fields["time"].choices = [("", "Todos")] + [
            (t.strftime("%H:%M"), t.strftime("%H:%M")) for t in times
        ]
        if editing:
            self.fields["date"].disabled = True
            self.initial["date"] = editing.date

    def clean_date(self):
        date = self.cleaned_data["date"]
        if date and date < timezone.localdate():
            raise forms.ValidationError("A data da rota não pode ser no passado.")
        return date


class RouteForm(SelectPlaceholderMixin, forms.ModelForm):
    date = forms.DateField(
        label="Data",
        disabled=True,
        widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
    )

    class Meta:
        model = Route
        fields = ["vehicle", "date", "departure_time", "region", "motorist"]
        widgets = {
            "departure_time": forms.TimeInput(attrs={"type": "time"}, format="%H:%M"),
        }

    def __init__(self, *args, route_date, appointments, **kwargs):
        super().__init__(*args, **kwargs)
        self.route_date = route_date
        self.appointments = list(appointments)
        self.initial["date"] = route_date

        vehicle = self.fields["vehicle"]
        vehicle.queryset = Vehicle.objects.filter(is_operational=True)
        vehicle.label_from_instance = (
            lambda v: f"{v.get_vehicle_type_display()} | {v.plate} | {v.seats} vagas"
        )
        self.fields["motorist"].label_from_instance = lambda m: m.name

        params = {"date": route_date.isoformat()}
        if self.instance.pk:
            params["route"] = self.instance.pk
        vehicle.widget.attrs.update({
            "data-picker": "",
            "data-search-url": f"{reverse('routes:vehicle_search')}?{urlencode(params)}",
            "data-placeholder": "Adicionar veículo",
        })

        if not self.instance.pk and self.appointments:
            common = Counter(a.region for a in self.appointments).most_common(1)[0][0]
            self.initial.setdefault("region", common)

    def clean_date(self):
        date = self.cleaned_data["date"]
        if date < timezone.localdate():
            raise forms.ValidationError("A data da rota não pode ser no passado.")
        return date

    def clean(self):
        cleaned = super().clean()
        vehicle = cleaned.get("vehicle")
        if vehicle and self.appointments:
            people = sum(1 + len(a.companions.all()) for a in self.appointments)
            if people > vehicle.seats:
                self.add_error(
                    "vehicle",
                    f"A rota tem {people} pessoas (pacientes e acompanhantes), "
                    f"mas o veículo tem apenas {vehicle.seats} vagas.",
                )
        return cleaned


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