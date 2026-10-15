"""Tests for the Projects app (milestones + tasks + progress rollup)."""
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.test import Client as TestClient

from userapp.models import Client
from projects.models import (
    Project, Milestone, Task,
    ProjectStatus, MilestoneStatus, TaskStatus, TaskPriority,
)
from projects.services import (
    mark_task_done, mark_milestone_done, recompute_milestone, recompute_project,
)

User = get_user_model()
pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
@pytest.fixture
def client_obj(make_user):
    u = make_user("projectclient")
    c, _ = Client.objects.get_or_create(user=u, defaults={"company_name": "Acme"})
    return c


@pytest.fixture
def project(client_obj):
    return Project.objects.create(client=client_obj, name="Build site")

class TestProjectsBase:
    def test_slug_auto_generated(self, project):
        assert project.slug == "build-site"

    def test_slug_uniqueness_per_client(self, client_obj):
        p1 = Project.objects.create(client=client_obj, name="Build site")
        p2 = Project.objects.create(client=client_obj, name="Build site")
        assert p1.slug == "build-site"
        assert p2.slug == "build-site-2"

    def test_soft_delete_excludes(self, project):
        mk = Milestone.objects.create(project=project, title="M1")
        mk.soft_delete()
        assert Milestone.objects.filter(pk=mk.pk).exists()


# ---------------------------------------------------------------------------
class TestRollupMath:
    def test_task_status_progress_counts(self, project):
        m = Milestone.objects.create(project=project, title="M")
        Task.objects.create(milestone=m, title="T1", status=TaskStatus.DONE)
        Task.objects.create(milestone=m, title="T2", status=TaskStatus.DONE)
        Task.objects.create(milestone=m, title="T3", status=TaskStatus.TODO)
        m.refresh_from_db()
        assert m.progress_pct == Decimal('66.67')

    def test_doing_counts_half(self, project):
        m = Milestone.objects.create(project=project, title="M")
        Task.objects.create(milestone=m, title="T1", status=TaskStatus.DOING)
        Task.objects.create(milestone=m, title="T2", status=TaskStatus.DONE)
        m.refresh_from_db()
        # (0.5 + 1.0) / 2 = 0.75
        assert m.progress_pct == Decimal('75.00')

    def test_weighted_by_estimated_hours(self, project):
        m = Milestone.objects.create(project=project, title="M")
        t1 = Task.objects.create(milestone=m, title="big", estimated_hours=Decimal('10'), status=TaskStatus.DONE)
        t2 = Task.objects.create(milestone=m, title="small", estimated_hours=Decimal('2'), status=TaskStatus.TODO)
        m.refresh_from_db()
        # (10*1 + 2*0) / 12 = 10/12 = 83.333
        assert m.progress_pct == Decimal('83.33')

    def test_milestone_with_no_tasks(self, project):
        m = Milestone.objects.create(project=project, title="M")
        m.refresh_from_db()
        assert m.progress_pct == Decimal('0')  # pending + no tasks

    def test_milestone_done_no_tasks(self, project):
        m = Milestone.objects.create(project=project, title="M", status=MilestoneStatus.DONE)
        m.refresh_from_db()
        assert m.progress_pct == Decimal('100')

    def test_project_weighted_by_task_count(self, project):
        # Milestone 1: 3 tasks (2 done) => 66.67
        # Milestone 2: 1 task (doing)    => 50
        # weighted by task counts: (3*66.67 + 1*50)/4 = 62.5
        m1 = Milestone.objects.create(project=project, title="M1", order=1)
        for s in (TaskStatus.DONE, TaskStatus.DONE, TaskStatus.TODO):
            Task.objects.create(milestone=m1, title='t', status=s)
        m2 = Milestone.objects.create(project=project, title="M2", order=2)
        Task.objects.create(milestone=m2, title='t', status=TaskStatus.DOING)
        project.refresh_from_db()
        assert project.progress_pct == Decimal('62.50')

    def test_project_no_milestones(self, project):
        project.refresh_from_db()
        assert project.progress_pct == Decimal('0')

    def test_project_completed_no_milestones(self, project):
        project.status = ProjectStatus.COMPLETED
        project.save()
        project.refresh_from_db()
        assert project.progress_pct == Decimal('100')


# ---------------------------------------------------------------------------
class TestCascadeRollup:
    def test_mark_task_done_cascades(self, project):
        m = Milestone.objects.create(project=project, title="M")
        t = Task.objects.create(milestone=m, title="T1", status=TaskStatus.TODO)
        m.refresh_from_db(); project.refresh_from_db()
        assert m.progress_pct == Decimal('0')
        assert project.progress_pct == Decimal('0')
        from projects.services import mark_task_done
        mark_task_done(t)
        m.refresh_from_db(); project.refresh_from_db()
        assert m.progress_pct == Decimal('100')
        assert project.progress_pct == Decimal('100')


class TestSoftDelete:
    def test_soft_deleted_task_excluded_from_rollup(self, project):
        m = Milestone.objects.create(project=project, title="M")
        t1 = Task.objects.create(milestone=m, title="T1", status=TaskStatus.DONE)
        t2 = Task.objects.create(milestone=m, title="T2", status=TaskStatus.TODO)
        m.refresh_from_db(); assert m.progress_pct == Decimal('50.00')
        t1.soft_delete()
        m.refresh_from_db(); assert m.progress_pct == Decimal('0.00')