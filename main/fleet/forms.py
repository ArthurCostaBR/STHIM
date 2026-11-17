from django import forms
from core.normalizers import plate_normalizer
from .models import Vehicle

class VehicleForm(forms.ModelForm):
    LOCKED_FIELDS = ("vehicle_type", "seats", "plate")

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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.locked = bool(self.instance.pk and self.instance.is_assigned())
        if self.locked:
            for name in self.LOCKED_FIELDS:
                self.fields[name].disabled = True

    def clean_plate(self):
        return plate_normalizer(self.cleaned_data["plate"])