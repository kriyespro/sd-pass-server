import logging
import re
import zipfile
from pathlib import Path

from django.conf import settings

from apps.security.models import ScanStatus

logger = logging.getLogger(__name__)

# ── Dangerous patterns per file type ─────────────────────────────────────────

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

# Patterns that are dangerous in ANY file type (Docker escape attempts)
UNIVERSAL_BLOCK = (
    r'/var/run/docker\.sock',
    r'--privileged',
)

# Python-specific: block Docker socket access and obvious shell-injection tricks
PYTHON_DANGER_PATTERNS = (
    r'/var/run/docker\.sock',
    r'--privileged',
    r'subprocess\.[a-zA-Z_]+\([^)]*shell\s*=\s*True',   # subprocess(..., shell=True)
    r'os\.system\s*\(',                                   # os.system(...)
    r'os\.popen\s*\(',                                    # os.popen(...)
)

# ── File classification ───────────────────────────────────────────────────────

# Binary extensions: skip text scanning entirely (can't contain PHP/Python patterns).
# SQLite / images / fonts are pure binary — reading them as text is pointless.
BINARY_EXTENSIONS = frozenset({
    '.sqlite', '.db', '.sqlite3',
    '.png', '.jpg', '.jpeg', '.gif', '.webp', '.ico', '.bmp', '.tiff',
    '.svg',   # treated as text but harmless without PHP/Dockerfile content
    '.woff', '.woff2', '.ttf', '.eot', '.otf',
    '.pdf', '.zip', '.tar', '.gz',
    '.mp3', '.mp4', '.ogg', '.wav',
    '.pyc', '.pyo',
})

# Max bytes to read per TEXT member for pattern scanning
MAX_TEXT_SCAN_BYTES = 4 * 1024 * 1024    # 4 MB — generous for minified JS etc.

# Max bytes for any single binary member (images, SQLite) — generous limit
MAX_BINARY_BYTES = 50 * 1024 * 1024      # 50 MB

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
    Scan a student ZIP upload:
    - ClamAV (if configured)
    - PHP heuristic patterns on .php files
    - Dockerfile privilege-escalation patterns
    - Python: subprocess shell=True, os.system, Docker socket
    - Universal: Docker socket path in any file

    Binary files (images, SQLite, fonts) are size-checked but NOT read for patterns.
    Text files are read up to MAX_TEXT_SCAN_BYTES for pattern matching.
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

    # ── Optional ClamAV ──────────────────────────────────────────────────────
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

    # ── ZIP member scanning ───────────────────────────────────────────────────
    with zipfile.ZipFile(zip_path, 'r') as zf:
        members = [m for m in zf.infolist() if not m.is_dir()]

        if len(members) > MAX_ZIP_MEMBERS:
            issues.append(f'zip:too_many_files:{len(members)}')

        for member in members[:MAX_ZIP_MEMBERS]:
            name = member.filename
            if not _member_path_safe(name):
                issues.append(f'zip:unsafe_path:{name}')
                continue

            lower = name.lower()
            ext = Path(lower).suffix

            is_binary = ext in BINARY_EXTENSIONS

            # Size check — binary files get a larger budget, text files smaller
            max_size = MAX_BINARY_BYTES if is_binary else MAX_TEXT_SCAN_BYTES
            if member.file_size > max_size:
                limit_mb = max_size // (1024 * 1024)
                issues.append(f'zip:file_too_large:{name}:{member.file_size // (1024*1024)}MB_exceeds_{limit_mb}MB')
                continue

            # Binary files: skip text pattern scanning entirely
            if is_binary:
                continue

            # Read text content for pattern scanning
            try:
                raw = zf.read(member)
            except (RuntimeError, zipfile.BadZipFile, OSError) as exc:
                issues.append(f'zip:read_error:{name}:{exc}')
                continue
            text = raw.decode('utf-8', errors='ignore')

            # PHP patterns
            if lower.endswith('.php'):
                for pat in PHP_DANGER_PATTERNS:
                    if re.search(pat, text, flags=re.IGNORECASE):
                        issues.append(f'php_pattern:{name}')
                        break

            # Dockerfile privilege patterns
            base = name.rsplit('/', 1)[-1]
            if lower.endswith('dockerfile') or base.lower().startswith('dockerfile'):
                for pat in DOCKERFILE_BLOCK:
                    if re.search(pat, text, flags=re.IGNORECASE):
                        issues.append(f'dockerfile_block:{name}')
                        break

            # Python dangerous patterns
            if lower.endswith('.py') or lower.endswith('.pyw'):
                for pat in PYTHON_DANGER_PATTERNS:
                    if re.search(pat, text, flags=re.IGNORECASE):
                        issues.append(f'python_danger:{name}:{pat[:40]}')
                        break

            # Universal: Docker socket in any file type
            for pat in UNIVERSAL_BLOCK:
                if re.search(pat, text, flags=re.IGNORECASE):
                    issues.append(f'universal_block:{name}:{pat}')
                    break

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
