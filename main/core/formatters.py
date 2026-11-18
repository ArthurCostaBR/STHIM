def format_cpf(value):
    if value and len(value) == 11:
        return f"{value[:3]}.{value[3:6]}.{value[6:9]}-{value[9:]}"
    return value or ""

def format_sus(value):
    if value and len(value) == 15:
        return f"{value[:3]} {value[3:7]} {value[7:11]} {value[11:]}"
    return value or ""

def format_phone(value):
    if not value:
        return ""
    if len(value) == 11:
        return f"({value[:2]}) {value[2:7]}-{value[7:]}"
    if len(value) == 10:
        return f"({value[:2]}) {value[2:6]}-{value[6:]}"
    return value

def format_cep(value):
    if value and len(value) == 8:
        return f"{value[:5]}-{value[5:]}"
    return value or ""