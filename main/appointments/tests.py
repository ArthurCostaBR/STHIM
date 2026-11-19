import datetime
from django.http import QueryDict
from django.test import TestCase
from django.urls import reverse
from accounts.models import Sector
from appointments.forms import AppointmentFilterForm, AppointmentForm
from appointments.models import Appointment
from audit.models import AuditLog
from core.factories import (
    create_appointment, create_patient, create_route, create_user, days, messages_of,
)

SCHEDULE = reverse("appointments:schedule")
MANAGE = reverse("appointments:manage")
SEARCH = reverse("appointments:patient_search")


def appointment_data(patient, companions=(), **overrides):
    data = {
        "patient": str(patient.pk),
        "companions": [str(c.pk) for c in companions],
        "region": "niteroi",
        "destination": "Hospital Antônio Pedro",
        "boarding_place": "Rodoviária",
        "neighborhood": "Centro",
        "date": days(2).isoformat(),
        "appointment_time": "10:30",
        "has_comorbidity": "True",
        "notes": "Cadeirante",
    }
    data.update(overrides)
    return data


def form_data(patient, companions=(), **overrides):
    """O AppointmentForm usa data.getlist(), como em request.POST."""
    data = QueryDict(mutable=True)
    for key, value in appointment_data(patient, companions, **overrides).items():
        data.setlist(key, value if isinstance(value, list) else [value])
    return data


class AppointmentQuerySetTests(TestCase):
    def test_upcoming_includes_today(self):
        past = create_appointment(date=days(-1))
        today_ = create_appointment(date=days(0))
        future = create_appointment(date=days(3))
        self.assertCountEqual(Appointment.objects.upcoming(), [today_, future])
        self.assertNotIn(past, Appointment.objects.upcoming())

    def test_search_by_patient(self):
        ana = create_appointment(patient=create_patient(name="Ana"))
        create_appointment(patient=create_patient(name="Bruno"))
        self.assertEqual(list(Appointment.objects.search("ana")), [ana])
        self.assertEqual(Appointment.objects.search("").count(), 2)

    def test_unassigned(self):
        free = create_appointment()
        taken = create_appointment()
        create_route([taken])
        self.assertEqual(list(Appointment.objects.unassigned()), [free])

    def test_ordering(self):
        late = create_appointment(appointment_time=datetime.time(15, 0))
        early = create_appointment(appointment_time=datetime.time(8, 0))
        tomorrow = create_appointment(date=days(2), appointment_time=datetime.time(7, 0))
        self.assertEqual(list(Appointment.objects.all()), [early, late, tomorrow])

    def test_str(self):
        appointment = create_appointment(
            patient=create_patient(name="Ana"), date=datetime.date(2030, 5, 6)
        )
        self.assertEqual(str(appointment), "Ana – 06/05/2030")

    def test_route_deletion_releases_appointment(self):
        appointment = create_appointment()
        route = create_route([appointment])
        route.delete()
        appointment.refresh_from_db()
        self.assertIsNone(appointment.route)


class AppointmentFormTests(TestCase):
    def setUp(self):
        self.patient = create_patient(name="Paciente Principal")
        self.companion = create_patient(name="Acompanhante")

    def test_valid(self):
        form = AppointmentForm(form_data(self.patient, [self.companion]))
        self.assertTrue(form.is_valid(), form.errors)
        self.assertIs(form.cleaned_data["has_comorbidity"], True)

    def test_rejects_past_date(self):
        form = AppointmentForm(form_data(self.patient, date=days(-1).isoformat()))
        self.assertEqual(form.errors["date"], ["A data da viagem não pode ser no passado."])

    def test_accepts_today(self):
        form = AppointmentForm(form_data(self.patient, date=days(0).isoformat()))
        self.assertTrue(form.is_valid(), form.errors)

    def test_patient_cannot_be_own_companion(self):
        form = AppointmentForm(form_data(self.patient, [self.patient]))
        self.assertIn(
            "O paciente não pode ser acompanhante dele mesmo.", form.errors["companions"]
        )

    def test_patient_busy_on_date(self):
        create_appointment(patient=self.patient, date=days(2))
        form = AppointmentForm(form_data(self.patient))
        self.assertIn("já está em um agendamento nesta data", form.errors["patient"][0])

    def test_patient_busy_as_companion_on_date(self):
        create_appointment(companions=[self.patient], date=days(2))
        form = AppointmentForm(form_data(self.patient))
        self.assertIn("patient", form.errors)

    def test_companion_busy_on_date(self):
        create_appointment(patient=self.companion, date=days(2))
        form = AppointmentForm(form_data(self.patient, [self.companion]))
        self.assertEqual(
            form.errors["companions"],
            ["Já estão em outro agendamento nesta data: Acompanhante."],
        )

    def test_other_dates_do_not_conflict(self):
        create_appointment(patient=self.patient, date=days(5))
        form = AppointmentForm(form_data(self.patient))
        self.assertTrue(form.is_valid(), form.errors)

    def test_editing_does_not_conflict_with_itself(self):
        appointment = create_appointment(
            patient=self.patient, companions=[self.companion], date=days(2)
        )
        form = AppointmentForm(
            form_data(self.patient, [self.companion]), instance=appointment
        )
        self.assertTrue(form.is_valid(), form.errors)

    def test_patient_options_are_selected_plus_search_results(self):
        other = create_patient(name="Zeca")
        form = AppointmentForm(patient_search="zeca")
        self.assertEqual(list(form.fields["patient"].queryset), [other])
        self.assertFalse(AppointmentForm().fields["patient"].queryset.exists())

        bound = AppointmentForm(form_data(self.patient, [self.companion]))
        self.assertEqual(list(bound.fields["patient"].queryset), [self.patient])
        self.assertEqual(list(bound.fields["companions"].queryset), [self.companion])

    def test_unbound_instance_options(self):
        appointment = create_appointment(patient=self.patient, companions=[self.companion])
        form = AppointmentForm(instance=appointment)
        self.assertEqual(list(form.fields["patient"].queryset), [self.patient])
        self.assertEqual(list(form.fields["companions"].queryset), [self.companion])

    def test_ignores_non_numeric_selected_ids(self):
        data = form_data(self.patient)
        data["patient"] = "abc"
        form = AppointmentForm(data)
        self.assertFalse(form.fields["patient"].queryset.exists())
        self.assertIn("patient", form.errors)

    def test_patient_label_and_picker_attrs(self):
        form = AppointmentForm(instance=create_appointment(patient=self.patient))
        field = form.fields["patient"]
        self.assertEqual(
            field.label_from_instance(self.patient),
            f"Paciente Principal | {self.patient.cpf}",
        )
        self.assertEqual(field.widget.attrs["data-search-url"], SEARCH)


class AppointmentFilterFormTests(TestCase):
    def test_all_optional(self):
        self.assertTrue(AppointmentFilterForm({}).is_valid())

    def test_invalid_region(self):
        self.assertIn("region", AppointmentFilterForm({"region": "marte"}).errors)


class AppointmentViewAccessTests(TestCase):
    def test_other_sectors_forbidden(self):
        appointment = create_appointment()
        for sector in (Sector.ADMINISTRACAO, Sector.GESTAO):
            with self.subTest(sector=sector):
                self.client.force_login(create_user(sector))
                for url in (
                    SCHEDULE, MANAGE, SEARCH,
                    reverse("appointments:edit", args=[appointment.pk]),
                    reverse("appointments:delete", args=[appointment.pk]),
                ):
                    self.assertEqual(self.client.get(url).status_code, 403)


class ScheduleViewTests(TestCase):
    def setUp(self):
        self.user = create_user(Sector.MARCACAO)
        self.client.force_login(self.user)
        self.patient = create_patient()
        self.companion = create_patient()

    def test_get(self):
        response = self.client.get(SCHEDULE, {"q": " ana ", "aq": "bia"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["patient_q"], "ana")
        self.assertEqual(response.context["companion_q"], "bia")

    def test_create(self):
        response = self.client.post(SCHEDULE, appointment_data(self.patient, [self.companion]))
        self.assertRedirects(response, SCHEDULE)
        appointment = Appointment.objects.get()
        self.assertEqual(appointment.registered_by, self.user)
        self.assertEqual(list(appointment.companions.all()), [self.companion])
        self.assertTrue(appointment.has_comorbidity)
        self.assertIsNone(appointment.route)
        self.assertEqual(AuditLog.objects.get().action, "create")
        self.assertIn("Agendamento cadastrado.", messages_of(response))

    def test_invalid_post_rerenders(self):
        response = self.client.post(
            SCHEDULE, appointment_data(self.patient, date=days(-1).isoformat())
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Appointment.objects.exists())

    def test_edit(self):
        author = create_user()
        appointment = create_appointment(patient=self.patient, registered_by=author)
        url = reverse("appointments:edit", args=[appointment.pk])
        self.assertEqual(self.client.get(url).context["editing"], appointment)

        response = self.client.post(
            url, appointment_data(self.patient, [self.companion], destination="Outro")
        )
        self.assertRedirects(response, MANAGE)
        appointment.refresh_from_db()
        self.assertEqual(appointment.destination, "Outro")
        self.assertEqual(appointment.registered_by, author)
        self.assertEqual(list(appointment.companions.all()), [self.companion])
        self.assertEqual(AuditLog.objects.get().action, "update")

    def test_edit_past_appointment_blocked(self):
        appointment = create_appointment(date=days(-1))
        response = self.client.get(reverse("appointments:edit", args=[appointment.pk]))
        self.assertRedirects(response, MANAGE)
        self.assertIn("data passada", messages_of(response)[0])

    def test_edit_appointment_in_active_route_blocked(self):
        appointment = create_appointment()
        create_route([appointment])
        response = self.client.post(
            reverse("appointments:edit", args=[appointment.pk]),
            appointment_data(appointment.patient, destination="Outro"),
        )
        self.assertRedirects(response, MANAGE)
        self.assertIn("Não é possível alterar este agendamento", messages_of(response)[0])
        appointment.refresh_from_db()
        self.assertNotEqual(appointment.destination, "Outro")


class ManageViewTests(TestCase):
    def setUp(self):
        self.client.force_login(create_user(Sector.MARCACAO))

    def listed(self, **params):
        return list(self.client.get(MANAGE, params).context["page_obj"])

    def test_lists_only_upcoming(self):
        create_appointment(date=days(-1))
        upcoming = create_appointment(date=days(0))
        self.assertEqual(self.listed(), [upcoming])

    def test_filters(self):
        ana = create_appointment(patient=create_patient(name="Ana"), region="niteroi", date=days(1))
        bia = create_appointment(patient=create_patient(name="Bia"), region="campos", date=days(2))
        self.assertEqual(self.listed(q="ana"), [ana])
        self.assertEqual(self.listed(region="campos"), [bia])
        self.assertEqual(self.listed(date=days(2).isoformat()), [bia])
        self.assertCountEqual(self.listed(), [ana, bia])

    def test_invalid_filter_ignored(self):
        appointment = create_appointment()
        self.assertEqual(self.listed(region="marte"), [appointment])

    def test_pagination(self):
        for _ in range(27):
            create_appointment()
        response = self.client.get(MANAGE, {"region": "niteroi", "page": 2})
        self.assertEqual(len(response.context["page_obj"].object_list), 2)
        self.assertEqual(response.context["querystring"], "region=niteroi")


class DeleteViewTests(TestCase):
    def setUp(self):
        self.client.force_login(create_user(Sector.MARCACAO))

    def test_get_confirmation(self):
        appointment = create_appointment()
        response = self.client.get(reverse("appointments:delete", args=[appointment.pk]))
        self.assertTemplateUsed(response, "core/confirm_delete.html")
        self.assertEqual(response.context["label"], str(appointment))

    def test_post_deletes_and_logs(self):
        appointment = create_appointment()
        response = self.client.post(reverse("appointments:delete", args=[appointment.pk]))
        self.assertRedirects(response, MANAGE)
        self.assertFalse(Appointment.objects.exists())
        self.assertEqual(AuditLog.objects.get().action, "delete")

    def test_blocked_in_active_route(self):
        appointment = create_appointment()
        create_route([appointment])
        response = self.client.post(reverse("appointments:delete", args=[appointment.pk]))
        self.assertRedirects(response, MANAGE)
        self.assertTrue(Appointment.objects.exists())

    def test_blocked_when_past(self):
        appointment = create_appointment(date=days(-2))
        self.client.post(reverse("appointments:delete", args=[appointment.pk]))
        self.assertTrue(Appointment.objects.exists())

    def test_404(self):
        self.assertEqual(
            self.client.post(reverse("appointments:delete", args=[999999])).status_code, 404
        )


class PatientSearchViewTests(TestCase):
    def setUp(self):
        self.client.force_login(create_user(Sector.MARCACAO))

    def test_short_term_returns_nothing(self):
        create_patient(name="Ana")
        self.assertEqual(self.client.get(SEARCH, {"q": "a"}).json(), {"results": []})

    def test_results(self):
        ana = create_patient(name="Ana Maria", cpf="52998224725")
        create_patient(name="Bruno")
        response = self.client.get(SEARCH, {"q": "ana"})
        self.assertEqual(
            response.json(),
            {"results": [{"id": ana.pk, "label": "Ana Maria | 52998224725"}]},
        )

    def test_limited_to_15(self):
        for i in range(20):
            create_patient(name=f"Silva {i}")
        self.assertEqual(len(self.client.get(SEARCH, {"q": "silva"}).json()["results"]), 15)
