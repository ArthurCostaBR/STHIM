import datetime
from django.utils import timezone

DRAFT_KEY = "route_draft"

def get_draft(request):
    """Rascunho do cadastro de rota: data, agendamentos escolhidos e rota em edição."""
    raw = request.session.get(DRAFT_KEY) or {}
    try:
        date = datetime.date.fromisoformat(raw["date"]) if raw.get("date") else None
    except ValueError:
        date = None

    if date and date < timezone.localdate():  # rascunho de uma data que já passou
        return {"date": None, "selected": [], "route_id": None}

    return {
        "date": date,
        "selected": [int(pk) for pk in raw.get("selected", [])],
        "route_id": raw.get("route_id"),
    }


def save_draft(request, *, date, selected, route_id=None):
    request.session[DRAFT_KEY] = {
        "date": date.isoformat() if date else None,
        "selected": sorted({int(pk) for pk in selected}),
        "route_id": route_id,
    }


def clear_draft(request):
    request.session.pop(DRAFT_KEY, None)