from django.urls import reverse
from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.billing.services import get_or_create_subscription
from apps.notifications.models import Notification
from apps.projects.models import Project

from .serializers import NotificationSerializer, ProjectSerializer, SubscriptionSerializer


class ProjectViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = ProjectSerializer

    def get_queryset(self):
        return (
            Project.objects.filter(owner=self.request.user, is_deleted=False)
            .select_related('owner')
            .order_by('-created_at')
        )


class NotificationViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = NotificationSerializer

    def get_queryset(self):
        return Notification.objects.filter(user=self.request.user).order_by('-created_at')


class BillingSummaryView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        sub = get_or_create_subscription(request.user)
        data = SubscriptionSerializer(sub).data
        data['portal_url'] = request.build_absolute_uri(reverse('projects:dashboard'))
        return Response(data)


class ApiRootView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(
            {
                'projects': request.build_absolute_uri(reverse('api:project-list')),
                'notifications': request.build_absolute_uri(reverse('api:notification-list')),
                'billing': request.build_absolute_uri(reverse('api:billing-summary')),
                'auth_token': request.build_absolute_uri(reverse('api:api-token')),
            }
        )
