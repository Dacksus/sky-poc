"""Test script for Notion synchronization functionality.

This script automates the otherwise manual steps to verify e2e functionality.
"""

import sys
import os
from pathlib import Path
import asyncio
import uuid

# Add project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import logging
from atlas_forge.core.normalize import sync_from_notion
from atlas_forge.db import db_create_snapshot, db_get_snapshot_by_id
from atlas_forge.config import get_settings

logger = logging.getLogger(__name__)
logger.setLevel(get_settings().log_level)

def test_notion_sync(notion_page_id: str):
    """Test Notion synchronization with a specific page.
    
    Args:
        notion_page_id: Notion page ID to sync
    """
    logger.info(f"Testing Notion sync for page: {notion_page_id}")
    
    try:
        # Create a test snapshot
        snapshot_id = db_create_snapshot(notion_page_id)
        logger.info(f"Created test snapshot: {snapshot_id}")
        
        # Run sync task
        result = sync_from_notion(str(snapshot_id))
        logger.info(f"Sync completed: {result}")
        
        # Check results
        snapshot = db_get_snapshot_by_id(snapshot_id)
        if snapshot:
            logger.info(f"Snapshot status: {snapshot.status}")
            if snapshot.document_structure:
                logger.info("✓ Document structure captured")
            if snapshot.changed_elements:
                logger.info("✓ Changed elements detected")

        # TODO use notion client to change something on the page, run sync again and verify diffs
        
    except Exception as e:
        logger.error(f"Test failed: {e}")
        raise

def main():
    """Main test routine."""
    settings = get_settings()
    
    if not settings.notion_token:
        logger.error("NOTION_TOKEN not configured")
        sys.exit(1)
    
    # Example page ID - replace with actual test page
    test_page_id = "your-test-page-id-here"
    
    if len(sys.argv) > 1:
        test_page_id = sys.argv[1]
    
    if test_page_id == "your-test-page-id-here":
        logger.error("Please provide a valid Notion page ID")
        logger.info("Usage: python scripts/test_notion_sync.py <notion-page-id>")
        sys.exit(1)
    
    test_notion_sync(test_page_id)

    # TODO wait for user input to run again against changed page

if __name__ == "__main__":
    main()