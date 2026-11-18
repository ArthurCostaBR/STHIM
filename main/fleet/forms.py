from django import forms
from core.forms import SelectPlaceholderMixin
from core.normalizers import plate_normalizer
from .models import Vehicle

class VehicleForm(SelectPlaceholderMixin, forms.ModelForm):
    plate = forms.CharField(label="Placa", max_length=8)
    is_operational = forms.TypedChoiceField(
        label="Funcionando",
        choices=[(True, "Sim"), (False, "Não")],
        coerce=lambda value: value == "True",
        initial=True,
    )

    class Meta:
        model = Vehicle
        fields = ["vehicle_type", "seats", "is_operational", "plate"]
        labels = {
            "vehicle_type": "Tipo de veículo",
            "seats": "Quantidade de vagas",
        }

    def clean_plate(self):
        return plate_normalizer(self.cleaned_data["plate"])