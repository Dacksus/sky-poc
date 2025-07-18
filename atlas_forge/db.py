import logging
import sys
import uuid

from sqlalchemy import DDL, Engine, Select, create_engine, select, update
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from atlas_forge.config import get_settings
from atlas_forge.models.db_models import (
    Base,
    Document,
    DocumentElement,
    DocumentElementContent,
    DocumentElementMetadata,
    Snapshot,
)

logger = logging.getLogger("uvicorn.error")

settings = get_settings()

engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    pool_recycle=300,
    echo=settings.debug,  # Log SQL queries in debug mode
)

Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Define trigger functions and triggers as DDL statements
TRIGGER_DDL = {
    # Function for metadata version updates
    "metadata_function": DDL(
        """
        CREATE OR REPLACE FUNCTION update_latest_metadata_version()
        RETURNS TRIGGER AS $$
        BEGIN
            UPDATE document_elements 
            SET latest_metadata_version = NEW.version
            WHERE id = NEW.document_element_id
            AND (
                latest_metadata_version IS NULL 
                OR NEW.version > latest_metadata_version
            );
            
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """
    ),
    # Trigger for INSERT on metadata
    "metadata_insert_trigger": DDL(
        """
        DROP TRIGGER IF EXISTS trigger_update_latest_metadata_version ON document_element_metadatas;
        CREATE TRIGGER trigger_update_latest_metadata_version
            AFTER INSERT ON document_element_metadatas
            FOR EACH ROW
            EXECUTE FUNCTION update_latest_metadata_version();
    """
    ),
    # Function for content version updates
    "content_function": DDL(
        """
        CREATE OR REPLACE FUNCTION update_latest_content_version()
        RETURNS TRIGGER AS $$
        BEGIN
            UPDATE document_elements 
            SET 
                latest_content_version = NEW.version,
                latest_content_hash = NEW.hash_raw
            WHERE id = NEW.document_element_id
            AND (
                latest_content_version IS NULL 
                OR NEW.version > latest_content_version
            );
            
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """
    ),
    # Trigger for INSERT on content
    "content_insert_trigger": DDL(
        """
        DROP TRIGGER IF EXISTS trigger_update_latest_content_version ON document_element_contents;
        CREATE TRIGGER trigger_update_latest_content_version
            AFTER INSERT ON document_element_contents
            FOR EACH ROW
            EXECUTE FUNCTION update_latest_content_version();
    """
    ),
    # Validation function
    "validation_function": DDL(
        """
        CREATE OR REPLACE FUNCTION validate_version_consistency()
        RETURNS TABLE(
            element_id UUID,
            stored_metadata_version TIMESTAMP,
            actual_max_metadata_version TIMESTAMP,
            stored_content_version TIMESTAMP,
            actual_max_content_version TIMESTAMP,
            metadata_consistent BOOLEAN,
            content_consistent BOOLEAN
        ) AS $$
        BEGIN
            RETURN QUERY
            SELECT 
                de.id as element_id,
                de.latest_metadata_version as stored_metadata_version,
                meta_max.max_version as actual_max_metadata_version,
                de.latest_content_version as stored_content_version,
                content_max.max_version as actual_max_content_version,
                (de.latest_metadata_version = meta_max.max_version OR (de.latest_metadata_version IS NULL AND meta_max.max_version IS NULL)) as metadata_consistent,
                (de.latest_content_version = content_max.max_version OR (de.latest_content_version IS NULL AND content_max.max_version IS NULL)) as content_consistent
            FROM document_elements de
            LEFT JOIN (
                SELECT 
                    document_element_id,
                    MAX(version) as max_version
                FROM document_element_metadatas
                GROUP BY document_element_id
            ) meta_max ON de.id = meta_max.document_element_id
            LEFT JOIN (
                SELECT 
                    document_element_id,
                    MAX(version) as max_version
                FROM document_element_contents
                GROUP BY document_element_id
            ) content_max ON de.id = content_max.document_element_id;
        END;
        $$ LANGUAGE plpgsql;
    """
    ),
}


def create_tables():
    """Create all database tables"""
    logger.info("Creating database tables...")
    Base.metadata.create_all(bind=engine)
    logger.info("✓ Tables created successfully")


def drop_tables():
    """Drop all database tables"""
    logger.info("Dropping database tables...")
    Base.metadata.drop_all(bind=engine)
    logger.info("✓ Tables dropped successfully")


def verify_connection():
    """Verify database connection"""
    try:
        settings = get_settings()
        logger.info(f"Connecting to database: {settings.database_url}")

        with engine.connect() as conn:
            result = conn.execute(text("SELECT 1"))
            logger.info("✓ Database connection successful")

    except Exception as e:
        logger.error(f"✗ Database connection failed: {e}")
        sys.exit(1)


def create_triggers(engine: Engine):
    """Create all triggers and functions"""
    logger.info("Creating database triggers and functions...")

    with engine.connect() as conn:
        # Execute all DDL statements
        for name, ddl_statement in TRIGGER_DDL.items():
            try:
                logger.debug(f"Creating {name}")
                conn.execute(ddl_statement)
                conn.commit()
            except Exception as e:
                logger.error(f"Error creating {name}: {e}")
                conn.rollback()
                raise

    logger.info("✓ All triggers and functions created successfully")


def drop_triggers(engine: Engine):
    """Drop all triggers and functions"""
    logger.info("Dropping database triggers and functions...")

    drop_statements = [
        "DROP TRIGGER IF EXISTS trigger_update_latest_metadata_version ON document_element_metadatas;",
        "DROP TRIGGER IF EXISTS trigger_update_latest_metadata_version_on_update ON document_element_metadatas;",
        "DROP TRIGGER IF EXISTS trigger_update_latest_metadata_version_on_delete ON document_element_metadatas;",
        "DROP TRIGGER IF EXISTS trigger_update_latest_content_version ON document_element_contents;",
        "DROP FUNCTION IF EXISTS update_latest_metadata_version();",
        "DROP FUNCTION IF EXISTS update_latest_metadata_version_on_update();",
        "DROP FUNCTION IF EXISTS update_latest_metadata_version_on_delete();",
        "DROP FUNCTION IF EXISTS update_latest_content_version();",
        "DROP FUNCTION IF EXISTS initialize_latest_versions();",
        "DROP FUNCTION IF EXISTS validate_version_consistency();",
    ]

    with engine.connect() as conn:
        for statement in drop_statements:
            try:
                conn.execute(text(statement))
            except Exception as e:
                logger.warning(f"Error dropping: {statement} - {e}")
        conn.commit()

    logger.info("✓ Triggers and functions dropped")


def initialize_database(reset: bool = False):
    if reset or get_settings().always_reset:
        drop_tables()
    create_tables()
    create_triggers(engine)


# Utility functions for management
def validate_triggers():
    """Validate that triggers are working correctly"""
    with engine.connect() as conn:
        result = conn.execute(
            sa.text("SELECT * FROM validate_version_consistency()")
        ).fetchall()
        inconsistencies = [
            row
            for row in result
            if not (row.metadata_consistent and row.content_consistent)
        ]

        if inconsistencies:
            logger.warning(f"Found {len(inconsistencies)} version inconsistencies")
            return False
        else:
            logger.info("All version data is consistent")
            return True


def recreate_triggers():
    """Drop and recreate all triggers"""
    from app.database_triggers import create_triggers, drop_triggers

    drop_triggers(engine)
    create_triggers(engine)
    logger.info("Triggers recreated successfully")


# def exec_session(stmt: Select):
#     with Session() as session:
#         return session.execute(stmt)


def db_get_document_by_id(document_id: uuid.UUID) -> Document:
    stmt = select(Document).where(Document.id == document_id)
    with Session() as session:
        return session.scalars(stmt).first()


def db_get_document_by_notion_id(notion_id: str) -> Document:
    stmt = select(Document).where(Document.reference_id == notion_id)
    with Session() as session:
        return session.scalars(stmt).first()


def db_get_document_element_by_id(notion_id: str) -> DocumentElement:
    stmt = select(DocumentElement).where(DocumentElement.id == notion_id)
    with Session() as session:
        return session.scalars(stmt).first()


def db_get_element_hash_by_id(id: str) -> str:
    stmt = select(DocumentElement.latest_content_hash).where(Document.id == id)
    with Session() as session:
        return session.scalars(stmt).first()


def db_get_latest_metadata_for_element(elment_id: str) -> DocumentElementMetadata:
    stmt = select(DocumentElementMetadata).order_by(
        DocumentElementMetadata.version.desc()
    )
    with Session() as session:
        return session.scalars(stmt).first()


def db_get_latest_content_for_element(element_id: str) -> DocumentElementContent:
    stmt = (
        select(DocumentElementContent)
        .where(DocumentElementContent.document_element_id == element_id)
        .order_by(DocumentElementContent.version.desc())
    )
    with Session() as session:
        return session.scalars(stmt).first()


def db_get_latest_content_pair_by_id(element_id: str) -> list[DocumentElementContent]:
    stmt = (
        select(DocumentElementContent)
        .where(DocumentElementContent.document_element_id == element_id)
        .order_by(DocumentElementContent.version.desc())
        .limit(2)
    )
    with Session() as session:
        return session.scalars(stmt).all()


def db_get_latest_elements_by_document(
    document_id: uuid.UUID,
) -> list[(DocumentElementMetadata, DocumentElementContent)]:
    stmt = (
        select(DocumentElement, DocumentElementMetadata)
        .join(
            DocumentElementMetadata,
            DocumentElement.id == DocumentElementMetadata.document_element_id,
        )
        .where(
            DocumentElementMetadata.document_element_id == DocumentElement.id,
            DocumentElement.latest_metadata_version == DocumentElementMetadata.version,
        )
        .filter(DocumentElement.document_id == document_id)
        .order_by(DocumentElementMetadata.position)
    )
    with Session() as session:
        return session.execute(stmt).all()


def db_create_snapshot(reference_id: str) -> uuid.UUID:
    snapshot = Snapshot(reference_id=reference_id)
    with Session() as session:
        session.add(snapshot)
        session.commit()
        return snapshot.id


def db_get_snapshot_by_id(snapshot_id: uuid.UUID) -> Snapshot:
    stmt = select(Snapshot).where(Snapshot.id == snapshot_id)
    with Session() as session:
        return session.scalars(stmt).first()


def db_set_snapshot_pending(snapshot_id: uuid.UUID):
    stmt = update(Snapshot).where(Snapshot.id == snapshot_id).values(status="pending")
    with Session() as session:
        session.execute(stmt)


def db_get_previous_snapshot(snapshot_id: uuid.UUID) -> Snapshot:
    document_stmt = select(Snapshot.document_id, Snapshot.triggered_at).where(
        Snapshot.id == snapshot_id
    )
    subq = document_stmt.subquery()
    stmt = (
        select(Snapshot)
        .where(Snapshot.document_id == subq.c.document_id)
        .filter(Snapshot.triggered_at < subq.c.triggered_at)
        .order_by(Snapshot.triggered_at.desc())
    )
    with Session() as session:
        return session.scalars(stmt).first()
