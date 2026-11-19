import datetime
from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from accounts.models import Sector
from core.factories import (
    create_appointment, create_patient, create_route, create_user, create_vehicle, days,
)
from reports import pdf
from reports.builders import (
    _count_text, _plural, build_fleet_report, build_patients_report, build_route_sheet,
)
from reports.forms import FleetReportForm, PatientsReportForm
from routes.models import TransportRecord
from routes.services import freeze_due_routes

SHEETS = reverse("reports:sheets")
PATIENTS = reverse("reports:patients")
FLEET = reverse("reports:fleet")


def pdf_bytes(response_or_buffer):
    if hasattr(response_or_buffer, "streaming_content"):
        return b"".join(response_or_buffer.streaming_content)
    return response_or_buffer.getvalue()


class PdfHelperTests(SimpleTestCase):
    def test_paragraph_escapes_markup_and_newlines(self):
        paragraph = pdf.p("<b>a & b</b>\nlinha 2")
        self.assertIn("&lt;b&gt;a &amp; b&lt;/b&gt;<br/>linha 2", paragraph.text)

    def test_paragraph_accepts_none_and_numbers(self):
        self.assertEqual(pdf.p(None).text, "")
        self.assertEqual(pdf.cell(7).text, "7")

    def test_render_pdf(self):
        buffer = pdf.render_pdf([pdf.p("Olá")], title="Teste", footer="Rodapé")
        self.assertTrue(buffer.getvalue().startswith(b"%PDF"))
        self.assertEqual(buffer.tell(), 0)

    def test_render_multipage_pdf(self):
        story = [pdf.data_table(["A"], [[pdf.cell(i)] for i in range(300)], [100])]
        buffer = pdf.render_pdf(story, title="T", footer="F", wide=True)
        self.assertGreater(buffer.getvalue().count(b"/Type /Page\n"), 1)


class BuilderHelperTests(SimpleTestCase):
    def test_plural(self):
        self.assertEqual(_plural(1, "rota", "rotas"), "1 rota")
        self.assertEqual(_plural(0, "rota", "rotas"), "0 rotas")
        self.assertEqual(_plural(2, "rota", "rotas"), "2 rotas")

    def test_count_text(self):
        self.assertEqual(
            _count_text(1, 2), "1 paciente + 2 acompanhantes = 3 pessoas"
        )


class BuilderTests(TestCase):
    def setUp(self):
        self.user = create_user(Sector.ADMINISTRACAO)

    def test_route_sheet_with_and_without_patients(self):
        appointment = create_appointment(
            companions=[create_patient()], has_comorbidity=True, notes="Oxigênio",
        )
        route = create_route([appointment])
        self.assertTrue(pdf_bytes(build_route_sheet(route, self.user)).startswith(b"%PDF"))
        self.assertTrue(pdf_bytes(build_route_sheet(create_route(), self.user)).startswith(b"%PDF"))

    def test_patients_report(self):
        for offset in (-3, -2):
            create_route(
                [create_appointment(date=days(offset), companions=[create_patient(cpf=None, sus=f"7000000000000{-offset:02d}")])],
                date=days(offset),
            )
        freeze_due_routes()
        records = TransportRecord.objects.all()
        buffer = build_patients_report(
            records, start=days(-3), end=days(-1), filter_lines=["Região: X"], user=self.user,
        )
        self.assertTrue(pdf_bytes(buffer).startswith(b"%PDF"))

    def test_patients_report_without_records(self):
        buffer = build_patients_report(
            [], start=days(-3), end=days(-1), filter_lines=[], user=self.user,
        )
        self.assertTrue(pdf_bytes(buffer).startswith(b"%PDF"))

    def test_fleet_report(self):
        vehicles = [create_vehicle(), create_vehicle(is_operational=False)]
        buffer = build_fleet_report(vehicles, type_label="Todos", user=self.user)
        self.assertTrue(pdf_bytes(buffer).startswith(b"%PDF"))


class PatientsReportFormTests(TestCase):
    def data(self, **overrides):
        data = {
            "start_date": days(-10).isoformat(),
            "end_date": days(-1).isoformat(),
            "region": "", "time": "", "comorbidity": "",
        }
        data.update(overrides)
        return data

    def test_valid(self):
        self.assertTrue(PatientsReportForm(self.data()).is_valid())

    def test_requires_dates(self):
        form = PatientsReportForm(self.data(start_date="", end_date=""))
        self.assertIn("start_date", form.errors)
        self.assertIn("end_date", form.errors)

    def test_end_before_start(self):
        form = PatientsReportForm(
            self.data(start_date=days(-1).isoformat(), end_date=days(-5).isoformat())
        )
        self.assertEqual(
            form.errors["end_date"],
            ["A data final deve ser igual ou posterior à data inicial."],
        )

    def test_time_choices_merge_records_and_routes(self):
        create_route(departure_time=datetime.time(7, 0))
        create_route([create_appointment(date=days(-1))], date=days(-1),
                     departure_time=datetime.time(5, 30))
        create_route(departure_time=datetime.time(7, 0), date=days(2))
        freeze_due_routes()
        self.assertEqual(
            list(PatientsReportForm().fields["time"].choices),
            [("", "Todos"), ("05:30", "05:30"), ("07:00", "07:00")],
        )

    def test_filter_lines(self):
        create_route(departure_time=datetime.time(7, 0))
        form = PatientsReportForm(self.data(region="campos", time="07:00", comorbidity="no"))
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.filter_lines(), [
            "Região da rota: Campos", "Horário de saída: 07:00", "Comorbidade: Não",
        ])
        form = PatientsReportForm(self.data())
        form.is_valid()
        self.assertEqual(form.filter_lines(), [])


class FleetReportFormTests(SimpleTestCase):
    def test_vehicle_type_optional_and_validated(self):
        self.assertTrue(FleetReportForm({"vehicle_type": ""}).is_valid())
        self.assertTrue(FleetReportForm({"vehicle_type": "van"}).is_valid())
        self.assertFalse(FleetReportForm({"vehicle_type": "foguete"}).is_valid())


class ReportsAccessTests(TestCase):
    def test_sheets_allowed_for_administracao_and_gestao(self):
        for sector in (Sector.ADMINISTRACAO, Sector.GESTAO):
            with self.subTest(sector=sector):
                self.client.force_login(create_user(sector))
                response = self.client.get(SHEETS)
                self.assertEqual(response.status_code, 200)
                self.assertIn("patients_form", response.context)
                self.assertIn("fleet_form", response.context)

    def test_marcacao_forbidden(self):
        self.client.force_login(create_user(Sector.MARCACAO))
        for url in (SHEETS, PATIENTS, FLEET):
            self.assertEqual(self.client.post(url).status_code, 403)

    def test_reports_require_post(self):
        self.client.force_login(create_user(Sector.GESTAO))
        self.assertEqual(self.client.get(PATIENTS).status_code, 405)
        self.assertEqual(self.client.get(FLEET).status_code, 405)

    def test_route_sheet_requires_routes_feature(self):
        route = create_route()
        url = reverse("reports:route_sheet", args=[route.pk])
        self.client.force_login(create_user(Sector.GESTAO))
        self.assertEqual(self.client.get(url).status_code, 403)
        self.client.force_login(create_user(Sector.ADMINISTRACAO))
        self.assertEqual(self.client.get(url).status_code, 200)


class PatientsReportViewTests(TestCase):
    def setUp(self):
        self.client.force_login(create_user(Sector.GESTAO))
        self.sick = create_appointment(date=days(-2), has_comorbidity=True, region="campos")
        self.route = create_route(
            [self.sick, create_appointment(date=days(-2))],
            date=days(-2), region="campos", departure_time=datetime.time(6, 0),
        )

    def post(self, **overrides):
        data = {
            "start_date": days(-7).isoformat(),
            "end_date": days(-1).isoformat(),
            "region": "", "time": "", "comorbidity": "",
        }
        data.update(overrides)
        return self.client.post(PATIENTS, data)

    def assert_pdf(self, response):
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertTrue(pdf_bytes(response).startswith(b"%PDF"))

    def test_generates_pdf_from_frozen_routes(self):
        response = self.post()
        self.assert_pdf(response)
        expected = f"relacao-pacientes-{days(-7):%Y%m%d}-{days(-1):%Y%m%d}.pdf"
        self.assertIn(f'attachment; filename="{expected}"', response["Content-Disposition"])
        self.assertEqual(TransportRecord.objects.count(), 2)

    def test_filters(self):
        self.assert_pdf(self.post(region="campos", time="06:00", comorbidity="yes"))
        self.assert_pdf(self.post(comorbidity="no"))

    def test_no_records_for_filters(self):
        response = self.post(region="niteroi")
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "reports/sheets.html")
        self.assertIn(
            "Nenhuma rota concluída foi encontrada para os filtros informados.",
            response.context["patients_form"].non_field_errors(),
        )

    def test_period_outside_records(self):
        response = self.post(start_date=days(-30).isoformat(), end_date=days(-20).isoformat())
        self.assertTrue(response.context["patients_form"].non_field_errors())

    def test_invalid_form(self):
        response = self.post(start_date="", end_date="")
        self.assertEqual(response.status_code, 200)
        self.assertIn("start_date", response.context["patients_form"].errors)

    def test_upcoming_routes_are_not_included(self):
        TransportRecord.objects.all().delete()
        self.route.delete()
        create_route([create_appointment(date=days(0))], date=days(0))
        response = self.post(end_date=days(1).isoformat())
        self.assertTrue(response.context["patients_form"].non_field_errors())


class FleetReportViewTests(TestCase):
    def setUp(self):
        self.client.force_login(create_user(Sector.ADMINISTRACAO))

    def test_generates_pdf(self):
        create_vehicle(vehicle_type="van")
        create_vehicle(vehicle_type="carro", is_operational=False)
        for vehicle_type in ("", "van"):
            with self.subTest(vehicle_type=vehicle_type):
                response = self.client.post(FLEET, {"vehicle_type": vehicle_type})
                self.assertEqual(response["Content-Type"], "application/pdf")
                self.assertIn(
                    f"relacao-frota-{days(0):%Y%m%d}.pdf", response["Content-Disposition"]
                )
                self.assertTrue(pdf_bytes(response).startswith(b"%PDF"))

    def test_no_vehicles_for_filter(self):
        create_vehicle(vehicle_type="van")
        response = self.client.post(FLEET, {"vehicle_type": "onibus"})
        self.assertEqual(response.status_code, 200)
        self.assertIn(
            "Nenhum veículo encontrado para o filtro informado.",
            response.context["fleet_form"].non_field_errors(),
        )

    def test_invalid_filter(self):
        response = self.client.post(FLEET, {"vehicle_type": "foguete"})
        self.assertIn("vehicle_type", response.context["fleet_form"].errors)


class RouteSheetViewTests(TestCase):
    def test_generates_pdf(self):
        self.client.force_login(create_user(Sector.ADMINISTRACAO))
        vehicle = create_vehicle(plate="ABC1D23")
        route = create_route(
            [create_appointment()], vehicle=vehicle, date=days(1),
            departure_time=datetime.time(6, 30),
        )
        response = self.client.get(reverse("reports:route_sheet", args=[route.pk]))
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertIn(f"rota-{days(1):%Y%m%d}-0630-ABC1D23.pdf", response["Content-Disposition"])
        self.assertTrue(pdf_bytes(response).startswith(b"%PDF"))

    def test_404(self):
        self.client.force_login(create_user(Sector.ADMINISTRACAO))
        self.assertEqual(
            self.client.get(reverse("reports:route_sheet", args=[999999])).status_code, 404
        )
