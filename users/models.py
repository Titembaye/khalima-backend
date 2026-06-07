from django.db import models
from django.contrib.auth.models import User


class UserProfile(models.Model):
    ROLE_CHOICES = [
        ('annotator', 'Annotator'),
        ('reviewer', 'Reviewer'),
        ('admin', 'Administrator'),
    ]
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='annotator')

    def __str__(self):
        return f"{self.user.username} ({self.role})"
