from django import forms
from django.db.models.fields import BLANK_CHOICE_LABEL

DEFAULT_EMPTY = "---------"


def _is_default_empty(label) -> bool:
    """Rótulo vazio padrão do Django: "---------" (USE_BLANK_CHOICE_DASH, descontinuado)
    ou BLANK_CHOICE_LABEL ("- Select an option -", traduzível), padrão desde o Django 6.1."""
    return label is not None and str(label) in {DEFAULT_EMPTY, str(BLANK_CHOICE_LABEL)}

class YesNoField(forms.TypedChoiceField):

    def __init__(self, **kwargs):
        kwargs.setdefault("choices", [(True, "Sim"), (False, "Não")])
        kwargs.setdefault("coerce", lambda value: value == "True")
        kwargs.setdefault("initial", False)
        super().__init__(**kwargs)


class SelectPlaceholderMixin:
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            label = str(field.label or "")
            if isinstance(field, forms.ModelChoiceField):
                if _is_default_empty(field.empty_label):
                    field.empty_label = label
            elif isinstance(field, forms.ChoiceField):
                choices = list(field.choices)
                if choices and choices[0][0] == "" and _is_default_empty(choices[0][1]):
                    field.choices = [("", label)] + choices[1:]