from django.db import models
from phonenumber_field.modelfields import PhoneNumberField

# Create your models here.
class Messages(models.Model):
    name = models.CharField(max_length=70)
    email = models.EmailField()
    phone = PhoneNumberField(region='BD', null=True, blank=True)
    service = models.CharField(max_length=255)
    note = models.CharField(max_length=200, null=True, blank=True)

    def __str__(self):
        return self.name