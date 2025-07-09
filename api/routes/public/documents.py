import json

from fastapi import APIRouter, Depends, HTTPException, Request
from notion_client import Client, APIResponseError

from api.models import (
    DocumentReference,
    DocumentUpdate,
    NewDocument,
    NewDocumentResponse,
    NewNotionDocument   
)
from app.db import get_db
from app.models import (
    Document,
    DocumentVersion,
    DocumentVersionDiff
)

router = APIRouter(prefix="/documents", tags=["documents"])

# @router.post("")
# def create_new_document(request: NewDocument) -> NewDocumentResponse:
#     pass

@router.post("")
def sync_from_notion(request: DocumentReference, db: Session = Depends(get_db)) -> NewDocumentResponse:
    notion = Client(auth=request.notion_token)
    try:
        page_contents = notion.blocks.retrieve(request.reference_id)
        print(page_contents)
    except APIResponseError as e:
        print(e)

@router.put("/{document_id}")
def update_document(request: DocumentUpdate) -> DocumentUpdateResponse:
    pass

@router.get("/notion-webhook")
def handle_notion_event(request):
    pass