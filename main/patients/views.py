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

@feature_required(Feature.PATIENTS)
def patient_manage_view(request, pk=None):
    editing = get_object_or_404(Patient, pk=pk) if pk else None

    if editing and request.method == "POST" and not ensure_history(request):
        return redirect("fleet:manage")

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
    patients = Patient.objects.search(q)
    if q:
        query = Q(name__icontains=q)
        digits = digits_only(q)
        if digits:
            query |= Q(cpf__startswith=digits) | Q(sus__startswith=digits)
        patients = patients.filter(query)

    return render(request, "patients/manage.html", {
        "form": form,
        "editing": editing,
        "patients": patients,
        "q": q,
    })


@feature_required(Feature.PATIENTS)
def patient_delete_view(request, pk):
    patient = get_object_or_404(Patient, pk=pk)

    blockers = patient.delete_blockers()
    if blockers:
        messages.error(
            request, "Não é possível excluir este paciente: " + "; ".join(blockers) + "."
        )
        return redirect("patients:manage")

    if request.method == "POST":
        if not ensure_history(request):
            return redirect("fleet:manage")

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