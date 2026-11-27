
from django.contrib.auth.models import AbstractUser
from django.db import models

class User(AbstractUser):
    ROLE_CHOICES = [('Admin','Admin'),('Engineer','Engineer'),('Supervisor','Supervisor')]
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='Engineer')

class Machine(models.Model):
    machine_id = models.CharField(max_length=50, primary_key=True) # M-HP200
    name = models.CharField(max_length=100)
    model = models.CharField(max_length=100, blank=True)
    def __str__(self): return self.machine_id

class Manual(models.Model):
    document_id = models.CharField(max_length=100)
    machine = models.ForeignKey(Machine, on_delete=models.CASCADE)
    revision = models.CharField(max_length=20)
    file = models.FileField(upload_to='manuals/')
    document_name = models.CharField(max_length=200)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    uploaded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)

class QuestionLog(models.Model):
    STATUS = [('answered','answered'),('insufficient','insufficient')]
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    selected_machine = models.ForeignKey(Machine, on_delete=models.CASCADE)
    question = models.TextField()
    answer = models.TextField()
    sources = models.JSONField(default=list) # [{doc_name, doc_id, revision, page, text}]
    status = models.CharField(max_length=20, choices=STATUS)
    timestamp = models.DateTimeField(auto_now_add=True)
