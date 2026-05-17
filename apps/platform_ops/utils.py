from __future__ import annotations


def format_bytes(num: int | float) -> str:
    n = float(num or 0)
    if n < 1024:
        return f'{int(n)} B'
    for unit in ('KB', 'MB', 'GB', 'TB'):
        n /= 1024
        if n < 1024:
            return f'{n:.1f} {unit}'
    return f'{n:.1f} PB'
