"""Functions for normalizing external content for further processing"""
import datetime
import json
import logging
import uuid

from celery import group
from hashlib import blake2b
from notion_client import Client, APIResponseError

from atlas_forge.config import get_settings
from atlas_forge.core.diff import diff_elements, diff_structure
from atlas_forge.db import (
    db_get_document_by_id,
    db_get_document_by_notion_id,
    db_get_document_element_by_id,
    db_get_element_hash_by_id,
    db_get_latest_content_for_element,
    db_get_snapshot_by_id,
    db_set_snapshot_pending,
    Session
)
from atlas_forge.models.api_models import (
    DocumentReference,
    DocumentUpdate,
    DocumentUpdateResponse,
    NewDocument,
    NewDocumentResponse,
    NewNotionDocument   
)
from atlas_forge.models.db_models import (
    Document,
    DocumentElement,
    DocumentElementContent,
    DocumentElementMetadata
)
from atlas_forge.worker import app

logger = logging.getLogger(__name__)
logger.setLevel(get_settings().log_level)

@app.task
def sync_from_notion(snapshot_id: str, notion_token: str = get_settings().notion_token):
    logger.warn(notion_token)
    notion_token = get_settings().notion_token
    logger.warn(notion_token)
    notion = Client(auth=notion_token)
    snapshot = db_get_snapshot_by_id(snapshot_id)
    db_set_snapshot_pending(snapshot_id)
    notion_page_id = snapshot.reference_id
    snapshot_timestamp = datetime.datetime.now()
    
    def dfs_notion_tree(block_id: uuid.UUID, session: Session, depth: int = 0, position: int = 0) -> list[tuple[DocumentElementMetadata, DocumentElementContent]]:
        """Recursively creates a structural json representation of the document and a list of all changed elements within that representation""" 
        nonlocal document_id
        nonlocal notion
        # structure for meta diff
        document_structure = []
        changed_elems = []
        try:
            children = notion.blocks.children.list(block_id)["results"]
            for child in children:
                # create a document element at the right level in the structure
                # generate hash and compare with previous hash, only store/add content if changed
                create_new = False
                child_id = child["id"]

                raw_text = "".join([item["plain_text"] for item in child[child["type"]]["rich_text"]])

                h = blake2b()
                h.update(raw_text.encode(encoding='UTF-8'))
                element_hash = h.hexdigest()
                old_element = db_get_document_element_by_id(child_id)
                
                if not old_element:
                    # new element
                    element = DocumentElement(
                        id=child_id,
                        element_type=child["type"],
                        document_id=document_id
                    )
                    # new metadata
                    element_metadata = DocumentElementMetadata(
                        document_element_id=child_id,
                        version=snapshot_timestamp,
                        level=depth,
                        parent_element=block_id if depth > 0 else None,
                        position=position
                    )
                    element_content = DocumentElementContent(
                        document_element_id=child_id,
                        version=snapshot_timestamp,
                        content_raw=raw_text,
                        hash_raw=element_hash,
                        content_formatted="".join([item["text"]["content"] for item in child[child["type"]]["rich_text"]])
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
                        content_formatted="".join([item["text"]["content"] for item in child[child["type"]]["rich_text"]])
                    )
                    session.add(element_content)
                    changed_elems.append(element_content)

                position = position + 1
                my_children = []
                if child["has_children"]:
                    # add children below current node
                    my_children, changed_children = dfs_notion_tree(child_id, session, depth+1, position)
                    # consider all children for adjusting next child position
                    position = position + len(my_children)
                    changed_elems.extend(changed_children)

                document_structure.append({child_id: my_children})  

            return (document_structure, changed_elems)

        except APIResponseError as e:
            logger.exception(e)

    page = notion.pages.retrieve(notion_page_id)

    root_document = db_get_document_by_notion_id(notion_page_id)
    is_update = False
    if root_document:
        logger.info(f"update document with id {root_document.id}")
        root_document.updated_at = snapshot_timestamp
        is_update = True
    else:
        logger.info("new document found. Creating new entry")
        root_document = Document(
            reference_id=notion_page_id,
            url=page["url"],
            title=page["properties"]["title"]["title"][0]["plain_text"],
            document_type="test",
            is_active=True,
        )

    with Session() as session:
        session.add(root_document)
        session.flush()

        document_id = root_document.id
        # recursively build the document structure
        document_structure, changed_elems = dfs_notion_tree(notion_page_id, session)

        snapshot.document_id = document_id
        snapshot.document_structure = json.dumps(document_structure)
        snapshot.changed_elements = json.dumps([e.document_element_id for e in changed_elems])
        snapshot.executed_at = snapshot_timestamp

        session.add(snapshot)
        session.commit()

        # calculate the diffs in other tasks
        if is_update:
            group([
                diff_structure.subtask((snapshot_id, document_structure)),
                diff_elements.subtask((snapshot_id,))
            ]).apply_async()
            


    return (document_structure, snapshot_timestamp)