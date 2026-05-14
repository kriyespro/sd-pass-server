import logging

from core.celery import app

logger = logging.getLogger(__name__)


@app.task(name='projects.on_project_created')
def on_project_created(project_id: int) -> dict:
    """Placeholder until the deploy engine runs in Celery. Confirms workers consume tasks."""
    logger.info('on_project_created project_id=%s', project_id)
    return {'project_id': project_id, 'ok': True}
