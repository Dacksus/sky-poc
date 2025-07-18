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
    """Application lifespan management.
    
    Handles startup and shutdown routines for the FastAPI application.
    During startup, initializes the database schema and triggers.
    """

    try:
        # Initialize database schema and triggers
        initialize_database()
        logger.info("Database initialization completed")
        
        # Additional startup tasks can be added here
        # await initialize_other_services()
        
    except Exception as e:
        logger.error(f"Failed to initialize application: {e}")
        raise

    yield

    # cleanup tasks follow here

DESCRIPTION = """
Minimal POC to snapshot documents from Notion and show diffs between snapshots.
"""

api = FastAPI(
    lifespan=lifespan,
    title="Atlas Forge API",
    description=DESCRIPTION,
    version="0.1.0",
    docs_url="/v1/forge/docs",
    redoc_url="/v1/forge/redoc",
    openapi_url="/v1/forge/openapi.json",
    swagger_ui_parameters={"defaultModelsExpandDepth": 0},
)

# Add CORS middleware for frontend integration
api.add_middleware(
    middleware_class=CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

api.include_router(router)

# Health check endpoint
@api.get("/health")
def health_check():
    """Basic health check endpoint for service monitoring."""
    return {
        "status": "healthy",
        "service": "atlas-forge",
        "version": "0.1.0"
    }
