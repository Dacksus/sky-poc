"""Functions for normalizing external content for further processing"""

import datetime
import json
import logging
import uuid
from hashlib import blake2b

from celery import group
from notion_client import APIResponseError, Client

from atlas_forge.config import get_settings
from atlas_forge.core.diff import diff_elements, diff_structure
from atlas_forge.db import (
    Session,
    db_get_document_by_id,
    db_get_document_by_notion_id,
    db_get_document_element_by_id,
    db_get_element_hash_by_id,
    db_get_latest_content_for_element,
    db_get_snapshot_by_id,
    db_set_snapshot_pending,
)
from atlas_forge.models.api_models import (
    DocumentReference,
    DocumentUpdate,
    DocumentUpdateResponse,
    NewDocument,
    NewDocumentResponse,
    NewNotionDocument,
)
from atlas_forge.models.db_models import (
    Document,
    DocumentElement,
    DocumentElementContent,
    DocumentElementMetadata,
)
from atlas_forge.worker import app

logger = logging.getLogger(__name__)
logger.setLevel(get_settings().log_level)


@app.task
def sync_from_notion(snapshot_id: uuid.UUID, notion_token: str | None = None):
    """Synchronize document content from Notion and process changes.
    
    This is the main task that orchestrates the complete document sync workflow:
    1. Fetches document content from Notion API using recursive traversal
    2. Creates/updates document elements with proper version tracking
    3. Generates hierarchical document structure representation of the new version
    4. Triggers diff processing for content and structure changes (separate tasks)
    5. Handles errors and retries for API reliability
    
    Args:
        snapshot_id: UUID string of the snapshot to process and link results
        notion_token: Optional Notion API token (uses config if not provided)
        
    Raises:
        ValueError: If snapshot not found or invalid
        APIResponseError: If Notion API calls fail
        Exception: For other processing errors
    """
    if not notion_token:
        notion_token = get_settings().notion_token
    
    if not notion_token:
        error_msg = "No Notion token provided and none found in configuration"
        logger.error(error_msg)
        raise ValueError(error_msg)

    logger.info(f"Starting Notion sync for snapshot: {snapshot_id}")

    notion = Client(auth=notion_token)
    snapshot = db_get_snapshot_by_id(snapshot_id)

    if not snapshot:
        error_msg = f"Snapshot {snapshot_id} not found"
        logger.error(error_msg)
        raise ValueError(error_msg)

    db_set_snapshot_pending(snapshot_id)
    notion_page_id = snapshot.reference_id
    snapshot_timestamp = datetime.datetime.now()

    def extract_text_from_rich_text(rich_text_array: list[dict]) -> tuple[str, str]:
        """Helper function to extract plain and formatted text from Notion rich text array."""         
        plain_text = "".join([
            item.get("plain_text", "") for item in rich_text_array
        ])
        
        formatted_text = "".join([
            item.get("text", {}).get("content", "") 
            for item in rich_text_array 
            if item.get("text")
        ])
        
        return plain_text, formatted_text

    def dfs_notion_tree(
        block_id: uuid.UUID, session: Session, depth: int = 0, position: int = 0
    ) -> list[tuple[DocumentElementMetadata, DocumentElementContent]]:
        """Recursively traverse Notion block tree and create document elements.
        
        Performs depth-first traversal of Notion blocks, creating DocumentElement
        records and tracking content changes through hash-based version comparison.
        This function handles the core normalization logic.
        
        Args:
            block_id: Notion block/page ID to process
            session: Database session for transactions
            depth: Current nesting level (0 = root)
            position: Starting position counter for this level
            
        Returns:
            Tuple of (document_structure, changed_elements)
            
        Raises:
            APIResponseError: If Notion API call fails
            Exception: For other processing errors
        """
        nonlocal document_id
        nonlocal notion
        # structure for meta diff
        document_structure = []
        changed_elems = []
        try:
            children = notion.blocks.children.list(block_id)["results"]
            logger.debug(f"Found {len(children)} children for block {block_id}")

            for child in children:
                # create a document element at the right level in the structure
                # generate hash and compare with previous hash, only store/add content if changed
                create_new = False
                child_id = child["id"]
                child_type = child["type"]

                # Extract text content based on block type
                type_content = child.get(child_type, {})
                rich_text = type_content.get("rich_text", [])

                # TODO handle edge cases in notion structure

                raw_text, formatted_text = extract_text_from_rich_text(rich_text)

                h = blake2b()
                h.update(raw_text.encode(encoding="UTF-8"))
                element_hash = h.hexdigest()

                old_element = db_get_document_element_by_id(child_id)

                if not old_element:
                    # new element
                    element = DocumentElement(
                        id=child_id, element_type=child_type, document_id=document_id
                    )

                    # initial metadata
                    element_metadata = DocumentElementMetadata(
                        document_element_id=child_id,
                        version=snapshot_timestamp,
                        level=depth,
                        parent_element=block_id if depth > 0 else None,
                        position=position,
                    )

                    # initial content
                    element_content = DocumentElementContent(
                        document_element_id=child_id,
                        version=snapshot_timestamp,
                        content_raw=raw_text,
                        hash_raw=element_hash,
                        content_formatted=formatted_text
                    )

                    session.add(element)
                    session.add(element_metadata)
                    session.add(element_content)
                    
                elif element_hash != old_element.latest_content_hash:
                    # element content changed, hence store new version
                    element_content = DocumentElementContent(
                        document_element_id=child_id,
                        version=snapshot_timestamp,
                        content_raw=raw_text,
                        hash_raw=element_hash,
                        content_formatted=formatted_text
                    )
                    session.add(element_content)
                    changed_elems.append(element_content)

                    # TODO recheck if we need to update metadata as well?

                position = position + 1
                my_children = []
                if child["has_children"]:
                    # add children below current node
                    my_children, changed_children = dfs_notion_tree(
                        child_id, session, depth + 1, position
                    )
                    # consider all children for adjusting next child position
                    position = position + len(my_children)
                    changed_elems.extend(changed_children)

                document_structure.append({child_id: my_children})

            return (document_structure, changed_elems)

        except APIResponseError as e:
            logger.exception(e)
            # TODO handle error cases
            raise
        except Exception as e:
            logger.error(f"Unexpected error processing block {block_id}: {e}")
            raise

    try:
        page = notion.pages.retrieve(notion_page_id)

        root_document = db_get_document_by_notion_id(notion_page_id)
        is_update = bool(root_document)

        if root_document:
            logger.info(f"update document with id {root_document.id}")
            root_document.updated_at = snapshot_timestamp
        else:
            logger.info("new document found. Creating new entry")
            root_document = Document(
                reference_id=notion_page_id,
                url=page["url"],
                title=page["properties"]["title"]["title"][0]["plain_text"],
                document_type="notion_page",
                is_active=True,
            )

        with Session() as session:
            session.add(root_document)
            session.flush() # Get the document ID without committing

            document_id = root_document.id
            logger.info(f"Processing document {document_id}")

            # recursively build the document structure
            document_structure, changed_elems = dfs_notion_tree(notion_page_id, session)

            snapshot.document_id = document_id
            snapshot.document_structure = json.dumps(document_structure)
            snapshot.changed_elements = json.dumps(
                [str(e.document_element_id) for e in changed_elems]
            )
            snapshot.executed_at = snapshot_timestamp
            snapshot.status = "done" if not changed_elems or not is_update else "processing_diffs"

            session.add(snapshot)
            session.commit()

            # calculate the diffs in other tasks
            if is_update:
                group(
                    [
                        diff_structure.subtask((snapshot_id, document_structure)),
                        diff_elements.subtask((snapshot_id,)),
                    ]
                ).apply_async()

        return (document_structure, snapshot_timestamp)
    except APIResponseError as e:
        logger.error(f"Notion API error for snapshot {snapshot_id}: {e}")
        raise
            
    except Exception as e:
        logger.error(f"Unexpected error processing snapshot {snapshot_id}: {e}")
        logger.exception("Full error traceback:")
        
        # Update snapshot with error status
        try:
            snapshot.status = "error"
            snapshot.error = f"Processing failed: {str(e)}"
            snapshot.executed_at = snapshot_timestamp
            
            with Session() as session:
                session.merge(snapshot)
                session.commit()
        except Exception as update_error:
            logger.error(f"Failed to update snapshot error status: {update_error}")
            
        raise
