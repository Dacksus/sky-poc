import os
from logging import DEBUG, INFO

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+psycopg://atlas:atlas@localhost:5432/atlas_forge"

    celery_broker_url: str = "redis://red-d1t6f2mmcj7s73b7mu80:6379"
    celery_result_backend: str = (
        "db+postgresql+psycopg://atlas:atlas@localhost:5432/atlas_forge"
    )

    notion_token: str = "ntn_F48112944128Gtu4wJ3tGVD4RSU6wQzoBwqOVBh9tdkgDY"

    app_name: str = "Atlas Forge"
    debug: bool = True
    # debug switch to facilitate database updates with dockerized setup
    always_reset: bool = False

    log_level: int = DEBUG if debug else INFO

    class Config:
        env_file = ".env"


def get_settings():
    return Settings()
