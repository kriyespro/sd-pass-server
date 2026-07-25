from core.celery import app


@app.task(name='phpapps.provision_php_site')
def provision_php_site(project_id: int, zip_path: str) -> dict:
    from pathlib import Path

    from apps.domains.services import site_url_for
    from apps.logs.models import LogKind
    from apps.logs.services import append_project_log
    from apps.notifications.models import NotificationLevel
    from apps.notifications.services import create_notification
    from apps.phpapps.services import provision
    from apps.projects.models import Project, ProjectStatus

    project = Project.objects.filter(pk=project_id, is_deleted=False).first()
    if project is None:
        return {'status': 'skipped_no_project'}

    try:
        provision(project, Path(zip_path))
    except RuntimeError as exc:
        Project.objects.filter(pk=project_id).update(status=ProjectStatus.FAILED)
        append_project_log(project, LogKind.SYSTEM, f'PHP deploy failed: {exc}')
        create_notification(
            user_id=project.owner_id,
            title='PHP app failed to deploy',
            body=str(exc),
            level=NotificationLevel.ERROR,
        )
        return {'status': 'failed', 'error': str(exc)}

    site_url = site_url_for(project)
    append_project_log(project, LogKind.BUILD, f'PHP app deployed at {site_url}')
    create_notification(
        user_id=project.owner_id,
        title='PHP app is live',
        body=f'Your PHP app is live at {site_url}',
        level=NotificationLevel.SUCCESS,
        link_url=site_url,
    )

    from apps.onboarding.services import complete_onboarding_on_deploy
    complete_onboarding_on_deploy(project.owner)

    return {'status': 'provisioned', 'url': site_url}


@app.task(name='phpapps.deprovision_php_site')
def deprovision_php_site(project_id: int) -> dict:
    from apps.phpapps.services import deprovision
    from apps.projects.models import Project

    project = Project.objects.filter(pk=project_id).first()
    if project is None:
        return {'status': 'skipped_no_project'}
    deprovision(project)
    return {'status': 'deprovisioned'}
