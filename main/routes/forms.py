from django import forms
from django.db.models import Q
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
    time = forms.ChoiceField(label="Horário", required=False)
    region = forms.ChoiceField(label="Região", required=False, choices=REGION_CHOICES)

    def __init__(self, *args, route_date, editing=None, **kwargs):
        super().__init__(*args, **kwargs)
        free = Q(route__isnull=True)
        if editing is not None:
            free |= Q(route=editing)
        times = (
            Appointment.objects.filter(date=route_date)
            .filter(free)
            .order_by("appointment_time")
            .values_list("appointment_time", flat=True)
            .distinct()
        )
        self.fields["time"].choices = [("", "Todos")] + [
            (t.strftime("%H:%M"), t.strftime("%H:%M")) for t in times
        ]


class RouteForm(SelectPlaceholderMixin, forms.ModelForm):
    date = forms.DateField(
        label="Data",
        widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
    )

    class Meta:
        model = Route
        fields = ["vehicle", "date", "departure_time", "region", "motorist"]
        widgets = {
            "departure_time": forms.TimeInput(attrs={"type": "time"}, format="%H:%M"),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:  # os agendamentos são de um dia; a data de uma rota existente não muda
            self.fields["date"].disabled = True

        vehicle = self.fields["vehicle"]
        vehicle.queryset = Vehicle.objects.filter(is_operational=True)
        vehicle.label_from_instance = (
            lambda v: f"{v.get_vehicle_type_display()} | {v.plate} | {v.seats} vagas"
        )
        self.fields["motorist"].label_from_instance = lambda m: m.name

        # Busca de veículo com chip; a data é lida do campo de data na hora da busca
        url = reverse("routes:vehicle_search")
        if self.instance.pk:
            url += "?" + urlencode({"route": self.instance.pk})
        vehicle.widget.attrs.update({
            "data-picker": "",
            "data-search-url": url,
            "data-date-source": self["date"].id_for_label,
            "data-placeholder": "Adicionar veículo",
        })

    def clean_date(self):
        date = self.cleaned_data["date"]
        if date < timezone.localdate():
            raise forms.ValidationError("A data da rota não pode ser no passado.")
        return date

    def clean(self):
        cleaned = super().clean()
        date = cleaned.get("date")
        if date:
            others = Route.objects.filter(date=date)
            if self.instance.pk:
                others = others.exclude(pk=self.instance.pk)
            vehicle, motorist = cleaned.get("vehicle"), cleaned.get("motorist")
            if vehicle and others.filter(vehicle=vehicle).exists():
                self.add_error("vehicle", "Este veículo já está em outra rota nesta data.")
            if motorist and others.filter(motorist=motorist).exists():
                self.add_error("motorist", "Este motorista já está em outra rota nesta data.")
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