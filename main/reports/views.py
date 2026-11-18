from django.http import FileResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.utils.dateparse import parse_time
from django.views.decorators.http import require_POST
from accounts.access import Feature, feature_required
from fleet.models import Vehicle, VehicleType
from routes.models import Route, TransportRecord
from routes.services import ensure_history
from .builders import build_fleet_report, build_patients_report, build_route_sheet
from .forms import FleetReportForm, PatientsReportForm


def _page(request, patients_form=None, fleet_form=None):
    return render(request, "reports/sheets.html", {
        "patients_form": patients_form or PatientsReportForm(),
        "fleet_form": fleet_form or FleetReportForm(),
    })


def _pdf(buffer, filename):
    return FileResponse(buffer, as_attachment=True, filename=filename, content_type="application/pdf")


@feature_required(Feature.SHEETS)
def sheets_view(request):
    return _page(request)


@feature_required(Feature.SHEETS)
@require_POST
def patients_report_view(request):
    form = PatientsReportForm(request.POST)
    if not form.is_valid():
        return _page(request, patients_form=form)

    data = form.cleaned_data

    if not ensure_history(request):
        return _page(request, patients_form=form)

    records = TransportRecord.objects.filter(
        route_date__range=(data["start_date"], data["end_date"])
    )
    if data["region"]:
        records = records.filter(region=data["region"])
    if data["time"]:
        records = records.filter(departure_time=parse_time(data["time"]))
    if data["comorbidity"] == "yes":
        records = records.filter(has_comorbidity=True)
    elif data["comorbidity"] == "no":
        records = records.filter(has_comorbidity=False)

    if not records.exists():
        form.add_error(None, "Nenhuma rota concluída foi encontrada para os filtros informados.")
        return _page(request, patients_form=form)

    buffer = build_patients_report(
        records.iterator(chunk_size=2000),
        start=data["start_date"],
        end=data["end_date"],
        filter_lines=form.filter_lines(),
        user=request.user,
    )
    return _pdf(
        buffer,
        f"relacao-pacientes-{data['start_date']:%Y%m%d}-{data['end_date']:%Y%m%d}.pdf",
    )


@feature_required(Feature.SHEETS)
@require_POST
def fleet_report_view(request):
    form = FleetReportForm(request.POST)
    if not form.is_valid():
        return _page(request, fleet_form=form)

    vehicle_type = form.cleaned_data["vehicle_type"]
    vehicles = Vehicle.objects.order_by("vehicle_type", "plate")
    if vehicle_type:
        vehicles = vehicles.filter(vehicle_type=vehicle_type)

    if not vehicles.exists():
        form.add_error(None, "Nenhum veículo encontrado para o filtro informado.")
        return _page(request, fleet_form=form)

    buffer = build_fleet_report(
        vehicles,
        type_label=dict(VehicleType.choices)[vehicle_type] if vehicle_type else "Todos",
        user=request.user,
    )
    return _pdf(buffer, f"relacao-frota-{timezone.localdate():%Y%m%d}.pdf")


@feature_required(Feature.ROUTES)
def route_sheet_view(request, pk):
    route = get_object_or_404(Route.objects.select_related("vehicle", "motorist"), pk=pk)
    buffer = build_route_sheet(route, request.user)
    return _pdf(
        buffer,
        f"rota-{route.date:%Y%m%d}-{route.departure_time:%H%M}-{route.vehicle.plate}.pdf",
    )