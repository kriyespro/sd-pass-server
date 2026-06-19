from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.sitemaps.views import sitemap
from django.urls import include, path, re_path
from django.views.static import serve

from core import views as core_views
from core.sitemaps import (
    ProgrammaticHubSitemap,
    ProgrammaticLandingSitemap,
    ResellProductSitemap,
    StaticViewSitemap,
)

admin.site.site_header = 'Krizn Admin'
admin.site.site_title = 'Krizn'
admin.site.index_title = 'Administration'

_sitemaps = {
    'static': StaticViewSitemap,
    'hubs': ProgrammaticHubSitemap,
    'landing': ProgrammaticLandingSitemap,
    'products': ResellProductSitemap,
}

urlpatterns = [
    path('sd/', admin.site.urls),
    path('admin/', include('apps.dashboard.urls_admin')),
    path('accounts/', include('apps.accounts.urls')),
    # Google OAuth (separate include so URL names are google_login / google_callback for allauth).
    path('accounts/', include('allauth.socialaccount.providers.google.urls')),
    path('projects/', include('apps.projects.urls')),
    path('billing/', include('apps.billing.urls')),
    path('notifications/', include('apps.notifications.urls')),
    path('onboarding/', include('apps.onboarding.urls')),
    path('ops/', include('apps.dashboard.urls_ops')),
    path('trainer/', include('apps.dashboard.urls_trainer')),
    path('api/v1/', include('apps.api.urls')),
    path('affiliate/', include('apps.affiliates.urls')),
    path('resell/', include('apps.resell.urls')),
    path('admin/emails/', include('apps.emails.urls')),
    # SEO utility URLs
    path('robots.txt', core_views.robots_txt, name='robots_txt'),
    path('sitemap.xml', sitemap, {'sitemaps': _sitemaps}, name='sitemap'),
    # Programmatic SEO landing pages (/hosting/, /server/, etc.)
    path('', include('apps.seo.urls')),
    path('', core_views.home, name='home'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
else:
    urlpatterns += [
        re_path(
            r'^media/(?P<path>.*)$',
            serve,
            {'document_root': settings.MEDIA_ROOT},
        ),
    ]

handler404 = core_views.handler404
handler500 = core_views.handler500
