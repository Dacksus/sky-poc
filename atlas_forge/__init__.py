"""Atlas Forge - The Atlas Document Versioning Service

This module initializes the FastAPI application with proper lifecycle management,
middleware configuration, and route registration.
"""

import logging
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from atlas_forge.db import initialize_database

from .routes.public import router

logger = logging.getLogger("uvicorn.error")


@asynccontextmanager
async def lifespan(api: FastAPI):
    """Setup routines for the app."""
    initialize_database()

    # await queue_init()
    yield
    # await queue_close()


DESCRIPTION = """
Minimal POC to snapshot documents from Notion and show diffs between snapshots.
"""

api = FastAPI(
    lifespan=lifespan,
    title="Atlas Forge API",
    description=DESCRIPTION,
    version="0.1.0",
    docs_url="/v1/forge/docs",
    redoc_url=None,
    openapi_url="/v1/forge/openapi.json",
    swagger_ui_parameters={"defaultModelsExpandDepth": 0},
)
api.include_router(router)

api.add_middleware(
    middleware_class=CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
