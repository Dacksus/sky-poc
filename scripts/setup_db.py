# scripts/setup_db.py
#!/usr/bin/env python3
"""
Database initialization script for Atlas Chronicles
"""
import sys
import os
from pathlib import Path

# Add the project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.db import engine, Base
from app.models import Document, DocumentVersion, DocumentVersionDiff
from app.config import get_settings

def create_tables():
    """Create all database tables"""
    print("Creating database tables...")
    Base.metadata.create_all(bind=engine)
    print("✓ Tables created successfully")

def verify_connection():
    """Verify database connection"""
    try:
        settings = get_settings()
        print(f"Connecting to database: {settings.database_url}")
        
        with engine.connect() as conn:
            result = conn.execute("SELECT 1")
            print("✓ Database connection successful")
            
    except Exception as e:
        print(f"✗ Database connection failed: {e}")
        sys.exit(1)

def main():
    print("🚀 Setting up Atlas Chronicles database...")
    
    # Verify connection first
    verify_connection()
    
    # Create tables
    create_tables()
    
    print("\n🎉 Database setup complete!")
    print("\nNext steps:")
    print("1. Configure .env file with proper database credentials")
    print("2. Configure .env file with Notion integration token")
    # print("3. Run: alembic revision --autogenerate -m 'Initial migration'")
    # print("4. Run: alembic upgrade head")

if __name__ == "__main__":
    main()