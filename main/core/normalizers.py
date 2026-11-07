import re

def digits_only(value: str) -> str | None:
    if value:
        return re.sub(r"[^0-9]", "", value)
    return value

def cpf_normalizer(value: str) -> str | None:
    return digits_only(value)