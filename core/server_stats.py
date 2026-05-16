"""Lightweight server health metrics via psutil. Falls back to safe defaults."""
from __future__ import annotations

_CACHE_KEY = 'sdpaas:server_stats'
_CACHE_TTL = 10  # seconds — fresh enough for dashboards, avoids per-request psutil calls


def get_server_stats() -> dict:
    try:
        from django.core.cache import cache
        cached = cache.get(_CACHE_KEY)
        if cached is not None:
            return cached
    except Exception:
        pass

    try:
        import psutil

        cpu_pct = psutil.cpu_percent(interval=0.2)
        vm = psutil.virtual_memory()
        ram_pct = vm.percent
        ram_used_gb = round(vm.used / 1024 ** 3, 1)
        ram_total_gb = round(vm.total / 1024 ** 3, 1)

        disk = psutil.disk_usage('/')
        disk_pct = disk.percent
        disk_used_gb = round(disk.used / 1024 ** 3, 1)
        disk_total_gb = round(disk.total / 1024 ** 3, 1)

        load1, load5, load15 = psutil.getloadavg()
        cpu_count = psutil.cpu_count(logical=True) or 1

        net = psutil.net_io_counters()
        net_sent_mb = round(net.bytes_sent / 1024 ** 2, 1)
        net_recv_mb = round(net.bytes_recv / 1024 ** 2, 1)

        boot = psutil.boot_time()
        import time
        uptime_hours = round((time.time() - boot) / 3600, 1)

    except Exception:
        cpu_pct = ram_pct = disk_pct = 0.0
        ram_used_gb = ram_total_gb = disk_used_gb = disk_total_gb = 0.0
        load1 = load5 = load15 = 0.0
        cpu_count = 1
        net_sent_mb = net_recv_mb = 0.0
        uptime_hours = 0.0

    def _status(pct: float) -> str:
        if pct >= 90:
            return 'critical'
        if pct >= 70:
            return 'warning'
        return 'ok'

    result = {
        'cpu_pct': round(cpu_pct, 1),
        'cpu_status': _status(cpu_pct),
        'ram_pct': round(ram_pct, 1),
        'ram_used_gb': ram_used_gb,
        'ram_total_gb': ram_total_gb,
        'ram_status': _status(ram_pct),
        'disk_pct': round(disk_pct, 1),
        'disk_used_gb': disk_used_gb,
        'disk_total_gb': disk_total_gb,
        'disk_status': _status(disk_pct),
        'load1': round(load1, 2),
        'load5': round(load5, 2),
        'load15': round(load15, 2),
        'cpu_count': cpu_count,
        'load_status': _status(min((load1 / cpu_count) * 100, 100)),
        'net_sent_mb': net_sent_mb,
        'net_recv_mb': net_recv_mb,
        'uptime_hours': uptime_hours,
    }

    try:
        from django.core.cache import cache
        cache.set(_CACHE_KEY, result, _CACHE_TTL)
    except Exception:
        pass

    return result
