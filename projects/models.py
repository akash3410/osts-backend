"""Projects domain: per-client work, broken into milestones and tasks.

Progress rolls up:
  Task    -> done/total (with `doing` counting as 0.5 by default)
  Milestone -> avg of its tasks
  Project   -> avg of its milestones (or avg of tasks if no milestones)

Stored as cached fields and recomputed on every save via the helpers in
projects.services.rollup. Signals (post_save/post_delete on Task/Milestone)
keep the cache honest.
"""

from django.db import models
from django.utils.text import slugify

from core.models import TimeStampedModel, SoftDeleteModel
from userapp.models import Client, Employee
from core.managers import TimestampedManager


class ProjectStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    ACTIVE = "active", "Active"
    ON_HOLD = "on_hold", "On hold"
    COMPLETED = "completed", "Completed"
    CANCELLED = "cancelled", "Cancelled"


class MilestoneStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    IN_PROGRESS = "in_progress", "In progress"
    DONE = "done", "Done"


class TaskStatus(models.TextChoices):
    TODO = "todo", "To do"
    DOING = "doing", "Doing"
    DONE = "done", "Done"
    BLOCKED = "blocked", "Blocked"


class TaskPriority(models.TextChoices):
    LOW = "low", "Low"
    MEDIUM = "medium", "Medium"
    HIGH = "high", "High"


class Project(SoftDeleteModel):
    """A per-client engagement."""

    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name="projects")
    name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=220, blank=True)
    description = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=ProjectStatus.choices, default=ProjectStatus.DRAFT, db_index=True)

    start_date = models.DateField(null=True, blank=True)
    due_date = models.DateField(null=True, blank=True)

    # Cached, recomputed by the rollup service. 0-100.
    progress_pct = models.DecimalField(max_digits=5, decimal_places=2, default=0)

    # Budget fields (money in the client's currency).
    budget = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    spent = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    objects = TimestampedManager()

    class Meta:
        ordering = ["-created_at"]
        unique_together = [("client", "slug")]
        indexes = [
            models.Index(fields=["status"]),
            models.Index(fields=["client", "status"]),
        ]

    def __str__(self):
        return f"{self.name} ({self.client})"

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(self.name) or "project"
            cand = base
            n = 2
            while Project.objects.filter(client=self.client, slug=cand).exclude(pk=self.pk).exists():
                cand = f"{base}-{n}"
                n += 1
            self.slug = cand
        return super().save(*args, **kwargs)


class Milestone(SoftDeleteModel):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="milestones")
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    due_date = models.DateField(null=True, blank=True)
    order = models.PositiveIntegerField(default=0, db_index=True)
    status = models.CharField(max_length=20, choices=MilestoneStatus.choices, default=MilestoneStatus.PENDING, db_index=True)

    # Cached. 0-100, computed from tasks (or 100 if manually done).
    progress_pct = models.DecimalField(max_digits=5, decimal_places=2, default=0)

    class Meta:
        ordering = ["order", "id"]
        indexes = [models.Index(fields=["project", "order"])]

    def __str__(self):
        return self.title


class Task(SoftDeleteModel):
    milestone = models.ForeignKey(Milestone, on_delete=models.CASCADE, related_name="tasks")
    assignee = models.ForeignKey(Employee, on_delete=models.SET_NULL, null=True, blank=True, related_name="assigned_tasks")

    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=TaskStatus.choices, default=TaskStatus.TODO, db_index=True)
    priority = models.CharField(max_length=10, choices=TaskPriority.choices, default=TaskPriority.MEDIUM)

    estimated_hours = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    actual_hours = models.DecimalField(max_digits=6, decimal_places=2, default=0)

    order = models.PositiveIntegerField(default=0, db_index=True)
    due_date = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ["order", "id"]
        indexes = [models.Index(fields=["milestone", "order"]), models.Index(fields=["status"])]

    def __str__(self):
        return self.title