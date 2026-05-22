from django.contrib import admin

from apps.platform_ops.models import AssetOptimizationRun, ImageCompressionLog, PlatformBackup


@admin.register(AssetOptimizationRun)
class AssetOptimizationRunAdmin(admin.ModelAdmin):
    list_display = (
        'pk',
        'status',
        'started_at',
        'finished_at',
        'projects_processed',
        'bytes_saved',
        'triggered_by',
    )
    list_filter = ('status',)
    readonly_fields = (
        'started_at',
        'finished_at',
        'next_run_at',
        'projects_processed',
        'css_files',
        'js_files',
        'image_files',
        'files_optimized',
        'bytes_before',
        'bytes_after',
        'bytes_saved',
        'cache_used_memory_human',
        'cache_peak_memory_human',
        'cache_keys',
        'error_message',
    )


@admin.register(ImageCompressionLog)
class ImageCompressionLogAdmin(admin.ModelAdmin):
    list_display = (
        'pk',
        'project',
        'status',
        'trigger',
        'images_found',
        'images_optimized',
        'total_bytes_saved',
        'started_at',
    )
    list_filter = ('status', 'trigger')
    readonly_fields = (
        'started_at',
        'finished_at',
        'images_found',
        'images_optimized',
        'bytes_saved',
        'ultra_images_optimized',
        'ultra_bytes_saved',
        'total_bytes_saved',
        'error_message',
    )


@admin.register(PlatformBackup)
class PlatformBackupAdmin(admin.ModelAdmin):
    list_display = (
        'pk',
        'backup_type',
        'status',
        'size_bytes',
        'created_at',
        'finished_at',
        'created_by',
    )
    list_filter = ('status', 'backup_type')
    readonly_fields = (
        'storage_path',
        'size_bytes',
        'includes_database',
        'includes_sites',
        'created_at',
        'finished_at',
        'error_message',
    )
