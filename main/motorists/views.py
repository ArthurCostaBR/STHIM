from django.contrib import messages
from django.db.models import ProtectedError, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from accounts.access import Feature, feature_required
from core.normalizers import digits_only
from .forms import MotoristsForm
from .models import Motorists

@feature_required(Feature.MOTORISTS)
def motorists_manage_view(request, pk=None):
    editing = get_object_or_404(Motorists, pk=pk) if pk else None
    form = MotoristsForm(request.POST or None, instance=editing)

    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(
            request, "Motorista atualizado." if editing else "Motorista cadastrado."
        )
        return redirect("motorists:manage")

    q = request.GET.get("q", "").strip()
    drivers = Motorists.objects.all()

    if q:
        query = Q(name__icontains=q)
        digits = digits_only(q)
        if digits:
            query |= Q(cpf__startswith=digits)
        drivers = drivers.filter(query)

    return render(request, "motorists/manage.html", {
        "form": form,
        "editing": editing,
        "motorists": drivers,
        "q": q,
    })


@feature_required(Feature.MOTORISTS)
def motorists_delete_view(request, pk):
    driver = get_object_or_404(Motorists, pk=pk)

    blockers = driver.delete_blockers()
    if blockers:
        messages.error(
            request, "Não é possível excluir este motorista: " + "; ".join(blockers) + "."
        )
        return redirect("motorists:manage")

    if request.method == "POST":
        try:
            driver.delete()
        except ProtectedError:
            messages.error(
                request, "Este motorista está designado em uma rota e não pode ser excluído."
            )
        else:
            messages.success(request, "Motorista excluído.")
        return redirect("motorists:manage")

    return render(request, "core/confirm_delete.html", {
        "heading": "Excluir motorista",
        "label": str(driver),
        "cancel_url": reverse("motorists:manage"),
    })