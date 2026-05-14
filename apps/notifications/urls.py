from django.urls import path

from . import views

app_name = 'notifications'

urlpatterns = [
    path('', views.NotificationListView.as_view(), name='list'),
    path('<int:pk>/read/', views.MarkNotificationReadView.as_view(), name='mark_read'),
    path('read-all/', views.MarkAllNotificationsReadView.as_view(), name='mark_all_read'),
]
