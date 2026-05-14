from core.celery import app


@app.task(name='databases.provision_stub')
def provision_database_stub(project_id: int, engine: str = 'postgres') -> str:
    """Placeholder: create container + credentials (durga D1)."""
    return f'stub provision project_id={project_id} engine={engine}'
