import logging

import requests
from django.conf import settings

logger = logging.getLogger(__name__)


def cloudflare_upsert_a_record(fqdn: str, ip: str) -> dict:
    """Create or update an A record in Cloudflare DNS (zone from settings)."""
    token = settings.CLOUDFLARE_API_TOKEN
    zone_id = settings.CLOUDFLARE_ZONE_ID
    if not token or not zone_id:
        raise RuntimeError('CLOUDFLARE_API_TOKEN and CLOUDFLARE_ZONE_ID must be set.')

    base = f'https://api.cloudflare.com/client/v4/zones/{zone_id}/dns_records'
    headers = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}
    params = {'name': fqdn, 'type': 'A'}
    r = requests.get(base, headers=headers, params=params, timeout=30)
    r.raise_for_status()
    payload = {'type': 'A', 'name': fqdn, 'content': ip, 'ttl': 120, 'proxied': False}
    data = r.json()
    if not data.get('success', True):
        raise RuntimeError(data.get('errors', data))

    records = data.get('result', [])
    if records:
        rid = records[0]['id']
        rr = requests.put(f'{base}/{rid}', headers=headers, json=payload, timeout=30)
        rr.raise_for_status()
        out = rr.json()
        if not out.get('success', True):
            raise RuntimeError(out.get('errors', out))
        logger.info('Cloudflare DNS updated %s id=%s', fqdn, rid)
        return {'id': rid, 'action': 'updated'}

    rr = requests.post(base, headers=headers, json=payload, timeout=30)
    rr.raise_for_status()
    out = rr.json()
    if not out.get('success', True):
        raise RuntimeError(out.get('errors', out))
    rid = out['result']['id']
    logger.info('Cloudflare DNS created %s id=%s', fqdn, rid)
    return {'id': rid, 'action': 'created'}
