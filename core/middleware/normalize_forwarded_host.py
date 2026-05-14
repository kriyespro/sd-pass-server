"""
Some proxies send ``X-Forwarded-Host: host1, host2`` or stray whitespace. Django
then validates the whole string against ``ALLOWED_HOSTS`` and raises
``DisallowedHost`` (HTTP 400). Keep only the first host segment.
"""


class NormalizeForwardedHostMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        key = 'HTTP_X_FORWARDED_HOST'
        raw = request.META.get(key)
        if raw:
            first = raw.split(',')[0].strip()
            if first != raw:
                request.META[key] = first
        return self.get_response(request)
