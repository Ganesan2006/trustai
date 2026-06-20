# processors/supabase_storage.py
import os
import logging
from supabase import create_client, Client
from typing import Tuple
import uuid

logger = logging.getLogger(__name__)

# Environment variables
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
SUPABASE_BUCKET = os.getenv("SUPABASE_BUCKET", "turstai")  # ← default to your bucket

if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set")

# Initialize client
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

def upload_file_to_supabase(file_bytes: bytes, file_name: str, content_type: str = None) -> Tuple[str, str]:
    """
    Upload file to Supabase Storage.
    Returns (file_key, public_url).
    """
    # Generate unique key
    unique_id = str(uuid.uuid4())
    file_key = f"files/{unique_id}_{file_name}"
    
    try:
        res = supabase.storage.from_(SUPABASE_BUCKET).upload(
            file_key,
            file_bytes,
            file_options={"content-type": content_type or "application/octet-stream"}
        )
        if hasattr(res, 'error') and res.error:
            raise Exception(f"Upload failed: {res.error.message}")
        logger.info(f"Uploaded {file_name} to Supabase bucket '{SUPABASE_BUCKET}'")
    except Exception as e:
        logger.error(f"Upload error: {e}")
        raise
    
    # Get public URL
    public_url = supabase.storage.from_(SUPABASE_BUCKET).get_public_url(file_key)
    return file_key, public_url

def download_file_from_supabase(file_key: str) -> bytes:
    """Download file from Supabase Storage by its key."""
    try:
        res = supabase.storage.from_(SUPABASE_BUCKET).download(file_key)
        if hasattr(res, 'error') and res.error:
            raise FileNotFoundError(f"File '{file_key}' not found: {res.error.message}")
        return res
    except Exception as e:
        logger.error(f"Download error: {e}")
        raise

def delete_file_from_supabase(file_key: str):
    """Delete file from Supabase Storage by its key."""
    try:
        res = supabase.storage.from_(SUPABASE_BUCKET).remove([file_key])
        if hasattr(res, 'error') and res.error:
            logger.warning(f"Failed to delete '{file_key}': {res.error.message}")
        else:
            logger.info(f"Deleted '{file_key}'")
    except Exception as e:
        logger.error(f"Deletion error: {e}")

def get_public_url(file_key: str) -> str:
    """Get public URL for a file key."""
    return supabase.storage.from_(SUPABASE_BUCKET).get_public_url(file_key)