import re

def cpf_normalizer(cpf: str) -> str:

    return re.sub(r"[^0-9]", "", cpf)