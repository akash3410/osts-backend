"""Signals: cascade progress rollup on task/milestone/project change."""
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from projects.models import Milestone, Project, Task


@receiver(post_save, sender=Task)
def _task_saved(sender, instance, created, **kwargs):
    update_fields = kwargs.get('update_fields')
    if update_fields and set(update_fields) <= {'progress_pct', 'updated_at'}:
        return
    from projects.services import recompute_for_task

    recompute_for_task(instance)


@receiver(post_delete, sender=Task)
def _task_deleted(sender, instance, **kwargs):
    if instance.milestone_id is not None:
        from projects.services import recompute_for_task

        try:
            recompute_for_task(instance)
        except Exception:
            pass


@receiver(post_save, sender=Milestone)
def _milestone_saved(sender, instance, created, **kwargs):
    update_fields = kwargs.get('update_fields')
    if update_fields and set(update_fields) <= {'progress_pct', 'updated_at'}:
        return
    from projects.services import recompute_milestone, recompute_for_milestone

    recompute_milestone(instance)
    recompute_for_milestone(instance)


@receiver(post_delete, sender=Milestone)
def _milestone_deleted(sender, instance, **kwargs):
    if instance.project_id is not None:
        from projects.services import recompute_project

        try:
            recompute_project(instance.project)
        except Exception:
            pass


@receiver(post_save, sender=Project)
def _project_saved(sender, instance, created, **kwargs):
    update_fields = kwargs.get('update_fields')
    if update_fields and set(update_fields) <= {'progress_pct', 'updated_at'}:
        return
    from projects.services import recompute_project

    recompute_project(instance)