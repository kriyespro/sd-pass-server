from django.contrib import admin
from django.urls import include, path

from core import views as core_views

admin.site.site_header = 'StudentCloud Deploy'
admin.site.site_title = 'StudentCloud'
admin.site.index_title = 'Administration'

urlpatterns = [
    path('sd/', admin.site.urls),
    path('admin/', include('apps.dashboard.urls_admin')),
    path('accounts/', include('apps.accounts.urls')),
    path('projects/', include('apps.projects.urls')),
    path('billing/', include('apps.billing.urls')),
    path('notifications/', include('apps.notifications.urls')),
    path('ops/', include('apps.dashboard.urls_ops')),
    path('trainer/', include('apps.dashboard.urls_trainer')),
    path('api/v1/', include('apps.api.urls')),
    path('', core_views.home, name='home'),
]

handler404 = core_views.handler404
handler500 = core_views.handler500
