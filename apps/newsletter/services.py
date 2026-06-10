import logging
from typing import Optional

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

_BASE = 'https://api.systeme.io/api'
_TAG_NAME = 'krizn-user'
_tag_id_cache: Optional[int] = None


def _headers() -> dict:
    return {
        'X-API-Key': settings.SYSTEME_IO_API_KEY,
        'Accept': 'application/json',
        'Content-Type': 'application/json',
    }


def _get_or_create_tag() -> int:
    global _tag_id_cache
    if _tag_id_cache:
        return _tag_id_cache

    resp = requests.get(f'{_BASE}/tags', params={'limit': 100}, headers=_headers(), timeout=10)
    resp.raise_for_status()
    for tag in resp.json().get('items', []):
        if tag['name'] == _TAG_NAME:
            _tag_id_cache = tag['id']
            return _tag_id_cache

    resp = requests.post(f'{_BASE}/tags', json={'name': _TAG_NAME}, headers=_headers(), timeout=10)
    resp.raise_for_status()
    _tag_id_cache = resp.json()['id']
    logger.info('Created systeme.io tag "%s" id=%s', _TAG_NAME, _tag_id_cache)
    return _tag_id_cache


def sync_user(email: str, first_name: str = '', last_name: str = '') -> bool:
    """Upsert a single user into systeme.io with the krizn-user tag. Returns True on success."""
    try:
        tag_id = _get_or_create_tag()
        payload = {
            'email': email,
            'firstName': first_name or '',
            'lastName': last_name or '',
            'tags': [{'id': tag_id}],
        }
        resp = requests.post(f'{_BASE}/contacts', json=payload, headers=_headers(), timeout=10)
        if resp.status_code in (200, 201):
            return True
        # 409 = already exists — tag it
        if resp.status_code == 409:
            contact_id = resp.json().get('id')
            if contact_id:
                requests.post(
                    f'{_BASE}/contacts/{contact_id}/tags',
                    json={'tagId': tag_id},
                    headers=_headers(),
                    timeout=10,
                )
            return True
        logger.warning('systeme.io upsert %s → %s %s', email, resp.status_code, resp.text[:200])
        return False
    except Exception:
        logger.exception('systeme.io sync_user failed for %s', email)
        return False
