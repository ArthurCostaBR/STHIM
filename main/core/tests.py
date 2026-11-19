from django import forms
from django.core.exceptions import ValidationError
from django.test import SimpleTestCase, TestCase
from core.factories import make_cpf
from core.fields import CPFField
from core.formatters import format_cep, format_cpf, format_phone, format_sus
from core.forms import DEFAULT_EMPTY, SelectPlaceholderMixin, YesNoField
from core.normalizers import digits_only, plate_normalizer
from core.validators import phone_validator, validate_cpf

VALID_CPF = "52998224725"


class ValidateCPFTests(SimpleTestCase):
    def test_accepts_valid_cpf(self):
        validate_cpf(VALID_CPF)

    def test_accepts_generated_cpfs(self):
        for n in (1, 42, 123456, 987654321):
            validate_cpf(make_cpf(n))

    def test_rejects_empty(self):
        with self.assertRaises(ValidationError) as ctx:
            validate_cpf("")
        self.assertEqual(ctx.exception.code, "empty_cpf")

    def test_rejects_malformed(self):
        for value in ("123", "5299822472", "529982247250", "529.982.247-25", "abcdefghijk"):
            with self.subTest(value=value), self.assertRaises(ValidationError) as ctx:
                validate_cpf(value)
            self.assertEqual(ctx.exception.code, "invalid_cpf")

    def test_rejects_repeated_digits(self):
        for digit in "0123456789":
            with self.subTest(digit=digit), self.assertRaises(ValidationError):
                validate_cpf(digit * 11)

    def test_rejects_wrong_check_digits(self):
        for value in ("52998224724", "52998224715"):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                validate_cpf(value)


class PhoneValidatorTests(SimpleTestCase):
    def test_accepts_10_and_11_digits(self):
        phone_validator("2133334444")
        phone_validator("21987654321")

    def test_rejects_other_lengths_and_non_digits(self):
        for value in ("213333444", "219876543210", "(21)98765-4321", ""):
            with self.subTest(value=value), self.assertRaises(ValidationError) as ctx:
                phone_validator(value)
            self.assertEqual(ctx.exception.code, "invalid_phone")


class NormalizerTests(SimpleTestCase):
    def test_digits_only(self):
        self.assertEqual(digits_only("529.982.247-25"), "52998224725")
        self.assertEqual(digits_only("(21) 98765-4321"), "21987654321")
        self.assertEqual(digits_only("abc"), "")
        self.assertIsNone(digits_only(None))
        self.assertEqual(digits_only(""), "")

    def test_plate_normalizer(self):
        self.assertEqual(plate_normalizer("abc-1d23"), "ABC1D23")
        self.assertEqual(plate_normalizer(" abc 1234 "), "ABC1234")
        self.assertIsNone(plate_normalizer(None))
        self.assertEqual(plate_normalizer(""), "")


class FormatterTests(SimpleTestCase):
    def test_format_cpf(self):
        self.assertEqual(format_cpf("52998224725"), "529.982.247-25")
        self.assertEqual(format_cpf("123"), "123")
        self.assertEqual(format_cpf(None), "")

    def test_format_sus(self):
        self.assertEqual(format_sus("700000000000001"), "700 0000 0000 0001")
        self.assertEqual(format_sus("123"), "123")
        self.assertEqual(format_sus(None), "")

    def test_format_phone(self):
        self.assertEqual(format_phone("21987654321"), "(21) 98765-4321")
        self.assertEqual(format_phone("2133334444"), "(21) 3333-4444")
        self.assertEqual(format_phone("123"), "123")
        self.assertEqual(format_phone(None), "")
        self.assertEqual(format_phone(""), "")

    def test_format_cep(self):
        self.assertEqual(format_cep("20000000"), "20000-000")
        self.assertEqual(format_cep("123"), "123")
        self.assertEqual(format_cep(None), "")


class CPFFieldTests(SimpleTestCase):
    def test_max_length_is_forced_to_11(self):
        self.assertEqual(CPFField(max_length=50).max_length, 11)

    def test_to_python_strips_mask(self):
        field = CPFField()
        self.assertEqual(field.to_python("529.982.247-25"), "52998224725")
        self.assertIsNone(field.to_python(None))

    def test_clean_validates_masked_value(self):
        field = CPFField()
        self.assertEqual(field.clean("529.982.247-25", None), "52998224725")
        with self.assertRaises(ValidationError):
            field.clean("111.111.111-11", None)

    def test_formfield_accepts_masked_length(self):
        self.assertEqual(CPFField().formfield().max_length, 14)


class YesNoFieldTests(SimpleTestCase):
    def test_coerces_to_bool(self):
        field = YesNoField()
        self.assertIs(field.clean("True"), True)
        self.assertIs(field.clean("False"), False)
        self.assertIs(field.initial, False)

    def test_rejects_unknown_value(self):
        with self.assertRaises(ValidationError):
            YesNoField().clean("talvez")


class SelectPlaceholderMixinTests(TestCase):
    def test_replaces_dashed_empty_choice_with_label(self):
        from accounts.models import User

        class SampleForm(SelectPlaceholderMixin, forms.Form):
            color = forms.ChoiceField(
                label="Cor", choices=[("", DEFAULT_EMPTY), ("a", "Azul")]
            )
            other = forms.ChoiceField(label="Outro", choices=[("x", "X")])
            user = forms.ModelChoiceField(
                label="Usuário", queryset=User.objects.all(), empty_label=DEFAULT_EMPTY
            )

        form = SampleForm()
        self.assertEqual(list(form.fields["color"].choices), [("", "Cor"), ("a", "Azul")])
        self.assertEqual(list(form.fields["other"].choices), [("x", "X")])
        self.assertEqual(form.fields["user"].empty_label, "Usuário")

    def test_replaces_django_default_empty_label_in_model_forms(self):
        from fleet.forms import VehicleForm
        from routes.forms import RouteForm

        self.assertEqual(
            list(VehicleForm().fields["vehicle_type"].choices)[0], ("", "Tipo de veículo")
        )
        self.assertEqual(RouteForm().fields["vehicle"].empty_label, "Veículo")
