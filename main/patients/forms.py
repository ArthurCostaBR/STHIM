from django import forms
from core.normalizers import digits_only
from .models import Patient

class PatientForm(forms.ModelForm):
    sus = forms.CharField(label="SUS", max_length=20, required=False)
    phone = forms.CharField(label="Telefone", max_length=15)
    cep = forms.CharField(label="CEP", max_length=9)

    class Meta:
        model = Patient
        fields = [
            "name", "cpf", "sus", "birth_date", "phone", "sex",
            "color", "city", "cep", "street", "neighborhood", "house_number",
        ]
        labels = {
            "name": "Nome completo",
            "cpf": "CPF",
            "birth_date": "Data de nascimento",
            "sex": "Sexo",
            "color": "Cor",
            "city": "Cidade",
            "street": "Endereço",
            "neighborhood": "Bairro",
            "house_number": "Número",
        }
        widgets = {
            "birth_date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
        }

    def clean_phone(self):
        return digits_only(self.cleaned_data["phone"])

    def clean_cep(self):
        return digits_only(self.cleaned_data["cep"])

    def clean_sus(self):
        return digits_only(self.cleaned_data["sus"]) or None