from django.contrib.auth.models import AnonymousUser
from django.http import HttpResponse
from django.test import RequestFactory, TestCase
from django.urls import reverse
from accounts.access import (
    ALL_FEATURES, SECTOR_FEATURES, Feature, feature_required, features_for, has_feature,
)
from accounts.context_processors import features
from accounts.forms import LoginForm, SignupForm
from accounts.models import Sector, User
from core.factories import PASSWORD, create_user, make_cpf


class UserModelTests(TestCase):
    def test_cpf_is_the_login_field(self):
        self.assertEqual(User.USERNAME_FIELD, "cpf")

    def test_new_users_are_inactive_by_default(self):
        user = User.objects.create_user(
            username="Ana", cpf=make_cpf(), sector=Sector.MARCACAO, password=PASSWORD
        )
        self.assertFalse(user.is_active)
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)

    def test_str(self):
        user = create_user(username="Ana", cpf="52998224725")
        self.assertEqual(str(user), "Ana (52998224725)")

    def test_username_is_not_unique(self):
        create_user(username="Maria")
        create_user(username="Maria")
        self.assertEqual(User.objects.filter(username="Maria").count(), 2)


class FeatureAccessTests(TestCase):
    def test_anonymous_has_no_features(self):
        self.assertEqual(features_for(AnonymousUser()), set())

    def test_inactive_user_has_no_features(self):
        user = create_user(Sector.ADMINISTRACAO, is_active=False)
        self.assertEqual(features_for(user), set())

    def test_superuser_has_all_features(self):
        user = create_user("", is_superuser=True)
        self.assertEqual(features_for(user), ALL_FEATURES)

    def test_each_sector_features(self):
        for sector, expected in SECTOR_FEATURES.items():
            with self.subTest(sector=sector):
                self.assertEqual(features_for(create_user(sector)), expected)

    def test_unknown_sector_has_no_features(self):
        self.assertEqual(features_for(create_user("")), set())

    def test_has_feature(self):
        user = create_user(Sector.GESTAO)
        self.assertTrue(has_feature(user, Feature.SHEETS))
        self.assertFalse(has_feature(user, Feature.ROUTES))

    def test_context_processor(self):
        request = RequestFactory().get("/")
        request.user = create_user(Sector.MARCACAO)
        self.assertEqual(
            features(request)["features"], SECTOR_FEATURES[Sector.MARCACAO]
        )


class FeatureRequiredDecoratorTests(TestCase):
    def setUp(self):
        @feature_required(Feature.FLEET)
        def view(request):
            return HttpResponse("ok")

        self.view = view
        self.factory = RequestFactory()

    def test_anonymous_is_redirected_to_login(self):
        request = self.factory.get("/x/")
        request.user = AnonymousUser()
        response = self.view(request)
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("accounts:login"), response.url)

    def test_user_without_feature_gets_403(self):
        from django.core.exceptions import PermissionDenied

        request = self.factory.get("/x/")
        request.user = create_user(Sector.MARCACAO)
        with self.assertRaises(PermissionDenied):
            self.view(request)

    def test_user_with_feature_gets_through(self):
        request = self.factory.get("/x/")
        request.user = create_user(Sector.ADMINISTRACAO)
        self.assertEqual(self.view(request).content, b"ok")

    def test_preserves_view_name(self):
        def my_view(request):
            return HttpResponse()

        self.assertEqual(feature_required(Feature.FLEET)(my_view).__name__, "my_view")


class SignupTests(TestCase):
    url = reverse("accounts:signup")

    def data(self, **overrides):
        data = {
            "username": "João da Silva",
            "cpf": "529.982.247-25",
            "sector": Sector.MARCACAO,
            "password1": PASSWORD,
            "password2": PASSWORD,
        }
        data.update(overrides)
        return data

    def test_form_normalizes_masked_cpf(self):
        form = SignupForm(self.data())
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["cpf"], "52998224725")

    def test_form_rejects_invalid_cpf(self):
        form = SignupForm(self.data(cpf="111.111.111-11"))
        self.assertFalse(form.is_valid())
        self.assertIn("cpf", form.errors)

    def test_form_rejects_cpf_without_digits(self):
        form = SignupForm(self.data(cpf="abc"))
        self.assertFalse(form.is_valid())
        self.assertIn("cpf", form.errors)

    def test_form_rejects_duplicate_cpf(self):
        create_user(cpf="52998224725")
        form = SignupForm(self.data())
        self.assertFalse(form.is_valid())
        self.assertIn("cpf", form.errors)

    def test_form_requires_sector(self):
        form = SignupForm(self.data(sector=""))
        self.assertFalse(form.is_valid())
        self.assertIn("sector", form.errors)

    def test_form_rejects_mismatched_passwords(self):
        form = SignupForm(self.data(password2="Outra!Senha2026"))
        self.assertFalse(form.is_valid())
        self.assertIn("password2", form.errors)

    def test_get_renders_form(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "signup/signup.html")

    def test_post_creates_inactive_user_and_redirects(self):
        response = self.client.post(self.url, self.data())
        self.assertRedirects(response, reverse("accounts:login"))
        user = User.objects.get(cpf="52998224725")
        self.assertFalse(user.is_active)
        self.assertEqual(user.username, "João da Silva")
        self.assertEqual(user.sector, Sector.MARCACAO)
        self.assertTrue(user.check_password(PASSWORD))

    def test_invalid_post_rerenders(self):
        response = self.client.post(self.url, self.data(cpf="123"))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.exists())


class LoginTests(TestCase):
    url = reverse("accounts:login")

    def setUp(self):
        self.user = create_user(cpf="52998224725")

    def test_get_renders_form(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "login/login.html")

    def test_login_with_masked_cpf(self):
        response = self.client.post(
            self.url, {"cpf": "529.982.247-25", "password": PASSWORD}
        )
        self.assertRedirects(response, reverse("pages:home"))
        self.assertEqual(int(self.client.session["_auth_user_id"]), self.user.pk)

    def test_wrong_password(self):
        form = LoginForm(None, {"cpf": "52998224725", "password": "errada"})
        self.assertFalse(form.is_valid())
        self.assertEqual(form.non_field_errors().as_data()[0].code, "invalid_credentials")

    def test_unknown_cpf(self):
        form = LoginForm(None, {"cpf": make_cpf(), "password": PASSWORD})
        self.assertFalse(form.is_valid())
        self.assertEqual(form.non_field_errors().as_data()[0].code, "invalid_credentials")

    def test_pending_approval(self):
        create_user(cpf="11144477735", is_active=False)
        form = LoginForm(None, {"cpf": "111.444.777-35", "password": PASSWORD})
        self.assertFalse(form.is_valid())
        self.assertEqual(form.non_field_errors().as_data()[0].code, "pending_approval")

    def test_inactive_user_with_wrong_password_gets_generic_error(self):
        create_user(cpf="11144477735", is_active=False)
        form = LoginForm(None, {"cpf": "11144477735", "password": "errada"})
        self.assertFalse(form.is_valid())
        self.assertEqual(form.non_field_errors().as_data()[0].code, "invalid_credentials")

    def test_cpf_without_digits(self):
        form = LoginForm(None, {"cpf": "abc", "password": PASSWORD})
        self.assertFalse(form.is_valid())
        self.assertIn("cpf", form.errors)

    def test_failed_post_does_not_log_in(self):
        response = self.client.post(self.url, {"cpf": "52998224725", "password": "x"})
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)


class LogoutTests(TestCase):
    def test_logout_redirects_to_login(self):
        self.client.force_login(create_user())
        response = self.client.post(reverse("accounts:logout"))
        self.assertRedirects(response, reverse("accounts:login"))
        self.assertNotIn("_auth_user_id", self.client.session)
