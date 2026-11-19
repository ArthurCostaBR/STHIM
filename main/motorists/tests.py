from unittest import mock
from django.test import TestCase
from django.urls import reverse
from accounts.models import Sector
from core.factories import (
    create_appointment, create_motorist, create_route, create_user, days, messages_of,
)
from motorists.forms import MotoristsForm
from motorists.models import Motorists
from routes.models import TransportRecord

MANAGE = reverse("motorists:manage")


def motorist_data(**overrides):
    data = {"name": "José Santos", "cpf": "529.982.247-25", "phone": "(21) 3333-4444"}
    data.update(overrides)
    return data


class MotoristModelTests(TestCase):
    def test_str(self):
        self.assertEqual(
            str(create_motorist(name="José", cpf="52998224725")), "José (52998224725)"
        )

    def test_ordering_by_name(self):
        b = create_motorist(name="Bruno")
        a = create_motorist(name="Abel")
        self.assertEqual(list(Motorists.objects.all()), [a, b])

    def test_delete_blockers(self):
        motorist = create_motorist()
        self.assertEqual(motorist.delete_blockers(), [])
        create_route(motorist=motorist, date=days(-1))
        self.assertEqual(motorist.delete_blockers(), [])
        create_route(motorist=motorist, date=days(0))
        self.assertEqual(motorist.delete_blockers(), ["está designado em uma rota ativa"])


class MotoristFormTests(TestCase):
    def test_normalizes_cpf_and_phone(self):
        form = MotoristsForm(motorist_data())
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.instance.cpf, "52998224725")
        self.assertEqual(form.cleaned_data["phone"], "2133334444")

    def test_rejects_invalid_values(self):
        for field, value in {"cpf": "123.456.789-00", "phone": "123", "name": ""}.items():
            with self.subTest(field=field):
                self.assertIn(field, MotoristsForm(motorist_data(**{field: value})).errors)

    def test_duplicate_cpf_message(self):
        create_motorist(cpf="52998224725")
        form = MotoristsForm(motorist_data())
        self.assertEqual(form.errors["cpf"], ["Já existe um motorista com este CPF."])


class MotoristViewAccessTests(TestCase):
    def test_other_sectors_forbidden(self):
        motorist = create_motorist()
        for sector in (Sector.MARCACAO, Sector.GESTAO):
            with self.subTest(sector=sector):
                self.client.force_login(create_user(sector))
                for url in (
                    MANAGE,
                    reverse("motorists:edit", args=[motorist.pk]),
                    reverse("motorists:delete", args=[motorist.pk]),
                ):
                    self.assertEqual(self.client.get(url).status_code, 403)


class MotoristManageViewTests(TestCase):
    def setUp(self):
        self.client.force_login(create_user(Sector.ADMINISTRACAO))

    def test_get_without_search_lists_nothing(self):
        create_motorist()
        response = self.client.get(MANAGE)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context["searched"])
        self.assertEqual(list(response.context["motorists"]), [])

    def test_search_by_name_and_masked_cpf(self):
        jose = create_motorist(name="José Santos", cpf="52998224725")
        create_motorist(name="Carlos")
        self.assertEqual(list(self.client.get(MANAGE, {"q": "josé"}).context["motorists"]), [jose])
        self.assertEqual(list(self.client.get(MANAGE, {"q": "529.98"}).context["motorists"]), [jose])

    def test_create(self):
        response = self.client.post(MANAGE, motorist_data())
        self.assertRedirects(response, MANAGE)
        motorist = Motorists.objects.get()
        self.assertEqual((motorist.cpf, motorist.phone), ("52998224725", "2133334444"))
        self.assertIn("Motorista cadastrado.", messages_of(response))

    def test_invalid_create_rerenders(self):
        response = self.client.post(MANAGE, motorist_data(cpf="1"))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Motorists.objects.exists())

    def test_edit(self):
        motorist = create_motorist(cpf="52998224725")
        url = reverse("motorists:edit", args=[motorist.pk])
        self.assertEqual(self.client.get(url).context["editing"], motorist)

        response = self.client.post(url, motorist_data(name="Novo Nome"))
        self.assertRedirects(response, MANAGE)
        motorist.refresh_from_db()
        self.assertEqual(motorist.name, "Novo Nome")
        self.assertIn("Motorista atualizado.", messages_of(response))

    def test_edit_blocked_when_in_active_route(self):
        motorist = create_motorist(name="Original", cpf="52998224725")
        create_route(motorist=motorist)
        response = self.client.post(
            reverse("motorists:edit", args=[motorist.pk]), motorist_data(name="Alterado")
        )
        self.assertRedirects(response, MANAGE)
        motorist.refresh_from_db()
        self.assertEqual(motorist.name, "Original")


class MotoristDeleteViewTests(TestCase):
    def setUp(self):
        self.client.force_login(create_user(Sector.ADMINISTRACAO))

    def url(self, motorist):
        return reverse("motorists:delete", args=[motorist.pk])

    def test_get_renders_confirmation(self):
        motorist = create_motorist()
        response = self.client.get(self.url(motorist))
        self.assertTemplateUsed(response, "core/confirm_delete.html")
        self.assertEqual(response.context["label"], str(motorist))

    def test_post_deletes(self):
        motorist = create_motorist()
        response = self.client.post(self.url(motorist))
        self.assertRedirects(response, MANAGE)
        self.assertFalse(Motorists.objects.exists())
        self.assertIn("Motorista excluído.", messages_of(response))

    def test_blocked_when_in_active_route(self):
        motorist = create_motorist(name="Zé")
        create_route(motorist=motorist)
        response = self.client.post(self.url(motorist))
        self.assertRedirects(response, MANAGE)
        self.assertIn("Não é possível excluir o motorista Zé", messages_of(response)[0])
        self.assertTrue(Motorists.objects.exists())

    def test_motorist_of_concluded_route_is_deleted_after_freezing(self):
        motorist = create_motorist(name="Zé")
        create_route([create_appointment(date=days(-1))], motorist=motorist, date=days(-1))
        self.client.post(self.url(motorist))
        self.assertFalse(Motorists.objects.exists())
        self.assertEqual(TransportRecord.objects.get().motorist_name, "Zé")

    def test_history_failure_keeps_motorist(self):
        motorist = create_motorist()
        with mock.patch("routes.services.freeze_due_routes", side_effect=RuntimeError):
            with self.assertLogs("routes.services", "ERROR"):
                self.client.post(self.url(motorist))
        self.assertTrue(Motorists.objects.exists())

    def test_history_failure_redirects_back_to_motorists(self):
        motorist = create_motorist()
        with mock.patch("routes.services.freeze_due_routes", side_effect=RuntimeError):
            with self.assertLogs("routes.services", "ERROR"):
                response = self.client.post(self.url(motorist))
        self.assertRedirects(response, MANAGE)
