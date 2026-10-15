from django.db import models

from core.models import ImageOptimizationMixin


class Service(ImageOptimizationMixin):
    title = models.CharField(max_length=255, unique=True)
    description = models.TextField()
    icon = models.CharField(max_length=100, blank=True, null=True)
    image = models.ImageField(upload_to="services/", blank=True, null=True)
    price = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Self-hosted Pillow pipeline: uploads get EXIF-stripped, resized, WebP.
    IMAGE_SPECS = {"image": (1920, 1440, 480)}

    class Meta:
        indexes = [
            models.Index(fields=["is_active", "title"]),
            models.Index(fields=["-created_at"]),
        ]

    def __str__(self):
        return self.title