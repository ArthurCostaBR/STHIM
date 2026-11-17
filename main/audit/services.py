from .models import AuditLog

def log_action(user, action, instance, label=None):
    if action not in AuditLog.Action.values:
        raise ValueError(f"Ação inválida: {action!r}")

    if label is None:
        label = instance.audit_label() if hasattr(instance, "audit_label") else str(instance)

    return AuditLog.objects.create(
        user_id=getattr(user, "pk", None),
        user_name=getattr(user, "username", ""),
        action=action,
        entity_type=instance._meta.label_lower,
        entity_id=instance.pk,
        entity_label=label[:200],
    )