"""Model descriptions for database"""
from app.db import Base
from sqlalchemy import DateTime, ForeignKey, ForeignKeyConstraint, func, PrimaryKeyConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

class Document(Base):
    """Persistent metadata for a single unique document. Actual content is stored in versions."""
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(primary_key=True)
    reference_id: Mapped[str]
    url: Mapped[str]
    title: Mapped[str]
    document_type: Mapped[str]
    created_at: Mapped[DateTime]
    updated_at: Mapped[DateTime] = mapped_column(server_default=func.now())
    num_versions: Mapped[int]
    is_active: Mapped[bool]
    versions: Mapped[list["DocumentVersion"]] = relationship()



class DocumentVersion(Base):
    """Individual version of a specific document for traceability."""
    __tablename__ = "document_versions"
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id"))
    version_number: Mapped[int]
    content_hash: Mapped[str] = mapped_column(nullable=False)
    raw_content: Mapped[str] = mapped_column(nullable=False)
    # normalized_content
    diff_to_last: Mapped["DocumentVersionDiff"] = relationship()
    created_at: Mapped[DateTime] = mapped_column(server_default=func.now())
    created_by: Mapped[str]

    __table_args__ = (
        PrimaryKeyConstraint("document_id", "version_number", name="mypk"),
        # ForeignKeyConstraint(
        #     columns=["diff_to_last"],
        #     refcolumns=["document_version_diffs.id"],
        #     ondelete="SET NULL (diff_to_last)"
        # )
    )

class DocumentVersionDiff(Base):
    """Diff of two specific versions of the same document."""
    __tablename__ = "document_version_diffs"

    id: Mapped[int] = mapped_column(primary_key=True)
    document_a: Mapped[int] = mapped_column(ForeignKey("document_versions.mypk"))
    document_b: Mapped[int] = mapped_column(ForeignKey("document_versions.mypk"))
    diff: Mapped[str]