from django.contrib import messages
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.dateparse import parse_time
from accounts.access import Feature, feature_required
from audit.models import AuditLog
from audit.services import log_action
from .forms import AvailableAppointmentFilterForm, RouteFilterForm, RouteForm
from .models import Route
from .services import AssignmentConflict, assign_appointments


@feature_required(Feature.ROUTES)
def route_register_view(request, pk=None):
    editing = get_object_or_404(Route, pk=pk) if pk else None

    if editing and editing.is_concluded:
        messages.error(request, "Esta rota já foi concluída e não pode ser alterada.")
        return redirect("routes:manage")

    filters = AvailableAppointmentFilterForm(request.GET)
    filters.is_valid()
    cleaned = filters.cleaned_data
    route_date = editing.date if editing else cleaned.get("date")

    form, options, selected_ids = None, [], set()
    if route_date:
        form = RouteForm(request.POST or None, instance=editing, route_date=route_date)
        options = form.available_options(
            region=cleaned.get("region", ""), search=cleaned.get("q", "")
        )
        selected_ids = form.selected_ids()

        if request.method == "POST" and form.is_valid():
            try:
                with transaction.atomic():
                    route = form.save(commit=False)
                    if editing is None:
                        route.registered_by = request.user
                    route.save()
                    assign_appointments(route, form.cleaned_data["appointments"])
                    log_action(
                        request.user,
                        AuditLog.Action.UPDATE if editing else AuditLog.Action.CREATE,
                        route,
                    )
            except AssignmentConflict:
                messages.error(
                    request,
                    "Algum agendamento selecionado foi incluído em outra rota. "
                    "Atualize a página e selecione novamente.",
                )
            else:
                messages.success(
                    request, "Rota atualizada." if editing else "Rota cadastrada."
                )
                if editing:
                    return redirect("routes:manage")
                return redirect(f"{reverse('routes:register')}?date={route.date:%Y-%m-%d}")

    return render(request, "routes/register.html", {
        "filters": filters,
        "form": form,
        "editing": editing,
        "route_date": route_date,
        "options": options,
        "selected_ids": selected_ids,
        "vehicle_warning": bool(editing and not editing.vehicle.is_operational),
    })


@feature_required(Feature.ROUTES)
def route_manage_view(request):
    filters = RouteFilterForm(request.GET)
    routes = (
        Route.objects.upcoming()
        .select_related("vehicle", "motorist")
        .annotate(
            people=Count("appointments", distinct=True) + Count("appointments__companions")
        )
    )

    if filters.is_valid():
        data = filters.cleaned_data
        if data["date"]:
            routes = routes.filter(date=data["date"])
        if data["region"]:
            routes = routes.filter(region=data["region"])
        if data["time"]:
            routes = routes.filter(departure_time=parse_time(data["time"]))

    params = request.GET.copy()
    params.pop("page", None)
    page_obj = Paginator(routes, 25).get_page(request.GET.get("page"))

    return render(request, "routes/manage.html", {
        "filters": filters,
        "page_obj": page_obj,
        "querystring": params.urlencode(),
    })


@feature_required(Feature.ROUTES)
def route_delete_view(request, pk):
    route = get_object_or_404(Route, pk=pk)

    if route.is_concluded:
        messages.error(request, "Esta rota já foi concluída e não pode ser excluída.")
        return redirect("routes:manage")

    if request.method == "POST":
        with transaction.atomic():
            log_action(request.user, AuditLog.Action.DELETE, route)
            route.delete()
        messages.success(
            request, "Rota excluída. Os pacientes voltaram para a lista de agendamentos."
        )
        return redirect("routes:manage")

    return render(request, "core/confirm_delete.html", {
        "heading": "Excluir rota",
        "label": str(route),
        "note": "Os pacientes agendados nesta rota voltarão para a lista de agendamentos.",
        "cancel_url": reverse("routes:manage"),
    })