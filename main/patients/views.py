from django.contrib import messages
from .models import Patient
from accounts.access import Feature, feature_required
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
from core.normalizers import digits_only
from .forms import PatientForm

@feature_required(Feature.PATIENTS)
def patient_manage_view(request, pk=None):
    editing = get_object_or_404(Patient, pk=pk) if pk else None
    form = PatientForm(request.POST or None, instance=editing)

    if request.method == "POST" and form.is_valid():
        patient = form.save(commit=False)
        if editing is None:
            patient.registered_by = request.user
        patient.save()
        messages.success(
            request, "Paciente atualizado." if editing else "Paciente cadastrado."
        )
        return redirect("patients:manage")

    query = request.GET.get("q", "").strip()
    patients = Patient.objects.all()
    if query:
        filters = Q(name__icontains=query)
        digits = digits_only(query)
        if digits:
            filters |= Q(cpf__startswith=digits)
            filters |= Q(sus__startswith=digits)
        patients = patients.filter(filters)

    return render(request, "patients/manage.html", {
        "form": form,
        "editing": editing,
        "patients": patients,
        "q": query,
    })


@feature_required(Feature.PATIENTS)
@require_POST
def patient_delete_view(request, pk):
    get_object_or_404(Patient, pk=pk).delete()
    messages.success(request, "Paciente excluído.")
    return redirect("patients:manage")