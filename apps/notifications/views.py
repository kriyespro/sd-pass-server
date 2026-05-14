from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.urls import reverse_lazy
from django.utils import timezone
from django.views import View
from django.views.generic import ListView
from django_htmx.http import HttpResponseClientRedirect

from core.mixins import SafePaginationMixin

from .models import Notification


class NotificationListView(LoginRequiredMixin, SafePaginationMixin, ListView):
    model = Notification
    template_name = 'pages/notifications/list.jinja'
    context_object_name = 'notifications'
    paginate_by = 30

    def get_queryset(self):
        return Notification.objects.filter(user=self.request.user).order_by('-created_at')


class MarkNotificationReadView(LoginRequiredMixin, View):
    def post(self, request, pk):
        get_object_or_404(Notification, pk=pk, user=request.user)
        Notification.objects.filter(pk=pk, user=request.user).update(read_at=timezone.now())
        if request.htmx:
            return HttpResponseClientRedirect(reverse_lazy('notifications:list'))
        return HttpResponseRedirect(reverse_lazy('notifications:list'))


class MarkAllNotificationsReadView(LoginRequiredMixin, View):
    def post(self, request):
        Notification.objects.filter(user=request.user, read_at__isnull=True).update(
            read_at=timezone.now()
        )
        if request.htmx:
            return HttpResponseClientRedirect(reverse_lazy('notifications:list'))
        return HttpResponseRedirect(reverse_lazy('notifications:list'))
