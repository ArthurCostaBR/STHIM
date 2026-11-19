"""Fábricas de objetos para os testes automatizados.

Cada função cria um objeto válido com valores padrão únicos; qualquer campo
pode ser sobrescrito por argumento nomeado.
"""
import datetime
import itertools
from django.contrib.auth import get_user_model
from django.contrib.messages import get_messages
from django.utils import timezone
from core.validators import _append_verification_digit

_seq = itertools.count(1)

PASSWORD = "SenhaForte!2026"


def next_id() -> int:
    return next(_seq)


def make_cpf(n: int | None = None) -> str:
    """Gera um CPF válido (apenas dígitos) e único para o número informado."""
    n = next_id() if n is None else n
    base = f"{n % 10**9:09d}"
    if len(set(base)) == 1:
        base = f"1{base[1:-1]}2"
    return _append_verification_digit(_append_verification_digit(base))


def make_sus(n: int | None = None) -> str:
    n = next_id() if n is None else n
    return f"7{n:014d}"


def make_plate(n: int | None = None) -> str:
    n = next_id() if n is None else n
    letters = "".join(chr(ord("A") + (n // 26**i) % 26) for i in (2, 1, 0))
    return f"{letters}{n % 10000:04d}"


def today() -> datetime.date:
    return timezone.localdate()


def days(offset: int) -> datetime.date:
    return today() + datetime.timedelta(days=offset)


def messages_of(response) -> list[str]:
    return [str(m) for m in get_messages(response.wsgi_request)]


def create_user(sector="marcacao", **kwargs):
    from accounts.models import User

    n = next_id()
    defaults = {
        "username": f"Usuário {n}",
        "cpf": make_cpf(n),
        "sector": sector,
        "is_active": True,
    }
    defaults.update(kwargs)
    password = defaults.pop("password", PASSWORD)
    return get_user_model().objects.create_user(password=password, **defaults)


def create_patient(**kwargs):
    from patients.models import Patient

    n = next_id()
    defaults = {
        "name": f"Paciente {n}",
        "cpf": make_cpf(n),
        "birth_date": datetime.date(1980, 1, 1),
        "phone": "21987654321",
        "sex": "f",
        "color": "parda",
        "city": "Rio de Janeiro",
        "cep": "20000000",
        "street": "Rua A",
        "neighborhood": "Centro",
        "house_number": "10",
    }
    defaults.update(kwargs)
    if "registered_by" not in defaults:
        defaults["registered_by"] = create_user()
    return Patient.objects.create(**defaults)


def create_vehicle(**kwargs):
    from fleet.models import Vehicle

    defaults = {"vehicle_type": "van", "plate": make_plate(), "seats": 10}
    defaults.update(kwargs)
    return Vehicle.objects.create(**defaults)


def create_motorist(**kwargs):
    from motorists.models import Motorists

    n = next_id()
    defaults = {"name": f"Motorista {n}", "cpf": make_cpf(n), "phone": "2133334444"}
    defaults.update(kwargs)
    return Motorists.objects.create(**defaults)


def create_appointment(companions=(), **kwargs):
    from appointments.models import Appointment

    defaults = {
        "region": "niteroi",
        "destination": "Hospital Central",
        "boarding_place": "Praça da Matriz",
        "neighborhood": "Centro",
        "date": days(1),
        "appointment_time": datetime.time(9, 0),
        "has_comorbidity": False,
        "notes": "",
    }
    defaults.update(kwargs)
    if "patient" not in defaults:
        defaults["patient"] = create_patient()
    if "registered_by" not in defaults:
        defaults["registered_by"] = defaults["patient"].registered_by
    appointment = Appointment.objects.create(**defaults)
    if companions:
        appointment.companions.set(companions)
    return appointment


def create_route(appointments=(), **kwargs):
    from routes.models import Route

    defaults = {
        "date": days(1),
        "departure_time": datetime.time(6, 30),
        "region": "niteroi",
    }
    defaults.update(kwargs)
    if "vehicle" not in defaults:
        defaults["vehicle"] = create_vehicle()
    if "motorist" not in defaults:
        defaults["motorist"] = create_motorist()
    if "registered_by" not in defaults:
        defaults["registered_by"] = create_user("administracao")
    route = Route.objects.create(**defaults)
    for appointment in appointments:
        appointment.route = route
        appointment.save(update_fields=["route"])
    return route
