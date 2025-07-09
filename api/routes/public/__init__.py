from fastapi import APIRouter
from . import documents

router = APIRouter(prefix="/v1/chronicles")

router.include_router(documents.router)