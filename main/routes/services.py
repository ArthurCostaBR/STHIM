import logging
from django.contrib import messages
from django.db import transaction
from django.utils import timezone
from appointments.models import Appointment
from .models import Route, TransportRecord

logger = logging.getLogger(__name__)

class AssignmentConflict(Exception):
    """A selected appointment has already been included in another route."""


def build_records(route):
    vehicle, motorist = route.vehicle, route.motorist
    base = {
        "route_id": route.pk,
        "route_date": route.date,
        "departure_time": route.departure_time,
        "region": route.region,
        "vehicle_type": vehicle.get_vehicle_type_display(),
        "vehicle_plate": vehicle.plate,
        "motorist_name": motorist.name,
    }
    records = []
    appointments = route.appointments.select_related("patient").prefetch_related("companions")
    for appointment in appointments:
        trip = {
            "destination": appointment.destination,
            "boarding_place": appointment.boarding_place,
            "appointment_time": appointment.appointment_time,
            "has_comorbidity": appointment.has_comorbidity,
            "notes": appointment.notes,
        }
        people = [(appointment.patient, False)]
        people += [(companion, True) for companion in appointment.companions.all()]
        for person, is_companion in people:
            records.append(
                TransportRecord(
                    **base,
                    **trip,
                    is_companion=is_companion,
                    person_id=person.pk,
                    name=person.name,
                    cpf=person.cpf,
                    sus=person.sus,
                    birth_date=person.birth_date,
                    phone=person.phone,
                    sex=person.sex,
                    color=person.color,
                    city=person.city,
                    cep=person.cep,
                    street=person.street,
                    neighborhood=person.neighborhood,
                    house_number=person.house_number,
                )
            )
    return records


def freeze_due_routes(today=None, *, wait=False) -> int:
    today = today or timezone.localdate()
    frozen = 0

    due = Route.objects.filter(date__lt=today)
    if due.exists():
        with transaction.atomic():
            routes = due.select_related("vehicle", "motorist").select_for_update(
                skip_locked=not wait, of=("self",)
            )
            for route in routes:
                TransportRecord.objects.bulk_create(
                    build_records(route), ignore_conflicts=True
                )
                route.appointments.all().delete()  # antes da rota, por causa do SET_NULL
                route.delete()
                frozen += 1

    Appointment.objects.filter(date__lt=today, route__isnull=True).delete()
    return frozen


def ensure_history(request) -> bool:
    try:
        freeze_due_routes(wait=True)
    except Exception:
        logger.exception("Falha ao converter rotas concluídas em histórico")
        messages.error(
            request,
            "Não foi possível preservar o histórico das rotas concluídas. "
            "A operação não foi realizada.",
        )
        return False
    return True


def assign_appointments(route, appointments):
    ids = [appointment.pk for appointment in appointments]
    locked = Appointment.objects.select_for_update().filter(pk__in=ids)
    if any(a.route_id not in (None, route.pk) for a in locked):
        raise AssignmentConflict
    route.appointments.exclude(pk__in=ids).update(route=None)
    Appointment.objects.filter(pk__in=ids).update(route=route)