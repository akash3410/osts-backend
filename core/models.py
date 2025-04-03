from django.db import models
from phonenumber_field.modelfields import PhoneNumberField

# Create your models here.
class SiteConfiguration(models.Model):
    site_name = models.CharField(max_length=255)
    site_logo = models.ImageField(upload_to='logos/', null=True, blank=True)
    site_mail = models.EmailField()
    site_phone = PhoneNumberField(region='BD', null=True, blank=True)
    site_address = models.TextField(max_length=200)
    site_bg = models.ImageField(upload_to='sitebg/', null=True, blank=True)
    fb_page = models.URLField(max_length=300)
    linkedIn = models.URLField(max_length=300)
    contact_description = models.TextField(max_length=500, null=True, blank=True)

    fact_title = models.CharField(max_length=200, null=True, blank=True)
    fact_description = models.TextField(max_length=500, null=True, blank=True)

    about_title = models.CharField(max_length=200)
    about_description = models.TextField(max_length=500)
    about_image = models.ImageField(upload_to='about/', null=True, blank=True)


    maintenance_mode = models.BooleanField(default=False)

    def save(self, *args, **kwargs):
        if SiteConfiguration.objects.exists() and not self.pk:
            raise ValueError("Only one instance of SiteConfiguration can be created.")
        super().save(*args, **kwargs)

    def __str__(self):
        return self.site_name