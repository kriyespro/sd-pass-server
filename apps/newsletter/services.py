import logging
import time
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


def _request_with_retry(method: str, url: str, **kwargs) -> requests.Response:
    """Make a request, retrying once on 429 after honouring Retry-After."""
    resp = getattr(requests, method)(url, **kwargs)
    if resp.status_code == 429:
        retry_after = int(resp.headers.get('Retry-After', 10))
        logger.info('systeme.io 429 — waiting %ss before retry', retry_after)
        time.sleep(retry_after)
        resp = getattr(requests, method)(url, **kwargs)
    return resp


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


def _tag_existing_contact(email: str, tag_id: int) -> bool:
    """Look up contact by email and apply tag."""
    resp = _request_with_retry(
        'get', f'{_BASE}/contacts',
        params={'limit': 10, 'email': email},
        headers=_headers(), timeout=10,
    )
    if resp.status_code != 200:
        return False
    items = resp.json().get('items', [])
    if not items:
        return False
    contact_id = items[0]['id']
    r = _request_with_retry(
        'post', f'{_BASE}/contacts/{contact_id}/tags',
        json={'tagId': tag_id},
        headers=_headers(), timeout=10,
    )
    return r.status_code in (200, 201, 204)


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
        resp = _request_with_retry(
            'post', f'{_BASE}/contacts',
            json=payload, headers=_headers(), timeout=10,
        )
        if resp.status_code in (200, 201):
            return True
        if resp.status_code in (409, 422):
            try:
                body = resp.json()
            except Exception:
                body = {}
            detail = body.get('detail', '')
            if 'already used' in detail or resp.status_code == 409:
                return _tag_existing_contact(email, tag_id)
            logger.warning('systeme.io upsert %s → %s %s', email, resp.status_code, detail[:120])
            return False
        logger.warning('systeme.io upsert %s → %s %s', email, resp.status_code, resp.text[:120])
        return False
    except Exception:
        logger.exception('systeme.io sync_user failed for %s', email)
        return False
