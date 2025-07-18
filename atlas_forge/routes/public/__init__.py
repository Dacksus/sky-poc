from fastapi import APIRouter

from . import documents

router = APIRouter(prefix="/v1/forge")

router.include_router(documents.router)
