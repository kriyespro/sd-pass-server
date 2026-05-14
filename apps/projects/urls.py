from django.urls import path

from apps.backups import views as backup_views
from apps.databases import views as db_views
from apps.envmanager import views as env_views
from apps.logs import views as log_views
from apps.uploads import views as upload_views

from . import views

app_name = 'projects'

urlpatterns = [
    path('', views.ProjectDashboardView.as_view(), name='dashboard'),
    path('new/', views.ProjectCreateView.as_view(), name='create'),
    path('<slug:slug>/upload/', upload_views.ZipUploadView.as_view(), name='upload_zip'),
    path(
        '<slug:slug>/upload/files/',
        upload_views.MultiStaticFilesView.as_view(),
        name='upload_static_files',
    ),
    path('<slug:slug>/environment/', env_views.ProjectEnvironmentView.as_view(), name='environment'),
    path('<slug:slug>/logs/', log_views.ProjectLogsView.as_view(), name='logs'),
    path('<slug:slug>/logs/table/', log_views.ProjectLogsTablePartialView.as_view(), name='logs_partial'),
    path('<slug:slug>/databases/', db_views.ProjectDatabasesView.as_view(), name='databases'),
    path('<slug:slug>/backups/', backup_views.ProjectBackupsView.as_view(), name='backups'),
    path('<slug:slug>/delete/', views.ProjectDeleteView.as_view(), name='delete'),
    path('<slug:slug>/domain/', views.ProjectCustomDomainView.as_view(), name='domain'),
    path(
        '<slug:slug>/domain/verify/',
        views.CustomDomainVerifyNowView.as_view(),
        name='domain_verify',
    ),
]
