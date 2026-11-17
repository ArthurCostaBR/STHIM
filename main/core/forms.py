from django import forms

class YesNoField(forms.TypedChoiceField):

    def __init__(self, **kwargs):
        kwargs.setdefault("choices", [(True, "Sim"), (False, "Não")])
        kwargs.setdefault("coerce", lambda value: value == "True")
        kwargs.setdefault("initial", False)
        super().__init__(**kwargs)