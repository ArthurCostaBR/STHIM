from django.shortcuts import render
from . forms import SignupForm, LoginForm
from django.contrib.auth import authenticate, login, get_user_model
from django.http import HttpResponse


def signup_view(request):
    if request.method == "POST":
        form = SignupForm(request.POST)
        
        if form.is_valid():
            User = get_user_model()

            registration = form.cleaned_data.get("registration")

            if User.objects.filter(email__iexact=registration).exists():
                form.add_error("registration", "Registration already in use.")
            else:
                form.save()
                return HttpResponse(f"Welcome {form.cleaned_data.get('username')}!")
        
        return render(request, 'signup/signup.html', context={"form":form})

    else:
        return render(request, 'signup/signup.html', context={"form":SignupForm()})
        

def login_view(request):
    if request.method == "POST":
        form = LoginForm(request.POST)

        if form.is_valid():
            registration = form.cleaned_data.get("registration")
            password = form.cleaned_data.get("password")

            user = authenticate(request, registration=registration, password=password)
        
            if user:
                login(request, user)
                return HttpResponse("OK")

            else:
                form.add_error(None, "Invalid credentials.")

        return render(request, "login/login.html", context={"form": form})

    return render(request, 'login/login.html', context={"form": LoginForm()})