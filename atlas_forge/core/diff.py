"""Basic diffing functionality for documents, handling content diffs and structure diffs separately"""

import difflib
import json
from collections import defaultdict
from typing import Any
from uuid import UUID

import jsondiff

from atlas_forge.db import (
    Session,
    db_get_document_by_id,
    db_get_latest_content_pair_by_id,
    db_get_latest_elements_by_document,
    db_get_previous_snapshot,
    db_get_snapshot_by_id,
)
from atlas_forge.models.db_models import (
    Document,
    DocumentElement,
    DocumentElementContent,
    DocumentElementMetadata,
    Snapshot,
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
        logger.warning(f"Document not found for ID: {document_id}")
        return None
    
    document_elements = db_get_latest_elements_by_document(document.id)
    
    if not document_elements:
        return {}
    
    # Build structure with content hashes
    structure = {}
    children_by_parent = defaultdict(list)
    element_info = {}
    
    # First pass: collect element information and parent-child relationships
    for element, metadata in document_elements:
        element_info[element.id] = {
            "content_hash": element.latest_content_hash or "no-content",
            "element_type": element.element_type,
            "level": metadata.level,
            "position": metadata.position
        }
        
        if metadata.parent_element:
            children_by_parent[metadata.parent_element].append(element.id)
    
    def build_versioned_structure(element_id: UUID) -> Dict[str, Any]:
        """Recursively build structure with version information."""
        info = element_info.get(element_id, {})
        children = children_by_parent.get(element_id, [])
        
        # Sort children by position for consistent ordering
        children.sort(key=lambda child_id: element_info.get(child_id, {}).get("position", 0))
        
        child_structure = {}
        for child_id in children:
            child_structure[str(child_id)] = build_versioned_structure(child_id)
        
        return {
            "content_hash": info.get("content_hash", ""),
            "element_type": info.get("element_type", "unknown"),
            "children": child_structure
        }
    
    # Build structure for root elements only
    root_elements = [element.id for element, metadata in document_elements 
                    if not metadata.parent_element]
    
    for root_id in root_elements:
        structure[str(root_id)] = build_versioned_structure(root_id)
    
    return structure

    # recursively resolve the document and build the structured dict TODO: store current version in db?


def generate_document_structure(document_id: UUID) -> list[dict[str, Any]]:
    """Generate hierarchical document structure representation.
    
    Creates a nested list structure representing the document hierarchy,
    where each element is a dict with element ID as key and children as value.
    Elements are ordered by their position within each level.
    
    Args:
        document_id: UUID of the document to process
        
    Returns:
        List of nested dictionaries representing document structure

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
    if not document_elements:
        logger.warning(f"No elements found for document {document_id}")
        return []

    children_by_parent = defaultdict(list)
    root_elements = []

    for element, metadata in document_elements:
        if metadata.parent_element:
            children_by_parent[metadata.parent_element].append(element.id)
        else:
            root_elements.append(element.id)

    def build_structure(element_ids: list[UUID]) -> list[dict[str, Any]]:
        # Recursively build nested structure from element IDs.
        structure = []
        for element_id in element_ids:
            children = children_by_parent.get(element_id, [])
            child_structure = build_structure(children) if children else []
            structure.append({str(element_id): child_structure})
        return structure

    return build_structure(root_elements)


@app.task
def diff_elements(snapshot_id: UUID):
    """Process content diffs for changed elements in a snapshot.
    
    Compares the latest two versions of each changed element and generates
    unified diff output showing exactly what content changed. This provides
    line-by-line comparison similar to git diff.
    
    Args:
        snapshot_id: UUID of the snapshot to process
        
    Raises:
        Exception: If snapshot not found or processing fails
    """
    logger.info(
        f"==========\nrunning element diff for snapshot: {snapshot_id}\n=========="
    )
    snapshot = db_get_snapshot_by_id(snapshot_id)
    if not snapshot:
        logger.error(f"Snapshot {snapshot_id} not found")
        raise ValueError(f"Snapshot {snapshot_id} not found")

    try:
        changed_elements = json.loads(snapshot.changed_elements)
        summary_diff = {}

        logger.info(f"Processing {len(changed_elements)} changed elements")

        for element_id in changed_elements:
            contents = db_get_latest_content_pair_by_id(element_id)
            if len(contents) < 2:
                logger.debug(f"Supposedly changed element {element_id} has only {len(contents)} versions, skipping diff")
                continue

            new_content = contents[0] # most recent
            old_content = contents[1] # previous

            # Split content into lines for unified diff
            old_lines = old_content.content_raw.splitlines(keepends=True)
            new_lines = new_content.content_raw.splitlines(keepends=True)
            
            # Generate unified diff with proper headers
            diff_lines = list(difflib.unified_diff(
                old_lines, 
                new_lines,
                fromfile=f"element_{element_id}@{old_content.version.isoformat()}",
                tofile=f"element_{element_id}@{new_content.version.isoformat()}",
                lineterm=""
            ))
           
            summary_diff[element_id] = "\n".join(diff_lines)

        snapshot.changed_elements_diff = json.dumps(summary_diff)

        with Session() as session:
            session.add(snapshot)
            session.commit()

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse changed_elements JSON for snapshot {snapshot_id}: {e}")
        raise
    except Exception as e:
        logger.error(f"Error processing element diff for snapshot {snapshot_id}: {e}")
        
        # Update snapshot with error information
        try:
            snapshot.status = "error"
            snapshot.error = f"Element diff failed: {str(e)}"
            
            with Session() as session:
                session.add(snapshot)
                session.commit()
        except Exception as update_error:
            logger.error(f"Failed to update snapshot error status: {update_error}")
        
        raise


@app.task
def diff_structure(snapshot_id: UUID, new_structure: list[dict[str, Any]]):
    """Process structure diff between current and previous snapshot.
    
    Compares document structure between snapshots to identify hierarchy
    changes, element additions/removals, and position changes. Uses JSON
    diff to provide detailed structural change information.
    
    Args:
        snapshot_id: UUID of the current snapshot
        new_structure: Current document structure as generated by generate_document_structure
        
    Raises:
        Exception: If snapshot not found or processing fails
    """
    logger.info(
        f"==========\nrunning structure diff for snapshot: {snapshot_id}\n=========="
    )
    snapshot = db_get_snapshot_by_id(snapshot_id)
    if not snapshot:
        logger.error(f"Snapshot {snapshot_id} not found")
        raise ValueError(f"Snapshot {snapshot_id} not found")

    old_snapshot = db_get_previous_snapshot(snapshot_id)
    if not old_snapshot or not old_snapshot.document_structure:
        logger.warn(f"No previous snapshot found for comparison with {snapshot_id}")
    try:
        old_structure = json.loads(old_snapshot.document_structure)

        diff_result = jsondiff.diff(old_structure, new_structure, syntax="symmetric", dump=True)

        # Create a more readable diff summary
        diff_summary = {
            # "old_snapshot_id": str(old_snapshot.id),
            "old_elements_count": len(old_structure),
            "new_elements_count": len(new_structure),
            "raw_diff": diff_result
        }
        
        # # Add human-readable change summary
        # if isinstance(diff_result, dict):
        #     changes = []
        #     for key, value in diff_result.items():
        #         if key.startswith('$'):
        #             # jsondiff metadata
        #             continue
        #         elif isinstance(value, dict) and '$delete' in str(value):
        #             changes.append(f"Removed element: {key}")
        #         elif isinstance(value, dict) and '$insert' in str(value):
        #             changes.append(f"Added element: {key}")
        #         else:
        #             changes.append(f"Modified element: {key}")
        #             # TODO include element diff here or combine later?
            
        #     diff_summary["change_summary"] = changes

        snapshot.document_structure_diff = json.dumps(diff_summary, indent=2)

        with Session() as session:
            session.add(snapshot)
            session.commit()

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse document structure JSON: {e}")
        raise
    except Exception as e:
        logger.error(f"Error processing structure diff for snapshot {snapshot_id}: {e}")
        
        # Update snapshot with error information
        try:
            snapshot.status = "error"
            snapshot.error = f"Structure diff failed: {str(e)}"
            
            with Session() as session:
                session.add(snapshot)
                session.commit()
        except Exception as update_error:
            logger.error(f"Failed to update snapshot error status: {update_error}")
        
        raise
