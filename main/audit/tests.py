import datetime
from django.contrib import admin
from django.contrib.auth.models import AnonymousUser
from django.test import RequestFactory, TestCase
from audit.admin import AuditLogAdmin
from audit.models import AuditLog
from audit.services import log_action
from core.factories import create_patient, create_user, create_vehicle


class LogActionTests(TestCase):
    def setUp(self):
        self.user = create_user(username="Operador")

    def test_creates_entry_using_audit_label(self):
        patient = create_patient(name="Maria Souza")
        entry = log_action(self.user, AuditLog.Action.CREATE, patient)

        entry.refresh_from_db()
        self.assertEqual(entry.user_id, self.user.pk)
        self.assertEqual(entry.user_name, "Operador")
        self.assertEqual(entry.action, "create")
        self.assertEqual(entry.entity_type, "patients.patient")
        self.assertEqual(entry.entity_id, patient.pk)
        self.assertEqual(entry.entity_label, "Maria Souza")
        self.assertIsNotNone(entry.timestamp)

    def test_falls_back_to_str_without_audit_label(self):
        vehicle = create_vehicle(plate="ABC1234")
        entry = log_action(self.user, AuditLog.Action.UPDATE, vehicle)
        self.assertEqual(entry.entity_label, "Van (ABC1234)")
        self.assertEqual(entry.entity_type, "fleet.vehicle")

    def test_explicit_label_is_truncated_to_200_chars(self):
        entry = log_action(self.user, AuditLog.Action.DELETE, create_vehicle(), label="x" * 300)
        self.assertEqual(len(entry.entity_label), 200)

    def test_rejects_unknown_action(self):
        with self.assertRaises(ValueError):
            log_action(self.user, "publish", create_vehicle())
        self.assertFalse(AuditLog.objects.exists())

    def test_anonymous_user(self):
        entry = log_action(AnonymousUser(), AuditLog.Action.CREATE, create_vehicle())
        self.assertIsNone(entry.user_id)
        self.assertEqual(entry.user_name, "")

    def test_none_user(self):
        entry = log_action(None, AuditLog.Action.CREATE, create_vehicle())
        self.assertIsNone(entry.user_id)
        self.assertEqual(entry.user_name, "")


class AuditLogModelTests(TestCase):
    def test_ordering_is_newest_first(self):
        user = create_user()
        first = log_action(user, AuditLog.Action.CREATE, create_vehicle())
        second = log_action(user, AuditLog.Action.CREATE, create_vehicle())
        AuditLog.objects.filter(pk=first.pk).update(
            timestamp=second.timestamp - datetime.timedelta(minutes=1)
        )
        self.assertEqual(list(AuditLog.objects.all()), [second, first])

    def test_str(self):
        entry = AuditLog(
            timestamp=datetime.datetime(2026, 1, 2, 3, 4),
            user_name="Ana", action="create", entity_type="fleet.vehicle", entity_id=7,
        )
        self.assertEqual(str(entry), "02/01/2026 03:04 Ana create fleet.vehicle#7")


class AuditLogAdminTests(TestCase):
    def setUp(self):
        self.model_admin = AuditLogAdmin(AuditLog, admin.site)
        self.request = RequestFactory().get("/")

    def test_is_read_only(self):
        self.request.user = create_user(is_superuser=True, is_staff=True)
        self.assertFalse(self.model_admin.has_add_permission(self.request))
        self.assertFalse(self.model_admin.has_change_permission(self.request))
        self.assertFalse(self.model_admin.has_delete_permission(self.request))

    def test_only_superuser_can_view(self):
        self.request.user = create_user(is_staff=True)
        self.assertFalse(self.model_admin.has_view_permission(self.request))
        self.request.user = create_user(is_superuser=True, is_staff=True)
        self.assertTrue(self.model_admin.has_view_permission(self.request))
