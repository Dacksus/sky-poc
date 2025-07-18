# Atlas Forge

**Atlas Forge** is a (poc of a) document versioning service that provides automated snapshots and change tracking for documents from external sources like Notion. It captures document structure and content changes over time, enabling detailed diff analysis at both structural and content levels.

LIVE DEMO DEPLOYMENT: https://sky-poc.onrender.com/v1/forge/docs (bring your own notion key)

Demo steps:
1. Setup a notion integration for the target workspace (see below for rerence)
2. Go to https://sky-poc.onrender.com/v1/forge/docs#/documents/create_new_document_v1_forge_documents_post
3. Paste the page id of the notion page to track as 'reference_id' and the token of step 1 as 'notion_token' and execute the API call
4. Do some changes on the notion page
5. Execute the call of step 3 again -> copy the result_id
6. Open the /v1/forge/documentssnapshot/{snapshot_id} endpoint and paste the result_id as snapshot_id
7. The result includes a hierarchic representation of the document, changes of the structure between the latest 2 snapshots, all blocks that changed content-wise and a detailed gitdiff-like description of what hanged in each element. See models/api_models.py and core/diff.py for more explanation. 

## Features

- **Document Snapshots**: Automated capturing of document versions via API call or notion webhooks
- **Granular Diffing**: Track changes at block/element level  
- **Structure Tracking**: Monitor document hierarchy changes
- **Async Processing**: Background tasks via Celery
- **Version History**: Complete audit trail of all changes

## Architecture

Core application logic is strictly separated from the API gateway for robustness and scalability.
Diffing and normalization Workflows are independent, database-centric and stateless, i.e., any needed intermediate results are stored in the database and every task could be (re)run at any time.

Stack:
- FastAPI to serve RESTful API
- PostgreSQL as application database and redis result backend
- Celery to run normalization and diffing tasks
- Redis for task queue

-- TODO create actual architecture diagram

```
┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│   FastAPI   │───▶│ PostgreSQL  │───▶│   Celery    │
│     API     │    │  Database   │    │   Workers   │
└─────────────┘    └─────────────┘    └─────────────┘
       │                    │                 │      
       ▼                    ▼                 ▼      
┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│   Notion    │    │  Triggers   │    │    Redis    │
│     API     │    │ & Functions │    │   Broker    │
└─────────────┘    └─────────────┘    └─────────────┘
```

## Quick Start

### Docker Setup (Recommended)

```bash
# Start all services
docker compose up -d

# View logs
docker compose logs -f

# Run database setup (first time only)
docker compose --profile setup run --rm db-setup
```

Services will be available at:
- **API**: http://localhost:8000/v1/forge/documents
- **API Docs**: http://localhost:8000/v1/forge/docs (use this for easy interaction with the API)
- **Celery Flower**: http://localhost:5555
- **PgAdmin**: http://localhost:5050 (admin@atlas.com / admin)

### Native Setup

Prerequisites: PostgreSQL and Redis running locally

```bash
# Install dependencies
poetry install

# Start API server
cd atlas_forge
poetry run uvicorn atlas_forge:api --host 0.0.0.0 --port 8000 --reload

# Start Celery worker (in project root)
poetry run celery -A atlas_forge.worker worker -l info --concurrency 2
```

### Notion Setup

A notion integration token is needed for all workspaces and (and pages) that are supposed to be versioned.
See [Notion's documentation](https://www.notion.com/help/create-integrations-with-the-notion-api#create-an-internal-integration) for details about setting up integrations.


## Configuration

Create a `.env` file:

```bash
# Database
DATABASE_URL=postgresql+psycopg://atlas_user:atlas_password@localhost:5432/atlas_forge

# Celery/Redis  
CELERY_BROKER_URL=redis://localhost:6379
CELERY_RESULT_BACKEND=db+postgresql+psycopg://atlas_user:atlas_password@localhost:5432/atlas_forge

# Notion Integration
NOTION_TOKEN=your_notion_token_here

# Application (optional)
DEBUG=true
LOG_LEVEL=INFO
APP_NAME=Atlas Forge
```

For Docker, use internal service names, e.g.:
```bash
DATABASE_URL=postgresql+psycopg://atlas_user:atlas_password@postgres:5432/atlas_forge
```

## API Usage

### Create Document Snapshot

```bash
curl -X POST http://localhost:8000/v1/forge/documents \
  -H "Content-Type: application/json" \
  -d '{
    "reference_id": "notion-page-id-here",
    "notion_token": "optional-notion-token"
  }'
```

Response:
```json
{
  "result_id": "snapshot-uuid"
}
```

### Get Snapshot Results

```bash
curl http://localhost:8000/v1/forge/documents/snapshot/{snapshot_id}
```

Response includes:
- `document_structure`: Current document hierarchy
- `document_structure_diff`: Changes to document structure as of the last snapshot
- `changed_elements`: List of modified elements
- `changed_elements_diff`: Content changes per element

### Check Snapshot Status

```bash
curl http://localhost:8000/v1/forge/documents/snapshot/{snapshot_id}/status
```

Response includes processing status, timing, and error information.

## Development

### Project Structure

```
atlas_forge/
├── __init__.py             # FastAPI app initialization
├── config.py               # Configuration management  
├── db.py                   # Database setup and utilities
├── worker.py               # Celery worker configuration
├── models/
│   ├── __init__.py 
│   ├── db_models.py        # SQLAlchemy models
│   └── api_models.py       # Pydantic API models
├── core/
│   ├── __init__.py 
│   ├── normalize.py        # Document normalization logic
│   └── diff.py             # Diffing algorithms
└── routes/public/
│   ├── __init__.py 
    └── documents.py        # Document API endpoints
```

### Database Schema

The schema uses a versioned approach where: (TODO ERM)
- **Elements** store static information (type, document reference)
- **Metadata versions** track structural changes per element (position, hierarchy)
- **Content versions** track actual content changes per element
- **Triggers** automatically maintain latest version pointers

### Key Design Decisions

#### Assumptions
- 1 Notion page = 1 Atlas document
- Diffing/editing required at Notion block level  
- Complete edit history preservation required
- What tasks a snapshot triggers should probably be configurable in the future

#### Normalization Strategy
The normalization target schema supports multiple use cases:
- **Formatting preservation**: Via `content_formatted` field
- **Reverse transformation**: Via `content_raw` storage
- **Cross-document comparison**: Through normalized structure
- **Version-only tracking**: Structure aids diff performance

#### Versioning Approach
- **DateTime-based versions**: More intuitive than sequential numbers but can be used similarly programmatically
- **Automatic triggers**: Better performance and less error-prone than programmatical version management
- **Separate content/metadata**: Allows independent versioning of structure vs content
- **Hash-based change detection**: Avoid unnecessary version creation and loading of large content blobs

### Adding New Sources

To add support for new document sources:

1. **Create normalization function** in `core/normalize.py`:
```python
@app.task
def sync_from_google_docs(snapshot_id: str, credentials: dict):
    # Implement Google Docs API integration
    pass
```

2. **Map to standard structure**:
```python
# Convert source-specific format to DocumentElement structure
element = DocumentElement(
    id=source_element_id,
    element_type=normalized_type,
    document_id=document_id
)
```

3. **Add API endpoints** in `routes/`:
```python
@router.post("/google-docs")
def create_google_docs_snapshot(request: GoogleDocsReference):
    # Handle Google Docs specific parameters
    pass
```

<!-- ### Running Tests

```bash
# Install test dependencies
poetry install --with dev

# Run tests
poetry run pytest

# Run with coverage
poetry run pytest --cov=atlas_forge
```

### Database Management

```bash
# Create/update database schema
python -c "from atlas_forge.db import initialize_database; initialize_database()"

# Reset database (careful!)
python -c "from atlas_forge.db import initialize_database; initialize_database(reset=True)"

# Validate triggers are working
python -c "from atlas_forge.db import validate_triggers; print(validate_triggers())"
```

## Production Deployment

### Docker Production

```bash
# Set production environment variables
export POSTGRES_PASSWORD=secure_production_password
export NOTION_TOKEN=production_notion_token

# Deploy with production settings
docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build 
```-->

### Monitoring

Key metrics to monitor:
- **Celery queue length**: Monitor Redis queue size
- **Processing time**: Track snapshot completion time
- **Error rates**: Monitor failed tasks and API errors
- **Database performance**: Watch for slow queries on version tables

### Scaling

- **Horizontal scaling**: Add more Celery workers
- **Database optimization**: Add indexes on frequently queried fields
- **Caching**: Consider Redis caching for frequently accessed snapshots

## Future Considerations

- If more diverse sources besides Notion should be integrated
 - consider frameworks like Docling if additional sources are meant to be integrated
 - it may be preferable to switch to "NoSQL" databases for highly variable document structures  
- UI/UX and scope of user-facing application needs to be fleshed out to decide for the best type of diff representation
- retention policies, i.e., automatic cleanup of old versions (easy with current structure)