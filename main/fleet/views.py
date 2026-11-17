from django.contrib import messages
from django.db.models import ProtectedError
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from accounts.access import Feature, feature_required
from .forms import VehicleForm
from .models import Vehicle

@feature_required(Feature.FLEET)
def vehicle_manage_view(request, pk=None):
    editing = get_object_or_404(Vehicle, pk=pk) if pk else None
    form = VehicleForm(request.POST or None, instance=editing)

    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(
            request, "Veículo atualizado." if editing else "Veículo cadastrado."
        )
        return redirect("fleet:manage")

    return render(request, "fleet/manage.html", {
        "form": form,
        "editing": editing,
        "locked": form.locked,
        "vehicles": Vehicle.objects.all(),
    })


@feature_required(Feature.FLEET)
def vehicle_delete_view(request, pk):
    vehicle = get_object_or_404(Vehicle, pk=pk)

    if vehicle.is_assigned():
        messages.error(
            request,
            "Este veículo está designado em uma rota ativa e não pode ser excluído.",
        )
        return redirect("fleet:manage")

    if request.method == "POST":
        try:
            vehicle.delete()
        except ProtectedError:
            messages.error(
                request,
                "Este veículo está designado em uma rota e não pode ser excluído.",
            )
        else:
            messages.success(request, "Veículo excluído.")
        return redirect("fleet:manage")

    return render(request, "core/confirm_delete.html", {
        "heading": "Excluir veículo",
        "label": str(vehicle),
        "cancel_url": reverse("fleet:manage"),
    })