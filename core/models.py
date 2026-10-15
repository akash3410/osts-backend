from django.db import models
from django.utils import timezone
from phonenumber_field.modelfields import PhoneNumberField


class TimeStampedModel(models.Model):
    """Abstract base: created_at / updated_at on every model.

    ``created_at`` is immutable (auto_now_add). ``updated_at`` refreshes on
    every save so we always know when a row last changed.
    """

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True
        # Subclasses override when a different default order is needed.
        ordering = ["-created_at"]


class SoftDeleteModel(TimeStampedModel):
    """Abstract base: soft delete via ``deleted_at``.

    Rows are never hard-deleted by the app, so history (inquiries, payments)
    survives. Use the ``objects`` manager (excludes deleted) or
    ``all_objects`` (includes them) explicitly.
    """

    deleted_at = models.DateTimeField(null=True, blank=True, db_index=True)

    class Meta:
        abstract = True

    @property
    def is_deleted(self):
        return self.deleted_at is not None

    def soft_delete(self):
        """Mark deleted without removing the row."""
        self.deleted_at = timezone.now()
        self.save(update_fields=["deleted_at", "updated_at"])

    def restore(self):
        """Undo a soft delete."""
        self.deleted_at = None
        self.save(update_fields=["deleted_at", "updated_at"])


class ActiveOnlyManager(models.Manager):
    """Manager that hides soft-deleted rows by default."""

    def get_queryset(self):
        return super().get_queryset().filter(deleted_at__isnull=True)


class AllObjectsManager(models.Manager):
    """Manager that returns every row, including soft-deleted ones."""

    def get_queryset(self):
        return super().get_queryset()


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