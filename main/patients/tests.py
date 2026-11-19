import datetime
from unittest import mock
from django.core.exceptions import ValidationError
from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from accounts.models import Sector
from appointments.models import Appointment
from audit.models import AuditLog
from core.factories import (
    create_appointment, create_patient, create_route, create_user, days, make_sus, messages_of, today,
)
from patients.forms import PatientForm
from patients.models import Patient
from patients.validators import cep_validator, sus_validator, validate_not_future

MANAGE = reverse("patients:manage")


class ValidatorTests(SimpleTestCase):
    def test_validate_not_future(self):
        validate_not_future(today())
        validate_not_future(datetime.date(1950, 5, 5))
        with self.assertRaises(ValidationError):
            validate_not_future(days(1))

    def test_cep_validator(self):
        cep_validator("20000000")
        for value in ("2000000", "200000000", "20000-000"):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                cep_validator(value)

    def test_sus_validator(self):
        sus_validator("700000000000001")
        for value in ("70000000000000", "7000000000000012", "700 0000 0000 0001"):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                sus_validator(value)


class PatientModelTests(TestCase):
    def test_document_prefers_cpf(self):
        patient = create_patient(cpf="52998224725", sus=make_sus())
        self.assertEqual(patient.document, "52998224725")

    def test_document_falls_back_to_sus(self):
        sus = make_sus()
        patient = create_patient(cpf=None, sus=sus)
        self.assertEqual(patient.document, sus)
        self.assertEqual(str(patient), f"{patient.name} ({sus})")

    def test_str_and_audit_label(self):
        patient = create_patient(name="Ana", cpf="52998224725")
        self.assertEqual(str(patient), "Ana (52998224725)")
        self.assertEqual(patient.audit_label(), "Ana")

    def test_ordering_by_name(self):
        b = create_patient(name="Bruno")
        a = create_patient(name="Ana")
        self.assertEqual(list(Patient.objects.all()), [a, b])

    def test_requires_cpf_or_sus_constraint(self):
        patient = create_patient()
        patient.cpf = None
        patient.sus = None
        with self.assertRaises(ValidationError):
            patient.validate_constraints()


class PatientSearchTests(TestCase):
    def setUp(self):
        self.ana = create_patient(name="Ana Lima", cpf="52998224725", sus=None)
        self.bia = create_patient(name="Beatriz Souza", cpf=None, sus="700000000000001")

    def test_blank_search_returns_everything(self):
        self.assertEqual(Patient.objects.search("  ").count(), 2)
        self.assertEqual(Patient.objects.search(None).count(), 2)

    def test_search_by_name_is_case_insensitive(self):
        self.assertEqual(list(Patient.objects.search("ana")), [self.ana])

    def test_search_by_masked_cpf_prefix(self):
        self.assertEqual(list(Patient.objects.search("529.982")), [self.ana])

    def test_search_by_sus_prefix(self):
        self.assertEqual(list(Patient.objects.search("70000")), [self.bia])


def patient_data(**overrides):
    data = {
        "name": "Carlos Pereira",
        "cpf": "529.982.247-25",
        "sus": "",
        "birth_date": "1970-03-15",
        "phone": "(21) 98765-4321",
        "sex": "m",
        "color": "preta",
        "city": "Niterói",
        "cep": "24000-000",
        "street": "Rua B",
        "neighborhood": "Icaraí",
        "house_number": "200",
    }
    data.update(overrides)
    return data


class PatientFormTests(TestCase):
    def data(self, **overrides):
        return patient_data(**overrides)

    def test_normalizes_masked_fields(self):
        form = PatientForm(self.data(sus="700 0000 0000 0001"))
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.instance.cpf, "52998224725")  # normalizado pelo CPFField
        self.assertEqual(form.cleaned_data["phone"], "21987654321")
        self.assertEqual(form.cleaned_data["cep"], "24000000")
        self.assertEqual(form.cleaned_data["sus"], "700000000000001")

    def test_blank_sus_becomes_none(self):
        form = PatientForm(self.data())
        self.assertTrue(form.is_valid(), form.errors)
        self.assertIsNone(form.cleaned_data["sus"])

    def test_sus_only_is_valid(self):
        form = PatientForm(self.data(cpf="", sus="700000000000001"))
        self.assertTrue(form.is_valid(), form.errors)

    def test_requires_cpf_or_sus(self):
        form = PatientForm(self.data(cpf="", sus=""))
        self.assertFalse(form.is_valid())
        self.assertIn("Informe o CPF ou o SUS.", form.non_field_errors())

    def test_rejects_invalid_values(self):
        cases = {
            "cpf": "123.456.789-00",
            "sus": "123",
            "phone": "1234",
            "cep": "123",
            "birth_date": days(1).isoformat(),
        }
        for field, value in cases.items():
            with self.subTest(field=field):
                form = PatientForm(self.data(**{field: value}))
                self.assertFalse(form.is_valid())
                self.assertIn(field, form.errors)

    def test_rejects_duplicate_cpf_and_sus(self):
        create_patient(cpf="52998224725", sus="700000000000001")
        form = PatientForm(self.data(sus="700000000000001"))
        self.assertFalse(form.is_valid())
        self.assertIn("cpf", form.errors)
        self.assertIn("sus", form.errors)


class PatientViewAccessTests(TestCase):
    def test_anonymous_redirected_to_login(self):
        response = self.client.get(MANAGE)
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("accounts:login"), response.url)

    def test_other_sectors_forbidden(self):
        patient = create_patient()
        for sector in (Sector.ADMINISTRACAO, Sector.GESTAO):
            with self.subTest(sector=sector):
                self.client.force_login(create_user(sector))
                for url in (
                    MANAGE,
                    reverse("patients:edit", args=[patient.pk]),
                    reverse("patients:delete", args=[patient.pk]),
                ):
                    self.assertEqual(self.client.get(url).status_code, 403)


class PatientManageViewTests(TestCase):
    def setUp(self):
        self.user = create_user(Sector.MARCACAO)
        self.client.force_login(self.user)

    def post_data(self, **overrides):
        return patient_data(**overrides)

    def test_get_without_search_lists_nothing(self):
        create_patient()
        response = self.client.get(MANAGE)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context["searched"])
        self.assertEqual(len(response.context["page_obj"].object_list), 0)

    def test_search_lists_matches(self):
        ana = create_patient(name="Ana Lima")
        create_patient(name="Bruno")
        response = self.client.get(MANAGE, {"q": " ana "})
        self.assertTrue(response.context["searched"])
        self.assertEqual(response.context["q"], "ana")
        self.assertEqual(list(response.context["page_obj"]), [ana])

    def test_search_is_paginated(self):
        for i in range(30):
            create_patient(name=f"Silva {i:02d}")
        response = self.client.get(MANAGE, {"q": "silva", "page": 2})
        self.assertEqual(len(response.context["page_obj"].object_list), 5)
        self.assertEqual(response.context["querystring"], "q=silva")

    def test_create_patient(self):
        response = self.client.post(MANAGE, self.post_data())
        self.assertRedirects(response, MANAGE)
        patient = Patient.objects.get(cpf="52998224725")
        self.assertEqual(patient.registered_by, self.user)
        self.assertIn("Paciente cadastrado.", messages_of(response))
        log = AuditLog.objects.get()
        self.assertEqual((log.action, log.entity_id), ("create", patient.pk))

    def test_invalid_post_rerenders_with_errors(self):
        response = self.client.post(MANAGE, self.post_data(name=""))
        self.assertEqual(response.status_code, 200)
        self.assertIn("name", response.context["form"].errors)
        self.assertFalse(Patient.objects.exists())

    def test_edit_patient_keeps_registered_by(self):
        author = create_user()
        patient = create_patient(registered_by=author, cpf="52998224725")
        url = reverse("patients:edit", args=[patient.pk])

        response = self.client.get(url)
        self.assertEqual(response.context["editing"], patient)

        response = self.client.post(url, self.post_data(name="Novo Nome"))
        self.assertRedirects(response, MANAGE)
        patient.refresh_from_db()
        self.assertEqual(patient.name, "Novo Nome")
        self.assertEqual(patient.registered_by, author)
        self.assertEqual(AuditLog.objects.get().action, "update")

    def test_edit_unknown_patient_404(self):
        self.assertEqual(self.client.get(reverse("patients:edit", args=[999999])).status_code, 404)

    def test_edit_blocked_when_patient_is_in_active_route(self):
        patient = create_patient(name="Ana")
        create_route([create_appointment(patient=patient)])
        url = reverse("patients:edit", args=[patient.pk])

        response = self.client.post(url, self.post_data(name="Outro"))
        self.assertRedirects(response, MANAGE)
        self.assertIn("Não é possível alterar o paciente Ana", messages_of(response)[0])
        patient.refresh_from_db()
        self.assertEqual(patient.name, "Ana")

    def test_edit_blocked_when_patient_is_companion_in_active_route(self):
        companion = create_patient(name="Acompanhante")
        create_route([create_appointment(companions=[companion])])
        response = self.client.get(reverse("patients:edit", args=[companion.pk]))
        self.assertRedirects(response, MANAGE)

    def test_edit_allowed_when_route_is_concluded(self):
        patient = create_patient()
        create_route([create_appointment(patient=patient, date=days(-3))], date=days(-3))
        response = self.client.get(reverse("patients:edit", args=[patient.pk]))
        self.assertEqual(response.status_code, 200)


class PatientDeleteViewTests(TestCase):
    def setUp(self):
        self.user = create_user(Sector.MARCACAO)
        self.client.force_login(self.user)

    def url(self, patient):
        return reverse("patients:delete", args=[patient.pk])

    def test_get_renders_confirmation(self):
        patient = create_patient()
        response = self.client.get(self.url(patient))
        self.assertTemplateUsed(response, "core/confirm_delete.html")
        self.assertEqual(response.context["label"], str(patient))

    def test_post_deletes_and_logs(self):
        patient = create_patient()
        response = self.client.post(self.url(patient))
        self.assertRedirects(response, MANAGE)
        self.assertFalse(Patient.objects.filter(pk=patient.pk).exists())
        log = AuditLog.objects.get()
        self.assertEqual((log.action, log.entity_id), ("delete", patient.pk))

    def test_post_removes_past_appointments(self):
        patient = create_patient()
        create_appointment(patient=patient, date=days(-5))
        self.client.post(self.url(patient))
        self.assertFalse(Patient.objects.filter(pk=patient.pk).exists())
        self.assertFalse(Appointment.objects.exists())

    def test_blocked_when_in_active_route(self):
        patient = create_patient()
        create_route([create_appointment(patient=patient)])
        response = self.client.post(self.url(patient))
        self.assertRedirects(response, MANAGE)
        self.assertTrue(Patient.objects.filter(pk=patient.pk).exists())
        self.assertFalse(AuditLog.objects.exists())

    def test_patient_with_future_appointment_is_kept(self):
        patient = create_patient()
        create_appointment(patient=patient)
        response = self.client.post(self.url(patient))
        self.assertRedirects(response, MANAGE)
        self.assertTrue(Patient.objects.filter(pk=patient.pk).exists())
        self.assertTrue(messages_of(response))

    def test_delete_blockers_lists_future_appointments(self):
        patient = create_patient()
        companion = create_patient()
        create_appointment(patient=patient, companions=[companion])
        self.assertEqual(patient.delete_blockers(), ["possui agendamento de transporte"])
        self.assertEqual(
            companion.delete_blockers(),
            ["é acompanhante em um agendamento de transporte"],
        )

    def test_companion_in_future_appointment_cannot_be_deleted(self):
        companion = create_patient()
        appointment = create_appointment(companions=[companion])
        self.client.post(self.url(companion))
        self.assertTrue(Patient.objects.filter(pk=companion.pk).exists())
        self.assertEqual(list(appointment.companions.all()), [companion])

    def test_history_failure_aborts_delete(self):
        patient = create_patient()
        with mock.patch("routes.services.freeze_due_routes", side_effect=RuntimeError):
            with self.assertLogs("routes.services", "ERROR"):
                self.client.post(self.url(patient))
        self.assertTrue(Patient.objects.filter(pk=patient.pk).exists())

    def test_history_failure_redirects_back_to_patients(self):
        patient = create_patient()
        with mock.patch("routes.services.freeze_due_routes", side_effect=RuntimeError):
            with self.assertLogs("routes.services", "ERROR"):
                response = self.client.post(self.url(patient))
        self.assertRedirects(response, MANAGE)

