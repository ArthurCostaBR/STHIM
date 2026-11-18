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
from core.normalizers import plate_normalizer
from fleet.models import Vehicle
from .drafts import clear_draft, get_draft, save_draft
from .forms import RouteFilterForm, RouteForm, SelectionFilterForm
from .models import Route
from .services import AssignmentConflict, assign_appointments, selectable_appointments


def _ids(values):
    return {int(value) for value in values if value.isdigit()}


def _people(appointments):
    return sum(1 + len(a.companions.all()) for a in appointments)


def _register_url(route_date=None, editing=None):
    url = reverse("routes:register")
    if route_date and not editing:
        url += "?" + urlencode({"date": route_date.isoformat()})
    return url


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

    data = request.POST if request.method == "POST" else request.GET
    filters = SelectionFilterForm(
        data or None, editing=editing, initial={"date": draft["date"]}
    )
    bound = filters.is_bound
    valid = filters.is_valid() if bound else True
    cleaned = filters.cleaned_data if bound else {}

    if editing:
        route_date = editing.date
    elif bound:
        route_date = cleaned.get("date")
    else:
        route_date = draft["date"]

    same_date = route_date is not None and draft["date"] == route_date
    selected = set(draft["selected"]) if same_date else set()

    if request.method == "POST" and route_date and valid:
        if same_date:
            shown = _ids(request.POST.getlist("shown"))
            checked = _ids(request.POST.getlist("appointments"))
            selected = (selected - shown) | checked  # só altera o que estava na tela
        route_id = editing.pk if editing else None
        save_draft(request, date=route_date, selected=selected, route_id=route_id)

        params = {"time": cleaned.get("time"), "region": cleaned.get("region")}
        if not editing:
            params["date"] = route_date.isoformat()
        query = urlencode({key: value for key, value in params.items() if value})
        results_url = reverse("routes:register") + (f"?{query}" if query else "")

        if request.POST.get("action") == "next":
            allowed = set(
                selectable_appointments(route_date, editing)
                .filter(pk__in=selected)
                .values_list("pk", flat=True)
            )
            if not allowed:
                messages.error(request, "Selecione ao menos um agendamento para continuar.")
                return redirect(results_url)
            save_draft(request, date=route_date, selected=allowed, route_id=route_id)
            return redirect("routes:details")
        return redirect(results_url)

    options, hidden = [], []
    if route_date and valid:
        base = selectable_appointments(route_date, editing)
        listed = base
        if cleaned.get("time"):
            listed = listed.filter(appointment_time=parse_time(cleaned["time"]))
        if cleaned.get("region"):
            listed = listed.filter(region=cleaned["region"])
        options = list(listed)
        hidden = list(base.filter(pk__in=selected - {a.pk for a in options}))

    picked = [a for a in options if a.pk in selected]
    return render(request, "routes/register.html", {
        "filters": filters,
        "editing": editing,
        "route_date": route_date,
        "options": options,
        "selected": selected,
        "selected_count": len(picked) + len(hidden),
        "selected_people": _people(picked) + _people(hidden),
        "hidden_count": len(hidden),
        "hidden_people": _people(hidden),
    })


@feature_required(Feature.ROUTES)
def route_details_view(request):
    draft = get_draft(request)
    editing, ok = _editing_route(draft)
    if not ok:
        clear_draft(request)
        messages.error(request, "A rota que estava sendo editada não está mais disponível.")
        return redirect("routes:manage")

    route_date = draft["date"]
    if route_date is None or not draft["selected"]:
        messages.warning(request, "Selecione os pacientes da rota antes de continuar.")
        return redirect("routes:register")

    appointments = list(
        selectable_appointments(route_date, editing).filter(pk__in=draft["selected"])
    )
    dropped = len(draft["selected"]) - len(appointments)
    if dropped:
        save_draft(
            request, date=route_date, selected=[a.pk for a in appointments],
            route_id=editing.pk if editing else None,
        )
        messages.warning(
            request,
            f"{dropped} agendamento(s) selecionado(s) não estão mais disponíveis "
            "e saíram da seleção.",
        )
        if not appointments:
            return redirect(_register_url(route_date, editing))

    form = RouteForm(
        request.POST or None, instance=editing,
        route_date=route_date, appointments=appointments,
    )

    if request.method == "POST" and form.is_valid():
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
                "Algum agendamento selecionado foi incluído em outra rota. "
                "Revise a seleção.",
            )
            return redirect(_register_url(route_date, editing))

        clear_draft(request)
        messages.success(request, "Rota atualizada." if editing else "Rota cadastrada.")
        if editing:
            return redirect("routes:manage")
        return redirect(_register_url(route.date))

    return render(request, "routes/details.html", {
        "form": form,
        "editing": editing,
        "route_date": route_date,
        "appointments": appointments,
        "people": _people(appointments),
        "vehicle_warning": bool(editing and not editing.vehicle.is_operational),
    })


@feature_required(Feature.ROUTES)
def route_edit_view(request, pk):
    route = get_object_or_404(Route, pk=pk)
    if route.is_concluded:
        messages.error(request, "Esta rota já foi concluída e não pode ser alterada.")
        return redirect("routes:manage")
    save_draft(
        request,
        date=route.date,
        selected=route.appointments.values_list("pk", flat=True),
        route_id=route.pk,
    )
    return redirect("routes:register")


@feature_required(Feature.ROUTES)
def route_reset_view(request):
    was_editing = bool(get_draft(request)["route_id"])
    clear_draft(request)
    return redirect("routes:manage" if was_editing else "routes:register")


@feature_required(Feature.ROUTES)
def vehicle_search_view(request):
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