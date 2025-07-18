"""SQLAlchemy database models for Atlas Forge.

This module defines the core data model for document versioning:
- Documents: Top-level document metadata
- DocumentElements: Individual blocks/components within documents
- DocumentElementMetadata: Versioned structural information
- DocumentElementContent: Versioned content data  
- Snapshots: Change tracking and processing status
"""

import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    DateTime,
    FetchedValue,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    PrimaryKeyConstraint,
    SmallInteger,
    func,
)
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class SMALLSERIAL(SmallInteger):
    pass


@compiles(SMALLSERIAL, "postgresql")
def compile_smallserial_pg(type_, compiler, **kw):
    return "SMALLSERIAL"


class Document(Base):
    """Top-level document metadata.
    
    Represents a single document from an external source (e.g., Notion page).
    The actual content is stored in versioned DocumentElements.
    """

    __tablename__ = "documents"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    reference_id: Mapped[str]
    url: Mapped[str]
    title: Mapped[str]
    document_type: Mapped[str]
    created_at: Mapped[datetime.datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime.datetime] = mapped_column(server_default=func.now())
    is_active: Mapped[bool] = mapped_column(default=True)
    elements: Mapped[list["DocumentElement"]] = relationship()


class DocumentElement(Base):
    """
    Proxy element describing the content and structure of a document.
    This class contains only static information about the element. Actual information
    is traced in `DocumentElementMetadata` and `DocumentElementContent` for versioning.
    """

    __tablename__ = "document_elements"

    id: Mapped[UUID] = mapped_column(primary_key=True) # Often external ID (e.g., Notion block ID)
    # id of the parent document
    document_id: Mapped[UUID] = mapped_column(
        ForeignKey("documents.id"), nullable=False
    )
    element_type: Mapped[str] # (e.g., heading, paragraph, list, etc.)
    # Cached latest version pointers (maintained by triggers)
    latest_metadata_version: Mapped[datetime.datetime] = mapped_column(nullable=True)
    latest_content_version: Mapped[datetime.datetime] = mapped_column(nullable=True)
    latest_content_hash: Mapped[str] = mapped_column(nullable=True)


class DocumentElementMetadata(Base):
    """Metadata of an element that is subject to change, such as position in the document"""

    __tablename__ = "document_element_metadatas"

    #
    document_element_id: Mapped[UUID] = mapped_column(
        ForeignKey("document_elements.id")
    )
    version: Mapped[datetime.datetime] = mapped_column(DateTime, server_default=func.now())
    level: Mapped[int] # Nesting depth (0 = root level)
    position: Mapped[int] # absolute position for ordering
    # the last element of lower level preceding this element in the document structure
    parent_element: Mapped[UUID] = mapped_column(
        ForeignKey("document_elements.id"), nullable=True
    )
    # absolute position for ordering
    position: Mapped[int]
    # preceding element on same level for ordering (`NULL` if first on this level)
    predecessor: Mapped[UUID] = mapped_column(
        ForeignKey("document_elements.id"), nullable=True
    )
    # preceding element on same level for ordering (`NULL` if last on this level)
    successor: Mapped[UUID] = mapped_column(
        ForeignKey("document_elements.id"), nullable=True
    )
    # hash over all properties to quickly discover changes
    # hash: Mapped[str] = mapped_column(unique=True)

    __table_args__ = (
        PrimaryKeyConstraint("document_element_id", "version", name="metadata_pk"),
        Index("idx_parent_position", "parent_element", "position"),
    )


class DocumentElementContent(Base):
    """Versioned content data for document elements.
    
    Stores the actual content of elements in both raw and formatted forms.
    Each content change creates a new version with a content hash for quick comparison.
    """

    __tablename__ = "document_element_contents"

    document_element_id: Mapped[UUID] = mapped_column(
        ForeignKey("document_elements.id")
    )
    version: Mapped[datetime.datetime] = mapped_column(DateTime, server_default=func.now())
    content_raw: Mapped[str]
    hash_raw: Mapped[str]
    content_formatted: Mapped[str]

    __table_args__ = (
        PrimaryKeyConstraint("document_element_id", "version", name="content_pk"),
    )


class Snapshot(Base):
    """Tracking triggers and executions of snapshots"""

    __tablename__ = "snapshots"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    document_id: Mapped[UUID] = mapped_column(ForeignKey("documents.id"), nullable=True)
    reference_id: Mapped[str]

    # Timing / lifecyle information
    triggered_at: Mapped[datetime.datetime] = mapped_column(server_default=func.now())
    executed_at: Mapped[datetime.datetime] = mapped_column(nullable=True)
    finished_at: Mapped[datetime.datetime] = mapped_column(nullable=True)

    # Processing status: 'open', 'pending', 'done', 'error' TODO SQL enum
    status: Mapped[str] = mapped_column(server_default="open")

    # Snapshot results (JSON strings)
    document_structure: Mapped[str] = mapped_column(nullable=True)
    document_structure_diff: Mapped[str] = mapped_column(nullable=True)
    changed_elements: Mapped[str] = mapped_column(nullable=True)
    changed_elements_diff: Mapped[str] = mapped_column(nullable=True)

    # Error info
    error: Mapped[str] = mapped_column(nullable=True)
