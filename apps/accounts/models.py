from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    phone        = models.CharField(max_length=20, blank=True)
    barangay     = models.CharField(max_length=100, blank=True)
    municipality = models.CharField(max_length=100, default='Panabo City')
    province     = models.CharField(max_length=100, default='Davao del Norte')
    created_at   = models.DateTimeField(auto_now_add=True)
    updated_at   = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.get_full_name()} ({self.username})"
