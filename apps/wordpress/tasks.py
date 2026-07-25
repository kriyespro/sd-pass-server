from core.celery import app


@app.task(name='wordpress.provision_wordpress_site')
def provision_wordpress_site(project_id: int, admin_email: str) -> dict:
    from apps.logs.models import LogKind
    from apps.logs.services import append_project_log
    from apps.notifications.models import NotificationLevel
    from apps.notifications.services import create_notification
    from apps.projects.models import Project, ProjectStatus
    from apps.wordpress.services import provision, site_url_for

    project = Project.objects.filter(pk=project_id, is_deleted=False).first()
    if project is None:
        return {'status': 'skipped_no_project'}

    try:
        provision(project, admin_email)
    except RuntimeError as exc:
        Project.objects.filter(pk=project_id).update(status=ProjectStatus.FAILED)
        append_project_log(project, LogKind.SYSTEM, f'WordPress provisioning failed: {exc}')
        create_notification(
            user_id=project.owner_id,
            title='WordPress site failed to start',
            body=str(exc),
            level=NotificationLevel.ERROR,
        )
        return {'status': 'failed', 'error': str(exc)}

    site_url = site_url_for(project)
    append_project_log(project, LogKind.BUILD, f'WordPress site provisioned at {site_url}')
    create_notification(
        user_id=project.owner_id,
        title='WordPress site is live',
        body=f'Your WordPress site is live at {site_url} | Admin: {site_url}wp-admin/',
        level=NotificationLevel.SUCCESS,
        link_url=site_url,
    )

    from apps.onboarding.services import complete_onboarding_on_deploy
    complete_onboarding_on_deploy(project.owner)

    return {'status': 'provisioned', 'url': site_url}


@app.task(name='wordpress.deprovision_wordpress_site')
def deprovision_wordpress_site(project_id: int) -> dict:
    from apps.projects.models import Project
    from apps.wordpress.services import deprovision

    project = Project.objects.filter(pk=project_id).first()
    if project is None:
        return {'status': 'skipped_no_project'}
    deprovision(project)
    return {'status': 'deprovisioned'}
