import datetime
import json
import logging
import uuid
from hashlib import blake2b

from fastapi import APIRouter, Depends, HTTPException, Request
from notion_client import APIResponseError, Client

from atlas_forge.config import get_settings
from atlas_forge.core.diff import diff_elements
from atlas_forge.core.normalize import sync_from_notion
from atlas_forge.db import (
    Session,
    db_create_snapshot,
    db_get_document_by_id,
    db_get_document_by_notion_id,
    db_get_document_element_by_id,
    db_get_element_hash_by_id,
    db_get_latest_content_for_element,
    db_get_snapshot_by_id,
)
from atlas_forge.models.api_models import (
    DocumentReference,
    DocumentUpdate,
    DocumentUpdateResponse,
    NewDocument,
    NewDocumentResponse,
    NewNotionDocument,
    SnapshotResult,
)
from atlas_forge.models.db_models import (
    Document,
    DocumentElement,
    DocumentElementContent,
    DocumentElementMetadata,
    Snapshot,
)

logger = logging.getLogger("uvicorn.error")
router = APIRouter(prefix="/documents", tags=["documents"])


@router.post("")
def create_new_document(request: DocumentReference) -> NewDocumentResponse:
    """Create a new document snapshot from an external source.
    
    This endpoint:
    1. Creates a new snapshot record in the database
    2. Triggers background processing to fetch and normalize document content
    3. Returns a snapshot ID for tracking processing status
    
    Args:
        request: Document reference containing external ID and optional token
        
    Returns:
        Response with snapshot ID for status tracking
        
    Raises:
        HTTPException: If snapshot creation fails
    """
    try:
        snapshot_id = db_create_snapshot(request.reference_id)
        # start the normalization and diffing celery tasks
        sync_from_notion.delay(snapshot_id, request.notion_token)

        return NewDocumentResponse(result_id=str(snapshot_id))

    except Exception as e:
        logger.error(f"Failed to create snapshot for {request.reference_id}: {e}")
        raise HTTPException(
            status_code=500, 
            detail=f"Failed to create document snapshot: {str(e)}"
        )

@router.get("snapshot/{snapshot_id}")
def get_result(snapshot_id: str) -> SnapshotResult:
    """Retrieve the results of a document snapshot.
    
    Returns the current state of snapshot processing, including:
    - Document structure representation
    - Structure diff from previous snapshot  
    - List of changed elements
    - Content diffs for changed elements
    
    Args:
        snapshot_id: UUID of the snapshot to retrieve
        
    Returns:
        Complete snapshot results and diff information
        
    Raises:
        HTTPException: If snapshot not found or invalid UUID
    """
    snapshot = db_get_snapshot_by_id(uuid.UUID(snapshot_id))
    if not snapshot:
        raise HTTPException(status_code=404, detail="no snapshot exists with that id")
    return SnapshotResult(
        status=snapshot.status,
        document_structure=snapshot.document_structure,
        document_structure_diff=snapshot.document_structure_diff,
        changed_elements=snapshot.changed_elements,
        changed_elements_diff=snapshot.changed_elements_diff,
    )


@router.put("/{document_id}")
def update_document(request: DocumentUpdate) -> DocumentUpdateResponse:
    pass


@router.post("/notion-webhook")
async def handle_notion_webhook(request: Request):
    """Handle webhook events from Notion.
    
    Processes webhook notifications from Notion when pages are updated,
    automatically triggering snapshot creation for tracked documents.
    
    Args:
        request: Raw webhook request from Notion
        background_tasks: FastAPI background task manager
        
    Returns:
        Acknowledgment response
    """
    try:
        # Parse webhook payload
        event = await request.json()
        event_type = event.get("type")
        entity = event.get("entity", {})
        entity_type = entity.get("type")
        entity_id = entity.get("id")
        
        logger.info(f"Received Notion webhook: {event_type} for {entity_type}({entity_id})")
        
        # Handle page update events
        if event_type == "page" and entity_type == "page":
            # Create snapshot for updated page
            snapshot_id = db_create_snapshot(entity_id)
            
            # Trigger background processing
            sync_from_notion.delay(str(snapshot_id))
            
            logger.info(f"Created webhook snapshot {snapshot_id} for page {entity_id}")
        
        return NewDocumentResponse(result_id=str(snapshot_id))
        
    except Exception as e:
        logger.error(f"Error processing Notion webhook: {e}")
        raise HTTPException(status_code=500, detail="Webhook processing failed")