from __future__ import annotations


def get_redis_cache_stats() -> dict:
    """Redis memory used by Django cache (django-redis)."""
    defaults = {
        'available': False,
        'used_memory_human': '—',
        'used_memory_peak_human': '—',
        'maxmemory_human': '—',
        'keys': 0,
        'hit_rate_pct': None,
    }
    try:
        from django_redis import get_redis_connection

        conn = get_redis_connection('default')
        info = conn.info('memory')
        stats = conn.info('stats')
        hits = int(stats.get('keyspace_hits', 0))
        misses = int(stats.get('keyspace_misses', 0))
        total = hits + misses
        hit_rate = round(hits / total * 100, 1) if total else None
        return {
            'available': True,
            'used_memory_human': info.get('used_memory_human', '—'),
            'used_memory_peak_human': info.get('used_memory_peak_human', '—'),
            'maxmemory_human': info.get('maxmemory_human', 'no limit'),
            'keys': conn.dbsize(),
            'hit_rate_pct': hit_rate,
        }
    except Exception:
        return defaults
