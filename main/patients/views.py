from django.contrib import messages
from django.db.models import ProtectedError, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from accounts.access import Feature, feature_required
from core.normalizers import digits_only
from .forms import PatientForm
from .models import Patient
from django.db import transaction
from audit.models import AuditLog
from audit.services import log_action
from django.utils import timezone
from routes.services import ensure_history
from django.core.paginator import Paginator
from routes.locks import blocked_message, routes_of_patient

@feature_required(Feature.PATIENTS)
def patient_manage_view(request, pk=None):
    editing = get_object_or_404(Patient, pk=pk) if pk else None

    if editing and _route_lock(request, editing, "alterar"):
        return redirect("patients:manage")

    form = PatientForm(request.POST or None, instance=editing)

    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            patient = form.save(commit=False)
            if editing is None:
                patient.registered_by = request.user
            patient.save()
            log_action(
                request.user,
                AuditLog.Action.UPDATE if editing else AuditLog.Action.CREATE,
                patient,
            )
        messages.success(
            request, "Paciente atualizado." if editing else "Paciente cadastrado."
        )
        return redirect("patients:manage")

    q = request.GET.get("q", "").strip()
    searched = bool(q)
    patients = Patient.objects.search(q) if searched else Patient.objects.none()
    page_obj = Paginator(patients, 25).get_page(request.GET.get("page"))
    params = request.GET.copy()
    params.pop("page", None)

    return render(request, "patients/manage.html", {
        "form": form,
        "editing": editing,
        "page_obj": page_obj,
        "querystring": params.urlencode(),
        "q": q,
        "searched": searched,
    })


@feature_required(Feature.PATIENTS)
def patient_delete_view(request, pk):
    patient = get_object_or_404(Patient, pk=pk)

    if _route_lock(request, patient, "excluir"):
        return redirect("patients:manage")

    blockers = patient.delete_blockers()
    if blockers:
        messages.error(
            request, "Não é possível excluir este paciente: " + "; ".join(blockers) + "."
        )
        return redirect("patients:manage")

    if request.method == "POST":
        if not ensure_history(request):
            return redirect("patients:manage")

        try:
            with transaction.atomic():
                log_action(request.user, AuditLog.Action.DELETE, patient)
                patient.appointments.filter(date__lt=timezone.localdate()).delete()
                patient.delete()
        except ProtectedError:
            messages.error(
                request, "Este paciente possui agendamentos e não pode ser excluído."
            )
        else:
            messages.success(request, "Paciente excluído.")
        return redirect("patients:manage")

    return render(request, "core/confirm_delete.html", {
        "heading": "Excluir paciente",
        "label": str(patient),
        "cancel_url": reverse("patients:manage"),
    })

def _route_lock(request, patient, action):
    routes = routes_of_patient(patient)
    if routes:
        messages.error(request, blocked_message(
            action, f"o paciente {patient.name}", routes,
            "Para continuar, retire o paciente (ou acompanhante) em",
        ))
        return True
    return False