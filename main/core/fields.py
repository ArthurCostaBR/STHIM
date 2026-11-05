from django.db import models
from .normalizers import cpf_normalizer
from .validators import validate_cpf

class CPFField(models.CharField):
    default_validators = [validate_cpf]

    def __init__(self, *args, **kwargs):
        kwargs["max_length"] = 11
        super().__init__(*args, **kwargs)

    def to_python(self, value):
        value = super().to_python(value)
        return cpf_normalizer(value) if value else value

    def formfield(self, **kwargs):
        kwargs.setdefault("max_length", 14)
        return super().formfield(**kwargs)