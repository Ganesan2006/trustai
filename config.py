# config.py
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import validator
from typing import Optional
import urllib.parse
import dns.resolver

class Settings(BaseSettings):
    DATABASE_URL: str
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 10080
    
    QDRANT_URL: Optional[str] = None
    QDRANT_API: Optional[str] = None
    QDRANT_COLLECTION_PREFIX: str = "org_"
    
    OPENAI_API_KEY: Optional[str] = None
    OPENAI_BASE_URL: str = "https://api.osmapi.com/v1/"
    OPENAI_DEFAULT_MODEL: str = "gemma-4-26b-a4b-it"
    
    @validator("OPENAI_API_KEY", "QDRANT_API", pre=True)
    def strip_api_keys(cls, v):
        if isinstance(v, str):
            return v.strip()
        return v
    
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()

# Parse the DATABASE_URL to bypass OS DNS bugs for Neon hosts
db_url = settings.DATABASE_URL
connect_args = {}

try:
    if "neon.tech" in db_url:
        parsed = urllib.parse.urlparse(db_url)
        hostname = parsed.hostname
        if hostname:
            resolver = dns.resolver.Resolver()
            resolver.nameservers = ['8.8.8.8', '8.8.4.4']
            answers = resolver.resolve(hostname, 'A')
            ip_address = answers[0].to_text()
            # Pass the IP directly to psycopg2, avoiding OS DNS lookups, while preserving SNI
            connect_args["hostaddr"] = ip_address
            print(f"[DNS Patch] Successfully bypassed OS DNS: resolved {hostname} to {ip_address}")
except Exception as e:
    print(f"[DNS Patch Warning] Failed to resolve Neon host manually: {e}")

# Database setup - Optimized for parallel multi-user thread-based concurrency
engine = create_engine(
    db_url, 
    pool_pre_ping=True,
    pool_size=20,          # Allow 20 connections to remain open
    max_overflow=40,       # Allow up to 40 additional temporary connections during spikes
    pool_timeout=30,       # Wait up to 30 seconds for a connection to become available
    pool_recycle=1800,     # Recycle connections every 30 minutes to prevent stale/dropped Neon pooler errors
    connect_args=connect_args
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# To maintain backwards compatibility with existing imports temporarily
DATABASE_URL = settings.DATABASE_URL
SECRET_KEY = settings.SECRET_KEY
ALGORITHM = settings.ALGORITHM
ACCESS_TOKEN_EXPIRE_MINUTES = settings.ACCESS_TOKEN_EXPIRE_MINUTES
QDRANT_URL = settings.QDRANT_URL
QDRANT_API_KEY = settings.QDRANT_API
QDRANT_COLLECTION_PREFIX = settings.QDRANT_COLLECTION_PREFIX
OPENAI_API_KEY = settings.OPENAI_API_KEY
OPENAI_BASE_URL = settings.OPENAI_BASE_URL
OPENAI_DEFAULT_MODEL = settings.OPENAI_DEFAULT_MODEL

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()