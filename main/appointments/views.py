from django.contrib import messages
from django.core.paginator import Paginator
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from accounts.access import Feature, feature_required
from audit.models import AuditLog
from audit.services import log_action
from .forms import AppointmentFilterForm, AppointmentForm
from .models import Appointment
from django.http import JsonResponse
from patients.models import Patient
from django.utils import timezone
from routes.locks import blocked_message, routes_of_appointment

@feature_required(Feature.SCHEDULE_TRANSPORT)
def appointment_schedule_view(request, pk=None):
    editing = get_object_or_404(Appointment, pk=pk) if pk else None

    if editing and _is_blocked(request, editing, "alterar"):
        return redirect("appointments:manage")

    patient_q = request.GET.get("q", "").strip()
    companion_q = request.GET.get("aq", "").strip()
    form = AppointmentForm(
        request.POST or None,
        instance=editing,
        patient_search=patient_q,
        companion_search=companion_q,
    )

    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            appointment = form.save(commit=False)
            if editing is None:
                appointment.registered_by = request.user
            appointment.save()
            form.save_m2m()
            log_action(
                request.user,
                AuditLog.Action.UPDATE if editing else AuditLog.Action.CREATE,
                appointment,
            )
        messages.success(
            request, "Agendamento atualizado." if editing else "Agendamento cadastrado."
        )
        return redirect("appointments:manage" if editing else "appointments:schedule")

    return render(request, "appointments/schedule.html", {
        "form": form,
        "editing": editing,
        "patient_q": patient_q,
        "companion_q": companion_q,
    })


@feature_required(Feature.APPOINTMENTS)
def appointment_manage_view(request):
    filters = AppointmentFilterForm(request.GET)
    appointments = (
        Appointment.objects.upcoming()
        .select_related("patient")
        .prefetch_related("companions")
    )

    if filters.is_valid():
        data = filters.cleaned_data
        appointments = appointments.search(data["q"])
        if data["date"]:
            appointments = appointments.filter(date=data["date"])
        if data["region"]:
            appointments = appointments.filter(region=data["region"])

    params = request.GET.copy()
    params.pop("page", None)
    page_obj = Paginator(appointments, 25).get_page(request.GET.get("page"))

    return render(request, "appointments/manage.html", {
        "filters": filters,
        "page_obj": page_obj,
        "querystring": params.urlencode(),
    })


@feature_required(Feature.APPOINTMENTS)
def appointment_delete_view(request, pk):
    appointment = get_object_or_404(Appointment, pk=pk)

    if _is_blocked(request, appointment, "excluir"):
        return redirect("appointments:manage")

    if request.method == "POST":
        with transaction.atomic():
            log_action(request.user, AuditLog.Action.DELETE, appointment)
            appointment.delete()
        messages.success(request, "Agendamento excluído.")
        return redirect("appointments:manage")

    return render(request, "core/confirm_delete.html", {
        "heading": "Excluir agendamento",
        "label": str(appointment),
        "cancel_url": reverse("appointments:manage"),
    })

@feature_required(Feature.SCHEDULE_TRANSPORT)
def patient_search_view(request):
    term = request.GET.get("q", "").strip()
    if len(term) < 2:
        return JsonResponse({"results": []})
    patients = Patient.objects.search(term)[:15]
    return JsonResponse({
        "results": [{"id": p.pk, "label": f"{p.name} | {p.document}"} for p in patients]
    })

def _is_blocked(request, appointment, action):
    if appointment.date < timezone.localdate():
        messages.error(
            request, "Este agendamento é de uma data passada e não pode ser alterado."
        )
        return True
    routes = routes_of_appointment(appointment)
    if routes:
        messages.error(request, blocked_message(
            action, "este agendamento", routes, "Para continuar, retire o agendamento em"
        ))
        return True
    return False