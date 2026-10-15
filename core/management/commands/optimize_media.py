"""Backfill existing media through the Pillow optimization pipeline."""

import os

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import models

from core.utils.images import optimize_image_file

FOLDER_SPECS = [
    ('services', 1920, 1440, 480),
    ('document', 1200, 1200, 320),
    ('about', 1200, 800, 480),
    ('logos', 512, 512, 128),
    ('sitebg', 1920, 1080, 480),
]


def spec_for(rel_path):
    head = (rel_path.split('/')[0] or rel_path.split(os.sep)[0])
    for seg, mw, mh, ts in FOLDER_SPECS:
        if seg == head:
            return mw, mh, ts
    return 1920, 1440, 480


class Command(BaseCommand):
    help = 'Backfill existing media through the Pillow optimization pipeline.'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help='Report, change nothing.')
        parser.add_argument('--path', help='Restrict to a subdirectory of MEDIA_ROOT.')

    def handle(self, *args, **options):
        root = os.path.realpath(settings.MEDIA_ROOT)
        sub = options.get('path')
        base_dir = os.path.realpath(os.path.join(root, sub)) if sub else root
        if not os.path.isdir(base_dir):
            raise CommandError(f'Directory not found: {base_dir}')

        dry = options['dry_run']

        candidates = []
        for dirpath, _dirs, files in os.walk(base_dir):
            for fn in files:
                ext = os.path.splitext(fn)[1].lower()
                if ext not in ('.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.tif', '.webp'):
                    continue
                if fn.endswith('_thumb.webp'):
                    continue
                full = os.path.join(dirpath, fn)
                rel = os.path.relpath(full, root).replace(os.sep, '/')
                candidates.append((full, rel))

        self.stdout.write(f'Found {len(candidates)} candidate images under {base_dir}')
        if dry:
            self.stdout.write('Dry run — nothing changes:')
            for full, rel in candidates:
                mw, mh, ts = spec_for(rel)
                self.stdout.write(f'  {rel}  -> max {mw}x{mh} thumb={ts}')
            return

        rename_map = {}
        converted = 0
        skipped = 0
        freed = 0
        for full, rel in candidates:
            mw, mh, ts = spec_for(rel)
            before = os.path.getsize(full) if os.path.exists(full) else 0
            webp_base, thumb_base = optimize_image_file(full, max_width=mw, max_height=mh, thumb_size=ts)
            if webp_base is None:
                skipped += 1
                continue
            dirname = os.path.dirname(rel)
            new_rel = (dirname + '/' + webp_base) if dirname else webp_base
            new_rel = new_rel.replace('\\', '/').lstrip('/')
            after = os.path.getsize(os.path.join(root, new_rel)) if os.path.exists(os.path.join(root, new_rel)) else before

            if new_rel != rel:
                rename_map[rel] = new_rel
                converted += 1
                freed += max(0, before - after)
            else:
                skipped += 1

        self.stdout.write(f'Converted {converted} -> .webp | skipped {skipped} (already optimal)')
        self.stdout.write(f'Approx. bytes freed by re-encoding: {freed:,}')

        self._rewrite_db(rename_map)
        self.stdout.write(self.style.SUCCESS('Backfill complete.'))

    @staticmethod
    def _rewrite_db(rename_map):
        if not rename_map:
            return
        from django.apps import apps
        total = 0
        for app in apps.get_app_configs():
            for model in app.get_models():
                fields = [f for f in model._meta.get_fields() if isinstance(f, models.ImageField)]
                if not fields:
                    continue
                for f in fields:
                    for old, new in rename_map.items():
                        qs = model.objects.filter(**{f.attname: old})
                        n = qs.count()
                        if n:
                            qs.update(**{f.attname: new})
                            total += n
                            print(f'  Updated {app.label}.{model.__name__}.{f.attname}: {old} -> {new} ({n})')
        print(f'  Total DB field updates: {total}')