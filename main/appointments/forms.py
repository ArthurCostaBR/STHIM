from django import forms
from django.db.models import Q
from django.utils import timezone
from core.choices import Region
from core.forms import YesNoField
from patients.models import Patient
from .models import Appointment
from django.urls import reverse

class PatientChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        return f"{obj.name} | {obj.document}"


class PatientMultipleChoiceField(forms.ModelMultipleChoiceField):
    def label_from_instance(self, obj):
        return f"{obj.name} | {obj.document}"


class AppointmentForm(forms.ModelForm):
    patient = PatientChoiceField(
        queryset=Patient.objects.none(),
        label="Paciente",
        empty_label="Pesquise e selecione o paciente",
    )

    has_comorbidity = YesNoField(label="Comorbidade")

    class Meta:
        model = Appointment
        fields = [
            "patient", "region", "destination", "boarding_place", "neighborhood",
            "date", "appointment_time", "has_comorbidity", "notes", "companions",
        ]
        widgets = {
            "date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "appointment_time": forms.TimeInput(attrs={"type": "time"}, format="%H:%M"),
            "notes": forms.Textarea(attrs={"rows": 2}),
        }

    def __init__(self, *args, patient_search="", companion_search="", **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["patient"].queryset = self._options(
            patient_search, self._selected("patient")
        )
        self.fields["companions"].queryset = self._options(
            companion_search, self._selected("companions")
        )

        search_url = reverse("appointments:patient_search")
        for name, hint in (("patient", "Pesquisar paciente"), ("companions", "Adicionar acompanhantes")):
            self.fields[name].widget.attrs.update({
                "data-picker": "",
                "data-search-url": search_url,
                "data-placeholder": hint,
            })

    def _selected(self, name):
        if self.is_bound:
            raw = self.data.getlist(self.add_prefix(name))
        elif self.instance.pk:
            if name == "patient":
                raw = [self.instance.patient_id]
            else:
                raw = list(self.instance.companions.values_list("pk", flat=True))
        else:
            raw = []
        return {int(value) for value in raw if str(value).isdigit()}

    @staticmethod
    def _options(search, selected_ids):
        query = Q(pk__in=selected_ids)
        if search:
            query |= Q(pk__in=Patient.objects.search(search).values("pk"))
        return Patient.objects.filter(query)

    def _busy_ids(self, date):
        others = Appointment.objects.filter(date=date)
        if self.instance.pk:
            others = others.exclude(pk=self.instance.pk)
        ids = set(others.values_list("patient_id", flat=True))
        ids.update(others.values_list("companions", flat=True))
        ids.discard(None)
        return ids

    def clean_date(self):
        date = self.cleaned_data["date"]
        if date < timezone.localdate():
            raise forms.ValidationError("A data da viagem não pode ser no passado.")
        return date

    def clean(self):
        cleaned = super().clean()
        patient = cleaned.get("patient")
        date = cleaned.get("date")
        companions = list(cleaned.get("companions") or [])

        if patient and patient in companions:
            self.add_error("companions", "O paciente não pode ser acompanhante dele mesmo.")
            companions = [c for c in companions if c != patient]

        if date:
            busy = self._busy_ids(date)
            if patient and patient.pk in busy:
                self.add_error(
                    "patient", f"{patient.name} já está em um agendamento nesta data."
                )
            taken = [c.name for c in companions if c.pk in busy]
            if taken:
                self.add_error(
                    "companions",
                    "Já estão em outro agendamento nesta data: " + ", ".join(taken) + ".",
                )
        return cleaned


class AppointmentFilterForm(forms.Form):
    q = forms.CharField(label="Pesquisar paciente agendado", required=False)
    date = forms.DateField(
        label="Data",
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
    )
    region = forms.ChoiceField(
        label="Região",
        required=False,
        choices=[("", "Todas")] + list(Region.choices),
    )