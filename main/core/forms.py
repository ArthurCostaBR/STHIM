from django import forms

DEFAULT_EMPTY = "---------"

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
                if field.empty_label == DEFAULT_EMPTY:
                    field.empty_label = label
            elif isinstance(field, forms.ChoiceField):
                choices = list(field.choices)
                if choices and choices[0] == ("", DEFAULT_EMPTY):
                    field.choices = [("", label)] + choices[1:]