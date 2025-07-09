"""Model definitions for the API"""
from pydantic import BaseModel

class DocumentReference(BaseModel):
    reference_id: str
    notion_token: str

class NewDocument(BaseModel):
    title: str
    reference_id: str
    document_type: str
    content: str | None = None
    url: str | None = None


class NewNotionDocument(NewDocument):
    notion_token: str


class NewDocumentResponse(BaseModel):
    id: str


class DocumentUpdate(NewDocument):
    id: str


class DocumentUpdateResponse(BaseModel):
    diff_id: str