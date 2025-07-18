"""Model descriptions for database"""
import datetime
from uuid import UUID, uuid4
from sqlalchemy import (
    DateTime, 
    ForeignKey, 
    ForeignKeyConstraint, 
    func, 
    PrimaryKeyConstraint, 
    FetchedValue, 
    SmallInteger,
    Index
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
    """Persistent metadata for a single unique document. Actual content is stored in versions"""
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

    id: Mapped[UUID] = mapped_column(primary_key=True)
    # id of the parent document
    document_id: Mapped[UUID] = mapped_column(ForeignKey("documents.id"), nullable=False)
    # type of the element (e.g., heading, paragraph, list, etc.)
    element_type: Mapped[str]
    # convenience pointers to latest versions
    latest_metadata_version: Mapped[datetime.datetime] = mapped_column(nullable=True)
    # latest_metadata_hash:  Mapped[str]
    latest_content_version: Mapped[datetime.datetime] = mapped_column(nullable=True)
    latest_content_hash: Mapped[str] = mapped_column(nullable=True)


class DocumentElementMetadata(Base):
    """Metadata of an element that is subject to change, such as position in the document"""
    __tablename__ = "document_element_metadatas"

    # 
    document_element_id: Mapped[UUID] = mapped_column(ForeignKey("document_elements.id"))
    version: Mapped[datetime.datetime] = mapped_column(server_default=func.now())
    # level of nesting / indentation of the element to map document structure
    level: Mapped[int]
    # absolute position for ordering
    position: Mapped[int]
    # the last element of lower level preceding this element in the document structure
    parent_element: Mapped[UUID] = mapped_column(ForeignKey("document_elements.id"), nullable=True)
    # absolute position for ordering
    position: Mapped[int]
    # preceding element on same level for ordering (`NULL` if first on this level)
    predecessor: Mapped[UUID] = mapped_column(ForeignKey("document_elements.id"), nullable=True)
    # preceding element on same level for ordering (`NULL` if last on this level)
    successor: Mapped[UUID] = mapped_column(ForeignKey("document_elements.id"), nullable=True)
    # hash over all properties to quickly discover changes
    # hash: Mapped[str] = mapped_column(unique=True)

    __table_args__ = (
        PrimaryKeyConstraint("document_element_id", "version", name="metadata_pk"),
        Index("idx_parent_position", "parent_element", "position"),
    )

class DocumentElementContent(Base):
    """The actual content of an element"""
    __tablename__ = "document_element_contents"

    document_element_id: Mapped[UUID] = mapped_column(ForeignKey("document_elements.id"))
    version: Mapped[datetime.datetime] = mapped_column(server_default=func.now())
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
    triggered_at: Mapped[datetime.datetime] = mapped_column(server_default=func.now())
    executed_at: Mapped[datetime.datetime] = mapped_column(nullable=True)
    finished_at: Mapped[datetime.datetime] = mapped_column(nullable=True)
    status: Mapped[str] = mapped_column(server_default="open") # pending, done
    document_structure: Mapped[str] = mapped_column(nullable=True)
    document_structure_diff: Mapped[str] = mapped_column(nullable=True)
    changed_elements: Mapped[str] = mapped_column(nullable=True)
    changed_elements_diff: Mapped[str] = mapped_column(nullable=True)
    error: Mapped[str] = mapped_column(nullable=True)