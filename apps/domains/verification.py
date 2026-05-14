"""DNS verification for custom hostnames (student domains)."""

from __future__ import annotations

import ipaddress
import logging

logger = logging.getLogger(__name__)

# Cloudflare's published IPv4 + IPv6 ranges (proxied records resolve to these).
# Source: https://www.cloudflare.com/ips/
_CF_NETWORKS = [
    ipaddress.ip_network(n) for n in (
        '173.245.48.0/20', '103.21.244.0/22', '103.22.200.0/22',
        '103.31.4.0/22', '141.101.64.0/18', '108.162.192.0/18',
        '190.93.240.0/20', '188.114.96.0/20', '197.234.240.0/22',
        '198.41.128.0/17', '162.158.0.0/15', '104.16.0.0/13',
        '104.24.0.0/14', '172.64.0.0/13', '131.0.72.0/22',
        '2400:cb00::/32', '2606:4700::/32', '2803:f800::/32',
        '2405:b500::/32', '2405:8100::/32', '2a06:98c0::/29',
        '2c0f:f248::/32',
    )
]


def _is_cloudflare_ip(ip_str: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip_str)
    except ValueError:
        return False
    return any(addr in net for net in _CF_NETWORKS)

# Legacy TXT-based verification (kept for backward compat; new flow uses A-record).
CHALLENGE_RR_LABEL = '_studentcloud-challenge'


def challenge_txt_fqdn(hostname: str) -> str:
    """FQDN where the student must publish a TXT record containing the token."""
    h = (hostname or '').strip().lower().rstrip('.')
    return f'{CHALLENGE_RR_LABEL}.{h}'


def domain_via_cloudflare_proxy(hostname: str) -> bool:
    """
    Return True if all resolved A records for *hostname* are Cloudflare proxy IPs.
    This means the student set up an orange-cloud A record in Cloudflare pointing
    somewhere — we still need a local probe to confirm it points HERE.
    """
    h = (hostname or '').strip().lower().rstrip('.')
    if not h:
        return False
    try:
        import dns.resolver
    except ImportError:
        return False
    resolver = dns.resolver.Resolver(configure=False)
    resolver.nameservers = ['1.1.1.1', '8.8.8.8']
    resolver.timeout = 5
    resolver.lifetime = 8
    try:
        answers = resolver.resolve(h, 'A')
    except Exception:  # noqa: BLE001
        return False
    ips = [str(r.address) for r in answers]
    return bool(ips) and all(_is_cloudflare_ip(ip) for ip in ips)


def local_http_probe(hostname: str, gunicorn_port: int = 9898) -> bool:
    """
    Hit Gunicorn directly on 127.0.0.1:{gunicorn_port} with Host: {hostname}.
    If Django responds (not 400 Bad Request / DisallowedHost), the hostname is
    registered in our system AND (combined with Cloudflare proxy detection) the
    student's A record points to this server.
    """
    import urllib.request
    import urllib.error

    url = f'http://127.0.0.1:{gunicorn_port}/'
    req = urllib.request.Request(url)
    req.add_header('Host', hostname)
    req.add_header('X-Forwarded-Proto', 'https')
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status < 500
    except urllib.error.HTTPError as e:
        # 400 = DisallowedHost (not registered), 4xx others = app responding = OK
        if e.code == 400:
            return False
        return True  # 403, 404, 301 etc. all mean Django accepted the host
    except Exception as exc:  # noqa: BLE001
        logger.warning('local_http_probe failed for %s: %s', hostname, exc)
        return False


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
