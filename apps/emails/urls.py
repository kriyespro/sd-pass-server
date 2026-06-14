from django.urls import path

from . import views

app_name = 'admin_emails'

urlpatterns = [
    # Templates
    path('', views.EmailTemplateListView.as_view(), name='list'),
    path('smtp/', views.SMTPConfigView.as_view(), name='smtp'),
    path('create/<str:template_type>/', views.EmailTemplateCreateView.as_view(), name='create'),
    path('<int:pk>/edit/', views.EmailTemplateEditView.as_view(), name='edit'),
    path('<int:pk>/delete/', views.EmailTemplateDeleteView.as_view(), name='delete'),
    path('<int:pk>/send-test/', views.EmailTemplateSendTestView.as_view(), name='send_test'),
    path('default/<str:template_type>/', views.LoadDefaultTemplateView.as_view(), name='load_default'),

    # Email Lists
    path('lists/', views.EmailListListView.as_view(), name='email_lists'),
    path('lists/create/', views.EmailListEditView.as_view(), name='email_list_create'),
    path('lists/<int:pk>/edit/', views.EmailListEditView.as_view(), name='email_list_edit'),
    path('lists/<int:pk>/delete/', views.EmailListDeleteView.as_view(), name='email_list_delete'),
    path('lists/<int:pk>/populate/', views.EmailListPopulateView.as_view(), name='email_list_populate'),
    path('lists/auto/<str:segment>/', views.AutoCreateListView.as_view(), name='email_list_auto_create'),

    # Scheduled Emails
    path('scheduled/', views.ScheduledEmailListView.as_view(), name='scheduled'),
    path('scheduled/create/', views.ScheduledEmailCreateView.as_view(), name='scheduled_create'),
    path('scheduled/<int:pk>/delete/', views.ScheduledEmailDeleteView.as_view(), name='scheduled_delete'),
    path('scheduled/<int:pk>/send-now/', views.ScheduledEmailSendNowView.as_view(), name='scheduled_send_now'),

    # Campaigns
    path('campaigns/', views.CampaignListView.as_view(), name='campaigns'),
    path('campaigns/create/', views.CampaignEditView.as_view(), name='campaign_create'),
    path('campaigns/<int:pk>/edit/', views.CampaignEditView.as_view(), name='campaign_edit'),
    path('campaigns/<int:pk>/delete/', views.CampaignDeleteView.as_view(), name='campaign_delete'),
    path('campaigns/<int:pk>/toggle/', views.CampaignToggleView.as_view(), name='campaign_toggle'),
    path('campaigns/<int:pk>/run-now/', views.CampaignRunNowView.as_view(), name='campaign_run_now'),
    path('campaigns/process-due/', views.ProcessDueCampaignsView.as_view(), name='campaigns_process_due'),
]
