from pathlib import Path

from core.celery import app


@app.task(name='security.scan_upload')
def scan_upload(upload_id: int) -> dict:
    from django.db import transaction

    from apps.projects.models import Project, ProjectStatus
    from apps.security.models import ScanReport, ScanStatus
    from apps.security.services import run_security_scan
    from apps.uploads.models import ProjectUpload, UploadStatus

    upload = (
        ProjectUpload.objects.select_related('project')
        .filter(pk=upload_id)
        .first()
    )
    if not upload:
        return {'upload_id': upload_id, 'passed': False, 'reason': 'missing_upload'}

    if upload.status in (UploadStatus.CLEAN, UploadStatus.REJECTED):
        passed = upload.status == UploadStatus.CLEAN
        return {'upload_id': upload_id, 'passed': passed, 'idempotent': True}

    upload.status = UploadStatus.SCANNING
    upload.save(update_fields=['status'])

    file_path = Path(upload.file.path)
    result = run_security_scan(file_path)
    scan_status = result['status']
    passed = scan_status == ScanStatus.CLEAN

    with transaction.atomic():
        ScanReport.objects.update_or_create(
            upload=upload,
            defaults={
                'status': scan_status,
                'summary': result['summary'],
                'details': result.get('details', {}),
            },
        )
        upload.status = UploadStatus.CLEAN if passed else UploadStatus.REJECTED
        upload.save(update_fields=['status'])
        project: Project = upload.project
        if passed:
            project.status = ProjectStatus.RUNNING
        else:
            project.status = ProjectStatus.FAILED
        project.save(update_fields=['status'])

    from apps.logs.models import LogKind
    from apps.logs.services import append_project_log

    append_project_log(
        project,
        LogKind.SYSTEM,
        f'Security scan finished: {scan_status}. {result.get("summary", "")}',
    )

    if not passed:
        from django.urls import reverse

        from apps.notifications.models import NotificationLevel
        from apps.notifications.services import create_notification

        create_notification(
            user_id=project.owner_id,
            title='Upload rejected by security scan',
            body=(result.get('summary') or '')[:2000],
            level=NotificationLevel.ERROR,
            link_url=reverse('projects:upload_zip', kwargs={'slug': project.slug}),
        )

    return {
        'upload_id': upload_id,
        'passed': passed,
        'scan_status': scan_status,
        'project_id': upload.project_id,
    }
