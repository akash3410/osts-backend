"""Self-hosted image optimization pipeline (Pillow).

Pipelines every uploaded image through:
  * EXIF orientation normalization (and EXIF strip) — no private metadata in
    the served file.
  * Resize to a configurable bounding box (aspect preserved) — no 25MP uploads
    served at 4K resolution.
  * Conversion to WebP at quality 85 — typically 5-10x smaller than JPEG.
  * A ``_thumb.webp`` sidecar for list/card views.

Dependency-free beyond Pillow (already required). No external image service.
"""

import os
from io import BytesIO

from django.core.files.storage import default_storage
from PIL import Image, ImageOps, UnidentifiedImageError


IMAGE_EXTENSIONS = ('.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.tif', '.webp')


def image_dimensions_for(spec):
    """Normalize a spec into (max_w, max_h, thumb_size)."""
    if isinstance(spec, tuple):
        max_w = spec[0]
        max_h = spec[1] if len(spec) > 1 else spec[0]
        thumb = spec[2] if len(spec) > 2 else None
    elif isinstance(spec, int):
        max_w = max_h = thumb = spec
    else:
        raise ValueError(f'Invalid image spec: {spec!r}')
    return int(max_w), int(max_h), (int(thumb) if thumb else None)


def optimize_image_file(src_path, *, max_width, max_height, thumb_size=None, quality=85):
    """Optimize a single image file on disk.

    Returns (new_filename, thumb_filename) — basenames only. ``new_filename``
    is the WebP that replaces the source (the source is removed when it differs
    from the new name). ``thumb_filename`` is the sidecar or None.

    Idempotent: an already-served optimal WebP under the size limits is
    left untouched. EXIF Orientation is normalized and then stripped on save.
    """
    if not os.path.exists(src_path):
        return None, None

    with Image.open(src_path) as im:
        # EXIF normalize: rotates per the Orientation tag and returns an image
        # with no Orientation/EXIF block — no metadata in the served file.
        im = ImageOps.exif_transpose(im)

        # WebP supports RGB + RGBA. Anything exotic becomes RGB.
        if im.mode in ('P', 'LA'):
            im = im.convert('RGBA')
        elif im.mode not in ('RGB', 'RGBA'):
            im = im.convert('RGB')

        needs_resize = im.width > max_width or im.height > max_height
        if needs_resize:
            im.thumbnail((max_width, max_height), Image.LANCZOS)

        directory = os.path.dirname(src_path)
        stem = os.path.splitext(os.path.basename(src_path))[0]
        webp_path = os.path.join(directory, f'{stem}.webp')

        # Skip the write only when the source is already an optimally-sized
        # WebP at the identical path.
        already_optimal = (
            src_path.lower().endswith('.webp')
            and os.path.realpath(src_path) == os.path.realpath(webp_path)
            and not needs_resize
            and os.path.exists(src_path)
        )
        if not already_optimal:
            im.save(webp_path, 'WEBP', quality=quality, method=6)

        # Remove the source if it differs (e.g. .jpg -> .webp). Keep the WebP
        # path in case im.save wrote in place.
        if (os.path.realpath(src_path) != os.path.realpath(webp_path)
                and os.path.exists(src_path)):
            os.remove(src_path)

        thumb_path = None
        if thumb_size and max(im.width, im.height) > thumb_size:
            thumb = ImageOps.exif_transpose(Image.open(webp_path))
            thumb.thumbnail((thumb_size, thumb_size), Image.LANCZOS)
            if thumb.mode not in ('RGB', 'RGBA'):
                thumb = thumb.convert('RGB')
            thumb_path = os.path.join(directory, f'{stem}_thumb.webp')
            thumb.save(thumb_path, 'WEBP', quality=75, method=4)
            thumb.close()

        # im goes out of scope; close handled by context manager.
    return os.path.basename(webp_path), (os.path.basename(thumb_path) if thumb_path else None)


def optimize_image_field(instance, field_name, max_width, max_height, thumb_size=None):
    """Optimize a Django ImageField *in place* after super().save().

    Updates the instance field to the new WebP path and re-saves (guarded by
    the mixin). Returns True if a file was produced.
    """
    field = getattr(instance, field_name)
    if not field:
        return False
    if not hasattr(field, 'path') or not field.path:
        return False  # remote storage or not on disk yet
    if not os.path.exists(field.path):
        return False

    webp_name, thumb_name = optimize_image_file(
        field.path,
        max_width=max_width, max_height=max_height, thumb_size=thumb_size,
    )
    if webp_name is None:
        return False

    # Preserve any subdirectory prefix the field carried (e.g. 'services/foo.jpg'
    # -> 'services/foo.webp').
    directory = os.path.dirname(field.name)
    new_name = webp_name if not directory else f'{directory.replace(chr(92), "/")}/{webp_name}'
    new_name = new_name.replace('\\', '/')

    changed = False
    if new_name and new_name != field.name:
        field.name = new_name
        changed = True
    if thumb_name:
        setattr(instance, f'{field_name}_thumb_name', thumb_name)
        changed = True
    return changed