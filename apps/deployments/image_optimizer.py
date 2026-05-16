"""
Lossless / near-lossless image optimization for extracted student static sites.

Supported formats
-----------------
JPEG  — re-saved at quality=85, optimize=True, progressive=True
PNG   — re-saved with optimize=True (lossless via zlib)
WebP  — lossless re-save with method=6
GIF   — left unchanged (animation support is complex)

Returns a summary dict with bytes saved and counts.
"""
from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_IMAGE_SUFFIXES = {'.jpg', '.jpeg', '.png', '.webp'}


def _optimize_image(path: Path) -> tuple[int, int]:
    """
    Optimize one image file in-place.
    Returns (original_bytes, new_bytes). Returns (0, 0) on failure.
    """
    try:
        from PIL import Image, UnidentifiedImageError
    except ImportError:
        return 0, 0

    orig_size = path.stat().st_size
    suffix = path.suffix.lower()

    try:
        with Image.open(path) as img:
            fmt = img.format or suffix.lstrip('.').upper()

            if suffix in ('.jpg', '.jpeg'):
                # Convert RGBA/P → RGB before JPEG save
                if img.mode in ('RGBA', 'P', 'LA'):
                    img = img.convert('RGB')
                img.save(path, format='JPEG', quality=85, optimize=True, progressive=True)

            elif suffix == '.png':
                img.save(path, format='PNG', optimize=True)

            elif suffix == '.webp':
                img.save(path, format='WEBP', lossless=True, method=6, quality=85)

            else:
                return 0, 0

    except (UnidentifiedImageError, OSError, Exception) as exc:
        logger.debug('image_optimizer: skipped %s — %s', path.name, exc)
        return 0, 0

    new_size = path.stat().st_size
    return orig_size, new_size


def optimize_site_images(site_dir: Path) -> dict:
    """
    Walk *site_dir* recursively and optimize all images.
    Returns:
        {
            'files_found': int,
            'files_optimized': int,
            'bytes_saved': int,
            'kb_saved': float,
        }
    """
    if not site_dir.is_dir():
        return {'files_found': 0, 'files_optimized': 0, 'bytes_saved': 0, 'kb_saved': 0.0}

    files_found = 0
    files_optimized = 0
    bytes_saved = 0

    for img_path in site_dir.rglob('*'):
        if img_path.suffix.lower() not in _IMAGE_SUFFIXES:
            continue
        if not img_path.is_file():
            continue

        files_found += 1
        orig, new = _optimize_image(img_path)
        if orig > 0 and new < orig:
            files_optimized += 1
            bytes_saved += orig - new
            logger.debug(
                'image_optimizer: %s %d → %d bytes (-%d%%)',
                img_path.name,
                orig,
                new,
                round((orig - new) / orig * 100),
            )

    return {
        'files_found': files_found,
        'files_optimized': files_optimized,
        'bytes_saved': bytes_saved,
        'kb_saved': round(bytes_saved / 1024, 1),
    }
