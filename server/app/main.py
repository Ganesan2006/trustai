"""FastAPI application entry point."""
import asyncio
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from server.app.api.v1.router import router as v1_router
from server.app.middleware.org_resolver import OrgResolverMiddleware
from server.app.tasks import cleanup_orphaned_files

PROJECT_ROOT = Path(__file__).resolve().parents[2]
COMPONENTS_DIR = PROJECT_ROOT / "client" / "components"

app = FastAPI(title="RAG Chat API")


@app.on_event("startup")
async def startup_event() -> None:
    asyncio.create_task(cleanup_orphaned_files())


app.add_middleware(OrgResolverMiddleware)
app.mount("/static", StaticFiles(directory=COMPONENTS_DIR), name="static")
app.include_router(v1_router)
