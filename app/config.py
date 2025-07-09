import os
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # Database
    database_url: str = "postgresql+psycopg://atlas:atlas@localhost:5432/atlas_chronicles"
    
    # Notion
    notion_token: str = ""
    
    # Application
    app_name: str = "Atlas Chronicles"
    debug: bool = True
    
    class Config:
        env_file = ".env"

def get_settings():
    return Settings()