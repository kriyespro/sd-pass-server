"""DNS verification for custom hostnames (student domains)."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# Legacy TXT-based verification (kept for backward compat; new flow uses A-record).
CHALLENGE_RR_LABEL = '_studentcloud-challenge'


def challenge_txt_fqdn(hostname: str) -> str:
    """FQDN where the student must publish a TXT record containing the token."""
    h = (hostname or '').strip().lower().rstrip('.')
    return f'{CHALLENGE_RR_LABEL}.{h}'


def a_record_matches_ip(hostname: str, expected_ip: str) -> bool:
    """
    Return True if any A record for *hostname* matches *expected_ip*.
    Uses a fresh resolver bypassing /etc/hosts so we check public DNS.
    """
    h = (hostname or '').strip().lower().rstrip('.')
    ip = (expected_ip or '').strip()
    if not h or not ip:
        return False
    try:
        import dns.resolver
    except ImportError:
        logger.error('dnspython is not installed; cannot verify custom domains.')
        return False

    resolver = dns.resolver.Resolver(configure=False)
    # Use Cloudflare public DNS for consistent results
    resolver.nameservers = ['1.1.1.1', '8.8.8.8']
    resolver.timeout = 5
    resolver.lifetime = 10
    try:
        answers = resolver.resolve(h, 'A')
    except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer, dns.resolver.NoNameservers):
        return False
    except dns.resolver.Timeout:
        logger.info('DNS timeout verifying A record for %s', h)
        return False
    except Exception as exc:  # noqa: BLE001
        logger.warning('DNS error verifying A record for %s: %s', h, exc)
        return False

    for rdata in answers:
        if str(rdata.address) == ip:
            return True
    return False


def challenge_txt_present(hostname: str, token: str) -> bool:
    """
    Return True if a public DNS TXT lookup for challenge_txt_fqdn(hostname)
    returns at least one string containing the verification token.
    """
    h = (hostname or '').strip().lower().rstrip('.')
    tok = (token or '').strip()
    if not h or not tok:
        return False
    fqdn = challenge_txt_fqdn(h)
    try:
        import dns.resolver
    except ImportError:
        logger.error('dnspython is not installed; cannot verify custom domains.')
        return False

    resolver = dns.resolver.Resolver()
    resolver.timeout = 5
    resolver.lifetime = 10
    try:
        answers = resolver.resolve(fqdn, 'TXT')
    except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer, dns.resolver.NoNameservers):
        return False
    except dns.resolver.Timeout:
        logger.info('DNS timeout verifying %s', fqdn)
        return False
    except Exception as exc:  # noqa: BLE001
        logger.warning('DNS error verifying %s: %s', fqdn, exc)
        return False

    for rdata in answers:
        for raw in rdata.strings:
            try:
                s = raw.decode('utf-8') if isinstance(raw, (bytes, bytearray)) else str(raw)
            except UnicodeDecodeError:
                continue
            if tok in s:
                return True
    return False
