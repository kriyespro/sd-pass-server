from .services import capture_referral


class AffiliateReferralMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        capture_referral(request)
        return self.get_response(request)
