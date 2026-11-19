from django.test import TestCase
from django.urls import reverse
from accounts.models import Sector
from core.factories import create_user

HOME = reverse("pages:home")

MENU = {
    "Cadastro de pacientes e acompanhantes": reverse("patients:manage"),
    "Agendamento de transporte": reverse("appointments:schedule"),
    "Gerenciamento de agendamentos": reverse("appointments:manage"),
    "Cadastro de rotas": reverse("routes:register"),
    "Gerenciamento de rotas": reverse("routes:manage"),
    "Cadastro de frota": reverse("fleet:manage"),
    "Cadastro de motorista": reverse("motorists:manage"),
    "Impressão de planilhas": reverse("reports:sheets"),
}

VISIBLE = {
    Sector.MARCACAO: {
        "Cadastro de pacientes e acompanhantes",
        "Agendamento de transporte",
        "Gerenciamento de agendamentos",
    },
    Sector.ADMINISTRACAO: {
        "Cadastro de rotas",
        "Gerenciamento de rotas",
        "Cadastro de frota",
        "Cadastro de motorista",
        "Impressão de planilhas",
    },
    Sector.GESTAO: {"Impressão de planilhas"},
}


class HomeViewTests(TestCase):
    def test_requires_login(self):
        response = self.client.get(HOME)
        self.assertRedirects(response, f"{reverse('accounts:login')}?next={HOME}")

    def test_renders_for_logged_user(self):
        self.client.force_login(create_user())
        response = self.client.get(HOME)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "homepage/homepage.html")

    def test_menu_shows_only_sector_features(self):
        for sector, visible in VISIBLE.items():
            with self.subTest(sector=sector):
                self.client.force_login(create_user(sector))
                response = self.client.get(HOME)
                for label, url in MENU.items():
                    if label in visible:
                        self.assertContains(response, f'href="{url}"')
                    else:
                        self.assertNotContains(response, f'href="{url}"')

    def test_superuser_sees_whole_menu(self):
        self.client.force_login(create_user("", is_superuser=True))
        response = self.client.get(HOME)
        for url in MENU.values():
            self.assertContains(response, f'href="{url}"')
