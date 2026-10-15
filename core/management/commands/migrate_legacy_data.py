"""
Migrate dev data from the pre-Phase-2 SQLite backup into the current schema.

Background
----------
Phase 2 replaced the built-in auth User with a custom ``userapp.User`` and
renamed ``Userinfo`` -> ``Profile``. Because AUTH_USER_MODEL changed, the old
migration history could not be replayed, so migrations were squashed. This
command carries the real rows across from a backup file taken before the
switch (``backup-before-backend-*.sqlite3``).

What it copies (idempotent — skips rows that already exist):
    auth_user            -> userapp.User      (password hashes preserved, so
                                               existing logins keep working)
    userapp_userinfo     -> userapp.Profile
    dashboardapp_service -> dashboardapp.Service
    myapp_messages       -> myapp.Inquiry
    core_siteconfiguration -> core.SiteConfiguration

Usage:
    python manage.py migrate_legacy_data                       # default backup
    python manage.py migrate_legacy_data --source /path/to.db  # explicit
    python manage.py migrate_legacy_data --dry-run             # report only

Media files are NOT touched — they live in ./media and keep the same paths,
so image references in the copied rows resolve unchanged.
"""

import os
import sqlite3
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

User = get_user_model()

# The newest backup in BASE_DIR, unless --source overrides it.
DEFAULT_GLOB = "backup-before-backend-*.sqlite3"


class Command(BaseCommand):
    help = "Copy users/profiles/services/messages/site-config from a legacy SQLite backup."

    def add_arguments(self, parser):
        parser.add_argument(
            "--source",
            help=f"Path to the legacy SQLite file (default: newest {DEFAULT_GLOB} in BASE_DIR).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report what would be copied without writing anything.",
        )

    def handle(self, *args, **options):
        source = self._resolve_source(options.get("source"))
        dry = options["dry_run"]

        self.stdout.write(f"Source: {source}" + ("  (dry run)" if dry else ""))
        conn = sqlite3.connect(f"file:{source}?mode=ro", uri=True)  # read-only
        conn.row_factory = sqlite3.Row
        try:
            counts = {
                "users": self._migrate_users(conn, dry),
                "profiles": self._migrate_profiles(conn, dry),
                "services": self._migrate_services(conn, dry),
                "messages": self._migrate_messages(conn, dry),
                "site_config": self._migrate_site_config(conn, dry),
            }
        finally:
            conn.close()

        verb = "Would copy" if dry else "Copied"
        self.stdout.write("")
        for k, v in counts.items():
            self.stdout.write(f"  {verb} {k:13} {v}")
        if dry:
            self.stdout.write(self.style.NOTICE("\nDry run — nothing written."))
        else:
            self.stdout.write(self.style.SUCCESS("\nDone."))

    # ------------------------------------------------------------------
    def _resolve_source(self, explicit):
        if explicit:
            p = Path(explicit).expanduser().resolve()
            if not p.exists():
                raise CommandError(f"Source not found: {p}")
            return p
        candidates = sorted(Path(settings.BASE_DIR).glob(DEFAULT_GLOB))
        if not candidates:
            raise CommandError(
                f"No backup matching {DEFAULT_GLOB} in {settings.BASE_DIR}. "
                "Pass --source explicitly."
            )
        # Filenames carry a date suffix; the lexicographically last is newest.
        return candidates[-1].resolve()

    def _table_exists(self, conn, name):
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (name,)
        ).fetchone()
        return row is not None

    # ------------------------------------------------------------------
    def _migrate_users(self, conn, dry):
        if not self._table_exists(conn, "auth_user"):
            self.stdout.write(self.style.WARNING("  auth_user table missing; skipping users"))
            return 0
        rows = conn.execute(
            "SELECT id, password, last_login, is_superuser, username, first_name,"
            " last_name, is_staff, is_active, date_joined, email FROM auth_user"
        ).fetchall()
        copied = 0
        for r in rows:
            if User.objects.filter(pk=r["id"]).exists():
                continue
            if not dry:
                User.objects.create(
                    id=r["id"],
                    password=r["password"],  # portable hash string — login still works
                    last_login=r["last_login"],
                    is_superuser=bool(r["is_superuser"]),
                    username=r["username"],
                    first_name=r["first_name"] or "",
                    last_name=r["last_name"] or "",
                    is_staff=bool(r["is_staff"]),
                    is_active=bool(r["is_active"]),
                    date_joined=r["date_joined"],
                    email=r["email"] or "",
                )
            copied += 1
        return copied

    def _migrate_profiles(self, conn, dry):
        if not self._table_exists(conn, "userapp_userinfo"):
            return 0
        from userapp.models import Profile

        rows = conn.execute(
            "SELECT user_id, phone, secondary_email, present_address,"
            " permanent_address, profile_picture, cover_photo FROM userapp_userinfo"
        ).fetchall()
        copied = 0
        for r in rows:
            if Profile.objects.filter(user_id=r["user_id"]).exists():
                continue
            if dry:
                copied += 1
                continue
            # Target user must exist (created above).
            if not User.objects.filter(pk=r["user_id"]).exists():
                continue
            Profile.objects.create(
                user_id=r["user_id"],
                phone=r["phone"] or None,
                secondary_email=r["secondary_email"] or None,
                present_address=r["present_address"] or None,
                permanent_address=r["permanent_address"] or None,
                profile_picture=r["profile_picture"] or None,
                cover_photo=r["cover_photo"] or None,
            )
            copied += 1
        return copied

    def _migrate_services(self, conn, dry):
        if not self._table_exists(conn, "dashboardapp_service"):
            return 0
        from dashboardapp.models import Service

        rows = conn.execute(
            "SELECT title, description, icon, image, price, is_active FROM dashboardapp_service"
        ).fetchall()
        copied = 0
        for r in rows:
            if Service.objects.filter(title=r["title"]).exists():
                continue
            if not dry:
                Service.objects.create(
                    title=r["title"],
                    description=r["description"] or "",
                    icon=r["icon"],
                    image=r["image"] or None,
                    price=r["price"],
                    is_active=bool(r["is_active"]),
                )
            copied += 1
        return copied

    def _migrate_messages(self, conn, dry):
        """Legacy `myapp_messages` -> Inquiry.

        Phase 3 changed the shape, so the values are translated while copying:
          * service (free text, e.g. "Web") -> service FK (matched by title)
            plus a service_title snapshot. If no active Service matches the
            text, the FK stays NULL but service_title preserves the original.
          * response (bool)              -> status (new <-> replied)
        """
        if not self._table_exists(conn, "myapp_messages"):
            return 0
        from myapp.models import Inquiry
        from dashboardapp.models import Service

        # Build a title -> Service map once (only active ones are selectable,
        # but we match any so legacy text still links if the row exists).
        by_title = {s.title: s for s in Service.objects.all()}

        rows = conn.execute(
            "SELECT name, email, phone, service, note, response, created_at"
            " FROM myapp_messages"
        ).fetchall()
        copied = 0
        for r in rows:
            # No natural unique key; dedupe on (name, email, created_at).
            if Inquiry.objects.filter(
                name=r["name"], email=r["email"], created_at=r["created_at"]
            ).exists():
                continue

            service_text = (r["service"] or "").strip()
            service_obj = by_title.get(service_text)
            status = (
                Inquiry.Status.REPLIED
                if r["response"]
                else Inquiry.Status.NEW
            )

            if not dry:
                obj = Inquiry(
                    name=r["name"],
                    email=r["email"] or "",
                    phone=r["phone"] or None,
                    service=service_obj,
                    service_title=service_text,
                    note=r["note"] or None,
                    status=status,
                )
                obj.save()
                # Preserve the original timestamp (created_at is auto_now_add,
                # so force it back with an explicit UPDATE) and stamp
                # responded_at for inquiries that were already answered.
                Inquiry.objects.filter(pk=obj.pk).update(
                    created_at=r["created_at"],
                    **(
                        {"responded_at": r["created_at"]}
                        if status == Inquiry.Status.REPLIED
                        else {}
                    ),
                )
            copied += 1
        return copied

    def _migrate_site_config(self, conn, dry):
        if not self._table_exists(conn, "core_siteconfiguration"):
            return 0
        from core.models import SiteConfiguration

        if SiteConfiguration.objects.exists():
            return 0
        row = conn.execute("SELECT * FROM core_siteconfiguration LIMIT 1").fetchone()
        if not row:
            return 0
        if not dry:
            keys = row.keys()
            kwargs = {k: row[k] for k in keys}
            SiteConfiguration.objects.create(**kwargs)
        return 1
