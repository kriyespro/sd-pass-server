from rest_framework import serializers

from apps.billing.models import Subscription
from apps.notifications.models import Notification
from apps.projects.models import Project


class ProjectSerializer(serializers.ModelSerializer):
    project_type_display = serializers.CharField(source='get_project_type_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)

    class Meta:
        model = Project
        fields = (
            'id',
            'slug',
            'name',
            'project_type',
            'project_type_display',
            'subdomain',
            'custom_hostname',
            'custom_hostname_verified',
            'description',
            'status',
            'status_display',
            'created_at',
        )
        read_only_fields = fields


class NotificationSerializer(serializers.ModelSerializer):
    level_display = serializers.CharField(source='get_level_display', read_only=True)

    class Meta:
        model = Notification
        fields = (
            'id',
            'title',
            'body',
            'level',
            'level_display',
            'link_url',
            'read_at',
            'created_at',
        )
        read_only_fields = fields


class SubscriptionSerializer(serializers.ModelSerializer):
    plan_display = serializers.CharField(source='get_plan_slug_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)

    class Meta:
        model = Subscription
        fields = (
            'plan_slug',
            'plan_display',
            'status',
            'status_display',
            'current_period_end',
            'updated_at',
        )
        read_only_fields = fields
