from functools import wraps
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from .models import Sector

class Feature:
    PATIENTS = "patients"                      
    SCHEDULE_TRANSPORT = "schedule_transport"  
    APPOINTMENTS = "appointments"              
    FIXED_ROUTES = "fixed_routes"              
    CUSTOM_ROUTES = "custom_routes"            
    FLEET = "fleet"                            
    ROUTE_SHEETS = "route_sheets"              
    AUDIT = "audit"                            
    REPORTS = "reports"                        

SECTOR_FEATURES = {
    Sector.MARCACAO: {
        Feature.PATIENTS, Feature.SCHEDULE_TRANSPORT
    },

    Sector.ADMINISTRACAO: {
        Feature.APPOINTMENTS, Feature.FIXED_ROUTES, Feature.CUSTOM_ROUTES,
        Feature.FLEET, Feature.ROUTE_SHEETS, Feature.AUDIT, Feature.REPORTS,
    },

    Sector.GESTAO: {
        Feature.REPORTS
        },
}

ALL_FEATURES = set().union(*SECTOR_FEATURES.values())

def features_for(user) -> set:
    if not user.is_authenticated or not user.is_active:
        return set()
    if user.is_superuser:
        return ALL_FEATURES
    return SECTOR_FEATURES.get(user.sector, set())

def has_feature(user, feature) -> bool:
    return feature in features_for(user)

def feature_required(feature):
    def decorator(view):
        @wraps(view)
        def wrapper(request, *args, **kwargs):
            if not has_feature(request.user, feature):
                raise PermissionDenied
            return view(request, *args, **kwargs)
        return login_required(wrapper)
    return decorator