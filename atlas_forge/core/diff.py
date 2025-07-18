"""Basic diffing functionality for documents, handling content diffs and structure diffs separately"""
import json
import jsondiff
import difflib

from typing import Any
from uuid import UUID

from collections import defaultdict

from atlas_forge.db import (
    db_get_document_by_id,
    db_get_latest_elements_by_document,
    db_get_latest_content_pair_by_id,
    db_get_previous_snapshot,
    db_get_snapshot_by_id,
    Session
)
from atlas_forge.models.db_models import (
    Document,
    DocumentElement,
    DocumentElementContent,
    DocumentElementMetadata,
    Snapshot
)

from atlas_forge.worker import app, logger

def generate_document_structure_versioned(document_id: str) -> dict[UUID, Any] | None:
    """
    Generates a simple json representation of the document's structure to quickly identify
    changes without having to look at the content.

    The struture is represented as a nested json dict, where the keys are the individual
    element ids and values are the element's content hashes.
    Order and nestedness map the actual structure.

    Example:

    {
        id1: {
            content_hash: hash1,
            children: {}
        },
        id2: {
            content_hash: hash2,
            children: {}
        },
        id3: {
            content_hash: hash3,
            children: {
                id4: {
                    content_hash: hash4,
                    children: {}
                },
                id5: {
                    content_hash: hash5,
                    children: {}
                }
            }
        },
        id6: {
            content_hash: hash6,
            children: {
                id7: {
                    content_hash: hash7,
                    children: {
                        id8: {
                            content_hash: hash8,
                            children: {}
                        }
                    }
                }
            }
        }
    }
    """
    document = db_get_document_by_notion_id(document_id)
    if not document:
        return None
    
    # recursively resolve the document and build the structured dict TODO: store current version in db?


def generate_document_structure(document_id: UUID) -> list[dict[str, Any]]:
    """
    
    Example:

    [
        {id1: []},
        {id2: []},
        {id3: [
            {id4: []},
            {id5: []}
        ]},
        {id6: [
            {id7: [
                {id8: []}
            ]}
        ]}
    ]
    """
    document_elements = db_get_latest_elements_by_document(document_id)
    children_by_parent = defaultdict(list)
    root_elements = []

    for element, metadata in document_elements:
        if metadata.parent_element:
            children_by_parent[metadata.parent_element].append(element.id)
        else:
            root_elements.append(element.id)
    
    def build_structure(element_ids: list[UUID]) -> list[dict[str, Any]]:
        structure = []
        for element_id in element_ids:
            children = children_by_parent.get(element_id, [])
            child_structure = build_structure(children) if children else []
            structure.append({str(element_id): child_structure})
        return structure
    
    return build_structure(root_elements)


@app.task
def diff_elements(snapshot_id: UUID):
    logger.info(f"==========\nrunning element diff for snapshot: {snapshot_id}\n==========")
    snapshot = db_get_snapshot_by_id(snapshot_id)
    changed_elements = json.loads(snapshot.changed_elements)
    summary_diff = {}
    for element_id in changed_elements:
        contents = db_get_latest_content_pair_by_id(element_id)
        new_content = contents[0]
        old_content = contents[1]
        diff = difflib.unified_diff(old_content.content_raw, new_content.content_raw)
        element_summary = []
        for d in diff:
            logger.debug(d)
            element_summary.append(d)
        summary_diff[element_id] = ''.join(element_summary)
    snapshot.changed_elements_diff = json.dumps(summary_diff)

    with Session() as session:
        session.add(snapshot)
        session.commit()

@app.task
def diff_structure(
    snapshot_id: UUID, 
    new_structure: list[dict[str, Any]]
):
    logger.info(f"==========\nrunning structure diff for snapshot: {snapshot_id}\n==========")
    snapshot = db_get_snapshot_by_id(snapshot_id)
    old_snapshot = db_get_previous_snapshot(snapshot_id)
    old_structure = json.loads(old_snapshot.document_structure)
    if not old_structure:
        logger.warn(f"Couldn't find an earlier snapshot to compare against for document_id {snapshot.document_id}")
        return
    diff = jsondiff.diff(old_structure, new_structure, dump=True)
    snapshot.document_structure_diff = diff

    with Session() as session:
        session.add(snapshot)
        session.commit()

