from django.db import models
from django.contrib.auth import get_user_model

User = get_user_model()

class Machine(models.Model):
    machine_id = models.CharField(max_length=50, primary_key=True)  # e.g., M-HP200
    name = models.CharField(max_length=100)
    model = models.CharField(max_length=100, blank=True)

    def __str__(self):
        return self.machine_id

class Manual(models.Model):
    document_id = models.CharField(max_length=100)
    machine = models.ForeignKey(Machine, on_delete=models.CASCADE)
    revision = models.CharField(max_length=20)
    file = models.FileField(upload_to='manuals/')
    document_name = models.CharField(max_length=200)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    uploaded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)

    class Meta:
        unique_together = ('document_id', 'machine', 'revision')

    def __str__(self):
        return f"{self.document_name} ({self.machine}) rev {self.revision}"