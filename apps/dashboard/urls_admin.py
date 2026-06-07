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
    path(
        'ops/optimize/',
        views.RunAssetOptimizationView.as_view(),
        name='run_asset_optimization',
    ),
    path(
        'ops/backup/',
        views.CreatePlatformBackupView.as_view(),
        name='create_platform_backup',
    ),
    path(
        'ops/backup/<int:backup_id>/download/',
        views.DownloadPlatformBackupView.as_view(),
        name='download_platform_backup',
    ),
    path(
        'ops/backup/<int:backup_id>/delete/',
        views.DeletePlatformBackupView.as_view(),
        name='delete_platform_backup',
    ),
    path(
        'projects/websiteoverview/',
        views.WebsiteOverviewDashboardView.as_view(),
        name='website_overview',
    ),
    path(
        'projects/<int:project_id>/delete/',
        views.DeleteProjectDashboardView.as_view(),
        name='delete_project',
    ),
]
