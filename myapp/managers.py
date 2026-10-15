from django.db import models


class InquiryQuerySet(models.QuerySet):
    def open(self):
        return self.filter(status__in=('new', 'in_progress'))

    def new(self):
        return self.filter(status='new')

    def replied(self):
        return self.filter(status='replied')

    def closed(self):
        return self.filter(status='closed')

    def inbox(self):
        return self.open().order_by('-created_at')


class InquiryManager(models.Manager):
    def get_queryset(self):
        return InquiryQuerySet(self.model, using=self._db)

    def inbox(self):
        return self.get_queryset().inbox()

    def open_count(self):
        return self.get_queryset().open().count()