from django.contrib import messages
from django.contrib.auth import login
from django.shortcuts import redirect, render
from .forms import LoginForm, SignupForm


def csrf_failure(request, reason=""):
    if request.user.is_authenticated:
        messages.warning(request, "O formulário expirou. Tente novamente.")
        return redirect("pages:home")
    messages.warning(request, "Sua sessão expirou, tente novamente.")
    return redirect("accounts:login")

def signup_view(request):
    form = SignupForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        form.save()
        return redirect("accounts:login")

    return render(request, "signup/signup.html", {"form": form})


def login_view(request):
    # Quem já está logado não precisa (nem deve) reenviar o formulário:
    # um token CSRF antigo de outra aba geraria erro 403.
    if request.user.is_authenticated:
        return redirect("pages:home")

    form = LoginForm(request, request.POST or None)

    if request.method == "POST" and form.is_valid():
        login(request, form.user)
        return redirect("pages:home")

    return render(request, "login/login.html", {"form": form})
