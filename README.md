# Setup

psql -U postgres -a -f scripts/setup_db.sql
python scripts/setup_db.py

# Questions / Observations

1. The schema to be used as normalization target depends greatly on the target use cases. (Is formatting relevant? Is reverse-transformation required? Is comparison between different documents needed or only between versions of the same document?) E.g., for versioning only, normalization doesn't really improve things.
2. docling

render vs railway

curl -X POST localhost:8000/v1/atlas-forge/documents -H'Content-Type: application/json' -d '{"refence_id":"22a11ec686cc8053b861c56c0cd8f90e", "notion_token":"ntn_F48112944128Gtu4wJ3tGVD4RSU6wQzoBwqOVBh9tdkgDY"}'


# Assumptions

- 1 Notion page represents exactly 1 Atlas document
- Diffing or editing is required at (notion) block level
- Complete history of edits required