from django.contrib import messages
from django.db.models import ProtectedError
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from accounts.access import Feature, feature_required
from routes.locks import blocked_message, routes_of_vehicle
from routes.services import ensure_history
from .forms import VehicleForm
from .models import Vehicle

def _route_lock(request, vehicle, action):
    routes = routes_of_vehicle(vehicle)
    if routes:
        messages.error(request, blocked_message(
            action, f"o veículo {vehicle.plate}", routes,
            "Para continuar, troque o veículo em",
        ))
        return True
    return False


@feature_required(Feature.FLEET)
def vehicle_manage_view(request, pk=None):
    editing = get_object_or_404(Vehicle, pk=pk) if pk else None

    if editing and _route_lock(request, editing, "alterar"):
        return redirect("fleet:manage")

    if editing and request.method == "POST" and not ensure_history(request):
        return redirect("fleet:manage")

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
        "vehicles": Vehicle.objects.all(),
    })


@feature_required(Feature.FLEET)
def vehicle_delete_view(request, pk):
    vehicle = get_object_or_404(Vehicle, pk=pk)

    if _route_lock(request, vehicle, "excluir"):
        return redirect("fleet:manage")

    if request.method == "POST":
        if not ensure_history(request):
            return redirect("fleet:manage")
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