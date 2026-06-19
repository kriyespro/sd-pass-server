from django.conf import settings
from django.contrib.sitemaps import Sitemap
from django.urls import reverse

_DOMAIN = getattr(settings, 'SITE_DOMAIN', 'krizn.com')


class _BaseSitemap(Sitemap):
    protocol = 'https'

    def get_domain(self, site=None):
        return _DOMAIN


class StaticViewSitemap(_BaseSitemap):
    priority = 1.0
    changefreq = 'weekly'

    def items(self):
        return ['home', 'resell:store']

    def location(self, item):
        return reverse(item)


class ProgrammaticHubSitemap(_BaseSitemap):
    """Top-level /hosting/ and /server/ hub pages."""
    priority = 0.9
    changefreq = 'monthly'

    def items(self):
        return [
            '/hosting/',
            '/server/',
            '/pricing/',
            '/features/',
        ]

    def location(self, item):
        return item


class ProgrammaticLandingSitemap(_BaseSitemap):
    """All /hosting/<slug>/ and /server/<slug>/ landing pages."""
    priority = 0.8
    changefreq = 'monthly'

    PAGES = [
        '/hosting/for-students/',
        '/hosting/python/',
        '/hosting/flask/',
        '/hosting/static-website/',
        '/hosting/portfolio/',
        '/hosting/affordable/',
        '/hosting/with-ssl/',
        '/hosting/custom-domain/',
        '/hosting/free-trial/',
        '/server/for-students/',
        '/server/deploy-website/',
        '/server/python/',
        '/server/affordable/',
        '/server/with-ssl/',
    ]

    def items(self):
        return self.PAGES

    def location(self, item):
        return item


class ResellProductSitemap(_BaseSitemap):
    priority = 0.6
    changefreq = 'weekly'

    def items(self):
        from apps.resell.models import ResellProduct
        return ResellProduct.objects.filter(is_active=True)

    def location(self, obj):
        return reverse('resell:product_detail', kwargs={'slug': obj.slug})
