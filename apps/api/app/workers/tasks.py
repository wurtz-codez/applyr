from app.workers.celery_app import celery_app


@celery_app.task(name="app.workers.tasks.healthcheck")
def healthcheck() -> dict[str, str]:
    return {"status": "ok"}


@celery_app.task(name="app.workers.tasks.execute_discovery")
def execute_discovery(run_id: str):
    from app.services.discovery import execute_run

    execute_run(run_id)


@celery_app.task(name="app.workers.tasks.scheduled_discovery")
def scheduled_discovery():
    from app.services.discovery import scheduled_discovery as run_scheduled

    run_scheduled()
