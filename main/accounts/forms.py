from django import forms
from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.forms import UserCreationForm
from core.normalizers import digits_only
from .models import Sector

User = get_user_model()

class SignupForm(UserCreationForm):
    class Meta:
        model = User
        fields = ["username", "cpf", "sector", "password1", "password2"]
        labels = {"username": "Nome", "cpf": "CPF", "sector": "Setor"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["password1"].label = "Senha"
        self.fields["password2"].label = "Repita a senha"
        self.fields["sector"].choices = [("", "Setor"), *Sector.choices]

        self.fields["cpf"].widget.attrs.pop("autofocus", None)
        placeholders = {
            "username": "Nome", "cpf": "CPF",
            "password1": "Senha", "password2": "Repita a senha",
        }
        for name, text in placeholders.items():
            self.fields[name].widget.attrs["placeholder"] = text
        self.fields["username"].widget.attrs["autocomplete"] = "name"
        self.fields["cpf"].widget.attrs.update({"autocomplete": "username", "inputmode": "numeric"})
        self.fields["password1"].widget.attrs["autocomplete"] = "new-password"
        self.fields["password2"].widget.attrs["autocomplete"] = "new-password"

    def clean_username(self):
        return self.cleaned_data["username"]

    def clean_cpf(self):
        cpf = digits_only(self.cleaned_data["cpf"])
        if not cpf:
            raise forms.ValidationError("Informe um CPF válido.", code="invalid_cpf")
        return cpf


class LoginForm(forms.Form):
    cpf = forms.CharField(label="CPF", max_length=14)
    password = forms.CharField(label="Senha", widget=forms.PasswordInput())

    def __init__(self, request=None, *args, **kwargs):
        self.request = request
        self.user = None
        super().__init__(*args, **kwargs)
        self.fields["cpf"].widget.attrs.update({
            "placeholder": "CPF", "autocomplete": "username",
            "inputmode": "numeric", "autofocus": True,
        })
        self.fields["password"].widget.attrs.update({
            "placeholder": "Senha", "autocomplete": "current-password",
        })

    def clean_cpf(self):
        cpf = digits_only(self.cleaned_data["cpf"])
        if not cpf:
            raise forms.ValidationError("Informe um CPF válido.", code="invalid_cpf")
        return cpf

    def clean(self):
        cleaned_data = super().clean()
        cpf = cleaned_data.get("cpf")
        password = cleaned_data.get("password")

        if cpf and password:
            self.user = authenticate(self.request, username=cpf, password=password)
            if self.user is None:
                pending = User.objects.filter(cpf=cpf, is_active=False).first()
                if pending and pending.check_password(password):
                    raise forms.ValidationError("Seu cadastro ainda aguarda aprovação.", code="pending_approval")
                raise forms.ValidationError("CPF ou senha inválidos.", code="invalid_credentials")
        return cleaned_data
