from django.contrib.auth import login
from django.shortcuts import redirect, render
from .forms import LoginForm, SignupForm

def signup_view(request):
    form = SignupForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        form.save()
        return redirect("accounts:login")

    return render(request, "signup/signup.html", {"form": form})


def login_view(request):
    form = LoginForm(request, request.POST or None)

    if request.method == "POST" and form.is_valid():
        login(request, form.user)
        return redirect("pages:home")

    return render(request, "login/login.html", {"form": form})
