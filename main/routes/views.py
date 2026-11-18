import unicodedata
from django.contrib import messages
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_time
from django.utils.http import urlencode
from accounts.access import Feature, feature_required
from audit.models import AuditLog
from audit.services import log_action
from core.choices import Region
from core.normalizers import plate_normalizer
from fleet.models import Vehicle
from .drafts import clear_draft, data_from_form, data_from_route, get_draft, save_draft
from .forms import RouteFilterForm, RouteForm, SelectionFilterForm
from .models import Route
from .services import AssignmentConflict, assign_appointments, selectable_appointments


def _ids(values):
    return {int(value) for value in values if value.isdigit()}


def _people(appointments):
    return sum(1 + len(a.companions.all()) for a in appointments)


def _selection_url(cleaned):
    params = {key: cleaned[key] for key in ("time", "region") if cleaned.get(key)}
    url = reverse("routes:selection")
    return f"{url}?{urlencode(params)}" if params else url


def _editing_route(draft):
    if not draft["route_id"]:
        return None, True
    route = (
        Route.objects.select_related("vehicle", "motorist")
        .filter(pk=draft["route_id"], date__gte=timezone.localdate())
        .first()
    )
    return route, route is not None


def _strip_accents(text):
    return "".join(
        c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn"
    )


@feature_required(Feature.ROUTES)
def route_register_view(request):
    draft = get_draft(request)
    editing, ok = _editing_route(draft)
    if not ok:
        clear_draft(request)
        messages.error(request, "A rota que estava sendo editada não está mais disponível.")
        return redirect("routes:manage")

    form = RouteForm(
        request.POST or None, instance=editing, initial=draft["route"] or {}
    )

    if request.method == "POST" and form.is_valid():
        same_date = draft["date"] == form.cleaned_data["date"]
        save_draft(
            request,
            route=data_from_form(form.cleaned_data),
            selected=draft["selected"] if same_date else [],
            route_id=editing.pk if editing else None,
        )
        return redirect("routes:selection")

    return render(request, "routes/register.html", {"form": form, "editing": editing})


@feature_required(Feature.ROUTES)
def route_selection_view(request):
    draft = get_draft(request)
    editing, ok = _editing_route(draft)
    if not ok:
        clear_draft(request)
        messages.error(request, "A rota que estava sendo editada não está mais disponível.")
        return redirect("routes:manage")

    if not draft["route"]:
        messages.warning(request, "Preencha os dados da rota antes de selecionar os pacientes.")
        return redirect("routes:register")

    route_date = draft["date"]
    vehicle = Vehicle.objects.filter(pk=draft["route"]["vehicle"]).first()
    if vehicle is None:
        messages.warning(request, "O veículo escolhido não existe mais. Escolha outro.")
        return redirect("routes:register")

    selected = set(draft["selected"])
    data = request.POST if request.method == "POST" else request.GET
    filters = SelectionFilterForm(data or None, route_date=route_date, editing=editing)
    valid = filters.is_valid() if filters.is_bound else True
    cleaned = filters.cleaned_data if filters.is_bound and valid else {}
    route_id = editing.pk if editing else None

    if request.method == "POST":
        shown = _ids(request.POST.getlist("shown"))
        checked = _ids(request.POST.getlist("appointments"))
        selected = (selected - shown) | checked
        save_draft(request, route=draft["route"], selected=selected, route_id=route_id)
        results_url = _selection_url(cleaned)

        if request.POST.get("action") != "register":
            return redirect(results_url)

        appointments = list(
            selectable_appointments(route_date, editing).filter(pk__in=selected)
        )
        if not appointments:
            messages.error(request, "Selecione ao menos um agendamento para cadastrar a rota.")
            return redirect(results_url)

        people = _people(appointments)
        if people > vehicle.seats:
            messages.error(
                request,
                f"Limite máximo atingido: a seleção tem {people} pessoas (pacientes e "
                f"acompanhantes) e o veículo tem {vehicle.seats} vagas.",
            )
            return redirect(results_url)

        form = RouteForm(draft["route"], instance=editing)
        if not form.is_valid():
            problems = " ".join(error for errors in form.errors.values() for error in errors)
            messages.error(request, f"Revise os dados da rota: {problems}")
            return redirect("routes:register")

        try:
            with transaction.atomic():
                route = form.save(commit=False)
                if editing is None:
                    route.registered_by = request.user
                route.save()
                assign_appointments(route, appointments)
                log_action(
                    request.user,
                    AuditLog.Action.UPDATE if editing else AuditLog.Action.CREATE,
                    route,
                )
        except AssignmentConflict:
            messages.error(
                request,
                "Algum agendamento selecionado foi incluído em outra rota. Revise a seleção.",
            )
            return redirect(results_url)

        clear_draft(request)
        messages.success(request, "Rota atualizada." if editing else "Rota cadastrada.")
        return redirect("routes:manage" if editing else "routes:register")

    base = selectable_appointments(route_date, editing)
    listed = base
    if cleaned.get("time"):
        listed = listed.filter(appointment_time=parse_time(cleaned["time"]))
    if cleaned.get("region"):
        listed = listed.filter(region=cleaned["region"])
    options = list(listed)

    hidden = list(base.filter(pk__in=selected - {a.pk for a in options}))
    picked = [a for a in options if a.pk in selected]

    route = draft["route"]
    return render(request, "routes/selection.html", {
        "filters": filters,
        "editing": editing,
        "route_date": route_date,
        "departure_time": route["departure_time"],
        "region_label": dict(Region.choices).get(route["region"], route["region"]),
        "vehicle_label": f"{vehicle.get_vehicle_type_display()} | {vehicle.plate}",
        "capacity": vehicle.seats,
        "options": options,
        "selected": selected,
        "selected_count": len(picked) + len(hidden),
        "selected_people": _people(picked) + _people(hidden),
        "hidden_count": len(hidden),
        "hidden_people": _people(hidden),
    })


@feature_required(Feature.ROUTES)
def route_edit_view(request, pk):
    """Abre a edição: carrega a rota no rascunho e segue para a tela 1."""
    route = get_object_or_404(Route, pk=pk)
    if route.is_concluded:
        messages.error(request, "Esta rota já foi concluída e não pode ser alterada.")
        return redirect("routes:manage")
    save_draft(
        request,
        route=data_from_route(route),
        selected=route.appointments.values_list("pk", flat=True),
        route_id=route.pk,
    )
    return redirect("routes:register")


@feature_required(Feature.ROUTES)
def route_reset_view(request):
    """Limpa o rascunho (lixeira dos wireframes)."""
    was_editing = bool(get_draft(request)["route_id"])
    clear_draft(request)
    return redirect("routes:manage" if was_editing else "routes:register")


@feature_required(Feature.ROUTES)
def vehicle_search_view(request):
    """Busca de veículos funcionando e livres na data, para o seletor da tela 1."""
    term = request.GET.get("q", "").strip()
    if len(term) < 2:
        return JsonResponse({"results": []})

    vehicles = Vehicle.objects.filter(is_operational=True)

    try:
        date = parse_date(request.GET.get("date", ""))
    except ValueError:
        date = None
    if date:
        busy = Route.objects.filter(date=date)
        route_id = request.GET.get("route", "")
        if route_id.isdigit():
            busy = busy.exclude(pk=int(route_id))
        vehicles = vehicles.exclude(pk__in=busy.values("vehicle"))

    query = Q(vehicle_type__icontains=_strip_accents(term).lower().replace(" ", "-"))
    plate = plate_normalizer(term)
    if plate:
        query |= Q(plate__icontains=plate)

    return JsonResponse({"results": [
        {
            "id": v.pk,
            "label": f"{v.get_vehicle_type_display()} | {v.plate} | {v.seats} vagas",
        }
        for v in vehicles.filter(query)[:15]
    ]})


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
        route_pk = route.pk
        with transaction.atomic():
            log_action(request.user, AuditLog.Action.DELETE, route)
            route.delete()
        if get_draft(request)["route_id"] == route_pk:
            clear_draft(request)
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