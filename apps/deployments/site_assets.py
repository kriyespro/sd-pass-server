"""
Minify CSS/JS and optimize images under a student static site directory.
"""
from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_CSS_SUFFIXES = {'.css'}
_JS_SUFFIXES = {'.js', '.mjs'}
_IMAGE_SUFFIXES = {'.jpg', '.jpeg', '.png', '.webp'}
_SKIP_MINIFIED_MARKERS = ('.min.css', '.min.js', '.min.mjs')


def _empty_stats() -> dict:
    return {
        'css_files': 0,
        'js_files': 0,
        'image_files': 0,
        'files_found': 0,
        'files_optimized': 0,
        'bytes_before': 0,
        'bytes_after': 0,
        'bytes_saved': 0,
        'kb_saved': 0.0,
    }


def _should_skip_minify(path: Path) -> bool:
    lower = path.name.lower()
    return any(marker in lower for marker in _SKIP_MINIFIED_MARKERS)


def _minify_text_file(path: Path, *, minifier) -> tuple[int, int]:
    try:
        original = path.read_text(encoding='utf-8')
    except (OSError, UnicodeDecodeError):
        return 0, 0
    try:
        compressed = minifier(original)
    except Exception as exc:
        logger.debug('site_assets: minify skipped %s — %s', path, exc)
        return 0, 0
    if not compressed or len(compressed) >= len(original):
        return len(original.encode('utf-8')), len(original.encode('utf-8'))
    path.write_text(compressed, encoding='utf-8')
    return len(original.encode('utf-8')), len(compressed.encode('utf-8'))


def _minify_css(path: Path) -> tuple[int, int]:
    import rcssmin

    return _minify_text_file(path, minifier=rcssmin.cssmin)


def _minify_js(path: Path) -> tuple[int, int]:
    import rjsmin

    return _minify_text_file(path, minifier=rjsmin.jsmin)


def _optimize_image(path: Path) -> tuple[int, int]:
    from apps.deployments.image_optimizer import _optimize_image as _opt_img

    return _opt_img(path)


def optimize_site_assets(site_dir: Path) -> dict:
    """Walk site_dir and minify CSS/JS + optimize images in place."""
    if not site_dir.is_dir():
        return _empty_stats()

    stats = _empty_stats()

    for path in site_dir.rglob('*'):
        if not path.is_file():
            continue
        suffix = path.suffix.lower()
        if suffix not in _CSS_SUFFIXES | _JS_SUFFIXES | _IMAGE_SUFFIXES:
            continue
        if _should_skip_minify(path):
            continue

        stats['files_found'] += 1
        if suffix in _CSS_SUFFIXES:
            stats['css_files'] += 1
            before, after = _minify_css(path)
        elif suffix in _JS_SUFFIXES:
            stats['js_files'] += 1
            before, after = _minify_js(path)
        else:
            stats['image_files'] += 1
            before, after = _optimize_image(path)

        if before <= 0:
            continue
        stats['bytes_before'] += before
        stats['bytes_after'] += after
        if after < before:
            stats['files_optimized'] += 1
            stats['bytes_saved'] += before - after

    stats['kb_saved'] = round(stats['bytes_saved'] / 1024, 1)
    return stats


def optimize_site_images(site_dir: Path) -> dict:
    """Backward-compatible image-only optimizer."""
    from apps.deployments.image_optimizer import optimize_site_images as _legacy

    return _legacy(site_dir)
