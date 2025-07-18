# scripts/setup_db.py
#!/usr/bin/env python3
"""
Database initialization script for Atlas Forge
"""
import os
import sys
from pathlib import Path

# Add the project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from atlas_forge.db import (
    create_tables,
    create_triggers,
    drop_tables,
    verify_connection,
)


def main():
    print("🚀 Setting up Atlas Forge database...")

    verify_connection()
    drop_tables()
    create_tables()
    create_triggers()

    print("\n🎉 Database setup complete!")
    print("\nNext steps:")
    print("1. Configure .env file with proper database credentials")
    print("2. Configure .env file with Notion integration token")


if __name__ == "__main__":
    main()
