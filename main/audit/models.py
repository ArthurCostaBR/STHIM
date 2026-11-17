from django.db import models

class AuditLog(models.Model):
    class Action(models.TextChoices):
        CREATE = "create", "Adição"
        UPDATE = "update", "Edição"
        DELETE = "delete", "Exclusão"

    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)
    user_id = models.PositiveIntegerField(null=True, blank=True)
    user_name = models.CharField(max_length=150)
    action = models.CharField(max_length=10, choices=Action.choices)
    entity_type = models.CharField(max_length=60)
    entity_id = models.PositiveIntegerField(null=True, blank=True)
    entity_label = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ["-timestamp"]

    def __str__(self):
        return f"{self.timestamp:%d/%m/%Y %H:%M} {self.user_name} {self.action} {self.entity_type}#{self.entity_id}"