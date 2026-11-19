import datetime
from types import SimpleNamespace
from unittest import mock
from django.db import IntegrityError, transaction
from django.test import RequestFactory, SimpleTestCase, TestCase
from django.urls import reverse
from accounts.models import Sector
from appointments.models import Appointment
from audit.models import AuditLog
from core.factories import (
    create_appointment, create_motorist, create_patient, create_route, create_user,
    create_vehicle, days, messages_of,
)
from routes import drafts
from routes.forms import RouteFilterForm, RouteForm, SelectionFilterForm
from routes.locks import (
    blocked_message, routes_of_appointment, routes_of_motorist, routes_of_patient,
    routes_of_vehicle,
)
from routes.models import Route, TransportRecord
from routes.services import (
    AssignmentConflict, assign_appointments, build_records, ensure_history,
    freeze_due_routes, selectable_appointments,
)

REGISTER = reverse("routes:register")
SELECTION = reverse("routes:selection")
MANAGE = reverse("routes:manage")
RESET = reverse("routes:reset")
VEHICLE_SEARCH = reverse("routes:vehicle_search")


def route_data(vehicle, motorist, **overrides):
    data = {
        "vehicle": str(vehicle.pk),
        "date": days(1).isoformat(),
        "departure_time": "06:30",
        "region": "niteroi",
        "motorist": str(motorist.pk),
    }
    data.update(overrides)
    return data


# --------------------------------------------------------------------------- #
# Rascunho em sessão
# --------------------------------------------------------------------------- #

class DraftTests(SimpleTestCase):
    def request(self, session=None):
        return SimpleNamespace(session={} if session is None else session)

    def route(self, **overrides):
        data = {
            "vehicle": "1", "date": days(1).isoformat(), "departure_time": "06:30",
            "region": "niteroi", "motorist": "2",
        }
        data.update(overrides)
        return data

    def test_empty_session(self):
        self.assertEqual(
            drafts.get_draft(self.request()),
            {"route": None, "date": None, "selected": [], "route_id": None},
        )

    def test_roundtrip(self):
        request = self.request()
        drafts.save_draft(request, route=self.route(), selected=["3", 1, 3], route_id=9)
        draft = drafts.get_draft(request)
        self.assertEqual(draft["route"], self.route())
        self.assertEqual(draft["date"], days(1))
        self.assertEqual(draft["selected"], [1, 3])
        self.assertEqual(draft["route_id"], 9)

    def test_today_is_still_valid(self):
        request = self.request()
        drafts.save_draft(request, route=self.route(date=days(0).isoformat()))
        self.assertEqual(drafts.get_draft(request)["date"], days(0))

    def test_invalid_drafts_are_discarded(self):
        incomplete = self.route()
        del incomplete["motorist"]
        for route in (
            "texto",
            incomplete,
            self.route(date="ontem"),
            self.route(date=None),
            self.route(date=days(-1).isoformat()),
        ):
            with self.subTest(route=route):
                request = self.request({drafts.DRAFT_KEY: {"route": route, "selected": [1]}})
                self.assertIsNone(drafts.get_draft(request)["route"])

    def test_clear(self):
        request = self.request()
        drafts.save_draft(request, route=self.route())
        drafts.clear_draft(request)
        self.assertNotIn(drafts.DRAFT_KEY, request.session)
        drafts.clear_draft(request)  # idempotente

    def test_data_from_form(self):
        cleaned = {
            "vehicle": SimpleNamespace(pk=4),
            "motorist": SimpleNamespace(pk=7),
            "date": datetime.date(2030, 1, 2),
            "departure_time": datetime.time(5, 45),
            "region": "campos",
        }
        self.assertEqual(drafts.data_from_form(cleaned), {
            "vehicle": "4", "date": "2030-01-02", "departure_time": "05:45",
            "region": "campos", "motorist": "7",
        })

    def test_data_from_route(self):
        route = SimpleNamespace(
            vehicle_id=4, motorist_id=7, date=datetime.date(2030, 1, 2),
            departure_time=datetime.time(5, 45), region="campos",
        )
        self.assertEqual(drafts.data_from_route(route)["departure_time"], "05:45")
        self.assertEqual(drafts.data_from_route(route)["vehicle"], "4")


# --------------------------------------------------------------------------- #
# Modelos
# --------------------------------------------------------------------------- #

class RouteModelTests(TestCase):
    def test_name_and_str(self):
        vehicle = create_vehicle(plate="ABC1D23", seats=12)
        route = create_route(
            vehicle=vehicle, date=datetime.date(2030, 3, 4),
            departure_time=datetime.time(6, 5), region="niteroi",
        )
        self.assertEqual(route.name, "04/03/2030 | Niterói - 06:05 | ABC1D23")
        self.assertEqual(str(route), route.name)
        self.assertEqual(route.capacity, 12)

    def test_is_concluded(self):
        self.assertTrue(create_route(date=days(-1)).is_concluded)
        self.assertFalse(create_route(date=days(0)).is_concluded)

    def test_upcoming(self):
        create_route(date=days(-1))
        upcoming = [create_route(date=days(0)), create_route(date=days(4))]
        self.assertEqual(list(Route.objects.upcoming()), upcoming)

    def test_one_route_per_vehicle_per_date(self):
        vehicle = create_vehicle()
        create_route(vehicle=vehicle)
        with self.assertRaises(IntegrityError), transaction.atomic():
            create_route(vehicle=vehicle)
        create_route(vehicle=vehicle, date=days(2))

    def test_one_route_per_motorist_per_date(self):
        motorist = create_motorist()
        create_route(motorist=motorist)
        with self.assertRaises(IntegrityError), transaction.atomic():
            create_route(motorist=motorist)

    def test_vehicle_and_motorist_are_protected(self):
        from django.db.models import ProtectedError

        route = create_route()
        with self.assertRaises(ProtectedError):
            route.vehicle.delete()
        with self.assertRaises(ProtectedError):
            route.motorist.delete()

    def test_transport_record_str(self):
        record = TransportRecord(route_date=datetime.date(2030, 1, 2), name="Ana")
        self.assertEqual(str(record), "02/01/2030 | Ana")


# --------------------------------------------------------------------------- #
# Travas
# --------------------------------------------------------------------------- #

class LockTests(TestCase):
    def test_routes_of_appointment(self):
        free = create_appointment()
        self.assertFalse(routes_of_appointment(free).exists())
        active = create_appointment()
        route = create_route([active])
        self.assertEqual(list(routes_of_appointment(active)), [route])
        old = create_appointment(date=days(-1))
        create_route([old], date=days(-1))
        self.assertFalse(routes_of_appointment(old).exists())

    def test_routes_of_patient_as_patient_or_companion_distinct(self):
        patient = create_patient()
        route = create_route([
            create_appointment(patient=patient),
            create_appointment(companions=[patient]),
        ])
        self.assertEqual(list(routes_of_patient(patient)), [route])

        companion = create_patient()
        other = create_route([create_appointment(companions=[companion], date=days(2))], date=days(2))
        self.assertEqual(list(routes_of_patient(companion)), [other])
        self.assertFalse(routes_of_patient(create_patient()).exists())

    def test_routes_of_motorist_and_vehicle_ignore_concluded(self):
        motorist, vehicle = create_motorist(), create_vehicle()
        create_route(motorist=motorist, vehicle=vehicle, date=days(-1))
        self.assertFalse(routes_of_motorist(motorist).exists())
        self.assertFalse(routes_of_vehicle(vehicle).exists())
        route = create_route(motorist=motorist, vehicle=vehicle)
        self.assertEqual(list(routes_of_motorist(motorist)), [route])
        self.assertEqual(list(routes_of_vehicle(vehicle)), [route])

    def test_blocked_message_single_route(self):
        route = create_route()
        message = blocked_message("excluir", "o veículo X", [route], "Troque em")
        self.assertIn("Não é possível excluir o veículo X porque está em uma rota ativa.", message)
        self.assertIn(f'<a href="{reverse("routes:edit", args=[route.pk])}">', message)
        self.assertNotIn(" e mais ", message)

    def test_blocked_message_lists_at_most_five(self):
        routes = [create_route() for _ in range(7)]
        message = blocked_message("alterar", "o paciente", routes, "Retire em")
        self.assertIn("7 rotas ativas", message)
        self.assertEqual(message.count("<a href="), 5)
        self.assertTrue(message.endswith(" e mais 2."))

    def test_blocked_message_escapes_subject(self):
        message = blocked_message("alterar", "<script>", [create_route()], "Dica")
        self.assertNotIn("<script>", message)
        self.assertIn("&lt;script&gt;", message)


# --------------------------------------------------------------------------- #
# Serviços
# --------------------------------------------------------------------------- #

class BuildRecordsTests(TestCase):
    def test_one_record_per_person_with_snapshot(self):
        patient = create_patient(name="Ana", cpf="52998224725", phone="21999998888")
        companion = create_patient(name="Bia", cpf=None, sus="700000000000001")
        appointment = create_appointment(
            patient=patient, companions=[companion], destination="Hospital X",
            has_comorbidity=True, notes="Oxigênio",
        )
        vehicle = create_vehicle(vehicle_type="ambulancia", plate="ABC1234")
        motorist = create_motorist(name="Zé")
        route = create_route([appointment], vehicle=vehicle, motorist=motorist)

        records = {r.name: r for r in build_records(route)}
        self.assertEqual(set(records), {"Ana", "Bia"})
        ana, bia = records["Ana"], records["Bia"]
        self.assertFalse(ana.is_companion)
        self.assertTrue(bia.is_companion)
        self.assertEqual(ana.person_id, patient.pk)
        self.assertEqual(ana.route_id, route.pk)
        self.assertEqual(ana.vehicle_type, "Ambulância")
        self.assertEqual(ana.vehicle_plate, "ABC1234")
        self.assertEqual(ana.motorist_name, "Zé")
        self.assertEqual(ana.destination, "Hospital X")
        self.assertTrue(bia.has_comorbidity)
        self.assertEqual(bia.notes, "Oxigênio")
        self.assertEqual(ana.phone, "21999998888")
        self.assertEqual(bia.sus, "700000000000001")
        self.assertIsNone(bia.cpf)

    def test_empty_route(self):
        self.assertEqual(build_records(create_route()), [])


class FreezeDueRoutesTests(TestCase):
    def test_freezes_past_routes_only(self):
        companion = create_patient()
        past_appointment = create_appointment(date=days(-1), companions=[companion])
        past_route = create_route([past_appointment], date=days(-1))
        future_appointment = create_appointment()
        future_route = create_route([future_appointment])

        self.assertEqual(freeze_due_routes(), 1)

        self.assertFalse(Route.objects.filter(pk=past_route.pk).exists())
        self.assertFalse(Appointment.objects.filter(pk=past_appointment.pk).exists())
        self.assertTrue(Route.objects.filter(pk=future_route.pk).exists())
        self.assertTrue(Appointment.objects.filter(pk=future_appointment.pk).exists())
        records = TransportRecord.objects.all()
        self.assertEqual(records.count(), 2)
        self.assertEqual({r.route_id for r in records}, {past_route.pk})
        # pessoas continuam cadastradas
        self.assertTrue(companion.__class__.objects.filter(pk=companion.pk).exists())

    def test_today_routes_are_not_frozen(self):
        create_route([create_appointment(date=days(0))], date=days(0))
        self.assertEqual(freeze_due_routes(), 0)
        self.assertFalse(TransportRecord.objects.exists())

    def test_deletes_past_unassigned_appointments(self):
        old = create_appointment(date=days(-3))
        current = create_appointment(date=days(0))
        freeze_due_routes()
        self.assertFalse(Appointment.objects.filter(pk=old.pk).exists())
        self.assertTrue(Appointment.objects.filter(pk=current.pk).exists())

    def test_custom_today_and_idempotency(self):
        create_route([create_appointment(date=days(2))], date=days(2))
        self.assertEqual(freeze_due_routes(days(1)), 0)
        self.assertEqual(freeze_due_routes(days(3), wait=True), 1)
        self.assertEqual(freeze_due_routes(days(3)), 0)
        self.assertEqual(TransportRecord.objects.count(), 1)

    def test_existing_records_are_not_duplicated(self):
        route = create_route([create_appointment(date=days(-1))], date=days(-1))
        TransportRecord.objects.bulk_create(build_records(route))
        freeze_due_routes()
        self.assertEqual(TransportRecord.objects.count(), 1)


class EnsureHistoryTests(TestCase):
    def test_success(self):
        create_route(date=days(-1))
        self.assertTrue(ensure_history(RequestFactory().get("/")))
        self.assertFalse(Route.objects.exists())

    def test_failure_reports_error(self):
        request = RequestFactory().get("/")
        with mock.patch("routes.services.freeze_due_routes", side_effect=RuntimeError), \
                mock.patch("routes.services.messages") as messages, \
                self.assertLogs("routes.services", "ERROR"):
            self.assertFalse(ensure_history(request))
        messages.error.assert_called_once()


class AssignAppointmentsTests(TestCase):
    def test_assigns_and_releases(self):
        kept, removed, added = create_appointment(), create_appointment(), create_appointment()
        route = create_route([kept, removed])
        assign_appointments(route, [kept, added])
        self.assertEqual(set(route.appointments.all()), {kept, added})
        removed.refresh_from_db()
        self.assertIsNone(removed.route)

    def test_conflict_with_other_route(self):
        taken = create_appointment()
        create_route([taken])
        route = create_route()
        with self.assertRaises(AssignmentConflict):
            assign_appointments(route, [taken, create_appointment()])
        self.assertFalse(route.appointments.exists())


class SelectableAppointmentsTests(TestCase):
    def test_free_on_date_plus_own(self):
        free = create_appointment(date=days(1))
        create_appointment(date=days(2))
        own = create_appointment(date=days(1))
        route = create_route([own])
        other = create_appointment(date=days(1))
        create_route([other])

        self.assertEqual(set(selectable_appointments(days(1))), {free})
        self.assertEqual(set(selectable_appointments(days(1), route)), {free, own})


# --------------------------------------------------------------------------- #
# Formulários
# --------------------------------------------------------------------------- #

class RouteFormTests(TestCase):
    def setUp(self):
        self.vehicle = create_vehicle()
        self.motorist = create_motorist()

    def test_valid(self):
        form = RouteForm(route_data(self.vehicle, self.motorist))
        self.assertTrue(form.is_valid(), form.errors)

    def test_past_date(self):
        form = RouteForm(route_data(self.vehicle, self.motorist, date=days(-1).isoformat()))
        self.assertEqual(form.errors["date"], ["A data da rota não pode ser no passado."])

    def test_only_operational_vehicles(self):
        broken = create_vehicle(is_operational=False)
        form = RouteForm(route_data(broken, self.motorist))
        self.assertIn("vehicle", form.errors)
        self.assertNotIn(broken, form.fields["vehicle"].queryset)

    def test_vehicle_and_motorist_busy_on_date(self):
        create_route(vehicle=self.vehicle, motorist=self.motorist)
        form = RouteForm(route_data(self.vehicle, self.motorist))
        self.assertEqual(form.errors["vehicle"], ["Este veículo já está em outra rota nesta data."])
        self.assertEqual(form.errors["motorist"], ["Este motorista já está em outra rota nesta data."])
        other_day = RouteForm(route_data(self.vehicle, self.motorist, date=days(2).isoformat()))
        self.assertTrue(other_day.is_valid(), other_day.errors)

    def test_editing_ignores_itself_and_locks_date(self):
        route = create_route(vehicle=self.vehicle, motorist=self.motorist, date=days(1))
        form = RouteForm(
            route_data(self.vehicle, self.motorist, date=days(5).isoformat(), departure_time="08:00"),
            instance=route,
        )
        self.assertTrue(form.fields["date"].disabled)
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["date"], days(1))
        self.assertIn(f"route={route.pk}", form.fields["vehicle"].widget.attrs["data-search-url"])

    def test_labels(self):
        vehicle = create_vehicle(vehicle_type="van", plate="ABC1234", seats=15)
        form = RouteForm()
        self.assertEqual(
            form.fields["vehicle"].label_from_instance(vehicle), "Van | ABC1234 | 15 vagas"
        )
        self.assertEqual(form.fields["motorist"].label_from_instance(self.motorist), self.motorist.name)


class RouteFilterFormTests(TestCase):
    def test_time_choices_from_upcoming_routes(self):
        create_route(departure_time=datetime.time(7, 0))
        create_route(departure_time=datetime.time(5, 0), date=days(2))
        create_route(departure_time=datetime.time(4, 0), date=days(-1))
        form = RouteFilterForm()
        self.assertEqual(
            list(form.fields["time"].choices),
            [("", "Todos"), ("05:00", "05:00"), ("07:00", "07:00")],
        )

    def test_past_date_rejected(self):
        form = RouteFilterForm({"date": days(-1).isoformat()})
        self.assertIn("date", form.errors)
        self.assertTrue(RouteFilterForm({"date": days(0).isoformat()}).is_valid())


class SelectionFilterFormTests(TestCase):
    def test_time_choices_from_free_and_own_appointments(self):
        create_appointment(date=days(1), appointment_time=datetime.time(9, 0))
        create_appointment(date=days(2), appointment_time=datetime.time(10, 0))
        own = create_appointment(date=days(1), appointment_time=datetime.time(11, 0))
        route = create_route([own])
        create_route([create_appointment(date=days(1), appointment_time=datetime.time(12, 0))])

        times = lambda form: [value for value, _ in form.fields["time"].choices]  # noqa: E731
        self.assertEqual(times(SelectionFilterForm(route_date=days(1))), ["", "09:00"])
        self.assertEqual(
            times(SelectionFilterForm(route_date=days(1), editing=route)), ["", "09:00", "11:00"]
        )


# --------------------------------------------------------------------------- #
# Views
# --------------------------------------------------------------------------- #

class RouteViewAccessTests(TestCase):
    def test_other_sectors_forbidden(self):
        route = create_route()
        urls = [
            REGISTER, SELECTION, MANAGE, RESET, VEHICLE_SEARCH,
            reverse("routes:edit", args=[route.pk]),
            reverse("routes:delete", args=[route.pk]),
        ]
        for sector in (Sector.MARCACAO, Sector.GESTAO):
            with self.subTest(sector=sector):
                self.client.force_login(create_user(sector))
                for url in urls:
                    self.assertEqual(self.client.get(url).status_code, 403, url)


class RouteViewTestCase(TestCase):
    def setUp(self):
        self.user = create_user(Sector.ADMINISTRACAO)
        self.client.force_login(self.user)
        self.vehicle = create_vehicle(seats=4)
        self.motorist = create_motorist()

    def set_draft(self, route=None, selected=(), route_id=None):
        session = self.client.session
        session[drafts.DRAFT_KEY] = {
            "route": route or route_data(self.vehicle, self.motorist),
            "selected": list(selected),
            "route_id": route_id,
        }
        session.save()

    def draft(self):
        return self.client.session.get(drafts.DRAFT_KEY)


class RegisterViewTests(RouteViewTestCase):
    def test_get_empty(self):
        response = self.client.get(REGISTER)
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.context["editing"])

    def test_get_prefills_from_draft(self):
        self.set_draft()
        response = self.client.get(REGISTER)
        self.assertEqual(response.context["form"].initial["vehicle"], str(self.vehicle.pk))

    def test_post_saves_draft_and_goes_to_selection(self):
        response = self.client.post(REGISTER, route_data(self.vehicle, self.motorist))
        self.assertRedirects(response, SELECTION)
        draft = self.draft()
        self.assertEqual(draft["route"]["vehicle"], str(self.vehicle.pk))
        self.assertEqual(draft["selected"], [])
        self.assertIsNone(draft["route_id"])
        self.assertFalse(Route.objects.exists())

    def test_invalid_post_rerenders(self):
        response = self.client.post(
            REGISTER, route_data(self.vehicle, self.motorist, date=days(-1).isoformat())
        )
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(self.draft())

    def test_selection_kept_when_date_unchanged(self):
        self.set_draft(selected=[5, 6])
        self.client.post(REGISTER, route_data(self.vehicle, self.motorist, departure_time="07:00"))
        self.assertEqual(self.draft()["selected"], [5, 6])

    def test_selection_reset_when_date_changes(self):
        self.set_draft(selected=[5, 6])
        self.client.post(REGISTER, route_data(self.vehicle, self.motorist, date=days(3).isoformat()))
        self.assertEqual(self.draft()["selected"], [])

    def test_draft_of_missing_route_is_discarded(self):
        self.set_draft(route_id=999999)
        response = self.client.get(REGISTER)
        self.assertRedirects(response, MANAGE)
        self.assertIn("não está mais disponível", messages_of(response)[0])
        self.assertIsNone(self.draft())


class SelectionViewTests(RouteViewTestCase):
    def test_requires_draft(self):
        response = self.client.get(SELECTION)
        self.assertRedirects(response, REGISTER)

    def test_vehicle_removed(self):
        route = route_data(self.vehicle, self.motorist)
        route["vehicle"] = "999999"
        self.set_draft(route=route)
        response = self.client.get(SELECTION)
        self.assertRedirects(response, REGISTER)
        self.assertIn("veículo escolhido não existe mais", messages_of(response)[0])

    def test_draft_of_missing_route_is_discarded(self):
        self.set_draft(route_id=999999)
        self.assertRedirects(self.client.get(SELECTION), MANAGE)

    def test_lists_selectable_appointments(self):
        free = create_appointment(date=days(1))
        create_appointment(date=days(2))
        create_route([create_appointment(date=days(1))])
        response = self.client.get(SELECTION)  # sem rascunho
        self.assertEqual(response.status_code, 302)

        self.set_draft()
        response = self.client.get(SELECTION)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["options"], [free])
        self.assertEqual(response.context["capacity"], 4)
        self.assertEqual(response.context["region_label"], "Niterói")
        self.assertEqual(response.context["departure_time"], "06:30")

    def test_filters_and_hidden_selected(self):
        morning = create_appointment(appointment_time=datetime.time(8, 0), region="niteroi")
        evening = create_appointment(
            appointment_time=datetime.time(18, 0), region="campos",
            companions=[create_patient()],
        )
        self.set_draft(selected=[morning.pk, evening.pk])

        response = self.client.get(SELECTION, {"time": "08:00"})
        self.assertEqual(response.context["options"], [morning])
        self.assertEqual(response.context["hidden_count"], 1)
        self.assertEqual(response.context["hidden_people"], 2)
        self.assertEqual(response.context["selected_count"], 2)
        self.assertEqual(response.context["selected_people"], 3)

        response = self.client.get(SELECTION, {"region": "campos"})
        self.assertEqual(response.context["options"], [evening])

    def test_post_updates_selection_of_shown_items_only(self):
        a, b, c = create_appointment(), create_appointment(), create_appointment()
        self.set_draft(selected=[a.pk, c.pk])
        response = self.client.post(SELECTION, {
            "shown": [str(a.pk), str(b.pk)],
            "appointments": [str(b.pk)],
            "region": "niteroi",
        })
        self.assertRedirects(response, f"{SELECTION}?region=niteroi")
        self.assertEqual(self.draft()["selected"], sorted([b.pk, c.pk]))
        self.assertFalse(Route.objects.exists())

    def test_register_creates_route(self):
        a = create_appointment(companions=[create_patient()])
        b = create_appointment()
        self.set_draft()
        response = self.client.post(SELECTION, {
            "shown": [str(a.pk), str(b.pk)],
            "appointments": [str(a.pk), str(b.pk)],
            "action": "register",
        })
        self.assertRedirects(response, REGISTER)
        route = Route.objects.get()
        self.assertEqual(route.registered_by, self.user)
        self.assertEqual((route.vehicle, route.motorist), (self.vehicle, self.motorist))
        self.assertEqual(set(route.appointments.all()), {a, b})
        self.assertEqual(AuditLog.objects.get().action, "create")
        self.assertIsNone(self.draft())
        self.assertIn("Rota cadastrada.", messages_of(response))

    def test_register_requires_selection(self):
        self.set_draft()
        response = self.client.post(SELECTION, {"action": "register"})
        self.assertRedirects(response, SELECTION)
        self.assertIn("Selecione ao menos um agendamento", messages_of(response)[0])
        self.assertFalse(Route.objects.exists())

    def test_register_respects_capacity(self):
        a = create_appointment(companions=[create_patient(), create_patient()])
        b = create_appointment(companions=[create_patient()])
        self.set_draft(selected=[a.pk, b.pk])  # 5 pessoas para 4 vagas
        response = self.client.post(SELECTION, {"action": "register"})
        self.assertRedirects(response, SELECTION)
        self.assertIn("Limite máximo atingido", messages_of(response)[0])
        self.assertFalse(Route.objects.exists())

    def test_register_revalidates_route_data(self):
        a = create_appointment()
        self.set_draft(selected=[a.pk])
        create_route(vehicle=self.vehicle)  # veículo ocupado depois do rascunho
        response = self.client.post(SELECTION, {"action": "register"})
        self.assertRedirects(response, REGISTER)
        self.assertIn("Revise os dados da rota", messages_of(response)[0])
        self.assertEqual(Route.objects.count(), 1)

    def test_register_assignment_conflict_rolls_back(self):
        a = create_appointment()
        self.set_draft(selected=[a.pk])
        with mock.patch("routes.views.assign_appointments", side_effect=AssignmentConflict):
            response = self.client.post(SELECTION, {"action": "register"})
        self.assertRedirects(response, SELECTION)
        self.assertIn("foi incluído em outra rota", messages_of(response)[0])
        self.assertFalse(Route.objects.exists())
        self.assertFalse(AuditLog.objects.exists())
        self.assertIsNotNone(self.draft())


class EditFlowTests(RouteViewTestCase):
    def test_edit_loads_draft(self):
        appointment = create_appointment()
        route = create_route([appointment], vehicle=self.vehicle, motorist=self.motorist)
        response = self.client.get(reverse("routes:edit", args=[route.pk]))
        self.assertRedirects(response, REGISTER)
        draft = self.draft()
        self.assertEqual(draft["route_id"], route.pk)
        self.assertEqual(draft["selected"], [appointment.pk])
        self.assertEqual(self.client.get(REGISTER).context["editing"], route)

    def test_edit_concluded_route_blocked(self):
        route = create_route(date=days(-1))
        response = self.client.get(reverse("routes:edit", args=[route.pk]))
        self.assertRedirects(response, MANAGE)
        self.assertIsNone(self.draft())

    def test_full_edit_updates_route(self):
        kept, removed, added = create_appointment(), create_appointment(), create_appointment()
        route = create_route([kept, removed], vehicle=self.vehicle, motorist=self.motorist)
        other_motorist = create_motorist()

        self.client.get(reverse("routes:edit", args=[route.pk]))
        self.client.post(REGISTER, route_data(self.vehicle, other_motorist, departure_time="09:15"))
        selection = self.client.get(SELECTION)
        self.assertCountEqual(selection.context["options"], [kept, removed, added])

        response = self.client.post(SELECTION, {
            "shown": [str(kept.pk), str(removed.pk), str(added.pk)],
            "appointments": [str(kept.pk), str(added.pk)],
            "action": "register",
        })
        self.assertRedirects(response, MANAGE)
        route.refresh_from_db()
        self.assertEqual(route.motorist, other_motorist)
        self.assertEqual(route.departure_time, datetime.time(9, 15))
        self.assertEqual(set(route.appointments.all()), {kept, added})
        removed.refresh_from_db()
        self.assertIsNone(removed.route)
        self.assertEqual(AuditLog.objects.get().action, "update")
        self.assertIn("Rota atualizada.", messages_of(response))


class ResetViewTests(RouteViewTestCase):
    def test_reset_new_draft(self):
        self.set_draft()
        self.assertRedirects(self.client.get(RESET), REGISTER)
        self.assertIsNone(self.draft())

    def test_reset_while_editing(self):
        route = create_route()
        self.set_draft(route_id=route.pk)
        self.assertRedirects(self.client.get(RESET), MANAGE)
        self.assertIsNone(self.draft())


class VehicleSearchViewTests(RouteViewTestCase):
    def results(self, **params):
        return [r["id"] for r in self.client.get(VEHICLE_SEARCH, params).json()["results"]]

    def test_short_term(self):
        self.assertEqual(self.results(q="v"), [])

    def test_search_by_type_ignoring_accents(self):
        ambulance = create_vehicle(vehicle_type="ambulancia")
        microbus = create_vehicle(vehicle_type="micro-onibus")
        self.assertEqual(self.results(q="Ambulância"), [ambulance.pk])
        self.assertEqual(self.results(q="micro ônibus"), [microbus.pk])

    def test_search_by_plate_and_label(self):
        vehicle = create_vehicle(vehicle_type="carro", plate="QWE1R23", seats=4)
        response = self.client.get(VEHICLE_SEARCH, {"q": "qwe-1"})
        self.assertEqual(
            response.json()["results"],
            [{"id": vehicle.pk, "label": "Carro | QWE1R23 | 4 vagas"}],
        )

    def test_excludes_non_operational(self):
        create_vehicle(vehicle_type="onibus", is_operational=False)
        self.assertEqual(self.results(q="onibus"), [])

    def test_excludes_busy_on_date_except_edited_route(self):
        bus = create_vehicle(vehicle_type="onibus")
        route = create_route(vehicle=bus, date=days(1))
        self.assertEqual(self.results(q="onibus"), [bus.pk])
        self.assertEqual(self.results(q="onibus", date=days(1).isoformat()), [])
        self.assertEqual(self.results(q="onibus", date=days(2).isoformat()), [bus.pk])
        self.assertEqual(
            self.results(q="onibus", date=days(1).isoformat(), route=str(route.pk)), [bus.pk]
        )

    def test_invalid_date_is_ignored(self):
        bus = create_vehicle(vehicle_type="onibus")
        self.assertEqual(self.results(q="onibus", date="2030-13-45"), [bus.pk])
        self.assertEqual(self.results(q="onibus", date="amanhã"), [bus.pk])


class ManageViewTests(RouteViewTestCase):
    def listed(self, **params):
        return list(self.client.get(MANAGE, params).context["page_obj"])

    def test_lists_upcoming_with_people_count(self):
        create_route(date=days(-1))
        route = create_route([
            create_appointment(companions=[create_patient(), create_patient()]),
            create_appointment(),
        ])
        listed = self.listed()
        self.assertEqual(listed, [route])
        self.assertEqual(listed[0].people, 4)

    def test_filters(self):
        a = create_route(date=days(1), region="niteroi", departure_time=datetime.time(6, 0))
        b = create_route(date=days(2), region="campos", departure_time=datetime.time(7, 0))
        self.assertEqual(self.listed(date=days(2).isoformat()), [b])
        self.assertEqual(self.listed(region="niteroi"), [a])
        self.assertEqual(self.listed(time="07:00"), [b])
        self.assertCountEqual(self.listed(), [a, b])

    def test_list_is_ordered_for_pagination(self):
        create_route()
        page_obj = self.client.get(MANAGE).context["page_obj"]
        self.assertTrue(page_obj.paginator.object_list.ordered)

    def test_past_date_filter_shows_error(self):
        route = create_route()
        response = self.client.get(MANAGE, {"date": days(-1).isoformat()})
        self.assertIn("date", response.context["filters"].errors)
        self.assertEqual(list(response.context["page_obj"]), [route])


class DeleteViewTests(RouteViewTestCase):
    def test_get_confirmation(self):
        route = create_route()
        response = self.client.get(reverse("routes:delete", args=[route.pk]))
        self.assertTemplateUsed(response, "core/confirm_delete.html")
        self.assertEqual(response.context["label"], route.name)
        self.assertIn("voltarão para a lista", response.context["note"])

    def test_post_deletes_and_releases_appointments(self):
        appointment = create_appointment()
        route = create_route([appointment])
        response = self.client.post(reverse("routes:delete", args=[route.pk]))
        self.assertRedirects(response, MANAGE)
        self.assertFalse(Route.objects.exists())
        appointment.refresh_from_db()
        self.assertIsNone(appointment.route)
        log = AuditLog.objects.get()
        self.assertEqual((log.action, log.entity_id), ("delete", route.pk))

    def test_post_clears_draft_of_deleted_route(self):
        route = create_route()
        other = create_route()
        self.set_draft(route_id=route.pk)
        self.client.post(reverse("routes:delete", args=[route.pk]))
        self.assertIsNone(self.draft())

        self.set_draft(route_id=other.pk)
        self.client.post(reverse("routes:delete", args=[create_route().pk]))
        self.assertEqual(self.draft()["route_id"], other.pk)

    def test_concluded_route_blocked(self):
        route = create_route(date=days(-1))
        response = self.client.post(reverse("routes:delete", args=[route.pk]))
        self.assertRedirects(response, MANAGE)
        self.assertTrue(Route.objects.exists())
