from .access import features_for

def features(request):
    return {"features": features_for(request.user)}