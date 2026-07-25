from core.celery import app


@app.task(name='containers.restart_crashed_containers')
def restart_crashed_containers() -> int:
    """
    Every 10 min: restart app + MySQL containers for WordPress/PHP/Drupal projects
    that should be RUNNING but whose container isn't alive. See php.txt section 3
    INF-7. Only starts already-created containers — never recreates.
    """
    from apps.containers.services import (
        container_is_running,
        container_name,
        mysql_container_name,
        start_stopped_container,
    )
    from apps.databases.models import DatabaseInstance
    from apps.projects.models import Project, ProjectStatus, ProjectType

    container_hosted_types = (ProjectType.WORDPRESS, ProjectType.PHP, ProjectType.DRUPAL)

    projects = list(
        Project.objects.filter(
            project_type__in=container_hosted_types,
            status=ProjectStatus.RUNNING,
            is_deleted=False,
        )
    )
    mysql_project_ids = set(
        DatabaseInstance.objects.filter(
            project__in=projects,
            engine=DatabaseInstance.Engine.MYSQL,
        ).values_list('project_id', flat=True)
    )

    restarted = 0
    for project in projects:
        name = container_name(project)
        if not container_is_running(name):
            ok, _ = start_stopped_container(name)
            if ok:
                restarted += 1

        if project.pk in mysql_project_ids:
            mysql_name = mysql_container_name(project)
            if not container_is_running(mysql_name):
                start_stopped_container(mysql_name)

    return restarted
