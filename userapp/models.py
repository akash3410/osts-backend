"""
Identity models.

Three-model split, per the platform design:

    User      = authentication identity only (who logs in)
    Profile   = shared personal info every account has
    Client    = business / billing info   (present only for clients)
    Employee  = HR / role info            (present only for employees)

Roles themselves live in Django Groups (client / employee / owner) so they
integrate with the admin and the permission matrix. A user can hold BOTH a
Client and an Employee row (e.g. a client who also does freelance work) —
this is exactly why they are separate 1:1 models, not nullable columns on one
bloated profile table.
"""

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models
from phonenumber_field.modelfields import PhoneNumberField

from core.models import TimeStampedModel
from core.models import ImageOptimizationMixin


class User(AbstractUser):
    """Custom user model.

    Username remains the login identifier (the auth UI is already built around
    it and every existing account has one). ``email`` is made unique so it can
    serve as a reliable secondary key for allauth social matching and future
    password-reset flows.

    DO NOT add business fields here — that is what Profile / Client / Employee
    are for.
    """

    # NOTE: not `unique=True` — 6 existing accounts have a blank email, and
    # several empty strings would violate a plain unique index. Uniqueness is
    # enforced only when an email is actually present (see the Meta constraint
    # below). This is the standard pattern for migrating mixed legacy data.
    email = models.EmailField(
        blank=True,
        default="",
        help_text="Used for notifications and social-login matching.",
    )

    class Meta:
        verbose_name = "user"
        verbose_name_plural = "users"
        constraints = [
            # Enforce email uniqueness ONLY when an email is present. Blank
            # emails (legacy accounts) are exempt, so multiple '' rows coexist.
            models.UniqueConstraint(
                fields=["email"],
                condition=~models.Q(email=""),
                name="user_email_unique_when_set",
            ),
        ]
        indexes = [
            # Login + lookup paths that filter on email.
            models.Index(fields=["email"], name="user_email_idx"),
        ]

    def __str__(self):
        return self.username

    # ------------------------------------------------------------------
    # Role helpers. Group membership is the single source of truth for role.
    # ------------------------------------------------------------------
    ROLE_CLIENT = "client"
    ROLE_EMPLOYEE = "employee"
    ROLE_OWNER = "owner"
    ROLE_CHOICES = [
        (ROLE_CLIENT, "Client"),
        (ROLE_EMPLOYEE, "Employee"),
        (ROLE_OWNER, "Owner"),
    ]

    def has_role(self, role):
        """True if the user belongs to the named Group."""
        # .exists() is cheap and avoids fetching the whole group set.
        return self.groups.filter(name=role).exists()

    @property
    def is_client(self):
        return self.has_role(self.ROLE_CLIENT)

    @property
    def is_employee(self):
        return self.has_role(self.ROLE_EMPLOYEE)

    @property
    def is_owner(self):
        # Owner == superuser OR member of the 'owner' Group. Superuser is
        # checked first so a freshly-created superuser needs no Group row.
        return self.is_superuser or self.has_role(self.ROLE_OWNER)


class Profile(TimeStampedModel, ImageOptimizationMixin):
    """Shared personal info present for every account."""

    IMAGE_SPECS = {
        "profile_picture": (900, 900, 240),
        "cover_photo": (1920, 720, 480),
    }

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="profile",
    )
    phone = PhoneNumberField(region="BD", null=True, blank=True)
    secondary_email = models.EmailField(null=True, blank=True)
    present_address = models.TextField(max_length=100, null=True, blank=True)
    permanent_address = models.TextField(max_length=100, null=True, blank=True)
    profile_picture = models.ImageField(upload_to="document/", null=True, blank=True)
    cover_photo = models.ImageField(upload_to="document/", null=True, blank=True)
    bio = models.TextField(max_length=500, null=True, blank=True)

    def __str__(self):
        return f"Profile({self.user.username})"


class Client(TimeStampedModel):
    """Business / billing information. Created when a user becomes a client."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="client_profile",
    )
    company_name = models.CharField(max_length=200, blank=True)
    billing_address = models.TextField(max_length=300, blank=True)
    tax_id = models.CharField(max_length=100, blank=True, null=True)
    website = models.URLField(max_length=300, blank=True, null=True)
    currency = models.CharField(max_length=3, default="BDT")

    class Meta:
        verbose_name_plural = "clients"

    def __str__(self):
        return self.company_name or self.user.get_full_name() or self.user.username


class Skill(TimeStampedModel):
    """A technology / capability tag that Employees can be tagged with."""

    name = models.CharField(max_length=100, unique=True)

    class Meta:
        verbose_name_plural = "skills"
        ordering = ["name"]

    def __str__(self):
        return self.name


class Employee(TimeStampedModel):
    """HR / role information. Created when a user becomes an employee."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="employee_profile",
    )
    designation = models.CharField(max_length=120, blank=True)
    skills = models.ManyToManyField(Skill, blank=True, related_name="employees")
    hourly_rate = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    joined_on = models.DateField(null=True, blank=True)
    capacity_hours_week = models.DecimalField(
        max_digits=5, decimal_places=1, default=40,
        help_text="Working hours per week for capacity planning.",
    )

    class Meta:
        verbose_name_plural = "employees"

    def __str__(self):
        return self.user.get_full_name() or self.user.username
