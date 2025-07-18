"""Celery worker instance to collect all tasks from core"""
import logging

from celery import Celery

from atlas_forge.config import get_settings

app = Celery("atlas_forge_worker", broker=get_settings().celery_broker_url, backend=get_settings().celery_result_backend)

logger = logging.getLogger(__name__)
logger.setLevel(get_settings().log_level)