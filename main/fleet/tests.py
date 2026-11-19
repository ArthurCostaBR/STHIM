from unittest import mock
from django.core.exceptions import ValidationError
from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from accounts.models import Sector
from core.factories import (
    create_appointment, create_route, create_user, create_vehicle, days, messages_of,
)
from fleet.forms import VehicleForm
from fleet.models import Vehicle
from fleet.validators import min_max_validator, validate_plate
from routes.models import Route, TransportRecord

MANAGE = reverse("fleet:manage")


class ValidatorTests(SimpleTestCase):
    def test_accepts_old_and_mercosul_plates(self):
        validate_plate("ABC1234")
        validate_plate("ABC1D23")

    def test_rejects_invalid_plates(self):
        for value in ("abc1234", "AB1234", "ABC-1234", "ABCD123", "ABC12345", "1BC1234"):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                validate_plate(value)

    def test_seats_range(self):
        min_max_validator(1)
        min_max_validator(100)
        for value in (0, 101):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                min_max_validator(value)


class VehicleModelTests(TestCase):
    def test_str(self):
        self.assertEqual(str(create_vehicle(vehicle_type="onibus", plate="ABC1D23")), "Ônibus (ABC1D23)")

    def test_is_operational_by_default(self):
        self.assertTrue(create_vehicle().is_operational)


class VehicleFormTests(TestCase):
    def data(self, **overrides):
        data = {"vehicle_type": "van", "seats": "15", "is_operational": "True", "plate": "abc-1d23"}
        data.update(overrides)
        return data

    def test_normalizes_plate(self):
        form = VehicleForm(self.data())
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["plate"], "ABC1D23")

    def test_is_operational_coercion(self):
        form = VehicleForm(self.data(is_operational="False"))
        self.assertTrue(form.is_valid(), form.errors)
        self.assertIs(form.cleaned_data["is_operational"], False)

    def test_invalid_plate(self):
        form = VehicleForm(self.data(plate="12-ABCD"))
        self.assertFalse(form.is_valid())
        self.assertIn("plate", form.errors)

    def test_invalid_seats(self):
        for seats in ("0", "101", "-1"):
            with self.subTest(seats=seats):
                self.assertIn("seats", VehicleForm(self.data(seats=seats)).errors)

    def test_duplicate_plate_message(self):
        create_vehicle(plate="ABC1D23")
        form = VehicleForm(self.data())
        self.assertFalse(form.is_valid())
        self.assertEqual(form.errors["plate"], ["Já existe um veículo com esta placa."])


class FleetViewAccessTests(TestCase):
    def test_other_sectors_forbidden(self):
        vehicle = create_vehicle()
        for sector in (Sector.MARCACAO, Sector.GESTAO):
            with self.subTest(sector=sector):
                self.client.force_login(create_user(sector))
                for url in (
                    MANAGE,
                    reverse("fleet:edit", args=[vehicle.pk]),
                    reverse("fleet:delete", args=[vehicle.pk]),
                ):
                    self.assertEqual(self.client.get(url).status_code, 403)


class VehicleManageViewTests(TestCase):
    def setUp(self):
        self.client.force_login(create_user(Sector.ADMINISTRACAO))

    def test_lists_all_vehicles(self):
        vehicles = [create_vehicle(), create_vehicle(is_operational=False)]
        response = self.client.get(MANAGE)
        self.assertEqual(response.status_code, 200)
        self.assertCountEqual(response.context["vehicles"], vehicles)

    def test_create(self):
        response = self.client.post(
            MANAGE, {"vehicle_type": "carro", "seats": "4", "is_operational": "True", "plate": "xyz9a87"}
        )
        self.assertRedirects(response, MANAGE)
        self.assertTrue(Vehicle.objects.filter(plate="XYZ9A87", seats=4).exists())
        self.assertIn("Veículo cadastrado.", messages_of(response))

    def test_invalid_create_rerenders(self):
        response = self.client.post(MANAGE, {"vehicle_type": "carro", "seats": "4", "plate": "x"})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Vehicle.objects.exists())

    def test_edit(self):
        vehicle = create_vehicle(plate="ABC1234")
        url = reverse("fleet:edit", args=[vehicle.pk])
        self.assertEqual(self.client.get(url).context["editing"], vehicle)

        response = self.client.post(
            url, {"vehicle_type": "van", "seats": "20", "is_operational": "False", "plate": "ABC1234"}
        )
        self.assertRedirects(response, MANAGE)
        vehicle.refresh_from_db()
        self.assertEqual(vehicle.seats, 20)
        self.assertFalse(vehicle.is_operational)
        self.assertIn("Veículo atualizado.", messages_of(response))

    def test_edit_blocked_when_in_active_route(self):
        vehicle = create_vehicle(seats=10)
        create_route(vehicle=vehicle)
        response = self.client.post(
            reverse("fleet:edit", args=[vehicle.pk]),
            {"vehicle_type": "van", "seats": "2", "is_operational": "True", "plate": vehicle.plate},
        )
        self.assertRedirects(response, MANAGE)
        self.assertIn(f"Não é possível alterar o veículo {vehicle.plate}", messages_of(response)[0])
        vehicle.refresh_from_db()
        self.assertEqual(vehicle.seats, 10)

    def test_edit_post_freezes_concluded_routes_first(self):
        vehicle = create_vehicle()
        create_route([create_appointment(date=days(-2))], vehicle=vehicle, date=days(-2))
        response = self.client.post(
            reverse("fleet:edit", args=[vehicle.pk]),
            {"vehicle_type": "van", "seats": "12", "is_operational": "True", "plate": vehicle.plate},
        )
        self.assertRedirects(response, MANAGE)
        self.assertFalse(Route.objects.exists())
        self.assertEqual(TransportRecord.objects.count(), 1)

    def test_edit_aborted_when_history_fails(self):
        vehicle = create_vehicle(seats=10)
        with mock.patch("routes.services.freeze_due_routes", side_effect=RuntimeError):
            with self.assertLogs("routes.services", "ERROR"):
                response = self.client.post(
                    reverse("fleet:edit", args=[vehicle.pk]),
                    {"vehicle_type": "van", "seats": "3", "is_operational": "True", "plate": vehicle.plate},
                )
        self.assertRedirects(response, MANAGE)
        vehicle.refresh_from_db()
        self.assertEqual(vehicle.seats, 10)


class VehicleDeleteViewTests(TestCase):
    def setUp(self):
        self.client.force_login(create_user(Sector.ADMINISTRACAO))

    def url(self, vehicle):
        return reverse("fleet:delete", args=[vehicle.pk])

    def test_get_renders_confirmation(self):
        vehicle = create_vehicle()
        response = self.client.get(self.url(vehicle))
        self.assertTemplateUsed(response, "core/confirm_delete.html")
        self.assertEqual(response.context["label"], str(vehicle))

    def test_post_deletes(self):
        vehicle = create_vehicle()
        response = self.client.post(self.url(vehicle))
        self.assertRedirects(response, MANAGE)
        self.assertFalse(Vehicle.objects.exists())
        self.assertIn("Veículo excluído.", messages_of(response))

    def test_blocked_when_in_active_route(self):
        vehicle = create_vehicle()
        create_route(vehicle=vehicle, date=days(0))
        response = self.client.post(self.url(vehicle))
        self.assertRedirects(response, MANAGE)
        self.assertTrue(Vehicle.objects.filter(pk=vehicle.pk).exists())

    def test_vehicle_used_only_in_concluded_route_is_deleted_after_freezing(self):
        vehicle = create_vehicle()
        create_route([create_appointment(date=days(-1))], vehicle=vehicle, date=days(-1))
        response = self.client.post(self.url(vehicle))
        self.assertRedirects(response, MANAGE)
        self.assertFalse(Vehicle.objects.exists())
        record = TransportRecord.objects.get()
        self.assertEqual(record.vehicle_plate, vehicle.plate)

    def test_history_failure_keeps_vehicle(self):
        vehicle = create_vehicle()
        with mock.patch("routes.services.freeze_due_routes", side_effect=RuntimeError):
            with self.assertLogs("routes.services", "ERROR"):
                response = self.client.post(self.url(vehicle))
        self.assertRedirects(response, MANAGE)
        self.assertTrue(Vehicle.objects.exists())
