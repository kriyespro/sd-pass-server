"""
Fetch a public GitHub repo as a ZIP — the same artifact GitHub's own "Download ZIP"
button produces — so it can be fed into the existing upload/scan/deploy pipeline
unchanged. Only github.com/api.github.com/codeload.github.com are ever contacted,
and only with owner/repo values that passed a strict allowlist regex (no SSRF).
"""
from __future__ import annotations

import re

import requests

# GitHub usernames/repo names: letters, digits, hyphens, underscores, dots.
_SEGMENT = r'[\w.-]+'
_REPO_URL_RE = re.compile(rf'^(?:https?://)?(?:www\.)?github\.com/({_SEGMENT})/({_SEGMENT})/?$')
_SHORTHAND_RE = re.compile(rf'^({_SEGMENT})/({_SEGMENT})$')

DOWNLOAD_TIMEOUT = 30
API_TIMEOUT = 10


def parse_github_repo(value: str) -> tuple[str, str] | None:
    """Accept 'https://github.com/owner/repo', 'github.com/owner/repo', or 'owner/repo'."""
    value = (value or '').strip()
    m = _REPO_URL_RE.match(value) or _SHORTHAND_RE.match(value)
    if not m:
        return None
    owner, repo = m.group(1), m.group(2)
    if repo.endswith('.git'):
        repo = repo[: -len('.git')]
    if not owner or not repo:
        return None
    return owner, repo


def resolve_default_branch(owner: str, repo: str) -> str | None:
    try:
        resp = requests.get(
            f'https://api.github.com/repos/{owner}/{repo}',
            headers={'Accept': 'application/vnd.github+json'},
            timeout=API_TIMEOUT,
        )
    except requests.RequestException:
        return None
    if resp.status_code != 200:
        return None
    return (resp.json() or {}).get('default_branch')


def fetch_github_zipball(owner: str, repo: str, branch: str, max_bytes: int) -> tuple[bool, bytes | str]:
    """Download the repo's zipball for `branch`. Returns (True, bytes) or (False, error_message)."""
    url = f'https://codeload.github.com/{owner}/{repo}/zip/refs/heads/{branch}'
    try:
        resp = requests.get(url, stream=True, timeout=DOWNLOAD_TIMEOUT)
    except requests.RequestException as exc:
        return False, f'Could not reach GitHub: {exc}'

    if resp.status_code == 404:
        return False, (
            f'Repo or branch not found ("{owner}/{repo}" @ "{branch}"). '
            'Only public repos are supported, and the branch must exist.'
        )
    if resp.status_code != 200:
        return False, f'GitHub returned HTTP {resp.status_code}.'

    chunks: list[bytes] = []
    total = 0
    try:
        for chunk in resp.iter_content(chunk_size=256 * 1024):
            total += len(chunk)
            if total > max_bytes:
                return False, f'Repo zipball exceeds {max_bytes // 1024 // 1024} MB limit.'
            chunks.append(chunk)
    finally:
        resp.close()
    return True, b''.join(chunks)
