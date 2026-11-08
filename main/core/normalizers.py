import re

def digits_only(value: str | None) -> str | None:
    if value:
        return re.sub(r"[^0-9]", "", value)
    return value

def plate_normalizer(value: str | None) -> str | None:
    if value:
        return re.sub(r"[^A-Za-z0-9]", "", value).upper()
    return value