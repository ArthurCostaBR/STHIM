from django import forms
from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.forms import UserCreationForm
from core.normalizers import cpf_normalizer

User = get_user_model()

class SignupForm(UserCreationForm):
    class Meta:
        model = User
        fields = ["cpf", "username", "sector", "password1", "password2"]

    def clean_username(self):
        return self.cleaned_data["username"]


class LoginForm(forms.Form):
    cpf = forms.CharField(label="CPF", max_length=14)
    password = forms.CharField(label="Senha", widget=forms.PasswordInput())

    def __init__(self, request=None, *args, **kwargs):
        self.request = request
        self.user = None
        super().__init__(*args, **kwargs)

    def clean_cpf(self):
        return cpf_normalizer(self.cleaned_data["cpf"])

    def clean(self):
        cleaned_data = super().clean()
        cpf = cleaned_data.get("cpf")
        password = cleaned_data.get("password")

        if cpf and password:
            self.user = authenticate(self.request, username=cpf, password=password)
            if self.user is None:
                raise forms.ValidationError("CPF ou senha inválidos.")
        return cleaned_data
