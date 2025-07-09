"""Atlas Chronicles - The Atlas Data Service"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from api.routes.public import router


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Setup routines for the app."""
    db_init()
    await queue_init()
    yield
    await queue_close()


DESCRIPTION = """
Minimal POC to snapshot documents from Notion and show diffs between snapshots.
"""

api = FastAPI(
    lifespan=lifespan,
    title="Chronicles API",
    description=DESCRIPTION,
    version="0.1.0",
    docs_url="/v1/chronicles/docs",
    redoc_url=None,
    openapi_url="/v1/chronicles/openapi.json",
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
