from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import get_user_model

User = get_user_model()

class SignupForm(UserCreationForm):
    class Meta:
        model = User
        fields = ["registration", "username", "password1", "password2"]

class LoginForm(forms.Form):
    registration = forms.CharField(
        label="Matrícula",
        max_length=100,
        )
    
    password = forms.CharField(
        label="Senha",
        widget=forms.PasswordInput(),
    )