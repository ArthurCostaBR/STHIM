from django import forms
from core.choices import Region
from fleet.models import VehicleType
from routes.models import Route, TransportRecord


class PatientsReportForm(forms.Form):
    COMORBIDITY_CHOICES = [("", "Todos"), ("yes", "Sim"), ("no", "Não")]

    start_date = forms.DateField(
        label="Data inicial",
        widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
    )
    end_date = forms.DateField(
        label="Data final",
        widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
        help_text="Considera apenas rotas já concluídas (até ontem).",
    )
    region = forms.ChoiceField(
        label="Região da rota",
        required=False,
        choices=[("", "Todas")] + list(Region.choices),
    )
    time = forms.ChoiceField(label="Horário de saída", required=False)
    comorbidity = forms.ChoiceField(
        label="Comorbidade", required=False, choices=COMORBIDITY_CHOICES
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # order_by explícito: evita que o Meta.ordering quebre o distinct()
        times = set(
            TransportRecord.objects.order_by("departure_time")
            .values_list("departure_time", flat=True).distinct()
        )
        times |= set(
            Route.objects.order_by("departure_time")
            .values_list("departure_time", flat=True).distinct()
        )
        self.fields["time"].choices = [("", "Todos")] + [
            (t.strftime("%H:%M"), t.strftime("%H:%M")) for t in sorted(times)
        ]

    def clean(self):
        cleaned = super().clean()
        start, end = cleaned.get("start_date"), cleaned.get("end_date")
        if start and end and start > end:
            self.add_error("end_date", "A data final deve ser igual ou posterior à data inicial.")
        return cleaned

    def filter_lines(self):
        data = self.cleaned_data
        lines = []
        if data["region"]:
            lines.append(f"Região da rota: {dict(Region.choices)[data['region']]}")
        if data["time"]:
            lines.append(f"Horário de saída: {data['time']}")
        if data["comorbidity"]:
            lines.append(f"Comorbidade: {dict(self.COMORBIDITY_CHOICES)[data['comorbidity']]}")
        return lines


class FleetReportForm(forms.Form):
    vehicle_type = forms.ChoiceField(
        label="Tipo de veículo",
        required=False,
        choices=[("", "Todos")] + list(VehicleType.choices),
    )