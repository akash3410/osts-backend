from django.db import models
from django.contrib.auth.models import User
from phonenumber_field.modelfields import PhoneNumberField

# Create your models here.
class Userinfo(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='userinfo')
    phone = PhoneNumberField(region='BD', null=True, blank=True)
    secondary_email = models.EmailField(null=True, blank=True)
    present_address = models.TextField(max_length=100, null=True, blank=True)
    permanent_address = models.TextField(max_length=100, null=True, blank=True)
    profile_picture = models.ImageField(upload_to='document/', null=True, blank=True)
    cover_photo = models.ImageField(upload_to='document/', null=True, blank=True)

    def __str__(self):
        return self.user.username

