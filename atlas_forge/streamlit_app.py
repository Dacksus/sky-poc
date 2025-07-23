# streamlit_app.py
"""
Atlas Forge - Basic Diff Visualization UI

A simple Streamlit interface for visualizing document diffs and snapshots.
Run with: streamlit run streamlit_app.py
"""

import streamlit as st
import requests
import json
import sys
from pathlib import Path
from datetime import datetime
import time
import pandas as pd
import os

# Add project root to path for imports
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# Configure Streamlit page
st.set_page_config(
    page_title="Atlas Forge - Document Diff Viewer",
    page_icon="",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Configuration
API_BASE_URL = os.environ.get("API_BASE_URL", "http://localhost:8000/v1/forge")
CELERY_FLOWER_URL = "http://localhost:5555"

def main():
    st.title("Atlas Forge - Document Versioning")
    st.markdown("*Visualize document changes and diffs from Notion*")
    
    # Sidebar for controls
    with st.sidebar:
        st.header("Controls")
        
        # API Status Check
        api_status = check_api_status()
        # if api_status:
        #     st.success("API Connected")
        # else:
        #     st.error("API Disconnected")
        #     st.markdown("Make sure FastAPI is running at `localhost:8000`")
        
        # st.markdown("---")
        
        # Create new snapshot section
        st.subheader("Create New Snapshot")
        
        notion_page_id = st.text_input(
            "Notion Page ID",
            placeholder="Enter Notion page ID...",
            help="The ID from your Notion page URL",
            value="22a11ec686cc8053b861c56c0cd8f90e"
        )
        
        notion_token = st.text_input(
            "Notion Token (optional)",
            type="password",
            help="Leave empty to use configured token"
        )
        
        if st.button("Create Snapshot", type="primary"):
            if notion_page_id:
                create_snapshot(notion_page_id, notion_token)
            else:
                st.error("Please enter a Notion page ID")
        
        st.markdown("---")
        
        # Quick actions
        st.subheader("Quick Actions")
        if st.button("Refresh Data"):
            st.rerun()
        
        if st.button("Open Celery Monitor"):
            st.markdown(f"[Open Flower Dashboard]({CELERY_FLOWER_URL})")
    
    # Main content area
    col1, col2 = st.columns([1, 1])
    
    with col1:
        st.header("Recent Snapshots")
        display_snapshots()
    
    with col2:
        st.header("Diff Viewer")
        display_diff_viewer()

def check_api_status():
    """Check if the Atlas Forge API is running"""
    try:
        response = requests.get(f"{API_BASE_URL[:-11]}/health", timeout=5)
        return response.status_code == 200
    except:
        return False

def create_snapshot(page_id: str, token: str = None):
    """Create a new document snapshot"""
    try:
        payload = {"reference_id": page_id}
        if token:
            payload["notion_token"] = token
        
        with st.spinner("Creating snapshot..."):
            response = requests.post(
                f"{API_BASE_URL}/documents",
                json=payload,
                timeout=10
            )
        
        if response.status_code == 200:
            result = response.json()
            snapshot_id = result["result_id"]
            
            st.success(f"Snapshot created: `{snapshot_id}`")
            
            # Auto-refresh to show new snapshot
            time.sleep(3)
            st.rerun()
            
        else:
            st.error(f"Failed to create snapshot: {response.text}")
            
    except Exception as e:
        st.error(f"Error creating snapshot: {str(e)}")

def display_snapshots():
    """Display recent snapshots with status"""
    
    # Mock data for demo - replace with actual API call
    response = requests.get(
                f"{API_BASE_URL}/documents/snapshot",
                timeout=10
            )
    
    if not response:
        st.info("No snapshots found. Create one using the sidebar!")
        return
    
    # Display snapshots as cards
    for item in response.json():
        snapshot_id = item["result_id"]
        snapshot = get_snapshot_diff(snapshot_id)
        snapshot["id"] = snapshot_id

        with st.container():
            st.markdown("---")
            
            # Status badge
            status_color = {
                "done": ":green",
                "processing_diffs": ":orange", 
                "pending": ":orange",
                "error": ":red",
                "open": ":blue"
            }.get(snapshot["status"], "")
            
            st.markdown(f"**{status_color}[{snapshot['title']}]**")
            
            col1, col2, col3 = st.columns([3,2,1])
            with col2:
                st.metric("Status", snapshot["status"])
            with col3:
                changes = "N/A"
                try:
                    structure_changes = len(json.loads(json.loads(snapshot.get("document_structure_diff")).get("raw_diff")))
                    content_changes = len(json.loads(snapshot.get("changed_elements")))
                    changes = f"{structure_changes}/{content_changes}"
                except KeyError as e:
                    pass
                except TypeError as e:
                    pass
                st.metric("Changes (structure/content)", changes)
            with col1:
                st.metric("Created", datetime.fromisoformat(snapshot.get("executed_at", "N/A")).strftime('%a %d %b %Y, %I:%M%p'))
            
            # Action buttons
            col1, col2, _ = st.columns([1,1,4])
            with col1:
                if st.button(f"View Diff", key=f"view_{snapshot_id}"):
                    st.session_state.selected_snapshot = snapshot_id
                    st.rerun()
            
            with col2:
                if st.button(f"Details", key=f"details_{snapshot_id}"):
                    show_snapshot_details(snapshot)

def display_diff_viewer():
    """Display diff results for selected snapshot"""
    
    if "selected_snapshot" not in st.session_state:
        st.info("Select a snapshot from the left to view diffs")
        return
    
    snapshot_id = st.session_state.selected_snapshot
    
    # Fetch snapshot data
    diff_data = get_snapshot_diff(snapshot_id)
    
    if not diff_data:
        st.error("Could not load diff data")
        return
    
    # Tabs for different diff views
    tab1, tab2, tab3 = st.tabs(["Content Changes", "Structure Changes", "Summary"])
    
    with tab1:
        display_content_diffs(diff_data)
    
    with tab2:
        display_structure_diffs(diff_data)
    
    with tab3:
        display_diff_summary(diff_data)

def display_content_diffs(diff_data):
    """Display content diffs for changed elements"""
    
    changed_diffs = diff_data.get("changed_elements_diff")
    if not changed_diffs:
        st.info("No content changes detected")
        return
    
    try:
        diffs = json.loads(changed_diffs) if isinstance(changed_diffs, str) else changed_diffs
        
        if not diffs:
            st.info("No content changes detected")
            return
        
        st.subheader(f"{len(diffs)} Elements Changed")
        
        for element_id, diff_text in diffs.items():
            with st.expander(f"Element: {element_id[:8]}..."):
                if diff_text and diff_text != "New element - no previous version to compare":
                    # Display unified diff with syntax highlighting
                    st.code(diff_text, language="diff")
                else:
                    st.info("New element - no previous version to compare")
    
    except json.JSONDecodeError:
        st.error("Could not parse diff data")
    except Exception as e:
        st.error(f"Error displaying diffs: {e}")

def display_structure_diffs(diff_data):
    """Display structure diffs"""
    
    structure_diff = diff_data.get("document_structure_diff")
    if not structure_diff:
        st.info("No structure changes detected")
        return
    
    try:
        diff = json.loads(structure_diff) if isinstance(structure_diff, str) else structure_diff
        
        if diff.get("diff_type") == "first_snapshot":
            st.info("This is the first snapshot - no previous structure to compare")
            st.metric("Elements", diff.get("elements_count", 0))
            return
        
        # Display change summary
        if diff.get("raw_diff") and len(json.loads(diff.get("raw_diff"))) > 0:
            st.subheader("Structure Changes Detected")
            
            changes = parse_jsondiff_symmetric(diff.get("raw_diff"))
            if changes:
                for change in changes["added"]:
                    st.success(f"{change}")
                for change in changes["removed"]:
                    st.error(f"{change}")
                for change in changes["changed"]:
                    st.warning(f"{change}")
            
            # Show raw diff for technical users
            with st.expander("Raw Structure Diff"):
                st.json(diff.get("raw_diff", {}))
        else:
            st.success("No structure changes detected")
            
        # Metrics
        col1, col2 = st.columns(2)
        with col1:
            st.metric("Previous Elements", diff.get("old_elements_count", 0))
        with col2:
            st.metric("Current Elements", diff.get("new_elements_count", 0))
    
    except json.JSONDecodeError:
        st.error("Could not parse structure diff data")
    except Exception as e:
        st.error(f"Error displaying structure diff: {e}")

def display_diff_summary(diff_data):
    """Display summary of all changes"""
    
    st.subheader("Change Summary")
    
    # Extract metrics
    has_content_changes = bool(diff_data.get("changed_elements_diff"))
    has_structure_changes = bool(diff_data.get("document_structure_diff"))
    
    # Content changes count
    content_changes_count = 0
    if has_content_changes:
        try:
            diffs = json.loads(diff_data["changed_elements_diff"])
            content_changes_count = len(diffs)
        except:
            pass
    
    # Display metrics
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.metric(
            "Content Changes", 
            content_changes_count,
            delta=content_changes_count if content_changes_count > 0 else None
        )
    
    with col2:
        st.metric(
            "Structure Changes",
            "Yes" if has_structure_changes else "No",
            delta="Changed" if has_structure_changes else None
        )
    
    with col3:
        change_type = "Major" if (content_changes_count > 5 or has_structure_changes) else "Minor" if content_changes_count > 0 else "None"
        st.metric("Change Type", change_type)
    
@st.dialog("Snapshot details")
def show_snapshot_details(snapshot):
    """Show detailed snapshot information in a modal"""
    
    st.markdown("### Snapshot Details")
    
    details = {
        "ID": snapshot["id"],
        "Title": snapshot["title"],
        "Status": snapshot["status"],
        "Created": snapshot["executed_at"],
        "Reference ID": snapshot.get("reference_id", "N/A"),
    }
    
    for key, value in details.items():
        st.markdown(f"**{key}**: {value}")


def get_snapshot_diff(snapshot_id: str):
    """Get diff data for a snapshot - replace with actual API call"""
    
    try:
        response = requests.get(f"{API_BASE_URL}/documents/snapshot/{snapshot_id}")
        if response.status_code == 200:
            return response.json()
    except:
        pass
    
    # Mock diff data for demo
#     return {
#         "document_structure": json.dumps([
#             {"element-1": []},
#             {"element-2": [
#                 {"element-3": []},
#                 {"element-4": []}
#             ]}
#         ]),
#         "document_structure_diff": json.dumps({
#             "diff_type": "structure_comparison",
#             "old_elements_count": 3,
#             "new_elements_count": 4,
#             "has_changes": True,
#             "change_summary": ["Added element: element-4", "Modified element: element-2"],
#             "raw_diff": {"element-4": {"$insert": True}}
#         }),
#         "changed_elements": json.dumps(["element-2", "element-4"]),
#         "changed_elements_diff": json.dumps({
#             "element-2": """--- element-2@2024-01-20T09:00:00
# +++ element-2@2024-01-20T10:00:00
# @@ -1,2 +1,3 @@
#  This is the original content
# -Old line that was removed
# +New line that was added
# +Another new line""",
#             "element-4": "New element - no previous version to compare"
#         })
#     }


def parse_jsondiff_symmetric(diff_str: str) -> dict[str, list[str]]:
    """
    Parse jsondiff symmetric syntax output and categorize changes.
    
    Args:
        diff_str: String representation of jsondiff output in symmetric syntax
        
    Returns:
        Dictionary with 'added', 'removed', and 'changed' lists
    """
    try:
        diff_data = json.loads(diff_str) if isinstance(diff_str, str) else diff_str
    except json.JSONDecodeError:
        # Try to evaluate as Python literal if JSON parsing fails
        diff_data = eval(diff_str)
    
    changes = {
        'added': [],
        'removed': [],
        'changed': []
    }
    
    # Track all deletes and inserts for cross-hierarchy matching
    all_deletes = []  # [(path, idx, value), ...]
    all_inserts = []  # [(path, idx, value), ...]
    
    def collect_operations(data, path=""):
        """First pass: collect all insert/delete operations across hierarchy."""
        if isinstance(data, dict):
            # Check for insert/delete operations
            if '$insert' in data:
                for item in data['$insert']:
                    if isinstance(item, list) and len(item) == 2:
                        idx, val = item
                        all_inserts.append((path, idx, val))
                    else:
                        all_inserts.append((path, None, item))
            
            if '$delete' in data:
                for item in data['$delete']:
                    if isinstance(item, list) and len(item) == 2:
                        idx, val = item
                        all_deletes.append((path, idx, val))
                    else:
                        all_deletes.append((path, None, item))
            
            # Recurse into nested structures
            for key, value in data.items():
                if key.startswith('$'):
                    continue
                current_path = f"{path}.{key}" if path else key
                collect_operations(value, current_path)
        
        elif isinstance(data, list):
            for i, item in enumerate(data):
                collect_operations(item, f"{path}[{i}]")
    
    def process_diff(data, path=""):
        """Second pass: process changes, avoiding already matched operations."""
        if isinstance(data, dict):
            # Check if this dict represents a simple before/after change
            if len(data) == 2 and all(isinstance(k, int) for k in data.keys()):
                # This is a change (old_value, new_value)
                keys = sorted(data.keys())
                old_val = data[keys[0]]
                new_val = data[keys[1]]
                changes['changed'].append(f"{path}: {old_val} → {new_val}")
                return
            
            # Check for combined operations at this level
            has_insert = '$insert' in data
            has_delete = '$delete' in data
            
            if has_insert and has_delete:
                # Local move/change operations
                inserts = data['$insert']
                deletes = data['$delete']
                
                # If same number of inserts and deletes, likely a move/change
                if len(inserts) == len(deletes):
                    for delete_item, insert_item in zip(deletes, inserts):
                        if isinstance(delete_item, list) and isinstance(insert_item, list):
                            del_idx, del_val = delete_item
                            ins_idx, ins_val = insert_item
                            if del_idx != ins_idx:
                                changes['changed'].append(f"{path}[{del_idx}→{ins_idx}]: {del_val} moved to {ins_val}")
                            else:
                                changes['changed'].append(f"{path}[{del_idx}]: {del_val} → {ins_val}")
                        else:
                            changes['changed'].append(f"{path}: {delete_item} → {insert_item}")
            
            # Recurse into nested structures for other changes
            for key, value in data.items():
                if key.startswith('$'):
                    continue
                current_path = f"{path}.{key}" if path else key
                process_diff(value, current_path)
        
        elif isinstance(data, list):
            for i, item in enumerate(data):
                process_diff(item, f"{path}[{i}]")
    
    # First pass: collect all operations
    collect_operations(diff_data)
    
    # Match deletes and inserts across hierarchy levels
    matched_deletes = set()
    matched_inserts = set()
    
    for i, (del_path, del_idx, del_val) in enumerate(all_deletes):
        for j, (ins_path, ins_idx, ins_val) in enumerate(all_inserts):
            if i in matched_deletes or j in matched_inserts:
                continue
            
            # Check if values match (hierarchy move)
            if del_val == ins_val and del_path != ins_path:
                # This is a hierarchy change
                del_location = f"{del_path}[{del_idx}]" if del_idx is not None else del_path
                ins_location = f"{ins_path}[{ins_idx}]" if ins_idx is not None else ins_path
                changes['changed'].append(f"{del_location} → {ins_location}: {del_val} (hierarchy change)")
                matched_deletes.add(i)
                matched_inserts.add(j)
                break
    
    # Add unmatched operations as regular adds/removes
    for i, (del_path, del_idx, del_val) in enumerate(all_deletes):
        if i not in matched_deletes:
            location = f"{del_path}[{del_idx}]" if del_idx is not None else del_path
            changes['removed'].append(f"{location} = {del_val}")
    
    for j, (ins_path, ins_idx, ins_val) in enumerate(all_inserts):
        if j not in matched_inserts:
            location = f"{ins_path}[{ins_idx}]" if ins_idx is not None else ins_path
            changes['added'].append(f"{location} = {ins_val}")
    
    # Second pass: process other changes (non-insert/delete operations)
    process_diff(diff_data)
    
    return changes

# Custom CSS for better styling
def load_css():
    st.markdown("""
    <style>
    .stContainer > div {
        padding-top: 1rem;
    }
    
    .metric-container {
        background-color: #f0f2f6;
        padding: 1rem;
        border-radius: 0.5rem;
        margin: 0.5rem 0;
    }
    
    .diff-container {
        background-color: #fafafa;
        border-left: 4px solid #ff6b6b;
        padding: 1rem;
        margin: 1rem 0;
    }
    
    .success-diff {
        border-left-color: #51cf66;
    }
    
    .warning-diff {
        border-left-color: #ffd43b;
    }
    </style>
    """, unsafe_allow_html=True)

if __name__ == "__main__":
    load_css()
    main()

