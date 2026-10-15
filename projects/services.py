"""Progress rollup.

Computation rules (deliberately simple and explainable to clients):
  * Task  -> 1.0 if done, 0.5 if doing, 0.0 otherwise
            (or weighted by estimated_hours when ALL tasks of a milestone have
             estimates — then the milestone reflects effort, not just count)
  * Milestone -> weighted average of its live (non-deleted) tasks' progress.
            0.00 if there are no tasks at all
            100.00 if the milestone is marked done and has no tasks
  * Project   -> weighted average of its (non-deleted) milestones' progress
            (weighted by number of tasks each milestone contains).
            100.00 if completed with no milestones, 0 if no milestones.
"""
from decimal import Decimal

from django.db import transaction


def _task_progress(task):
    if task.status == 'done':
        return Decimal('1')
    if task.status == 'doing':
        return Decimal('50')  # /100 at caller if percentage scale
    return Decimal('0')


def recompute_milestone(milestone):
    tasks = milestone.tasks.filter(deleted_at__isnull=True)
    qs = list(tasks)
    if not qs:
        # manual state if there are no tasks
        if milestone.status == 'done':
            milestone.progress_pct = Decimal('100')
        elif milestone.status == 'in_progress':
            milestone.progress_pct = Decimal('50')
        else:
            milestone.progress_pct = Decimal('0')
        milestone.save(update_fields=['progress_pct', 'updated_at'])
        return milestone.progress_pct

    # Weighted by estimated_hours if every task has one
    if all(t.estimated_hours is not None for t in qs):
        total_weight = sum(t.estimated_hours for t in qs)
        if total_weight:
            prog = sum(
                (Decimal('1') if t.status == 'done'
                 else (Decimal('50') if t.status == 'doing' else Decimal('0')))
                * (t.estimated_hours or Decimal('0'))
                for t in qs
            ) / total_weight
            milestone.progress_pct = (prog * Decimal('100')).quantize(Decimal('0.01'))
        else:
            milestone.progress_pct = Decimal('0')
    else:
        counts = len(qs)
        progress = sum(
            (1.0 if t.status == 'done' else (0.5 if t.status == 'doing' else 0.0))
            for t in qs
        )
        milestone.progress_pct = (Decimal(str(progress * 100 / counts))).quantize(Decimal('0.01'))
    milestone.save(update_fields=['progress_pct', 'updated_at'])
    return milestone.progress_pct


def recompute_project(project):
    milestones = project.milestones.filter(deleted_at__isnull=True)
    qs = list(milestones)
    if not qs:
        # No milestones: 100% if completed, else 0.
        if project.status == 'completed':
            project.progress_pct = Decimal('100')
        else:
            project.progress_pct = Decimal('0')
        project.save(update_fields=['progress_pct', 'updated_at'])
        return project.progress_pct

    # Weight milestones by their task counts so a milestone with 10 tasks
    # counts 10x more than a todo milestone with 1 (falls back to 1 for
    # milestones that have no tasks, so manual weighting still counts).
    weights = [max(len(m.tasks.filter(deleted_at__isnull=True)), 1) for m in qs]
    total_w = sum(weights)
    progress = sum(m.progress_pct * w for m, w in zip(qs, weights)) / total_w
    project.progress_pct = progress.quantize(Decimal('0.01'))
    project.save(update_fields=['progress_pct', 'updated_at'])
    return project.progress_pct


def recompute_for_task(task):
    """Cascade from a task change up to its milestone and project."""
    recompute_milestone(task.milestone)
    recompute_project(task.milestone.project)


def recompute_for_milestone(milestone):
    recompute_project(milestone.project)


@transaction.atomic
def mark_task_done(task):
    task.status = 'done'
    task.save(update_fields=['status', 'updated_at'])
    recompute_for_task(task)
    return task


@transaction.atomic
def mark_milestone_done(milestone):
    milestone.status = 'done'
    milestone.save(update_fields=['status', 'updated_at'])
    recompute_for_milestone(milestone)
    return milestone