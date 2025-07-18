import datetime
import json
import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from hashlib import blake2b
from notion_client import Client, APIResponseError

from atlas_forge.models.api_models import (
    DocumentReference,
    DocumentUpdate,
    DocumentUpdateResponse,
    NewDocument,
    NewDocumentResponse,
    NewNotionDocument,
    SnapshotResult
)
from atlas_forge.config import get_settings
from atlas_forge.core.normalize import sync_from_notion
from atlas_forge.core.diff import diff_elements
from atlas_forge.db import (
    db_create_snapshot,
    db_get_document_by_id,
    db_get_document_by_notion_id,
    db_get_document_element_by_id,
    db_get_element_hash_by_id,
    db_get_latest_content_for_element,
    db_get_snapshot_by_id,
    Session
)
from atlas_forge.models.db_models import (
    Document,
    DocumentElement,
    DocumentElementContent,
    DocumentElementMetadata,
    Snapshot
)

logger = logging.getLogger('uvicorn.error')
router = APIRouter(prefix="/documents", tags=["documents"])

@router.post("")
def create_new_document(request: DocumentReference) -> NewDocumentResponse:
    # create a new snapshot in the db to be completed in background from the worker
    snapshot_id = db_create_snapshot(request.reference_id)
    # start the normalization and diffing celery tasks
    sync_from_notion.delay(snapshot_id, request.notion_token)

    return NewDocumentResponse(result_id = str(snapshot_id))

@router.get("snapshot/{snapshot_id}")    
def get_result(snapshot_id: str) -> SnapshotResult:
    snapshot = db_get_snapshot_by_id(uuid.UUID(snapshot_id))
    if not snapshot:
        raise HTTPException(status_code=404, detail="no snapshot exists with that id")
    return SnapshotResult(
        document_structure=snapshot.document_structure,
        document_structure_diff=snapshot.document_structure_diff,
        changed_elements=snapshot.changed_elements,
        changed_elements_diff=snapshot.changed_elements_diff,
    )

@router.put("/{document_id}")
def update_document(request: DocumentUpdate) -> DocumentUpdateResponse:
    pass

@router.post("/notion-webhook")
def handle_notion_event(request: Request):
    event = request.json()
    logger.info(f"received event of type {event["type"]} for {event["entity"]["type"]}({event["entity"]["id"]})")