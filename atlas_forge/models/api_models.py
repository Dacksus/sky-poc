"""Model definitions for the API"""

from uuid import UUID

from pydantic import BaseModel

from .db_models import DocumentElement


class DocumentReference(BaseModel):
    reference_id: str
    notion_token: str | None = None


class NewDocument(BaseModel):
    title: str
    reference_id: str
    document_type: str
    content: str | None = None
    url: str | None = None


class NewNotionDocument(NewDocument):
    notion_token: str


class NewDocumentResponse(BaseModel):
    result_id: str


class DocumentUpdate(NewDocument):
    id: str


class DocumentUpdateResponse(BaseModel):
    diff_id: str


class SnapshotResult(BaseModel):
    document_structure: str | None = None
    document_structure_diff: str | None = None
    changed_elements: str | None = None
    changed_elements_diff: str | None = None


# class DocumentStructure(BaseModel):
#     """internal and temporary representation of a notion page"""
#     element: DocumentElement
#     level: int
#     raw_hash: str
