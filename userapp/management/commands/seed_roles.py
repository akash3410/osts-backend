"""
Create (or update) the three application roles as Django Groups.

Usage:
    python manage.py seed_roles          # create/update the role Groups

Roles are Groups so they integrate with the Django admin and the permission
matrix. Custom per-model permissions are attached to the 'owner' Group, which
is the privileged operations role. Idempotent — safe to run repeatedly.
"""

from django.contrib.auth.models import Group, Permission
from django.core.management.base import BaseCommand

# Permissions an Owner can exercise that a plain staff/employee should not.
# These map to the Meta.permissions declared on the business models.
OWNER_PERMISSION_CODENAMES = [
    "approve_proposal",
    "record_payment",
    "manage_users",
    "manage_content",
]

ROLE_DESCRIPTIONS = {
    "client": "Registered customer who can view their own projects and invoices.",
    "employee": "Internal staff assigned to projects and tasks.",
    "owner": "Administrator with full operational control.",
}


class Command(BaseCommand):
    help = "Create/update the client, employee, and owner Groups (roles)."

    def handle(self, *args, **options):
        for role, desc in ROLE_DESCRIPTIONS.items():
            group, created = Group.objects.get_or_create(name=role)
            action = "Created" if created else "Exists "
            self.stdout.write(f"  {action} role group: {role:9} — {desc}")

        self._attach_owner_permissions()
        self.stdout.write(self.style.SUCCESS("\nRoles ready."))

    def _attach_owner_permissions(self):
        """Grant the owner Group every custom 'core'/'billing'-style permission
        we've defined. Missing codenames are skipped gracefully so this command
        doesn't break before those apps exist."""
        owner = Group.objects.get(name="owner")
        added = 0
        for codename in OWNER_PERMISSION_CODENAMES:
            perm = Permission.objects.filter(codename=codename).first()
            if perm and not owner.permissions.filter(pk=perm.pk).exists():
                owner.permissions.add(perm)
                added += 1
        if added:
            self.stdout.write(f"  Attached {added} permission(s) to 'owner'.")
        else:
            self.stdout.write(
                "  (no custom permissions defined yet — owner keeps default access)"
            )
