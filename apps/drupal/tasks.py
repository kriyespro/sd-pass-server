from core.celery import app


@app.task(name='drupal.provision_drupal_site')
def provision_drupal_site(project_id: int, zip_path: str | None = None, admin_email: str | None = None) -> dict:
    from pathlib import Path

    from apps.domains.services import site_url_for
    from apps.drupal.models import DrupalInstance
    from apps.drupal.services import provision
    from apps.logs.models import LogKind
    from apps.logs.services import append_project_log
    from apps.notifications.models import NotificationLevel
    from apps.notifications.services import create_notification
    from apps.projects.models import Project, ProjectStatus

    project = Project.objects.filter(pk=project_id, is_deleted=False).first()
    if project is None:
        return {'status': 'skipped_no_project'}

    if not admin_email:
        existing = DrupalInstance.objects.filter(project=project).first()
        admin_email = (existing.admin_email if existing else '') or project.owner.email

    try:
        provision(project, Path(zip_path) if zip_path else None, admin_email)
    except RuntimeError as exc:
        Project.objects.filter(pk=project_id).update(status=ProjectStatus.FAILED)
        append_project_log(project, LogKind.SYSTEM, f'Drupal provisioning failed: {exc}')
        create_notification(
            user_id=project.owner_id,
            title='Drupal site failed to start',
            body=str(exc),
            level=NotificationLevel.ERROR,
        )
        return {'status': 'failed', 'error': str(exc)}

    site_url = site_url_for(project)
    append_project_log(project, LogKind.BUILD, f'Drupal site provisioned at {site_url}')
    create_notification(
        user_id=project.owner_id,
        title='Drupal site is live',
        body=f'Your Drupal site is live at {site_url} | Admin: {site_url}user/login',
        level=NotificationLevel.SUCCESS,
        link_url=site_url,
    )

    from apps.onboarding.services import complete_onboarding_on_deploy
    complete_onboarding_on_deploy(project.owner)

    return {'status': 'provisioned', 'url': site_url}


@app.task(name='drupal.deprovision_drupal_site')
def deprovision_drupal_site(project_id: int) -> dict:
    from apps.drupal.services import deprovision
    from apps.projects.models import Project

    project = Project.objects.filter(pk=project_id).first()
    if project is None:
        return {'status': 'skipped_no_project'}
    deprovision(project)
    return {'status': 'deprovisioned'}
