# routers/pages.py
"""
Static page routes for the frontend application.
These endpoints serve HTML pages and are independent of the multi-database architecture.
No database session or authentication is required for these routes.
"""

from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter(tags=["pages"])
PAGES_DIR = Path(__file__).resolve().parents[4] / "client" / "pages"


def _read_page(filename: str) -> HTMLResponse:
    return HTMLResponse(content=(PAGES_DIR / filename).read_text(encoding="utf-8"))


@router.get("/", response_class=HTMLResponse)
async def login_page():
    """Serve the login/signup page."""
    return _read_page("login.html")


@router.get("/start", response_class=HTMLResponse)
async def start_page():
    """Serve the main chat interface."""
    return _read_page("chat.html")


@router.get("/chat/{conversation_id}", response_class=HTMLResponse)
async def chat_page(conversation_id: str):
    """Serve the chat interface for a specific conversation."""
    return _read_page("chat.html")


@router.get("/org/register", response_class=HTMLResponse)
async def org_register_page():
    """Serve the organization registration page."""
    return _read_page("org_login.html")


@router.get("/admin/dashboard", response_class=HTMLResponse)
async def admin_dashboard_page():
    """Serve the analytics dashboard (requires authentication, handled by frontend JS)."""
    return _read_page("admin_dashboard.html")


@router.get("/admin", response_class=HTMLResponse)
async def admin_panel_page():
    """Serve the admin management panel (users, API keys, model assignments, departments, teams)."""
    return _read_page("admin.html")