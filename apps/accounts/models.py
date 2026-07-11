from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    email = models.EmailField("e-mail", unique=True)

    def __str__(self) -> str:
        return self.get_full_name() or self.username

