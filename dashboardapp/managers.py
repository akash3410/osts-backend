from django.db import models


class ServiceQuerySet(models.QuerySet):
    def active(self):
        return self.filter(is_active=True)

    def inactive(self):
        return self.filter(is_active=False)

    def search(self, q):
        if not q:
            return self
        return self.filter(models.Q(title__icontains=q) | models.Q(description__icontains=q))


class ServiceManager(models.Manager):
    def get_queryset(self):
        from .models import Service  # noqa: F401 — keeps import at call time
        return ServiceQuerySet(self.model, using=self._db)

    def active(self):
        return self.get_queryset().active()

    def public_list(self):
        """Services shown to public visitors, newest-first."""
        return self.get_queryset().active().order_by('title')

    def for_owner(self):
        return self.get_queryset()