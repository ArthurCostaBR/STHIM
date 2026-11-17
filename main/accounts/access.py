from functools import wraps
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from .models import Sector

class Feature:
    PATIENTS = "patients"                      # Cadastro e gerenciamento de pacientes
    SCHEDULE_TRANSPORT = "schedule_transport"  # Agendamento de transporte
    APPOINTMENTS = "appointments"              # Gerenciamento de agendamentos
    ROUTES = "routes"                          # Cadastro e gerenciamento de rotas
    FLEET = "fleet"                            # Cadastro e gerenciamento de frota
    MOTORISTS = "motorists"                    # Cadastro e gerenciamento de motoristas
    SHEETS = "sheets"                          # Impressão de planilhas


SECTOR_FEATURES = {
    Sector.MARCACAO: {Feature.PATIENTS, Feature.SCHEDULE_TRANSPORT, Feature.APPOINTMENTS},
    Sector.ADMINISTRACAO: {Feature.ROUTES, Feature.FLEET, Feature.MOTORISTS, Feature.SHEETS},
    Sector.GESTAO: {Feature.SHEETS},
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