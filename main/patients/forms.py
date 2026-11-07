from django import forms
from core.normalizers import digits_only
from .models import Patient

class PatientForm(forms.ModelForm):
    phone = forms.CharField(label="Telefone", max_length=15)
    cep = forms.CharField(label="CEP", max_length=9)
    sus = forms.CharField(label="SUS", max_length=20, required=False)

    class Meta:
        model = Patient
        fields = [
            "name", "cpf", "sus", "phone", "sex",
            "birth_date", "color", "cep",
            "street", "neighborhood", "house_number",
            "city"
        ]
        labels = {
            "name": "Nome completo",
            "cpf": "CPF",
            "sus": "SUS",
            "sex": "Sexo",
            "birth_date": "Data de nascimento",
            "color": "Cor",
            "street": "Rua / Avenida",
            "neighborhood": "Bairro",
            "house_number": "Número",
            "city": "Cidade",
        }
        widgets = {
            "birth_date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
        }

    def clean_phone(self):
        return digits_only(self.cleaned_data["phone"])

    def clean_cep(self):
        return digits_only(self.cleaned_data["cep"])

    def clean_sus(self):
        if digits_only(self.cleaned_data["sus"]) == "":
            return None
        return digits_only(self.cleaned_data["sus"])