from django import forms
from core.normalizers import plate_normalizer
from .models import Vehicle

class VehicleForm(forms.ModelForm):
    plate = forms.CharField(label="Placa", max_length=8)

    class Meta:
        model = Vehicle
        fields = ["vehicle_type", "seats", "plate"]
        labels = {
            "vehicle_type": "Tipo de veículo",
            "seats": "Quantidade de vagas",
        }

    def clean_plate(self):
        return plate_normalizer(self.cleaned_data["plate"])