from django.db import models
from django.utils import timezone
from phonenumber_field.modelfields import PhoneNumberField

from core.utils.images import image_dimensions_for, optimize_image_field


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


class ImageOptimizationMixin(models.Model):
    """Override ``save()`` to run the Pillow pipeline on declared image fields.

    A model opts in by defining::

        IMAGE_SPECS = {
            # field_name: (max_width, max_height, thumb_size or None)
            'image': (1600, 1200, 400),
        }

    Only new uploads are re-encoded, so existing optimized files are untouched.
    """

    IMAGE_SPECS = {}

    class Meta:
        abstract = True

    def _image_snapshot(self):
        return {
            f: (getattr(self, f).name if getattr(self, f) else '')
            for f in self.IMAGE_SPECS
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._image_snapshot = self._image_snapshot()
        self._image_optimizing = False

    def save(self, *args, **kwargs):
        current = {f: (getattr(self, f).name if getattr(self, f) else '') for f in self.IMAGE_SPECS}
        super().save(*args, **kwargs)
        if self._image_optimizing:
            return

        dirty = []
        for field, spec in self.IMAGE_SPECS.items():
            if not current[field]:
                continue  # field cleared — nothing to process
            from core.utils.images import image_dimensions_for, optimize_image_field
            max_w, max_h, thumb = image_dimensions_for(spec)
            if optimize_image_field(self, field, max_w, max_h, thumb):
                dirty.append(field)

        if not dirty:
            self._image_snapshot = current
            return

        self._image_optimizing = True
        try:
            self._image_snapshot = {
                f: (getattr(self, f).name if getattr(self, f) else '')
                for f in self.IMAGE_SPECS
            }
            super().save(update_fields=dirty)
        finally:
            self._image_optimizing = False

class SiteConfiguration(ImageOptimizationMixin):
    IMAGE_SPECS = {
        "site_logo": (400, 400, None),
        "site_bg": (1920, 1080, 480),
        "about_image": (1200, 800, 480),
    }

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
        result = super().save(*args, **kwargs)  # runs image optimization (mixin) + model save
        # Bust the cached singleton in the context processor immediately.
        try:
            from django.core.cache import cache
            cache.delete('core:site_configuration')
        except Exception:
            pass
        return result

    def delete(self, *args, **kwargs):
        result = super().delete(*args, **kwargs)
        try:
            from django.core.cache import cache
            cache.delete('core:site_configuration')
        except Exception:
            pass
        return result

    def __str__(self):
        return self.site_name
