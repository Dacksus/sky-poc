"""Celery worker instance to collect all tasks from core"""

import logging

from celery import Celery
from celery.signals import task_failure

from atlas_forge.config import get_settings

logger = logging.getLogger(__name__)
logger.setLevel(get_settings().log_level)

app = Celery(
    "atlas_forge_worker",
    broker=get_settings().celery_broker_url,
    backend=get_settings().celery_result_backend,
)

# Configure Celery
app.conf.update(
    # Serialization
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    
    # Timezone
    timezone='UTC',
    enable_utc=True,
    
    # Task execution
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_reject_on_worker_lost=True,
    
    # Task routing (though overkill for now)
    # task_routes={
    #     'atlas_forge.core.normalize.*': {'queue': 'normalization'},
    #     'atlas_forge.core.diff.*': {'queue': 'diffing'},
    # },
    
    result_expires=3600,  # TODO explicit results still needed?
    
    # Worker settings
    worker_max_tasks_per_child=1000,
    worker_disable_rate_limits=True,
)

@task_failure.connect
def task_failure_handler(*args, **kwargs):
    """Log task failures for monitoring."""
    logger.error(f"❌ Task {task_id} failed: {exception}")
    logger.debug(f"Traceback: {traceback}")