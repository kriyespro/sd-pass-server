from django.urls import path

from . import views

app_name = 'admin_monitor'

urlpatterns = [
    path('', views.SuperuserMonitorView.as_view(), name='dashboard'),
    path('export/websites.csv', views.StudentWebsitesCsvView.as_view(), name='export_websites_csv'),
    path(
        'export/project/<int:project_id>/files.zip',
        views.StudentProjectSiteZipView.as_view(),
        name='download_project_files',
    ),
]
