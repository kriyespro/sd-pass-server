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
import os
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)

_IMAGE_SUFFIXES = {'.jpg', '.jpeg', '.png', '.webp'}


def _optimize_image(path: Path) -> tuple[int, int]:
    """
    Optimize one image file in-place via a temp file so a mid-write failure
    never corrupts the original.
    Returns (original_bytes, new_bytes). Returns (0, 0) on failure/skip.
    """
    try:
        from PIL import Image, UnidentifiedImageError
    except ImportError:
        return 0, 0

    orig_size = path.stat().st_size
    suffix = path.suffix.lower()
    tmp_path = None

    try:
        with Image.open(path) as img:
            if suffix in ('.jpg', '.jpeg'):
                if img.mode in ('RGBA', 'P', 'LA'):
                    img = img.convert('RGB')
                save_kwargs: dict = {'format': 'JPEG', 'quality': 85, 'optimize': True, 'progressive': True}
            elif suffix == '.png':
                save_kwargs = {'format': 'PNG', 'optimize': True}
            elif suffix == '.webp':
                save_kwargs = {'format': 'WEBP', 'lossless': True, 'method': 6, 'quality': 85}
            else:
                return 0, 0

            fd, tmp_name = tempfile.mkstemp(dir=path.parent, suffix=suffix)
            os.close(fd)
            tmp_path = Path(tmp_name)
            img.save(tmp_path, **save_kwargs)

        new_size = tmp_path.stat().st_size
        if new_size >= orig_size:
            # New file is not smaller — keep original untouched.
            tmp_path.unlink(missing_ok=True)
            tmp_path = None
            return orig_size, orig_size
        tmp_path.replace(path)  # atomic rename — original never half-written
        tmp_path = None
        return orig_size, new_size

    except (UnidentifiedImageError, OSError, Exception) as exc:
        logger.debug('image_optimizer: skipped %s — %s', path.name, exc)
        return 0, 0
    finally:
        if tmp_path is not None:
            try:
                tmp_path.unlink()
            except OSError:
                pass


def _ultra_compress_image(path: Path) -> tuple[int, int]:
    """
    Second-pass aggressive lossy compression.
    JPEG → quality=55, PNG → quantize to 256 colours then save, WebP → lossy quality=45.
    Returns (original_bytes, new_bytes). Returns (0, 0) on failure/skip.
    """
    try:
        from PIL import Image, UnidentifiedImageError
    except ImportError:
        return 0, 0

    orig_size = path.stat().st_size
    suffix = path.suffix.lower()
    tmp_path = None

    try:
        with Image.open(path) as img:
            if suffix in ('.jpg', '.jpeg'):
                if img.mode in ('RGBA', 'P', 'LA'):
                    img = img.convert('RGB')
                save_kwargs: dict = {'format': 'JPEG', 'quality': 55, 'optimize': True, 'progressive': True}
            elif suffix == '.png':
                # Quantize to 256-colour palette for lossy-like PNG shrink.
                # Keep as 'P' mode — converting back to RGBA would undo the size saving.
                if img.mode not in ('P',):
                    img = img.quantize(colors=256, method=Image.Quantize.MEDIANCUT)
                save_kwargs = {'format': 'PNG', 'optimize': True}
            elif suffix == '.webp':
                save_kwargs = {'format': 'WEBP', 'lossless': False, 'method': 6, 'quality': 45}
            else:
                return 0, 0

            fd, tmp_name = tempfile.mkstemp(dir=path.parent, suffix=suffix)
            os.close(fd)
            tmp_path = Path(tmp_name)
            img.save(tmp_path, **save_kwargs)

        new_size = tmp_path.stat().st_size
        if new_size >= orig_size:
            # ultra result is larger — keep original
            tmp_path.unlink(missing_ok=True)
            tmp_path = None
            return orig_size, orig_size
        tmp_path.replace(path)
        tmp_path = None
        return orig_size, new_size

    except (UnidentifiedImageError, OSError, Exception) as exc:
        logger.debug('image_optimizer ultra: skipped %s — %s', path.name, exc)
        return 0, 0
    finally:
        if tmp_path is not None:
            try:
                tmp_path.unlink()
            except OSError:
                pass


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


def ultra_compress_site_images(site_dir: Path) -> dict:
    """
    Second aggressive pass over all images in *site_dir*.
    Calls _ultra_compress_image on each supported file.
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
        orig, new = _ultra_compress_image(img_path)
        if orig > 0 and new < orig:
            files_optimized += 1
            bytes_saved += orig - new
            logger.debug(
                'image_optimizer ultra: %s %d → %d bytes (-%d%%)',
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
