import datetime
from django.utils import timezone

DRAFT_KEY = "route_draft"
ROUTE_FIELDS = ("vehicle", "date", "departure_time", "region", "motorist")

def _empty():
    return {"route": None, "date": None, "selected": [], "route_id": None}

def get_draft(request):
    raw = request.session.get(DRAFT_KEY) or {}
    route = raw.get("route")
    if not isinstance(route, dict) or any(field not in route for field in ROUTE_FIELDS):
        return _empty()
    try:
        date = datetime.date.fromisoformat(route["date"])
    except (TypeError, ValueError):
        return _empty()
    if date < timezone.localdate():  # rascunho de uma data que já passou
        return _empty()
    return {
        "route": route,
        "date": date,
        "selected": [int(pk) for pk in raw.get("selected", [])],
        "route_id": raw.get("route_id"),
    }

def save_draft(request, *, route, selected=(), route_id=None):
    request.session[DRAFT_KEY] = {
        "route": route,
        "selected": sorted({int(pk) for pk in selected}),
        "route_id": route_id,
    }

def clear_draft(request):
    request.session.pop(DRAFT_KEY, None)

def data_from_form(cleaned):
    return {
        "vehicle": str(cleaned["vehicle"].pk),
        "date": cleaned["date"].isoformat(),
        "departure_time": cleaned["departure_time"].strftime("%H:%M"),
        "region": cleaned["region"],
        "motorist": str(cleaned["motorist"].pk),
    }

def data_from_route(route):
    return {
        "vehicle": str(route.vehicle_id),
        "date": route.date.isoformat(),
        "departure_time": route.departure_time.strftime("%H:%M"),
        "region": route.region,
        "motorist": str(route.motorist_id),
    }