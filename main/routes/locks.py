from django.db.models import Q
from django.urls import reverse
from django.utils import timezone
from django.utils.html import format_html, format_html_join
from .models import Route

MAX_LISTED = 5

def active_routes():
    return Route.objects.filter(date__gte=timezone.localdate()).select_related("vehicle")


def routes_of_appointment(appointment):
    if not appointment.route_id:
        return Route.objects.none()
    return active_routes().filter(pk=appointment.route_id)


def routes_of_patient(patient):
    """Rotas ativas em que o paciente está, como paciente ou como acompanhante."""
    return active_routes().filter(
        Q(appointments__patient=patient) | Q(appointments__companions=patient)
    ).distinct()


def routes_of_motorist(motorist):
    return active_routes().filter(motorist=motorist)


def routes_of_vehicle(vehicle):
    return active_routes().filter(vehicle=vehicle)


def blocked_message(action, subject, routes, hint):
    routes = list(routes)
    listed = routes[:MAX_LISTED]
    links = format_html_join(
        ", ",
        '<a href="{}">{}</a>',
        ((reverse("routes:edit", args=[route.pk]), route.name) for route in listed),
    )
    more = (
        format_html(" e mais {}", len(routes) - len(listed))
        if len(routes) > len(listed)
        else ""
    )
    where = "uma rota ativa" if len(routes) == 1 else f"{len(routes)} rotas ativas"
    return format_html(
        "Não é possível {} {} porque está em {}. {}: {}{}.",
        action, subject, where, hint, links, more,
    )