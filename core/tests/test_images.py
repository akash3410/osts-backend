"""Tests for the self-hosted image optimization pipeline (Phase 3)."""
import os
import shutil
import tempfile
from io import BytesIO

import pytest
from django.conf import settings
from PIL import Image
from PIL import ImageOps

from core.utils.images import (
    image_dimensions_for,
    optimize_image_file,
    optimize_image_field,
)


# ---------------------------------------------------------------------------
class TestDimensionsFor:
    def test_tuple_three(self):
        assert image_dimensions_for((1600, 1200, 400)) == (1600, 1200, 400)

    def test_tuple_two_defaults_height(self):
        # no thumb (None) when not provided
        assert image_dimensions_for((800, 600)) == (800, 600, None)

    def test_single_int(self):
        assert image_dimensions_for(400) == (400, 400, 400)

    def test_invalid_spec(self):
        with pytest.raises(ValueError):
            image_dimensions_for("nope")


# ---------------------------------------------------------------------------
class TestOptimizeImageFile:
    @pytest.fixture
    def src(self, tmp_path):
        # Big landscape JPEG. (Pillow always writes one when asked.)
        img = Image.new('RGB', (4000, 3000), (10, 60, 100))
        buf = BytesIO()
        img.save(buf, 'JPEG', quality=90)
        p = tmp_path / 'source.jpg'
        p.write_bytes(buf.getvalue())
        return p

    def test_converts_to_webp(self, src, tmp_path):
        webp_name, thumb_name = optimize_image_file(
            str(src), max_width=1600, max_height=1200, thumb_size=400,
        )
        assert webp_name.endswith('.webp'), webp_name
        assert webp_name == 'source.webp'

    def test_resizes_to_bounds(self, src, tmp_path):
        optimize_image_file(
            str(src), max_width=1600, max_height=1200, thumb_size=400,
        )
        out = tmp_path / 'source.webp'
        assert out.exists()
        with Image.open(out) as im:
            assert max(im.width, im.height) <= 1600
            assert im.width <= 1600 and im.height <= 1200

    def test_strips_exif(self, src, tmp_path):
        optimize_image_file(str(src), max_width=1600, max_height=1200)
        with Image.open(tmp_path / 'source.webp') as im:
            assert im.info.get('exif') is None

    def test_creates_thumbnail_sidecar(self, src, tmp_path):
        webp_name, thumb_name = optimize_image_file(
            str(src), max_width=1600, max_height=1200, thumb_size=400,
        )
        assert thumb_name is not None
        assert (tmp_path / thumb_name).exists()
        with Image.open(tmp_path / thumb_name) as im:
            assert max(im.width, im.height) <= 400

    def test_source_file_removed(self, src, tmp_path):
        optimize_image_file(str(src), max_width=1600, max_height=1200)
        assert not src.exists()

    def test_idempotent_does_not_grow(self, src, tmp_path):
        name1, _ = optimize_image_file(str(src), max_width=1600, max_height=1200)
        size1 = (tmp_path / name1).stat().st_size
        # Re-running on the same file should be a no-op (file is already there).
        # Call on the result path directly.
        webp2, thumb2 = optimize_image_file(
            str(tmp_path / name1), max_width=1600, max_height=1200,
        )
        assert webp2 == name1
        size2 = (tmp_path / name1).stat().st_size
        assert size1 == size2  # no further change

    def test_no_thumb_when_size_small(self, tmp_path):
        img = Image.new('RGB', (200, 150), (255, 0, 0))
        p = tmp_path / 'tiny.png'
        img.save(p, 'PNG')
        _, thumb = optimize_image_file(str(p), max_width=1600, max_height=1200, thumb_size=400)
        assert thumb is None

    def test_missing_file_returns_none(self, tmp_path):
        assert optimize_image_file(str(tmp_path / 'nope.jpg'), max_width=100, max_height=100) == (None, None)


# ---------------------------------------------------------------------------
class TestMixinGeneral:
    """Sanity: Service declares specs and uses the mixin."""

    def test_service_has_specs(self):
        from dashboardapp.models import Service
        specs = getattr(Service, 'IMAGE_SPECS', None)
        assert isinstance(specs, dict)
        assert 'image' in specs

    def test_profile_has_specs(self):
        from userapp.models import Profile
        specs = getattr(Profile, 'IMAGE_SPECS', None)
        assert isinstance(specs, dict)
        assert 'profile_picture' in specs and 'cover_photo' in specs