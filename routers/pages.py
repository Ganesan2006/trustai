# routers/pages.py
"""
Static page routes for the frontend application.
These endpoints serve HTML pages and are independent of the multi-database architecture.
No database session or authentication is required for these routes.
"""

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter(tags=["pages"])


@router.get("/", response_class=HTMLResponse)
async def login_page():
    """Serve the login/signup page."""
    with open("static/login.html", "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())


@router.get("/start", response_class=HTMLResponse)
async def start_page():
    """Serve the main chat interface."""
    with open("static/chat.html", "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())


@router.get("/org/register", response_class=HTMLResponse)
async def org_register_page():
    """Serve the organization registration page."""
    with open("static/org_login.html", "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())


@router.get("/admin/dashboard", response_class=HTMLResponse)
async def admin_dashboard_page():
    """Serve the analytics dashboard (requires authentication, handled by frontend JS)."""
    with open("static/admin_dashboard.html", "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())


@router.get("/admin", response_class=HTMLResponse)
async def admin_panel_page():
    """Serve the admin management panel (users, API keys, model assignments, departments, teams)."""
    with open("static/admin.html", "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())