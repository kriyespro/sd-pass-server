import logging
import re
import zipfile
from pathlib import Path

from django.conf import settings

from apps.security.models import ScanStatus

logger = logging.getLogger(__name__)

PHP_DANGER_PATTERNS = (
    r'\beval\s*\(',
    r'\bbase64_decode\s*\(',
    r'\bsystem\s*\(',
    r'\bexec\s*\(',
    r'\bshell_exec\s*\(',
    r'\bpassthru\s*\(',
    r'\bproc_open\s*\(',
)

DOCKERFILE_BLOCK = (
    r'--privileged',
    r'network_mode\s*:\s*host',
    r'--network\s*=\s*host',
    r'/var/run/docker\.sock',
)

MAX_MEMBER_BYTES = 2 * 1024 * 1024
MAX_ZIP_MEMBERS = 2000


def _member_path_safe(member_name: str) -> bool:
    if not member_name:
        return False
    p = Path(member_name)
    if p.is_absolute():
        return False
    return '..' not in p.parts


def run_security_scan(zip_path: Path) -> dict:
    """
    Inspect a ZIP on disk: optional ClamAV, PHP heuristics, Dockerfile rules.
    Returns dict: status (ScanStatus value), summary, details.
    """
    details: dict = {'checks': []}
    issues: list[str] = []

    if not zip_path.is_file():
        return {
            'status': ScanStatus.REJECTED,
            'summary': 'Upload file missing on disk.',
            'details': details,
        }

    if not zipfile.is_zipfile(zip_path):
        return {
            'status': ScanStatus.REJECTED,
            'summary': 'Not a valid ZIP archive.',
            'details': details,
        }

    socket = getattr(settings, 'CLAMD_UNIX_SOCKET', '') or ''
    if socket:
        try:
            import pyclamd  # type: ignore

            cd = pyclamd.ClamdUnixSocket(socket)
            scan = cd.scan_file(str(zip_path))
            details['checks'].append({'clamav': scan})
            if scan and scan.get(str(zip_path)) and scan[str(zip_path)][0] == 'FOUND':
                issues.append('clamav:virus')
        except Exception as exc:  # noqa: BLE001
            logger.warning('ClamAV scan skipped or failed: %s', exc)
            details['checks'].append({'clamav_error': str(exc)})

    with zipfile.ZipFile(zip_path, 'r') as zf:
        members = [m for m in zf.infolist() if not m.is_dir()]
        if len(members) > MAX_ZIP_MEMBERS:
            issues.append('zip:too_many_files')
        for member in members[:MAX_ZIP_MEMBERS]:
            name = member.filename
            if not _member_path_safe(name):
                issues.append(f'zip:unsafe_path:{name}')
                continue
            if member.file_size > MAX_MEMBER_BYTES:
                issues.append(f'zip:large_member:{name}')
                continue
            lower = name.lower()
            try:
                raw = zf.read(member)
            except (RuntimeError, zipfile.BadZipFile, OSError) as exc:
                issues.append(f'zip:read_error:{name}:{exc}')
                continue
            text = raw.decode('utf-8', errors='ignore')
            if lower.endswith('.php'):
                for pat in PHP_DANGER_PATTERNS:
                    if re.search(pat, text, flags=re.IGNORECASE):
                        issues.append(f'php_pattern:{pat}:{name}')
            base = name.rsplit('/', 1)[-1]
            if lower.endswith('dockerfile') or base.startswith('Dockerfile'):
                for pat in DOCKERFILE_BLOCK:
                    if re.search(pat, text, flags=re.IGNORECASE):
                        issues.append(f'dockerfile_block:{pat}:{name}')

    if issues:
        return {
            'status': ScanStatus.REJECTED,
            'summary': 'Security checks failed.',
            'details': {**details, 'issues': issues},
        }
    return {
        'status': ScanStatus.CLEAN,
        'summary': 'No issues reported by configured scanners.',
        'details': details,
    }
