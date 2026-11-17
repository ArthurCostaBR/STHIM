from django import forms
from core.normalizers import digits_only
from .models import Motorists


class MotoristsForm(forms.ModelForm):
    phone = forms.CharField(label="Telefone", max_length=15)

    class Meta:
        model = Motorists
        fields = ["name", "cpf", "phone"]

    def clean_phone(self):
        return digits_only(self.cleaned_data["phone"])